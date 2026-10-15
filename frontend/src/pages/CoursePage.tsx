import { useEffect, useState } from "react";

import { Problem, Session, api } from "../api";

export function CoursePage({ session, courseId }: { session: Session; courseId: number }) {
  const [problems, setProblems] = useState<Problem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ problems: Problem[] }>(`/problems?course_id=${courseId}`, session)
      .then((r) => setProblems(r.problems))
      .catch((e: Error) => setError(e.message));
  }, [courseId]);

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
          {session.role === "instructor" && (
            <>
              <a className="button" href={`#/course/${courseId}/problem/new`}>
                Add a problem
              </a>
              <a className="button" href={`#/course/${courseId}/notes`}>
                Course notes
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
          </a>
        </p>
      )}
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
            {session.role !== "student" && p.review_status === "needs human review" && (
              <span className="flag">needs review</span>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
