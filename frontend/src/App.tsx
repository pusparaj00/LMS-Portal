import { useEffect, useState } from "react";

import { ApiError, Course, Session, api, loadSession, saveSession } from "./api";
import { AccountPage, Me } from "./pages/AccountPage";
import { AdminPage } from "./pages/AdminPage";
import { AssignmentsPage } from "./pages/AssignmentsPage";
import { ChatPanel } from "./pages/ChatPanel";
import { CoursePage } from "./pages/CoursePage";
import { CoursesPage } from "./pages/CoursesPage";
import { DashboardPage, WhyPage } from "./pages/DashboardPage";
import { GradebookPage } from "./pages/GradebookPage";
import { NewProblemPage } from "./pages/NewProblemPage";
import { Nav } from "./pages/Nav";
import { NotesPage } from "./pages/NotesPage";
import { InstructorPage } from "./pages/InstructorPage";
import { LtiLanding } from "./pages/LtiLanding";
import { LoginPage } from "./pages/LoginPage";
import { PlacementPage } from "./pages/PlacementPage";
import { StudentWorkPage, SubmissionView } from "./pages/StudentWorkPage";
import { ErasureBanner, ErasureState } from "./pages/ErasureSection";
import { ConsentState, PrivacyPage } from "./pages/PrivacyPage";
import { ProblemPage } from "./pages/ProblemPage";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => {
      setHash(window.location.hash);
      // a hash change keeps the old scroll position, so a new page would open part-way down
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

export function App() {
  const [session, setSession] = useState<Session | null>(loadSession);
  const [consent, setConsent] = useState<ConsentState | null>(null);
  const [consentError, setConsentError] = useState<string | null>(null);
  const [erasure, setErasure] = useState<ErasureState | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [lastCourse, setLastCourse] = useState<number | null>(null);
  const hash = useHash();
  // The course menu stays on screen while a problem of that course is open, since a problem's address has no course id.
  const hashCourse = hash.match(/^#\/(?:course|class|mastery|placement)\/(\d+)/);
  useEffect(() => {
    if (hashCourse) setLastCourse(Number(hashCourse[1]));
    else if (!hash.startsWith("#/problem/")) setLastCourse(null);
  }, [hash]);

  const update = (next: Session | null) => {
    saveSession(next);
    setSession(next);
    setConsent(null);
    setErasure(null);
    setMe(null);
    window.location.hash = !next ? "#/login" : next.role === "admin" ? "#/admin" : "#/courses";
  };

  // Who is signed in, and whether they must choose a new password before anything else (F-01).
  useEffect(() => {
    if (!session) return;
    api<Me>("/me", session)
      .then(setMe)
      .catch((e) => {
        // a session that ended (password changed elsewhere, account disabled) goes back to the login page
        if (e instanceof ApiError && e.status === 401) update(null);
      });
  }, [session?.token]);

  // After a password change the new token replaces the old one without leaving the page.
  const replaceToken = (next: Session) => {
    saveSession(next);
    setSession(next);
  };

  // A student's data is only processed after they agree to the privacy notice (TR-S-05).
  useEffect(() => {
    if (session?.role !== "student" || !me || me.must_change_password) return;
    setConsentError(null);
    api<ConsentState>("/consent", session)
      .then(setConsent)
      .catch((e: Error) => setConsentError(e.message));
    api<ErasureState>("/me/erasure", session)
      .then(setErasure)
      .catch(() => setErasure(null));
  }, [session?.token, me?.must_change_password]);

  useEffect(() => {
    if (!session || !me || me.must_change_password) return;
    api<Course[]>("/courses", session)
      .then(setCourses)
      .catch(() => setCourses([]));
  }, [session?.token, me?.must_change_password, lastCourse]);

  const ltiCode = hash.match(/^#\/lti\/([\w-]+)$/);
  if (ltiCode)
    return (
      <LtiLanding
        code={ltiCode[1]}
        onSession={(next, courseId) => {
          update(next);
          window.location.hash = `#/course/${courseId}`;
        }}
      />
    );
  if (!session) return <LoginPage onSession={update} />;
  if (!me) return <p>Loading…</p>;
  if (me.must_change_password)
    return (
      <main>
        <AccountPage session={session} me={me} onMe={setMe} onSession={replaceToken} />
        <p className="narrow">
          <button className="link" onClick={() => update(null)}>
            Log out
          </button>
        </p>
      </main>
    );
  const waitingForConsent = session.role === "student" && consent === null;
  const mustAgree = session.role === "student" && consent !== null && !consent.accepted;

  const course = hash.match(/^#\/course\/(\d+)$/);
  const newProblem = hash.match(/^#\/course\/(\d+)\/problem\/new$/);
  const editProblem = hash.match(/^#\/course\/(\d+)\/problem\/(\d+)\/edit$/);
  const notes = hash.match(/^#\/course\/(\d+)\/notes$/);
  const assignments = hash.match(/^#\/course\/(\d+)\/assignments$/);
  const gradebook = hash.match(/^#\/course\/(\d+)\/gradebook$/);
  const problem = hash.match(/^#\/problem\/(\d+)$/);
  const classView = hash.match(/^#\/class\/(\d+)$/);
  const studentWork = hash.match(/^#\/class\/(\d+)\/student\/(\d+)$/);
  const studentSubmission = hash.match(/^#\/class\/(\d+)\/student\/(\d+)\/submission\/(\d+)$/);
  const studentConcept = hash.match(/^#\/class\/(\d+)\/student\/(\d+)\/concept\/(\d+)$/);
  const placement = hash.match(/^#\/placement\/(\d+)$/);
  const mastery = hash.match(/^#\/mastery\/(\d+)$/);
  const why = hash.match(/^#\/mastery\/(\d+)\/concept\/(\d+)$/);

  return (
    <>
      <a
        className="skip"
        href="#content"
        onClick={(e) => {
          // the app routes on the hash, so focus the content instead of navigating to "#content"
          e.preventDefault();
          document.getElementById("content")?.focus();
        }}
      >
        Skip to content
      </a>
      <header className="bar">
        <a className="brand" href={session.role === "admin" ? "#/admin" : "#/courses"}>
          Adaptive LMS
        </a>
        <span className="who">
          <span className="who-name">{me.display_name ?? me.email}</span>
          <span className={`role role-${session.role}`}>{session.role}</span>
        </span>
        <button className="ghost" onClick={() => update(null)}>
          Log out
        </button>
      </header>
      {erasure && <ErasureBanner state={erasure} />}
      <div className="shell">
        {!mustAgree && !waitingForConsent && (
          <Nav
            role={session.role}
            courseId={lastCourse}
            courseTitle={courses.find((c) => c.id === lastCourse)?.title}
            hash={hash}
          />
        )}
        <main id="content" tabIndex={-1}>
          {consentError ? (
            <p role="alert" className="error">
              {consentError}
            </p>
          ) : waitingForConsent ? (
            <p>Loading…</p>
          ) : hash === "#/account" ? (
            <AccountPage session={session} me={me} onMe={setMe} onSession={replaceToken} />
          ) : hash === "#/admin" && session.role === "admin" ? (
            <AdminPage session={session} myId={me.id} />
          ) : mustAgree || hash === "#/privacy" ? (
            <PrivacyPage
              session={session}
              state={consent}
              gate={mustAgree}
              onChange={setConsent}
              erasure={erasure}
              onErasureChange={setErasure}
            />
          ) : newProblem && session.role === "instructor" ? (
            <NewProblemPage session={session} courseId={Number(newProblem[1])} />
          ) : editProblem && session.role === "instructor" ? (
            <NewProblemPage
              key={editProblem[2]}
              session={session}
              courseId={Number(editProblem[1])}
              problemId={Number(editProblem[2])}
            />
          ) : notes && session.role === "instructor" ? (
            <NotesPage session={session} courseId={Number(notes[1])} />
          ) : assignments && session.role === "instructor" ? (
            <AssignmentsPage session={session} courseId={Number(assignments[1])} />
          ) : gradebook && session.role !== "student" ? (
            <GradebookPage session={session} courseId={Number(gradebook[1])} />
          ) : studentWork && session.role === "instructor" ? (
            <StudentWorkPage session={session} courseId={Number(studentWork[1])} studentId={Number(studentWork[2])} />
          ) : studentSubmission && session.role === "instructor" ? (
            <SubmissionView
              session={session}
              courseId={Number(studentSubmission[1])}
              studentId={Number(studentSubmission[2])}
              submissionId={Number(studentSubmission[3])}
            />
          ) : studentConcept && session.role === "instructor" ? (
            <WhyPage
              session={session}
              courseId={Number(studentConcept[1])}
              conceptId={Number(studentConcept[3])}
              source={`/courses/${studentConcept[1]}/students/${studentConcept[2]}/mastery/${studentConcept[3]}/history`}
              back={{ href: `#/class/${studentConcept[1]}/student/${studentConcept[2]}`, label: "Back to the student" }}
            />
          ) : classView ? (
            <InstructorPage session={session} courseId={Number(classView[1])} />
          ) : why ? (
            <WhyPage session={session} courseId={Number(why[1])} conceptId={Number(why[2])} />
          ) : mastery ? (
            <DashboardPage session={session} courseId={Number(mastery[1])} />
          ) : placement ? (
            <PlacementPage session={session} courseId={Number(placement[1])} />
          ) : problem ? (
            <ProblemPage session={session} problemId={Number(problem[1])} />
          ) : course ? (
            <CoursePage
              session={session}
              courseId={Number(course[1])}
              title={courses.find((c) => c.id === Number(course[1]))?.title}
            />
          ) : (
            <CoursesPage session={session} />
          )}
        </main>
      </div>
      {!mustAgree && !waitingForConsent && <ChatPanel session={session} problemId={problem ? Number(problem[1]) : null} />}
    </>
  );
}
