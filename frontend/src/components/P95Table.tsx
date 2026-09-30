import type { P95Row } from '../api/types';
import { formatMs } from '../lib/money.ts';
import { EmptyState } from './ui';

/** p95 latency per endpoint with an inline bar scaled to the slowest endpoint. */
export function P95Table({ rows }: { rows: Array<Pick<P95Row, 'endpoint' | 'p95_duration_ms'> & { calls?: number }> }) {
  if (rows.length === 0) return <EmptyState title="No requests in this period" hint="p95 latency appears once the account has traffic." />;
  const slowest = Math.max(...rows.map((r) => r.p95_duration_ms), 1);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">p95 latency per endpoint</caption>
        <thead className="text-xs uppercase tracking-wide text-slate-400">
          <tr><th scope="col" className="py-2 pr-4 font-medium">Endpoint</th><th scope="col" className="py-2 pr-4 font-medium">p95 latency</th><th scope="col" className="w-1/2 py-2 font-medium"><span className="sr-only">Relative</span></th></tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {rows.map((row) => (
            <tr key={row.endpoint}>
              <td className="py-2 pr-4 font-mono text-slate-200">{row.endpoint}</td>
              <td className="py-2 pr-4 tabular-nums text-slate-100">{formatMs(row.p95_duration_ms)}{row.calls !== undefined && <span className="ml-2 text-xs text-slate-500">{row.calls.toLocaleString('en-US')} calls</span>}</td>
              <td className="py-2"><div className="h-2 rounded-full bg-slate-800"><div className="h-2 rounded-full bg-cyan-500" style={{ width: `${Math.max(2, Math.round((row.p95_duration_ms / slowest) * 100))}%` }} /></div></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
