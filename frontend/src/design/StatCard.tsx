import { ReactNode } from "react";

/** One headline figure with its label and, where the figure alone is unclear, a short note. */
export function StatCard({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="stat">
      <p className="eyebrow">{label}</p>
      <p className="stat-value">{value}</p>
      {note && <p className="stat-note">{note}</p>}
    </div>
  );
}
