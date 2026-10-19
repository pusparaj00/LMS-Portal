import { useEffect, useState } from "react";

import { Session, api } from "../api";
import { STATUS_TEXT, points, when } from "./AssignmentsPage";
import { CourseGrades, percent } from "./dashboardTypes";

/** F-63: the student's own score for every assignment, course by course. Late work is shown beside the on-time score. */
export function GradesPage({ session }: { session: Session }) {
  const [courses, setCourses] = useState<CourseGrades[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<CourseGrades[]>("/students/me/grades", session)
      .then(setCourses)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <article className="dash-wide">
      <h1>Your grades</h1>
      {error && <p role="alert" className="error">{error}</p>}
      {!courses && !error && <p className="empty">Loading your grades…</p>}
      {courses?.length === 0 && (
        <p className="empty">
          You have not joined a class yet. <a href="#/courses">Join one with a class code</a>.
        </p>
      )}
      {courses?.map((c) => (
        <section key={c.course_id} className="panel" aria-label={c.title}>
          <h2>
            <a href={`#/course/${c.course_id}`}>{c.title}</a>
          </h2>
          <p>
            Course score: {points(c.score)} of {points(c.possible)} ({percent(c.percent)})
          </p>
          {c.assignments.length === 0 ? (
            <p className="empty">This course has no assignments yet.</p>
          ) : (
            <table className="grades-table">
              <thead>
                <tr>
                  <th>Assignment</th>
                  <th>Due</th>
                  <th className="num">Score</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {c.assignments.map((a) => (
                  <tr key={a.assignment_id}>
                    <td>{a.title}</td>
                    <td>{when(a.due_at)}</td>
                    <td className="num">
                      {points(a.score)} / {points(a.possible)}
                      {a.with_late > a.score && <span className="muted"> ({points(a.with_late)} with late work)</span>}
                    </td>
                    <td>{STATUS_TEXT[a.status]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ))}
    </article>
  );
}
