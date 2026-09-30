import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { AccountDetailData, AccountsPage, MtdReport, P95Row, Plan, TopOverageRow, UsagePoint } from './types';
import { rangeError, resolveRange } from '../lib/time.ts';
import type { Granularity, RangeSelection } from '../lib/time.ts';
import type { SortKey, SortOrder } from '../lib/url.ts';

/** Dashboards poll while the tab is visible so numbers move while the generator runs. */
export const LIVE_MS = 5000;

const rangeKey = (range: RangeSelection) => [range.preset, range.start ?? null, range.end ?? null] as const;

function rangeParams(range: RangeSelection) {
  // Preset ranges are resolved when the request runs, so a polling chart slides forward with the clock.
  const { start, end } = resolveRange(range);
  return { start: start.toISOString(), end: end.toISOString() };
}

export function useUsageSeries(account: string, granularity: Granularity, range: RangeSelection) {
  return useQuery({
    queryKey: ['usage', account, granularity, ...rangeKey(range)],
    queryFn: async ({ signal }) => {
      const body = await api.get<{ data: UsagePoint[] }>('/reports/usage',
        { report: 'time_series', account_id: account, granularity, ...rangeParams(range) }, { signal });
      return body.data;
    },
    enabled: rangeError(range, granularity) === null,
    refetchInterval: range.preset === 'custom' ? false : LIVE_MS,
    placeholderData: keepPreviousData, // keep the old chart on screen while a new range loads: no empty flash
  });
}

export function useP95(account: string, granularity: Granularity, range: RangeSelection) {
  return useQuery({
    queryKey: ['p95', account, granularity, ...rangeKey(range)],
    queryFn: async ({ signal }) => {
      const body = await api.get<{ data: P95Row[] }>('/reports/usage',
        { report: 'p95', account_id: account, granularity, ...rangeParams(range) }, { signal });
      return body.data;
    },
    enabled: rangeError(range, granularity) === null,
    refetchInterval: range.preset === 'custom' ? false : LIVE_MS * 3,
    placeholderData: keepPreviousData,
  });
}

export function useMtd(account: string) {
  return useQuery({
    queryKey: ['mtd', account],
    queryFn: ({ signal }) => api.get<MtdReport>('/reports/usage', { report: 'mtd', account_id: account }, { signal }),
    refetchInterval: LIVE_MS,
  });
}

export function useTopOverage() {
  return useQuery({
    queryKey: ['top-overage'],
    queryFn: async ({ signal }) => {
      const body = await api.get<{ data: TopOverageRow[] }>('/reports/usage', { report: 'top_overage' }, { signal, financeOnly: true });
      return body.data;
    },
    refetchInterval: LIVE_MS * 6,
    retry: false,
  });
}

export interface AccountsQuery { page: number; q: string; sort: SortKey; order: SortOrder; pageSize: number }

export function useAccounts({ page, q, sort, order, pageSize }: AccountsQuery) {
  return useQuery({
    queryKey: ['accounts', page, q, sort, order, pageSize],
    queryFn: ({ signal }) => api.get<AccountsPage>('/accounts', { page, page_size: pageSize, search: q, sort, order }, { signal, financeOnly: true }),
    placeholderData: keepPreviousData,
    refetchInterval: LIVE_MS * 2,
    retry: false,
  });
}

export function useAccountDetail(account: string) {
  return useQuery({
    queryKey: ['account', account],
    queryFn: ({ signal }) => api.get<AccountDetailData>(`/accounts/${account}`, undefined, { signal }),
    refetchInterval: LIVE_MS,
  });
}

export function usePlans(account: string) {
  return useQuery({
    queryKey: ['plans', account],
    queryFn: async ({ signal }) => (await api.get<{ data: Plan[] }>(`/accounts/${account}/plans`, undefined, { signal })).data,
  });
}
