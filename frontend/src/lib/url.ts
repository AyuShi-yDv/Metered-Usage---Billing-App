// The URL is the source of truth for what the user is looking at, so a view can be bookmarked or shared.
import type { Granularity, RangePreset, RangeSelection } from './time.ts';

export type View = 'dashboard' | 'accounts' | 'invoices' | 'keys' | 'plans';
export type SortKey = 'usage' | 'name';
export type SortOrder = 'asc' | 'desc';

export const DEMO_ACCOUNT = '00000000-0000-0000-0000-000000000001';
export const VIEWS: View[] = ['dashboard', 'accounts', 'invoices', 'keys', 'plans'];

export interface UrlState {
  view: View;
  account: string;
  granularity: Granularity;
  range: RangeSelection;
  q: string;
  sort: SortKey;
  order: SortOrder;
  page: number;
  month: string; // invoice period, "YYYY-MM" (empty = default chosen by the view)
}

export const DEFAULT_STATE: UrlState = {
  view: 'dashboard', account: DEMO_ACCOUNT, granularity: 'hour', range: { preset: '24h' },
  q: '', sort: 'usage', order: 'desc', page: 1, month: '',
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const isoOrNull = (v: string | null): string | null => (v && !Number.isNaN(new Date(v).getTime()) ? new Date(v).toISOString() : null);

export function parseUrl(search: string): UrlState {
  const p = new URLSearchParams(search);
  const view = VIEWS.find((v) => v === p.get('view')) ?? DEFAULT_STATE.view;
  const account = p.get('account') ?? '';
  const preset = (['24h', '7d', '30d', 'custom'] as RangePreset[]).find((v) => v === p.get('range')) ?? '24h';
  const start = isoOrNull(p.get('start'));
  const end = isoOrNull(p.get('end'));
  const range: RangeSelection = preset === 'custom' && start && end ? { preset, start, end } : { preset: preset === 'custom' ? '24h' : preset };
  const page = Number.parseInt(p.get('page') ?? '1', 10);
  return {
    view,
    account: UUID.test(account) ? account.toLowerCase() : DEFAULT_STATE.account,
    granularity: p.get('g') === 'day' ? 'day' : 'hour',
    range,
    q: (p.get('q') ?? '').slice(0, 100),
    sort: p.get('sort') === 'name' ? 'name' : 'usage',
    order: p.get('order') === 'asc' ? 'asc' : 'desc',
    page: Number.isFinite(page) && page > 0 ? page : 1,
    month: /^\d{4}-(0[1-9]|1[0-2])$/.test(p.get('month') ?? '') ? (p.get('month') as string) : '',
  };
}

/** Serialise only what differs from the defaults, so URLs stay short and readable. */
export function toSearch(state: UrlState): string {
  const p = new URLSearchParams();
  if (state.view !== DEFAULT_STATE.view) p.set('view', state.view);
  if (state.account !== DEFAULT_STATE.account) p.set('account', state.account);
  if (state.granularity !== DEFAULT_STATE.granularity) p.set('g', state.granularity);
  if (state.range.preset !== '24h') p.set('range', state.range.preset);
  if (state.range.preset === 'custom' && state.range.start && state.range.end) {
    p.set('start', state.range.start);
    p.set('end', state.range.end);
  }
  if (state.q) p.set('q', state.q);
  if (state.sort !== DEFAULT_STATE.sort) p.set('sort', state.sort);
  if (state.order !== DEFAULT_STATE.order) p.set('order', state.order);
  if (state.page !== 1) p.set('page', String(state.page));
  if (state.month) p.set('month', state.month);
  const text = p.toString();
  return text ? `?${text}` : '';
}
