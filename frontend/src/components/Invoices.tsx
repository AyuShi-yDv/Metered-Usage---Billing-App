import { useMemo, useState } from 'react';
import { useAccountDetail, useFinalizeInvoice, useInvoicePreview, useInvoices } from '../api/hooks';
import { formatCents, formatInt } from '../lib/money';
import { Async, Badge, Button, EmptyState, ErrorState, LoadingBlock, Panel, Stat } from './ui';

function monthStartInput(): string {
  const now = new Date();
  now.setUTCMonth(now.getUTCMonth() - 1, 1);
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}-01`;
}
function periodStartIso(month: string): string { return new Date(`${month}T00:00:00.000Z`).toISOString(); }
function formatDate(value: string): string { return new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }); }

export function Invoices({ account }: { account: string }) {
  const detail = useAccountDetail(account);
  const [month, setMonth] = useState(monthStartInput);
  const periodStart = useMemo(() => periodStartIso(month), [month]);
  const preview = useInvoicePreview(account, periodStart);
  const invoices = useInvoices(account);
  const finalize = useFinalizeInvoice(account);
  const [message, setMessage] = useState('');

  const print = () => window.print();
  const create = async () => { setMessage(''); try { const result = await finalize.mutateAsync(periodStart); setMessage(result.created ? 'Invoice finalized.' : 'The invoice was already finalized.'); } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not finalize invoice.'); } };

  return <div className="space-y-6">
    <Panel title="Invoice preview" subtitle="Preview a UTC billing month before finalizing it."
      actions={<div className="flex items-center gap-2"><label className="text-sm text-slate-400" htmlFor="invoice-month">Period</label><input id="invoice-month" type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-300" /><Button variant="secondary" onClick={print}>Print / Save PDF</Button></div>}>
      {detail.data && <p className="mb-4 text-sm text-slate-400">Account: <span className="text-slate-200">{detail.data.account_name}</span> · Plan: <span className="text-slate-200">{detail.data.plan_name}</span></p>}
      <Async query={preview} loading={<LoadingBlock height="h-56" label="Loading invoice preview" />}>
        {(invoice) => <div className="space-y-5" id="invoice-document">
          <div className="grid gap-3 sm:grid-cols-4">
            <Stat label="Period" value={`${formatDate(invoice.period_start)} – ${formatDate(invoice.period_end)}`} />
            <Stat label="Billable calls" value={formatInt(invoice.calls)} />
            <Stat label="Overage calls" value={formatInt(invoice.overage_calls)} />
            <Stat label="Total" value={formatCents(invoice.total_cents)} tone={invoice.total_cents > 0 ? 'warn' : undefined} />
          </div>
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-left text-sm"><caption className="sr-only">Invoice line items</caption><thead className="bg-slate-950 text-xs uppercase tracking-wide text-slate-400"><tr><th className="px-4 py-3">Description</th><th className="px-4 py-3 text-right">Quantity</th><th className="px-4 py-3 text-right">Amount</th></tr></thead>
              <tbody className="divide-y divide-slate-800">{invoice.lines.map((line, index) => <tr key={`${line.description}-${index}`}><td className="px-4 py-3 text-slate-200">{line.description}</td><td className="px-4 py-3 text-right tabular-nums text-slate-300">{formatInt(line.quantity)}</td><td className="px-4 py-3 text-right tabular-nums text-slate-100">{formatCents(line.amount_cents)}</td></tr>)}<tr className="font-semibold"><td colSpan={2} className="px-4 py-3 text-right">Total</td><td className="px-4 py-3 text-right">{formatCents(invoice.total_cents)}</td></tr></tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 print:hidden"><div className="text-sm text-slate-400">{invoice.pending_adjustments_cents ? `Pending adjustments: ${formatCents(invoice.pending_adjustments_cents)}` : 'No pending adjustments.'} · {invoice.finalizable ? 'Ready to finalize.' : 'Not currently finalizable.'}</div><Button onClick={create} disabled={!invoice.finalizable || finalize.isPending}>{finalize.isPending ? 'Finalizing…' : 'Finalize invoice'}</Button></div>
          {message && <p role="status" className="text-sm text-emerald-300">{message}</p>}
        </div>}
      </Async>
    </Panel>

    <Panel title="Finalized invoices" subtitle="Previously generated invoices for this account.">
      <Async query={invoices} loading={<LoadingBlock height="h-32" label="Loading invoices" />} isEmpty={(rows) => rows.length === 0} empty={<EmptyState title="No finalized invoices yet" hint="Preview a billing period above and finalize it when ready." />}>
        {(rows) => <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs uppercase tracking-wide text-slate-400"><tr><th className="py-2 pr-4">Period</th><th className="py-2 pr-4">Status</th><th className="py-2 text-right">Total</th></tr></thead><tbody className="divide-y divide-slate-800">{rows.map((invoice) => <tr key={invoice.id}><td className="py-3 pr-4 text-slate-200">{formatDate(invoice.period_start)} – {formatDate(invoice.period_end)}</td><td className="py-3 pr-4"><Badge tone={invoice.status === 'final' ? 'good' : 'warn'}>{invoice.status}</Badge></td><td className="py-3 text-right font-medium tabular-nums">{formatCents(invoice.total_cents)}</td></tr>)}</tbody></table></div>}
      </Async>
    </Panel>
  </div>;
}
