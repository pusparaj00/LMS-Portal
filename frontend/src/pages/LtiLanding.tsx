import { useEffect, useState } from "react";

import { ApiError, Role, Session, api } from "../api";

type LtiSession = { access_token: string; role: Role; course_id: number };

/** TR-A-09: the end of a launch from the LMS. The one-time code in the address is swapped for a session once. */
export function LtiLanding({ code, onSession }: { code: string; onSession: (s: Session, courseId: number) => void }) {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<LtiSession>("/lti/session", null, { body: { code } })
      .then((s) => onSession({ token: s.access_token, role: s.role }, s.course_id))
      .catch((e) => setError(e instanceof ApiError ? e.message : "The server could not be reached."));
  }, [code]);

  return (
    <main className="narrow">
      {error ? (
        <p role="alert" className="error">
          {error}
        </p>
      ) : (
        <p role="status">Opening the course…</p>
      )}
    </main>
  );
}
