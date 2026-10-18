import { Course, Session } from "../api";
import { Me } from "./AccountPage";

/** The first page each role sees after signing in: a dashboard that links into the real views. */
export function RoleDashboard({ session, me, courses }: { session: Session; me: Me; courses: Course[] }) {
  const needsProfile = !me.academic_history && !me.interests;
  if (session.role === "admin") {
    return (
      <article className="narrow">
        <h1>Admin</h1>
        <p>
          <a href="#/admin">Open the admin dashboard</a>
        </p>
      </article>
    );
  }

  if (session.role === "instructor") {
    const mine = courses.filter((c) => c.instructor_id === me.id);
    return (
      <article className="narrow">
        <h1>Instructor dashboard</h1>
        {needsProfile && (
          <p className="notice">
            <a href="#/account">Complete your profile</a> — your students will see your name.
          </p>
        )}
        <p>
          <a className="primary" href="#/courses">Create or manage courses</a>
        </p>
        <section className="cards">
          <h2>Your courses ({mine.length})</h2>
          {mine.length === 0 ? (
            <p>You have no courses yet. <a href="#/courses">Create one</a>.</p>
          ) : (
            <ul>
              {mine.map((c) => (
                <li key={c.id}>
                  <a href={`#/course/${c.id}`}>{c.title}</a>{" "}
                  <a href={`#/class/${c.id}`}>class heatmap</a>{" "}
                  <a href={`#/course/${c.id}/gradebook`}>gradebook</a>
                </li>
              ))}
            </ul>
          )}
        </section>
      </article>
    );
  }

  const enrolled = courses.filter((c) => c.enrolled && !c.archived);
  return (
    <article className="narrow">
      <h1>Your dashboard</h1>
      {needsProfile && (
        <p className="notice">
          <a href="#/account">Complete your profile</a> so recommendations fit you.
        </p>
      )}
      <section className="cards">
        <h2>Your courses ({enrolled.length})</h2>
        {enrolled.length === 0 ? (
          <p>You are not enrolled in a course yet. <a href="#/courses">Browse courses</a>.</p>
        ) : (
          <ul>
            {enrolled.map((c) => (
              <li key={c.id}>
                <a href={`#/course/${c.id}`}>{c.title}</a>{" "}
                <a href={`#/placement/${c.id}`}>placement test</a>{" "}
                <a href={`#/mastery/${c.id}`}>your mastery</a>
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}
