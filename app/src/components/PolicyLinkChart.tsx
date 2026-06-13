import type { LatencySample } from "../lib/series";

interface Props {
  samples: readonly LatencySample[];
  width?: number;
  height?: number;
}

const W = 320;
const H = 80;
const PAD = 8;

export default function PolicyLinkChart({ samples, width = W, height = H }: Props) {
  if (samples.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        className="rounded bg-zinc-900"
        data-testid="policy-link-chart"
      >
        <text x={width / 2} y={height / 2} textAnchor="middle" fill="#52525b" fontSize={11}>
          No data
        </text>
      </svg>
    );
  }

  const maxMs = Math.max(...samples.map((s) => s.inferMs), 1);
  const n = samples.length;
  const xScale = (i: number) => PAD + ((width - 2 * PAD) * i) / (n - 1);
  const yScale = (v: number) => height - PAD - ((height - 2 * PAD) * v) / maxMs;

  const points = samples
    .map((s, i) => `${xScale(i).toFixed(1)},${yScale(s.inferMs).toFixed(1)}`)
    .join(" ");

  const stale = samples[samples.length - 1]?.stale;

  return (
    <svg
      width={width}
      height={height}
      className="rounded bg-zinc-900"
      data-testid="policy-link-chart"
    >
      <polyline
        points={points}
        fill="none"
        stroke={stale ? "#a16207" : "#4ade80"}
        strokeWidth={1.5}
      />
      {/* Axis label */}
      <text x={PAD} y={height - 2} fill="#52525b" fontSize={9}>
        infer ms (max {maxMs.toFixed(0)})
      </text>
    </svg>
  );
}
