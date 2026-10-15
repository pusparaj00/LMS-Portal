import { ConceptMastery, Misconception } from "../types";

const pretty = (name: string) => name.replace(/_/g, " ");

export function MasteryBars({ concepts, courseId }: { concepts: ConceptMastery[]; courseId?: number }) {
  return (
    <ul className="bars">
      {concepts.map((c) => {
        const percent = Math.round(c.p_known * 100);
        return (
          <li key={c.concept_id}>
            <span className="name">
              {courseId ? (
                <a href={`#/mastery/${courseId}/concept/${c.concept_id}`}>{pretty(c.name)}</a>
              ) : (
                pretty(c.name)
              )}
            </span>
            <span className="track" role="img" aria-label={`${pretty(c.name)}, ${percent}% mastery`}>
              <span className="fill" style={{ width: `${percent}%` }} />
            </span>
            <span className="value">{percent}%</span>
          </li>
        );
      })}
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
