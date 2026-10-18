import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const AXIS = { fill: "var(--slate)", fontSize: 12 };
const GRID = "var(--line)";

/** Students per score band. The table beside it carries the same numbers for screen readers. */
export function DistributionChart({ data }: { data: { label: string; students: number }[] }) {
  return (
    <figure className="chart-box" aria-label="Students per score band">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={AXIS} stroke={GRID} />
          <YAxis allowDecimals={false} tick={AXIS} stroke={GRID} />
          <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)" }} cursor={{ fill: "var(--signal-soft)" }} />
          <Bar dataKey="students" name="Students" fill="var(--signal)" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}

export type StatusRow = {
  title: string;
  complete: number;
  in_progress: number;
  late: number;
  missing: number;
  not_started: number;
};

/** Where every student stands on each assignment, one stacked bar per assignment. */
export function StatusChart({ data }: { data: StatusRow[] }) {
  return (
    <figure className="chart-box" aria-label="Student progress per assignment">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="title" tick={AXIS} stroke={GRID} />
          <YAxis allowDecimals={false} tick={AXIS} stroke={GRID} />
          <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)" }} cursor={{ fill: "var(--signal-soft)" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="complete" name="Complete" stackId="s" fill="var(--pass)" />
          <Bar dataKey="in_progress" name="In progress" stackId="s" fill="var(--signal)" />
          <Bar dataKey="late" name="Late work" stackId="s" fill="var(--warn)" />
          <Bar dataKey="missing" name="Missing" stackId="s" fill="var(--fail)" />
          <Bar dataKey="not_started" name="Not started" stackId="s" fill="var(--slate)" />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
