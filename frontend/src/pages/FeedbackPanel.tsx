import { CodeEditor as Editor } from "./CodeEditor";
import { useState } from "react";

import { ApiError, BUSY_RETRIES, Session, api } from "../api";
import { withoutFences } from "../statement";

type Source = { chunk_id: number; title: string; section: string; text: string };
type Probe = {
  problem_id: number;
  kind: "code" | "mcq";
  title: string;
  statement: string;
  options: { id: number; text: string }[];
};
type Explanation = {
  status: "verified" | "fallback";
  attempts: number;
  cached: boolean;
  explanation: {
    claim: string;
    line: number;
    concept: string | null;
    sources: Source[];
    example_input: string | null;
    example_output: string | null;
  } | null;
  fallback_text: string | null;
  fallback_sources: Source[];
  probe: Probe | null;
};
type Hint = {
  level: number;
  max_level: number;
  kind: string;
  text: string;
  source_title: string | null;
  example_title: string | null;
  example_solution: string | null;
};
type ProbeResult = {
  correct: boolean;
  mastery_changes: { concept: string; before: number; after: number }[];
  next_step: { problem_id: number; title: string; reason: string } | null;
};

const HINT_TITLES: Record<string, string> = {
  concept: "Concept hint",
  location: "Where to look",
  example: "Worked example on a different problem",
};

