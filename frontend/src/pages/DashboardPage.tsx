import { useEffect, useState } from "react";

import { Session, api } from "../api";
import { Dashboard, LedgerEntry } from "../types";
import { MasteryBars, Misconceptions } from "./MasteryBars";

const pretty = (name: string) => name.replace(/_/g, " ");

export function DashboardPage({ session, courseId }: { session: Session; courseId: number }) {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Dashboard>(`/students/me/mastery?course_id=${courseId}`, session)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [courseId]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!data) return <p>Loading…</p>;

  return (
    <>
      <p>
        <a href={`#/course/${courseId}`}>Back to problems</a>
      </p>
      <h1>My mastery</h1>
      {data.placement_available && !data.placement_completed && (
        <p className="notice">
          You have not taken the placement test yet, so every concept sits at its starting value.{" "}
          <a href={`#/placement/${courseId}`}>Take the placement test</a>
        </p>
      )}
      <MasteryBars concepts={data.concepts} courseId={courseId} />
      <small>Select a concept to see why it changed.</small>

      {data.recommended && (
        <>
          <h2>Next problem</h2>
          <p>
            <a href={`#/problem/${data.recommended.problem_id}`}>{data.recommended.title}</a>
            <br />
            <small>{data.recommended.reason}</small>
          </p>
        </>
      )}

      <h2>Misconceptions to look at</h2>
      <Misconceptions items={data.misconceptions} />

      <h2>Recent submissions</h2>
      {data.recent_submissions.length === 0 ? (
        <p className="empty">Nothing submitted yet. Pick a problem and press Submit.</p>
      ) : (
        <ul className="rows">
          {data.recent_submissions.map((s) => (
            <li key={s.submission_id}>
              <a className="grow" href={`#/problem/${s.problem_id}`}>
                {s.problem_title}
              </a>
              <span className={`status ${s.status}`}>
                {s.status === "passed" ? "Passed" : `${s.passed} passed, ${s.failed} failed`}
              </span>
              <small>{new Date(s.created_at).toLocaleString()}</small>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function WhyPage({
  session,
  courseId,
  conceptId,
  source,
  back,
}: {
  session: Session;
  courseId: number;
  conceptId: number;
  source?: string;
  back?: { href: string; label: string };
}) {
  const [entries, setEntries] = useState<LedgerEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<LedgerEntry[]>(source ?? `/students/me/mastery/${conceptId}/history`, session)
      .then(setEntries)
      .catch((e: Error) => setError(e.message));
  }, [conceptId, source]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!entries) return <p>Loading…</p>;
  const name = entries[0] ? pretty(entries[0].concept) : "this concept";

  return (
    <>
      <p>
        <a href={back?.href ?? `#/mastery/${courseId}`}>{back?.label ?? "Back to my mastery"}</a>
      </p>
      <h1>Why {name} changed</h1>
      {entries.length === 0 && <p className="empty">Nothing has changed yet. Answer a question or submit code.</p>}
      <ul className="ledger">
        {entries.map((e, i) => {
          const delta = e.p_after - e.p_before;
          return (
            <li key={i}>
              <span className={delta >= 0 ? "up" : "down"}>
                {Math.round(e.p_before * 100)}% to {Math.round(e.p_after * 100)}%
              </span>
              <span>{e.explanation}</span>
              <small>
                {new Date(e.created_at).toLocaleString()} · rule {pretty(e.rule_id)}, evidence {pretty(e.evidence_type)}
              </small>
            </li>
          );
        })}
      </ul>
    </>
  );
}
