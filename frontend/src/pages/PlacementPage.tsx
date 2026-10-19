import Editor from "@monaco-editor/react";
import { useState } from "react";

import { ApiError, BUSY_RETRIES, Session, api } from "../api";
import { DiagnosticItem, DiagnosticResult, DiagnosticStart, DiagnosticStep } from "../types";
import { MasteryBars, Misconceptions } from "./MasteryBars";
import { withoutFences } from "../statement";

const STARTER = "# Read from input(), print the answer.\n";

const BACKGROUNDS = [
  { value: "new", label: "New to this", hint: "I have not studied it before" },
  { value: "some", label: "Some experience", hint: "I know some of it" },
  { value: "comfortable", label: "Comfortable", hint: "I have used it a fair amount" },
] as const;

const CONFIDENCES = [
  { value: "guessing", label: "Guessing" },
  { value: "fairly", label: "Fairly sure" },
  { value: "sure", label: "Sure" },
] as const;

export function PlacementPage({ session, courseId }: { session: Session; courseId: number }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [item, setItem] = useState<DiagnosticItem | null>(null);
  const [number, setNumber] = useState(1);
  const [max, setMax] = useState(10);
  const [option, setOption] = useState<number | null>(null);
  const [code, setCode] = useState(STARTER);
  const [result, setResult] = useState<DiagnosticResult | null>(null);
  const [background, setBackground] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const onBusy = (attempt: number) => setNotice(`The sandbox is busy, trying again (${attempt} of ${BUSY_RETRIES})…`);

  async function call<T>(run: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    setError(null);
    try {
      return await run();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
      return null;
    } finally {
      setBusy(false);
      setNotice(null);
    }
  }

  async function start() {
    const started = await call(() =>
      api<DiagnosticStart>("/diagnostic/start", session, { body: { course_id: courseId, background } }),
    );
    if (!started) return;
    setSessionId(started.session_id);
    setItem(started.item);
    setNumber(started.item_number);
    setMax(started.max_items);
  }

  async function submit(dontKnow = false) {
    if (!item || !sessionId) return;
    const base = { session_id: sessionId, problem_id: item.problem_id };
    const body = dontKnow
      ? { ...base, dont_know: true }
      : item.kind === "mcq"
        ? { ...base, option_id: option, confidence }
        : { ...base, code };
    const step = await call(() => api<DiagnosticStep>("/diagnostic/answer", session, { body, onBusy }));
    if (!step) return;
    setOption(null);
    setConfidence(null);
    setCode(STARTER);
    setNumber(step.item_number);
    if (step.done) {
      setItem(null);
      setResult(step.result);
    } else {
      setItem(step.next_item);
    }
  }

  if (result) {
    return (
      <>
        <h1>Your starting point</h1>
        <p>
          This is where you start, not a grade. Each concept shows how sure the system is: a concept the test did
          not ask about is only an estimate from your overall level, and it changes as soon as you answer real questions.
        </p>
        <h2>Mastery by concept</h2>
        <MasteryBars concepts={result.mastery} courseId={courseId} />
        <h2>Misconceptions to look at</h2>
        <Misconceptions items={result.misconceptions} />
        <p>
          <a className="button primary" href={`#/mastery/${courseId}`}>
            Go to my dashboard
          </a>
        </p>
      </>
    );
  }

  if (!item) {
    return (
      <>
        <p>
          <a href={`#/course/${courseId}`}>Back to problems</a>
        </p>
        <h1>Placement test</h1>
        <p>
          About 16 to 20 questions, 10 to 20 minutes: mostly tracing questions, then a few short coding tasks. Some are
          easier and some harder, and they adapt to your answers. The result sets your starting mastery for each
          concept. Saying "I don't know" is fine and helps the test more than a guess.
        </p>
        <fieldset className="options">
          <legend>How much do you know about this course already? (optional)</legend>
          {BACKGROUNDS.map((b) => (
            <label key={b.value} className="option">
              <input
                type="radio"
                name="background"
                checked={background === b.value}
                onChange={() => setBackground(b.value)}
              />
              <span>
                {b.label}: {b.hint}
              </span>
            </label>
          ))}
        </fieldset>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button className="primary" onClick={start} disabled={busy}>
          Start the test
        </button>
      </>
    );
  }

  const ready = item.kind === "mcq" ? option !== null : code.trim().length > 0;
  return (
    <>
      <h1>
        Question {number} of up to {max}
      </h1>
      <progress value={number - 1} max={max} aria-label="Progress" />
      <h2>{item.title}</h2>
      <pre className="statement-block">{withoutFences(item.statement)}</pre>
      {item.kind === "mcq" ? (
        <fieldset className="options">
          <legend>Choose one answer</legend>
          {item.options.map((o) => (
            <label key={o.id} className="option">
              <input type="radio" name="option" checked={option === o.id} onChange={() => setOption(o.id)} />
              <pre>{o.text}</pre>
            </label>
          ))}
        </fieldset>
      ) : (
        <div className="editor">
          <Editor
            height="100%"
            defaultLanguage="python"
            value={code}
            onChange={(v) => setCode(v ?? "")}
            options={{ minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false }}
          />
        </div>
      )}
      {item.kind === "mcq" && (
        <fieldset className="options confidence">
          <legend>How sure are you? (optional)</legend>
          {CONFIDENCES.map((c) => (
            <label key={c.value} className="inline">
              <input
                type="radio"
                name="confidence"
                checked={confidence === c.value}
                onChange={() => setConfidence(c.value)}
              />{" "}
              {c.label}
            </label>
          ))}
        </fieldset>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p className="clear-assistant">
        <button className="primary" onClick={() => submit()} disabled={busy || !ready}>
          {busy ? "Checking…" : "Next question"}
        </button>{" "}
        <button onClick={() => submit(true)} disabled={busy}>
          I don't know
        </button>{" "}
        {notice && <span role="status">{notice}</span>}
      </p>
    </>
  );
}
