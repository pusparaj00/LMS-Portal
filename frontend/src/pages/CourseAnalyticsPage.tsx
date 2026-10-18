import { useEffect, useState } from "react";

import { Session, api } from "../api";
import { DistributionChart, StatusChart } from "../design/Charts";
import { StatCard } from "../design/StatCard";
import { CourseAnalytics, CourseRatings, average, percent } from "./dashboardTypes";
import { ReviewList } from "./RatingsSection";

/** F-64, F-65: how one course is going: completion, score spread, each assignment, and what students say. */
export function CourseAnalyticsPage({ session, courseId }: { session: Session; courseId: number }) {
  const [data, setData] = useState<CourseAnalytics | null>(null);
  const [ratings, setRatings] = useState<CourseRatings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<CourseAnalytics>(`/courses/${courseId}/analytics`, session)
      .then(setData)
      .catch((e: Error) => setError(e.message));
    api<CourseRatings>(`/courses/${courseId}/ratings`, session)
      .then(setRatings)
      .catch(() => setRatings(null));
  }, [courseId]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!data) return <p className="empty">Loading analytics…</p>;

  return (
    <article className="dash-wide">
      <h1>{data.title}: analytics</h1>
      <p>
        <a href={`#/course/${courseId}`}>Back to the course</a> · <a href={`#/course/${courseId}/gradebook`}>Gradebook</a>{" "}
        · <a href={`#/class/${courseId}`}>Class heatmap</a>
      </p>
      <section className="stats" aria-label="Summary">
        <StatCard label="Students" value={data.students} />
        <StatCard label="Assignments" value={data.assignments} />
        <StatCard label="Completion" value={percent(data.completion_rate)} note="Finished student-assignment pairs" />
        <StatCard label="Average score" value={percent(data.average_percent)} />
        <StatCard label="Submissions" value={data.submissions_total} note={`${data.submissions_7d} in the last 7 days`} />
        <StatCard
          label="Course rating"
          value={data.ratings.average_course === null ? "—" : `${data.ratings.average_course.toFixed(1)} / 5`}
          note={
            data.ratings.count === 0
              ? "No ratings yet"
              : `Instructor ${average(data.ratings.average_instructor)} · ${data.ratings.count} ratings`
          }
        />
      </section>

      <div className="dash-cols">
        <section className="panel" aria-label="Score distribution">
          <p className="chart-caption">Students by total score</p>
          {data.students === 0 || data.assignments === 0 ? (
            <p className="empty">Scores appear once the course has students and assignments.</p>
          ) : (
            <>
              <DistributionChart data={data.distribution} />
              <table className="sr-only">
                <caption>Students by total score</caption>
                <tbody>
                  {data.distribution.map((b) => (
                    <tr key={b.label}>
                      <th>{b.label}</th>
                      <td>{b.students}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
        <section className="panel" aria-label="Assignment progress">
          <p className="chart-caption">Progress on each assignment</p>
          {data.per_assignment.length === 0 ? (
            <p className="empty">No assignments yet.</p>
          ) : (
            <>
              <StatusChart data={data.per_assignment} />
              <table className="sr-only">
                <caption>Progress on each assignment</caption>
                <tbody>
                  {data.per_assignment.map((a) => (
                    <tr key={a.assignment_id}>
                      <th>{a.title}</th>
                      <td>
                        {a.complete} complete, {a.in_progress} in progress, {a.late} late, {a.missing} missing,{" "}
                        {a.not_started} not started
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
      </div>

      <section className="panel" aria-label="Student reviews">
        <h2>What students say</h2>
        {ratings && <ReviewList reviews={ratings.reviews} />}
      </section>
    </article>
  );
}
