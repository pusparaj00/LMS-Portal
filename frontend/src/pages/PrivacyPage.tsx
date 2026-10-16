import { useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { ErasureSection, ErasureState } from "./ErasureSection";

export type ConsentState = { version: string; accepted: boolean; accepted_at: string | null; withdrawn_at: string | null };
type Notice = {
  version: string;
  title: string;
  sections: { heading: string; paragraphs: string[] }[];
  providers: { name: string; order: string }[];
};

const when = (iso: string) => new Date(iso).toLocaleString();

/**
 * TR-S-05: the privacy notice. As a gate it blocks a student until they agree; on the Privacy page it can be read at any
 * time and a student can withdraw. `onChange` reports the new state so the app can lock or unlock the rest.
 */
export function PrivacyPage({
  session,
  state,
  gate,
  onChange,
  erasure,
  onErasureChange,
}: {
  session: Session;
  state: ConsentState | null;
  gate: boolean;
  onChange: (state: ConsentState) => void;
  erasure: ErasureState | null;
  onErasureChange: (state: ErasureState) => void;
}) {
  const [notice, setNotice] = useState<Notice | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const student = session.role === "student";

  useEffect(() => {
    api<Notice>("/consent/notice", session)
      .then(setNotice)
      .catch((e: Error) => setError(e.message));
  }, []);

  async function act(path: "/consent/accept" | "/consent/withdraw") {
    if (!notice) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api<ConsentState>(path, session, {
        method: "POST",
        body: path === "/consent/accept" ? { version: notice.version } : {},
      });
      setConfirming(false);
      onChange(next);
      if (gate && next.accepted) window.location.hash = "#/courses";
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  if (!notice)
    return error ? (
      <p role="alert" className="error">
        {error}
      </p>
    ) : (
      <p>Loading…</p>
    );

  return (
    <article className="notice-page">
      <h1>{gate ? "Before you start: how your data is used" : notice.title}</h1>
      {gate && <p>Please read this and agree to continue. You can withdraw later from Privacy in the top bar.</p>}
      {notice.sections.map((section) => (
        <section key={section.heading}>
          <h2>{section.heading}</h2>
          {section.paragraphs.map((p) => (
            <p key={p}>{p}</p>
          ))}
          {section.heading === "Who receives it" && (
            <>
              {notice.providers.length > 0 && <p>The model providers that can receive a request, in the order they are tried:</p>}
              <ul className="provider-list">
                {notice.providers.map((p) => (
                  <li key={p.name}>
                    <strong>{p.name}</strong> <small>({p.order})</small>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      ))}
      <small>Notice version {notice.version}</small>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {student && (
        <div className="consent-actions">
          {!gate && state?.accepted && (
            <p role="status">You agreed on {when(state.accepted_at as string)}.</p>
          )}
          {!gate && state && !state.accepted && (
            <p role="status">
              {state.withdrawn_at ? `You withdrew your agreement on ${when(state.withdrawn_at)}. ` : ""}
              Exercises and the assistant are switched off until you agree again.
            </p>
          )}
          {(!state?.accepted || gate) && (
            <button className="primary" disabled={busy} onClick={() => act("/consent/accept")}>
              I agree
            </button>
          )}
          {!gate && state?.accepted && !confirming && (
            <button disabled={busy} onClick={() => setConfirming(true)}>
              Withdraw my agreement
            </button>
          )}
          {!gate && state?.accepted && confirming && (
            <>
              <p>Exercises, the placement test and the assistant stop working for you until you agree again.</p>
              <button className="primary" disabled={busy} onClick={() => act("/consent/withdraw")}>
                Yes, withdraw
              </button>{" "}
              <button disabled={busy} onClick={() => setConfirming(false)}>
                Keep my agreement
              </button>
            </>
          )}
        </div>
      )}
      {student && !gate && erasure && <ErasureSection session={session} state={erasure} onChange={onErasureChange} />}
    </article>
  );
}
