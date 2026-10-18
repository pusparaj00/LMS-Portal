import { useEffect, useState } from "react";

import { ActivityLog, LogRow } from "../design/ActivityLog";
import { EvidenceChip } from "../design/EvidenceChip";
import { MasteryStrip } from "../design/MasteryStrip";
import { TerminalWindow } from "../design/TerminalWindow";

/* Everything here is fixed sample data. The public page never calls the API (ux-plan 4.0, rule 3). */

export function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export const SAMPLE_LOG: LogRow[] = [
  { verb: "Ran", text: "5 tests · 3 passed · 2 failed" },
  { verb: "Read", text: "notes: lists.md, slicing (chunk 12)" },
  { verb: "Drafted", text: "explanation, attempt 1" },
  { verb: "Checked", text: "failing test, line, concept, sources, leak guard: 6 of 6" },
  { verb: "Updated", text: "Loops 0.62 → 0.55 (ledger)" },
];

const REPLAY_STEPS = 7;
const REPLAY_STEP_MS = 900;

export const REPLAY_TRANSCRIPT =
  "A student submits reverse_list.py. Five tests run: three pass and two fail, including a hidden test named " +
  "empty_input that raised an IndexError. The student asks for an explanation. The system reads the lists notes, " +
  "drafts an explanation, checks it against the failing test, the line, the concept and the sources, and passes " +
  "six of six checks. The Loops mastery value then moves from 0.62 to 0.55.";

/** The hero: one failed submission, played once, with Pause and Replay. The last frame is shown for reduced motion. */
export function Replay() {
  const [step, setStep] = useState(() => (prefersReducedMotion() ? REPLAY_STEPS : 0));
  const [paused, setPaused] = useState(false);
  const [run, setRun] = useState(0);

  useEffect(() => {
    if (paused || step >= REPLAY_STEPS) return;
    const timer = window.setTimeout(() => setStep((s) => s + 1), REPLAY_STEP_MS);
    return () => window.clearTimeout(timer);
  }, [step, paused, run]);

  const done = step >= REPLAY_STEPS;
  const shownRows = Math.max(0, Math.min(SAMPLE_LOG.length, step - 2));
  return (
    <div className="replay">
      <TerminalWindow title="~/python-101  reverse_list.py" tag="Sample data">
        <div className="replay-lines" aria-hidden={!done}>
          {step >= 1 && <p className="cmd">&gt; submit</p>}
          {step >= 1 && <p>ran 5 tests · 3 passed · 2 failed</p>}
          {step >= 2 && (
            <p className="fail-line">
              ✗ <EvidenceChip>empty_input</EvidenceChip> hidden test · IndexError
            </p>
          )}
          {step >= 3 && <p className="cmd">&gt; explain</p>}
          {shownRows > 0 && <ActivityLog rows={SAMPLE_LOG.slice(0, shownRows)} open />}
          {step >= REPLAY_STEPS - 1 && (
            <MasteryStrip name="Loops" value={step >= REPLAY_STEPS ? 0.55 : 0.62} delta={{ from: 0.62, to: 0.55 }} />
          )}
        </div>
      </TerminalWindow>
      <div className="replay-controls">
        <button type="button" className="ghost" onClick={() => setPaused((p) => !p)} disabled={done}>
          {paused ? "Resume" : "Pause"}
        </button>
        <button
          type="button"
          className="ghost"
          onClick={() => {
            setStep(0);
            setPaused(false);
            setRun((r) => r + 1);
          }}
        >
          Replay
        </button>
        <span className="sr-only" role="status">
          {done ? "Replay finished." : ""}
        </span>
      </div>
      <details className="transcript">
        <summary>Text version of the replay</summary>
        <p>{REPLAY_TRANSCRIPT}</p>
      </details>
    </div>
  );
}

export function QuestionCard() {
  return (
    <div className="sample">
      <p className="sample-q">Question 4 of up to 10 · What does this code print?</p>
      <pre className="code">{`for i in range(1, 4):\n    print(i)`}</pre>
      <ul className="options">
        {["1 2 3", "1 2 3 4", "0 1 2 3", "1 2"].map((o, i) => (
          <li key={o}>
            <label>
              <input type="radio" name="sample-option" disabled defaultChecked={i === 0} /> {o}
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TestResults() {
  return (
    <ul className="sample-tests">
      <li className="pass">
        <span className="mark">✓</span> <span className="cat">basic</span> passed
      </li>
      <li className="pass">
        <span className="mark">✓</span> <span className="cat">single_item</span> passed
      </li>
      <li className="fail">
        <span className="mark">✗</span> <span className="cat">empty_input</span> Hidden test, category: empty_input
      </li>
    </ul>
  );
}

export function VerifiedExplanation() {
  return (
    <div className="sample">
      <ActivityLog rows={SAMPLE_LOG.slice(0, 4)} open />
      <p>
        <span className="badge badge-verified">Verified · 6 of 6</span>
      </p>
      <p>
        Your loop reads <EvidenceChip>xs[0]</EvidenceChip> before it checks that the list has items, so an empty list
        raises an IndexError.
      </p>
      <p className="sources">
        <EvidenceChip>test: empty_input</EvidenceChip> <EvidenceChip>line 3</EvidenceChip>{" "}
        <EvidenceChip>notes: lists.md</EvidenceChip>
      </p>
    </div>
  );
}

export function HintLadder() {
  return (
    <div className="sample">
      <div className="ladder">
        <button type="button" disabled>
          Concept hint
        </button>
        <button type="button" disabled>
          Where to look
        </button>
        <button type="button" disabled>
          Worked example on another problem
        </button>
      </div>
      <p className="hint-text">
        Hint 1 of 3 · Think about what the list looks like before the loop runs the first time.
      </p>
    </div>
  );
}

export function LedgerSample() {
  return (
    <div className="sample">
      <MasteryStrip name="Loops" value={0.55} delta={{ from: 0.62, to: 0.55 }} />
      <table className="ledger-table">
        <thead>
          <tr>
            <th scope="col">Evidence</th>
            <th scope="col">Rule</th>
            <th scope="col">Change</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Submission, failed test empty_input</td>
            <td>Weak negative</td>
            <td>0.62 → 0.55</td>
          </tr>
          <tr>
            <td>Placement, Question 4 (off-by-one option)</td>
            <td>Misconception</td>
            <td>0.70 → 0.62</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function ChatSample() {
  return (
    <div className="sample chat-sample">
      <p className="me">Why does my code fail on an empty list?</p>
      <p className="route">
        <span className="evidence">Routed to: Explain</span> Wrong? Change
      </p>
      <p>
        It reads the first item before it checks that the list has items. The checked explanation shows the line and the note it comes from.
      </p>
    </div>
  );
}

export function ResultSample() {
  return (
    <div className="sample">
      <MasteryStrip name="Variables" value={0.86} />
      <MasteryStrip name="Loops" value={0.31} />
      <MasteryStrip name="Recursion" value={0.44} />
      <p className="hint-text">Likely misunderstanding: off-by-one in loop bounds (from your answer to Question 4).</p>
    </div>
  );
}
