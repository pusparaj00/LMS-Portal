import { ReactNode, useState } from "react";

import { ThemeToggle } from "../design/ThemeToggle";
import {
  ChatSample,
  HintLadder,
  LedgerSample,
  QuestionCard,
  prefersReducedMotion,
  Replay,
  ResultSample,
  TestResults,
  VerifiedExplanation,
} from "./HomePreviews";

const ANCHORS = [
  { id: "features", label: "Features" },
  { id: "walkthroughs", label: "Walkthroughs" },
  { id: "roles", label: "Roles" },
  { id: "status", label: "Status" },
  { id: "faq", label: "FAQ" },
];

function scrollToSection(id: string) {
  const section = document.getElementById(id);
  if (!section) return;
  section.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth" });
  section.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true });
}

/** Anchor links on the public page cannot use plain "#id" hrefs, because the app routes on the hash. */
function SectionLink({ id, children }: { id: string; children: ReactNode }) {
  return (
    <a
      href={`#/${id}`}
      onClick={(e) => {
        e.preventDefault();
        scrollToSection(id);
      }}
    >
      {children}
    </a>
  );
}

/** Top bar of the public layout. Log in sits top-left at every width (ux-plan 4.0). */
export function PublicBar({ dashboardHref }: { dashboardHref?: string }) {
  return (
    <header className="pubbar">
      {dashboardHref ? (
        <a className="button primary" href={dashboardHref}>
          Open dashboard
        </a>
      ) : (
        <a className="button primary" href="#/login">
          Log in
        </a>
      )}
      <a className="pubbrand" href={dashboardHref ? "#/home" : "#/"}>
        Adaptive LMS
      </a>
      <nav className="pubnav" aria-label="Sections">
        {ANCHORS.map((a) => (
          <SectionLink key={a.id} id={a.id}>
            {a.label}
          </SectionLink>
        ))}
      </nav>
      <details className="pubmenu">
        <summary>Menu</summary>
        <div>
          {ANCHORS.map((a) => (
            <SectionLink key={a.id} id={a.id}>
              {a.label}
            </SectionLink>
          ))}
          <ThemeToggle />
        </div>
      </details>
      {!dashboardHref && (
        <a className="button" href="#/register">
          Create account
        </a>
      )}
    </header>
  );
}

const FEATURES: { title: string; text: string; preview: ReactNode }[] = [
  {
    title: "Placement test",
    text: "Up to 10 questions that adapt to your answers and stop early once there is enough to go on. Some wrong answers point to a specific misunderstanding.",
    preview: <QuestionCard />,
  },
  {
    title: "Run with evidence",
    text: "Your code runs in an isolated runner against the course tests. You see which passed, which failed and why. Hidden tests show their category, never their inputs.",
    preview: <TestResults />,
  },
  {
    title: "Checked explanations",
    text: "When a submission fails, the explanation is built from the failing test, your code and your instructor's notes, then checked against the run result before you see it. If it cannot be checked, you get a plain hint.",
    preview: <VerifiedExplanation />,
  },
  {
    title: "Hints, one step at a time",
    text: "A concept hint, then where to look, then a worked example on a different problem. Replies never contain the full solution.",
    preview: <HintLadder />,
  },
  {
    title: "Mastery you can audit",
    text: "Every concept has a value that changes after each answer. Open any change to see the test, the error and the rule behind it.",
    preview: <LedgerSample />,
  },
  {
    title: "An assistant that routes",
    text: "Ask for a hint, an explanation or a progress summary. You see which route answered and can change it.",
    preview: <ChatSample />,
  },
];

function Features() {
  const [selected, setSelected] = useState(0);
  return (
    <section id="features" className="band" aria-labelledby="features-h">
      <p className="label">//what it does</p>
      <h2 id="features-h" tabIndex={-1}>
        what you get when you practise here.
      </h2>
      <div className="features">
        <div role="tablist" aria-label="Features" aria-orientation="vertical" className="feature-list">
          {FEATURES.map((f, i) => (
            <button
              key={f.title}
              role="tab"
              id={`feature-tab-${i}`}
              aria-selected={selected === i}
              aria-controls="feature-panel"
              tabIndex={selected === i ? 0 : -1}
              onClick={() => setSelected(i)}
              onKeyDown={(e) => {
                const delta = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
                if (!delta) return;
                e.preventDefault();
                const next = (i + delta + FEATURES.length) % FEATURES.length;
                setSelected(next);
                document.getElementById(`feature-tab-${next}`)?.focus();
              }}
            >
              <span className="feature-no">{String(i + 1).padStart(2, "0")}</span> {f.title}
            </button>
          ))}
        </div>
        <div role="tabpanel" id="feature-panel" aria-labelledby={`feature-tab-${selected}`} className="feature-pane">
          <p className="pane-text">{FEATURES[selected].text}</p>
          <div className="pane-preview">
            <span className="terminal-tag">Sample data</span>
            {FEATURES[selected].preview}
          </div>
        </div>
      </div>
    </section>
  );
}

