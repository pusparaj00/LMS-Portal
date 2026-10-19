import { useEffect, useRef, useState } from "react";

import { ApiError, Course, Session, api, loadSession, saveSession } from "./api";
import { AccountPage, Me } from "./pages/AccountPage";
import { AdminPage } from "./pages/AdminPage";
import { AssignmentsPage } from "./pages/AssignmentsPage";
import { QuizPage } from "./pages/QuizPage";
import { RubricsPage } from "./pages/RubricsPage";
import { CalendarPage } from "./pages/CalendarPage";
import { InsightPage } from "./pages/InsightPage";
import { JoinPage } from "./pages/JoinPage";
import { PeoplePage } from "./pages/PeoplePage";
import { Bell, NotificationsPage } from "./pages/NotificationsPage";
import { ToDoPage } from "./pages/ToDoPage";
import { ToReviewPage } from "./pages/ToReviewPage";
import { WorkPage } from "./pages/WorkPage";
import { WorkReviewPage } from "./pages/WorkReviewPage";
import { QuizzesPage } from "./pages/QuizzesPage";
import { ChatPanel } from "./pages/ChatPanel";
import { CoursePage } from "./pages/CoursePage";
import { CoursesPage } from "./pages/CoursesPage";
import { DashboardPage, WhyPage } from "./pages/DashboardPage";
import { RoleDashboard } from "./pages/RoleDashboard";
import { ContentEditorPage } from "./pages/ContentEditorPage";
import { CourseAnalyticsPage } from "./pages/CourseAnalyticsPage";
import { GradebookPage } from "./pages/GradebookPage";
import { GradesPage } from "./pages/GradesPage";
import { HomePage } from "./pages/HomePage";
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
import { ThemeToggle } from "./design/ThemeToggle";
import { clearRecent } from "./design/recent";

