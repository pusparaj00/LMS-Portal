import { FormEvent, useState } from "react";

import { Comment } from "./workTypes";
import { when } from "./AssignmentsPage";

/** F-77: the private thread between a student and their instructor about one piece of work. */
export function Comments({ comments, onSend, teacherView }: { comments: Comment[]; onSend: (body: string) => Promise<void>; teacherView: boolean }) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    try {
      await onSend(body);
      setBody("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h3>Private comments</h3>
      <small>{teacherView ? "Only you and this student can read these." : "Only you and your instructor can read these."}</small>
      {comments.length === 0 && <p className="empty">No comments yet.</p>}
      <ul className="rows">
        {comments.map((c) => (
          <li key={c.id}>
            <span className="grow">
              <strong>{c.mine ? "You" : c.from_teacher ? "Instructor" : "Student"}</strong> <small>{when(c.created_at)}</small>
              <br />
              <span className="comment-body">{c.body}</span>
            </span>
          </li>
        ))}
      </ul>
      <form className="item-form" onSubmit={send}>
        <input value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add a private comment" maxLength={2000} aria-label="Private comment" />
        <button type="submit" disabled={busy || !body.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
