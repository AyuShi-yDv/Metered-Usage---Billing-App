// Pure geometry helpers for the SVG chart (kept free of React so they can be unit-tested).

/** Round a positive number up to 1/2/5 x 10^n so y-axis ticks land on friendly values. */
export function niceCeil(value: number): number {
  if (!Number.isFinite(value) || value <= 1) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(value)));
  const f = value / exp;
  const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
  return nice * exp;
}

/** Evenly spaced tick values from 0 to `max` (max should already be nice). Integers only for small maxima. */
export function yTicks(max: number, count = 4): number[] {
  if (max <= count) return Array.from({ length: max + 1 }, (_, i) => i);
  return Array.from({ length: count + 1 }, (_, i) => Math.round((max * i) / count));
}

/** Up to `target` evenly spaced indexes into a series of `length` points, always including first and last. */
export function tickIndexes(length: number, target = 6): number[] {
  if (length <= 0) return [];
  if (length <= target) return Array.from({ length }, (_, i) => i);
  const out = new Set<number>();
  for (let i = 0; i < target; i++) out.add(Math.round((i * (length - 1)) / (target - 1)));
  return [...out].sort((a, b) => a - b);
}

export interface Plot { x0: number; y0: number; width: number; height: number }

export function xFor(index: number, length: number, plot: Plot): number {
  return length <= 1 ? plot.x0 + plot.width / 2 : plot.x0 + (index / (length - 1)) * plot.width;
}

export function yFor(value: number, max: number, plot: Plot): number {
  return plot.y0 + plot.height - (max <= 0 ? 0 : (value / max) * plot.height);
}

const n = (v: number) => v.toFixed(1);

export function linePath(values: number[], max: number, plot: Plot): string {
  return values.map((v, i) => `${i === 0 ? 'M' : 'L'}${n(xFor(i, values.length, plot))} ${n(yFor(v, max, plot))}`).join(' ');
}

export function areaPath(values: number[], max: number, plot: Plot): string {
  if (values.length === 0) return '';
  const baseline = plot.y0 + plot.height;
  const first = xFor(0, values.length, plot);
  const last = xFor(values.length - 1, values.length, plot);
  return `${linePath(values, max, plot)} L${n(last)} ${n(baseline)} L${n(first)} ${n(baseline)} Z`;
}

/** Index of the point closest to a pointer x (in the same coordinate space as the plot). */
export function nearestIndex(pointerX: number, length: number, plot: Plot): number {
  if (length <= 1) return 0;
  const ratio = (pointerX - plot.x0) / plot.width;
  return Math.min(length - 1, Math.max(0, Math.round(ratio * (length - 1))));
}
