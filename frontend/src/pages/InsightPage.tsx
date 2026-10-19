import { useEffect, useState } from "react";

import { Session, api } from "../api";
import { QuizSummary } from "./quizTypes";

type Factor = { kind: string; summary: string; evidence: string[] };
type AtRisk = {
  checked: number;
  thresholds: Record<string, number>;
  students: { student_id: number; label: string; synthetic: boolean; factors: Factor[] }[];
};
type QuestionReport = {
  question_id: number;
  prompt: string;
  kind: "single" | "multiple" | "short";
  options: string[];
  answered: number;
  right: number;
  percent_right: number | null;
  chosen_counts: number[];
  right_choices: number[];
  class_missed: boolean;
};
type QuizReport = { quiz_id: number; title: string; students: number; attempts: number; average_percent: number | null; questions: QuestionReport[] };
type Comparison = { n_with: number; n_without: number; average_with: number | null; average_without: number | null; difference: number | null };
type ContentReport = {
  students: number;
  min_group: number;
  items: { item_id: number; title: string; module: string; kind: string; completed: number; not_completed: number; scores: Comparison; mastery: Comparison }[];
};

const FACTOR_TEXT: Record<string, string> = {
  missing_work: "Missing work",
  low_scores: "Low scores",
  falling_scores: "Falling scores",
  low_mastery: "Low mastery",
  inactive: "Inactive",
};

function compare(c: Comparison, min: number): string {
  if (c.difference === null) return c.n_with + c.n_without === 0 ? "no data" : `not enough students (need ${min} on each side)`;
  return `${c.average_with}% with, ${c.average_without}% without (${c.difference > 0 ? "+" : ""}${c.difference})`;
}

/** F-90, F-91, F-92: who may need help and why, which quiz questions the class missed, and how lessons relate to results. */
export function InsightPage({ session, courseId }: { session: Session; courseId: number }) {
  const base = `/courses/${courseId}`;
  const [risk, setRisk] = useState<AtRisk | null>(null);
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([]);
  const [quizId, setQuizId] = useState("");
  const [quiz, setQuiz] = useState<QuizReport | null>(null);
  const [content, setContent] = useState<ContentReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<AtRisk>(`${base}/at-risk`, session).then(setRisk).catch((e: Error) => setError(e.message));
    api<ContentReport>(`${base}/content-report`, session).then(setContent).catch((e: Error) => setError(e.message));
    api<QuizSummary[]>(`${base}/quizzes`, session)
      .then((all) => {
        setQuizzes(all);
        if (all.length) setQuizId(String(all[0].id));
      })
      .catch(() => setQuizzes([]));
  }, [courseId]);

  useEffect(() => {
    if (!quizId) return setQuiz(null);
    api<QuizReport>(`${base}/quizzes/${quizId}/report`, session).then(setQuiz).catch((e: Error) => setError(e.message));
  }, [quizId]);

  return (
    <>
      <p>
        <a href={`#/course/${courseId}/analytics`}>Analytics</a> · <a href={`#/course/${courseId}/gradebook`}>Gradebook</a>
      </p>
      <h1>Insight</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      <section className="panel" aria-label="Students who may need help">
        <h2>Students who may need help</h2>
        {risk && (
          <p>
            <small>
              {risk.students.length} of {risk.checked} students have at least one warning sign. Each sign shows the facts behind it.
            </small>
          </p>
        )}
        {risk && risk.students.length === 0 && <p className="empty">No student has a warning sign right now.</p>}
        <ul className="rows">
          {risk?.students.map((s) => (
            <li key={s.student_id} className="at-risk">
              <span className="grow">
                <a href={`#/class/${courseId}/student/${s.student_id}`}>
                  <strong>{s.label}</strong>
                </a>{" "}
                {s.factors.map((f) => (
                  <span key={f.kind} className="flag">
                    {FACTOR_TEXT[f.kind] ?? f.kind}
                  </span>
                ))}
                <details>
                  <summary>Why</summary>
                  <ul>
                    {s.factors.map((f) => (
                      <li key={f.kind}>
                        <strong>{FACTOR_TEXT[f.kind]}:</strong> {f.summary}
                        <ul>
                          {f.evidence.map((e, i) => (
                            <li key={i}>
                              <small>{e}</small>
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </details>
              </span>
            </li>
          ))}
        </ul>
        {risk && (
          <details>
            <summary>What counts as a sign</summary>
            <ul>
              <li>Missing work: {risk.thresholds.missing_assignments} or more assignments past due with nothing handed in.</li>
              <li>Low scores: under {risk.thresholds.low_score_percent}% of the points on at least {risk.thresholds.low_score_min_assignments} past-due assignments.</li>
              <li>Falling scores: the latest two assignments {risk.thresholds.falling_percentage_points} or more points below the earlier ones (at least {risk.thresholds.falling_min_assignments} assignments).</li>
              <li>Low mastery: average under {Math.round(risk.thresholds.low_mastery * 100)}% over at least {risk.thresholds.low_mastery_min_concepts} concepts with evidence.</li>
              <li>Inactive: nothing run, answered, handed in or completed for {risk.thresholds.inactive_days} days (after a week in the class).</li>
            </ul>
          </details>
        )}
      </section>

      <section className="panel" aria-label="Quiz questions">
        <h2>Quiz questions</h2>
        {quizzes.length === 0 && <p className="empty">This course has no quizzes yet.</p>}
        {quizzes.length > 0 && (
          <label className="inline">
            Quiz
            <select value={quizId} onChange={(e) => setQuizId(e.target.value)}>
              {quizzes.map((q) => (
                <option key={q.id} value={q.id}>
                  {q.title}
                </option>
              ))}
            </select>
          </label>
        )}
        {quiz && (
          <>
            <p>
              <small>
                {quiz.students} students took it ({quiz.attempts} attempts); their latest attempt is counted.
                {quiz.average_percent !== null && ` Average ${quiz.average_percent}%.`}
              </small>
            </p>
            <ol>
              {quiz.questions.map((q) => (
                <li key={q.question_id}>
                  {q.prompt}{" "}
                  {q.class_missed && <span className="flag">most of the class missed this</span>}
                  <br />
                  <small>
                    {q.answered === 0 ? "nobody answered" : `${q.right} of ${q.answered} right (${q.percent_right}%)`}
                  </small>
                  {q.kind !== "short" && q.answered > 0 && (
                    <ul>
                      {q.options.map((o, i) => (
                        <li key={i}>
                          <small>
                            {o}: chosen by {q.chosen_counts[i]}
                            {q.right_choices.includes(i) && " (right)"}
                          </small>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ol>
          </>
        )}
      </section>

      <section className="panel" aria-label="Lessons and results">
        <h2>Lessons and results</h2>
        <small>
          Students who finished a lesson compared with those who did not. This shows an association, not that the lesson caused the
          difference: students who do more of everything also finish more lessons.
        </small>
        {content && content.items.length === 0 && <p className="empty">This course has no lesson items yet.</p>}
        {content && content.items.length > 0 && (
          <table className="grades-table">
            <thead>
              <tr>
                <th>Lesson</th>
                <th>Finished</th>
                <th>Average score</th>
                <th>Average mastery</th>
              </tr>
            </thead>
            <tbody>
              {content.items.map((i) => (
                <tr key={i.item_id}>
                  <td>
                    {i.title}
                    <br />
                    <small>{i.module}</small>
                  </td>
                  <td>
                    {i.completed} of {i.completed + i.not_completed}
                  </td>
                  <td>{compare(i.scores, content.min_group)}</td>
                  <td>{compare(i.mastery, content.min_group)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
