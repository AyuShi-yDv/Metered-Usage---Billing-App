import assert from 'node:assert/strict';
import { test } from 'node:test';
import { areaPath, linePath, nearestIndex, niceCeil, tickIndexes, xFor, yFor, yTicks } from './chart.ts';

const plot = { x0: 10, y0: 10, width: 100, height: 50 };

test('niceCeil rounds up to 1/2/5 x 10^n', () => {
  assert.deepEqual([0, 1, 1.5, 3, 7, 12, 480, 5001].map(niceCeil), [1, 1, 2, 5, 10, 20, 500, 10000]);
});

test('yTicks are integers and end at the max', () => {
  assert.deepEqual(yTicks(1), [0, 1]);
  assert.deepEqual(yTicks(3), [0, 1, 2, 3]);
  assert.deepEqual(yTicks(100), [0, 25, 50, 75, 100]);
});

test('tickIndexes always include first and last and never duplicate', () => {
  assert.deepEqual(tickIndexes(0), []);
  assert.deepEqual(tickIndexes(3), [0, 1, 2]);
  const many = tickIndexes(721);
  assert.equal(many[0], 0);
  assert.equal(many[many.length - 1], 720);
  assert.equal(new Set(many).size, many.length);
});

test('zero values sit on the baseline (zero-filled hours stay visible)', () => {
  assert.equal(yFor(0, 10, plot), 60);
  assert.equal(yFor(10, 10, plot), 10);
  assert.equal(yFor(0, 0, plot), 60); // empty series must not divide by zero
});

test('paths cover every point and area closes on the baseline', () => {
  const values = [0, 5, 0, 10];
  const line = linePath(values, 10, plot);
  assert.equal(line.split('L').length - 1, 3);
  assert.ok(line.startsWith('M10.0 60.0'));
  assert.ok(areaPath(values, 10, plot).endsWith('L10.0 60.0 Z'));
  assert.equal(areaPath([], 10, plot), '');
  assert.equal(xFor(0, 1, plot), 60); // a single point is centred
});

test('nearestIndex clamps to the series', () => {
  assert.equal(nearestIndex(-500, 5, plot), 0);
  assert.equal(nearestIndex(500, 5, plot), 4);
  assert.equal(nearestIndex(60, 5, plot), 2);
  assert.equal(nearestIndex(60, 1, plot), 0);
});
