import { FormEvent, useState } from "react";

import { ApiError, Session, api } from "../api";

export type Concept = { concept_id: number; name: string; prerequisite_ids?: number[] };

/** F-02: add a concept to a course without leaving the page. The new concept is reported back so it can be picked. */
export function ConceptAdder({
  session,
  courseId,
  onAdded,
}: {
  session: Session;
  courseId: number;
  onAdded: (concept: Concept) => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    event.stopPropagation();
    setBusy(true);
    setError(null);
    try {
      const concept = await api<Concept>(`/courses/${courseId}/concepts`, session, { body: { name } });
      setName("");
      onAdded(concept);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  // Not a nested <form>: the problem form around it must not be submitted by this field.
  return (
    <div className="concept-adder">
      <label>
        New concept
        <input
          value={name}
          maxLength={60}
          placeholder="for example: string formatting"
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") add(e as unknown as FormEvent);
          }}
        />
      </label>
      <button type="button" disabled={busy || name.trim().length < 2} onClick={(e) => add(e as unknown as FormEvent)}>
        Add concept
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
