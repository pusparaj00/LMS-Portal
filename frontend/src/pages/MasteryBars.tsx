import { MasteryStrip } from "../design/MasteryStrip";
import { ConceptMastery, Misconception } from "../types";

const pretty = (name: string) => name.replace(/_/g, " ");

/** F-28: what the number rests on, in words. */
function evidenceNote(c: ConceptMastery): string | null {
  if (c.status === "not assessed") return "Not assessed yet";
  if (c.status === "estimated") return "Estimated from your overall level, not asked about yet";
  if (c.status !== "assessed") return null;
  const n = c.evidence_count ?? 0;
  const when = c.last_assessed ? `, last ${new Date(c.last_assessed).toLocaleDateString()}` : "";
  return `${c.confidence} confidence, from ${n} ${n === 1 ? "answer" : "answers"}${when}`;
}

export function MasteryBars({
  concepts,
  courseId,
  link,
}: {
  concepts: ConceptMastery[];
  courseId?: number;
  link?: (conceptId: number) => string;
}) {
  return (
    <ul className="bars">
      {concepts.map((c) => (
        <li key={c.concept_id}>
          <MasteryStrip
            name={
              link || courseId ? (
                <a href={link ? link(c.concept_id) : `#/mastery/${courseId}/concept/${c.concept_id}`}>{pretty(c.name)}</a>
              ) : (
                pretty(c.name)
              )
            }
            value={c.p_known}
          />
          {evidenceNote(c) && <small className="evidence-note">{evidenceNote(c)}</small>}
        </li>
      ))}
    </ul>
  );
}

export function Misconceptions({ items }: { items: Misconception[] }) {
  if (items.length === 0) return <p className="empty">No misconception stands out yet.</p>;
  return (
    <ul className="rows">
      {items.map((m) => (
        <li key={m.name}>
          <span className="grow">{m.description}</span>
          <span className="tag">{Math.round(m.probability * 100)}% likely</span>
        </li>
      ))}
    </ul>
  );
}