// Addresses a signed-out visitor can see; anything else is a deep link that waits behind the login page.
const PUBLIC_HASHES = new Set(["", "#/", "#/login", "#/register", "#/features", "#/walkthroughs", "#/roles", "#/status", "#/faq"]);

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
  const [coursesTick, setCoursesTick] = useState(0);
  const [lastCourse, setLastCourse] = useState<number | null>(null);
  const hash = useHash();
  const returnTo = useRef<string | null>(null);
  // null = automatic: the menu gives the editor room on a problem page and is open elsewhere (ux-plan 3)
  const [menuPref, setMenuPref] = useState<boolean | null>(null);
  const menuOpen = menuPref ?? !hash.startsWith("#/problem/");
  // The course menu stays on screen while a problem of that course is open, since a problem's address has no course id.
  const hashCourse = hash.match(/^#\/(?:course|class|mastery|placement|recheck)\/(\d+)/);
  useEffect(() => {
    if (hashCourse) setLastCourse(Number(hashCourse[1]));
    else if (!hash.startsWith("#/problem/")) setLastCourse(null);
  }, [hash]);

  const update = (next: Session | null) => {
    if (!next) clearRecent();
    saveSession(next);
    setSession(next);
    setConsent(null);
    setErasure(null);
    setMe(null);
    const target = returnTo.current;
    returnTo.current = null;
    window.location.hash = !next ? "#/login" : target ?? (next.role === "admin" ? "#/admin" : "#/dashboard");
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

  // a page that changes a course (its details, or a join by code) says so, and the menu and headers follow
  useEffect(() => {
    const again = () => setCoursesTick((n) => n + 1);
    window.addEventListener("lms:courses", again);
    return () => window.removeEventListener("lms:courses", again);
  }, []);

  useEffect(() => {
    if (!session || !me || me.must_change_password) return;
    api<Course[]>("/courses", session)
      .then(setCourses)
      .catch(() => setCourses([]));
  }, [session?.token, me?.must_change_password, lastCourse, coursesTick]);

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
  if (!session) {
    if (!PUBLIC_HASHES.has(hash)) returnTo.current = hash;
    else if (hash !== "#/login" && hash !== "#/register") returnTo.current = null;
    if (returnTo.current || hash === "#/login" || hash === "#/register")
      return <LoginPage key={hash} onSession={update} initialMode={hash === "#/register" ? "register" : "login"} />;
    return <HomePage />;
  }
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
  if (hash === "#/home") return <HomePage dashboardHref={session.role === "admin" ? "#/admin" : "#/dashboard"} />;
  const waitingForConsent = session.role === "student" && consent === null;
  const mustAgree = session.role === "student" && consent !== null && !consent.accepted;

  const course = hash.match(/^#\/course\/(\d+)$/);
  const newProblem = hash.match(/^#\/course\/(\d+)\/problem\/new$/);
  const editProblem = hash.match(/^#\/course\/(\d+)\/problem\/(\d+)\/edit$/);
  const notes = hash.match(/^#\/course\/(\d+)\/notes$/);
  const assignments = hash.match(/^#\/course\/(\d+)\/assignments$/);
  const quizzes = hash.match(/^#\/course\/(\d+)\/quizzes$/);
  const takeQuiz = hash.match(/^#\/course\/(\d+)\/quiz\/(\d+)$/);
  const handIn = hash.match(/^#\/course\/(\d+)\/assignment\/(\d+)$/);
  const reviewWork = hash.match(/^#\/course\/(\d+)\/assignment\/(\d+)\/review$/);
  const joinLink = hash.match(/^#\/join\/([0-9A-Za-z-]+)$/);
  const insight = hash.match(/^#\/course\/(\d+)\/insight$/);
  const rubrics = hash.match(/^#\/course\/(\d+)\/rubrics$/);
  const classwork = hash.match(/^#\/course\/(\d+)\/classwork$/);
  const people = hash.match(/^#\/course\/(\d+)\/people$/);
  const gradebook = hash.match(/^#\/course\/(\d+)\/gradebook$/);
  const contentEditor = hash.match(/^#\/course\/(\d+)\/content$/);
  const analytics = hash.match(/^#\/course\/(\d+)\/analytics$/);
  const problem = hash.match(/^#\/problem\/(\d+)$/);
  const classView = hash.match(/^#\/class\/(\d+)$/);
  const studentWork = hash.match(/^#\/class\/(\d+)\/student\/(\d+)$/);
  const studentSubmission = hash.match(/^#\/class\/(\d+)\/student\/(\d+)\/submission\/(\d+)$/);
  const studentConcept = hash.match(/^#\/class\/(\d+)\/student\/(\d+)\/concept\/(\d+)$/);
  const placement = hash.match(/^#\/(placement|recheck)\/(\d+)$/);
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
        <button className="ghost" aria-expanded={menuOpen} aria-controls="main-menu" onClick={() => setMenuPref(!menuOpen)}>
          Menu
        </button>
        <a className="brand" href={session.role === "admin" ? "#/admin" : "#/dashboard"}>
          Adaptive LMS
        </a>
        <span className="who">
          <span className="who-name">{me.display_name ?? me.email}</span>
          <span className={`role role-${session.role}`}>{session.role}</span>
        </span>
        {/* the privacy notice and several messages tell people to find these two in the top bar */}
        {session.role !== "admin" && <Bell session={session} current={hash === "#/notifications"} />}
        <a href="#/account" aria-current={hash === "#/account" ? "page" : undefined}>
          Account
        </a>
        <a href="#/privacy" aria-current={hash === "#/privacy" ? "page" : undefined}>
          Privacy
        </a>
        <ThemeToggle />
        <button className="ghost" onClick={() => update(null)}>
          Log out
        </button>
      </header>
      {erasure && <ErasureBanner state={erasure} />}
      <div className={menuOpen ? "shell" : "shell menu-closed"}>
        {menuOpen && !mustAgree && !waitingForConsent && (
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
          ) : handIn && session.role === "student" ? (
            <WorkPage key={handIn[2]} session={session} courseId={Number(handIn[1])} assignmentId={Number(handIn[2])} />
          ) : reviewWork && session.role === "instructor" ? (
            <WorkReviewPage key={reviewWork[2]} session={session} courseId={Number(reviewWork[1])} assignmentId={Number(reviewWork[2])} />
          ) : insight && session.role !== "student" ? (
            <InsightPage session={session} courseId={Number(insight[1])} />
          ) : rubrics && session.role === "instructor" ? (
            <RubricsPage session={session} courseId={Number(rubrics[1])} />
          ) : classwork ? (
            <CoursePage
              key={`${classwork[1]}-classwork`}
              session={session}
              courseId={Number(classwork[1])}
              title={courses.find((c) => c.id === Number(classwork[1]))?.title}
              details={courses.find((c) => c.id === Number(classwork[1]))}
              tab="classwork"
            />
          ) : joinLink ? (
            <JoinPage key={joinLink[1]} session={session} code={joinLink[1]} />
          ) : people && session.role !== "admin" ? (
            <PeoplePage key={people[1]} session={session} courseId={Number(people[1])} />
          ) : hash === "#/todo" && session.role === "student" ? (
            <ToDoPage session={session} />
          ) : hash === "#/calendar" && session.role !== "admin" ? (
            <CalendarPage session={session} />
          ) : hash === "#/notifications" && session.role !== "admin" ? (
            <NotificationsPage session={session} />
          ) : hash === "#/review" && session.role === "instructor" ? (
            <ToReviewPage session={session} />
          ) : quizzes && session.role === "instructor" ? (
            <QuizzesPage session={session} courseId={Number(quizzes[1])} />
          ) : takeQuiz && session.role === "student" ? (
            <QuizPage key={takeQuiz[2]} session={session} courseId={Number(takeQuiz[1])} quizId={Number(takeQuiz[2])} />
          ) : gradebook && session.role !== "student" ? (
            <GradebookPage session={session} courseId={Number(gradebook[1])} />
          ) : contentEditor && session.role === "instructor" ? (
            <ContentEditorPage session={session} courseId={Number(contentEditor[1])} />
          ) : analytics && session.role !== "student" ? (
            <CourseAnalyticsPage session={session} courseId={Number(analytics[1])} />
          ) : hash === "#/grades" && session.role === "student" ? (
            <GradesPage session={session} />
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
            <PlacementPage session={session} courseId={Number(placement[2])} recheck={placement[1] === "recheck"} />
          ) : problem ? (
            <ProblemPage session={session} problemId={Number(problem[1])} />
          ) : course ? (
            <CoursePage
              session={session}
              courseId={Number(course[1])}
              title={courses.find((c) => c.id === Number(course[1]))?.title}
              details={courses.find((c) => c.id === Number(course[1]))}
              tab="stream"
            />
          ) : hash === "#/dashboard" ? (
            <RoleDashboard session={session} me={me} courses={courses} />
          ) : (
            <CoursesPage session={session} />
          )}
        </main>
      </div>
      {!mustAgree && !waitingForConsent && <ChatPanel session={session} problemId={problem ? Number(problem[1]) : null} />}
    </>
  );
}
