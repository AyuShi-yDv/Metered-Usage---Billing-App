import { useTopOverage } from '../api/hooks';
import { ApiError } from '../api/client';
import { formatCents } from '../lib/money.ts';
import { Async, EmptyState, Panel } from './ui';

/** Finance-only: top ten accounts by overage this month (DENSE_RANK) with month-over-month change. */
export function TopOverage({ onSelect }: { onSelect: (accountId: string) => void }) {
  const query = useTopOverage();
  if (query.error instanceof ApiError && query.error.status === 401) return null; // customer token: finance-only panel is simply not offered
  return (
    <Panel title="Top accounts by overage" subtitle="This month so far, compared with the same point last month">
      <Async query={query} isEmpty={(rows) => rows.length === 0}
        empty={<EmptyState title="No account is over its allowance" hint="Accounts appear here once they exceed their plan's included calls." />}>
        {(rows) => (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Top accounts by overage</caption>
              <thead className="text-xs uppercase tracking-wide text-slate-400">
                <tr><th scope="col" className="py-2 pr-3 font-medium">Rank</th><th scope="col" className="py-2 pr-3 font-medium">Account</th><th scope="col" className="py-2 pr-3 text-right font-medium">Overage</th><th scope="col" className="py-2 text-right font-medium">vs last month</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="py-2 pr-3 tabular-nums text-slate-400">#{row.rank}</td>
                    <td className="py-2 pr-3"><button type="button" onClick={() => onSelect(row.id)} className="text-cyan-300 hover:underline focus:outline-none focus:ring-2 focus:ring-cyan-300">{row.name}</button></td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-100">{formatCents(row.overage_cents)}</td>
                    <td className={`py-2 text-right tabular-nums ${row.month_over_month_change_cents > 0 ? 'text-rose-300' : row.month_over_month_change_cents < 0 ? 'text-emerald-300' : 'text-slate-400'}`}>{formatCents(row.month_over_month_change_cents, { signed: true })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Async>
    </Panel>
  );
}
