import { useState } from 'react';
import { useAccountDetail, usePlans, useSchedulePlanChange, useWhatIf } from '../api/hooks';
import { formatCents, formatInt } from '../lib/money';
import { Async, Badge, Button, EmptyState, Panel, Stat } from './ui';
import { errorMessage } from './ui';

function localDateTimePlusMinutes(minutes: number): string { const d = new Date(Date.now() + minutes * 60000); const pad = (n: number) => String(n).padStart(2, '0'); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; }
function isoFromLocal(value: string): string { return new Date(value).toISOString(); }

export function Plans({ account }: { account: string }) {
  const detail = useAccountDetail(account);
  const plans = usePlans(account);
  const [selected, setSelected] = useState('');
  const [effectiveAt, setEffectiveAt] = useState(() => localDateTimePlusMinutes(10));
  const whatIf = useWhatIf(account, selected);
  const schedule = useSchedulePlanChange(account);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const activePlanId = detail.data?.plan_id ?? '';

  const scheduleChange = async () => { if (!selected) return; setError(''); setMessage(''); try { await schedule.mutateAsync({ planId: selected, effectiveAt: isoFromLocal(effectiveAt) }); setMessage('Plan change scheduled successfully.'); } catch (e) { setError(errorMessage(e)); } };

  return <div className="space-y-6">
    <Panel title="Plan comparison" subtitle="Compare the account's current plan with another plan using the backend what-if calculation.">
      <Async query={plans} isEmpty={(rows) => rows.length === 0} empty={<EmptyState title="No plans available" />}>
        {(rows) => <div className="space-y-5"><div className="grid gap-4 sm:grid-cols-3">{rows.map((plan) => <button key={plan.id} type="button" onClick={() => setSelected(plan.id)} className={`rounded-lg border p-4 text-left transition ${selected === plan.id ? 'border-cyan-500 bg-cyan-950/30' : 'border-slate-800 bg-slate-950/50 hover:border-slate-600'}`}><div className="flex items-center justify-between gap-2"><h3 className="font-semibold text-slate-100">{plan.name}</h3>{plan.id === activePlanId && <Badge tone="good">Current</Badge>}</div><p className="mt-3 text-2xl font-semibold">{formatCents(plan.monthly_base_fee_cents)}<span className="text-xs font-normal text-slate-500"> / month</span></p><p className="mt-2 text-sm text-slate-400">{formatInt(plan.included_calls)} included calls</p><p className="text-sm text-slate-400">{formatCents(plan.overage_cents_per_1000)} per 1,000 overage</p></button>)}</div>
          {selected && selected !== activePlanId && <Async query={whatIf} loading={<p className="text-sm text-slate-400">Calculating comparison…</p>}>{(comparison) => <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><div className="grid gap-4 sm:grid-cols-3"><Stat label="Current cost" value={formatCents(comparison.current_cost_cents)} hint={comparison.current_plan_name} /><Stat label="Alternative cost" value={formatCents(comparison.alternative_cost_cents)} hint={comparison.alternative_plan_name} /><Stat label="Difference" value={formatCents(comparison.difference_cents, { signed: true })} /></div><p className="mt-4 text-sm text-slate-400">The comparison is based on the previous 30 days of usage, as defined by the backend what-if endpoint.</p></div>}</Async>}
        </div>}
      </Async>
    </Panel>

    <Panel title="Schedule a plan change" subtitle="Changes are effective at a future UTC timestamp and are recorded as effective-dated plan history.">
      <div className="grid gap-4 md:grid-cols-[1fr_auto_auto] md:items-end"><label className="text-sm text-slate-300">New plan<select value={selected} onChange={(e) => setSelected(e.target.value)} className="mt-1 block w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-300"><option value="">Select a plan…</option>{plans.data?.filter((p) => p.id !== activePlanId).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label className="text-sm text-slate-300">Effective at<input type="datetime-local" value={effectiveAt} onChange={(e) => setEffectiveAt(e.target.value)} className="mt-1 block rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-300" /></label><Button onClick={() => void scheduleChange()} disabled={!selected || schedule.isPending}>{schedule.isPending ? 'Scheduling…' : 'Schedule change'}</Button></div>
      {message && <p role="status" className="mt-4 text-sm text-emerald-300">{message}</p>}{error && <p role="alert" className="mt-4 text-sm text-rose-300">{error}</p>}
    </Panel>
  </div>;
}
