// All timestamps travel as UTC ISO strings. Inputs and labels are shown in the viewer's local zone.
// Hourly buckets are aligned to UTC hours (whole-hour zones line up with local hours); daily buckets are
// UTC days and are labelled as such, because the API buckets in UTC.

export type Granularity = 'hour' | 'day';
export type RangePreset = '24h' | '7d' | '30d' | 'custom';
export interface RangeSelection { preset: RangePreset; start?: string; end?: string }

export const MAX_SPAN_DAYS: Record<Granularity, number> = { hour: 92, day: 1100 }; // mirrors billing-service caps
const DAY_MS = 86_400_000;
const PRESET_MS: Record<Exclude<RangePreset, 'custom'>, number> = { '24h': DAY_MS, '7d': 7 * DAY_MS, '30d': 30 * DAY_MS };

export const PRESET_LABEL: Record<Exclude<RangePreset, 'custom'>, string> = { '24h': 'Last 24 hours', '7d': 'Last 7 days', '30d': 'Last 30 days' };

export function resolveRange(selection: RangeSelection, now: Date = new Date()): { start: Date; end: Date } {
  if (selection.preset !== 'custom') return { start: new Date(now.getTime() - PRESET_MS[selection.preset]), end: now };
  return { start: new Date(selection.start ?? NaN), end: new Date(selection.end ?? NaN) };
}

/** `<input type="datetime-local">` speaks local wall-clock time; convert an ISO instant to that format. */
export function toLocalInput(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Inverse of toLocalInput: local wall-clock text -> UTC ISO instant (null when empty/invalid). */
export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(value); // "YYYY-MM-DDTHH:mm" without an offset is interpreted as local time
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function rangeError(selection: RangeSelection, granularity: Granularity, now: Date = new Date()): string | null {
  if (selection.preset !== 'custom') return null;
  const { start, end } = resolveRange(selection, now);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 'Choose both a start and an end time.';
  if (end <= start) return 'The end must be after the start.';
  const limit = MAX_SPAN_DAYS[granularity];
  if ((end.getTime() - start.getTime()) / DAY_MS > limit) {
    return granularity === 'hour'
      ? `Hourly view covers at most ${limit} days. Shorten the range or switch to daily.`
      : `Daily view covers at most ${limit} days.`;
  }
  return null;
}

export function localTimeZoneName(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'local time'; } catch { return 'local time'; }
}

export function formatDateTime(iso: string, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
}

export function formatDate(iso: string, locale?: string, utc = false): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', ...(utc ? { timeZone: 'UTC' } : {}) }).format(new Date(iso));
}

/** Tooltip/table label for one bucket. Hours are local; days are UTC calendar days (and say so). */
export function formatBucket(iso: string, granularity: Granularity, locale?: string): string {
  if (granularity === 'day') {
    return `${new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(new Date(iso))} (UTC day)`;
  }
  return new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(iso));
}

/** Short x-axis label; shows the time of day only while the whole chart spans <= 2 days. */
export function formatAxisLabel(iso: string, granularity: Granularity, spanMs: number, locale?: string): string {
  const d = new Date(iso);
  if (granularity === 'day') return new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric', timeZone: 'UTC' }).format(d);
  if (spanMs <= 2 * DAY_MS) return new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: '2-digit' }).format(d);
  return new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' }).format(d);
}
