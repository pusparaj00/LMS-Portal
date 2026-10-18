import { FormEvent, useState } from "react";

import { ApiError, Role, Session, api } from "../api";
import { PublicBar } from "./HomePage";

type Token = { access_token: string; role: Role };

export function LoginPage({ onSession, initialMode = "login" }: { onSession: (s: Session) => void; initialMode?: "login" | "register" }) {
  const [mode, setMode] = useState<"login" | "register">(initialMode);
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
    <div className="pub">
    <PublicBar />
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
      <p>
        <a href="#/">Back to the home page</a>
      </p>
    </main>
    </div>
  );
}
