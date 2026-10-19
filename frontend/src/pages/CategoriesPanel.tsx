import { FormEvent, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";

export type Category = { id: number; name: string; weight: number; share: number; assignments: number };

/** F-87: the course's grade categories and their weights. The overall grade is the weighted mean of the categories. */
export function CategoriesPanel({ session, courseId, onChange }: { session: Session; courseId: number; onChange: () => void }) {
  const base = `/courses/${courseId}/categories`;
  const [items, setItems] = useState<Category[] | null>(null);
  const [name, setName] = useState("");
  const [weight, setWeight] = useState(10);
  const [editing, setEditing] = useState<Category | null>(null);
  const [error, setError] = useState<string | null>(null);
  const teacher = session.role === "instructor";

  useEffect(() => {
    api<Category[]>(base, session)
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, [courseId]);

  async function run(call: () => Promise<Category[]>, failure: string) {
    setError(null);
    try {
      setItems(await call());
      setEditing(null);
      setName("");
      onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : failure);
    }
  }

  const add = (event: FormEvent) => {
    event.preventDefault();
    run(() => api<Category[]>(base, session, { body: { name, weight } }), "Could not add the category.");
  };
  const save = (event: FormEvent) => {
    event.preventDefault();
    if (editing)
      run(
        () => api<Category[]>(`${base}/${editing.id}`, session, { method: "PUT", body: { name: editing.name, weight: editing.weight } }),
        "Could not save the category.",
      );
  };

  return (
    <section className="panel" aria-label="Grade categories">
      <h2>Grade categories</h2>
      <small>
        With categories, each student's overall grade is the weighted mean of their category percentages. A category with nothing
        given to a student yet is left out. Assignments without a category do not count in it.
      </small>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {items && items.length === 0 && <p className="empty">No categories: the course score is the points total.</p>}
      <ul className="rows">
        {items?.map((c) => (
          <li key={c.id}>
            {editing?.id === c.id ? (
              <form className="inline-form grow" onSubmit={save}>
                <label>
                  Name
                  <input value={editing.name} maxLength={100} required onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
                </label>
                <label>
                  Weight
                  <input type="number" min={1} max={100} step={1} value={editing.weight} onChange={(e) => setEditing({ ...editing, weight: Number(e.target.value) })} />
                </label>
                <button type="submit">Save</button>
                <button type="button" onClick={() => setEditing(null)}>
                  Cancel
                </button>
              </form>
            ) : (
              <>
                <span className="grow">
                  <strong>{c.name}</strong> <small>weight {c.weight} · {c.share}% of the grade · {c.assignments} assignments</small>
                </span>
                {teacher && (
                  <>
                    <button onClick={() => setEditing(c)}>Edit</button>
                    <button
                      className="link"
                      onClick={() => {
                        if (window.confirm(`Delete "${c.name}"? Its assignments stay and stop counting in the overall grade.`))
                          run(() => api<Category[]>(`${base}/${c.id}`, session, { method: "DELETE" }), "Could not delete the category.");
                      }}
                    >
                      Delete
                    </button>
                  </>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      {teacher && (
        <form className="inline-form" onSubmit={add}>
          <label>
            New category
            <input value={name} maxLength={100} required placeholder="for example Homework" onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Weight
            <input type="number" min={1} max={100} step={1} value={weight} onChange={(e) => setWeight(Number(e.target.value))} />
          </label>
          <button type="submit">Add category</button>
        </form>
      )}
    </section>
  );
}
