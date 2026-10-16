import { useEffect, useRef, useState } from "react";

import { ApiError, Session, api } from "../api";

type Route = "explain" | "hint" | "progress" | "recommend" | "lms" | "general";
type Source = { chunk_id: number; title: string; section: string };
type ChatReply = {
  message_id: number;
  reply: string;
  route: Route;
  router: { how: "llm" | "keyword" | "student"; confidence: number | null; reason: string };
  tools: string[];
  sources: Source[];
};
type Entry = { id: number; student: string; problemId: number | null; reply: ChatReply | null; error?: string };

const ROUTE_LABELS: Record<Route, string> = {
  explain: "Explain an error",
  hint: "Hint",
  progress: "My progress",
  recommend: "What next",
  lms: "Course info",
  general: "Python question",
};

const HOW_LABELS = {
  llm: "chosen by the assistant",
  keyword: "chosen by keyword rules",
  student: "chosen by you",
};

export function ChatPanel({ session, problemId }: { session: Session; problemId: number | null }) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [entries, open]);

  async function send(message: string, route?: Route, existing?: Entry) {
    const id = existing?.id ?? Date.now();
    const askedAbout = existing ? existing.problemId : problemId;
    setBusy(true);
    setEntries((all) =>
      existing
        ? all.map((e) => (e.id === id ? { ...e, reply: null, error: undefined } : e))
        : [...all, { id, student: message, problemId, reply: null }],
    );
    try {
      const reply = await api<ChatReply>("/chat", session, { body: { message, problem_id: askedAbout, route } });
      setEntries((all) => all.map((e) => (e.id === id ? { ...e, reply } : e)));
    } catch (e) {
      const error = e instanceof ApiError ? e.message : "The assistant could not be reached.";
      setEntries((all) => all.map((e2) => (e2.id === id ? { ...e2, error } : e2)));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    void send(message);
  }

  if (session.role !== "student") return null;
  return (
    <aside className={`chat ${open ? "open" : ""}`} aria-label="Assistant chat">
      <button className="chat-toggle primary" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "Close assistant" : "Ask the assistant"}
      </button>
      {open && (
        <div className="chat-body">
          <div className="chat-log" aria-live="polite">
            {entries.length === 0 && (
              <p className="empty">
                Ask about an error in your last submission, ask for a hint, check your progress, or ask a Python
                question.
                {problemId === null && " Open a problem to get help with a submission."}
              </p>
            )}
            {entries.map((entry) => (
              <div key={entry.id} className="exchange">
                <p className="you">{entry.student}</p>
                {entry.error && (
                  <p role="alert" className="error">
                    {entry.error}
                  </p>
                )}
                {!entry.reply && !entry.error && <p className="progress">Thinking…</p>}
                {entry.reply && (
                  <div className="answer">
                    <p className="route">
                      <strong>{ROUTE_LABELS[entry.reply.route]}</strong>{" "}
                      <small>({HOW_LABELS[entry.reply.router.how]})</small>
                    </p>
                    <p className="reply">{entry.reply.reply}</p>
                    {entry.reply.sources.length > 0 && (
                      <small>
                        From the course notes: {entry.reply.sources.map((s) => `${s.title} > ${s.section}`).join("; ")}
                      </small>
                    )}
                    <label className="correct">
                      <small>Wrong route?</small>
                      <select
                        value=""
                        onChange={(e) => void send(entry.student, e.target.value as Route, entry)}
                        disabled={busy}
                        aria-label="Choose the right route and ask again"
                      >
                        <option value="">Choose…</option>
                        {(Object.keys(ROUTE_LABELS) as Route[])
                          .filter((r) => r !== entry.reply?.route)
                          .map((r) => (
                            <option key={r} value={r}>
                              {ROUTE_LABELS[r]}
                            </option>
                          ))}
                      </select>
                    </label>
                  </div>
                )}
              </div>
            ))}
            <div ref={bottom} />
          </div>
          <form onSubmit={submit} className="chat-form">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type your question"
              maxLength={2000}
              aria-label="Your message"
            />
            <button className="primary" disabled={busy || !text.trim()}>
              Send
            </button>
          </form>
        </div>
      )}
    </aside>
  );
}
