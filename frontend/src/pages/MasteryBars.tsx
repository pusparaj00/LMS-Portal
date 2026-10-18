import { MasteryStrip } from "../design/MasteryStrip";
import { ConceptMastery, Misconception } from "../types";

const pretty = (name: string) => name.replace(/_/g, " ");

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
