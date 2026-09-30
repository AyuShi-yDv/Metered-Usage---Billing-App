import { useEffect, useState } from 'react';
import { ApiError } from '../api/client';
import { useAccounts } from '../api/hooks';
import type { AccountRow } from '../api/types';
import { useDebounced } from '../hooks/useDebounced';
import { formatInt, percentUsed } from '../lib/money.ts';
import type { SortKey, UrlState } from '../lib/url.ts';
import { Async, Badge, Button, cx, EmptyState, LiveIndicator, LoadingBlock, Panel } from './ui';

const PAGE_SIZE = 10;
const DEFAULT_ORDER: Record<SortKey, 'asc' | 'desc'> = { usage: 'desc', name: 'asc' };

function status(row: AccountRow): { tone: 'good' | 'warn' | 'bad' | 'neutral'; text: string; pct: number } {
  if (!row.included_calls) return { tone: 'neutral', text: 'No plan', pct: 0 };
  const pct = percentUsed(row.calls, row.included_calls);
  if (pct > 100) return { tone: 'bad', text: 'Over allowance', pct };
  if (pct >= 80) return { tone: 'warn', text: 'Near limit', pct };
  return { tone: 'good', text: 'Within plan', pct };
}

export function AccountsTable({ state, update }: { state: UrlState; update: (patch: Partial<UrlState>, mode?: 'push' | 'replace') => void }) {
  // The box is typed into freely; the URL/server only see the value after a short pause.
  const [draft, setDraft] = useState(state.q);
  const debounced = useDebounced(draft, 300);
  useEffect(() => {
    if (debounced !== state.q) update({ q: debounced, page: 1 });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to the debounced text
  }, [debounced]);

  const query = useAccounts({ page: state.page, q: state.q, sort: state.sort, order: state.order, pageSize: PAGE_SIZE });
  const total = query.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    // A shared link (or a shrinking result set) can point past the last page: land on the last real one.
    if (query.data && total > 0 && state.page > pages) update({ page: pages });
  }, [query.data, total, pages, state.page, update]);

  const sortBy = (key: SortKey) => {
    if (state.sort === key) update({ order: state.order === 'asc' ? 'desc' : 'asc', page: 1 });
    else update({ sort: key, order: DEFAULT_ORDER[key], page: 1 });
  };
  const ariaSort = (key: SortKey) => (state.sort !== key ? 'none' : state.order === 'asc' ? 'ascending' : 'descending');
  const arrow = (key: SortKey) => (state.sort !== key ? '' : state.order === 'asc' ? ' ▲' : ' ▼');

  const financeOnly = query.error instanceof ApiError && query.error.status === 401 && query.data === undefined;
  const first = total === 0 ? 0 : (state.page - 1) * PAGE_SIZE + 1;
  const last = Math.min(total, state.page * PAGE_SIZE);

  return (
    <Panel title="Accounts" subtitle="Usage is billable calls this month"
      actions={<><LiveIndicator fetching={query.isFetching} failing={query.isError && query.data !== undefined} />
        <input type="search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Search accounts" aria-label="Search accounts"
          className="w-56 rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-300" /></>}>
      {financeOnly ? (
        <EmptyState title="Listing accounts needs a finance token"
          hint="This token is scoped to a single account. Its usage is available on the Dashboard; sign out and use the finance token to browse all accounts." />
      ) : (
        <Async query={query} loading={<LoadingBlock height="h-64" label="Loading accounts" />}
          isEmpty={(page) => page.data.length === 0}
          empty={<EmptyState title={state.q ? `No accounts match “${state.q}”` : 'No accounts yet'}
            hint={state.q ? 'Check the spelling or clear the search.' : 'Accounts appear once they have sent usage.'}
            action={state.q ? <Button variant="secondary" onClick={() => { setDraft(''); update({ q: '', page: 1 }); }}>Clear search</Button> : undefined} />}>
          {(page) => (
            <>
              <div className={cx('overflow-x-auto transition-opacity', query.isPlaceholderData && 'opacity-60')}>
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Accounts, sortable by name and usage</caption>
                  <thead className="text-xs uppercase tracking-wide text-slate-400">
                    <tr>
                      <th scope="col" aria-sort={ariaSort('name')} className="py-2 pr-4 font-medium"><button type="button" onClick={() => sortBy('name')} className="uppercase tracking-wide hover:text-white focus:outline-none focus:ring-2 focus:ring-cyan-300">Account{arrow('name')}</button></th>
                      <th scope="col" className="py-2 pr-4 font-medium">Plan</th>
                      <th scope="col" aria-sort={ariaSort('usage')} className="py-2 pr-4 text-right font-medium"><button type="button" onClick={() => sortBy('usage')} className="uppercase tracking-wide hover:text-white focus:outline-none focus:ring-2 focus:ring-cyan-300">Calls{arrow('usage')}</button></th>
                      <th scope="col" className="w-40 py-2 pr-4 font-medium">Allowance</th>
                      <th scope="col" className="py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {page.data.map((row) => {
                      const s = status(row);
                      const selected = row.id === state.account;
                      return (
                        <tr key={row.id} className={cx(selected && 'bg-cyan-950/30')}>
                          <td className="py-2 pr-4"><button type="button" aria-current={selected ? 'true' : undefined} onClick={() => update({ account: row.id })}
                            className={cx('text-left hover:underline focus:outline-none focus:ring-2 focus:ring-cyan-300', selected ? 'font-semibold text-cyan-300' : 'text-slate-100')}>{row.name}</button></td>
                          <td className="py-2 pr-4 text-slate-300">{row.plan_name ?? '—'}</td>
                          <td className="py-2 pr-4 text-right tabular-nums text-slate-100">{formatInt(row.calls)}</td>
                          <td className="py-2 pr-4"><div className="h-2 rounded-full bg-slate-800"><div className={cx('h-2 rounded-full', s.tone === 'bad' ? 'bg-rose-500' : s.tone === 'warn' ? 'bg-amber-400' : 'bg-emerald-500')} style={{ width: `${Math.min(100, s.pct)}%` }} /></div></td>
                          <td className="py-2"><Badge tone={s.tone}>{s.text}{s.pct > 0 ? ` · ${s.pct}%` : ''}</Badge></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <nav aria-label="Pagination" className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-400">
                <span>Showing {first}–{last} of {formatInt(total)}</span>
                <span className="flex items-center gap-2">
                  <Button variant="secondary" disabled={state.page <= 1} onClick={() => update({ page: state.page - 1 })}>Previous</Button>
                  <span aria-live="polite">Page {Math.min(state.page, pages)} of {pages}</span>
                  <Button variant="secondary" disabled={state.page >= pages} onClick={() => update({ page: state.page + 1 })}>Next</Button>
                </span>
              </nav>
            </>
          )}
        </Async>
      )}
    </Panel>
  );
}
