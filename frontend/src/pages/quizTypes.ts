export type QuestionKind = "single" | "multiple" | "short";

export const KIND_TEXT: Record<QuestionKind, string> = {
  single: "One right answer",
  multiple: "Several right answers",
  short: "Short answer",
};

export type Question = {
  id: number;
  kind: QuestionKind;
  prompt: string;
  options: string[];
  weight: number;
  correct_choices: number[] | null;
  accepted: string[] | null;
};

export type QuizSummary = {
  id: number;
  title: string;
  max_attempts: number;
  show_answers: boolean;
  published: boolean;
  questions: number;
  in_assignments: number;
  attempts_used: number | null;
  best_fraction: number | null;
};

export type Quiz = QuizSummary & { question_list: Question[] };

export type ReviewItem = { question_id: number; correct: boolean; correct_choices: number[] | null; accepted: string[] | null };

export type AttemptResult = {
  attempt_id: number;
  attempt_number: number;
  attempts_left: number;
  earned: number;
  possible: number;
  fraction: number;
  review: ReviewItem[] | null;
};

export type MyAttempts = {
  attempts: { id: number; number: number; fraction: number; submitted_at: string }[];
  attempts_left: number;
  review: ReviewItem[] | null;
};
