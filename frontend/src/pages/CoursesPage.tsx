import { useEffect, useState } from "react";

import { ApiError, Course, Session, api } from "../api";

export function CoursesPage({ session }: { session: Session }) {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api<Course[]>("/courses", session)
      .then(setCourses)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

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
      {courses && courses.length === 0 && (
        <p className="empty">No courses yet. An instructor needs to create one.</p>
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
