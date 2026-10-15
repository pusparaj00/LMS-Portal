import { FormEvent, useEffect, useState } from "react";

import { ApiError, Course, Session, api } from "../api";

export function CoursesPage({ session }: { session: Session }) {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");

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

  async function enroll(id: number) {
    try {
      await api(`/courses/${id}/enroll`, session, { method: "POST" });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not enrol.");
    }
  }

  return (
    <>
      <h1>Courses</h1>
      {error && <p role="alert" className="error">{error}</p>}
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
          {session.role === "instructor" ? "No courses yet. Create the first one above." : "No courses yet. An instructor needs to create one."}
        </p>
      )}
      <ul className="rows">
        {courses?.map((c) => (
          <li key={c.id}>
            <span className="grow">{c.title}</span>
            {session.role === "student" && !c.enrolled ? (
              <button className="primary" onClick={() => enroll(c.id)}>
                Enrol
              </button>
            ) : (
              <a className="button" href={`#/course/${c.id}`}>
                Open
              </a>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
