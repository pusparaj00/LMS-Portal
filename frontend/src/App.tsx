import { useEffect, useState } from "react";

import { Session, loadSession, saveSession } from "./api";
import { CoursePage } from "./pages/CoursePage";
import { CoursesPage } from "./pages/CoursesPage";
import { DashboardPage, WhyPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { PlacementPage } from "./pages/PlacementPage";
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
  const hash = useHash();

  const update = (next: Session | null) => {
    saveSession(next);
    setSession(next);
    window.location.hash = next ? "#/courses" : "#/login";
  };

  if (!session) return <LoginPage onSession={update} />;

  const course = hash.match(/^#\/course\/(\d+)$/);
  const problem = hash.match(/^#\/problem\/(\d+)$/);
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
        <button className="link" onClick={() => update(null)}>
          Log out
        </button>
      </header>
      <main>
        {why ? (
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
    </>
  );
}
