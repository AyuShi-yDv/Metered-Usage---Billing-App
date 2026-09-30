import assert from 'node:assert/strict';
import { test } from 'node:test';
import { invoiceCsv, monthToPeriodStart, utcMonthOf } from './period.ts';

test('a month maps to the first UTC instant of that month', () => {
  assert.equal(monthToPeriodStart('2026-09'), '2026-09-01T00:00:00Z');
  assert.equal(monthToPeriodStart('2026-9'), null);
  assert.equal(monthToPeriodStart('2026-13'), null);
  assert.equal(monthToPeriodStart(''), null);
});

test('utcMonthOf handles year boundaries', () => {
  assert.equal(utcMonthOf(new Date('2026-01-15T12:00:00Z'), 1), '2025-12');
  assert.equal(utcMonthOf(new Date('2026-09-30T23:59:59Z')), '2026-09');
});

test('invoice CSV keeps cents as integers, quotes commas and neutralises formulas', () => {
  const csv = invoiceCsv([
    { description: 'Overage: 1,500 calls', quantity: 1500, amount_cents: 250 },
    { description: '=HYPERLINK("x")', quantity: 1, amount_cents: 1000 },
  ], 1250);
  const rows = csv.trim().split('\r\n');
  assert.equal(rows[0], 'description,quantity,amount_cents');
  assert.equal(rows[1], '"Overage: 1,500 calls",1500,250');
  assert.ok(rows[2].startsWith(`"'=HYPERLINK(""x"")"`));
  assert.equal(rows[3], 'TOTAL,,1250');
});