type Step = { title: string; text: string; preview: ReactNode };

const WALKTHROUGHS: { tab: string; steps: Step[] }[] = [
  {
    tab: "Take the placement test",
    steps: [
      { title: "One question at a time", text: "Each screen shows one item. The test says “up to 10” because it can stop early.", preview: <QuestionCard /> },
      { title: "A wrong answer can point to a misunderstanding", text: "Some wrong options map to a specific misunderstanding, such as an off-by-one in loop bounds. The result lists the likely ones and the answer each came from.", preview: <ResultSample /> },
      { title: "A starting point, not a grade", text: "Every concept gets a value and a label. Estimates sharpen as you solve problems.", preview: <ResultSample /> },
    ],
  },
  {
    tab: "A failed submission, explained",
    steps: [
      { title: "Tests first", text: "The result lists each test. For hidden tests you see the category only, never the input or the expected output.", preview: <TestResults /> },
      { title: "The work is shown", text: "The activity log lists what ran, what was read and which checks passed. Each row opens its detail.", preview: <VerifiedExplanation /> },
      { title: "Hints stay available", text: "If an explanation cannot be checked, you get a plain hint, and the next hint is one click away.", preview: <HintLadder /> },
    ],
  },
  {
    tab: "Why did my mastery change?",
    steps: [
      { title: "The value moves", text: "After a submission or a probe answer, the strip shows the old and new value.", preview: <LedgerSample /> },
      { title: "The ledger gives the reason", text: "Each change lists the evidence and the fixed rule that applied. Only a logged rule changes a value, never the AI.", preview: <LedgerSample /> },
      { title: "Ask about it", text: "In the assistant you can ask for a progress summary and see which route answered.", preview: <ChatSample /> },
    ],
  },
];

function Walkthroughs() {
  const [tab, setTab] = useState(0);
  const [step, setStep] = useState(0);
  const steps = WALKTHROUGHS[tab].steps;
  const current = steps[step];
  return (
    <section id="walkthroughs" className="band" aria-labelledby="walk-h">
      <p className="label">//take a closer look</p>
      <h2 id="walk-h" tabIndex={-1}>
        step through it.
      </h2>
      <div role="tablist" aria-label="Walkthroughs" className="tabs">
        {WALKTHROUGHS.map((w, i) => (
          <button
            key={w.tab}
            role="tab"
            aria-selected={tab === i}
            onClick={() => {
              setTab(i);
              setStep(0);
            }}
          >
            {w.tab}
          </button>
        ))}
      </div>
      <div className="walk" role="tabpanel" aria-label={WALKTHROUGHS[tab].tab}>
        <div className="walk-text">
          <p className="walk-count">
            Step {step + 1} of {steps.length}
          </p>
          <h3>{current.title}</h3>
          <p>{current.text}</p>
          <div className="walk-buttons">
            <button type="button" onClick={() => setStep(step - 1)} disabled={step === 0}>
              Back
            </button>
            <button type="button" onClick={() => setStep(step + 1)} disabled={step === steps.length - 1}>
              Next
            </button>
          </div>
        </div>
        <div className="pane-preview">
          <span className="terminal-tag">Sample data</span>
          {current.preview}
        </div>
      </div>
    </section>
  );
}

function Comparison() {
  return (
    <section className="band" aria-labelledby="why-h">
      <p className="label">//why checks matter</p>
      <h2 id="why-h" tabIndex={-1}>
        stop guessing why your code failed.
      </h2>
      <p className="reading">
        An explanation is only useful if it matches what actually ran. Here is the same failed submission with and
        without checks.
      </p>
      <div className="compare">
        <div className="compare-side">
          <p className="terminal-tag">Illustration · without checks</p>
          <p>
            Your <code>while</code> loop on line 14 never ends, so the program times out.
          </p>
          <p className="muted">The code has no line 14, and the failing test was empty_input.</p>
        </div>
        <div className="compare-side compare-checked">
          <p className="terminal-tag">Illustration · with checks</p>
          <p>
            <span className="badge badge-verified">Verified · 6 of 6</span>
          </p>
          <p>
            Your loop reads <code>xs[0]</code> before it checks that the list has items.
          </p>
          <p className="sources">
            <span className="evidence">test: empty_input</span> <span className="evidence">line 3</span>{" "}
            <span className="evidence">notes: lists.md</span>
          </p>
        </div>
      </div>
    </section>
  );
}

