import { Status } from "./AssignmentsPage";

export type Upcoming = {
  assignment_id: number;
  course_id: number;
  course_title: string;
  title: string;
  due_at: string;
  status: Status | null;
  students_complete: number | null;
  students: number | null;
};

export type StudentStats = {
  enrolled_courses: number;
  average_percent: number | null;
  assignments_complete: number;
  assignments_total: number;
  courses: {
    course_id: number;
    title: string;
    assignments: number;
    completed: number;
    score: number;
    possible: number;
    percent: number | null;
    next_due_at: string | null;
    content_done: number;
    content_total: number;
  }[];
  upcoming: Upcoming[];
};

export type CourseGrades = {
  course_id: number;
  title: string;
  score: number;
  possible: number;
  percent: number | null;
  assignments: {
    assignment_id: number;
    title: string;
    due_at: string;
    score: number;
    with_late: number;
    possible: number;
    status: Status;
  }[];
};

export type InstructorStats = {
  courses: number;
  students: number;
  upcoming_assignments: number;
  submissions_7d: number;
  course_stats: {
    course_id: number;
    title: string;
    students: number;
    assignments: number;
    submissions_7d: number;
    completion_rate: number | null;
    rating_count: number;
    average_course_rating: number | null;
  }[];
  upcoming: Upcoming[];
};

export type RatingSummary = { count: number; average_course: number | null; average_instructor: number | null };
export type Rating = { course_rating: number; instructor_rating: number; review: string | null; created_at: string };
export type CourseRatings = { summary: RatingSummary; mine: Rating | null; reviews: Rating[] };

export type CourseAnalytics = {
  course_id: number;
  title: string;
  students: number;
  assignments: number;
  submissions_total: number;
  submissions_7d: number;
  completion_rate: number | null;
  average_percent: number | null;
  distribution: { label: string; students: number }[];
  per_assignment: {
    assignment_id: number;
    title: string;
    due_at: string;
    complete: number;
    in_progress: number;
    late: number;
    missing: number;
    not_started: number;
  }[];
  ratings: RatingSummary;
};

export const percent = (value: number | null) => (value === null ? "No data yet" : `${Math.round(value)}%`);
export const average = (value: number | null) => (value === null ? "No ratings" : `${value.toFixed(1)} / 5`);
