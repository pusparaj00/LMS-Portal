import { FormEvent, useState } from "react";

import { ApiError, Role, Session, api } from "../api";

type Token = { access_token: string; role: Role };

export function LoginPage({ onSession }: { onSession: (s: Session) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const token = await api<Token>(`/auth/${mode}`, null, { body: { email, password } });
      onSession({ token: token.access_token, role: token.role });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="narrow">
      <h1>{mode === "login" ? "Log in" : "Create a student account"}</h1>
      <form onSubmit={submit} className="stack">
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={mode === "register" ? 8 : undefined}
            required
          />
          {mode === "register" && <small>At least 8 characters.</small>}
        </label>
        {error && <p role="alert" className="error">{error}</p>}
        <button className="primary" disabled={busy}>
          {mode === "login" ? "Log in" : "Create account"}
        </button>
      </form>
      <p>
        {mode === "login" ? "New here? " : "Already registered? "}
        <button className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Create a student account" : "Log in"}
        </button>
      </p>
    </main>
  );
}
