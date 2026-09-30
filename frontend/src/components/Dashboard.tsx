import { useMtd, useP95, useUsageSeries } from '../api/hooks';
import { formatCents, formatInt, percentUsed } from '../lib/money.ts';
import { rangeError } from '../lib/time.ts';
import type { UrlState } from '../lib/url.ts';
import { P95Table } from './P95Table';
import { RangeControls } from './RangeControls';
import { TopOverage } from './TopOverage';
import { UsageChart } from './UsageChart';
import { Async, EmptyState, LiveIndicator, LoadingBlock, Panel, Stat } from './ui';

export function Dashboard({ state, update }: { state: UrlState; update: (patch: Partial<UrlState>, mode?: 'push' | 'replace') => void }) {
  const { account, granularity, range } = state;
  const series = useUsageSeries(account, granularity, range);
  const p95 = useP95(account, granularity, range);
  const mtd = useMtd(account);
  const problem = rangeError(range, granularity);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Async query={mtd} loading={<><LoadingBlock height="h-20" label="Loading month-to-date usage" /><LoadingBlock height="h-20" /><LoadingBlock height="h-20" /><LoadingBlock height="h-20" /></>}>
          {(m) => {
            const pct = percentUsed(m.calls, m.included_calls);
            return (
              <>
                <Stat label="Calls this month" value={formatInt(m.calls)} hint={`${pct}% of ${formatInt(m.included_calls)} included`} tone={pct > 100 ? 'bad' : pct >= 80 ? 'warn' : undefined} />
                <Stat label="Overage so far" value={formatInt(m.overage_calls)} hint="calls beyond the allowance" tone={m.overage_calls > 0 ? 'bad' : undefined} />
                <Stat label="Projected month-end overage" value={formatInt(m.projected_overage_calls)} hint="calls, at the current pace" tone={m.projected_overage_calls > 0 ? 'warn' : undefined} />
                <Stat label="Projected overage cost" value={formatCents(m.projected_overage_cents)} hint={`${formatCents(m.overage_cents_per_1000)} per 1,000 calls`} tone={m.projected_overage_cents > 0 ? 'warn' : undefined} />
              </>
            );
          }}
        </Async>
      </div>

      <Panel title="Billable calls over time"
        subtitle="Only 2xx and 4xx responses are billable. Empty periods are shown as zero."
        actions={<LiveIndicator fetching={series.isFetching} failing={series.isError && series.data !== undefined} />}>
        <div className="mb-4"><RangeControls range={range} granularity={granularity}
          onRange={(next) => update({ range: next })} onGranularity={(g) => update({ granularity: g })} /></div>
        {problem ? (
          <EmptyState title="This range can't be charted" hint={problem} />
        ) : (
          <Async query={series} loading={<LoadingBlock height="h-72" label="Loading usage chart" />}
            isEmpty={(points) => points.length === 0}
            empty={<EmptyState title="No time buckets in this range" hint="Pick a longer range." />}>
            {(points) => <UsageChart points={points} granularity={granularity} />}
          </Async>
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="p95 latency by endpoint" subtitle="Over the selected range">
          {problem ? <EmptyState title="Choose a valid range" hint={problem} /> : (
            <Async query={p95} loading={<LoadingBlock height="h-32" label="Loading latency" />}>{(rows) => <P95Table rows={rows} />}</Async>
          )}
        </Panel>
        <TopOverage onSelect={(id) => update({ account: id, view: 'accounts' }, 'push')} />
      </div>
    </div>
  );
}
