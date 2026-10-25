import { CodeEditor as Editor } from "./CodeEditor";
import { useEffect, useRef, useState } from "react";

import { ApiError, BUSY_RETRIES, DRAFT_PREFIX, ProblemDetail, Session, SubmissionResult, api } from "../api";
import { editorLanguage, starterComment } from "../design/language";
import { recordRecent } from "../design/recent";
import { FeedbackPanel } from "./FeedbackPanel";
import { HelpPolicy } from "./HelpPolicy";
import { withoutFences } from "../statement";

const STARTER = "# Read from input(), print the answer.\n";

// An unsent draft survives moving to another page and back for the rest of the browser session (F-10).
// Logging out clears every draft (see saveSession).
const draftKey = (problemId: number) => `${DRAFT_PREFIX}${problemId}`;

function loadDraft(problemId: number): string {
  try {
    return sessionStorage.getItem(draftKey(problemId)) ?? STARTER;
  } catch {
    return STARTER;
  }
}

function saveDraft(problemId: number, code: string): void {
  try {
    sessionStorage.setItem(draftKey(problemId), code);
  } catch {
    // storage can be blocked; the draft then lasts only while the page is open
  }
}

const ERROR_TEXT: Record<string, string> = {
  syntax_error: "Your code has a syntax error.",
  runtime_error: "Your code stopped with an error.",
  time_limit: "Your code ran too long.",
  memory_limit: "Your code used too much memory.",
  output_limit: "Your code printed too much output.",
};

type CustomRun = { status: string; stdout: string; stderr: string; runtime_ms: number };

/** F-14: what the program printed for the input typed above. It is not graded and is not stored. */
function CustomOutput({ run }: { run: CustomRun }) {
  return (
    <div className="custom-output" aria-live="polite">
      <p className="eyebrow">
        Output of your run · {run.runtime_ms} ms
        {run.status !== "ok" && ` · ${ERROR_TEXT[run.status] ?? run.status}`}
      </p>
      {run.stdout !== "" || run.stderr === "" ? <pre>{run.stdout === "" ? "(no output)" : run.stdout}</pre> : null}
      {run.stderr !== "" && <pre className="stderr">{run.stderr}</pre>}
    </div>
  );
}

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
  const [stdin, setStdin] = useState("");
  const [custom, setCustom] = useState<CustomRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The problem now on screen: a run that finishes after the student moved to another problem must not show there.
  const current = useRef(problemId);
  current.current = problemId;

  useEffect(() => {
    setProblem(null);
    setResult(null);
    setCustom(null);
    setStdin("");
    setError(null);
    setCode(loadDraft(problemId));
    api<ProblemDetail>(`/problems/${problemId}`, session)
      .then((p) => {
        setProblem(p);
        recordRecent({ href: `#/problem/${problemId}`, title: p.title });
        setCode((prev) => (prev === STARTER ? starterComment(p.language) : prev));
      })
      .catch((e: Error) => setError(e.message));
  }, [problemId]);

  async function execute(kind: "run" | "submit" | "custom") {
    const asked = problemId;
    setBusy(true);
    setError(null);
    try {
      if (kind === "custom") {
        const r = await api<CustomRun>("/submissions/run-custom", session, {
          body: { problem_id: problemId, code, stdin },
          onBusy: (attempt) => setNotice(`The sandbox is busy, trying again (${attempt} of ${BUSY_RETRIES})…`),
        });
        if (current.current === asked) setCustom(r);
        return;
      }
      const path = kind === "run" ? "/submissions/run" : "/submissions";
      const r = await api<SubmissionResult>(path, session, {
        body: { problem_id: problemId, code },
        onBusy: (attempt) => setNotice(`The sandbox is busy, trying again (${attempt} of ${BUSY_RETRIES})…`),
      });
      if (current.current !== asked) return;
      setResult(r);
      setSubmitted(kind === "submit");
    } catch (e) {
      if (current.current === asked) setError(e instanceof ApiError ? e.message : "The server could not be reached.");
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
          <p>{withoutFences(problem.statement)}</p>
          <span className="tags">
            {problem.concepts.map((c) => (
              <span key={c.concept_id} className="tag">
                {c.name.replace(/_/g, " ")}
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
              defaultLanguage={editorLanguage(problem?.language)}
              value={code}
              onChange={(v) => {
                setCode(v ?? "");
                saveDraft(problemId, v ?? "");
              }}
              options={{ minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false }}
            />
          </div>
          <label className="stdin">
            <span className="eyebrow">Input for your run (optional)</span>
            <textarea
              value={stdin}
              maxLength={10000}
              rows={3}
              spellCheck={false}
              placeholder="Type what the program should read with input(), one line per call"
              onChange={(e) => setStdin(e.target.value)}
            />
          </label>
          <div className="actions">
            <button className="primary" onClick={() => execute("custom")} disabled={busy}>
              Run
            </button>
            <button onClick={() => execute("run")} disabled={busy || !isStudent}>
              Run examples
            </button>
            <button onClick={() => execute("submit")} disabled={busy || !isStudent}>
              Submit
            </button>
            {busy && <span role="status">{notice ?? "Running in the sandbox…"}</span>}
            {!isStudent && <span>Only students can run the examples and submit.</span>}
          </div>
          {error && <p role="alert" className="error">{error}</p>}
          {custom && <CustomOutput run={custom} />}
          {session.role === "instructor" && <HelpPolicy session={session} problemId={problemId} />}
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
