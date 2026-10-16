import { useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";

type Policy = { max_hint_level: number; leak_threshold: number | null; effective_leak_threshold: number };

// Measured on the question bank (evaluation/leak_threshold.py): every level blocks all 120 solution fragments and lets
// all 137 ordinary explanations through; a stricter level also blocks more short code that merely resembles the solution.
const LEVELS = [
  { value: "", label: "Standard", detail: "the threshold tuned on the question bank" },
  { value: "0.5", label: "Strict", detail: "also refuses short code that partly resembles the solution" },
  { value: "0.3", label: "Very strict", detail: "refuses most code that resembles the solution at all" },
];

/** F-62: the teacher sets how many hints a student may take on this problem and how strict the leak guard is. */
export function HelpPolicy({ session, problemId }: { session: Session; problemId: number }) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [hints, setHints] = useState(3);
  const [level, setLevel] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Policy>(`/problems/${problemId}/policy`, session)
      .then((p) => {
        setPolicy(p);
        setHints(p.max_hint_level);
        setLevel(p.leak_threshold === null ? "" : String(p.leak_threshold));
      })
      .catch((e: Error) => setError(e.message));
  }, [problemId]);

  async function save() {
    setError(null);
    setSaved(null);
    try {
      const next = await api<Policy>(`/problems/${problemId}/policy`, session, {
        method: "PUT",
        body: { max_hint_level: hints, leak_threshold: level === "" ? null : Number(level) },
      });
      setPolicy(next);
      setSaved("Saved. It applies to every explanation and hint from now on.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The policy could not be saved.");
    }
  }

  if (!policy) return error ? <p role="alert" className="error">{error}</p> : null;
  return (
    <section className="help-policy">
      <h2>Help for this problem</h2>
      <label>
        Hints a student may take
        <select value={hints} onChange={(e) => setHints(Number(e.target.value))}>
          <option value={1}>1: concept only</option>
          <option value={2}>2: concept and where to look</option>
          <option value={3}>3: also a worked example on another problem</option>
        </select>
      </label>
      <label>
        How strictly replies are kept from resembling the solution
        <select value={level} onChange={(e) => setLevel(e.target.value)}>
          {LEVELS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}: {l.detail}
            </option>
          ))}
        </select>
        <small>A full solution is never shown at any level; this can only make the check stricter.</small>
      </label>
      <p className="actions">
        <button onClick={save}>Save help settings</button>
        {saved && <span role="status">{saved}</span>}
      </p>
      {error && <p role="alert" className="error">{error}</p>}
    </section>
  );
}
