import { ReactNode, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { ReplyText } from "./ReplyText";

type NoteItem = { id: number; title: string; concept: string | null };
type NoteBody = NoteItem & { text: string };

const pretty = (name: string) => name.replace(/_/g, " ");

/** F-93: the notes the instructor shows to students, on Classwork and (a few of them) on the stream. */
export function CourseNotes({ session, courseId, compact = false }: { session: Session; courseId: number; compact?: boolean }) {
  const [notes, setNotes] = useState<NoteItem[] | null>(null);

  useEffect(() => {
    api<NoteItem[]>(`/courses/${courseId}/notes`, session)
      .then(setNotes)
      .catch(() => setNotes([]));
  }, [courseId]);

  if (!notes || notes.length === 0) return null;
  const shown = compact ? notes.slice(0, 4) : notes;
  return (
    <section className="panel" aria-label="Course notes">
      <h2>Notes to read</h2>
      <ul className="rows">
        {shown.map((n) => (
          <li key={n.id}>
            <a className="grow" href={`#/course/${courseId}/note/${n.id}`}>
              {n.title}
            </a>
            {n.concept && <span className="tag">{pretty(n.concept)}</span>}
          </li>
        ))}
      </ul>
      {compact && notes.length > shown.length && (
        <p>
          <a href={`#/course/${courseId}/classwork`}>All {notes.length} notes in Classwork</a>
        </p>
      )}
    </section>
  );
}

/** Notes mark sections with "## Heading"; each heading is shown as a heading, the text under it as formatted text. */
function NoteText({ text }: { text: string }) {
  const parts = text.split(/^##\s+(.*)$/m);
  const blocks: ReactNode[] = [];
  if (parts[0].trim()) blocks.push(<ReplyText key="intro" text={parts[0]} />);
  for (let i = 1; i < parts.length; i += 2) {
    blocks.push(
      <section key={i}>
        <h2>{parts[i]}</h2>
        <ReplyText text={parts[i + 1] ?? ""} />
      </section>,
    );
  }
  return <>{blocks}</>;
}

export function NoteReader({ session, courseId, noteId }: { session: Session; courseId: number; noteId: number }) {
  const [note, setNote] = useState<NoteBody | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<NoteBody>(`/courses/${courseId}/notes/${noteId}`, session)
      .then(setNote)
      .catch((e: Error) => setError(e instanceof ApiError && e.status === 404 ? "These notes are not available." : e.message));
  }, [courseId, noteId]);

  return (
    <>
      <p>
        <a href={`#/course/${courseId}/classwork`}>Back to classwork</a>
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {note && (
        <article>
          <h1>{note.title}</h1>
          {note.concept && <p className="tag">{pretty(note.concept)}</p>}
          <NoteText text={note.text} />
        </article>
      )}
    </>
  );
}
