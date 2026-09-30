import { useEffect, useState } from 'react';
import type { MouseEvent, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { onAuthFailure, tokenStore } from './api/client';
import { useAccountDetail } from './api/hooks';
import { AccountDetail } from './components/AccountDetail';
import { AccountsTable } from './components/AccountsTable';
import { Invoices } from './components/Invoices';
import { ApiKeys } from './components/ApiKeys';
import { Plans } from './components/Plans';
import { Dashboard } from './components/Dashboard';
import { TokenGate } from './components/TokenGate';
import { cx } from './components/ui';
import { useUrlState } from './hooks/useUrlState';
import { localTimeZoneName } from './lib/time.ts';
import { toSearch } from './lib/url.ts';
import type { UrlState, View } from './lib/url.ts';

const NAV: Array<{ view: View; label: string; icon: string; description: string }> = [
  { view: 'dashboard', label: 'Overview', icon: '⌂', description: 'Usage & health' },
  { view: 'accounts', label: 'Accounts', icon: '◫', description: 'Customers & usage' },
  { view: 'invoices', label: 'Invoices', icon: '▤', description: 'Billing periods' },
  { view: 'keys', label: 'API keys', icon: '⌁', description: 'Access management' },
  { view: 'plans', label: 'Plans', icon: '◇', description: 'Compare & change' },
];

const VIEW_META: Record<View, { eyebrow: string; title: string; description: string }> = {
  dashboard: { eyebrow: 'Finance workspace', title: 'Usage overview', description: 'Monitor billable traffic, latency, allowance consumption and projected overage.' },
  accounts: { eyebrow: 'Customer operations', title: 'Accounts', description: 'Search customers, inspect usage and open account-level billing details.' },
  invoices: { eyebrow: 'Finance', title: 'Invoices', description: 'Preview monthly charges, review adjustments and finalize printable invoices.' },
  keys: { eyebrow: 'Developer access', title: 'API keys', description: 'Create, rotate and revoke customer credentials. Secrets are shown only once.' },
  plans: { eyebrow: 'Pricing & billing', title: 'Plans', description: 'Compare current pricing with alternatives and schedule effective-dated changes.' },
};

function AccountName({ id }: { id: string }) {
  const detail = useAccountDetail(id);
  return <span className="font-medium text-slate-100">{detail.data?.account_name ?? `${id.slice(0, 8)}…`}</span>;
}

function NavIcon({ icon }: { icon: string }) {
  return <span aria-hidden="true" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white/[0.04] text-sm text-slate-400">{icon}</span>;
}

function Shell({ onSignOut }: { onSignOut: () => void }) {
  const [state, update] = useUrlState();
  const [mobileOpen, setMobileOpen] = useState(false);
  const meta = VIEW_META[state.view];
  const go = (event: MouseEvent, view: View) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    update({ view }, 'push');
    setMobileOpen(false);
  };
  const href = (view: View) => `${window.location.pathname}${toSearch({ ...state, view })}`;

  return (
    <div className="min-h-screen bg-[#070b14] text-slate-100">
      <div className="pointer-events-none fixed inset-0 -z-0 overflow-hidden">
        <div className="absolute -left-32 -top-40 h-96 w-96 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="absolute right-0 top-1/3 h-80 w-80 rounded-full bg-violet-500/10 blur-3xl" />
      </div>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-white/[0.07] bg-[#090e19]/95 px-4 py-5 backdrop-blur-xl lg:block">
        <div className="flex h-full flex-col">
          <div className="flex items-center gap-3 px-2">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-cyan-300 to-blue-600 font-black text-slate-950 shadow-lg shadow-cyan-500/10">M</div>
            <div>
              <p className="text-sm font-semibold tracking-tight">Metered<span className="text-cyan-300">Flow</span></p>
              <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Billing console</p>
            </div>
          </div>
          <div className="mt-8 px-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-600">Workspace</div>
          <nav aria-label="Primary" className="mt-2 space-y-1">
            {NAV.map((item) => (
              <a key={item.view} href={href(item.view)} onClick={(e) => go(e, item.view)} aria-current={state.view === item.view ? 'page' : undefined}
                className={cx('group flex items-center gap-3 rounded-xl px-2.5 py-2.5 transition focus:outline-none focus:ring-2 focus:ring-cyan-300', state.view === item.view ? 'bg-cyan-400/10 text-white ring-1 ring-cyan-300/10' : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-100')}>
                <NavIcon icon={item.icon} />
                <span className="min-w-0 flex-1"><span className="block text-sm font-medium">{item.label}</span><span className="block text-[11px] text-slate-600 group-hover:text-slate-500">{item.description}</span></span>
                {state.view === item.view && <span className="h-1.5 w-1.5 rounded-full bg-cyan-300 shadow-[0_0_12px_rgba(103,232,249,.9)]" />}
              </a>
            ))}
          </nav>
          <div className="mt-auto rounded-2xl border border-white/[0.07] bg-white/[0.025] p-3">
            <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.8)]" /><span className="text-xs font-medium text-slate-300">System connected</span></div>
            <p className="mt-2 text-[11px] leading-5 text-slate-500">PostgreSQL · RabbitMQ · FastAPI</p>
          </div>
        </div>
      </aside>

      <div className="relative z-10 lg:pl-64">
        <header className="sticky top-0 z-30 border-b border-white/[0.07] bg-[#070b14]/80 backdrop-blur-xl print:hidden">
          <div className="mx-auto flex max-w-[1500px] items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => setMobileOpen(!mobileOpen)} className="grid h-10 w-10 place-items-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-slate-300 lg:hidden" aria-label="Open navigation">☰</button>
              <div className="lg:hidden"><p className="text-sm font-semibold">Metered<span className="text-cyan-300">Flow</span></p><p className="text-[9px] uppercase tracking-[0.2em] text-slate-600">Billing console</p></div>
              <div className="hidden lg:block"><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300">{meta.eyebrow}</p><h1 className="text-lg font-semibold tracking-tight">{meta.title}</h1></div>
            </div>
            <div className="flex items-center gap-2 sm:gap-3">
              <div className="hidden rounded-full border border-white/[0.07] bg-white/[0.03] px-3 py-1.5 text-xs text-slate-400 sm:block">UTC billing · {localTimeZoneName()} display</div>
              <button type="button" onClick={onSignOut} className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs font-medium text-slate-400 hover:bg-white/[0.06] hover:text-white focus:outline-none focus:ring-2 focus:ring-cyan-300">Sign out</button>
            </div>
          </div>
        </header>

        {mobileOpen && <div className="fixed inset-0 z-50 bg-[#070b14]/95 p-5 backdrop-blur-xl lg:hidden"><div className="flex items-center justify-between"><span className="font-semibold">Navigation</span><button onClick={() => setMobileOpen(false)} className="rounded-lg px-3 py-2 text-slate-400">Close</button></div><nav className="mt-6 space-y-2">{NAV.map((item) => <a key={item.view} href={href(item.view)} onClick={(e) => go(e, item.view)} className={cx('flex items-center gap-3 rounded-xl p-3', state.view === item.view ? 'bg-cyan-400/10 text-white' : 'text-slate-400')}><NavIcon icon={item.icon}/><span>{item.label}</span></a>)}</nav></div>}

        <main className="mx-auto max-w-[1500px] space-y-6 px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
          <div className="lg:hidden"><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300">{meta.eyebrow}</p><h1 className="mt-1 text-2xl font-semibold tracking-tight">{meta.title}</h1><p className="mt-1 max-w-2xl text-sm text-slate-500">{meta.description}</p></div>
          <div className="hidden items-end justify-between lg:flex"><div><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300">{meta.eyebrow}</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">{meta.title}</h2><p className="mt-1 text-sm text-slate-500">{meta.description}</p></div><div className="rounded-xl border border-white/[0.07] bg-white/[0.025] px-3 py-2 text-right"><p className="text-[10px] uppercase tracking-wider text-slate-600">Active account</p><p className="text-sm"><AccountName id={state.account} /></p></div></div>
          <CurrentView state={state} update={update} />
        </main>
        <footer className="mx-auto max-w-[1500px] px-4 pb-8 text-xs text-slate-600 sm:px-6 lg:px-8 print:hidden">
          <div className="flex flex-wrap justify-between gap-3 border-t border-white/[0.05] pt-5"><span>MeteredFlow billing console · production-style demo UI</span><span>Times displayed locally ({localTimeZoneName()}); billing remains UTC.</span></div>
        </footer>
      </div>
    </div>
  );
}

function CurrentView({ state, update }: { state: UrlState; update: (patch: Partial<UrlState>, mode?: 'push' | 'replace') => void }) {
  switch (state.view) {
    case 'accounts': return (<><AccountsTable state={state} update={update} /><AccountDetail account={state.account} /></>);
    case 'invoices': return <Invoices account={state.account} />;
    case 'keys': return <ApiKeys account={state.account} />;
    case 'plans': return <Plans account={state.account} />;
    default: return <Dashboard state={state} update={update} />;
  }
}

export function App() {
  const queryClient = useQueryClient();
  const [token, setToken] = useState(() => tokenStore.get());
  const [message, setMessage] = useState('');
  useEffect(() => onAuthFailure(() => { tokenStore.clear(); queryClient.clear(); setToken(''); setMessage('That token was rejected by the server. Enter a valid dashboard token.'); }), [queryClient]);
  if (!token) return <TokenGate message={message} onSubmit={(value) => { tokenStore.set(value); queryClient.clear(); setMessage(''); setToken(value); }} />;
  return <Shell onSignOut={() => { tokenStore.clear(); queryClient.clear(); setMessage(''); setToken(''); }} />;
}
