import { useEffect, useState } from "react";

import { ApiError, Course, Problem, Session, api } from "../api";
import { Dashboard } from "../types";
import { Announcements } from "./Announcements";
import { StudentAssignments } from "./AssignmentsPage";
import { CourseTabs, UpcomingBox } from "./CourseTabs";
import { StudentQuizzes } from "./QuizPage";
import { CourseContent } from "./CourseContent";
import { CourseSettings } from "./CourseSettings";
import { RatingsSection } from "./RatingsSection";

const pretty = (name: string) => name.replace(/_/g, " ");
const sentence = (name: string) => pretty(name).charAt(0).toUpperCase() + pretty(name).slice(1);
const STATUS_LABEL = { solved: "Solved", tried: "In progress", new: "Not started" } as const;

/** F-60: where a student stands in the course and what to do next, before the list of problems. */
function StudentHome({ session, courseId, problems }: { session: Session; courseId: number; problems: Problem[] }) {
  const [data, setData] = useState<Dashboard | null>(null);

  useEffect(() => {
    api<Dashboard>(`/students/me/mastery?course_id=${courseId}`, session)
      .then(setData)
      .catch(() => setData(null));
  }, [courseId]);

  const solved = problems.filter((p) => p.my_status === "solved").length;
  const weakest = data ? [...data.concepts].sort((a, b) => a.p_known - b.p_known).slice(0, 3) : [];

  return (
    <section className="home-grid" aria-label="Your progress">
      <div className="panel continue">
        <p className="eyebrow">Continue</p>
        {data && data.placement_available && !data.placement_completed ? (
          <>
            <h2>Start with the placement test</h2>
            <p>About 16 to 20 questions (10 to 20 minutes) show which concepts you already know, so the next problems fit you.</p>
            <a className="button primary" href={`#/placement/${courseId}`}>
              Take the placement test
            </a>
          </>
        ) : data?.recommended ? (
          <>
            <h2>{data.recommended.title}</h2>
            <p>{data.recommended.reason}</p>
            <a className="button primary" href={`#/problem/${data.recommended.problem_id}`}>
              Open this problem
            </a>
          </>
        ) : (
          <>
            <h2>Pick any problem below</h2>
            <p>There is no recommendation yet.</p>
          </>
        )}
      </div>
      <div className="panel">
        <p className="eyebrow">Progress</p>
        <p className="big-number">
          {solved}
          <span> of {problems.length} solved</span>
        </p>
        <div className="meter" role="img" aria-label={`${solved} of ${problems.length} problems solved`}>
          <span style={{ width: `${problems.length ? (solved / problems.length) * 100 : 0}%` }} />
        </div>
        {weakest.length > 0 && (
          <>
            <p className="eyebrow">Weakest concepts</p>
            <ul className="mini-bars">
              {weakest.map((c) => (
                <li key={c.concept_id}>
                  <span>{sentence(c.name)}</span>
                  <span className="value">{Math.round(c.p_known * 100)}%</span>
                </li>
              ))}
            </ul>
          </>
        )}
        <a href={`#/mastery/${courseId}`}>See all my progress</a>
      </div>
    </section>
  );
}

/** Problems grouped under their main concept (the one with the highest weight). */
function groupByConcept(problems: Problem[]): [string, Problem[]][] {
  const groups = new Map<string, Problem[]>();
  for (const p of problems) {
    const main = [...p.concepts].sort((a, b) => b.weight - a.weight)[0];
    const key = main ? sentence(main.name) : "Other";
    groups.set(key, [...(groups.get(key) ?? []), p]);
  }
  return [...groups];
}

