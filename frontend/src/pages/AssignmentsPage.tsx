import { FormEvent, useEffect, useState } from "react";

import { ApiError, Problem, Session, api } from "../api";
import { QuizSummary } from "./quizTypes";

export type Status = "complete" | "in_progress" | "late" | "missing" | "not_started";
export type Assignment = {
  id: number;
  title: string;
  due_at: string;
  possible: number;
  problems: { problem_id: number; title: string; points: number }[];
  quizzes: { quiz_id: number; title: string; points: number; published: boolean }[];
  work: WorkConfig | null;
  module_id: number | null;
  category_id: number | null;
  students: number[] | null;
  mine: { score: number; with_late: number; possible: number; status: Status } | null;
};

export type WorkConfig = {
  instructions: string;
  points: number;
  allow_file: boolean;
  allow_link: boolean;
  allow_text: boolean;
  rubric_id: number | null;
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
  const [topics, setTopics] = useState<{ id: number; title: string }[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Assignment[]>(`/courses/${courseId}/assignments`, session)
      .then(setItems)
      .catch((e: Error) => setError(e.message));
    // a student is only sent the topics that are published, so work under a hidden topic is filed under "Other work"
    api<{ modules: { id: number; title: string }[] }>(`/courses/${courseId}/content`, session)
      .then((r) => setTopics(r.modules))
      .catch(() => setTopics([]));
  }, [courseId]);

  if (error) return <p role="alert" className="error">{error}</p>;
  if (!items || items.length === 0) return null;

  const row = (a: Assignment) => (
    <li key={a.id}>
      <span className="grow">
        <strong>{a.title}</strong>
        <br />
        <small>
          Due {when(a.due_at)} ·{" "}
          {[...a.problems.map((p) => p.title), ...a.quizzes.map((q) => `Quiz: ${q.title}`), ...(a.work ? ["Handed-in work"] : [])].join(", ")}
        </small>
        {a.quizzes.map((q) => (
          <small key={q.quiz_id}>
            {" "}
            {q.published ? <a href={`#/course/${courseId}/quiz/${q.quiz_id}`}>Take {q.title}</a> : `${q.title} is not open yet`}
          </small>
        ))}
        {a.work && (
          <small>
            {" "}
            <a href={`#/course/${courseId}/assignment/${a.id}`}>Hand in your work</a>
          </small>
        )}
      </span>
      {a.mine && (
        <span className={`status status-${a.mine.status}`}>
          {STATUS_TEXT[a.mine.status]} · {points(a.mine.score)} / {points(a.possible)}
          {a.mine.status === "late" && <small> (with late work {points(a.mine.with_late)})</small>}
        </span>
      )}
    </li>
  );

  const known = new Set(topics.map((t) => t.id));
  const groups = [
    ...topics.map((t) => ({ title: t.title, rows: items.filter((a) => a.module_id === t.id) })),
    { title: "Other work", rows: items.filter((a) => a.module_id === null || !known.has(a.module_id)) },
  ].filter((g) => g.rows.length > 0);

  return (
    <section>
      <h2>Assignments</h2>
      {groups.map((g) => (
        <div key={g.title}>
          {(groups.length > 1 || g.title !== "Other work") && <h3>{g.title}</h3>}
          <ul className="rows">{g.rows.map(row)}</ul>
        </div>
      ))}
      <small>Your best attempt before the due time counts. Work handed in late is shown but not counted.</small>
    </section>
  );
}

type WorkDraft = WorkConfig & { on: boolean };
const NO_WORK: WorkDraft = { on: false, instructions: "", points: 10, allow_file: true, allow_link: true, allow_text: true, rubric_id: null };
type Draft = {
  id: number | null;
  title: string;
  due: string;
  picked: Record<number, number>;
  quizzes: Record<number, number>;
  work: WorkDraft;
  moduleId: string;
  categoryId: string;
  given: "all" | "selected";
  chosen: number[];
};
const EMPTY: Draft = { id: null, title: "", due: "", picked: {}, quizzes: {}, work: NO_WORK, moduleId: "", categoryId: "", given: "all", chosen: [] };
type Topic = { id: number; title: string };
type Classmate = { user_id: number; label: string };

