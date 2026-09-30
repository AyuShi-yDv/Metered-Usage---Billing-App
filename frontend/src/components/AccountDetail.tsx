import { ApiError } from '../api/client';
import { useAccountDetail } from '../api/hooks';
import { formatCents, formatInt, percentUsed } from '../lib/money.ts';
import { P95Table } from './P95Table';
import { Async, cx, EmptyState, ErrorState, LiveIndicator, LoadingBlock, Panel, Stat } from './ui';

export function AllowanceBar({ calls, included }: { calls: number; included: number }) {
  const pct = percentUsed(calls, included);
  const shown = Math.min(100, pct);
  const tone = pct > 100 ? 'bg-rose-500' : pct >= 80 ? 'bg-amber-400' : 'bg-emerald-500';
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span className="text-slate-300">{formatInt(calls)} of {formatInt(included)} included calls</span>
        <span className={cx('font-medium tabular-nums', pct > 100 ? 'text-rose-300' : 'text-slate-200')}>{pct}%{pct > 100 ? ` (${pct - 100}% over)` : ''}</span>
      </div>
      <div role="progressbar" aria-label="Allowance consumed this month" aria-valuemin={0} aria-valuemax={100} aria-valuenow={shown}
        className="h-3 w-full overflow-hidden rounded-full bg-slate-800">
        <div className={cx('h-full rounded-full transition-all duration-500', tone)} style={{ width: `${shown}%` }} />
      </div>
    </div>
  );
}

export function AccountDetail({ account }: { account: string }) {
  const query = useAccountDetail(account);
  const noPlan = query.error instanceof ApiError && query.error.status === 404 && query.data === undefined;
  return (
    <Panel title={query.data ? query.data.account_name : 'Account details'} subtitle="Current plan, allowance and latency this month"
      actions={<LiveIndicator fetching={query.isFetching} failing={query.isError && query.data !== undefined} />}>
      {noPlan ? (
        <EmptyState title="This account has no active plan" hint="Usage is recorded, but there is nothing to rate it against until a plan is assigned." />
      ) : query.error instanceof ApiError && query.error.status === 403 && query.data === undefined ? (
        <ErrorState error={query.error} title="This token cannot view that account" />
      ) : (
        <Async query={query} loading={<LoadingBlock height="h-48" label="Loading account" />}>
          {(d) => (
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Stat label="Plan" value={d.plan_name} hint={`${formatCents(d.monthly_base_fee_cents)} / month base`} />
                <Stat label="Overage rate" value={formatCents(d.overage_cents_per_1000)} hint="per 1,000 calls" />
                <Stat label="Calls this month" value={formatInt(d.calls)} />
                <Stat label="Projected overage cost" value={formatCents(d.projected_overage_cents)} hint="at the current pace, end of month" tone={d.projected_overage_cents > 0 ? 'warn' : undefined} />
              </div>
              <AllowanceBar calls={d.calls} included={d.included_calls} />
              <div>
                <h3 className="mb-2 text-sm font-medium text-slate-300">p95 latency by endpoint (month to date)</h3>
                <P95Table rows={d.endpoints} />
              </div>
            </div>
          )}
        </Async>
      )}
    </Panel>
  );
}
