import { FormEvent, useEffect, useState } from "react";

import { ApiError, Problem, Session, api } from "../api";

export type Status = "complete" | "in_progress" | "late" | "missing" | "not_started";
export type Assignment = {
  id: number;
  title: string;
  due_at: string;
  possible: number;
  problems: { problem_id: number; title: string; points: number }[];
  mine: { score: number; with_late: number; possible: number; status: Status } | null;
};

export const STATUS_TEXT: Record<Status, string> = {
  complete: "Complete",
  in_progress: "In progress",
  late: "Late work",
  missing: "Missing",
  not_started: "Not started",
};

export const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
export const points = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));

/** The value a datetime-local input needs: the viewer's local time, to the minute. */
function localInput(iso: string): string {
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

/** F-04: what is due in the course, with the student's own score and status. */
export function StudentAssignments({ session, courseId }: { session: Session; courseId: number }) {
  const [items, setItems] = useState<Assignment[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Assignment[]>(`/courses/${courseId}/assignments`, session)
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, [courseId]);

  if (error) return <p role="alert" className="error">{error}</p>;
  if (!items || items.length === 0) return null;
  return (
    <section>
      <h2>Assignments</h2>
      <ul className="rows">
        {items.map((a) => (
          <li key={a.id}>
            <span className="grow">
              <strong>{a.title}</strong>
              <br />
              <small>
                Due {when(a.due_at)} · {a.problems.map((p) => p.title).join(", ")}
              </small>
            </span>
            {a.mine && (
              <span className={`status status-${a.mine.status}`}>
                {STATUS_TEXT[a.mine.status]} · {points(a.mine.score)} / {points(a.possible)}
                {a.mine.status === "late" && <small> (with late work {points(a.mine.with_late)})</small>}
              </span>
            )}
          </li>
        ))}
      </ul>
      <small>Your best attempt before the due time counts. Work handed in late is shown but not counted.</small>
    </section>
  );
}

type Draft = { id: number | null; title: string; due: string; picked: Record<number, number> };
const EMPTY: Draft = { id: null, title: "", due: "", picked: {} };

/** F-04: the instructor creates, edits and deletes the course's assignments. */
export function AssignmentsPage({ session, courseId }: { session: Session; courseId: number }) {
  const [items, setItems] = useState<Assignment[] | null>(null);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api<Assignment[]>(`/courses/${courseId}/assignments`, session)
      .then(setItems)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
    api<{ problems: Problem[] }>(`/problems?course_id=${courseId}`, session)
      .then((r) => setProblems(r.problems.filter((p) => p.kind === "code")))
      .catch((e: Error) => setError(e.message));
  }, [courseId]);

  function edit(a: Assignment) {
    setDraft({
      id: a.id,
      title: a.title,
      due: localInput(a.due_at),
      picked: Object.fromEntries(a.problems.map((p) => [p.problem_id, p.points])),
    });
    window.scrollTo({ top: 0 });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      title: draft.title,
      due_at: new Date(draft.due).toISOString(),
      problems: Object.entries(draft.picked).map(([id, p]) => ({ problem_id: Number(id), points: p })),
    };
    try {
      const path = `/courses/${courseId}/assignments${draft.id ? `/${draft.id}` : ""}`;
      await api(path, session, { method: draft.id ? "PUT" : "POST", body });
      setDraft(EMPTY);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the assignment.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(a: Assignment) {
    if (!window.confirm(`Delete "${a.title}"? Students' submissions are kept.`)) return;
    try {
      await api(`/courses/${courseId}/assignments/${a.id}`, session, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete the assignment.");
    }
  }

  const toggle = (id: number, on: boolean) => {
    const picked = { ...draft.picked };
    if (on) picked[id] = 1;
    else delete picked[id];
    setDraft({ ...draft, picked });
  };

  return (
    <>
      <p>
        <a href={`#/course/${courseId}`}>Back to problems</a> · <a href={`#/course/${courseId}/gradebook`}>Gradebook</a>
      </p>
      <h1>Assignments</h1>
      {error && <p role="alert" className="error">{error}</p>}

      <form className="stack" onSubmit={save}>
        <fieldset>
          <legend>{draft.id ? "Edit assignment" : "New assignment"}</legend>
          <label>
            Title
            <input value={draft.title} maxLength={200} required onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </label>
          <label>
            Due (your local time)
            <input type="datetime-local" value={draft.due} required onChange={(e) => setDraft({ ...draft, due: e.target.value })} />
          </label>
          <p>Problems and points</p>
          {problems.length === 0 && <p className="empty">This course has no coding problems yet.</p>}
          {problems.map((p) => (
            <div key={p.id} className="concept-pick">
              <label className="inline">
                <input type="checkbox" checked={p.id in draft.picked} onChange={(e) => toggle(p.id, e.target.checked)} />
                {p.title}
              </label>
              {p.id in draft.picked && (
                <label className="inline">
                  Points
                  <input
                    type="number"
                    min={0.5}
                    max={100}
                    step={0.5}
                    value={draft.picked[p.id]}
                    onChange={(e) => setDraft({ ...draft, picked: { ...draft.picked, [p.id]: Number(e.target.value) } })}
                  />
                </label>
              )}
            </div>
          ))}
          {draft.id && <small>Changing the problems or the due date changes every student's score straight away.</small>}
        </fieldset>
        <p className="actions">
          <button className="primary" type="submit" disabled={busy || Object.keys(draft.picked).length === 0}>
            {draft.id ? "Save changes" : "Create assignment"}
          </button>
          {draft.id && (
            <button type="button" onClick={() => setDraft(EMPTY)}>
              Cancel
            </button>
          )}
        </p>
      </form>

      <h2>In this course</h2>
      {items && items.length === 0 && <p className="empty">No assignments yet.</p>}
      <ul className="rows">
        {items?.map((a) => (
          <li key={a.id}>
            <span className="grow">
              <strong>{a.title}</strong>
              <br />
              <small>
                Due {when(a.due_at)} · {points(a.possible)} points · {a.problems.map((p) => p.title).join(", ")}
              </small>
            </span>
            <button onClick={() => edit(a)}>Edit</button>
            <button className="link" onClick={() => remove(a)}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