function Inline({ text }: { text: string }) {
  return (
    <>
      {text.split(/(`[^`]+`)/).map((part, i) =>
        part.length > 2 && part.startsWith("`") && part.endsWith("`") ? <code key={i}>{part.slice(1, -1)}</code> : part,
      )}
    </>
  );
}

const pretty = (name: string) => name.replace(/_/g, " ");
const percent = (value: number) => `${Math.round(value * 100)}%`;

export function FeedbackPanel({ session, submissionId }: { session: Session; submissionId: number }) {
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [hints, setHints] = useState<Hint[]>([]);
  const [busy, setBusy] = useState<"explain" | "hint" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [noMoreHints, setNoMoreHints] = useState(false);

  async function explain() {
    setBusy("explain");
    setError(null);
    try {
      setExplanation(await api<Explanation>(`/submissions/${submissionId}/explain`, session, { method: "POST" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setBusy(null);
    }
  }

  async function nextHint() {
    setBusy("hint");
    setError(null);
    try {
      const hint = await api<Hint>(`/submissions/${submissionId}/hint`, session, { method: "POST" });
      setHints((shown) => [...shown, hint]);
      if (hint.level >= hint.max_level) setNoMoreHints(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setNoMoreHints(true);
      else setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="feedback" aria-label="Help with this submission">
      <h2>Help with this submission</h2>
      {!explanation && (
        <button className="primary" onClick={explain} disabled={busy !== null}>
          {busy === "explain" ? "Checking the explanation…" : "Explain what went wrong"}
        </button>
      )}
      {busy === "explain" && (
        <p role="status" className="progress">
          Writing an explanation and checking it against your test results. This takes a few seconds.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {explanation?.explanation && (
        <div className="explanation verified">
          <p className="badge">
            {explanation.cached ? "Stored explanation, checked again against your test results" : "Checked against your test results"}
          </p>
          <p>
            <Inline text={explanation.explanation.claim} />
          </p>
          {explanation.explanation.example_input !== null && (
            <div className="example-run">
              <strong>Try it yourself</strong>
              <dl>
                <dt>Input</dt>
                <dd>
                  <pre>{explanation.explanation.example_input}</pre>
                </dd>
                <dt>Your program prints</dt>
                <dd>
                  <pre>{explanation.explanation.example_output}</pre>
                </dd>
              </dl>
              <small>The system ran your program on this input to check the explanation before showing it.</small>
            </div>
          )}
          <p>
            <small>
              Line {explanation.explanation.line}
              {explanation.explanation.concept ? ` · concept: ${pretty(explanation.explanation.concept)}` : ""}
            </small>
          </p>
          <Sources sources={explanation.explanation.sources} />
        </div>
      )}
      {explanation && !explanation.explanation && (
        <div className="explanation">
          <p className="badge standard">Standard hint</p>
          <p>
            <Inline text={explanation.fallback_text ?? ""} />
          </p>
          <Sources sources={explanation.fallback_sources} />
        </div>
      )}

      {explanation && (
        <>
          <h3>More help</h3>
          {hints.map((hint) => (
            <div key={hint.level} className="hint">
              <strong>
                {HINT_TITLES[hint.kind]} ({hint.level} of {hint.max_level})
              </strong>
              <p>
                <Inline text={hint.text} />
              </p>
              {hint.example_solution && <pre>{hint.example_solution}</pre>}
              {hint.source_title && <small>From the notes: {hint.source_title}</small>}
            </div>
          ))}
          {noMoreHints ? (
            <p className="empty">You have used every hint for this problem.</p>
          ) : (
            <button onClick={nextHint} disabled={busy !== null}>
              {hints.length === 0 ? "Give me a hint" : "Give me a stronger hint"}
            </button>
          )}
          {explanation.probe && <ProbeCard session={session} submissionId={submissionId} probe={explanation.probe} />}
        </>
      )}
    </section>
  );
}

function Sources({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;
  return (
    <div className="sources">
      <small>From the course notes</small>
      <ul>
        {sources.map((s) => (
          <li key={s.chunk_id}>
            <details>
              <summary>
                {s.title}
                {s.section ? ` · ${s.section}` : ""}
              </summary>
              <p>
                <Inline text={s.text} />
              </p>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ProbeCard({ session, submissionId, probe }: { session: Session; submissionId: number; probe: Probe }) {
  const [option, setOption] = useState<number | null>(null);
  const [code, setCode] = useState("# Read from input(), print the answer.\n");
  const [result, setResult] = useState<ProbeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const body =
        probe.kind === "mcq" ? { submission_id: submissionId, option_id: option } : { submission_id: submissionId, code };
      const onBusy = (attempt: number) => setNotice(`The sandbox is busy, trying again (${attempt} of ${BUSY_RETRIES})…`);
      setResult(await api<ProbeResult>(`/probes/${probe.problem_id}/answer`, session, { body, onBusy }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setBusy(false);
      setNotice(null);
    }
  }

  const ready = probe.kind === "mcq" ? option !== null : code.trim().length > 0;
  return (
    <div className="probe">
      <h3>Check your understanding</h3>
      <p>
        <strong>{probe.title}</strong>
      </p>
      <pre className="statement-block">{withoutFences(probe.statement)}</pre>
      {!result && (
        <>
          {probe.kind === "mcq" ? (
            <fieldset className="options">
              <legend>Choose one answer</legend>
              {probe.options.map((o) => (
                <label key={o.id} className="option">
                  <input type="radio" name={`probe-${probe.problem_id}`} checked={option === o.id} onChange={() => setOption(o.id)} />
                  <pre>{o.text}</pre>
                </label>
              ))}
            </fieldset>
          ) : (
            <div className="editor short">
              <Editor
                height="100%"
                defaultLanguage="python"
                value={code}
                onChange={(v) => setCode(v ?? "")}
                options={{ minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false }}
              />
            </div>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="primary" onClick={submit} disabled={busy || !ready}>
            {busy ? "Checking…" : "Answer"}
          </button>{" "}
          {notice && <span role="status">{notice}</span>}
        </>
      )}
      {result && (
        <div role="status">
          <p className={result.correct ? "status passed" : "status failed"}>
            {result.correct ? "Correct." : "Not quite."}
          </p>
          {result.mastery_changes.length === 0 ? (
            <p className="empty">Your mastery already counts this answer.</p>
          ) : (
            <ul className="ledger">
              {result.mastery_changes.map((c) => (
                <li key={c.concept}>
                  <span className={c.after >= c.before ? "up" : "down"}>
                    {pretty(c.concept)}: {percent(c.before)} to {percent(c.after)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {result.next_step && (
            <p>
              Next: <a href={`#/problem/${result.next_step.problem_id}`}>{result.next_step.title}</a>
              <br />
              <small>{result.next_step.reason}</small>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
