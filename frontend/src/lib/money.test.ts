import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatCents, formatInt, formatMs, percentUsed } from './money.ts';

test('formats integer cents without float arithmetic', () => {
  assert.equal(formatCents(0), '$0.00');
  assert.equal(formatCents(5), '$0.05');
  assert.equal(formatCents(1250), '$12.50');
  assert.equal(formatCents(123456789), '$1,234,567.89');
  assert.equal(formatCents(-250), '-$2.50');
  assert.equal(formatCents(250, { signed: true }), '+$2.50');
});

test('classic float traps stay exact because cents are integers', () => {
  // 0.1 + 0.2 style trap: 10c + 20c must be exactly 30c
  assert.equal(formatCents(10 + 20), '$0.30');
  assert.equal(formatCents(1999 + 1), '$20.00');
});

test('rejects non-integer money instead of silently rounding', () => {
  assert.throws(() => formatCents(12.5), RangeError);
  assert.throws(() => formatCents(Number.NaN), RangeError);
});

test('percentUsed is a whole percent and can exceed 100', () => {
  assert.equal(percentUsed(0, 1000), 0);
  assert.equal(percentUsed(999, 1000), 99);
  assert.equal(percentUsed(1300, 1000), 130);
  assert.equal(percentUsed(5, 0), 100);
  assert.equal(percentUsed(0, 0), 0);
});

test('number helpers', () => {
  assert.equal(formatInt(1234567), '1,234,567');
  assert.equal(formatMs(95.06), '95.1 ms');
  assert.equal(formatMs(1500), '1.50 s');
});
