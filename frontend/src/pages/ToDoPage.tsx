import { useEffect, useState } from "react";

import { Session, api } from "../api";
import { points, when } from "./AssignmentsPage";

type Todo = {
  assignment_id: number;
  course_id: number;
  course_title: string;
  title: string;
  due_at: string;
  state: "assigned" | "missing" | "done";
  score: number;
  possible: number;
  has_work: boolean;
};

const TABS = [
  ["assigned", "Assigned"],
  ["missing", "Missing"],
  ["done", "Done"],
] as const;

const startOfWeek = (d: Date) => {
  const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  day.setDate(day.getDate() - ((day.getDay() + 6) % 7)); // weeks start on Monday
  return day;
};

/** Which group a due date falls in, by the viewer's own calendar. */
export function dueGroup(due: Date, now: Date): "Earlier" | "This week" | "Next week" | "Later" {
  const week = startOfWeek(now).getTime();
  const weekMs = 7 * 24 * 3600 * 1000;
  const startOfDue = new Date(due.getFullYear(), due.getMonth(), due.getDate()).getTime();
  if (due.getTime() < now.getTime()) return "Earlier";
  if (startOfDue < week + weekMs) return "This week";
  if (startOfDue < week + 2 * weekMs) return "Next week";
  return "Later";
}

const GROUPS = ["Earlier", "This week", "Next week", "Later"] as const;

export const itemHref = (courseId: number, assignmentId: number, hasWork: boolean) =>
  hasWork ? `#/course/${courseId}/assignment/${assignmentId}` : `#/course/${courseId}`;

/** F-78: what a student still has to do, in three tabs, grouped by when it is due. */
export function ToDoPage({ session }: { session: Session }) {
  const [items, setItems] = useState<Todo[] | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("assigned");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Todo[]>("/students/me/todo", session)
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, []);

  const now = new Date();
  const shown = (items ?? []).filter((i) => i.state === tab);
  const count = (state: string) => (items ?? []).filter((i) => i.state === state).length;

  return (
    <>
      <h1>To-do</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "primary" : undefined} onClick={() => setTab(key)}>
            {label} ({count(key)})
          </button>
        ))}
      </div>
      {items && shown.length === 0 && (
        <p className="empty">
          {tab === "assigned" ? "Nothing is waiting for you." : tab === "missing" ? "Nothing is missing." : "Nothing is done yet."}
        </p>
      )}
      {GROUPS.map((group) => {
        const rows = shown.filter((i) => dueGroup(new Date(i.due_at), now) === group);
        if (rows.length === 0) return null;
        return (
          <section key={group}>
            <h2>{group}</h2>
            <ul className="rows">
              {rows.map((i) => (
                <li key={`${i.course_id}-${i.assignment_id}`}>
                  <span className="grow">
                    <a href={itemHref(i.course_id, i.assignment_id, i.has_work)}>
                      <strong>{i.title}</strong>
                    </a>
                    <br />
                    <small>
                      {i.course_title} · due {when(i.due_at)}
                    </small>
                  </span>
                  {i.possible > 0 && (
                    <span>
                      {points(i.score)} / {points(i.possible)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </>
  );
}
