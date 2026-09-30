import { useMemo, useState } from 'react';
import type { PointerEvent } from 'react';
import type { UsagePoint } from '../api/types';
import { areaPath, linePath, nearestIndex, niceCeil, tickIndexes, xFor, yFor, yTicks } from '../lib/chart.ts';
import type { Plot } from '../lib/chart.ts';
import { formatInt } from '../lib/money.ts';
import { formatAxisLabel, formatBucket } from '../lib/time.ts';
import type { Granularity } from '../lib/time.ts';

const W = 900;
const H = 300;
const PLOT: Plot = { x0: 56, y0: 16, width: W - 56 - 16, height: H - 16 - 36 };

/** Zero-filled line/area chart. Every bucket from the API is drawn, including the zeros. */
export function UsageChart({ points, granularity }: { points: UsagePoint[]; granularity: Granularity }) {
  const [hover, setHover] = useState<number | null>(null);
  const stats = useMemo(() => {
    const values = points.map((p) => p.billable_calls);
    const total = values.reduce((sum, v) => sum + v, 0);
    const peak = values.reduce((m, v) => Math.max(m, v), 0);
    return { values, total, peak, zeros: values.filter((v) => v === 0).length, max: niceCeil(Math.max(peak, 1)) };
  }, [points]);

  const span = points.length > 1 ? new Date(points[points.length - 1].bucket).getTime() - new Date(points[0].bucket).getTime() : 0;
  const ticks = tickIndexes(points.length);
  const active = hover !== null && hover < points.length ? hover : null;

  const onMove = (event: PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width === 0) return;
    setHover(nearestIndex(((event.clientX - rect.left) / rect.width) * W, points.length, PLOT));
  };

  return (
    <div>
      <p className="mb-2 text-sm text-slate-400">
        <span className="font-medium text-slate-200">{formatInt(stats.total)}</span> billable calls · peak{' '}
        <span className="font-medium text-slate-200">{formatInt(stats.peak)}</span> per {granularity} ·{' '}
        {stats.zeros} of {points.length} {granularity === 'hour' ? 'hours' : 'days'} had no traffic (drawn as 0)
      </p>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-72 w-full touch-none select-none" role="img"
          aria-label={`Billable calls per ${granularity}: ${formatInt(stats.total)} in total, peak ${formatInt(stats.peak)}`}
          onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
          {yTicks(stats.max).map((tick) => {
            const y = yFor(tick, stats.max, PLOT);
            return (
              <g key={tick}>
                <line x1={PLOT.x0} x2={PLOT.x0 + PLOT.width} y1={y} y2={y} stroke="rgb(51 65 85)" strokeWidth="1" strokeDasharray={tick === 0 ? undefined : '3 4'} />
                <text x={PLOT.x0 - 8} y={y + 4} textAnchor="end" fontSize="11" fill="rgb(148 163 184)">{formatInt(tick)}</text>
              </g>
            );
          })}
          <path d={areaPath(stats.values, stats.max, PLOT)} fill="rgb(6 182 212 / 0.18)" />
          <path d={linePath(stats.values, stats.max, PLOT)} fill="none" stroke="rgb(34 211 238)" strokeWidth="2" strokeLinejoin="round" />
          {points.length <= 60 && stats.values.map((v, i) => (
            <circle key={points[i].bucket} cx={xFor(i, points.length, PLOT)} cy={yFor(v, stats.max, PLOT)} r={v === 0 ? 2.5 : 3} fill={v === 0 ? 'rgb(100 116 139)' : 'rgb(34 211 238)'} />
          ))}
          {ticks.map((i) => (
            <text key={i} x={xFor(i, points.length, PLOT)} y={H - 12} fontSize="11" fill="rgb(148 163 184)"
              textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}>
              {formatAxisLabel(points[i].bucket, granularity, span)}
            </text>
          ))}
          {active !== null && (
            <g pointerEvents="none">
              <line x1={xFor(active, points.length, PLOT)} x2={xFor(active, points.length, PLOT)} y1={PLOT.y0} y2={PLOT.y0 + PLOT.height} stroke="rgb(148 163 184)" strokeWidth="1" />
              <circle cx={xFor(active, points.length, PLOT)} cy={yFor(stats.values[active], stats.max, PLOT)} r="5" fill="rgb(34 211 238)" stroke="rgb(15 23 42)" strokeWidth="2" />
            </g>
          )}
        </svg>
        {active !== null && (
          <div role="tooltip" className="pointer-events-none absolute top-2 z-10 -translate-x-1/2 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-xs shadow-lg"
            style={{ left: `${Math.min(88, Math.max(12, (xFor(active, points.length, PLOT) / W) * 100))}%` }}>
            <p className="text-slate-400">{formatBucket(points[active].bucket, granularity)}</p>
            <p className="mt-0.5 text-base font-semibold tabular-nums text-slate-50">{formatInt(stats.values[active])} calls</p>
          </div>
        )}
      </div>
    </div>
  );
}
