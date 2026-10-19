import { FormEvent, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";

type State = "published" | "draft" | "scheduled";
type Announcement = {
  id: number;
  title: string;
  body: string;
  created_at: string;
  edited_at: string | null;
  state: State;
  publish_at: string | null;
};
type Mode = "publish" | "draft" | "schedule";
type Draft = { id: number | null; title: string; body: string; mode: Mode; at: string };

const SHOWN = 3;
const EMPTY: Draft = { id: null, title: "", body: "", mode: "publish", at: "" };
const localInput = (iso: string) => {
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const MODE_TEXT: Record<Mode, string> = { publish: "Post now", draft: "Save as a draft (only teachers see it)", schedule: "Schedule for later" };
const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

/** F-05: the course's announcements, newest first. The teacher can post, edit and delete. Text is shown as text. */
export function Announcements({ session, courseId }: { session: Session; courseId: number }) {
  const [items, setItems] = useState<Announcement[] | null>(null);
  const [all, setAll] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const teacher = session.role === "instructor";

  const load = () =>
    api<Announcement[]>(`/courses/${courseId}/announcements`, session)
      .then(setItems)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, [courseId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const target = `/courses/${courseId}/announcements${draft.id ? `/${draft.id}` : ""}`;
      await api(target, session, {
        method: draft.id ? "PUT" : "POST",
        body: { title: draft.title, body: draft.body, mode: draft.mode, publish_at: draft.mode === "schedule" ? new Date(draft.at).toISOString() : null },
      });
      setDraft(null);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The announcement could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(a: Announcement) {
    if (!window.confirm(`Delete the announcement "${a.title}"?`)) return;
    try {
      await api(`/courses/${courseId}/announcements/${a.id}`, session, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The announcement could not be deleted.");
    }
  }

  if (!items) return error ? <p role="alert" className="error">{error}</p> : null;
  if (items.length === 0 && !teacher) return null;
  const shown = all ? items : items.slice(0, SHOWN);

  return (
    <section className="announcements" aria-label="Announcements">
      <h2>Announcements</h2>
      {error && <p role="alert" className="error">{error}</p>}
      {teacher && !draft && (
        <p>
          <button onClick={() => setDraft(EMPTY)}>Post an announcement</button>
        </p>
      )}
      {draft && (
        <form className="stack" onSubmit={save}>
          <label>
            Title
            <input value={draft.title} maxLength={200} required onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </label>
          <label>
            Text
            <textarea rows={4} value={draft.body} maxLength={5000} required onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
          </label>
          <label>
            When
            <select value={draft.mode} onChange={(e) => setDraft({ ...draft, mode: e.target.value as Mode })}>
              {(Object.keys(MODE_TEXT) as Mode[]).map((m) => (
                <option key={m} value={m}>
                  {MODE_TEXT[m]}
                </option>
              ))}
            </select>
          </label>
          {draft.mode === "schedule" && (
            <label>
              Publish at (your local time)
              <input type="datetime-local" value={draft.at} required onChange={(e) => setDraft({ ...draft, at: e.target.value })} />
            </label>
          )}
          <p className="actions">
            <button className="primary" type="submit" disabled={busy}>
              {draft.id ? "Save changes" : draft.mode === "publish" ? "Post" : draft.mode === "draft" ? "Save draft" : "Schedule"}
            </button>
            <button type="button" onClick={() => setDraft(null)}>
              Cancel
            </button>
          </p>
        </form>
      )}
      {items.length === 0 && <p className="empty">No announcements yet.</p>}
      {shown.map((a) => (
        <article key={a.id} className="announcement">
          <h3>
            {a.title} {a.state === "draft" && <span className="flag">draft</span>}
            {a.state === "scheduled" && <span className="flag">scheduled</span>}
          </h3>
          <small>
            {a.state === "scheduled" && a.publish_at ? `Will be posted ${when(a.publish_at)}` : `Posted ${when(a.publish_at ?? a.created_at)}`}
            {a.edited_at && ` · edited ${when(a.edited_at)}`}
          </small>
          <p className="announcement-body">{a.body}</p>
          {teacher && (
            <p className="actions">
              <button
                onClick={() =>
                  setDraft({
                    id: a.id,
                    title: a.title,
                    body: a.body,
                    mode: a.state === "draft" ? "draft" : a.state === "scheduled" ? "schedule" : "publish",
                    at: a.publish_at ? localInput(a.publish_at) : "",
                  })
                }
              >
                Edit
              </button>
              <button className="link" onClick={() => remove(a)}>
                Delete
              </button>
            </p>
          )}
        </article>
      ))}
      {items.length > SHOWN && (
        <button className="link" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </section>
  );
}
