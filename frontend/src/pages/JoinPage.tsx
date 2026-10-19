import { useEffect, useState } from "react";

import { ApiError, Course, Session, api } from "../api";

/** F-81: an invite link (#/join/CODE) joins the signed-in student to the course the code belongs to. */
export function JoinPage({ session, code }: { session: Session; code: string }) {
  const [message, setMessage] = useState("Joining the class…");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (session.role !== "student") {
      setMessage("Only students can join a class with a code. You are signed in as " + session.role + ".");
      setFailed(true);
      return;
    }
    api<Course>("/courses/join", session, { body: { code } })
      .then((course) => {
        window.dispatchEvent(new Event("lms:courses"));
        window.location.hash = `#/course/${course.id}`;
      })
      .catch((e) => {
        setFailed(true);
        setMessage(e instanceof ApiError ? e.message : "Could not join the class.");
      });
  }, [code]);

  return (
    <>
      <h1>Join a class</h1>
      <p role={failed ? "alert" : "status"} className={failed ? "error" : undefined}>
        {message}
      </p>
      {failed && (
        <p>
          <a href="#/courses">Back to my courses</a>
        </p>
      )}
    </>
  );
}
