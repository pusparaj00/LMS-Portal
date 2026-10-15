import { useEffect, useState } from "react";

import { Session, api } from "../api";

type Entry = {
  signature: string;
  problem_title: string;
  claim: string;
  line: number;
  line_text: string | null;
  concept: string;
  test_category: string;
  status: "auto_verified" | "instructor_approved" | "rejected";
  hit_count: number;
};

const STATUS_LABEL: Record<Entry["status"], string> = {
  auto_verified: "checked automatically",
  instructor_approved: "approved",
  rejected: "rejected, not shown to students",
};

const pretty = (name: string) => name.replace(/_/g, " ");

/** F-62: review the explanations that are reused for later students with the same failure. */
export function StoredExplanations({ session, courseId }: { session: Session; courseId: number }) {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ signature: string | null; message: string } | null>(null);
  const canDecide = session.role === "instructor";

  useEffect(() => {
    api<Entry[]>(`/courses/${courseId}/explanations`, session)
      .then(setEntries)
      .catch((e: Error) => setError({ signature: null, message: e.message }));
  }, [courseId]);

  async function decide(entry: Entry, decision: "approve" | "reject", claim?: string) {
    setBusy(true);
    setError(null);
    try {
      const updated = await api<Entry>(`/explanations/${entry.signature}/approve`, session, {
        body: { decision, ...(claim !== undefined ? { claim } : {}) },
      });
      setEntries((list) => list && list.map((e) => (e.signature === updated.signature ? updated : e)));
      setEditing(null);
    } catch (e) {
      setError({ signature: entry.signature, message: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  if (entries === null)
    return error ? (
      <p role="alert" className="error">
        {error.message}
      </p>
    ) : (
      <p>Loading…</p>
    );

  return (
    <>
      <h2>Stored explanations</h2>
      <p>
        When a student's failure matches one of these, the stored explanation is shown again instead of asking the
        model. It is checked against that student's code first. Rejected explanations are never shown.
      </p>
      {entries.length === 0 ? (
        <p className="empty">No explanation has been stored yet. They appear after students get verified explanations.</p>
      ) : (
        <ul className="rows review">
          {entries.map((entry) => (
            <li key={entry.signature}>
              <div className="review-head">
                <strong className="grow">{entry.problem_title}</strong>
                <span className="tag">{STATUS_LABEL[entry.status]}</span>
                <span className="tag">
                  shown {entry.hit_count} {entry.hit_count === 1 ? "time" : "times"} again
                </span>
              </div>
              <small>
                Failing {pretty(entry.test_category)} test, concept {pretty(entry.concept)}, line {entry.line}
                {entry.line_text ? (
                  <>
                    : <code>{entry.line_text}</code>
                  </>
                ) : null}
              </small>
              {editing === entry.signature ? (
                <label className="stack">
                  <span>Explanation shown to students</span>
                  <textarea value={draft} maxLength={400} rows={3} onChange={(e) => setDraft(e.target.value)} />
                </label>
              ) : (
                <p className="claim">{entry.claim}</p>
              )}
              {error?.signature === entry.signature && (
                <p role="alert" className="error">
                  {error.message}
                </p>
              )}
              {canDecide && (
                <div className="actions">
                  {editing === entry.signature ? (
                    <>
                      <button
                        className="primary"
                        disabled={busy || !draft.trim()}
                        onClick={() => decide(entry, "approve", draft)}
                      >
                        Save and approve
                      </button>
                      <button disabled={busy} onClick={() => setEditing(null)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      {entry.status !== "instructor_approved" && (
                        <button className="primary" disabled={busy} onClick={() => decide(entry, "approve")}>
                          Approve
                        </button>
                      )}
                      <button
                        disabled={busy}
                        onClick={() => {
                          setEditing(entry.signature);
                          setDraft(entry.claim);
                          setError(null);
                        }}
                      >
                        Edit
                      </button>
                      {entry.status !== "rejected" && (
                        <button disabled={busy} onClick={() => decide(entry, "reject")}>
                          Reject
                        </button>
                      )}
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