/** F-04: the instructor creates, edits and deletes the course's assignments. */
export function AssignmentsPage({ session, courseId }: { session: Session; courseId: number }) {
  const [items, setItems] = useState<Assignment[] | null>(null);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [students, setStudents] = useState<Classmate[]>([]);
  const [categories, setCategories] = useState<{ id: number; name: string }[]>([]);
  const [rubrics, setRubrics] = useState<{ id: number; title: string; max_points: number }[]>([]);
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
    api<QuizSummary[]>(`/courses/${courseId}/quizzes`, session)
      .then(setQuizzes)
      .catch((e: Error) => setError(e.message));
    api<{ modules: Topic[] }>(`/courses/${courseId}/content`, session)
      .then((r) => setTopics(r.modules))
      .catch(() => setTopics([]));
    api<{ students: Classmate[] | null }>(`/courses/${courseId}/people`, session)
      .then((r) => setStudents(r.students ?? []))
      .catch(() => setStudents([]));
    api<{ id: number; name: string }[]>(`/courses/${courseId}/categories`, session)
      .then(setCategories)
      .catch(() => setCategories([]));
    api<{ id: number; title: string; max_points: number }[]>(`/courses/${courseId}/rubrics`, session)
      .then(setRubrics)
      .catch(() => setRubrics([]));
  }, [courseId]);

  function edit(a: Assignment) {
    setDraft({
      id: a.id,
      title: a.title,
      due: localInput(a.due_at),
      picked: Object.fromEntries(a.problems.map((p) => [p.problem_id, p.points])),
      quizzes: Object.fromEntries(a.quizzes.map((q) => [q.quiz_id, q.points])),
      work: a.work ? { ...a.work, on: true } : NO_WORK,
      moduleId: a.module_id === null ? "" : String(a.module_id),
      categoryId: a.category_id === null ? "" : String(a.category_id),
      given: a.students === null ? "all" : "selected",
      chosen: a.students ?? [],
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
      quizzes: Object.entries(draft.quizzes).map(([id, p]) => ({ quiz_id: Number(id), points: p })),
      work: draft.work.on ? { instructions: draft.work.instructions, points: draft.work.points, allow_file: draft.work.allow_file, allow_link: draft.work.allow_link, allow_text: draft.work.allow_text, rubric_id: draft.work.rubric_id } : null,
      module_id: draft.moduleId ? Number(draft.moduleId) : null,
      category_id: draft.categoryId ? Number(draft.categoryId) : null,
      students: draft.given === "selected" ? draft.chosen : null,
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
          <p>Quizzes and points</p>
          {quizzes.length === 0 && (
            <p className="empty">
              This course has no quizzes yet. <a href={`#/course/${courseId}/quizzes`}>Create one</a>.
            </p>
          )}
          {quizzes.map((q) => (
            <div key={q.id} className="concept-pick">
              <label className="inline">
                <input
                  type="checkbox"
                  checked={q.id in draft.quizzes}
                  onChange={(e) => {
                    const next = { ...draft.quizzes };
                    if (e.target.checked) next[q.id] = 1;
                    else delete next[q.id];
                    setDraft({ ...draft, quizzes: next });
                  }}
                />
                {q.title}
                {!q.published && " (draft: students cannot take it yet)"}
              </label>
              {q.id in draft.quizzes && (
                <label className="inline">
                  Points
                  <input
                    type="number"
                    min={0.5}
                    max={100}
                    step={0.5}
                    value={draft.quizzes[q.id]}
                    onChange={(e) => setDraft({ ...draft, quizzes: { ...draft.quizzes, [q.id]: Number(e.target.value) } })}
                  />
                </label>
              )}
            </div>
          ))}
          <label>
            Topic
            <select value={draft.moduleId} onChange={(e) => setDraft({ ...draft, moduleId: e.target.value })}>
              <option value="">No topic</option>
              {topics.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            Grade category
            <select value={draft.categoryId} onChange={(e) => setDraft({ ...draft, categoryId: e.target.value })}>
              <option value="">No category (not part of the weighted grade)</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>Given to</legend>
            <label className="inline">
              <input type="radio" name="given" checked={draft.given === "all"} onChange={() => setDraft({ ...draft, given: "all" })} />
              The whole class
            </label>
            <label className="inline">
              <input type="radio" name="given" checked={draft.given === "selected"} onChange={() => setDraft({ ...draft, given: "selected" })} />
              Chosen students
            </label>
            {draft.given === "selected" && (
              <>
                {students.length === 0 && <p className="empty">Nobody has joined the class yet.</p>}
                {students.map((s) => (
                  <label key={s.user_id} className="inline">
                    <input
                      type="checkbox"
                      checked={draft.chosen.includes(s.user_id)}
                      onChange={(e) =>
                        setDraft({ ...draft, chosen: e.target.checked ? [...draft.chosen, s.user_id] : draft.chosen.filter((id) => id !== s.user_id) })
                      }
                    />
                    {s.label}
                  </label>
                ))}
              </>
            )}
          </fieldset>
          <p>Handed-in work</p>
          <label className="inline">
            <input type="checkbox" checked={draft.work.on} onChange={(e) => setDraft({ ...draft, work: { ...draft.work, on: e.target.checked } })} />
            Ask students to hand in work (a file, a link or text) that you score yourself
          </label>
          {draft.work.on && (
            <>
              <label>
                Instructions
                <textarea value={draft.work.instructions} rows={4} maxLength={5000} required onChange={(e) => setDraft({ ...draft, work: { ...draft.work, instructions: e.target.value } })} />
              </label>
              <label className="inline">
                Points
                <input type="number" min={0.5} max={100} step={0.5} value={draft.work.points} disabled={draft.work.rubric_id !== null} onChange={(e) => setDraft({ ...draft, work: { ...draft.work, points: Number(e.target.value) } })} />
              </label>
              <label>
                Rubric
                <select
                  value={draft.work.rubric_id ?? ""}
                  onChange={(e) => {
                    const chosen = rubrics.find((r) => r.id === Number(e.target.value));
                    setDraft({ ...draft, work: { ...draft.work, rubric_id: chosen ? chosen.id : null, points: chosen ? chosen.max_points : draft.work.points } });
                  }}
                >
                  <option value="">No rubric: I give a score</option>
                  {rubrics.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title} ({r.max_points} points)
                    </option>
                  ))}
                </select>
                <small>
                  A rubric sets the points. <a href={`#/course/${courseId}/rubrics`}>Write a rubric</a>.
                </small>
              </label>
              {(["allow_file", "allow_link", "allow_text"] as const).map((k) => (
                <label key={k} className="inline">
                  <input type="checkbox" checked={draft.work[k]} onChange={(e) => setDraft({ ...draft, work: { ...draft.work, [k]: e.target.checked } })} />
                  Accept {k === "allow_file" ? "a file" : k === "allow_link" ? "a link" : "text"}
                </label>
              ))}
            </>
          )}
          {draft.id && <small>Changing the problems or the due date changes every student's score straight away.</small>}
        </fieldset>
        <p className="actions">
          <button className="primary" type="submit" disabled={busy || Object.keys(draft.picked).length + Object.keys(draft.quizzes).length + (draft.work.on ? 1 : 0) === 0 || (draft.given === "selected" && draft.chosen.length === 0)}>
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
                Due {when(a.due_at)} · {points(a.possible)} points · {[...a.problems.map((p) => p.title), ...a.quizzes.map((q) => `Quiz: ${q.title}`), ...(a.work ? ["Handed-in work"] : [])].join(", ")}
                {a.students !== null && ` · given to ${a.students.length} ${a.students.length === 1 ? "student" : "students"}`}
                {a.module_id !== null && ` · topic: ${topics.find((t) => t.id === a.module_id)?.title ?? "removed"}`}
              </small>
            </span>
            {a.work && <a className="button" href={`#/course/${courseId}/assignment/${a.id}/review`}>Review work</a>}
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
