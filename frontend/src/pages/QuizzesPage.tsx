import { FormEvent, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { KIND_TEXT, Question, QuestionKind, Quiz, QuizSummary } from "./quizTypes";

type QDraft = { kind: QuestionKind; prompt: string; options: string[]; correct: number[]; accepted: string; weight: number };
type Draft = { id: number | null; title: string; maxAttempts: number; showAnswers: boolean; published: boolean; questions: QDraft[] };

const blankQuestion = (): QDraft => ({ kind: "single", prompt: "", options: ["", ""], correct: [], accepted: "", weight: 1 });
const EMPTY: Draft = { id: null, title: "", maxAttempts: 3, showAnswers: false, published: false, questions: [blankQuestion()] };

const toDraft = (quiz: Quiz): Draft => ({
  id: quiz.id,
  title: quiz.title,
  maxAttempts: quiz.max_attempts,
  showAnswers: quiz.show_answers,
  published: quiz.published,
  questions: quiz.question_list.map((q: Question) => ({
    kind: q.kind,
    prompt: q.prompt,
    options: q.kind === "short" ? ["", ""] : q.options,
    correct: q.correct_choices ?? [],
    accepted: (q.accepted ?? []).join("\n"),
    weight: q.weight,
  })),
});

const toBody = (d: Draft) => ({
  title: d.title,
  max_attempts: d.maxAttempts,
  show_answers: d.showAnswers,
  published: d.published,
  questions: d.questions.map((q) =>
    q.kind === "short"
      ? { kind: q.kind, prompt: q.prompt, accepted: q.accepted.split("\n").map((a) => a.trim()).filter(Boolean), weight: q.weight }
      : { kind: q.kind, prompt: q.prompt, options: q.options, correct_choices: q.correct, weight: q.weight },
  ),
});

function QuestionEditor({ q, onChange, onRemove, number }: { q: QDraft; onChange: (q: QDraft) => void; onRemove: () => void; number: number }) {
  const setOption = (i: number, value: string) => onChange({ ...q, options: q.options.map((o, n) => (n === i ? value : o)) });
  const toggle = (i: number) => {
    if (q.kind === "single") return onChange({ ...q, correct: [i] });
    onChange({ ...q, correct: q.correct.includes(i) ? q.correct.filter((c) => c !== i) : [...q.correct, i] });
  };
  const removeOption = (i: number) =>
    onChange({ ...q, options: q.options.filter((_, n) => n !== i), correct: q.correct.filter((c) => c !== i).map((c) => (c > i ? c - 1 : c)) });
  return (
    <fieldset className="question-editor">
      <legend>Question {number}</legend>
      <label>
        Type
        <select
          value={q.kind}
          onChange={(e) => onChange({ ...q, kind: e.target.value as QuestionKind, correct: q.kind === "short" || e.target.value === "single" ? [] : q.correct })}
        >
          {(Object.keys(KIND_TEXT) as QuestionKind[]).map((k) => (
            <option key={k} value={k}>
              {KIND_TEXT[k]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Question
        <textarea value={q.prompt} rows={2} maxLength={2000} required onChange={(e) => onChange({ ...q, prompt: e.target.value })} />
      </label>
      {q.kind === "short" ? (
        <label>
          Accepted answers (one per line; case and extra spaces are ignored)
          <textarea value={q.accepted} rows={3} required onChange={(e) => onChange({ ...q, accepted: e.target.value })} />
        </label>
      ) : (
        <>
          <p>Options (tick the right {q.kind === "single" ? "one" : "ones"})</p>
          {q.options.map((o, i) => (
            <div key={i} className="concept-pick">
              <label className="inline">
                <input
                  type={q.kind === "single" ? "radio" : "checkbox"}
                  name={`right-${number}`}
                  checked={q.correct.includes(i)}
                  onChange={() => toggle(i)}
                  aria-label={`Option ${i + 1} is right`}
                />
                <input value={o} maxLength={300} required aria-label={`Option ${i + 1}`} onChange={(e) => setOption(i, e.target.value)} />
              </label>
              {q.options.length > 2 && (
                <button type="button" className="link" onClick={() => removeOption(i)}>
                  Remove
                </button>
              )}
            </div>
          ))}
          {q.options.length < 8 && (
            <button type="button" onClick={() => onChange({ ...q, options: [...q.options, ""] })}>
              Add an option
            </button>
          )}
        </>
      )}
      <label className="inline">
        Weight
        <input type="number" min={0.5} max={100} step={0.5} value={q.weight} onChange={(e) => onChange({ ...q, weight: Number(e.target.value) })} />
      </label>
      <button type="button" className="link" onClick={onRemove}>
        Remove this question
      </button>
    </fieldset>
  );
}

/** F-71: the instructor builds, publishes and deletes the course's quizzes. */
export function QuizzesPage({ session, courseId }: { session: Session; courseId: number }) {
  const [items, setItems] = useState<QuizSummary[] | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const base = `/courses/${courseId}/quizzes`;

  const load = () =>
    api<QuizSummary[]>(base, session)
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  useEffect(() => {
    load();
  }, [courseId]);

  async function edit(id: number) {
    try {
      setDraft(toDraft(await api<Quiz>(`${base}/${id}`, session)));
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not open the quiz.");
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (draft.questions.some((q) => q.kind !== "short" && q.correct.length === 0)) {
      setError("Tick the right option of every choice question.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api(draft.id ? `${base}/${draft.id}` : base, session, { method: draft.id ? "PUT" : "POST", body: toBody(draft) });
      setDraft(EMPTY);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the quiz.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(q: QuizSummary) {
    if (!window.confirm(`Delete "${q.title}"?`)) return;
    try {
      await api(`${base}/${q.id}`, session, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete the quiz.");
    }
  }

  const setQuestion = (i: number, q: QDraft) => setDraft({ ...draft, questions: draft.questions.map((x, n) => (n === i ? q : x)) });

  return (
    <>
      <p>
        <a href={`#/course/${courseId}`}>Back to problems</a> · <a href={`#/course/${courseId}/assignments`}>Assignments</a>
      </p>
      <h1>Quizzes</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form className="stack" onSubmit={save}>
        <fieldset>
          <legend>{draft.id ? "Edit quiz" : "New quiz"}</legend>
          <label>
            Title
            <input value={draft.title} maxLength={200} required onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </label>
          <label className="inline">
            Attempts allowed
            <input type="number" min={1} max={10} value={draft.maxAttempts} onChange={(e) => setDraft({ ...draft, maxAttempts: Number(e.target.value) })} />
          </label>
          <label className="inline">
            <input type="checkbox" checked={draft.published} onChange={(e) => setDraft({ ...draft, published: e.target.checked })} />
            Published (students can take it)
          </label>
          <label className="inline">
            <input type="checkbox" checked={draft.showAnswers} onChange={(e) => setDraft({ ...draft, showAnswers: e.target.checked })} />
            Show the right answers after every assignment holding this quiz is past due
          </label>
          {draft.id && <small>Once a student has taken the quiz, its questions are locked; the settings above can still change.</small>}
        </fieldset>
        {draft.questions.map((q, i) => (
          <QuestionEditor
            key={i}
            q={q}
            number={i + 1}
            onChange={(next) => setQuestion(i, next)}
            onRemove={() => setDraft({ ...draft, questions: draft.questions.filter((_, n) => n !== i) })}
          />
        ))}
        <p className="actions">
          {draft.questions.length < 50 && (
            <button type="button" onClick={() => setDraft({ ...draft, questions: [...draft.questions, blankQuestion()] })}>
              Add a question
            </button>
          )}
          <button className="primary" type="submit" disabled={busy || draft.questions.length === 0}>
            {draft.id ? "Save changes" : "Create quiz"}
          </button>
          {draft.id && (
            <button type="button" onClick={() => setDraft(EMPTY)}>
              Cancel
            </button>
          )}
        </p>
      </form>

      <h2>In this course</h2>
      {items && items.length === 0 && <p className="empty">No quizzes yet.</p>}
      <ul className="rows">
        {items?.map((q) => (
          <li key={q.id}>
            <span className="grow">
              <strong>{q.title}</strong>
              <br />
              <small>
                {q.questions} questions · {q.max_attempts} attempts · {q.published ? "published" : "draft"}
                {q.in_assignments > 0 && ` · in ${q.in_assignments} assignment${q.in_assignments === 1 ? "" : "s"}`}
              </small>
            </span>
            <button onClick={() => edit(q.id)}>Edit</button>
            <button className="link" onClick={() => remove(q)}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
