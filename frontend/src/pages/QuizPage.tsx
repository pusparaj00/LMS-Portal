import { FormEvent, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { Protected, Watermark } from "./ProtectedContent";
import { AttemptResult, MyAttempts, Quiz, QuizSummary, ReviewItem } from "./quizTypes";

const percent = (f: number) => `${Math.round(f * 100)}%`;

/** F-72: the published quizzes of a course, with the student's own attempts. */
export function StudentQuizzes({ session, courseId }: { session: Session; courseId: number }) {
  const [items, setItems] = useState<QuizSummary[] | null>(null);
  useEffect(() => {
    api<QuizSummary[]>(`/courses/${courseId}/quizzes`, session)
      .then(setItems)
      .catch(() => setItems([]));
  }, [courseId]);
  if (!items || items.length === 0) return null;
  return (
    <section>
      <h2>Quizzes</h2>
      <ul className="rows">
        {items.map((q) => (
          <li key={q.id}>
            <span className="grow">
              <a href={`#/course/${courseId}/quiz/${q.id}`}>
                <strong>{q.title}</strong>
              </a>
              <br />
              <small>
                {q.questions} questions · {q.attempts_used ?? 0} of {q.max_attempts} attempts used
                {q.best_fraction !== null && ` · best ${percent(q.best_fraction)}`}
              </small>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

type Given = Record<number, { choices: number[]; text: string }>;

/** F-72: take a quiz. The page only ever holds the questions; the server grades and says how it went. */
export function QuizPage({ session, courseId, quizId }: { session: Session; courseId: number; quizId: number }) {
  const base = `/courses/${courseId}/quizzes/${quizId}`;
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [mine, setMine] = useState<MyAttempts | null>(null);
  const [given, setGiven] = useState<Given>({});
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Quiz>(base, session).then(setQuiz).catch((e: Error) => setError(e.message));
    api<MyAttempts>(`${base}/attempts/mine`, session).then(setMine).catch((e: Error) => setError(e.message));
  }, [quizId]);

  const answer = (id: number) => given[id] ?? { choices: [], text: "" };
  const pick = (id: number, option: number, single: boolean) => {
    const now = answer(id).choices;
    const choices = single ? [option] : now.includes(option) ? now.filter((c) => c !== option) : [...now, option];
    setGiven({ ...given, [id]: { ...answer(id), choices } });
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!quiz) return;
    setBusy(true);
    setError(null);
    const answers = quiz.question_list.map((q) => ({
      question_id: q.id,
      choices: answer(q.id).choices,
      text: q.kind === "short" ? answer(q.id).text : null,
    }));
    try {
      setResult(await api<AttemptResult>(`${base}/attempts`, session, { body: { answers } }));
      setGiven({});
      setMine(await api<MyAttempts>(`${base}/attempts/mine`, session));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not hand in the quiz.");
    } finally {
      setBusy(false);
    }
  }

  const review = result?.review ?? mine?.review ?? null;
  const verdict = (item: ReviewItem | undefined) => (item ? (item.correct ? "Right" : "Wrong") : null);
  const left = result?.attempts_left ?? mine?.attempts_left ?? 0;

  return (
    <>
      <p>
        <a href={`#/course/${courseId}`}>Back to the course</a>
      </p>
      <h1>{quiz?.title ?? "Quiz"}</h1>
      <Watermark session={session} />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {result && (
        <p role="status" className="notice">
          Attempt {result.attempt_number}: {result.earned} of {result.possible} points ({percent(result.fraction)}).{" "}
          {result.attempts_left > 0 ? `${result.attempts_left} attempt${result.attempts_left === 1 ? "" : "s"} left.` : "No attempts left."}
        </p>
      )}
      {mine && mine.attempts.length > 0 && !result && (
        <p>
          Your attempts: {mine.attempts.map((a) => `${a.number}: ${percent(a.fraction)}`).join(", ")}. The best one counts.
        </p>
      )}
      <form className="stack" onSubmit={submit}>
        {quiz?.question_list.map((q, n) => {
          const item = review?.find((r) => r.question_id === q.id);
          return (
            <fieldset key={q.id}>
              <legend>
                Question {n + 1} ({q.weight} {q.weight === 1 ? "point" : "points"})
              </legend>
              <Protected session={session}>
                <p>{q.prompt}</p>
              </Protected>
              {q.kind === "short" ? (
                <input
                  value={answer(q.id).text}
                  maxLength={500}
                  aria-label={`Answer to question ${n + 1}`}
                  onChange={(e) => setGiven({ ...given, [q.id]: { ...answer(q.id), text: e.target.value } })}
                />
              ) : (
                q.options.map((o, i) => (
                  <div key={i}>
                    <label className="inline">
                      <input
                        type={q.kind === "single" ? "radio" : "checkbox"}
                        name={`q-${q.id}`}
                        checked={answer(q.id).choices.includes(i)}
                        onChange={() => pick(q.id, i, q.kind === "single")}
                      />
                      <Protected session={session}>{o}</Protected>
                    </label>
                  </div>
                ))
              )}
              {item && (
                <small>
                  Last attempt: {verdict(item)}.{" "}
                  {item.correct_choices && `Right: ${item.correct_choices.map((i) => q.options[i]).join(", ")}.`}
                  {item.accepted && `Accepted: ${item.accepted.join(", ")}.`}
                </small>
              )}
            </fieldset>
          );
        })}
        <p className="actions">
          <button className="primary" type="submit" disabled={busy || left === 0 || !quiz}>
            {left === 0 && mine ? "No attempts left" : "Hand in"}
          </button>
          {mine && left > 0 && <small>{left} attempt{left === 1 ? "" : "s"} left. Unanswered questions score zero.</small>}
        </p>
      </form>
    </>
  );
}
