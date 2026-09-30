import assert from 'node:assert/strict';
import { test } from 'node:test';

process.env.TZ = 'Asia/Kolkata'; // UTC+05:30, no DST: the awkward zone that exposes UTC/local mix-ups

import { formatAxisLabel, formatBucket, fromLocalInput, rangeError, resolveRange, toLocalInput } from './time.ts';

test('datetime-local values are local wall-clock time, not UTC', () => {
  // 2026-09-30 00:00 UTC is 05:30 in Kolkata. Slicing the ISO string (the old bug) would show 00:00.
  assert.equal(toLocalInput('2026-09-30T00:00:00.000Z'), '2026-09-30T05:30');
});

test('local input round-trips to the same UTC instant', () => {
  const iso = '2026-09-30T08:15:00.000Z';
  assert.equal(fromLocalInput(toLocalInput(iso)), iso);
  assert.equal(fromLocalInput('2026-09-30T05:30'), '2026-09-30T00:00:00.000Z');
  assert.equal(fromLocalInput(''), null);
  assert.equal(fromLocalInput('not a date'), null);
  assert.equal(toLocalInput('garbage'), '');
});

test('presets slide with "now"; custom ranges are fixed', () => {
  const now = new Date('2026-09-30T12:00:00Z');
  const day = resolveRange({ preset: '24h' }, now);
  assert.equal(day.end.toISOString(), now.toISOString());
  assert.equal(day.start.toISOString(), '2026-09-29T12:00:00.000Z');
  const custom = resolveRange({ preset: 'custom', start: '2026-01-01T00:00:00.000Z', end: '2026-01-02T00:00:00.000Z' }, now);
  assert.equal(custom.end.toISOString(), '2026-01-02T00:00:00.000Z');
});

test('range validation mirrors the server caps', () => {
  const custom = (start: string, end: string) => ({ preset: 'custom' as const, start, end });
  assert.equal(rangeError({ preset: '30d' }, 'hour'), null);
  assert.match(rangeError({ preset: 'custom' }, 'hour') ?? '', /start and an end/);
  assert.match(rangeError(custom('2026-02-01T00:00:00Z', '2026-01-01T00:00:00Z'), 'hour') ?? '', /after the start/);
  assert.match(rangeError(custom('2026-01-01T00:00:00Z', '2026-06-01T00:00:00Z'), 'hour') ?? '', /at most 92 days/);
  assert.equal(rangeError(custom('2026-01-01T00:00:00Z', '2026-06-01T00:00:00Z'), 'day'), null);
  assert.match(rangeError(custom('2020-01-01T00:00:00Z', '2026-06-01T00:00:00Z'), 'day') ?? '', /at most 1100 days/);
});

test('hour labels use local time; day labels are explicit UTC days', () => {
  assert.match(formatBucket('2026-09-30T00:00:00Z', 'hour', 'en-US'), /5:30/);
  assert.match(formatBucket('2026-09-30T00:00:00Z', 'day', 'en-US'), /Sep 30, 2026 \(UTC day\)/);
  // a UTC day must not slide into the neighbouring day when the viewer is east of UTC
  assert.match(formatBucket('2026-09-30T20:00:00Z', 'day', 'en-US'), /Sep 30/);
});

test('axis labels show time of day only for short spans', () => {
  assert.match(formatAxisLabel('2026-09-30T00:00:00Z', 'hour', 3_600_000 * 24, 'en-US'), /5:30/);
  assert.match(formatAxisLabel('2026-09-30T00:00:00Z', 'hour', 3_600_000 * 24 * 30, 'en-US'), /Sep 30/);
});
