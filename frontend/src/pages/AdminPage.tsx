import { FormEvent, useEffect, useState } from "react";

import { ApiError, Role, Session, api } from "../api";

type User = {
  id: number;
  email: string;
  role: Role;
  display_name: string | null;
  disabled: boolean;
  must_change_password: boolean;
  opened_from_lms: boolean;
  created_at: string;
};
type Temporary = { user: User; temporary_password: string };

/** F-01: admins find people, create staff, reset passwords, disable accounts and change roles. */
export function AdminPage({ session, myId }: { session: Session; myId: number }) {
  const [users, setUsers] = useState<User[] | null>(null);
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<"instructor" | "admin">("instructor");
  const [name, setName] = useState("");
  const [temporary, setTemporary] = useState<Temporary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    const params = new URLSearchParams({ q: query, ...(role ? { role } : {}) });
    return api<User[]>(`/admin/users?${params}`, session)
      .then(setUsers)
      .catch((e: Error) => setError(e.message));
  };

  useEffect(() => {
    load();
  }, []);

  async function run<T>(call: () => Promise<T>, after?: (result: T) => void) {
    setError(null);
    try {
      const result = await call();
      after?.(result);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The change could not be made.");
    }
  }

  const search = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    load();
  };

  const create = (event: FormEvent) => {
    event.preventDefault();
    run(
      () => api<Temporary>("/admin/users", session, { body: { email, role: newRole, display_name: name.trim() || null } }),
      (made) => {
        setTemporary(made);
        setEmail("");
        setName("");
      },
    );
  };

  return (
    <>
      <h1>Users</h1>
      {error && <p role="alert" className="error">{error}</p>}
      {temporary && (
        <div className="notice" role="status">
          <p>
            Temporary password for <strong>{temporary.user.email}</strong>: <code className="secret">{temporary.temporary_password}</code>
          </p>
          <p>
            It is shown only now. Pass it on in person; they must choose their own password when they first sign in.{" "}
            <button className="link" onClick={() => setTemporary(null)}>
              Hide
            </button>
          </p>
        </div>
      )}

      <form className="stack" onSubmit={create}>
        <fieldset>
          <legend>Add a staff account</legend>
          <label>
            Email
            <input type="email" value={email} required onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>
            Name (optional)
            <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Role
            <select value={newRole} onChange={(e) => setNewRole(e.target.value as "instructor" | "admin")}>
              <option value="instructor">instructor</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <p>
            <button className="primary" type="submit">
              Create account
            </button>
          </p>
        </fieldset>
      </form>

      <form className="inline-form" onSubmit={search}>
        <label>
          Search email or name
          <input value={query} maxLength={100} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <label>
          Role
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">any</option>
            <option value="student">student</option>
            <option value="instructor">instructor</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <button type="submit">Search</button>
      </form>

      {users && users.length === 0 && <p className="empty">Nobody matches.</p>}
      <ul className="rows users">
        {users?.map((u) => (
          <li key={u.id}>
            <span className="grow">
              <strong>{u.display_name ?? u.email}</strong>
              <br />
              <small>
                {u.display_name ? `${u.email} · ` : ""}
                {u.opened_from_lms ? "opened from the LMS" : `since ${new Date(u.created_at).toLocaleDateString()}`}
              </small>
            </span>
            {u.disabled && <span className="flag">disabled</span>}
            {u.must_change_password && <span className="tag">new password due</span>}
            {u.id === myId ? (
              <span className="tag">you</span>
            ) : (
              <span className="row-actions">
                <label className="inline">
                  <span className="visually-hidden">Role of {u.email}</span>
                  <select
                    value={u.role}
                    disabled={u.opened_from_lms}
                    onChange={(e) => run(() => api(`/admin/users/${u.id}/role`, session, { method: "PATCH", body: { role: e.target.value } }))}
                  >
                    <option value="student">student</option>
                    <option value="instructor">instructor</option>
                    <option value="admin">admin</option>
                  </select>
                </label>
                {!u.opened_from_lms && (
                  <button
                    className="link"
                    aria-label={`Reset the password of ${u.email}`}
                    onClick={() => {
                      if (window.confirm(`Reset the password of ${u.email}? Their sessions end and they need the temporary password.`))
                        run(() => api<Temporary>(`/admin/users/${u.id}/reset-password`, session, { method: "POST" }), setTemporary);
                    }}
                  >
                    Reset password
                  </button>
                )}
                <button
                  className="link"
                  aria-label={`${u.disabled ? "Enable" : "Disable"} ${u.email}`}
                  onClick={() => run(() => api(`/admin/users/${u.id}/${u.disabled ? "enable" : "disable"}`, session, { method: "POST" }))}
                >
                  {u.disabled ? "Enable" : "Disable"}
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
      <small>Shows the newest 200 matches. Synthetic demo students are left out.</small>
    </>
  );
}
