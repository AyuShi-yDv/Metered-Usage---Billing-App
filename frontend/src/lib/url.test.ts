import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DEFAULT_STATE, parseUrl, toSearch } from './url.ts';

test('an empty URL is the default state and serialises back to nothing', () => {
  assert.deepEqual(parseUrl(''), DEFAULT_STATE);
  assert.equal(toSearch(DEFAULT_STATE), '');
});

test('state round-trips through the URL', () => {
  const state = {
    ...DEFAULT_STATE, view: 'accounts' as const, granularity: 'day' as const, q: 'acme corp', sort: 'name' as const,
    order: 'asc' as const, page: 3, month: '2026-08', account: '11111111-2222-3333-4444-555555555555',
    range: { preset: 'custom' as const, start: '2026-08-01T00:00:00.000Z', end: '2026-08-31T00:00:00.000Z' },
  };
  assert.deepEqual(parseUrl(toSearch(state)), state);
});

test('hostile or malformed parameters fall back to safe defaults', () => {
  const parsed = parseUrl('?view=admin&account=../../etc&g=week&range=custom&start=nope&end=nope&page=-4&sort=DROP&order=x&month=2026-13');
  assert.deepEqual(parsed, DEFAULT_STATE);
  assert.equal(parseUrl('?page=abc').page, 1);
  assert.equal(parseUrl(`?q=${'x'.repeat(500)}`).q.length, 100);
});

test('a custom range without both ends degrades to the sliding default', () => {
  assert.deepEqual(parseUrl('?range=custom&start=2026-01-01T00:00:00Z').range, { preset: '24h' });
});
