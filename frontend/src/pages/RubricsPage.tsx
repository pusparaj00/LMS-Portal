import { FormEvent, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";

export type Rubric = {
  id: number;
  title: string;
  max_points: number;
  used_by: number;
  criteria: { id: number; title: string; description: string | null; levels: { id: number; label: string; points: number }[]; chosen_level_id: number | null }[];
};

type LevelDraft = { label: string; points: number };
type CriterionDraft = { title: string; description: string; levels: LevelDraft[] };
type Draft = { id: number | null; title: string; criteria: CriterionDraft[] };

const blankCriterion = (): CriterionDraft => ({
  title: "",
  description: "",
  levels: [
    { label: "Needs work", points: 0 },
    { label: "Good", points: 5 },
  ],
});
const EMPTY: Draft = { id: null, title: "", criteria: [blankCriterion()] };

const toDraft = (r: Rubric): Draft => ({
  id: r.id,
  title: r.title,
  criteria: r.criteria.map((c) => ({ title: c.title, description: c.description ?? "", levels: c.levels.map((l) => ({ label: l.label, points: l.points })) })),
});

const topOf = (criteria: CriterionDraft[]) => criteria.reduce((sum, c) => sum + Math.max(0, ...c.levels.map((l) => l.points)), 0);

/** F-88: reusable rubrics. A rubric attached to handed-in work must have the same top score as the work. */
export function RubricsPage({ session, courseId }: { session: Session; courseId: number }) {
  const base = `/courses/${courseId}/rubrics`;
  const [items, setItems] = useState<Rubric[] | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api<Rubric[]>(base, session)
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  useEffect(() => {
    load();
  }, [courseId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const body = {
      title: draft.title,
      criteria: draft.criteria.map((c) => ({ title: c.title, description: c.description.trim() || null, levels: c.levels })),
    };
    try {
      await api(draft.id ? `${base}/${draft.id}` : base, session, { method: draft.id ? "PUT" : "POST", body });
      setDraft(EMPTY);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the rubric.");
    }
  }

  async function remove(r: Rubric) {
    if (!window.confirm(`Delete "${r.title}"?`)) return;
    try {
      await api(`${base}/${r.id}`, session, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete the rubric.");
    }
  }

  const setCriterion = (i: number, next: CriterionDraft) => setDraft({ ...draft, criteria: draft.criteria.map((c, n) => (n === i ? next : c)) });

  return (
    <>
      <p>
        <a href={`#/course/${courseId}/classwork`}>Back to classwork</a> · <a href={`#/course/${courseId}/assignments`}>Assignments</a>
      </p>
      <h1>Rubrics</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form className="stack" onSubmit={save}>
        <fieldset>
          <legend>{draft.id ? "Edit rubric" : "New rubric"}</legend>
          <label>
            Title
            <input value={draft.title} maxLength={200} required onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </label>
          <small>Top score: {topOf(draft.criteria)} points (the best level of every criterion added up).</small>
        </fieldset>
        {draft.criteria.map((c, i) => (
          <fieldset key={i}>
            <legend>Criterion {i + 1}</legend>
            <label>
              Name
              <input value={c.title} maxLength={200} required onChange={(e) => setCriterion(i, { ...c, title: e.target.value })} />
            </label>
            <label>
              What it looks for (optional)
              <input value={c.description} maxLength={1000} onChange={(e) => setCriterion(i, { ...c, description: e.target.value })} />
            </label>
            {c.levels.map((l, n) => (
              <div key={n} className="concept-pick">
                <label className="inline">
                  Level
                  <input
                    value={l.label}
                    maxLength={100}
                    required
                    aria-label={`Level ${n + 1} name`}
                    onChange={(e) => setCriterion(i, { ...c, levels: c.levels.map((x, k) => (k === n ? { ...x, label: e.target.value } : x)) })}
                  />
                </label>
                <label className="inline">
                  Points
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.5}
                    value={l.points}
                    aria-label={`Level ${n + 1} points`}
                    onChange={(e) => setCriterion(i, { ...c, levels: c.levels.map((x, k) => (k === n ? { ...x, points: Number(e.target.value) } : x)) })}
                  />
                </label>
                {c.levels.length > 2 && (
                  <button type="button" className="link" onClick={() => setCriterion(i, { ...c, levels: c.levels.filter((_, k) => k !== n) })}>
                    Remove level
                  </button>
                )}
              </div>
            ))}
            <p className="actions">
              {c.levels.length < 8 && (
                <button type="button" onClick={() => setCriterion(i, { ...c, levels: [...c.levels, { label: "", points: 0 }] })}>
                  Add a level
                </button>
              )}
              {draft.criteria.length > 1 && (
                <button type="button" className="link" onClick={() => setDraft({ ...draft, criteria: draft.criteria.filter((_, k) => k !== i) })}>
                  Remove criterion
                </button>
              )}
            </p>
          </fieldset>
        ))}
        <p className="actions">
          {draft.criteria.length < 20 && (
            <button type="button" onClick={() => setDraft({ ...draft, criteria: [...draft.criteria, blankCriterion()] })}>
              Add a criterion
            </button>
          )}
          <button className="primary" type="submit">
            {draft.id ? "Save changes" : "Create rubric"}
          </button>
          {draft.id && (
            <button type="button" onClick={() => setDraft(EMPTY)}>
              Cancel
            </button>
          )}
        </p>
      </form>

      <h2>In this course</h2>
      {items && items.length === 0 && <p className="empty">No rubrics yet.</p>}
      <ul className="rows">
        {items?.map((r) => (
          <li key={r.id}>
            <span className="grow">
              <strong>{r.title}</strong>
              <br />
              <small>
                {r.criteria.length} criteria · top score {r.max_points} · used by {r.used_by} {r.used_by === 1 ? "assignment" : "assignments"}
              </small>
            </span>
            <button onClick={() => { setDraft(toDraft(r)); window.scrollTo({ top: 0 }); }}>Edit</button>
            <button className="link" onClick={() => remove(r)}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
