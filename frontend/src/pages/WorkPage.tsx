import { FormEvent, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { Comments } from "./Comments";
import { when } from "./AssignmentsPage";
import { MAX_FILE_BYTES, MyWork, downloadWorkFile, sizeText, toBase64 } from "./workTypes";

const STATE_TEXT: Record<MyWork["state"], string> = {
  assigned: "Assigned",
  missing: "Missing",
  turned_in: "Turned in",
  returned: "Returned",
};

/** F-73, F-74, F-77: a student's hand-in for one assignment, with the score and feedback once it is returned. */
export function WorkPage({ session, courseId, assignmentId }: { session: Session; courseId: number; assignmentId: number }) {
  const base = `/courses/${courseId}/assignments/${assignmentId}/work`;
  const [work, setWork] = useState<MyWork | null>(null);
  const [text, setText] = useState("");
  const [link, setLink] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const show = (w: MyWork) => {
    setWork(w);
    setText(w.text ?? "");
    setLink(w.link ?? "");
  };

  useEffect(() => {
    api<MyWork>(base, session).then(show).catch((e: Error) => setError(e.message));
  }, [assignmentId]);

  async function run(action: () => Promise<MyWork>, failure: string) {
    setBusy(true);
    setError(null);
    try {
      show(await action());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : failure);
    } finally {
      setBusy(false);
    }
  }

  async function save(event: { preventDefault(): void }, removeFile = false) {
    event.preventDefault();
    if (file && file.size > MAX_FILE_BYTES) return setError(`The file is larger than ${sizeText(MAX_FILE_BYTES)}.`);
    const body = {
      text: text.trim() || null,
      link: link.trim() || null,
      remove_file: removeFile,
      ...(file ? { file_base64: await toBase64(file), file_name: file.name } : {}),
    };
    await run(() => api<MyWork>(`${base}/draft`, session, { body }), "Could not save your work.");
    setFile(null);
    setFileKey((k) => k + 1);
  }

  const post = (tail: string, failure: string) => run(() => api<MyWork>(`${base}${tail}`, session, { method: "POST" }), failure);
  const locked = work !== null && (work.state === "turned_in" || work.state === "returned");

  return (
    <>
      <p>
        <a href={`#/course/${courseId}`}>Back to the course</a>
      </p>
      <h1>{work?.title ?? "Assignment"}</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {work && (
        <>
          <p>
            <span className={`status status-${work.state === "turned_in" ? "in_progress" : work.state === "returned" ? "complete" : work.state}`}>
              {STATE_TEXT[work.state]}
              {work.late && work.state !== "assigned" && " (late)"}
            </span>{" "}
            <small>
              Due {when(work.due_at)} · {work.points} points
            </small>
          </p>
          <p className="instructions">{work.instructions}</p>

          {work.state === "returned" && (
            <section className="notice">
              <h2>
                Your score: {work.score} of {work.points}
              </h2>
              {work.feedback && <p className="comment-body">{work.feedback}</p>}
              {work.late && <small>Handed in late, so this score is not counted in your grade.</small>}
            </section>
          )}

          <form className="stack" onSubmit={save}>
            <fieldset disabled={locked || busy}>
              <legend>Your work</legend>
              {work.allow_text && (
                <label>
                  Text
                  <textarea value={text} rows={6} maxLength={20000} onChange={(e) => setText(e.target.value)} />
                </label>
              )}
              {work.allow_link && (
                <label>
                  Link
                  <input type="url" value={link} placeholder="https://…" maxLength={2000} onChange={(e) => setLink(e.target.value)} />
                </label>
              )}
              {work.allow_file && (
                <>
                  {work.file_name && (
                    <p>
                      File: <button type="button" className="link" onClick={() => downloadWorkFile(session, `${base}/file`, work.file_name ?? "work").catch((e: Error) => setError(e.message))}>{work.file_name}</button>{" "}
                      <small>({sizeText(work.file_size ?? 0)})</small>{" "}
                      {!locked && (
                        <button type="button" className="link" onClick={(e) => save(e, true)}>
                          Remove
                        </button>
                      )}
                    </p>
                  )}
                  <label>
                    {work.file_name ? "Replace the file" : "Attach a file"} (PDF, text, Python or zip, up to {sizeText(MAX_FILE_BYTES)})
                    <input key={fileKey} type="file" accept=".pdf,.txt,.py,.zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                  </label>
                </>
              )}
            </fieldset>
            <p className="actions">
              {!locked && (
                <>
                  <button type="submit" disabled={busy}>
                    Save draft
                  </button>
                  <button type="button" className="primary" disabled={busy} onClick={() => post("/turn-in", "Could not turn in your work.")}>
                    Turn in
                  </button>
                </>
              )}
              {work.state === "turned_in" && (
                <button type="button" disabled={busy} onClick={() => post("/unsubmit", "Could not unsubmit.")}>
                  Unsubmit
                </button>
              )}
              {work.turned_in_at && <small>Turned in {when(work.turned_in_at)}</small>}
            </p>
            {work.state === "turned_in" && <small>You can unsubmit until your instructor has graded this work.</small>}
          </form>

          <Comments
            comments={work.comments}
            teacherView={false}
            onSend={async (body) => show(await api<MyWork>(`${base}/comments`, session, { body: { body } }))}
          />
        </>
      )}
    </>
  );
}
