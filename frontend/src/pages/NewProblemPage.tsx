import { FormEvent, useEffect, useState } from "react";

import { ApiError, BUSY_RETRIES, Problem, Session, api } from "../api";
import { Concept, ConceptAdder } from "./ConceptAdder";

type TestRow = { input: string; expected: string; hidden: boolean; category: string };

const CATEGORIES = ["basic", "zero", "negative_numbers", "single_item", "empty_input", "large_input", "boundary"];
// "" asks the server to estimate it from the text and concepts (F-23); the problem is then marked as estimated.
const DIFFICULTY = [
  { label: "Estimate it for me", value: "" },
  { label: "Easy", value: "-1" },
  { label: "Medium", value: "0" },
  { label: "Hard", value: "1" },
];
const pretty = (name: string) => name.replace(/_/g, " ");
const blankTest = (): TestRow => ({ input: "", expected: "", hidden: false, category: "basic" });

type Draft = {
  title: string;
  statement: string;
  reference_solution: string;
  test_cases: TestRow[];
  concept_id: number;
  wrong_category: string;
  checks: string[];
};

type Source = {
  title: string;
  statement: string;
  difficulty_b: number;
  param_source: "prior" | "estimated";
  concepts: { concept_id: number; name: string; weight: number }[];
  reference_solution: string;
  test_cases: TestRow[];
};

/** F-02: an instructor adds a coding problem, or edits one. The server runs the reference solution against every test
 * first, either way. */
