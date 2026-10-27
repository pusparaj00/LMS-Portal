import { ReactNode, useEffect, useState } from "react";

import { Session, api } from "../api";
import { Me } from "./AccountPage";

const stamp = () => new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC";
const TILES = 48;

/** TR-S-11: a faint, unclickable label with the signed-in student's name and the time over a page that shows test
 * content, so a screenshot or photo of it can be traced back to who had it open. It deters; it cannot stop a capture. */
export function Watermark({ session }: { session: Session }) {
  const [name, setName] = useState("");
  const [time, setTime] = useState(stamp);
  useEffect(() => {
    api<Me>("/me", session)
      .then((me) => setName(me.display_name || me.email))
      .catch(() => setName(""));
  }, [session.token]);
  useEffect(() => {
    const timer = window.setInterval(() => setTime(stamp()), 30000);
    return () => window.clearInterval(timer);
  }, []);
  if (session.role !== "student" || !name) return null;
  return (
    <div className="watermark" aria-hidden="true">
      {Array.from({ length: TILES }, (_, i) => (
        <span key={i}>
          {name} · {time}
        </span>
      ))}
    </div>
  );
}

const block = (e: { preventDefault: () => void }) => e.preventDefault();

/** TR-S-11: question text that cannot be selected, copied, cut, dragged, opened in a context menu or printed. Screen
 * readers still read it. Wrap only text, never the editor or an answer box. Staff are not restricted. */
export function Protected({ session, children }: { session: Session; children: ReactNode }) {
  if (session.role !== "student") return <>{children}</>;
  return (
    <div className="protected" onCopy={block} onCut={block} onDragStart={block} onContextMenu={block}>
      {children}
    </div>
  );
}
