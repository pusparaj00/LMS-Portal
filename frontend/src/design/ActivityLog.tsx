import { ReactNode } from "react";

export type Verb = "Ran" | "Read" | "Drafted" | "Checked" | "Used" | "Updated";

export type LogRow = { verb: Verb; text: ReactNode };

/** The "Worked · n" list: what ran, what was read and which checks passed (ux-plan 5). */
export function ActivityLog({ rows, open = false }: { rows: LogRow[]; open?: boolean }) {
  return (
    <details className="worked" open={open}>
      <summary>Worked · {rows.length}</summary>
      <ol aria-label="What the system did">
        {rows.map((row, i) => (
          <li key={i}>
            <span className="verb">{row.verb}</span>
            <span>{row.text}</span>
          </li>
        ))}
      </ol>
    </details>
  );
}
