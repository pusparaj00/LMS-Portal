import { useEffect, useState } from "react";

import { Course, Session, api } from "../api";
import { StatCard } from "../design/StatCard";
import { Dashboard } from "../types";
import { MasteryBars } from "./MasteryBars";
import { STATUS_TEXT, when } from "./AssignmentsPage";
import { StudentStats, percent } from "./dashboardTypes";

type Notice = { id: number; course_id: number; course_title: string; title: string; body: string; created_at: string };
type Announcement = Omit<Notice, "course_title">;

const NOTICES_SHOWN = 4;
const WEAKEST_SHOWN = 3;

/** F-63, F-60: progress, the next work, the weakest concepts and the latest announcements, all from the student's own data. */
export function StudentDashboard({
  session,
  needsProfile,
  courses,
}: {
  session: Session;
  needsProfile: boolean;
  courses: Course[];
}) {
  const [stats, setStats] = useState<StudentStats | null>(null);
  const [mastery, setMastery] = useState<Record<number, Dashboard>>({});
  const [notices, setNotices] = useState<Notice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const enrolled = courses.filter((c) => c.enrolled && !c.archived);
  const key = enrolled.map((c) => c.id).join(",");

  useEffect(() => {
    api<StudentStats>("/students/me/stats", session)
      .then(setStats)
      .catch((e: Error) => setError(e.message));
  }, [key]);

  useEffect(() => {
    let current = true;
    Promise.all(
      enrolled.map(async (c) => ({
        course: c,
        dashboard: await api<Dashboard>(`/students/me/mastery?course_id=${c.id}`, session).catch(() => null),
        announcements: await api<Announcement[]>(`/courses/${c.id}/announcements`, session).catch(() => []),
      })),
    ).then((results) => {
      if (!current) return;
      setMastery(Object.fromEntries(results.flatMap((r) => (r.dashboard ? [[r.course.id, r.dashboard]] : []))));
      setNotices(
        results
          .flatMap((r) => r.announcements.map((a) => ({ ...a, course_title: r.course.title })))
          .sort((a, b) => b.created_at.localeCompare(a.created_at))
          .slice(0, NOTICES_SHOWN),
      );
    });
    return () => {
      current = false;
    };
  }, [key]);

  const nextDue = stats?.upcoming[0];

  return (
    <article className="dash-wide">
      <h1>Your dashboard</h1>
      {needsProfile && (
        <p className="notice">
          <a href="#/account">Complete your profile</a> so recommendations fit you.
        </p>
      )}
      {error && <p role="alert" className="error">{error}</p>}
      {!stats && !error && <p className="empty">Loading your figures…</p>}
      {stats && (
        <>
          <section className="stats" aria-label="Summary">
            <StatCard label="Courses" value={stats.enrolled_courses} note="You are enrolled in" />
            <StatCard label="Average score" value={percent(stats.average_percent)} note="Across your assignments" />
            <StatCard
              label="Assignments done"
              value={`${stats.assignments_complete} of ${stats.assignments_total}`}
              note={<a href="#/grades">See all grades</a>}
            />
            <StatCard
              label="Next due"
              value={nextDue ? new Date(nextDue.due_at).toLocaleDateString([], { dateStyle: "medium" }) : "Nothing due"}
              note={nextDue && `${nextDue.title} · ${nextDue.course_title}`}
            />
          </section>

          <h2>Your courses ({stats.courses.length})</h2>
          {stats.courses.length === 0 ? (
            <p className="empty">
              You have not joined a class yet. <a href="#/courses">Join one with a class code</a>.
            </p>
          ) : (
            <ul className="course-cards">
              {stats.courses.map((c) => {
                const weakest = [...(mastery[c.course_id]?.concepts ?? [])]
                  .sort((a, b) => a.p_known - b.p_known)
                  .slice(0, WEAKEST_SHOWN);
                const placed = mastery[c.course_id]?.placement_available ? mastery[c.course_id]?.placement_completed : undefined;
                return (
                  <li key={c.course_id} className="course-card">
                    <h3>{c.title}</h3>
                    <p className="meta">
                      {c.completed} of {c.assignments} assignments complete · Score: {percent(c.percent)}
                    </p>
                    <div
                      className="meter"
                      role="img"
                      aria-label={`${c.completed} of ${c.assignments} assignments complete`}
                    >
                      <span style={{ width: `${c.assignments ? (c.completed / c.assignments) * 100 : 0}%` }} />
                    </div>
                    {c.content_total > 0 && (
                      <p className="meta">
                        Lessons: {c.content_done} of {c.content_total} items done
                      </p>
                    )}
                    {weakest.length > 0 && (
                      <>
                        <p className="eyebrow">Weakest concepts</p>
                        <MasteryBars concepts={weakest} courseId={c.course_id} />
                      </>
                    )}
                    <div className="links">
                      <a href={`#/course/${c.course_id}`}>Course home</a>
                      {placed === false && <a href={`#/placement/${c.course_id}`}>Placement test</a>}
                      <a href={`#/mastery/${c.course_id}`}>My progress</a>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="dash-cols">
            <section className="panel" aria-label="Upcoming assignments">
              <h2>Upcoming assignments</h2>
              {stats.upcoming.length === 0 ? (
                <p className="empty">Nothing is waiting for you.</p>
              ) : (
                <ul className="due-list">
                  {stats.upcoming.map((a) => (
                    <li key={a.assignment_id}>
                      <span>
                        <a href={`#/course/${a.course_id}`}>{a.title}</a>
                        <span className="sub">{a.course_title}</span>
                      </span>
                      <span>
                        {when(a.due_at)}
                        <span className="sub">{a.status ? STATUS_TEXT[a.status] : ""}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="panel" aria-label="Announcements">
              <h2>Latest announcements</h2>
              {notices.length === 0 ? (
                <p className="empty">No announcements yet.</p>
              ) : (
                <ul className="due-list">
                  {notices.map((n) => (
                    <li key={`${n.course_id}-${n.id}`}>
                      <span>
                        <a href={`#/course/${n.course_id}`}>{n.title}</a>
                        <span className="sub">{n.course_title}</span>
                      </span>
                      <span className="sub">{when(n.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
    </article>
  );
}
