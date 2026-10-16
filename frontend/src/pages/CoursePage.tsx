import { useEffect, useState } from "react";

import { ApiError, Problem, Session, api } from "../api";
import { Announcements } from "./Announcements";
import { StudentAssignments } from "./AssignmentsPage";
import { CourseSettings } from "./CourseSettings";

export function CoursePage({ session, courseId }: { session: Session; courseId: number }) {
  const [problems, setProblems] = useState<Problem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api<{ problems: Problem[] }>(`/problems?course_id=${courseId}`, session)
      .then((r) => setProblems(r.problems))
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, [courseId]);

  async function act(path: string, method = "POST") {
    setError(null);
    try {
      await api(path, session, { method });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The change could not be saved.");
    }
  }

  async function leave() {
    if (!window.confirm("Leave this course? Your work is kept, and you can enrol again later.")) return;
    try {
      await api(`/courses/${courseId}/enroll`, session, { method: "DELETE" });
      window.location.hash = "#/courses";
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not leave the course.");
    }
  }

  const coding = problems?.filter((p) => p.kind === "code") ?? [];

  return (
    <>
      <p>
        <a href="#/courses">All courses</a>
      </p>
      <h1>Problems</h1>
      {session.role !== "student" && (
        <p className="actions">
          <a className="button" href={`#/class/${courseId}`}>
            Class overview
          </a>
          <a className="button" href={`#/course/${courseId}/gradebook`}>
            Gradebook
          </a>
          {session.role === "instructor" && (
            <>
              <a className="button" href={`#/course/${courseId}/problem/new`}>
                Add a problem
              </a>
              <a className="button" href={`#/course/${courseId}/notes`}>
                Course notes
              </a>
              <a className="button" href={`#/course/${courseId}/assignments`}>
                Assignments
              </a>
            </>
          )}
        </p>
      )}
      {session.role === "student" && (
        <p>
          <a className="button" href={`#/placement/${courseId}`}>
            Placement test
          </a>{" "}
          <a className="button" href={`#/mastery/${courseId}`}>
            My mastery
          </a>{" "}
          <button className="link" onClick={leave}>
            Leave course
          </button>
        </p>
      )}
      {session.role === "instructor" && <CourseSettings session={session} courseId={courseId} />}
      <Announcements session={session} courseId={courseId} />
      {session.role === "student" && <StudentAssignments session={session} courseId={courseId} />}
      {error && <p role="alert" className="error">{error}</p>}
      {problems && coding.length === 0 && (
        <p className="empty">This course has no coding problems yet.</p>
      )}
      <ul className="rows">
        {coding.map((p) => (
          <li key={p.id}>
            <a className="grow" href={`#/problem/${p.id}`}>
              {p.title}
            </a>
            <span className="tags">
              {p.concepts.map((c) => (
                <span key={c.concept_id} className="tag">
                  {c.name}
                </span>
              ))}
            </span>
            {p.archived && <span className="flag">archived</span>}
            {session.role !== "student" && !p.archived && p.review_status === "needs human review" && (
              <span className="flag">needs review</span>
            )}
            {session.role === "instructor" && (
              <span className="row-actions">
                <a href={`#/course/${courseId}/problem/${p.id}/edit`} aria-label={`Edit ${p.title}`}>
                  Edit
                </a>
                {p.review_status === "needs human review" && !p.archived && (
                  <button className="link" onClick={() => act(`/problems/${p.id}/review`)} aria-label={`Mark ${p.title} reviewed`}>
                    Mark reviewed
                  </button>
                )}
                {p.archived ? (
                  <button className="link" onClick={() => act(`/problems/${p.id}/restore`)} aria-label={`Restore ${p.title}`}>
                    Restore
                  </button>
                ) : (
                  <button
                    className="link"
                    aria-label={`Archive ${p.title}`}
                    onClick={() => {
                      if (window.confirm(`Archive "${p.title}"? Students stop seeing it; their work and grades are kept.`))
                        act(`/problems/${p.id}/archive`);
                    }}
                  >
                    Archive
                  </button>
                )}
              </span>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
