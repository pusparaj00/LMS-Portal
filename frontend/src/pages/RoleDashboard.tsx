import { Course, Session } from "../api";
import { Me } from "./AccountPage";
import { InstructorDashboard } from "./InstructorDashboard";
import { StudentDashboard } from "./StudentDashboard";

/** The first page each role sees after signing in: figures from their own data, linking into the real views. */
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
  if (session.role === "instructor") return <InstructorDashboard session={session} needsProfile={needsProfile} />;
  return <StudentDashboard session={session} needsProfile={needsProfile} courses={courses} />;
}
