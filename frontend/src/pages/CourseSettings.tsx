import { FormEvent, useEffect, useState } from "react";

import { ApiError, Course, Session, api } from "../api";
import { Concept } from "./ConceptAdder";

const pretty = (name: string) => name.replace(/_/g, " ");

/** F-02: the teacher renames or archives the course and renames or deletes its concepts. Nothing here loses history. */
export function CourseSettings({ session, courseId }: { session: Session; courseId: number }) {
  const [course, setCourse] = useState<Course | null>(null);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [title, setTitle] = useState("");
  const [renaming, setRenaming] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const load = () =>
    Promise.all([api<Course[]>("/courses", session), api<Concept[]>(`/courses/${courseId}/concepts`, session)])
      .then(([all, list]) => {
        const found = all.find((c) => c.id === courseId) ?? null;
        setCourse(found);
        setTitle(found?.title ?? "");
        setConcepts(list);
      })
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, [courseId]);

  async function run(call: () => Promise<unknown>) {
    setError(null);
    try {
      await call();
      setRenaming(null);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The change could not be saved.");
    }
  }

  const rename = (event: FormEvent) => {
    event.preventDefault();
    run(() => api(`/courses/${courseId}`, session, { method: "PATCH", body: { title } }));
  };

  if (!course) return null;
  return (
    <section className="course-settings">
      {course.archived && (
        <p className="notice">
          This course is archived: students no longer see it and cannot enrol.{" "}
          <button onClick={() => run(() => api(`/courses/${courseId}/restore`, session, { method: "POST" }))}>Restore course</button>
        </p>
      )}
      <button className="link" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide course settings" : "Course settings"}
      </button>
      {open && (
        <div className="stack">
          {error && <p role="alert" className="error">{error}</p>}
          <form className="inline-form" onSubmit={rename}>
            <label>
              Course title
              <input value={title} maxLength={200} required onChange={(e) => setTitle(e.target.value)} />
            </label>
            <button type="submit">Rename course</button>
          </form>
          <div>
            <h3>Concepts</h3>
            <small>Renaming keeps every tag and all mastery history. A concept can be deleted only while nothing uses it.</small>
            <ul className="rows">
              {concepts.map((c) => (
                <li key={c.concept_id}>
                  {renaming === c.concept_id ? (
                    <form
                      className="inline-form grow"
                      onSubmit={(e) => {
                        e.preventDefault();
                        run(() => api(`/courses/${courseId}/concepts/${c.concept_id}`, session, { method: "PATCH", body: { name } }));
                      }}
                    >
                      <label>
                        New name
                        <input value={name} required minLength={2} maxLength={60} onChange={(e) => setName(e.target.value)} />
                      </label>
                      <button type="submit">Save</button>
                      <button type="button" onClick={() => setRenaming(null)}>
                        Cancel
                      </button>
                    </form>
                  ) : (
                    <>
                      <span className="grow">{pretty(c.name)}</span>
                      <button
                        aria-label={`Rename ${pretty(c.name)}`}
                        onClick={() => {
                          setRenaming(c.concept_id);
                          setName(pretty(c.name));
                        }}
                      >
                        Rename
                      </button>
                      <button
                        className="link"
                        aria-label={`Delete ${pretty(c.name)}`}
                        onClick={() => run(() => api(`/courses/${courseId}/concepts/${c.concept_id}`, session, { method: "DELETE" }))}
                      >
                        Delete
                      </button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </div>
          {!course.archived && (
            <p>
              <button
                onClick={() => {
                  if (window.confirm("Archive this course? Students stop seeing it; nothing is deleted and you can restore it."))
                    run(() => api(`/courses/${courseId}/archive`, session, { method: "POST" }));
                }}
              >
                Archive course
              </button>
            </p>
          )}
        </div>
      )}
    </section>
  );
}
