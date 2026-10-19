import { useEffect, useState } from "react";

import { Session, api } from "../api";
import { itemHref } from "./ToDoPage";
import { when } from "./AssignmentsPage";

export type CourseTab = "stream" | "classwork" | "people";

const TABS: [CourseTab, string, (id: number) => string][] = [
  ["stream", "Stream", (id) => `#/course/${id}`],
  ["classwork", "Classwork", (id) => `#/course/${id}/classwork`],
  ["people", "People", (id) => `#/course/${id}/people`],
];

/** F-84: the three parts of a course, on every course page. */
export function CourseTabs({ courseId, active }: { courseId: number; active: CourseTab }) {
  return (
    <nav className="course-tabs" aria-label="Course sections">
      {TABS.map(([key, label, href]) => (
        <a key={key} href={href(courseId)} aria-current={key === active ? "page" : undefined}>
          {label}
        </a>
      ))}
    </nav>
  );
}

type Todo = { assignment_id: number; course_id: number; title: string; due_at: string; state: string; has_work: boolean };

/** F-84: the next things due in this course, from the student's own to-do list. */
export function UpcomingBox({ session, courseId }: { session: Session; courseId: number }) {
  const [items, setItems] = useState<Todo[] | null>(null);
  useEffect(() => {
    api<Todo[]>("/students/me/todo", session)
      .then((all) => setItems(all.filter((t) => t.course_id === courseId && t.state !== "done")))
      .catch(() => setItems([]));
  }, [courseId]);
  if (!items) return null;
  const next = items.filter((t) => t.state === "assigned").slice(0, 3);
  const missing = items.filter((t) => t.state === "missing").length;
  return (
    <section className="upcoming" aria-label="Upcoming">
      <h2>Upcoming</h2>
      {next.length === 0 && <p className="empty">Nothing is due soon.</p>}
      <ul className="rows">
        {next.map((t) => (
          <li key={t.assignment_id}>
            <span className="grow">
              <a href={itemHref(t.course_id, t.assignment_id, t.has_work)}>{t.title}</a>
              <br />
              <small>Due {when(t.due_at)}</small>
            </span>
          </li>
        ))}
      </ul>
      {missing > 0 && (
        <small>
          {missing} missing. <a href="#/todo">See your to-do list</a>.
        </small>
      )}
    </section>
  );
}
