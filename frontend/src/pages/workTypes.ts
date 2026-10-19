import { ApiError, Session } from "../api";
import type { Rubric } from "./RubricsPage";

export type Comment = { id: number; from_teacher: boolean; mine: boolean; body: string; created_at: string };

export type MyWork = {
  assignment_id: number;
  title: string;
  due_at: string;
  instructions: string;
  points: number;
  allow_file: boolean;
  allow_link: boolean;
  allow_text: boolean;
  state: "assigned" | "missing" | "turned_in" | "returned";
  late: boolean;
  text: string | null;
  link: string | null;
  file_name: string | null;
  file_size: number | null;
  turned_in_at: string | null;
  score: number | null;
  feedback: string | null;
  returned_at: string | null;
  comments: Comment[];
  rubric: Rubric | null;
};

export type WorkState = "assigned" | "missing" | "turned_in" | "graded" | "returned";

export const WORK_STATE_TEXT: Record<WorkState, string> = {
  assigned: "Assigned",
  missing: "Missing",
  turned_in: "Turned in",
  graded: "Graded, not returned",
  returned: "Returned",
};

export type WorkRow = { student_id: number; label: string; synthetic: boolean; state: WorkState; late: boolean; turned_in_at: string | null; score: number | null };
export type WorkList = { assignment_id: number; title: string; due_at: string; points: number; rows: WorkRow[] };

export type TheirWork = {
  student_id: number;
  label: string;
  title: string;
  due_at: string;
  instructions: string;
  points: number;
  state: WorkState;
  late: boolean;
  text: string | null;
  link: string | null;
  file_name: string | null;
  file_size: number | null;
  turned_in_at: string | null;
  score: number | null;
  feedback: string | null;
  graded_at: string | null;
  returned_at: string | null;
  comments: Comment[];
  rubric: Rubric | null;
};

export type ReviewGroup = {
  course_id: number;
  course_title: string;
  assignment_id: number;
  title: string;
  due_at: string;
  waiting: number;
  graded: number;
  not_returned: number;
};

export const MAX_FILE_BYTES = 4_500_000;

export const toBase64 = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });

/** Saves a handed-in file. The request carries the sign-in token, so it is fetched and then handed to the browser. */
export async function downloadWorkFile(session: Session, path: string, name: string): Promise<void> {
  const response = await fetch(`/api/v1${path}`, { headers: { Authorization: `Bearer ${session.token}` } });
  if (!response.ok) throw new ApiError(response.status, `Download failed (${response.status})`);
  const url = URL.createObjectURL(await response.blob());
  Object.assign(document.createElement("a"), { href: url, download: name }).click();
  URL.revokeObjectURL(url);
}

export const sizeText = (bytes: number) => (bytes >= 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1000))} KB`);
