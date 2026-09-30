// Invoice periods are UTC calendar months. The API addresses one by its first instant.

/** "2026-09" -> "2026-09-01T00:00:00Z" (null when the input is not a valid year-month). */
export function monthToPeriodStart(month: string): string | null {
  const match = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month);
  return match ? `${match[1]}-${match[2]}-01T00:00:00Z` : null;
}

/** The UTC year-month of an instant, e.g. for defaulting the picker to the last full month. */
export function utcMonthOf(date: Date, monthsBack = 0): string {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() - monthsBack, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

function csvCell(value: string | number): string {
  const text = String(value);
  // Text cells that start like a formula are neutralised (CSV injection); real numbers are left untouched.
  const safe = typeof value === 'string' && /^[=+\-@]/.test(text) ? `'${text}` : text;
  return /[",\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export interface CsvLine { description: string; quantity: number; amount_cents: number }

/** Line items as CSV with amounts in whole-cent integers plus a formatted total row. */
export function invoiceCsv(lines: CsvLine[], totalCents: number): string {
  const rows = [['description', 'quantity', 'amount_cents'], ...lines.map((l) => [l.description, l.quantity, l.amount_cents]), ['TOTAL', '', totalCents]];
  return rows.map((r) => r.map(csvCell).join(',')).join('\r\n') + '\r\n';
}
