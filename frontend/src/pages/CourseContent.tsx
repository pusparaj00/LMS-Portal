import { useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { Content, ContentItem, KIND_LABEL, size } from "./contentTypes";

/** Saves a lesson PDF. The request carries the sign-in token, so it is fetched and then handed to the browser. */
export async function downloadPdf(session: Session, courseId: number, item: ContentItem): Promise<void> {
  const response = await fetch(`/api/v1/courses/${courseId}/items/${item.id}/file`, {
    headers: { Authorization: `Bearer ${session.token}` },
  });
  if (!response.ok) throw new ApiError(response.status, `Download failed (${response.status})`);
  const url = URL.createObjectURL(await response.blob());
  const link = Object.assign(document.createElement("a"), { href: url, download: item.file_name ?? "lesson.pdf" });
  link.click();
  URL.revokeObjectURL(url);
}

function ItemView({
  item,
  session,
  courseId,
  onToggle,
  onError,
}: {
  item: ContentItem;
  session: Session;
  courseId: number;
  onToggle?: (item: ContentItem) => void;
  onError: (message: string) => void;
}) {
  return (
    <li className="lesson">
      <div className="lesson-head">
        {onToggle && (
          <label className="lesson-done">
            <input type="checkbox" checked={item.completed === true} onChange={() => onToggle(item)} />
            <span className="sr-only">Mark “{item.title}” as complete</span>
          </label>
        )}
        <strong>{item.title}</strong>
        <span className="tag">{KIND_LABEL[item.kind]}</span>
        {!item.published && <span className="tag">Hidden from students</span>}
      </div>
      {item.kind === "text" && <p className="lesson-text">{item.body}</p>}
      {(item.kind === "link" || item.kind === "video") && item.url && (
        <p>
          <a href={item.url} target="_blank" rel="noopener noreferrer">
            {item.kind === "video" ? "Watch the video" : "Open the link"}
          </a>{" "}
          <span className="muted">(opens in a new tab)</span>
        </p>
      )}
      {item.kind === "file" && (
        <p>
          <button
            className="link"
            onClick={() => downloadPdf(session, courseId, item).catch((e: Error) => onError(e.message))}
          >
            Download {item.file_name}
          </button>{" "}
          {item.file_size !== null && <span className="muted">({size(item.file_size)})</span>}
        </p>
      )}
    </li>
  );
}

/** F-66, F-67, F-68: the course's modules and lessons. A student ticks items off; the teacher sees what is hidden. */
export function CourseContent({ session, courseId }: { session: Session; courseId: number }) {
  const [content, setContent] = useState<Content | null>(null);
  const [error, setError] = useState<string | null>(null);
  const student = session.role === "student";

  useEffect(() => {
    api<Content>(`/courses/${courseId}/content`, session)
      .then(setContent)
      .catch((e: Error) => setError(e.message));
  }, [courseId]);

  async function toggle(item: ContentItem) {
    setError(null);
    try {
      await api(`/courses/${courseId}/items/${item.id}/completion`, session, {
        method: item.completed ? "DELETE" : "PUT",
      });
      const next = await api<Content>(`/courses/${courseId}/content`, session);
      setContent(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Your progress could not be saved.");
    }
  }

  if (error && !content)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!content) return null;
  if (content.modules.length === 0 && student) return null;

  return (
    <section className="panel content" aria-label="Course content">
      <h2>Course content</h2>
      {student && content.total > 0 && (
        <>
          <p>
            {content.completed} of {content.total} items complete
          </p>
          <div className="meter" role="img" aria-label={`${content.completed} of ${content.total} items complete`}>
            <span style={{ width: `${content.total ? ((content.completed ?? 0) / content.total) * 100 : 0}%` }} />
          </div>
        </>
      )}
      {!student && (
        <p>
          <a className="button" href={`#/course/${courseId}/content`}>
            Manage content
          </a>
        </p>
      )}
      {content.modules.length === 0 && <p className="empty">This course has no modules yet.</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {content.modules.map((m) => (
        <details key={m.id} className="module" open>
          <summary>
            <strong>{m.title}</strong>{" "}
            {student ? (
              <span className="muted">
                {m.completed} of {m.total} done
              </span>
            ) : (
              <>
                {!m.published && <span className="tag">Draft</span>}
                {m.completion_rate !== null && <span className="muted">{m.completion_rate}% of the class done</span>}
              </>
            )}
          </summary>
          {m.items.length === 0 ? (
            <p className="empty">Nothing in this module yet.</p>
          ) : (
            <ul className="lessons">
              {m.items.map((item) => (
                <ItemView
                  key={item.id}
                  item={item}
                  session={session}
                  courseId={courseId}
                  onToggle={student ? toggle : undefined}
                  onError={setError}
                />
              ))}
            </ul>
          )}
        </details>
      ))}
    </section>
  );
}
