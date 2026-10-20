import { useEffect, useState } from "react";

import { Course, Session, api } from "../api";
import { itemHref } from "./ToDoPage";

type Entry = {
  assignment_id: number;
  course_id: number;
  course_title: string;
  title: string;
  due_at: string;
  state: "assigned" | "missing" | "done" | null;
  has_work: boolean;
};

const DAY = 24 * 3600 * 1000;
const NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const startOfWeek = (d: Date) => {
  const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  day.setDate(day.getDate() - ((day.getDay() + 6) % 7));
  return day;
};

/** F-79: due dates by month or by week, for one course or all of them. Weeks start on Monday. */
export function CalendarPage({ session }: { session: Session }) {
  const [view, setView] = useState<"month" | "week">("month");
  const [anchor, setAnchor] = useState(() => new Date());
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const first = view === "week" ? startOfWeek(anchor) : startOfWeek(new Date(anchor.getFullYear(), anchor.getMonth(), 1));
  const days = view === "week" ? 7 : 42;
  const cells = Array.from({ length: days }, (_, n) => new Date(first.getFullYear(), first.getMonth(), first.getDate() + n));
  const weeks = Array.from({ length: Math.ceil(days / 7) }, (_, w) => cells.slice(w * 7, w * 7 + 7));

  useEffect(() => {
    api<Course[]>("/courses", session)
      .then((all) => setCourses(all.filter((c) => !c.archived && (session.role === "instructor" || c.enrolled))))
      .catch(() => setCourses([]));
  }, []);

  useEffect(() => {
    const end = new Date(first.getTime() + days * DAY + DAY);
    const query = `start=${encodeURIComponent(first.toISOString())}&end=${encodeURIComponent(end.toISOString())}${courseId ? `&course_id=${courseId}` : ""}`;
    api<Entry[]>(`/calendar?${query}`, session)
      .then(setEntries)
      .catch((e: Error) => setError(e.message));
  }, [view, anchor, courseId]);

  const move = (direction: number) => {
    const next = new Date(anchor);
    if (view === "week") next.setDate(next.getDate() + 7 * direction);
    else next.setMonth(next.getMonth() + direction, 1);
    setAnchor(next);
  };
  const title = view === "week"
    ? `Week of ${first.toLocaleDateString([], { dateStyle: "medium" })}`
    : anchor.toLocaleDateString([], { month: "long", year: "numeric" });

  return (
    <>
      <h1>Calendar</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p className="actions">
        <button onClick={() => move(-1)} aria-label="Previous">
          ‹
        </button>
        <strong aria-live="polite">{title}</strong>
        <button onClick={() => move(1)} aria-label="Next">
          ›
        </button>
        <button onClick={() => setAnchor(new Date())}>Today</button>
        <button className={view === "month" ? "primary" : undefined} aria-pressed={view === "month"} onClick={() => setView("month")}>
          Month
        </button>
        <button className={view === "week" ? "primary" : undefined} aria-pressed={view === "week"} onClick={() => setView("week")}>
          Week
        </button>
        <label className="inline">
          Course
          <select value={courseId} onChange={(e) => setCourseId(e.target.value)}>
            <option value="">All courses</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </label>
      </p>
      <div className={`calendar calendar-${view}`} role="grid" aria-label={title}>
        <div role="row" className="calendar-row">
          {NAMES.map((n) => (
            <div key={n} className="calendar-head" role="columnheader">
              {n}
            </div>
          ))}
        </div>
        {weeks.map((week) => (
          <div key={week[0].toISOString()} role="row" className="calendar-row">
            {week.map((day) => {
              const due = entries.filter((e) => sameDay(new Date(e.due_at), day));
              const outside = view === "month" && day.getMonth() !== anchor.getMonth();
              return (
                <div key={day.toISOString()} role="gridcell" className={`calendar-cell${outside ? " outside" : ""}${sameDay(day, new Date()) ? " today" : ""}`}>
                  <span className="calendar-date">{day.getDate()}</span>
                  {due.map((e) => (
                    <a
                      key={`${e.course_id}-${e.assignment_id}`}
                      className={`calendar-item${e.state ? ` state-${e.state}` : ""}`}
                      href={session.role === "student" ? itemHref(e.course_id, e.assignment_id, e.has_work) : `#/course/${e.course_id}/assignments`}
                      title={`${e.title} (${e.course_title}), due ${new Date(e.due_at).toLocaleTimeString([], { timeStyle: "short" })}`}
                    >
                      {e.title}
                    </a>
                  ))}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </>
  );
}
