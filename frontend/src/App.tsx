import { useEffect, useState } from 'react';
import type { MouseEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { onAuthFailure, tokenStore } from './api/client';
import { useAccountDetail } from './api/hooks';
import { AccountDetail } from './components/AccountDetail';
import { AccountsTable } from './components/AccountsTable';
import { ComingSoon } from './components/ComingSoon';
import { Dashboard } from './components/Dashboard';
import { TokenGate } from './components/TokenGate';
import { cx } from './components/ui';
import { useUrlState } from './hooks/useUrlState';
import { localTimeZoneName } from './lib/time.ts';
import { toSearch } from './lib/url.ts';
import type { UrlState, View } from './lib/url.ts';

const NAV: Array<{ view: View; label: string }> = [
  { view: 'dashboard', label: 'Dashboard' },
  { view: 'accounts', label: 'Accounts' },
  { view: 'invoices', label: 'Invoices' },
  { view: 'keys', label: 'API keys' },
  { view: 'plans', label: 'Plans' },
];

function AccountName({ id }: { id: string }) {
  const detail = useAccountDetail(id);
  return <span className="font-medium text-slate-100">{detail.data?.account_name ?? `${id.slice(0, 8)}…`}</span>;
}

function Shell({ onSignOut }: { onSignOut: () => void }) {
  const [state, update] = useUrlState();
  const go = (event: MouseEvent, view: View) => {
    // Plain left-click navigates in-app; modified clicks keep the browser's "open in new tab" behaviour.
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    update({ view }, 'push');
  };
  const href = (view: View) => `${window.location.pathname}${toSearch({ ...state, view })}`;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-950/80 print:hidden">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-cyan-400">Metered billing</p>
            <p className="text-sm text-slate-400">Account: <AccountName id={state.account} />{' '}
              <button type="button" onClick={() => update({ view: 'accounts' }, 'push')} className="ml-1 text-cyan-300 hover:underline focus:outline-none focus:ring-2 focus:ring-cyan-300">change</button>
            </p>
          </div>
          <nav aria-label="Primary" className="flex flex-wrap gap-1">
            {NAV.map((item) => (
              <a key={item.view} href={href(item.view)} onClick={(e) => go(e, item.view)} aria-current={state.view === item.view ? 'page' : undefined}
                className={cx('rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-300',
                  state.view === item.view ? 'bg-slate-800 font-medium text-white' : 'text-slate-400 hover:text-white')}>
                {item.label}
              </a>
            ))}
            <button type="button" onClick={onSignOut} className="ml-2 rounded-md px-3 py-1.5 text-sm text-slate-400 hover:text-white focus:outline-none focus:ring-2 focus:ring-cyan-300">Sign out</button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl space-y-6 px-6 py-6">
        <CurrentView state={state} update={update} />
      </main>
      <footer className="mx-auto max-w-6xl px-6 pb-8 text-xs text-slate-500 print:hidden">
        Times are shown in your local time zone ({localTimeZoneName()}). Stored and billed in UTC; daily buckets and invoice months are UTC.
      </footer>
    </div>
  );
}

function CurrentView({ state, update }: { state: UrlState; update: (patch: Partial<UrlState>, mode?: 'push' | 'replace') => void }) {
  switch (state.view) {
    case 'accounts':
      return (<><AccountsTable state={state} update={update} /><AccountDetail account={state.account} /></>);
    case 'invoices':
      return <ComingSoon title="Invoice preview" />;
    case 'keys':
      return <ComingSoon title="API keys" />;
    case 'plans':
      return <ComingSoon title="Plans" />;
    default:
      return <Dashboard state={state} update={update} />;
  }
}

export function App() {
  const queryClient = useQueryClient();
  const [token, setToken] = useState(() => tokenStore.get());
  const [message, setMessage] = useState('');

  useEffect(() => onAuthFailure(() => {
    tokenStore.clear();
    queryClient.clear();
    setToken('');
    setMessage('That token was rejected by the server. Enter a valid dashboard token.');
  }), [queryClient]);

  if (!token) {
    return <TokenGate message={message} onSubmit={(value) => { tokenStore.set(value); queryClient.clear(); setMessage(''); setToken(value); }} />;
  }
  return <Shell onSignOut={() => { tokenStore.clear(); queryClient.clear(); setMessage(''); setToken(''); }} />;
}
