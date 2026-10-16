import { FormEvent, useState } from "react";

import { ApiError, Role, Session, api } from "../api";

export type Me = {
  id: number;
  email: string;
  role: Role;
  display_name: string | null;
  must_change_password: boolean;
  opened_from_lms: boolean;
};

/** F-01: the user's own name and password. When a new password is required, this is the only page shown. */
export function AccountPage({
  session,
  me,
  onMe,
  onSession,
}: {
  session: Session;
  me: Me;
  onMe: (me: Me) => void;
  onSession: (session: Session) => void;
}) {
  const [name, setName] = useState(me.display_name ?? "");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function saveName(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(null);
    try {
      onMe(await api<Me>("/me", session, { method: "PATCH", body: { display_name: name.trim() || null } }));
      setSaved("Your name is saved.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Your name could not be saved.");
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(null);
    if (next !== repeat) {
      setError("The two new passwords are not the same.");
      return;
    }
    setBusy(true);
    try {
      const token = await api<{ access_token: string; role: Role }>("/me/password", session, {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      setCurrent("");
      setNext("");
      setRepeat("");
      onSession({ token: token.access_token, role: token.role });
      onMe({ ...me, must_change_password: false });
      setSaved("Your password is changed. You stay signed in here; every other session was signed out.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Your password could not be changed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="narrow">
      <h1>{me.must_change_password ? "Choose a new password" : "Account"}</h1>
      {me.must_change_password && (
        <p className="notice">You signed in with a temporary password. Choose your own to continue.</p>
      )}
      <p>
        {me.email} · {me.role}
      </p>
      {error && <p role="alert" className="error">{error}</p>}
      {saved && <p role="status">{saved}</p>}

      {!me.must_change_password && (
        <form className="stack" onSubmit={saveName}>
          <h2>Your name</h2>
          <label>
            Name shown to your teachers
            <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
            <small>Optional. It is never sent to the AI model. Leave it empty to remove it.</small>
          </label>
          <p>
            <button type="submit">Save name</button>
          </p>
        </form>
      )}

      {me.opened_from_lms ? (
        <p>You sign in through your LMS, so there is no password to change here.</p>
      ) : (
        <form className="stack" onSubmit={changePassword}>
          <h2>Password</h2>
          <label>
            {me.must_change_password ? "Temporary password" : "Current password"}
            <input type="password" autoComplete="current-password" value={current} required onChange={(e) => setCurrent(e.target.value)} />
          </label>
          <label>
            New password
            <input type="password" autoComplete="new-password" value={next} required minLength={8} maxLength={72} onChange={(e) => setNext(e.target.value)} />
            <small>At least 8 characters.</small>
          </label>
          <label>
            New password again
            <input type="password" autoComplete="new-password" value={repeat} required onChange={(e) => setRepeat(e.target.value)} />
          </label>
          <p>
            <button className="primary" type="submit" disabled={busy}>
              Change password
            </button>
          </p>
        </form>
      )}
    </article>
  );
}
