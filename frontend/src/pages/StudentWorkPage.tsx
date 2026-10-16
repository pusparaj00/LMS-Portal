import { useEffect, useState } from "react";

import { Session, api } from "../api";
import { ConceptMastery, Misconception } from "../types";
import { MasteryBars, Misconceptions } from "./MasteryBars";

type Submission = {
  submission_id: number;
  problem_id: number;
  problem_title: string;
  created_at: string;
  status: string;
  passed: number;
  failed: number;
};
type Work = {
  student_id: number;
  label: string;
  synthetic: boolean;
  concepts: ConceptMastery[];
  misconceptions: Misconception[];
  submissions: Submission[];
};
type Detail = Submission & {
  code: string;
  error_type: string | null;
  failed_categories: string[];
  visible_tests: { input: string; expected: string; passed: boolean }[] | null;
  hidden_failed: number | null;
  explanation: { requested: boolean; attempts: number; outcome: "verified" | "template" | null; from_cache: boolean; text: string | null };
};

const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
const pretty = (name: string) => name.replace(/_/g, " ");

function useLoad<T>(path: string, session: Session): [T | null, string | null] {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setData(null);
    api<T>(path, session)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [path]);
  return [data, error];
}

/** F-61, F-34: one student's mastery, why it changed, and their submissions, for the course's teacher. */
export function StudentWorkPage({ session, courseId, studentId }: { session: Session; courseId: number; studentId: number }) {
  const base = `#/class/${courseId}/student/${studentId}`;
  const [work, error] = useLoad<Work>(`/courses/${courseId}/students/${studentId}`, session);
  if (error) return <p role="alert" className="error">{error}</p>;
  if (!work) return <p>Loading…</p>;
  return (
    <>
      <p>
        <a href={`#/class/${courseId}`}>Back to the class overview</a>
      </p>
      <h1>
        {work.label} {work.synthetic && <span className="tag">synthetic</span>}
      </h1>
      <h2>Mastery</h2>
      <MasteryBars concepts={work.concepts} link={(id) => `${base}/concept/${id}`} />
      <small>Open a concept to see each change and the evidence behind it.</small>
      <h2>Suspected misconceptions</h2>
      <Misconceptions items={work.misconceptions} />
      <h2>Submissions</h2>
      {work.submissions.length === 0 && <p className="empty">No submissions in this course yet.</p>}
      <ul className="rows">
        {work.submissions.map((s) => (
          <li key={s.submission_id}>
            <a className="grow" href={`${base}/submission/${s.submission_id}`}>
              {s.problem_title}
              <br />
              <small>{when(s.created_at)}</small>
            </a>
            <span className={`status status-${s.status === "passed" ? "complete" : "missing"}`}>
              {s.status} · {s.passed}/{s.passed + s.failed}
            </span>
          </li>
        ))}
      </ul>
      <small>Shows the newest 100. The student's messages to the assistant are not shown.</small>
    </>
  );
}

/** One submission as the student made it: the code, its result and any explanation. Opening it is recorded. */
export function SubmissionView({
  session,
  courseId,
  studentId,
  submissionId,
}: {
  session: Session;
  courseId: number;
  studentId: number;
  submissionId: number;
}) {
  const [s, error] = useLoad<Detail>(`/courses/${courseId}/students/${studentId}/submissions/${submissionId}`, session);
  if (error) return <p role="alert" className="error">{error}</p>;
  if (!s) return <p>Loading…</p>;
  const lines = s.code.split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  const e = s.explanation;
  return (
    <>
      <p>
        <a href={`#/class/${courseId}/student/${studentId}`}>Back to the student</a>
      </p>
      <h1>{s.problem_title}</h1>
      <p>
        Submitted {when(s.created_at)} · <strong>{s.status}</strong> · {s.passed} of {s.passed + s.failed} tests passed
        {s.error_type && ` · ${pretty(s.error_type)}`}
      </p>
      {s.failed_categories.length > 0 && <p>Failing categories: {s.failed_categories.map(pretty).join(", ")}</p>}
      <pre className="code-view" aria-label="Submitted code">
        {lines.map((line, i) => (
          <span key={i} className="code-line">
            <span className="line-no" aria-hidden="true">
              {i + 1}
            </span>
            {line}
            {"\n"}
          </span>
        ))}
      </pre>
      <h2>Tests</h2>
      {s.visible_tests === null ? (
        <p className="notice">The tests were changed after this submission, so only the totals above are known.</p>
      ) : (
        <>
          <ul className="tests">
            {s.visible_tests.map((t, i) => (
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
              </li>
            ))}
          </ul>
          {s.hidden_failed !== null && s.hidden_failed > 0 && (
            <p>
              {s.hidden_failed} hidden {s.hidden_failed === 1 ? "test" : "tests"} failed (hidden tests are never shown).
            </p>
          )}
        </>
      )}
      <h2>Explanation</h2>
      {!e.requested ? (
        <p className="empty">The student did not ask for an explanation.</p>
      ) : (
        <>
          <p>
            {e.outcome === "verified" ? "A checked explanation was shown" : "A template explanation was shown"}
            {e.from_cache ? ", from the stored explanations" : ` after ${e.attempts} model ${e.attempts === 1 ? "attempt" : "attempts"}`}.
          </p>
          {e.text ? <blockquote>{e.text}</blockquote> : <small>The text is kept for 24 hours and is no longer available.</small>}
        </>
      )}
    </>
  );
}
