import { FormEvent, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { when } from "./AssignmentsPage";
import { CourseRatings, Rating, average } from "./dashboardTypes";

const STARS = [1, 2, 3, 4, 5];

/** Reviews are anonymous and shown as text, so nothing a student types can run. */
export function ReviewList({ reviews }: { reviews: Rating[] }) {
  if (reviews.length === 0) return <p className="empty">No written reviews yet.</p>;
  return (
    <div>
      {reviews.map((r) => (
        <div key={r.created_at + r.review} className="review">
          <span className="muted">
            Course {r.course_rating}/5 · Instructor {r.instructor_rating}/5 · {when(r.created_at)}
          </span>
          <p>{r.review}</p>
        </div>
      ))}
    </div>
  );
}

/** F-65: an enrolled student rates the course and its instructor; saving again replaces the rating. */
export function RatingsSection({ session, courseId }: { session: Session; courseId: number }) {
  const [data, setData] = useState<CourseRatings | null>(null);
  const [course, setCourse] = useState(5);
  const [instructor, setInstructor] = useState(5);
  const [review, setReview] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const show = (next: CourseRatings) => {
    setData(next);
    if (next.mine) {
      setCourse(next.mine.course_rating);
      setInstructor(next.mine.instructor_rating);
      setReview(next.mine.review ?? "");
    }
  };

  useEffect(() => {
    api<CourseRatings>(`/courses/${courseId}/ratings`, session)
      .then(show)
      .catch((e: Error) => setError(e.message));
  }, [courseId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      show(
        await api<CourseRatings>(`/courses/${courseId}/ratings`, session, {
          method: "PUT",
          body: { course_rating: course, instructor_rating: instructor, review: review.trim() || null },
        }),
      );
      setMessage("Your rating is saved.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Your rating could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const options = STARS.map((n) => (
    <option key={n} value={n}>
      {n} of 5
    </option>
  ));

  return (
    <section className="panel" aria-label="Rate this course">
      <h2>Rate this course</h2>
      {data && (
        <p className="muted">
          Course {average(data.summary.average_course)} · Instructor {average(data.summary.average_instructor)} (
          {data.summary.count} {data.summary.count === 1 ? "rating" : "ratings"})
        </p>
      )}
      <form className="rating-form" onSubmit={save}>
        <label>
          The course
          <select value={course} onChange={(e) => setCourse(Number(e.target.value))}>
            {options}
          </select>
        </label>
        <label>
          The instructor
          <select value={instructor} onChange={(e) => setInstructor(Number(e.target.value))}>
            {options}
          </select>
        </label>
        <label>
          Review (optional, shown without your name)
          <textarea value={review} maxLength={1000} rows={3} onChange={(e) => setReview(e.target.value)} />
        </label>
        <div>
          <button className="primary" disabled={busy}>
            {data?.mine ? "Update my rating" : "Save my rating"}
          </button>
        </div>
      </form>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {data && data.reviews.length > 0 && (
        <>
          <h3>What other students say</h3>
          <ReviewList reviews={data.reviews} />
        </>
      )}
    </section>
  );
}
