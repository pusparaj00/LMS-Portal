import { FormEvent, useEffect, useState } from "react";

import { ApiError, Session, api } from "../api";
import { Content, ContentItem, ContentModule, ItemKind, KIND_LABEL, MAX_PDF_BYTES, size } from "./contentTypes";

const toBase64 = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });

type Run = (action: () => Promise<unknown>, failure: string) => Promise<void>;

function AddItem({ courseId, module, session, run }: { courseId: number; module: ContentModule; session: Session; run: Run }) {
  const [kind, setKind] = useState<ItemKind>("text");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [visible, setVisible] = useState(true);
  const [problem, setProblem] = useState<string | null>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    if (kind === "file" && !file) return setProblem("Choose a PDF file.");
    if (file && file.size > MAX_PDF_BYTES) return setProblem(`The PDF is larger than ${size(MAX_PDF_BYTES)}.`);
    const payload =
      kind === "text"
        ? { kind, title, body, published: visible }
        : kind === "file"
          ? { kind, title, pdf_base64: await toBase64(file as File), file_name: (file as File).name, published: visible }
          : { kind, title, url, published: visible };
    await run(() => api(`/courses/${courseId}/modules/${module.id}/items`, session, { body: payload }), "The item could not be added.");
    setTitle("");
    setBody("");
    setUrl("");
    setFile(null);
    setFileKey((k) => k + 1);
  }

  return (
    <form className="item-form" onSubmit={add} aria-label={`Add an item to ${module.title}`}>
      <select value={kind} onChange={(e) => setKind(e.target.value as ItemKind)} aria-label="Item type">
        {(Object.keys(KIND_LABEL) as ItemKind[]).map((k) => (
          <option key={k} value={k}>
            {KIND_LABEL[k]}
          </option>
        ))}
      </select>
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Item title" maxLength={200} required />
      {kind === "text" && (
        <textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Text" rows={3} maxLength={20000} required />
      )}
      {(kind === "link" || kind === "video") && (
        <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" maxLength={2000} required />
      )}
      {kind === "file" && (
        <input key={fileKey} type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-label="PDF file" />
      )}
      <label>
        <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} /> Visible to students
      </label>
      <button className="primary">Add item</button>
      {problem && <p role="alert" className="error">{problem}</p>}
    </form>
  );
}

function ItemRow({
  item, courseId, session, run, first, last,
}: { item: ContentItem; courseId: number; session: Session; run: Run; first: boolean; last: boolean }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [value, setValue] = useState(item.body ?? item.url ?? "");
  const base = `/courses/${courseId}/items/${item.id}`;

  async function save(event: FormEvent) {
    event.preventDefault();
    const change = item.kind === "text" ? { title, body: value } : item.kind === "file" ? { title } : { title, url: value };
    await run(() => api(base, session, { method: "PATCH", body: change }), "The item could not be saved.");
    setEditing(false);
  }

  return (
    <li className="lesson">
      {editing ? (
        <form className="item-form" onSubmit={save}>
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required aria-label="Item title" />
          {item.kind === "text" && (
            <textarea value={value} onChange={(e) => setValue(e.target.value)} rows={4} maxLength={20000} required aria-label="Text" />
          )}
          {(item.kind === "link" || item.kind === "video") && (
            <input type="url" value={value} onChange={(e) => setValue(e.target.value)} maxLength={2000} required aria-label="Link" />
          )}
          <span>
            <button className="primary">Save</button> <button type="button" onClick={() => setEditing(false)}>Cancel</button>
          </span>
        </form>
      ) : (
        <div className="lesson-head">
          <strong>{item.title}</strong>
          <span className="tag">{KIND_LABEL[item.kind]}</span>
          {item.file_name && <span className="muted">{item.file_name} ({size(item.file_size ?? 0)})</span>}
          {!item.published && <span className="tag">Hidden</span>}
          <span className="row-actions">
            <button disabled={first} onClick={() => run(() => api(`${base}/move`, session, { body: { direction: "up" } }), "Could not move it.")}>
              Up
            </button>
            <button disabled={last} onClick={() => run(() => api(`${base}/move`, session, { body: { direction: "down" } }), "Could not move it.")}>
              Down
            </button>
            <button onClick={() => run(() => api(base, session, { method: "PATCH", body: { published: !item.published } }), "Could not change it.")}>
              {item.published ? "Hide" : "Show"}
            </button>
            {item.kind !== "file" && <button onClick={() => setEditing(true)}>Edit</button>}
            <button
              onClick={() => window.confirm(`Delete “${item.title}”? Students' progress on it is deleted too.`) && run(() => api(base, session, { method: "DELETE" }), "Could not delete it.")}
            >
              Delete
            </button>
          </span>
        </div>
      )}
    </li>
  );
}