const ROLES = [
  {
    name: "Students",
    items: [
      "See what you know and what to do next.",
      "Get unstuck without being handed the answer.",
      "Ask for hints, explanations or a progress summary.",
    ],
  },
  {
    name: "Instructors",
    items: [
      "See where the class struggles on a heatmap and a list of common misunderstandings.",
      "Upload the notes explanations draw on.",
      "Review stored explanations and make the checks stricter per problem.",
    ],
  },
  {
    name: "Administrators",
    items: [
      "Manage users and roles.",
      "Disable accounts and reset passwords.",
      "Create staff accounts with a temporary password.",
    ],
  },
];

function Roles() {
  const [tab, setTab] = useState(0);
  return (
    <section id="roles" className="band" aria-labelledby="roles-h">
      <p className="label">//for your role</p>
      <h2 id="roles-h" tabIndex={-1}>
        one app, three views.
      </h2>
      <div role="tablist" aria-label="Roles" className="tabs">
        {ROLES.map((r, i) => (
          <button key={r.name} role="tab" aria-selected={tab === i} onClick={() => setTab(i)}>
            {r.name}
          </button>
        ))}
      </div>
      <ul className="plain" role="tabpanel" aria-label={ROLES[tab].name}>
        {ROLES[tab].items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function WillNot() {
  return (
    <section className="band" aria-labelledby="not-h">
      <p className="label">//what it will not do</p>
      <h2 id="not-h" tabIndex={-1}>
        limits we keep on purpose.
      </h2>
      <ul className="plain">
        <li>Give you the full solution.</li>
        <li>Show an explanation that failed its checks.</li>
        <li>Let the AI change your mastery value. Only a fixed, logged rule does.</li>
        <li>Run your code anywhere except the isolated runner.</li>
      </ul>
    </section>
  );
}

type Status = "Live now" | "Preview" | "Planned";

/** Mirrors docs/results/gap-report.md. Add a row here only when that report says so. */
const STATUS_ROWS: [string, Status, string][] = [
  ["Placement test with likely misunderstandings", "Live now", "Student"],
  ["Run code against tests in an isolated runner", "Live now", "Student"],
  ["Checked explanations with a plain-hint fallback", "Live now", "Student"],
  ["Hint ladder and a quick check after a failure", "Live now", "Student"],
  ["Mastery dashboard with a ledger of every change", "Live now", "Student"],
  ["Assistant that routes questions", "Live now", "Student"],
  ["Class heatmap, misconceptions and student drill-down", "Live now", "Instructor"],
  ["Course notes upload (text, Markdown, PDF)", "Live now", "Instructor"],
  ["Problem editor with sandbox validation", "Live now", "Instructor"],
  ["Review of stored explanations", "Live now", "Instructor"],
  ["Assignments, gradebook and announcements", "Live now", "Instructor"],
  ["Users, roles and password resets", "Live now", "Administrator"],
  ["Launch from Moodle and grade passback (LTI 1.3, tested on a local Moodle 5.3)", "Live now", "All"],
  ["Admin pages for model and runner settings", "Planned", "Administrator"],
  ["Roster sync and deep linking from an LMS", "Planned", "All"],
  ["C and Java courses", "Planned", "All"],
  ["Full run on a local model", "Planned", "All"],
];

const GATES = [
  ["G0 Foundation", "Passed"],
  ["G1 Execution core", "Passed"],
  ["G2 Diagnostic and mastery", "Passed with a caveat"],
  ["G3 Verified feedback", "Passed"],
  ["G4 Router and dashboards", "Passed"],
  ["G5 Integration and demo", "Technical part passed; recording, report and IPR conversation open"],
];

function StatusSection() {
  return (
    <section id="status" className="band" aria-labelledby="status-h">
      <p className="label">//status</p>
      <h2 id="status-h" tabIndex={-1}>
        what works today.
      </h2>
      <div className="table-wrap">
        <table className="status-table">
          <thead>
            <tr>
              <th scope="col">Feature</th>
              <th scope="col">Who</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {STATUS_ROWS.map(([feature, status, who]) => (
              <tr key={feature}>
                <td>{feature}</td>
                <td>{who}</td>
                <td>
                  <span className={`badge badge-${status === "Live now" ? "verified" : "plain"}`}>{status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Build log</h3>
      <ul className="plain">
        {GATES.map(([gate, result]) => (
          <li key={gate}>
            <strong>{gate}:</strong> {result}
          </li>
        ))}
      </ul>
      <p className="muted">
        This is a prototype built for a course review. Everything above comes from measured results in the project
        repository; nothing on this page is a claim about learning outcomes.
      </p>
    </section>
  );
}

const FAQ: [string, string][] = [
  ["Does it give me the answer?", "No. Hints go one step at a time, and replies never contain a full solution."],
  [
    "Can I use it with Moodle or Canvas?",
    "A course can launch it from an LMS that supports LTI 1.3, and scores can be sent back. This was tested on a local Moodle 5.3. Canvas has not been tested.",
  ],
  [
    "Where does my code go?",
    "To the isolated runner and, for explanations, to the configured AI model. A privacy notice states which provider before you start.",
  ],
  ["Is the AI always right?", "No. Explanations are checked against the run result and fall back to a plain hint when they fail."],
  [
    "Who can see my code and chat?",
    "You and your course's teacher can see your submissions and code. Your chat messages are not shown to teachers.",
  ],
];

function Faq() {
  return (
    <section id="faq" className="band" aria-labelledby="faq-h">
      <p className="label">//faq</p>
      <h2 id="faq-h" tabIndex={-1}>
        questions people ask.
      </h2>
      {FAQ.map(([q, a]) => (
        <details key={q} className="faq">
          <summary>{q}</summary>
          <p>{a}</p>
        </details>
      ))}
    </section>
  );
}

export function HomePage({ dashboardHref }: { dashboardHref?: string }) {
  return (
    <div className="pub">
      <a
        className="skip"
        href="#/"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("content")?.focus();
        }}
      >
        Skip to content
      </a>
      <PublicBar dashboardHref={dashboardHref} />
      <p className="statusstrip">
        Placement test and checked explanations are live. <SectionLink id="status">See status</SectionLink>
      </p>
      <main id="content" tabIndex={-1} className="pubmain">
        <section className="hero" aria-labelledby="hero-h">
          <div className="hero-text">
            <h1 id="hero-h">programming practice that shows you what to fix next.</h1>
            <p className="reading">
              Run your code, see which tests failed, and get an explanation checked against the test result and your
              course notes. Mastery of every concept updates after each submission.
            </p>
            <div className="hero-actions">
              {!dashboardHref && (
                <a className="button primary" href="#/register">
                  Create account
                </a>
              )}
              <a
                className="button"
                href="#/walkthroughs"
                onClick={(e) => {
                  e.preventDefault();
                  scrollToSection("walkthroughs");
                }}
              >
                See how it works
              </a>
            </div>
          </div>
          <Replay />
        </section>
        <Features />
        <Walkthroughs />
        <Comparison />
        <Roles />
        <WillNot />
        <section className="band" aria-labelledby="courses-h">
          <p className="label">//courses</p>
          <h2 id="courses-h" tabIndex={-1}>
            what you can study.
          </h2>
          <div className="course-cards">
            <div className="course-card">
              <h3>Python 101</h3>
              <p>Open now.</p>
              {!dashboardHref && (
                <a className="button" href="#/register">
                  Create account to enrol
                </a>
              )}
            </div>
            <div className="course-card muted-card">
              <h3>C</h3>
              <span className="badge badge-plain">Planned</span>
            </div>
            <div className="course-card muted-card">
              <h3>Java</h3>
              <span className="badge badge-plain">Planned</span>
            </div>
          </div>
        </section>
        <StatusSection />
        <Faq />
        <section className="closing" aria-labelledby="closing-h">
          <h2 id="closing-h" tabIndex={-1}>
            find your starting point.
          </h2>
          {dashboardHref ? (
            <a className="button primary" href={dashboardHref}>
              Open dashboard
            </a>
          ) : (
            <div className="hero-actions">
              <a className="button primary" href="#/register">
                Create account
              </a>
              <a className="button" href="#/login">
                Log in
              </a>
            </div>
          )}
        </section>
      </main>
      <footer className="pubfooter">
        <div className="footgrid">
          <div>
            <p className="label">//product</p>
            <ul className="plain">
              {ANCHORS.filter((a) => a.id !== "roles" && a.id !== "faq").map((a) => (
                <li key={a.id}>
                  <SectionLink id={a.id}>{a.label}</SectionLink>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="label">//account</p>
            <ul className="plain">
              <li>
                <a href="#/login">Log in</a>
              </li>
              <li>
                <a href="#/register">Create account</a>
              </li>
            </ul>
          </div>
          <div>
            <p className="label">//display</p>
            <ThemeToggle />
          </div>
        </div>
        <p className="muted">A prototype built for the course review.</p>
      </footer>
    </div>
  );
}
