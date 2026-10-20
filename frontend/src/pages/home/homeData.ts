/** Content of the public page. The questions and misconceptions are copied from data/bank (items.json and
 *  misconceptions.json); the status rows follow docs/results/verification-status-2026-10-20.md. */

export type Option = { text: string; correct: boolean; misconception: string | null };
export type Question = { id: string; label: string; code: string; concept: string; options: Option[] };

export const MISCONCEPTIONS: Record<string, string> = {
  string_methods_in_place: "Believes string methods modify the string in place.",
  off_by_one_range: "Believes range(n) includes n or starts at 1.",
  counter_vs_sum: "Confuses the number of loop iterations with the accumulated total.",
  list_alias_copy: "Believes assigning a list to a new name copies it.",
};

export const QUESTIONS: Question[] = [
  {
    id: "upper",
    label: "Strings",
    code: 's = "hello"\ns.upper()\nprint(s)',
    concept: "strings",
    options: [
      { text: "hello", correct: true, misconception: null },
      { text: "HELLO", correct: false, misconception: "string_methods_in_place" },
      { text: "Hello", correct: false, misconception: "string_methods_in_place" },
      { text: "None", correct: false, misconception: "string_methods_in_place" },
    ],
  },
  {
    id: "range",
    label: "Loops",
    code: "total = 0\nfor i in range(4):\n    total += i\nprint(total)",
    concept: "loops",
    options: [
      { text: "6", correct: true, misconception: null },
      { text: "10", correct: false, misconception: "off_by_one_range" },
      { text: "3", correct: false, misconception: "off_by_one_range" },
      { text: "4", correct: false, misconception: "counter_vs_sum" },
    ],
  },
  {
    id: "alias",
    label: "Lists",
    code: "a = [1, 2]\nb = a\nb.append(3)\nprint(a)",
    concept: "lists",
    options: [
      { text: "[1, 2, 3]", correct: true, misconception: null },
      { text: "[1, 2]", correct: false, misconception: "list_alias_copy" },
      { text: "[3]", correct: false, misconception: "list_alias_copy" },
    ],
  },
];

/** Names shown in the blank of the headline, taken from the bank. */
export const HERO_NAMES = [
  "off by one range",
  "string methods in place",
  "list alias copy",
  "return vs print",
  "negative index confusion",
  "mutable default arg",
  "tuple mutable",
  "condition inverted",
];

export const CONCEPTS = [
  "variables and input",
  "conditionals",
  "loops",
  "strings",
  "lists",
  "tuples and sets",
  "dictionaries",
  "functions",
  "recursion",
  "comprehensions",
  "exceptions",
  "classes",
];

export const STAGES = [
  { name: "Run", time: "Under a second", grow: 1, text: "Your code runs in an isolated sandbox against the visible and the hidden tests." },
  {
    name: "Explain",
    time: "Up to fourteen seconds",
    grow: 14,
    text: "A model drafts an explanation from the failing test, your code and your instructor's notes.",
  },
  {
    name: "Check",
    time: "Before you see anything",
    grow: 2,
    text: "The cited test and line must exist, the concept must match, and no solution code or hidden test data may appear.",
  },
  { name: "Show", time: "Or a plain hint", grow: 2, text: "If a check fails once more, you get a plain hint built from the same evidence." },
];

export type Row = { title: string; text: string; image: string; alt: string; width: string; ratio: string };

export const ROWS: Row[] = [
  {
    title: "A starting point, not a grade",
    text: "Sixteen to twenty questions from your own course, mostly tracing code, then a few short tasks. Saying “I don't know” is allowed, and it tells the system something a lucky guess hides.",
    image: "/archive/hollerith-card.jpg",
    alt: "A Hollerith punched card from 1895 with rows of rectangular holes",
    width: "320px",
    ratio: "3 / 2",
  },
  {
    title: "Mastery you can audit",
    text: "Every concept has a value, how sure the system is, and when it was last assessed. Open a change to see the test, the error and the rule behind it. Only a logged rule changes it; the model never does.",
    image: "/archive/note-g.jpg",
    alt: "Ada Lovelace's 1842 table for computing Bernoulli numbers, the first published program",
    width: "240px",
    ratio: "4 / 5",
  },
  {
    title: "Hints, one step at a time",
    text: "A concept hint, then where to look, then a worked example on a different problem. Replies never contain the solution to your problem.",
    image: "/archive/ada-lovelace.jpg",
    alt: "Watercolour portrait of Ada Lovelace, about 1840",
    width: "180px",
    ratio: "1 / 1",
  },
  {
    title: "An assistant that shows its route",
    text: "Ask for a hint, an explanation, your progress or what to do next. You see which route answered and can change it.",
    image: "/archive/eniac.jpg",
    alt: "Two women operating the ENIAC computer in 1946",
    width: "300px",
    ratio: "3 / 2",
  },
];

export type StatusRow = { who: string; what: string; status: string };

export const STATUS: StatusRow[] = [
  { who: "Students", what: "Placement test, sandbox runs, checked explanations, hints, mastery with its ledger, assistant", status: "Live" },
  { who: "Students", what: "Quizzes, handed-in work with rubrics, to-do list, calendar, in-app notifications", status: "Live" },
  { who: "Instructors", what: "Class heatmap, alerts with the facts behind them, grading, gradebook with weighted categories", status: "Live" },
  { who: "Instructors", what: "Course notes, lessons, problem editor checked in the sandbox, review of stored explanations", status: "Live" },
  { who: "Admins", what: "Users, roles, password resets, deletion on request with 48 hours' notice", status: "Live" },
  { who: "Everyone", what: "Launch from Moodle and grades sent back", status: "Tested on Moodle only" },
  { who: "Everyone", what: "A pilot with real students", status: "Not yet" },
  { who: "Everyone", what: "People rating the explanations", status: "Not yet" },
  { who: "Everyone", what: "Email notifications, discussion forums, Canvas, C and Java", status: "Not yet" },
];

export const FAQ: [string, string][] = [
  ["Does it give me the answer?", "No. Hints go one step at a time and replies never contain the full solution to your problem."],
  [
    "Is the AI always right?",
    "No. An explanation is checked against the run result before you see it, and when a check fails you get a plain hint. In a recent test with simulated students most explanations ended as plain hints, which we are working on.",
  ],
  [
    "Where does my code go?",
    "To the isolated sandbox and, for explanations, to the model provider named in the privacy notice you agree to before you start.",
  ],
  [
    "Who can see my code and chat?",
    "You and your course's teachers can see your submissions and code, and each view by a teacher is logged. Your chat messages are not shown to teachers.",
  ],
  [
    "Can I use it from Moodle?",
    "A course can launch it through LTI 1.3 and send scores back. This was tested on Moodle 5.3 only; Canvas has not been tested.",
  ],
  [
    "Can I delete my data?",
    "Yes. You can request deletion from your account. It runs after 48 hours so you can cancel, and it removes your submissions, chat and mastery.",
  ],
];
