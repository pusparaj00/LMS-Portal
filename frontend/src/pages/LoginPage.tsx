import { FormEvent, useEffect, useState } from "react";

import { ApiError, Role, Session, api } from "../api";
import { PREFILL_KEY, PublicBar } from "./HomePage";

type Token = { access_token: string; role: Role };

export function LoginPage({ onSession, initialMode = "login" }: { onSession: (s: Session) => void; initialMode?: "login" | "register" }) {
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [history, setHistory] = useState("");
  const [interests, setInterests] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    try {
      const prefill = sessionStorage.getItem(PREFILL_KEY);
      if (prefill) {
        setEmail(prefill);
        sessionStorage.removeItem(PREFILL_KEY);
      }
    } catch {
      // storage can be blocked; the field then starts empty
    }
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body =
        mode === "register"
          ? {
              email,
              password,
              academic_history: history.trim() || null,
              interests: interests.trim() || null,
            }
          : { email, password };
      const token = await api<Token>(`/auth/${mode}`, null, { body });
      onSession({ token: token.access_token, role: token.role });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="home auth">
    <PublicBar />
    <main className="narrow">
      <div className="auth-form">
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

        {mode === "register" && (
          <>
            <h2>Build your profile</h2>
            <label>
              Academic history
              <textarea value={history} maxLength={1000} rows={3} onChange={(e) => setHistory(e.target.value)} />
              <small>Optional, for example: class 12, finished an introductory programming course.</small>
            </label>
            <label>
              Areas of interest
              <textarea value={interests} maxLength={500} rows={2} onChange={(e) => setInterests(e.target.value)} />
              <small>Optional, for example: web development, data science, games.</small>
            </label>
          </>
        )}

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
      </div>
      <img
        className="auth-picture"
        src="/archive/eniac.jpg"
        width={1920}
        height={1318}
        alt="Two women operating the ENIAC computer in 1946"
      />
    </main>
    </div>
  );
}
