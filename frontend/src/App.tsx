import { useEffect, useState } from "react";

import { Session, loadSession, saveSession } from "./api";
import { CoursePage } from "./pages/CoursePage";
import { CoursesPage } from "./pages/CoursesPage";
import { LoginPage } from "./pages/LoginPage";
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
        {problem ? (
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
