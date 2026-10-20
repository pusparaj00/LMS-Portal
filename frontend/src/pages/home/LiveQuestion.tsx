import { useState } from "react";

import { MISCONCEPTIONS, QUESTIONS } from "./homeData";

/** The one live thing on the public page: a real tracing question from the course bank. A wrong option names the
 *  misconception the bank maps it to, as the placement test does. Nothing is sent anywhere. */
export function LiveQuestion() {
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const question = QUESTIONS[index];
  const option = picked === null ? null : question.options[picked];

  function choose(next: number) {
    setIndex(next);
    setPicked(null);
  }

  return (
    <div className="live" data-ui>
      <pre className="live-code" aria-label="The program">
        <code>{question.code}</code>
      </pre>
      <div className="live-side">
        <p className="live-ask" id="live-ask">
          What does this program print?
        </p>
        <div role="group" aria-labelledby="live-ask" className="live-options">
          {question.options.map((o, i) => (
            <button
              key={`${question.id}-${o.text}`}
              type="button"
              aria-pressed={picked === i}
              className="live-option"
              onClick={() => setPicked(i)}
            >
              <code>{o.text}</code>
            </button>
          ))}
        </div>
        <div className="live-answer" role="status" aria-live="polite">
          {option === null ? (
            <p className="live-hint">Pick an answer. Nothing is recorded.</p>
          ) : option.correct ? (
            <>
              <p className="live-verdict">That is right.</p>
              <p>The placement test would count this toward your {question.concept} mastery, with how sure you said you were.</p>
            </>
          ) : (
            <>
              <p className="live-verdict">This answer has a name.</p>
              <p className="live-name">{option.misconception?.replace(/_/g, " ")}</p>
              <p>{option.misconception ? MISCONCEPTIONS[option.misconception] : ""}</p>
              <p className="live-note">The result of the placement test lists suspected misconceptions like this one, with the answer each came from.</p>
            </>
          )}
        </div>
      </div>
      <div className="live-more">
        <p>More from the bank</p>
        {QUESTIONS.map((q, i) =>
          i === index ? null : (
            <button key={q.id} type="button" className="textbutton" onClick={() => choose(i)}>
              {q.label}
            </button>
          ),
        )}
      </div>
    </div>
  );
}
