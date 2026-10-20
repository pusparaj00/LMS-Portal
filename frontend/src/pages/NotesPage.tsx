import { FormEvent, useEffect, useRef, useState } from "react";

import { ApiError, Session, api } from "../api";

type Concept = { concept_id: number; name: string };
type Note = { id: number; title: string; concept: string | null; status: "pending" | "ready" | "failed"; detail: string | null; visible_to_students: boolean };

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
  const [visible, setVisible] = useState(false);
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

  async function remove(note: Note) {
    if (!window.confirm(`Delete the notes "${note.title}"? The assistant will no longer quote them.`)) return;
    setError(null);
    try {
      await api(`/courses/${courseId}/documents/${note.id}`, session, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The notes could not be deleted.");
    }
  }

  async function setShown(note: Note, shown: boolean, confirmSolution = false): Promise<void> {
    setError(null);
    try {
      await api(`/courses/${courseId}/documents/${note.id}`, session, {
        method: "PATCH",
        body: { visible_to_students: shown, confirm_solution: confirmSolution },
      });
      await load();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && window.confirm(`${e.message}\n\nShow it to students anyway?`)) {
        return setShown(note, shown, true);
      }
      setError(e instanceof ApiError ? e.message : "The notes could not be changed.");
    }
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSent(null);
    setBusy(true);
    try {
      const body: Record<string, unknown> = { title, visible_to_students: visible, ...(concept ? { concept } : {}) };
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
      try {
        await api(`/courses/${courseId}/documents`, session, { body });
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 409 && window.confirm(`${e.message}\n\nShow it to students anyway?`))) throw e;
        await api(`/courses/${courseId}/documents`, session, { body: { ...body, confirm_solution: true } });
      }
      setSent(`"${title}" was added and is being prepared.`);
      setTitle("");
      setPasted("");
      setVisible(false);
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
        Students' explanations and the assistant draw on all of these notes and cite them. Notes you show to students can
        also be read under Classwork. A note is cut into sections and
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
        <label className="inline">
          <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
          Show these notes to students
        </label>
        <small>
          Students read them under Classwork. The assistant uses the notes either way. Do not show notes that contain a
          solution.
        </small>
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
            <span className="tag">{n.visible_to_students ? "shown to students" : "hidden from students"}</span>
            <button className="link" onClick={() => setShown(n, !n.visible_to_students)}>
              {n.visible_to_students ? "Hide from students" : "Show to students"}
            </button>
            <button className="link" onClick={() => remove(n)}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
