import { useEffect, useState } from "react";

import { Session, api, loadSession, saveSession } from "./api";
import { ChatPanel } from "./pages/ChatPanel";
import { CoursePage } from "./pages/CoursePage";
import { CoursesPage } from "./pages/CoursesPage";
import { DashboardPage, WhyPage } from "./pages/DashboardPage";
import { NewProblemPage } from "./pages/NewProblemPage";
import { NotesPage } from "./pages/NotesPage";
import { InstructorPage } from "./pages/InstructorPage";
import { LoginPage } from "./pages/LoginPage";
import { PlacementPage } from "./pages/PlacementPage";
import { ConsentState, PrivacyPage } from "./pages/PrivacyPage";
import { ProblemPage } from "./pages/ProblemPage";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

export function App() {
  const [session, setSession] = useState<Session | null>(loadSession);
  const [consent, setConsent] = useState<ConsentState | null>(null);
  const [consentError, setConsentError] = useState<string | null>(null);
  const hash = useHash();

  const update = (next: Session | null) => {
    saveSession(next);
    setSession(next);
    setConsent(null);
    window.location.hash = next ? "#/courses" : "#/login";
  };

  // A student's data is only processed after they agree to the privacy notice (TR-S-05).
  useEffect(() => {
    if (session?.role !== "student") return;
    setConsentError(null);
    api<ConsentState>("/consent", session)
      .then(setConsent)
      .catch((e: Error) => setConsentError(e.message));
  }, [session?.token]);

  if (!session) return <LoginPage onSession={update} />;
  const waitingForConsent = session.role === "student" && consent === null;
  const mustAgree = session.role === "student" && consent !== null && !consent.accepted;

  const course = hash.match(/^#\/course\/(\d+)$/);
  const newProblem = hash.match(/^#\/course\/(\d+)\/problem\/new$/);
  const notes = hash.match(/^#\/course\/(\d+)\/notes$/);
  const problem = hash.match(/^#\/problem\/(\d+)$/);
  const classView = hash.match(/^#\/class\/(\d+)$/);
  const placement = hash.match(/^#\/placement\/(\d+)$/);
  const mastery = hash.match(/^#\/mastery\/(\d+)$/);
  const why = hash.match(/^#\/mastery\/(\d+)\/concept\/(\d+)$/);

  return (
    <>
      <header className="bar">
        <a className="brand" href="#/courses">
          Adaptive LMS
        </a>
        <span className="who">{session.role}</span>
        <a href="#/privacy">Privacy</a>
        <button className="link" onClick={() => update(null)}>
          Log out
        </button>
      </header>
      <main>
        {consentError ? (
          <p role="alert" className="error">
            {consentError}
          </p>
        ) : waitingForConsent ? (
          <p>Loading…</p>
        ) : mustAgree || hash === "#/privacy" ? (
          <PrivacyPage session={session} state={consent} gate={mustAgree} onChange={setConsent} />
        ) : newProblem && session.role === "instructor" ? (
          <NewProblemPage session={session} courseId={Number(newProblem[1])} />
        ) : notes && session.role === "instructor" ? (
          <NotesPage session={session} courseId={Number(notes[1])} />
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
          <CoursePage session={session} courseId={Number(course[1])} />
        ) : (
          <CoursesPage session={session} />
        )}
      </main>
      {!mustAgree && !waitingForConsent && <ChatPanel session={session} problemId={problem ? Number(problem[1]) : null} />}
    </>
  );
}
