import { useEffect, useState } from "react";

import { Session, api } from "../api";
import { StatCard } from "../design/StatCard";
import { when } from "./AssignmentsPage";
import { InstructorStats, average, percent } from "./dashboardTypes";

/** F-64: the instructor's courses at a glance, the next assignments and where to look closer. */
export function InstructorDashboard({ session, needsProfile }: { session: Session; needsProfile: boolean }) {
  const [stats, setStats] = useState<InstructorStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<InstructorStats>("/instructor/stats", session)
      .then(setStats)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <article className="dash-wide">
      <h1>Instructor dashboard</h1>
      {needsProfile && (
        <p className="notice">
          <a href="#/account">Complete your profile</a> — your students will see your name.
        </p>
      )}
      <p>
        <a className="button primary" href="#/courses">
          Create or manage courses
        </a>
      </p>
      {error && <p role="alert" className="error">{error}</p>}
      {!stats && !error && <p className="empty">Loading your figures…</p>}
      {stats && (
        <>
          <section className="stats" aria-label="Summary">
            <StatCard label="Courses" value={stats.courses} />
            <StatCard label="Students" value={stats.students} note="Enrolled in your courses" />
            <StatCard label="Upcoming assignments" value={stats.upcoming_assignments} />
            <StatCard label="Submissions" value={stats.submissions_7d} note="In the last 7 days" />
          </section>

          <h2>Your courses ({stats.course_stats.length})</h2>
          {stats.course_stats.length === 0 ? (
            <p className="empty">
              You have no courses yet. <a href="#/courses">Create one</a>.
            </p>
          ) : (
            <ul className="course-cards">
              {stats.course_stats.map((c) => (
                <li key={c.course_id} className="course-card">
                  <h3>{c.title}</h3>
                  <p className="meta">
                    {c.students} {c.students === 1 ? "student" : "students"} · {c.assignments}{" "}
                    {c.assignments === 1 ? "assignment" : "assignments"} · {c.submissions_7d} submissions this week
                  </p>
                  <p className="meta">
                    Completion: {percent(c.completion_rate)} · Rating: {average(c.average_course_rating)}
                    {c.rating_count > 0 && ` (${c.rating_count})`}
                  </p>
                  <div className="links">
                    <a href={`#/course/${c.course_id}`}>Problems</a>
                    <a href={`#/course/${c.course_id}/analytics`}>Analytics</a>
                    <a href={`#/class/${c.course_id}`}>Class heatmap</a>
                    <a href={`#/course/${c.course_id}/gradebook`}>Gradebook</a>
                    <a href={`#/course/${c.course_id}/assignments`}>Assignments</a>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <section className="panel" aria-label="Upcoming assignments">
            <h2>Upcoming assignments</h2>
            {stats.upcoming.length === 0 ? (
              <p className="empty">Nothing is due soon.</p>
            ) : (
              <ul className="due-list">
                {stats.upcoming.map((a) => (
                  <li key={a.assignment_id}>
                    <span>
                      <a href={`#/course/${a.course_id}/assignments`}>{a.title}</a>
                      <span className="sub">{a.course_title}</span>
                    </span>
                    <span>
                      {when(a.due_at)}
                      <span className="sub">
                        {a.students_complete} of {a.students} students complete
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </article>
  );
}
