import { fromLocalInput, localTimeZoneName, PRESET_LABEL, rangeError, resolveRange, toLocalInput } from '../lib/time.ts';
import type { Granularity, RangePreset, RangeSelection } from '../lib/time.ts';
import { cx } from './ui';

const PRESETS: Array<Exclude<RangePreset, 'custom'>> = ['24h', '7d', '30d'];

function Segmented<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: Array<{ value: T; text: string }>; onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-md bg-slate-800 p-0.5">
      {options.map((option) => (
        <button key={option.value} type="button" aria-pressed={value === option.value} onClick={() => onChange(option.value)}
          className={cx('rounded px-3 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-300',
            value === option.value ? 'bg-cyan-500 font-medium text-slate-950' : 'text-slate-300 hover:text-white')}>
          {option.text}
        </button>
      ))}
    </div>
  );
}

/** Date range picker + hourly/daily toggle. Both write straight to the URL via `onChange`. */
export function RangeControls({ range, granularity, onRange, onGranularity }: {
  range: RangeSelection; granularity: Granularity; onRange: (range: RangeSelection) => void; onGranularity: (g: Granularity) => void;
}) {
  const custom = range.preset === 'custom';
  const problem = rangeError(range, granularity);
  const resolved = resolveRange(range);

  const chooseCustom = () => {
    // Start from whatever the chart is showing right now, so switching to "Custom" changes nothing visually.
    onRange({ preset: 'custom', start: resolved.start.toISOString(), end: resolved.end.toISOString() });
  };
  const setEdge = (edge: 'start' | 'end', value: string) => {
    const iso = fromLocalInput(value);
    if (!iso) return; // cleared or half-typed: keep the last valid range
    const next = { start: range.start ?? resolved.start.toISOString(), end: range.end ?? resolved.end.toISOString() };
    next[edge] = iso;
    onRange({ preset: 'custom', start: next.start, end: next.end });
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented<string> label="Date range" value={range.preset}
          options={[...PRESETS.map((p) => ({ value: p as string, text: PRESET_LABEL[p] })), { value: 'custom', text: 'Custom' }]}
          onChange={(value) => (value === 'custom' ? chooseCustom() : onRange({ preset: value as RangePreset }))} />
        <Segmented<Granularity> label="Granularity" value={granularity}
          options={[{ value: 'hour', text: 'Hourly' }, { value: 'day', text: 'Daily' }]} onChange={onGranularity} />
      </div>
      {custom && (
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm text-slate-300">
            <span className="mb-1 block text-xs text-slate-400">From ({localTimeZoneName()})</span>
            <input type="datetime-local" value={toLocalInput(range.start ?? '')} onChange={(e) => setEdge('start', e.target.value)}
              className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-300" />
          </label>
          <label className="text-sm text-slate-300">
            <span className="mb-1 block text-xs text-slate-400">To ({localTimeZoneName()})</span>
            <input type="datetime-local" value={toLocalInput(range.end ?? '')} onChange={(e) => setEdge('end', e.target.value)}
              className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-300" />
          </label>
        </div>
      )}
      {problem && <p role="alert" className="text-sm text-amber-300">{problem}</p>}
    </div>
  );
}