function ModuleCard({
  module, courseId, session, run, first, last,
}: { module: ContentModule; courseId: number; session: Session; run: Run; first: boolean; last: boolean }) {
  const [title, setTitle] = useState(module.title);
  const base = `/courses/${courseId}/modules/${module.id}`;
  return (
    <section className="panel module-card" aria-label={module.title}>
      <div className="module-head">
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} aria-label="Module title" />
        <button disabled={title.trim() === module.title || !title.trim()} onClick={() => run(() => api(base, session, { method: "PATCH", body: { title } }), "Could not rename it.")}>
          Rename
        </button>
        <label>
          <input
            type="checkbox"
            checked={module.published}
            onChange={() => run(() => api(base, session, { method: "PATCH", body: { published: !module.published } }), "Could not change it.")}
          />{" "}
          Visible to students
        </label>
        <span className="row-actions">
          <button disabled={first} onClick={() => run(() => api(`${base}/move`, session, { body: { direction: "up" } }), "Could not move it.")}>Up</button>
          <button disabled={last} onClick={() => run(() => api(`${base}/move`, session, { body: { direction: "down" } }), "Could not move it.")}>Down</button>
          <button
            onClick={() => window.confirm(`Delete “${module.title}” with its ${module.total} items? Students' progress is deleted too.`) && run(() => api(base, session, { method: "DELETE" }), "Could not delete it.")}
          >
            Delete module
          </button>
        </span>
      </div>
      {module.completion_rate !== null && <p className="muted">{module.completion_rate}% of the class has completed this module.</p>}
      {module.items.length === 0 ? (
        <p className="empty">No items yet.</p>
      ) : (
        <ul className="lessons">
          {module.items.map((item, i) => (
            <ItemRow key={item.id} item={item} courseId={courseId} session={session} run={run} first={i === 0} last={i === module.items.length - 1} />
          ))}
        </ul>
      )}
      <AddItem courseId={courseId} module={module} session={session} run={run} />
    </section>
  );
}

/** F-66, F-67: the teacher builds the course: modules, items, their order, and what students can see. */
export function ContentEditorPage({ session, courseId }: { session: Session; courseId: number }) {
  const [content, setContent] = useState<Content | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");

  const load = () =>
    api<Content>(`/courses/${courseId}/content`, session)
      .then(setContent)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, [courseId]);

  const run: Run = async (action, failure) => {
    setError(null);
    try {
      await action();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : failure);
    }
  };

  return (
    <article className="dash-wide">
      <p>
        <a href={`#/course/${courseId}`}>Back to the course</a>
      </p>
      <h1>Course content</h1>
      <p>Modules start hidden. Turn on “Visible to students” when a module is ready.</p>
      {error && <p role="alert" className="error">{error}</p>}
      <form
        className="item-form"
        onSubmit={async (e) => {
          e.preventDefault();
          await run(() => api(`/courses/${courseId}/modules`, session, { body: { title } }), "The module could not be added.");
          setTitle("");
        }}
      >
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New module title" maxLength={200} required aria-label="New module title" />
        <button className="primary">Add module</button>
      </form>
      {!content && !error && <p className="empty">Loading…</p>}
      {content?.modules.map((m, i) => (
        <ModuleCard key={m.id} module={m} courseId={courseId} session={session} run={run} first={i === 0} last={i === content.modules.length - 1} />
      ))}
    </article>
  );
}
