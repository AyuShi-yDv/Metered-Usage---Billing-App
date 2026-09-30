// Money is integer cents end to end. The API sends cents; we only split into dollars/cents with
// integer arithmetic at the display edge and never do float math on amounts.

export function formatCents(cents: number, options: { signed?: boolean } = {}): string {
  if (!Number.isSafeInteger(cents)) throw new RangeError(`money must be an integer number of cents, got ${cents}`);
  const negative = cents < 0;
  const abs = Math.abs(cents);
  const dollars = Math.trunc(abs / 100).toLocaleString('en-US');
  const rest = String(abs % 100).padStart(2, '0');
  const sign = negative ? '-' : options.signed && cents > 0 ? '+' : '';
  return `${sign}$${dollars}.${rest}`;
}

export function formatInt(value: number): string {
  return Math.round(value).toLocaleString('en-US');
}

/** Share of the allowance consumed, as a whole percent (not capped, so 130 means 30% over). */
export function percentUsed(calls: number, included: number): number {
  if (included <= 0) return calls > 0 ? 100 : 0;
  return Math.floor((calls * 100) / included);
}

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms.toFixed(1)} ms`;
}
