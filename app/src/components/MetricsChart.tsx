import type { TelemetryRow } from "../lib/api/types";

interface Props {
  rows: TelemetryRow[];
  field?: keyof TelemetryRow;
  height?: number;
}

function minmax(vals: number[]): [number, number] {
  if (vals.length === 0) return [0, 1];
  return [Math.min(...vals), Math.max(...vals)];
}

export default function MetricsChart({ rows, field = "temp_c", height = 80 }: Props) {
  const width = 400;

  const vals = rows
    .map((r) => r[field])
    .filter((v): v is number => typeof v === "number");

  if (vals.length < 2) {
    return (
      <div
        data-testid="metrics-chart-empty"
        className="flex items-center justify-center rounded bg-zinc-800 text-xs text-zinc-500"
        style={{ width, height }}
      >
        No data
      </div>
    );
  }

  const [lo, hi] = minmax(vals);
  const span = hi - lo || 1;

  const points = vals
    .map((v, i) => {
      const x = (i / (vals.length - 1)) * width;
      const y = height - ((v - lo) / span) * (height - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      data-testid="metrics-chart"
      width={width}
      height={height}
      className="rounded bg-zinc-800"
      role="img"
      aria-label={`${String(field)} over time`}
    >
      <polyline
        points={points}
        fill="none"
        stroke="#34d399"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}
