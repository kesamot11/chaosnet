import type { Experiment } from "./api";
import { segments, timeline, toPoints } from "./chart";

const WIDTH = 600;
const HEIGHT = 120;
const PHASE_NAMES = ["baseline", "inject", "recover"];

type ChartProps = {
  label: string;
  values: (number | null)[]; // one per second of the whole experiment
  max: number; // the value at the top of the chart
  format: (value: number) => string;
  phaseStarts: number[];
};

/** One quantity over the whole experiment; a second without data is a gap (#79). */
function Chart({ label, values, max, format, phaseStarts }: ChartProps) {
  // The phases are three separate load runs: a line across a border would rise before
  // the fault starts. So each phase gets its own lines, the rest of the axis masked out.
  const lines = phaseStarts.flatMap((start, i) => {
    const end = phaseStarts[i + 1] ?? values.length;
    const phase = values.map((v, s) => (s >= start && s < end ? v : null));
    return segments(phase, max, WIDTH, HEIGHT);
  });
  const step = values.length > 1 ? WIDTH / (values.length - 1) : 0; // as in segments
  return (
    <figure>
      <figcaption>
        {label} (top: {format(max)})
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        role="img"
        aria-label={label}
        style={{ overflow: "visible", border: "1px solid #ddd" }}
      >
        {phaseStarts.map((start, i) => (
          <g key={start}>
            {i > 0 && (
              <line
                x1={start * step}
                x2={start * step}
                y1={0}
                y2={HEIGHT}
                stroke="#999"
                strokeDasharray="4 4"
              />
            )}
            <text x={start * step + 4} y={12} fontSize={10} fill="#666">
              {PHASE_NAMES[i]}
            </text>
          </g>
        ))}
        {lines.map((line) => (
          // a line never starts twice at the same x, so its first x is a stable key
          <g key={line[0]?.x}>
            <polyline points={toPoints(line)} fill="none" stroke="#d6336c" strokeWidth={2} />
            {line.length === 1 && line[0] && (
              // a lone second is a line of one point, which <polyline> does not draw
              <circle cx={line[0].x} cy={line[0].y} r={2} fill="#d6336c" />
            )}
          </g>
        ))}
      </svg>
    </figure>
  );
}

/** p95 and error rate per second, one chart above the other on the same time axis. */
export function LatencyChart({ experiment }: { experiment: Experiment }) {
  const t = timeline(experiment);
  const measured = t.p95.filter((v) => v !== null);
  return (
    <section aria-label="latency over time">
      <Chart
        label="p95 latency"
        values={t.p95}
        max={measured.length > 0 ? Math.max(...measured) : 0}
        format={(v) => `${v.toFixed(1)} ms`}
        phaseStarts={t.phaseStarts}
      />
      <Chart
        label="error rate"
        values={t.errorRate}
        max={1}
        format={(v) => `${(v * 100).toFixed(0)} %`}
        phaseStarts={t.phaseStarts}
      />
    </section>
  );
}
