export type Role = "student" | "instructor" | "admin";

export type Session = { token: string; role: Role };

export type Course = { id: number; title: string; instructor_id: number; enrolled: boolean };

export type ConceptTag = { concept_id: number; name: string; weight: number };

export type Problem = {
  id: number;
  course_id: number;
  title: string;
  statement: string;
  kind: "code" | "mcq";
  review_status: "needs human review" | "reviewed";
  concepts: ConceptTag[];
};

export type ProblemDetail = Problem & { examples: { input: string; expected: string }[] };

export type VisibleTest = {
  input: string;
  expected: string;
  actual: string;
  passed: boolean;
  status: string;
};

export type SubmissionResult = {
  submission_id: number | null;
  status: "passed" | "failed" | "error";
  passed: number;
  failed: number;
  error_type: string | null;
  failed_categories: string[];
  runtime_ms: number;
  visible_tests: VisibleTest[];
};

const KEY = "lms.session";

export function loadSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session | null): void {
  try {
    if (session) sessionStorage.setItem(KEY, JSON.stringify(session));
    else sessionStorage.removeItem(KEY);
  } catch {
    // Storage can be blocked; the session then lasts until the page is reloaded.
  }
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  session: Session | null,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: init.method ?? (init.body ? "POST" : "GET"),
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
    },
    body: init.body ? JSON.stringify(init.body) : undefined,
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = data?.error?.message ?? `Request failed (${response.status})`;
    throw new ApiError(response.status, typeof message === "string" ? message : "Request failed");
  }
  return data as T;
}
