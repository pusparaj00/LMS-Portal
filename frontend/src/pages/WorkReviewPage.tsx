import { FormEvent, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { Comments } from "./Comments";
import { when } from "./AssignmentsPage";
import { TheirWork, WORK_STATE_TEXT, WorkList, downloadWorkFile, sizeText } from "./workTypes";

/** F-74, F-77: the students of one assignment on the left, the chosen student's work and a grade box on the right. */
export function WorkReviewPage({ session, courseId, assignmentId }: { session: Session; courseId: number; assignmentId: number }) {
  const base = `/courses/${courseId}/assignments/${assignmentId}/work`;
  const [list, setList] = useState<WorkList | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [work, setWork] = useState<TheirWork | null>(null);
  const [score, setScore] = useState("");
  const [levels, setLevels] = useState<Record<number, number>>({});
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    api<WorkList>(`${base}/submissions`, session)
      .then(setList)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    refresh();
  }, [assignmentId]);

  const show = (w: TheirWork) => {
    setWork(w);
    setScore(w.score === null ? "" : String(w.score));
    setLevels(
      Object.fromEntries((w.rubric?.criteria ?? []).filter((c) => c.chosen_level_id !== null).map((c) => [c.id, c.chosen_level_id as number])),
    );
    setFeedback(w.feedback ?? "");
  };

  async function open(studentId: number) {
    setChosen(studentId);
    setError(null);
    try {
      show(await api<TheirWork>(`${base}/students/${studentId}`, session));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not open the work.");
    }
  }

  async function act(action: () => Promise<TheirWork>, failure: string) {
    setBusy(true);
    setError(null);
    try {
      show(await action());
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : failure);
    } finally {
      setBusy(false);
    }
  }

  const saveGrade = (event: FormEvent) => {
    event.preventDefault();
    return act(
      () =>
        api<TheirWork>(`${base}/students/${chosen}/grade`, session, {
          method: "PUT",
          body: work?.rubric ? { levels, feedback: feedback.trim() || null } : { score: Number(score), feedback: feedback.trim() || null },
        }),
      "Could not save the score.",
    );
  };

  async function returnAll() {
    setError(null);
    try {
      await api(`${base}/return-all`, session, { method: "POST" });
      await refresh();
      if (chosen) await open(chosen);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not return the work.");
    }
  }

  const waiting = list?.rows.filter((r) => r.state === "turned_in").length ?? 0;
  const unreturned = list?.rows.filter((r) => r.state === "graded").length ?? 0;

  return (
    <>
      <p>
        <a href={`#/review`}>To review</a> · <a href={`#/course/${courseId}/assignments`}>Assignments</a> ·{" "}
        <a href={`#/course/${courseId}/gradebook`}>Gradebook</a>
      </p>
      <h1>{list?.title ?? "Student work"}</h1>
      {list && (
        <p>
          <small>
            Due {when(list.due_at)} · {list.points} points · {waiting} waiting for a score · {unreturned} scored, not returned
          </small>{" "}
          {unreturned > 0 && (
            <button onClick={returnAll}>Return all scored work</button>
          )}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="review-layout">
        <ul className="rows review-students" aria-label="Students">
          {list?.rows.map((r) => (
            <li key={r.student_id} className={r.student_id === chosen ? "chosen" : undefined}>
              <button className="link" onClick={() => open(r.student_id)} aria-current={r.student_id === chosen}>
                {r.label}
              </button>
              <small>
                {WORK_STATE_TEXT[r.state]}
                {r.late && " (late)"}
                {r.score !== null && ` · ${r.score}`}
              </small>
            </li>
          ))}
          {list && list.rows.length === 0 && <li className="empty">No students are enrolled yet.</li>}
        </ul>

        <section className="review-work">
          {!work && <p className="empty">Choose a student to see their work.</p>}
          {work && (
            <>
              <h2>
                {work.label} <small>{WORK_STATE_TEXT[work.state]}{work.late && " (late)"}</small>
              </h2>
              {work.turned_in_at ? <small>Turned in {when(work.turned_in_at)}</small> : <p className="empty">Nothing is turned in yet.</p>}
              {work.text && <pre className="work-text">{work.text}</pre>}
              {work.link && (
                <p>
                  Link:{" "}
                  <a href={work.link} target="_blank" rel="noopener noreferrer">
                    {work.link}
                  </a>
                </p>
              )}
              {work.file_name && (
                <p>
                  File:{" "}
                  <button className="link" onClick={() => downloadWorkFile(session, `${base}/students/${work.student_id}/file`, work.file_name ?? "work").catch((e: Error) => setError(e.message))}>
                    {work.file_name}
                  </button>{" "}
                  <small>({sizeText(work.file_size ?? 0)}, downloaded, never opened here)</small>
                </p>
              )}

              {work.turned_in_at && (
                <form className="stack" onSubmit={saveGrade}>
                  <fieldset disabled={busy}>
                    <legend>Score</legend>
                    {work.rubric ? (
                      <>
                        <p>
                          <strong>{work.rubric.title}</strong>: choose a level for every criterion. Score:{" "}
                          {work.rubric.criteria.reduce((sum, c) => sum + (c.levels.find((l) => l.id === levels[c.id])?.points ?? 0), 0)} of {work.points}
                        </p>
                        {work.rubric.criteria.map((c) => (
                          <fieldset key={c.id}>
                            <legend>{c.title}</legend>
                            {c.description && <small>{c.description}</small>}
                            {c.levels.map((l) => (
                              <label key={l.id} className="inline">
                                <input type="radio" name={`criterion-${c.id}`} checked={levels[c.id] === l.id} onChange={() => setLevels({ ...levels, [c.id]: l.id })} />
                                {l.label} ({l.points})
                              </label>
                            ))}
                          </fieldset>
                        ))}
                      </>
                    ) : (
                      <label className="inline">
                        Score out of {work.points}
                        <input type="number" min={0} max={work.points} step={0.5} value={score} required onChange={(e) => setScore(e.target.value)} />
                      </label>
                    )}
                    <label>
                      Feedback for the student
                      <textarea value={feedback} rows={4} maxLength={5000} onChange={(e) => setFeedback(e.target.value)} />
                    </label>
                  </fieldset>
                  <p className="actions">
                    <button type="submit" disabled={busy || (work.rubric ? Object.keys(levels).length !== work.rubric.criteria.length : score === "")}>
                      Save score
                    </button>
                    {work.graded_at && !work.returned_at && (
                      <button type="button" className="primary" disabled={busy} onClick={() => act(() => api<TheirWork>(`${base}/students/${work.student_id}/return`, session, { method: "POST" }), "Could not return the work.")}>
                        Return to student
                      </button>
                    )}
                    {work.returned_at && <small>Returned {when(work.returned_at)}. A new score is shown to the student at once.</small>}
                  </p>
                </form>
              )}

              <Comments
                comments={work.comments}
                teacherView
                onSend={async (body) => show(await api<TheirWork>(`${base}/students/${work.student_id}/comments`, session, { body: { body } }))}
              />
            </>
          )}
        </section>
      </div>
    </>
  );
}
