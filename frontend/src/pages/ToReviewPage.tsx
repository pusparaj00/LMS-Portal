import { useEffect, useState } from "react";

import { Session, api } from "../api";
import { when } from "./AssignmentsPage";
import { ReviewGroup } from "./workTypes";

/** F-76: the instructor's grading queue across every course they teach. */
export function ToReviewPage({ session }: { session: Session }) {
  const [groups, setGroups] = useState<ReviewGroup[] | null>(null);
  const [tab, setTab] = useState<"review" | "reviewed">("review");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<ReviewGroup[]>("/instructor/to-review", session)
      .then(setGroups)
      .catch((e: Error) => setError(e.message));
  }, []);

  const shown = (groups ?? []).filter((g) => (tab === "review" ? g.waiting > 0 : g.graded > 0));
  const courses = [...new Set(shown.map((g) => g.course_id))];

  return (
    <>
      <h1>To review</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="tabs" role="tablist">
        {(["review", "reviewed"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "primary" : undefined} onClick={() => setTab(t)}>
            {t === "review" ? "To review" : "Reviewed"}
          </button>
        ))}
      </div>
      {groups && shown.length === 0 && (
        <p className="empty">{tab === "review" ? "Nothing is waiting for a score." : "No work has been scored yet."}</p>
      )}
      {courses.map((courseId) => (
        <section key={courseId}>
          <h2>{shown.find((g) => g.course_id === courseId)?.course_title}</h2>
          <ul className="rows">
            {shown
              .filter((g) => g.course_id === courseId)
              .map((g) => (
                <li key={g.assignment_id}>
                  <span className="grow">
                    <a href={`#/course/${g.course_id}/assignment/${g.assignment_id}/review`}>
                      <strong>{g.title}</strong>
                    </a>
                    <br />
                    <small>Due {when(g.due_at)}</small>
                  </span>
                  <span>
                    {tab === "review"
                      ? `${g.waiting} turned in`
                      : `${g.graded} scored${g.not_returned ? `, ${g.not_returned} not returned` : ""}`}
                  </span>
                </li>
              ))}
          </ul>
        </section>
      ))}
    </>
  );
}
