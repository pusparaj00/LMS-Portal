import { useCallback, useEffect, useState } from "react";

import { Session, api } from "../api";
import { when } from "./AssignmentsPage";

export type Notice = { id: number; kind: string; title: string; link: string; created_at: string; read: boolean };
export type Inbox = { unread: number; items: Notice[] };

const POLL_MS = 60_000;

/** F-80: the bell in the top bar. It shows how many notifications are unread and checks again every minute. */
export function Bell({ session, current }: { session: Session; current: boolean }) {
  const [unread, setUnread] = useState(0);
  const load = useCallback(() => {
    api<Inbox>("/notifications", session)
      .then((r) => setUnread(r.unread))
      .catch(() => undefined);
  }, [session.token]);
  useEffect(() => {
    load();
    const timer = window.setInterval(load, POLL_MS);
    window.addEventListener("lms:notifications", load);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("lms:notifications", load);
    };
  }, [load]);
  return (
    <a href="#/notifications" aria-current={current ? "page" : undefined} aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}>
      Notifications{unread > 0 && <span className="badge"> {unread > 99 ? "99+" : unread}</span>}
    </a>
  );
}

/** F-80: a person's own notifications, newest first; opening one marks it read and goes to the page it is about. */
export function NotificationsPage({ session }: { session: Session }) {
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api<Inbox>("/notifications", session)
      .then(setInbox)
      .catch((e: Error) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function open(n: Notice) {
    try {
      if (!n.read) await api(`/notifications/${n.id}/read`, session, { method: "POST" });
      window.dispatchEvent(new Event("lms:notifications"));
    } finally {
      window.location.hash = n.link;
    }
  }

  async function readAll() {
    try {
      await api("/notifications/read-all", session, { method: "POST" });
      window.dispatchEvent(new Event("lms:notifications"));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not mark them read.");
    }
  }

  return (
    <>
      <h1>Notifications</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p>
        <small>{inbox ? `${inbox.unread} unread` : "Loading…"}</small>{" "}
        {inbox && inbox.unread > 0 && <button onClick={readAll}>Mark all read</button>}
      </p>
      {inbox && inbox.items.length === 0 && <p className="empty">Nothing yet. New announcements, returned work, comments and due dates appear here.</p>}
      <ul className="rows">
        {inbox?.items.map((n) => (
          <li key={n.id} className={n.read ? "read" : "unread"}>
            <span className="grow">
              <button className="link" onClick={() => open(n)}>
                {!n.read && <span className="dot" aria-label="unread" />} {n.title}
              </button>
              <br />
              <small>{when(n.created_at)}</small>
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}
