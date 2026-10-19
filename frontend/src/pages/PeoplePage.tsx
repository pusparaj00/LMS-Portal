import { FormEvent, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { when } from "./AssignmentsPage";
import { CourseTabs } from "./CourseTabs";

type Teacher = { user_id: number; label: string; owner: boolean };
type Classmate = { user_id: number; label: string; muted: boolean; joined_at: string };
type People = { teachers: Teacher[]; student_count: number; students: Classmate[] | null; can_manage_teachers: boolean };

/** F-82: who teaches the course and who is in it. A student sees the teachers and the number of classmates only. */
export function PeoplePage({ session, courseId }: { session: Session; courseId: number }) {
  const base = `/courses/${courseId}`;
  const [people, setPeople] = useState<People | null>(null);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<People>(`${base}/people`, session)
      .then(setPeople)
      .catch((e: Error) => setError(e.message));
  }, [courseId]);

  async function run(call: () => Promise<People | void>, failure: string) {
    setError(null);
    try {
      const next = await call();
      if (next) setPeople(next);
      else setPeople(await api<People>(`${base}/people`, session));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : failure);
    }
  }

  const addTeacher = (event: FormEvent) => {
    event.preventDefault();
    run(() => api<People>(`${base}/teachers`, session, { body: { email } }), "Could not add the teacher.").then(() => setEmail(""));
  };

  const staff = session.role !== "student";
  const isOwner = people?.can_manage_teachers ?? false;

  return (
    <>
      <h1>People</h1>
      <CourseTabs courseId={courseId} active="people" />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <section>
        <h2>Teachers</h2>
        <ul className="rows">
          {people?.teachers.map((t) => (
            <li key={t.user_id}>
              <span className="grow">
                {t.label} {t.owner && <small>(owner)</small>}
              </span>
              {session.role === "instructor" && isOwner && !t.owner && (
                <button className="link" onClick={() => run(() => api(`${base}/teachers/${t.user_id}`, session, { method: "DELETE" }), "Could not remove the teacher.")}>
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
        {session.role === "instructor" && isOwner && (
          <form className="inline-form" onSubmit={addTeacher}>
            <label>
              Add a co-teacher by email
              <input type="email" value={email} required placeholder="teacher@school.edu" onChange={(e) => setEmail(e.target.value)} />
            </label>
            <button type="submit">Add</button>
          </form>
        )}
      </section>
      <section>
        <h2>Students ({people?.student_count ?? 0})</h2>
        {!staff && <p>{people?.student_count ?? 0} students are in this class. Their names are not shown to other students.</p>}
        {people?.students && people.students.length === 0 && <p className="empty">Nobody has joined yet. Share the class code from the course page.</p>}
        <ul className="rows">
          {people?.students?.map((s) => (
            <li key={s.user_id}>
              <span className="grow">
                {s.label} <small>joined {when(s.joined_at)}</small> {s.muted && <span className="flag">comments off</span>}
              </span>
              <button
                onClick={() =>
                  run(() => api<People>(`${base}/students/${s.user_id}/mute`, session, { method: "PUT", body: { muted: !s.muted } }), "Could not change that.")
                }
              >
                {s.muted ? "Allow comments" : "Mute comments"}
              </button>
              {session.role === "instructor" && (
                <button
                  className="link"
                  onClick={() => {
                    if (window.confirm(`Remove ${s.label} from the course? Their work is kept.`))
                      run(() => api(`${base}/students/${s.user_id}`, session, { method: "DELETE" }), "Could not remove the student.");
                  }}
                >
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
