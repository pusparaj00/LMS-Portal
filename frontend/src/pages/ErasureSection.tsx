import { useState } from "react";

import { ApiError, Session, api } from "../api";

export type ErasureState = { confirm_with: "password" | "lms"; pending: boolean; kind: "requested" | "retention" | null; notified_at: string | null; due_at: string | null };

const when = (iso: string) => new Date(iso).toLocaleString();

/** TR-S-07: delete my data. Deletion waits 48 hours so the student sees the date and can cancel. */
export function ErasureSection({
  session,
  state,
  onChange,
}: {
  session: Session;
  state: ErasureState;
  onChange: (state: ErasureState) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const lms = state.confirm_with === "lms";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(call: () => Promise<ErasureState>) {
    setBusy(true);
    setError(null);
    try {
      onChange(await call());
      setConfirming(false);
      setPassword("");
      setConfirmed(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="erasure">
      <h2>Delete my data</h2>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {state.pending ? (
        <>
          <p role="status">
            Your account and everything in it will be deleted on <strong>{when(state.due_at as string)}</strong>
            {state.kind === "retention" ? " because it has been inactive." : "."} Until then you can cancel.
          </p>
          <button disabled={busy} onClick={() => run(() => api<ErasureState>("/me/erasure", session, { method: "DELETE" }))}>
            Cancel deletion
          </button>
        </>
      ) : confirming ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const body = lms ? { confirm: confirmed } : { password };
            run(() => api<ErasureState>("/me/erasure", session, { method: "POST", body }));
          }}
        >
          <p>
            This deletes your account, submissions, chat messages and mastery in 48 hours. It cannot be undone after that.
            {lms ? "You opened this tool from your LMS, so tick the box to confirm." : "Enter your password to confirm."}
          </p>
          {lms ? (
            <label className="inline">
              <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
              Yes, delete my data
            </label>
          ) : (
            <label>
              Password
              <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
          )}{" "}
          <button className="primary" type="submit" disabled={busy || (lms ? !confirmed : !password)}>
            Delete my data in 48 hours
          </button>{" "}
          <button type="button" disabled={busy} onClick={() => setConfirming(false)}>
            Keep my data
          </button>
        </form>
      ) : (
        <button disabled={busy} onClick={() => setConfirming(true)}>
          Delete my account and data
        </button>
      )}
    </section>
  );
}

export function ErasureBanner({ state }: { state: ErasureState }) {
  if (!state.pending) return null;
  return (
    <p role="status" className="erasure-banner">
      Your data will be deleted on {when(state.due_at as string)}. <a href="#/privacy">Cancel on the Privacy page</a>
    </p>
  );
}
