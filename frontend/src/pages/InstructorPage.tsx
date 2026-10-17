import { useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { StoredExplanations } from "./StoredExplanations";

type Cell = { concept_id: number; name: string; p_known: number };
type Student = { student_id: number; label: string; synthetic: boolean; mastery: Cell[] };
type ClassMastery = { concepts: Cell[]; students: Student[] };
type Misconception = { name: string; description: string; concept: string; students: number; mean_probability: number };

const pretty = (name: string) => name.replace(/_/g, " ");

function cellStyle(p: number) {
  return {
    background: `color-mix(in srgb, var(--signal) ${Math.round(p * 100)}%, var(--panel))`,
    color: p > 0.55 ? "#fff" : "var(--ink)",
  };
}

export function InstructorPage({ session, courseId }: { session: Session; courseId: number }) {
  const [grid, setGrid] = useState<ClassMastery | null>(null);
  const [misconceptions, setMisconceptions] = useState<Misconception[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function remove(student: Student) {
    if (!window.confirm(`Remove ${student.label} from the course? Their work and history are kept.`)) return;
    try {
      await api(`/courses/${courseId}/students/${student.student_id}`, session, { method: "DELETE" });
      setGrid((g) => (g ? { ...g, students: g.students.filter((s) => s.student_id !== student.student_id) } : g));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The student could not be removed.");
    }
  }

  useEffect(() => {
    Promise.all([
      api<ClassMastery>(`/courses/${courseId}/class-mastery`, session),
      api<Misconception[]>(`/courses/${courseId}/misconceptions`, session),
    ])
      .then(([g, m]) => {
        setGrid(g);
        setMisconceptions(m);
      })
      .catch((e: Error) => setError(e.message));
  }, [courseId]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!grid || !misconceptions) return <p>Loading…</p>;
  const synthetic = grid.students.filter((s) => s.synthetic).length;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow">Course insight</p>
          <h1>Class overview</h1>
        </div>
      </div>
      {synthetic > 0 && (
        <p className="notice">
          {synthetic} of the {grid.students.length} students shown are <strong>synthetic</strong> demo data
          (marked “synthetic”), not real learners.
        </p>
      )}

      <h2>Mastery by student and concept</h2>
      {grid.students.length === 0 ? (
        <p className="empty">No students are enrolled yet.</p>
      ) : (
        <div className="heatmap-wrap">
          <table className="heatmap">
            <caption className="visually-hidden">Mastery percentage for each student and concept</caption>
            <thead>
              <tr>
                <th scope="col">Student</th>
                {grid.concepts.map((c) => (
                  <th key={c.concept_id} scope="col">
                    {pretty(c.name)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="average">
                <th scope="row">Class average</th>
                {grid.concepts.map((c) => (
                  <td key={c.concept_id} style={cellStyle(c.p_known)}>
                    {Math.round(c.p_known * 100)}
                  </td>
                ))}
              </tr>
              {grid.students.map((s) => (
                <tr key={s.student_id}>
                  <th scope="row">
                    <a href={`#/class/${courseId}/student/${s.student_id}`}>{s.label}</a>
                    {s.synthetic && <span className="tag">synthetic</span>}
                    {session.role === "instructor" && (
                      <button className="link remove" onClick={() => remove(s)} aria-label={`Remove ${s.label}`}>
                        Remove
                      </button>
                    )}
                  </th>
                  {s.mastery.map((c) => (
                    <td key={c.concept_id} style={cellStyle(c.p_known)}>
                      {Math.round(c.p_known * 100)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="legend">
        <span>Percent mastery:</span>
        {[0, 0.25, 0.5, 0.75, 1].map((p) => (
          <span key={p} className="swatch" style={cellStyle(p)}>
            {p * 100}
          </span>
        ))}
      </p>

      <h2>Common misconceptions</h2>
      {misconceptions.filter((m) => m.students > 0).length === 0 ? (
        <p className="empty">No misconception is suspected for any student yet.</p>
      ) : (
        <ul className="rows">
          {misconceptions
            .filter((m) => m.students > 0)
            .map((m) => (
              <li key={m.name}>
                <span className="grow">
                  {m.description} <small>({pretty(m.concept)})</small>
                </span>
                <span className="tag">
                  {m.students} {m.students === 1 ? "student" : "students"}
                </span>
              </li>
            ))}
        </ul>
      )}

      <StoredExplanations session={session} courseId={courseId} />
    </>
  );
}
