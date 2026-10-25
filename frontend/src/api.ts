export type Role = "student" | "instructor" | "admin";

export type Session = { token: string; role: Role };

export type Course = {
  id: number;
  title: string;
  instructor_id: number;
  enrolled: boolean;
  archived?: boolean;
  section?: string | null;
  subject?: string | null;
  color?: string | null;
  language?: string;
};

export type ConceptTag = { concept_id: number; name: string; weight: number };

export type Problem = {
  id: number;
  course_id: number;
  title: string;
  statement: string;
  language?: string;
  kind: "code" | "mcq";
  review_status: "needs human review" | "reviewed";
  concepts: ConceptTag[];
  archived?: boolean;
  my_status?: "solved" | "tried" | "new" | null;
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
export const DRAFT_PREFIX = "lms.draft.";

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
    else {
      sessionStorage.removeItem(KEY);
      // the next person on this browser must not see this student's unsent code
      Object.keys(sessionStorage)
        .filter((k) => k.startsWith(DRAFT_PREFIX))
        .forEach((k) => sessionStorage.removeItem(k));
    }
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

export const BUSY_RETRIES = 3;

/** A 503 with Retry-After means the sandbox queue is full and the request was not started, so it is safe to repeat. */
export async function api<T>(
  path: string,
  session: Session | null,
  init: { method?: string; body?: unknown; onBusy?: (attempt: number) => void } = {},
): Promise<T> {
  let response: Response;
  for (let attempt = 1; ; attempt++) {
    response = await fetch(`/api/v1${path}`, {
      method: init.method ?? (init.body ? "POST" : "GET"),
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
      },
      body: init.body ? JSON.stringify(init.body) : undefined,
    });
    const retryAfter = Number(response.headers.get("Retry-After"));
    if (response.status !== 503 || !retryAfter || attempt > BUSY_RETRIES) break;
    init.onBusy?.(attempt);
    await new Promise((resolve) => setTimeout(resolve, retryAfter * 1000));
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = data?.error?.message ?? `Request failed (${response.status})`;
    throw new ApiError(response.status, typeof message === "string" ? message : "Request failed");
  }
  return data as T;
}
