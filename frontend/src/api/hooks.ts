import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { AccountDetailData, AccountsPage, ApiKeyInfo, CreatedKey, FinalizedInvoice, FinalizeResult, InvoicePreviewData, MtdReport, P95Row, Plan, PlanChangeResult, TopOverageRow, UsagePoint, WhatIfResult } from './types';
import { rangeError, resolveRange } from '../lib/time.ts';
import type { Granularity, RangeSelection } from '../lib/time.ts';
import type { SortKey, SortOrder } from '../lib/url.ts';

export const LIVE_MS = 5000;
const rangeKey = (range: RangeSelection) => [range.preset, range.start ?? null, range.end ?? null] as const;
function rangeParams(range: RangeSelection) { const { start, end } = resolveRange(range); return { start: start.toISOString(), end: end.toISOString() }; }

export function useUsageSeries(account: string, granularity: Granularity, range: RangeSelection) {
  return useQuery({ queryKey: ['usage', account, granularity, ...rangeKey(range)], queryFn: async ({ signal }) => (await api.get<{ data: UsagePoint[] }>('/reports/usage', { report: 'time_series', account_id: account, granularity, ...rangeParams(range) }, { signal })).data, enabled: rangeError(range, granularity) === null, refetchInterval: range.preset === 'custom' ? false : LIVE_MS, placeholderData: keepPreviousData });
}
export function useP95(account: string, granularity: Granularity, range: RangeSelection) {
  return useQuery({ queryKey: ['p95', account, granularity, ...rangeKey(range)], queryFn: async ({ signal }) => (await api.get<{ data: P95Row[] }>('/reports/usage', { report: 'p95', account_id: account, granularity, ...rangeParams(range) }, { signal })).data, enabled: rangeError(range, granularity) === null, refetchInterval: range.preset === 'custom' ? false : LIVE_MS * 3, placeholderData: keepPreviousData });
}
export function useMtd(account: string) { return useQuery({ queryKey: ['mtd', account], queryFn: ({ signal }) => api.get<MtdReport>('/reports/usage', { report: 'mtd', account_id: account }, { signal }), refetchInterval: LIVE_MS }); }
export function useTopOverage() { return useQuery({ queryKey: ['top-overage'], queryFn: async ({ signal }) => (await api.get<{ data: TopOverageRow[] }>('/reports/usage', { report: 'top_overage' }, { signal, financeOnly: true })).data, refetchInterval: LIVE_MS * 6, retry: false }); }

export interface AccountsQuery { page: number; q: string; sort: SortKey; order: SortOrder; pageSize: number }
export function useAccounts({ page, q, sort, order, pageSize }: AccountsQuery) { return useQuery({ queryKey: ['accounts', page, q, sort, order, pageSize], queryFn: ({ signal }) => api.get<AccountsPage>('/accounts', { page, page_size: pageSize, search: q, sort, order }, { signal, financeOnly: true }), placeholderData: keepPreviousData, refetchInterval: LIVE_MS * 2, retry: false }); }
export function useAccountDetail(account: string) { return useQuery({ queryKey: ['account', account], queryFn: ({ signal }) => api.get<AccountDetailData>(`/accounts/${account}`, undefined, { signal }), refetchInterval: LIVE_MS }); }

export function usePlans(account: string) { return useQuery({ queryKey: ['plans', account], queryFn: async ({ signal }) => (await api.get<{ data: Plan[] }>(`/accounts/${account}/plans`, undefined, { signal })).data }); }
export function useWhatIf(account: string, planId: string) { return useQuery({ queryKey: ['what-if', account, planId], queryFn: ({ signal }) => api.get<WhatIfResult>(`/accounts/${account}/what-if`, { plan_id: planId }, { signal }), enabled: Boolean(account && planId) }); }
export function useSchedulePlanChange(account: string) { const qc = useQueryClient(); return useMutation({ mutationFn: ({ planId, effectiveAt }: { planId: string; effectiveAt: string }) => api.post<PlanChangeResult>(`/accounts/${account}/plan-changes`, { plan_id: planId, effective_at: effectiveAt }), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['account', account] }); void qc.invalidateQueries({ queryKey: ['plans', account] }); } }); }

export function useInvoicePreview(account: string, periodStart: string) { return useQuery({ queryKey: ['invoice-preview', account, periodStart], queryFn: ({ signal }) => api.get<InvoicePreviewData>(`/invoices/preview/${account}/${encodeURIComponent(periodStart)}`, undefined, { signal }), enabled: Boolean(account && periodStart) }); }
export function useInvoices(account: string) { return useQuery({ queryKey: ['invoices', account], queryFn: async ({ signal }) => (await api.get<{ data: FinalizedInvoice[] }>(`/invoices/${account}`, undefined, { signal })).data, enabled: Boolean(account) }); }
export function useFinalizeInvoice(account: string) { const qc = useQueryClient(); return useMutation({ mutationFn: (periodStart: string) => api.post<FinalizeResult>(`/invoices/${account}/${encodeURIComponent(periodStart)}`), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['invoices', account] }); void qc.invalidateQueries({ queryKey: ['invoice-preview', account] }); } }); }

export function useApiKeys(account: string) { return useQuery({ queryKey: ['api-keys', account], queryFn: async ({ signal }) => (await api.get<{ data: ApiKeyInfo[] }>(`/accounts/${account}/api-keys`, undefined, { signal })).data, enabled: Boolean(account) }); }
export function useCreateApiKey(account: string) { const qc = useQueryClient(); return useMutation({ mutationFn: () => api.post<CreatedKey>(`/accounts/${account}/api-keys`), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['api-keys', account] }); } }); }
export function useRevokeApiKey(account: string) { const qc = useQueryClient(); return useMutation({ mutationFn: (keyId: string) => api.del(`/accounts/${account}/api-keys/${keyId}`), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['api-keys', account] }); } }); }
export function useRotateApiKey(account: string) { const qc = useQueryClient(); return useMutation({ mutationFn: ({ keyId, overlapSeconds }: { keyId: string; overlapSeconds: number }) => api.post<CreatedKey>(`/accounts/${account}/api-keys/${keyId}/rotate`, { overlap_seconds: overlapSeconds }), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['api-keys', account] }); } }); }
