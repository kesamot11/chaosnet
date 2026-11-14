export type Point = { x: number; y: number };
export type Box = { x: number; y: number; width: number; height: number };

const MARGIN = 12; // px of air between a bent link and a service it goes around
const STEP = 20; // px the bend rises per try
const TRIES = 30; // then it gives up and keeps the highest bend
const SAMPLES = 32; // the curve is checked as this many short lines

/**
 * How a link is drawn (#211): the same curve as React Flow's, from a service's right side
 * to another's left side. If it would cross a service in between, it bends upwards, a
 * little more each try, until it goes around (Tomáš: "odklonit ji", as an arc).
 */
export function route(from: Point, to: Point, services: Box[]) {
  // a service on top of either end can't be gone around: an arc would only fly off the screen
  const boxes = services.map(grow).filter((box) => !hits(from, from, box) && !hits(to, to, box));
  for (let i = 0; ; i++) {
    const lift = i * STEP;
    const curve = cubic(from, to, lift);
    const points = Array.from({ length: SAMPLES + 1 }, (_, n) => at(curve, n / SAMPLES));
    const crosses = boxes.some((box) =>
      points.some((p, n) => n > 0 && hits(points[n - 1] as Point, p, box)),
    );
    if (!crosses || i === TRIES) {
      const [a, b, c, d] = curve;
      const middle = at(curve, 0.5); // where the label goes
      return {
        path: `M ${a.x},${a.y} C ${b.x},${b.y} ${c.x},${c.y} ${d.x},${d.y}`,
        labelX: middle.x,
        labelY: middle.y,
      };
    }
  }
}

type Cubic = [Point, Point, Point, Point];

/**
 * React Flow's bezier for these sides (its control offset). A bent one has its controls
 * straight above the ends: it rises at once, so it clears a near service with a low arc.
 */
function cubic(from: Point, to: Point, lift: number): Cubic {
  const dx = to.x - from.x;
  const k = lift > 0 ? 0 : dx >= 0 ? dx / 2 : 6.25 * Math.sqrt(-dx);
  return [from, { x: from.x + k, y: from.y - lift }, { x: to.x - k, y: to.y - lift }, to];
}

function at([a, b, c, d]: Cubic, t: number): Point {
  const s = 1 - t;
  const w = [s * s * s, 3 * s * s * t, 3 * s * t * t, t * t * t] as const;
  return {
    x: w[0] * a.x + w[1] * b.x + w[2] * c.x + w[3] * d.x,
    y: w[0] * a.y + w[1] * b.y + w[2] * c.y + w[3] * d.y,
  };
}

function grow(box: Box): Box {
  return {
    x: box.x - MARGIN,
    y: box.y - MARGIN,
    width: box.width + 2 * MARGIN,
    height: box.height + 2 * MARGIN,
  };
}

/** Does the line from a to b touch the box? (Liang–Barsky: clip the line to each side.) */
export function hits(a: Point, b: Point, box: Box): boolean {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  let enter = 0;
  let leave = 1;
  const sides = [
    [-dx, a.x - box.x],
    [dx, box.x + box.width - a.x],
    [-dy, a.y - box.y],
    [dy, box.y + box.height - a.y],
  ] as const;
  for (const [p, q] of sides) {
    if (p === 0) {
      if (q < 0) return false; // parallel to this side and outside it
    } else if (p < 0) {
      enter = Math.max(enter, q / p);
    } else {
      leave = Math.min(leave, q / p);
    }
  }
  return enter <= leave;
}
