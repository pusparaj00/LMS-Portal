import { FormEvent, useEffect, useState } from "react";

import { ApiError, Course, Session, api } from "../api";
import { Concept } from "./ConceptAdder";

const pretty = (name: string) => name.replace(/_/g, " ");

type JoinCode = { code: string; enabled: boolean; link: string };
export const COLORS = ["#1a73e8", "#188038", "#e8710a", "#a142f4", "#d93025", "#12b5cb", "#5f6368"];

/** F-02: the teacher renames or archives the course and renames or deletes its concepts. Nothing here loses history. */
export function CourseSettings({ session, courseId }: { session: Session; courseId: number }) {
  const [course, setCourse] = useState<Course | null>(null);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [title, setTitle] = useState("");
  const [renaming, setRenaming] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [join, setJoin] = useState<JoinCode | null>(null);
  const [copied, setCopied] = useState(false);
  const [section, setSection] = useState("");
  const [subject, setSubject] = useState("");
  const [color, setColor] = useState("");

  const load = () =>
    Promise.all([api<Course[]>("/courses", session), api<Concept[]>(`/courses/${courseId}/concepts`, session)])
      .then(([all, list]) => {
        const found = all.find((c) => c.id === courseId) ?? null;
        setCourse(found);
        setTitle(found?.title ?? "");
        setSection(found?.section ?? "");
        setSubject(found?.subject ?? "");
        setColor(found?.color ?? "");
        setConcepts(list);
      })
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
    api<JoinCode>(`/courses/${courseId}/join-code`, session)
      .then(setJoin)
      .catch(() => setJoin(null));
  }, [courseId]);

  async function run(call: () => Promise<unknown>) {
    setError(null);
    try {
      await call();
      setRenaming(null);
      await load();
      window.dispatchEvent(new Event("lms:courses"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The change could not be saved.");
    }
  }

  const rename = (event: FormEvent) => {
    event.preventDefault();
    run(() => api(`/courses/${courseId}`, session, { method: "PATCH", body: { title } }));
  };

  const saveDetails = (event: FormEvent) => {
    event.preventDefault();
    run(() =>
      api(`/courses/${courseId}`, session, {
        method: "PATCH",
        body: { section: section.trim() || null, subject: subject.trim() || null, color: color || null },
      }),
    );
  };

  const link = join ? `${window.location.origin}/${join.link}` : "";
  const copy = async (what: string) => {
    try {
      await navigator.clipboard.writeText(what);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy; select the text and copy it.");
    }
  };
  const changeCode = (call: () => Promise<JoinCode>) =>
    call()
      .then(setJoin)
      .catch((e) => setError(e instanceof ApiError ? e.message : "The class code could not be changed."));

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
          {join && (
            <div>
              <h3>Class code</h3>
              <p>
                Students join with this code. <strong className="join-code">{join.code}</strong>{" "}
                <button onClick={() => copy(join.code)}>Copy code</button>{" "}
                <button onClick={() => copy(link)}>Copy invite link</button> {copied && <small role="status">Copied</small>}
              </p>
              <p>
                {join.enabled ? "New students can join." : "The class is closed: nobody new can join."}{" "}
                <button
                  onClick={() =>
                    changeCode(() => api<JoinCode>(`/courses/${courseId}/join-code`, session, { method: "PUT", body: { enabled: !join.enabled } }))
                  }
                >
                  {join.enabled ? "Close the class to new students" : "Open the class again"}
                </button>{" "}
                <button
                  onClick={() => {
                    if (window.confirm("Make a new code? The old code and invite link stop working. Students already in the class stay."))
                      changeCode(() => api<JoinCode>(`/courses/${courseId}/join-code/reset`, session, { method: "POST" }));
                  }}
                >
                  Reset the code
                </button>
              </p>
            </div>
          )}
          <form className="inline-form" onSubmit={saveDetails}>
            <label>
              Section
              <input value={section} maxLength={100} placeholder="for example Period 3" onChange={(e) => setSection(e.target.value)} />
            </label>
            <label>
              Subject
              <input value={subject} maxLength={100} placeholder="for example Python" onChange={(e) => setSubject(e.target.value)} />
            </label>
            <label>
              Colour
              <select value={color} onChange={(e) => setColor(e.target.value)}>
                <option value="">None</option>
                {COLORS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit">Save details</button>
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
