import { useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { STATUS_TEXT, Status, points, when } from "./AssignmentsPage";

type Gradebook = {
  assignments: { id: number; title: string; due_at: string; possible: number }[];
  students: {
    student_id: number;
    label: string;
    synthetic: boolean;
    cells: { assignment_id: number; score: number; with_late: number; status: Status }[];
    total: number;
    total_with_late: number;
  }[];
  possible: number;
};

/** F-04: students by assignment, with on-time scores, what late work would make them, and a download. */
export function GradebookPage({ session, courseId }: { session: Session; courseId: number }) {
  const [book, setBook] = useState<Gradebook | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Gradebook>(`/courses/${courseId}/gradebook`, session)
      .then(setBook)
      .catch((e: Error) => setError(e.message));
  }, [courseId]);

  async function download() {
    setError(null);
    try {
      const response = await fetch(`/api/v1/courses/${courseId}/export/gradebook?format=csv`, {
        headers: { Authorization: `Bearer ${session.token}` },
      });
      if (!response.ok) throw new ApiError(response.status, `Download failed (${response.status})`);
      const url = URL.createObjectURL(await response.blob());
      const link = Object.assign(document.createElement("a"), { href: url, download: `gradebook-course-${courseId}.csv` });
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The download could not be started.");
    }
  }

  return (
    <>
      <p>
        <a href={`#/course/${courseId}`}>Back to problems</a> ·{" "}
        <a href={`#/course/${courseId}/assignments`}>Assignments</a>
      </p>
      <h1>Gradebook</h1>
      {error && <p role="alert" className="error">{error}</p>}
      {!book && !error && <p>Loading…</p>}
      {book && book.assignments.length === 0 && (
        <p className="empty">
          No assignments yet. <a href={`#/course/${courseId}/assignments`}>Create one</a>.
        </p>
      )}
      {book && book.assignments.length > 0 && (
        <>
          <p className="actions">
            <button onClick={download}>Download CSV</button>
          </p>
          {book.students.length === 0 ? (
            <p className="empty">No students are enrolled yet.</p>
          ) : (
            <div className="heatmap-wrap">
              <table className="heatmap gradebook">
                <caption className="visually-hidden">Score for each student and assignment</caption>
                <thead>
                  <tr>
                    <th scope="col">Student</th>
                    {book.assignments.map((a) => (
                      <th key={a.id} scope="col">
                        {a.title}
                        <br />
                        <small>
                          due {when(a.due_at)} · {points(a.possible)}
                        </small>
                      </th>
                    ))}
                    <th scope="col">
                      Total
                      <br />
                      <small>of {points(book.possible)}</small>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {book.students.map((s) => (
                    <tr key={s.student_id}>
                      <th scope="row">
                        {s.label}
                        {s.synthetic && <span className="tag">synthetic</span>}
                      </th>
                      {book.assignments.map((a) => s.cells.find((c) => c.assignment_id === a.id)!).map((c) => (
                        <td key={c.assignment_id} className={`status-${c.status}`}>
                          {points(c.score)}
                          <br />
                          <small>
                            {STATUS_TEXT[c.status]}
                            {c.status === "late" && ` (${points(c.with_late)} with late)`}
                          </small>
                        </td>
                      ))}
                      <td>
                        <strong>{points(s.total)}</strong>
                        {s.total_with_late > s.total && (
                          <>
                            <br />
                            <small>{points(s.total_with_late)} with late</small>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <small>
            A score is the best attempt before the due time: points times the share of tests passed, hidden tests
            included. Late work is shown but never counted, and no penalty is applied.
          </small>
        </>
      )}
    </>
  );
}
