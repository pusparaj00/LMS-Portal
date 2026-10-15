import Editor from "@monaco-editor/react";
import { useEffect, useState } from "react";

import { ApiError, BUSY_RETRIES, ProblemDetail, Session, SubmissionResult, api } from "../api";
import { FeedbackPanel } from "./FeedbackPanel";

const STARTER = "# Read from input(), print the answer.\n";

const ERROR_TEXT: Record<string, string> = {
  syntax_error: "Your code has a syntax error.",
  runtime_error: "Your code stopped with an error.",
  time_limit: "Your code ran too long.",
  memory_limit: "Your code used too much memory.",
  output_limit: "Your code printed too much output.",
};

function Summary({ result, submitted }: { result: SubmissionResult; submitted: boolean }) {
  const total = result.passed + result.failed;
  const headline =
    result.status === "passed"
      ? "Accepted"
      : result.status === "error"
        ? "Could not run"
        : `${result.failed} of ${total} tests failed`;
  return (
    <div className={`summary ${result.status}`}>
      <strong>{headline}</strong>
      <span>
        {submitted ? `${result.passed} of ${total} tests passed` : `${result.passed} of ${total} examples passed`}
        {" · "}
        {result.runtime_ms} ms
      </span>
      {result.error_type && <span>{ERROR_TEXT[result.error_type] ?? result.error_type}</span>}
      {submitted && result.failed_categories.length > 0 && (
        <span>Failing categories: {result.failed_categories.join(", ")}</span>
      )}
    </div>
  );
}

export function ProblemPage({ session, problemId }: { session: Session; problemId: number }) {
  const [problem, setProblem] = useState<ProblemDetail | null>(null);
  const [code, setCode] = useState(STARTER);
  const [result, setResult] = useState<SubmissionResult | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setProblem(null);
    setResult(null);
    setError(null);
    setCode(STARTER);
    api<ProblemDetail>(`/problems/${problemId}`, session)
      .then(setProblem)
      .catch((e: Error) => setError(e.message));
  }, [problemId]);

  async function execute(kind: "run" | "submit") {
    setBusy(true);
    setError(null);
    try {
      const path = kind === "run" ? "/submissions/run" : "/submissions";
      const r = await api<SubmissionResult>(path, session, {
        body: { problem_id: problemId, code },
        onBusy: (attempt) => setNotice(`The sandbox is busy, trying again (${attempt} of ${BUSY_RETRIES})…`),
      });
      setResult(r);
      setSubmitted(kind === "submit");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setBusy(false);
      setNotice(null);
    }
  }

  if (error && !problem) return <p role="alert" className="error">{error}</p>;
  if (!problem) return <p>Loading…</p>;
  const isStudent = session.role === "student";

  return (
    <>
      <p>
        <a href={`#/course/${problem.course_id}`}>Back to problems</a>
      </p>
      <div className="workspace">
        <section className="statement">
          <h1>{problem.title}</h1>
          <p>{problem.statement}</p>
          <span className="tags">
            {problem.concepts.map((c) => (
              <span key={c.concept_id} className="tag">
                {c.name}
              </span>
            ))}
          </span>
          <h2>Examples</h2>
          {problem.examples.map((ex, i) => (
            <div key={i} className="example">
              <div>
                <small>Input</small>
                <pre>{ex.input}</pre>
              </div>
              <div>
                <small>Output</small>
                <pre>{ex.expected}</pre>
              </div>
            </div>
          ))}
        </section>

        <section className="solve">
          <div className="editor">
            <Editor
              height="100%"
              defaultLanguage="python"
              value={code}
              onChange={(v) => setCode(v ?? "")}
              options={{ minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false }}
            />
          </div>
          <div className="actions">
            <button onClick={() => execute("run")} disabled={busy || !isStudent}>
              Run examples
            </button>
            <button className="primary" onClick={() => execute("submit")} disabled={busy || !isStudent}>
              Submit
            </button>
            {busy && <span role="status">{notice ?? "Running in the sandbox…"}</span>}
            {!isStudent && <span>Only students can run code.</span>}
          </div>
          {error && <p role="alert" className="error">{error}</p>}
          {result && (
            <div className="results" aria-live="polite">
              <Summary result={result} submitted={submitted} />
              {submitted && result.submission_id !== null && result.status !== "passed" && (
                <FeedbackPanel key={result.submission_id} session={session} submissionId={result.submission_id} />
              )}
              <ul className="tests">
                {result.visible_tests.map((t, i) => (
                  <li key={i} className={t.passed ? "pass" : "fail"}>
                    <span className="mark">{t.passed ? "Passed" : "Failed"}</span>
                    <div>
                      <small>Input</small>
                      <pre>{t.input}</pre>
                    </div>
                    <div>
                      <small>Expected</small>
                      <pre>{t.expected}</pre>
                    </div>
                    <div>
                      <small>Your output</small>
                      <pre>{t.status === "ok" ? t.actual : ERROR_TEXT[t.status] ?? t.status}</pre>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
