import { useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { STATUS_TEXT, Status, points, when } from "./AssignmentsPage";
import { CategoriesPanel } from "./CategoriesPanel";
import { Overall } from "./dashboardTypes";

type Gradebook = {
  assignments: { id: number; title: string; due_at: string; possible: number }[];
  students: {
    student_id: number;
    label: string;
    synthetic: boolean;
    cells: { assignment_id: number; score: number; with_late: number; status: Status; override_reason: string | null }[];
    possible: number;
    overall: Overall | null;
    total: number;
    total_with_late: number;
  }[];
  possible: number;
  lms_grades: "none" | "not_allowed" | "ready";
};
type SendResult = {
  assignments: number;
  scores_sent: number;
  students_not_from_lms: number;
  failures: { assignment_id: number; student_id: number | null; error: string }[];
};

/** F-04: students by assignment, with on-time scores, what late work would make them, and a download. */
export function GradebookPage({ session, courseId }: { session: Session; courseId: number }) {
  const [book, setBook] = useState<Gradebook | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<SendResult | null>(null);
  const [adjust, setAdjust] = useState<{ studentId: number; label: string; assignmentId: number; title: string; possible: number; score: string; reason: string; existing: boolean } | null>(null);
  const teacher = session.role === "instructor";

  async function sendToLms() {
    setSending(true);
    setError(null);
    setSent(null);
    try {
      setSent(await api<SendResult>(`/courses/${courseId}/gradebook/send`, session, { method: "POST" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The grades could not be sent.");
    } finally {
      setSending(false);
    }
  }

  const reload = () =>
    api<Gradebook>(`/courses/${courseId}/gradebook`, session)
      .then(setBook)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    reload();
  }, [courseId]);

  async function saveAdjust() {
    if (!adjust) return;
    setError(null);
    try {
      await api(`/courses/${courseId}/assignments/${adjust.assignmentId}/students/${adjust.studentId}/override`, session, {
        method: "PUT",
        body: { score: Number(adjust.score), reason: adjust.reason },
      });
      setAdjust(null);
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The score could not be changed.");
    }
  }

  async function removeAdjust() {
    if (!adjust) return;
    setError(null);
    try {
      await api(`/courses/${courseId}/assignments/${adjust.assignmentId}/students/${adjust.studentId}/override`, session, { method: "DELETE" });
      setAdjust(null);
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The adjustment could not be removed.");
    }
  }

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
      <CategoriesPanel session={session} courseId={courseId} onChange={reload} />
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
            {book.lms_grades === "ready" && session.role === "instructor" && (
              <button className="primary" onClick={sendToLms} disabled={sending}>
                {sending ? "Sending…" : "Send grades to the LMS"}
              </button>
            )}
          </p>
          {book.lms_grades === "not_allowed" && (
            <p className="notice">
              This course was opened from an LMS that has not allowed this tool to send grades. Turn on grade sync for
              the tool in the LMS, then open the tool from the course again.
            </p>
          )}
          {sent && (
            <div role="status" className={sent.failures.length ? "notice" : undefined}>
              <p>
                Sent {sent.scores_sent} {sent.scores_sent === 1 ? "score" : "scores"} for {sent.assignments}{" "}
                {sent.assignments === 1 ? "assignment" : "assignments"} (on-time scores only).
                {sent.students_not_from_lms > 0 &&
                  ` ${sent.students_not_from_lms} enrolled ${sent.students_not_from_lms === 1 ? "student has" : "students have"} no LMS account, so nothing was sent for them.`}
              </p>
              {sent.failures.length > 0 && (
                <ul>
                  {sent.failures.map((f, i) => (
                    <li key={i}>
                      Not sent: assignment {f.assignment_id}
                      {f.student_id !== null && `, student ${f.student_id}`} ({f.error})
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
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
                    {book.students.some((s) => s.overall) && <th scope="col">Overall</th>}
                  </tr>
                </thead>
                <tbody>
                  {book.students.map((s) => (
                    <tr key={s.student_id}>
                      <th scope="row">
                        {s.label}
                        {s.synthetic && <span className="tag">synthetic</span>}
                      </th>
                      {book.assignments.map((a) => {
                        const c = s.cells.find((cell) => cell.assignment_id === a.id);
                        if (!c)
                          return (
                            <td key={a.id} className="not-given" title="This assignment was not given to this student">
                              <small>not given</small>
                            </td>
                          );
                        return (
                          <td key={a.id} className={`status-${c.status}`}>
                            {points(c.score)}
                            <br />
                            <small>
                              {STATUS_TEXT[c.status]}
                              {c.status === "late" && ` (${points(c.with_late)} with late)`}
                              {c.override_reason && " · adjusted"}
                            </small>
                            {teacher && (
                              <>
                                <br />
                                <button
                                  className="link"
                                  aria-label={`Adjust ${s.label}'s score for ${a.title}`}
                                  onClick={() =>
                                    setAdjust({
                                      studentId: s.student_id, label: s.label, assignmentId: a.id, title: a.title, possible: a.possible,
                                      score: String(c.score), reason: c.override_reason ?? "", existing: c.override_reason !== null,
                                    })
                                  }
                                >
                                  Adjust
                                </button>
                              </>
                            )}
                          </td>
                        );
                      })}
                      <td>
                        <strong>{points(s.total)}</strong>
                        {s.possible !== book.possible && (
                          <>
                            <br />
                            <small>of {points(s.possible)}</small>
                          </>
                        )}
                        {s.total_with_late > s.total && (
                          <>
                            <br />
                            <small>{points(s.total_with_late)} with late</small>
                          </>
                        )}
                      </td>
                      {book.students.some((x) => x.overall) && (
                        <td>
                          {s.overall?.percent == null ? "—" : <strong>{s.overall.percent}%</strong>}
                          {s.overall && s.overall.uncategorised > 0 && (
                            <>
                              <br />
                              <small>{s.overall.uncategorised} uncategorised</small>
                            </>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {adjust && (
            <form
              className="stack panel"
              aria-label="Adjust a score"
              onSubmit={(e) => {
                e.preventDefault();
                saveAdjust();
              }}
            >
              <h2>
                Adjust {adjust.label}'s score for {adjust.title}
              </h2>
              <label className="inline">
                Score out of {points(adjust.possible)}
                <input type="number" min={0} max={adjust.possible} step={0.5} required value={adjust.score} onChange={(e) => setAdjust({ ...adjust, score: e.target.value })} />
              </label>
              <label>
                Reason (the student can read this)
                <input value={adjust.reason} maxLength={500} required onChange={(e) => setAdjust({ ...adjust, reason: e.target.value })} />
              </label>
              <p className="actions">
                <button className="primary" type="submit">
                  Save adjustment
                </button>
                {adjust.existing && (
                  <button type="button" onClick={removeAdjust}>
                    Remove the adjustment
                  </button>
                )}
                <button type="button" onClick={() => setAdjust(null)}>
                  Cancel
                </button>
              </p>
            </form>
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
