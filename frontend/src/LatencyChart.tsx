import { type RefObject, useEffect, useRef, useState } from "react";
import { type Experiment, JAEGER } from "./api";
import { segments, timeline, toPoints } from "./chart";

// The size until the plot is measured, and in tests: jsdom has no layout.
const SIZE = { width: 600, height: 120 };
const PHASE_NAMES = ["baseline", "inject", "recover"];
const TOP = 20; // px above the line for the phase names, so a high dot doesn't cover them
const BOTTOM = 6; // px below it, so a dot at zero isn't cut by the border

type ChartProps = {
  label: string;
  values: (number | null)[]; // one per second of the whole experiment
  max: number; // the value at the top of the chart
  format: (value: number) => string;
  phaseStarts: number[];
  traces: (string | null)[]; // a dot per second that has one, linking to Jaeger (#173)
};

/**
 * The size of the element, kept up to date (#210). The chart draws in real pixels, so a
 * bigger panel gives a bigger plot, while text and dots keep their size (Tomáš).
 */
function useSize(ref: RefObject<HTMLElement | null>) {
  const [size, setSize] = useState(SIZE);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}

/** One quantity over the whole experiment; a second without data is a gap (#79). */
function Chart({ label, values, max, format, phaseStarts, traces }: ChartProps) {
  const plot = useRef<HTMLDivElement>(null);
  const { width, height } = useSize(plot);
  const h = Math.max(height - TOP - BOTTOM, 0); // where the line is drawn
  // The phases are three separate load runs: a line across a border would rise before
  // the fault starts. So each phase gets its own lines, the rest of the axis masked out.
  const lines = phaseStarts.flatMap((start, i) => {
    const end = phaseStarts[i + 1] ?? values.length;
    const phase = values.map((v, s) => (s >= start && s < end ? v : null));
    return segments(phase, max, width, h);
  });
  const step = values.length > 1 ? width / (values.length - 1) : 0; // as in segments
  return (
    <figure>
      <figcaption>
        {label} (top: {format(max)})
      </figcaption>
      <div className="plot" ref={plot}>
        <svg width={width} height={height} role="img" aria-label={label}>
          {phaseStarts.map((start, i) => (
            <g key={start}>
              {i > 0 && (
                <line
                  x1={start * step}
                  x2={start * step}
                  y1={0}
                  y2={height}
                  style={{ stroke: "var(--muted)" }}
                  strokeDasharray="4 4"
                />
              )}
              <text x={start * step + 4} y={12} fontSize={10} style={{ fill: "var(--muted)" }}>
                {PHASE_NAMES[i]}
              </text>
            </g>
          ))}
          <g transform={`translate(0 ${TOP})`}>
            {values.map((v, s) => {
              const trace = traces[s];
              if (v === null || !trace) {
                return null;
              }
              const y = max === 0 ? h : h - (v / max) * h; // as in segments
              return (
                <a key={trace} href={`${JAEGER}/trace/${trace}`} target="_blank" rel="noreferrer">
                  <circle cx={s * step} cy={y} r={4} style={{ fill: "var(--main)" }}>
                    <title>
                      second {s}: {format(v)}, open the trace
                    </title>
                  </circle>
                </a>
              );
            })}
            {lines.map((line) => (
              // a line never starts twice at the same x, so its first x is a stable key
              <g key={line[0]?.x}>
                <polyline
                  points={toPoints(line)}
                  fill="none"
                  style={{ stroke: "var(--main)" }}
                  strokeWidth={2}
                />
                {line.length === 1 && line[0] && (
                  // a lone second is a line of one point, which <polyline> does not draw
                  <circle cx={line[0].x} cy={line[0].y} r={2} style={{ fill: "var(--main)" }} />
                )}
              </g>
            ))}
          </g>
        </svg>
      </div>
    </figure>
  );
}

/** p95 and error rate per second, one chart above the other on the same time axis. */
export function LatencyChart({ experiment }: { experiment: Experiment }) {
  const t = timeline(experiment);
  const measured = t.p95.filter((v) => v !== null);
  return (
    <section aria-label="latency over time" className="latency">
      <Chart
        label="p95 latency"
        values={t.p95}
        max={measured.length > 0 ? Math.max(...measured) : 0}
        format={(v) => `${v.toFixed(1)} ms`}
        phaseStarts={t.phaseStarts}
        traces={t.traces}
      />
      <Chart
        label="error rate"
        values={t.errorRate}
        max={1}
        format={(v) => `${(v * 100).toFixed(0)} %`}
        phaseStarts={t.phaseStarts}
        traces={t.traces}
      />
    </section>
  );
}