export function CoursePage({
  session,
  courseId,
  title,
  details,
  tab,
}: {
  session: Session;
  courseId: number;
  title?: string;
  details?: Course;
  tab: "stream" | "classwork";
}) {
  const [problems, setProblems] = useState<Problem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api<{ problems: Problem[] }>(`/problems?course_id=${courseId}`, session)
      .then((r) => setProblems(r.problems))
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, [courseId]);

  async function act(path: string, method = "POST") {
    setError(null);
    try {
      await api(path, session, { method });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The change could not be saved.");
    }
  }

  async function leave() {
    if (!window.confirm("Leave this course? Your work is kept, and you can enrol again later.")) return;
    try {
      await api(`/courses/${courseId}/enroll`, session, { method: "DELETE" });
      window.location.hash = "#/courses";
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not leave the course.");
    }
  }

  const coding = problems?.filter((p) => p.kind === "code") ?? [];
  const student = session.role === "student";

  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow">
            {[details?.section, details?.subject].filter(Boolean).join(" · ") || (student ? "Course" : "Course problems")}
          </p>
          <h1 style={details?.color ? { borderLeft: `6px solid ${details.color}`, paddingLeft: "0.6rem" } : undefined}>
            {title ?? "Course"}
          </h1>
        </div>
        {session.role === "instructor" && (
          <a className="button primary" href={`#/course/${courseId}/problem/new`}>
            Add a problem
          </a>
        )}
      </div>
      <CourseTabs courseId={courseId} active={tab} />
      {error && <p role="alert" className="error">{error}</p>}
      {tab === "stream" && (
        <>
          {session.role === "instructor" && <CourseSettings session={session} courseId={courseId} />}
          {student && <UpcomingBox session={session} courseId={courseId} />}
          <Announcements session={session} courseId={courseId} />
          {student && problems && <StudentHome session={session} courseId={courseId} problems={coding} />}
          {student && <RatingsSection session={session} courseId={courseId} />}
        </>
      )}
      {tab === "classwork" && (
        <>
          {session.role === "instructor" && (
            <p className="actions">
              <a className="button" href={`#/course/${courseId}/content`}>
                Lessons
              </a>
              <a className="button" href={`#/course/${courseId}/assignments`}>
                Assignments
              </a>
              <a className="button" href={`#/course/${courseId}/quizzes`}>
                Quizzes
              </a>
              <a className="button" href={`#/course/${courseId}/notes`}>
                Course notes
              </a>
            </p>
          )}
          {student && <StudentAssignments session={session} courseId={courseId} />}
          {student && <StudentQuizzes session={session} courseId={courseId} />}
          <CourseContent session={session} courseId={courseId} />
          {problems === null && !error && <p className="empty">Loading problems…</p>}
          {problems && coding.length === 0 && <p className="empty">This course has no coding problems yet.</p>}
        </>
      )}

      {tab === "classwork" && (student ? (
        groupByConcept(coding).map(([concept, items]) => (
          <section key={concept} className="group">
            <h2>{concept}</h2>
            <ul className="rows">
              {items.map((p) => (
                <li key={p.id}>
                  <a className="grow" href={`#/problem/${p.id}`}>
                    {p.title}
                  </a>
                  <span className="tags">
                    {p.concepts.slice(1).map((c) => (
                      <span key={c.concept_id} className="tag">
                        {pretty(c.name)}
                      </span>
                    ))}
                  </span>
                  {p.my_status && <span className={`state state-${p.my_status}`}>{STATUS_LABEL[p.my_status]}</span>}
                </li>
              ))}
            </ul>
          </section>
        ))
      ) : (
        <ul className="rows">
          {coding.map((p) => (
            <li key={p.id}>
              <a className="grow" href={`#/problem/${p.id}`}>
                {p.title}
              </a>
              <span className="tags">
                {p.concepts.map((c) => (
                  <span key={c.concept_id} className="tag">
                    {pretty(c.name)}
                  </span>
                ))}
              </span>
              {p.archived && <span className="flag">archived</span>}
              {!p.archived && p.review_status === "needs human review" && <span className="flag">needs review</span>}
              {session.role === "instructor" && (
                <span className="row-actions">
                  <a href={`#/course/${courseId}/problem/${p.id}/edit`} aria-label={`Edit ${p.title}`}>
                    Edit
                  </a>
                  {p.review_status === "needs human review" && !p.archived && (
                    <button className="link" onClick={() => act(`/problems/${p.id}/review`)} aria-label={`Mark ${p.title} reviewed`}>
                      Mark reviewed
                    </button>
                  )}
                  {p.archived ? (
                    <button className="link" onClick={() => act(`/problems/${p.id}/restore`)} aria-label={`Restore ${p.title}`}>
                      Restore
                    </button>
                  ) : (
                    <button
                      className="link"
                      aria-label={`Archive ${p.title}`}
                      onClick={() => {
                        if (window.confirm(`Archive "${p.title}"? Students stop seeing it; their work and grades are kept.`))
                          act(`/problems/${p.id}/archive`);
                      }}
                    >
                      Archive
                    </button>
                  )}
                </span>
              )}
            </li>
          ))}
        </ul>
      ))}
      {tab === "stream" && student && (
        <p className="quiet-actions">
          <button className="link" onClick={leave}>
            Leave this course
          </button>
        </p>
      )}
    </>
  );
}
