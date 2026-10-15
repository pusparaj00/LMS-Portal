"""F-03, F-02, TR-S-04: notes as text or PDF, read safely; the concept list for forms."""
import base64
import io

import pytest
from pypdf import PdfWriter
from sqlalchemy import text

from app.retrieval import pdf
from tests.test_feedback_api import FakeLLM, llm, world  # noqa: F401  (fixtures)

API = "/api/v1"


def make_pdf(*pages: str) -> bytes:
    """A small but valid PDF with one line of text per page."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    font = 3 + 2 * len(pages)
    for i, line in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({line}) Tj ET"
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R"
            f" /Resources << /Font << /F1 {font} 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def blank_pdf(pages: int, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if password:
        writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def upload(client, world, **body):
    url = f"{API}/courses/{world['course']}/documents"
    return client.post(url, headers=world["instructor"], json={"title": "Uploaded notes", **body})


def stored_body(owner, document_id):
    with owner.connect() as conn:
        return conn.execute(text("SELECT body FROM documents WHERE id = :d"), {"d": document_id}).scalar_one()


def test_a_pdf_is_read_and_its_text_becomes_the_note(client, world, owner):
    response = upload(client, world, pdf_base64=b64(make_pdf("Loops repeat a block of code.", "Range stops before n.")))
    assert response.status_code == 202 and response.json()["status"] == "pending"
    body = stored_body(owner, response.json()["id"])
    assert "Loops repeat a block of code." in body and "Range stops before n." in body


def test_text_notes_still_work_and_exactly_one_source_is_required(client, world, owner):
    ok = upload(client, world, text="A short note about lists.")
    assert ok.status_code == 202 and stored_body(owner, ok.json()["id"]) == "A short note about lists."
    assert upload(client, world).status_code == 422
    assert upload(client, world, text="x", pdf_base64=b64(make_pdf("x"))).status_code == 422


@pytest.mark.parametrize(
    "data,message",
    [
        pytest.param(b"this is not a pdf at all", "not a PDF", id="not-a-pdf"),
        pytest.param(b"%PDF-1.4 but then garbage that no reader can parse", "could not be read", id="corrupt"),
        pytest.param(blank_pdf(2), "no text", id="no-text-scanned"),
        pytest.param(blank_pdf(101), "101 pages; at most 100", id="too-many-pages"),
        pytest.param(blank_pdf(1, password="secret"), "password protected", id="encrypted"),
    ],
)
def test_unusable_pdfs_are_refused_with_a_reason_and_nothing_is_stored(client, world, owner, data, message):
    with owner.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM documents WHERE course_id = :c"), {"c": world["course"]}).scalar_one()
    response = upload(client, world, pdf_base64=b64(data))
    assert response.status_code == 422 and message in response.json()["error"]["message"]
    with owner.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM documents WHERE course_id = :c"), {"c": world["course"]}).scalar_one() == before


def test_invalid_base64_is_refused(client, world):
    response = upload(client, world, pdf_base64="***not base64***")
    assert response.status_code == 422 and "base64" in response.json()["error"]["message"]


def test_a_pdf_with_too_much_text_is_refused_not_silently_cut(client, world):
    big = make_pdf(*["word " * 200] * 60)  # 60 pages of about 1,000 characters
    response = upload(client, world, pdf_base64=b64(big))
    assert response.status_code == 422 and "more than 50,000 characters" in response.json()["error"]["message"]


def test_a_pdf_over_the_size_limit_is_refused(client, world):
    response = upload(client, world, pdf_base64=b64(b"%PDF-" + b"0" * (pdf.MAX_PDF_BYTES + 10)))
    assert response.status_code == 422 and "larger than 4 MB" in response.json()["error"]["message"]


def test_only_the_notes_upload_accepts_a_large_body(client, world):
    big = {"title": "x", "pdf_base64": "A" * 1_000_000}
    assert client.post(f"{API}/courses/{world['course']}/documents", headers=world["instructor"], json=big).status_code != 413
    assert client.post(f"{API}/courses", headers=world["instructor"], json={"title": "x" * 1_000_000}).status_code == 413
    too_big = {"title": "x", "pdf_base64": "A" * 6_100_000}
    assert client.post(f"{API}/courses/{world['course']}/documents", headers=world["instructor"], json=too_big).status_code == 413


def test_the_reader_runs_apart_from_the_api_with_no_secrets_and_a_time_limit(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "must-not-be-visible-to-the-reader")
    captured = {}
    real = pdf.subprocess.run

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(pdf.subprocess, "run", spy)
    assert "hello" in pdf.extract_text(make_pdf("hello"))
    assert captured["env"] == {} and captured["timeout"] == pdf.TIMEOUT_SECONDS and captured["preexec_fn"] is pdf._limit


def test_a_reader_that_takes_too_long_is_stopped(monkeypatch):
    monkeypatch.setattr(pdf, "TIMEOUT_SECONDS", 0.01)
    with pytest.raises(pdf.PdfError, match="took too long"):
        pdf.extract_text(make_pdf("hello"))


def test_students_and_other_instructors_cannot_upload_notes(client, world, make_user):
    _, student = make_user("student")
    _, other = make_user("instructor")
    url = f"{API}/courses/{world['course']}/documents"
    assert client.post(url, headers=student, json={"title": "x", "text": "y"}).status_code == 403
    assert client.post(url, headers=other, json={"title": "x", "text": "y"}).status_code == 403


def test_the_concept_list_is_available_to_people_with_access_to_the_course(client, world, make_user):
    url = f"{API}/courses/{world['course']}/concepts"
    listed = client.get(url, headers=world["instructor"])
    assert listed.status_code == 200 and [c["name"] for c in listed.json()] == ["loops"]
    assert listed.json()[0]["concept_id"] == world["loops"]
    _, outsider = make_user("student")
    assert client.get(url, headers=outsider).status_code == 403
    _, other = make_user("instructor")
    assert client.get(url, headers=other).status_code == 403
    assert client.get(url).status_code == 401


def test_a_decompression_bomb_is_refused_quickly_and_the_api_stays_up(client, world):
    import time
    import zlib

    comp = zlib.compressobj(9)
    stream = b"".join([comp.compress(b"0" * 1_000_000) for _ in range(400)] + [comp.flush()])  # 400 MB once unpacked
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R >>",
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream"]
    data, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objs, 1):
        offsets.append(len(data))
        data += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    data += b"xref\n0 5\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    data += b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(data))
    started = time.monotonic()
    response = upload(client, world, pdf_base64=b64(data))
    assert response.status_code == 422 and time.monotonic() - started < pdf.TIMEOUT_SECONDS
    assert client.get(f"{API}/health").status_code == 200
