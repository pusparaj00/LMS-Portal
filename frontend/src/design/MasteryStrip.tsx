import { ReactNode } from "react";

/** The five bands of docs/ux-plan.md 1.1. Every strip carries the number and the label, so colour is never the only signal. */
const BANDS = [
  { label: "Needs work", upTo: 0.2 },
  { label: "Shaky", upTo: 0.4 },
  { label: "Developing", upTo: 0.6 },
  { label: "Solid", upTo: 0.8 },
  { label: "Strong", upTo: 1.01 },
];

export function masteryBand(p: number): { index: number; label: string } {
  const index = BANDS.findIndex((b) => p < b.upTo);
  return { index, label: BANDS[index].label };
}

export type Delta = { from: number; to: number };

const two = (p: number) => p.toFixed(2);

export function DeltaChip({ delta }: { delta: Delta }) {
  const direction = delta.to >= delta.from ? "up" : "down";
  return (
    <span className={`delta delta-${direction}`} title="Change from the last evidence">
      {two(delta.from)} → {two(delta.to)}
    </span>
  );
}

export function MasteryStrip({
  name,
  value,
  delta,
  size = "medium",
}: {
  name: ReactNode;
  value: number;
  delta?: Delta;
  size?: "small" | "medium";
}) {
  const { index, label } = masteryBand(value);
  const plain = typeof name === "string" ? name : "concept";
  return (
    <div className={`strip strip-${size}`}>
      <span className="strip-name">{name}</span>
      <span className="strip-track" role="img" aria-label={`${plain}, ${two(value)}, ${label}`}>
        <span className="strip-fill" style={{ width: `${Math.round(value * 100)}%`, background: `var(--r${index})` }} />
      </span>
      <span className="strip-value">{two(value)}</span>
      <span className="strip-label">{label}</span>
      {delta && <DeltaChip delta={delta} />}
    </div>
  );
}