export function NewProblemPage({ session, courseId, problemId }: { session: Session; courseId: number; problemId?: number }) {
  const [concepts, setConcepts] = useState<Concept[] | null>(null);
  const [title, setTitle] = useState("");
  const [statement, setStatement] = useState("");
  const [difficulty, setDifficulty] = useState("0");
  const [estimated, setEstimated] = useState<number | null>(null);
  const [weights, setWeights] = useState<Record<number, number>>({});
  const [solution, setSolution] = useState("");
  const [tests, setTests] = useState<TestRow[]>([
    { ...blankTest() },
    { ...blankTest(), hidden: true, category: "boundary" },
  ]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draftConcept, setDraftConcept] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draftChecks, setDraftChecks] = useState<string[] | null>(null);

  useEffect(() => {
    api<Concept[]>(`/courses/${courseId}/concepts`, session)
      .then(setConcepts)
      .catch((e: Error) => setError(e.message));
    if (!problemId) return;
    api<Source>(`/problems/${problemId}/source`, session)
      .then((s) => {
        setTitle(s.title);
        setStatement(s.statement);
        if (s.param_source === "estimated") {
          setDifficulty("");
          setEstimated(s.difficulty_b);
        } else {
          const nearest = ["-1", "0", "1"].reduce((a, b) => (Math.abs(Number(b) - s.difficulty_b) < Math.abs(Number(a) - s.difficulty_b) ? b : a));
          setDifficulty(Number(nearest) === s.difficulty_b ? nearest : String(s.difficulty_b));
        }
        setWeights(Object.fromEntries(s.concepts.map((c) => [c.concept_id, c.weight])));
        setSolution(s.reference_solution);
        setTests(s.test_cases);
      })
      .catch((e: Error) => setError(e.message));
  }, [courseId, problemId]);

  const update = (index: number, change: Partial<TestRow>) =>
    setTests((rows) => rows.map((row, i) => (i === index ? { ...row, ...change } : row)));

  /** TR-L-10: fill the form with a model-written problem that already passed both sandbox checks; the instructor
   * reviews and edits it, and nothing is stored until they press Save. */
  async function draft() {
    setDrafting(true);
    setError(null);
    setDraftChecks(null);
    try {
      const d = await api<Draft>("/problems/draft", session, {
        body: { course_id: courseId, concept_id: Number(draftConcept) },
        onBusy: (attempt) => setNotice(`The sandbox is busy, trying again (${attempt} of ${BUSY_RETRIES})…`),
      });
      setTitle(d.title);
      setStatement(d.statement);
      setSolution(d.reference_solution);
      setTests(d.test_cases);
      setWeights({ [d.concept_id]: 1 });
      setDifficulty("");
      setDraftChecks(d.checks);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setDrafting(false);
      setNotice(null);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const chosen = Object.entries(weights).filter(([, w]) => w > 0);
      const problem = await api<Problem>(problemId ? `/problems/${problemId}` : "/problems", session, {
        method: problemId ? "PUT" : "POST",
        body: {
          course_id: courseId,
          title,
          statement,
          difficulty_b: difficulty === "" ? null : Number(difficulty),
          discrimination_a: 1,
          concepts: chosen.map(([id, weight]) => ({
            concept_id: Number(id),
            name: concepts?.find((c) => c.concept_id === Number(id))?.name ?? "",
            weight,
          })),
          reference_solution: solution,
          test_cases: tests,
        },
        onBusy: (attempt) => setNotice(`The sandbox is busy, trying again (${attempt} of ${BUSY_RETRIES})…`),
      });
      window.location.hash = `#/problem/${problem.id}`;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The server could not be reached.");
    } finally {
      setBusy(false);
      setNotice(null);
    }
  }

  if (!concepts) return error ? <p role="alert" className="error">{error}</p> : <p>Loading…</p>;

  return (
    <>
      <p>
        <a href={`#/course/${courseId}`}>Back to problems</a>
      </p>
      <h1>{problemId ? "Edit the problem" : "Add a coding problem"}</h1>
      <p>
        Students' programs read from standard input and print their answer. Before the problem is saved, your reference
        solution is run in the sandbox against every test and must pass them all.
      </p>
      {!problemId && concepts.length > 0 && (
        <section className="panel draft-panel" aria-label="Draft with AI">
          <h2>Start from an AI draft</h2>
          <p>
            A model writes a problem for one concept. It is offered only if its reference solution passes all its tests
            and a version with a typical mistake fails them, both run in the sandbox. Read it and change anything before
            you save.
          </p>
          <div className="inline-form">
            <label>
              Concept
              <select value={draftConcept} onChange={(e) => setDraftConcept(e.target.value)}>
                <option value="">Choose a concept</option>
                {concepts.map((c) => (
                  <option key={c.concept_id} value={c.concept_id}>
                    {pretty(c.name)}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" onClick={draft} disabled={drafting || !draftConcept}>
              {drafting ? "Writing and checking…" : "Draft a problem"}
            </button>
          </div>
          {drafting && <p role="status">This takes up to half a minute: the model writes it, then the sandbox runs both solutions.</p>}
          {draftChecks && (
            <div role="status" className="notice">
              <p>
                <strong>Draft placed in the form below. It is not saved yet.</strong>
              </p>
              <ul>
                {draftChecks.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
      {problemId && (
        <p className="notice">
          Saving an edit marks the problem as needing review again. Submissions already made keep the results they had;
          an explanation for an old submission may fall back to a template if its failing test was changed.
        </p>
      )}
      <form className="stack" onSubmit={save}>
        <label>
          Title
          <input value={title} maxLength={200} required onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          Statement
          <textarea value={statement} rows={4} required onChange={(e) => setStatement(e.target.value)} />
        </label>
        <label>
          Difficulty
          <select value={difficulty} aria-describedby="difficulty-help" onChange={(e) => setDifficulty(e.target.value)}>
            {DIFFICULTY.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
            {!DIFFICULTY.some((d) => d.value === difficulty) && <option value={difficulty}>Kept as it is ({difficulty})</option>}
          </select>
        </label>
        <small id="difficulty-help">
          {difficulty === ""
            ? "Estimated from the reference solution, the statement and the concepts, in the way the question bank's authors rated theirs."
            : "A starting value. It is marked as a prior until real answers refine it."}
          {estimated !== null && difficulty === "" && ` Current estimate: ${estimated}.`}
        </small>

        <fieldset>
          <legend>Concepts this problem practises</legend>
          {concepts.length === 0 && (
            <p className="empty">This course has no concepts yet. A problem needs at least one: add it below.</p>
          )}
          {concepts.map((c) => (
            <div key={c.concept_id} className="concept-pick">
              <label className="inline">
                <input
                  type="checkbox"
                  checked={(weights[c.concept_id] ?? 0) > 0}
                  onChange={(e) => setWeights({ ...weights, [c.concept_id]: e.target.checked ? 1 : 0 })}
                />
                {pretty(c.name)}
              </label>
              {(weights[c.concept_id] ?? 0) > 0 && (
                <label className="inline">
                  <small>weight</small>
                  <input
                    type="number"
                    min={0.1}
                    max={1}
                    step={0.1}
                    value={weights[c.concept_id]}
                    onChange={(e) => setWeights({ ...weights, [c.concept_id]: Number(e.target.value) })}
                  />
                </label>
              )}
            </div>
          ))}
          <ConceptAdder
            session={session}
            courseId={courseId}
            onAdded={(concept) => {
              setConcepts((list) => [...(list ?? []), concept]);
              setWeights((w) => ({ ...w, [concept.concept_id]: 1 }));
            }}
          />
        </fieldset>

        <label>
          Reference solution
          <textarea
            className="code"
            value={solution}
            rows={8}
            required
            spellCheck={false}
            onChange={(e) => setSolution(e.target.value)}
          />
        </label>

        <fieldset>
          <legend>Tests</legend>
          <p>Hidden tests are never shown to students; they only see how many failed and in which category.</p>
          {tests.map((row, i) => (
            <div className="test-row" key={i}>
              <label>
                Input
                <textarea className="code" rows={2} value={row.input} spellCheck={false} onChange={(e) => update(i, { input: e.target.value })} />
              </label>
              <label>
                Expected output
                <textarea className="code" rows={2} value={row.expected} spellCheck={false} onChange={(e) => update(i, { expected: e.target.value })} />
              </label>
              <label>
                Category
                <input list="categories" value={row.category} required onChange={(e) => update(i, { category: e.target.value })} />
              </label>
              <label className="inline">
                <input type="checkbox" checked={row.hidden} onChange={(e) => update(i, { hidden: e.target.checked })} />
                Hidden
              </label>
              <button type="button" className="link" disabled={tests.length === 1} onClick={() => setTests(tests.filter((_, k) => k !== i))}>
                Remove
              </button>
            </div>
          ))}
          <datalist id="categories">
            {CATEGORIES.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
          <button type="button" onClick={() => setTests([...tests, blankTest()])} disabled={tests.length >= 50}>
            Add a test
          </button>
        </fieldset>

        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <p>
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "Checking the reference solution…" : "Check and save"}
          </button>{" "}
          {notice && <span role="status">{notice}</span>}
        </p>
      </form>
    </>
  );
}
