import { FormEvent, useEffect, useState } from "react";

import { ApiError, Course, Session, api } from "../api";

export function CoursesPage({ session }: { session: Session }) {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [filter, setFilter] = useState("");
  const [code, setCode] = useState("");

  const load = () =>
    api<Course[]>("/courses", session)
      .then(setCourses)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const course = await api<Course>("/courses", session, { body: { title: newTitle } });
      window.location.hash = `#/course/${course.id}`;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the course.");
    }
  }

  async function join(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const course = await api<Course>("/courses/join", session, { body: { code } });
      window.location.hash = `#/course/${course.id}`;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not join the class.");
    }
  }

  const needle = filter.trim().toLowerCase();
  // Students see their own courses first; everyone can narrow a long list by title.
  const shown = (courses ?? [])
    .filter((c) => c.title.toLowerCase().includes(needle))
    .sort((a, b) => (session.role === "student" ? Number(b.enrolled) - Number(a.enrolled) : 0));

  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow">{session.role === "admin" ? "Everything on this system" : "Your learning space"}</p>
          <h1>{session.role === "admin" ? "All courses" : session.role === "instructor" ? "My courses" : "Courses"}</h1>
        </div>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {session.role === "student" && (
        <form className="inline-form" onSubmit={join}>
          <label>
            Class code
            <input value={code} maxLength={40} required autoComplete="off" onChange={(e) => setCode(e.target.value)} />
          </label>
          <button className="primary" type="submit">
            Join class
          </button>
        </form>
      )}
      {session.role === "instructor" && (
        <form className="inline-form" onSubmit={create}>
          <label>
            New course title
            <input value={newTitle} maxLength={200} required onChange={(e) => setNewTitle(e.target.value)} />
          </label>
          <button className="primary" type="submit">
            Create course
          </button>
        </form>
      )}
      {courses && courses.length === 0 && (
        <p className="empty">
          {session.role === "instructor" ? "No courses yet. Create the first one above." : "You have not joined a class yet. Ask your instructor for the class code and enter it above."}
        </p>
      )}
      {courses && courses.length > 6 && (
        <label className="search">
          <span className="visually-hidden">Find a course</span>
          <input type="search" placeholder="Find a course by title" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </label>
      )}
      {courses && courses.length > 0 && shown.length === 0 && <p className="empty">No course title matches.</p>}
      <ul className="rows">
        {shown.map((c) => (
          <li key={c.id} className="course-row" style={c.color ? { borderLeft: `6px solid ${c.color}` } : undefined}>
            <span className="grow">
              <strong>{c.title}</strong> {c.archived && <span className="flag">archived</span>}
              {(c.section || c.subject) && (
                <>
                  <br />
                  <small>{[c.section, c.subject].filter(Boolean).join(" · ")}</small>
                </>
              )}
            </span>
            {session.role === "student" && c.enrolled && <span className="state state-solved">Enrolled</span>}
            <a className="button" href={`#/course/${c.id}`}>
              Open
            </a>
          </li>
        ))}
      </ul>
    </>
  );
}
