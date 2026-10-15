import { FormEvent, useEffect, useRef, useState } from "react";

import { ApiError, Session, api } from "../api";

type Concept = { concept_id: number; name: string };
type Note = { id: number; title: string; concept: string | null; status: "pending" | "ready" | "failed"; detail: string | null };

const MAX_PDF_BYTES = 4_000_000;
const MAX_TEXT_CHARS = 50_000;
const STATUS_LABEL: Record<Note["status"], string> = {
  pending: "being prepared",
  ready: "ready",
  failed: "failed",
};
const pretty = (name: string) => name.replace(/_/g, " ");

function toBase64(bytes: ArrayBuffer): string {
  let binary = "";
  const view = new Uint8Array(bytes);
  for (let i = 0; i < view.length; i += 0x8000) binary += String.fromCharCode(...view.subarray(i, i + 0x8000));
  return btoa(binary);
}

/** F-03: course notes as pasted text or a .md, .txt or .pdf file. Students are helped from these notes. */
export function NotesPage({ session, courseId }: { session: Session; courseId: number }) {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [title, setTitle] = useState("");
  const [concept, setConcept] = useState("");
  const [pasted, setPasted] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = () =>
    api<Note[]>(`/courses/${courseId}/documents`, session)
      .then(setNotes)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
    api<Concept[]>(`/courses/${courseId}/concepts`, session).then(setConcepts).catch(() => undefined);
  }, [courseId]);

  // Notes are embedded in the background; check again until none is waiting.
  useEffect(() => {
    if (!notes?.some((n) => n.status === "pending")) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [notes]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSent(null);
    setBusy(true);
    try {
      const body: Record<string, unknown> = { title, ...(concept ? { concept } : {}) };
      if (file) {
        const isPdf = file.name.toLowerCase().endsWith(".pdf");
        if (isPdf) {
          if (file.size > MAX_PDF_BYTES) throw new Error("The PDF is larger than 4 MB.");
          body.pdf_base64 = toBase64(await file.arrayBuffer());
        } else {
          body.text = await file.text();
        }
        body.source_ref = file.name;
      } else {
        body.text = pasted;
      }
      if (typeof body.text === "string" && body.text.length > MAX_TEXT_CHARS)
        throw new Error(`The text is longer than ${MAX_TEXT_CHARS.toLocaleString()} characters. Split it into smaller notes.`);
      await api(`/courses/${courseId}/documents`, session, { body });
      setSent(`"${title}" was added and is being prepared.`);
      setTitle("");
      setPasted("");
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      await load();
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : "The server could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p>
        <a href={`#/course/${courseId}`}>Back to problems</a>
      </p>
      <h1>Course notes</h1>
      <p>
        Students' explanations and the assistant draw on these notes and cite them. A note is cut into sections and
        prepared in the background, which takes a few seconds.
      </p>

      <form className="stack" onSubmit={upload}>
        <label>
          Title
          <input value={title} maxLength={200} required onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          Concept
          <select value={concept} onChange={(e) => setConcept(e.target.value)}>
            <option value="">Not tied to one concept</option>
            {concepts.map((c) => (
              <option key={c.concept_id} value={c.name}>
                {pretty(c.name)}
              </option>
            ))}
          </select>
          <small>Notes tied to a concept are looked up first when a student fails a problem on that concept.</small>
        </label>
        <label>
          File (.md, .txt or .pdf, PDF up to 4 MB)
          <input
            ref={fileInput}
            type="file"
            accept=".md,.txt,.pdf,text/markdown,text/plain,application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        {!file && (
          <label>
            Or paste the text
            <textarea value={pasted} rows={8} required={!file} onChange={(e) => setPasted(e.target.value)} />
            <small>Use headings (## Heading) to mark sections. A PDF must contain text, not scanned images.</small>
          </label>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {sent && <p role="status">{sent}</p>}
        <p>
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "Uploading…" : "Add notes"}
          </button>
        </p>
      </form>

      <h2>Notes in this course</h2>
      {notes && notes.length === 0 && <p className="empty">No notes yet. Add the first one above.</p>}
      <ul className="rows">
        {notes?.map((n) => (
          <li key={n.id}>
            <span className="grow">
              {n.title} {n.concept && <small>({pretty(n.concept)})</small>}
              {n.status === "failed" && n.detail && <small className="error"> {n.detail}</small>}
            </span>
            <span className="tag">{STATUS_LABEL[n.status]}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
