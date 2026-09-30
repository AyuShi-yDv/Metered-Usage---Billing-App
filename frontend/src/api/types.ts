// Response shapes of billing-service. Money fields are integer cents; timestamps are UTC ISO strings.

export interface UsagePoint { bucket: string; billable_calls: number }
export interface P95Row { endpoint: string; p95_duration_ms: number }

export interface MtdReport {
  calls: number;
  included_calls: number;
  overage_calls: number;
  projected_remaining_calls: number;
  projected_overage_calls: number;
  projected_overage_cents: number;
  overage_cents_per_1000: number;
}

export interface TopOverageRow {
  id: string;
  name: string;
  overage_cents: number;
  previous_overage_cents: number;
  rank: number;
  month_over_month_change_cents: number;
}

export interface AccountRow { id: string; name: string; calls: number; plan_name: string | null; included_calls: number | null }
export interface AccountsPage { data: AccountRow[]; page: number; page_size: number; total: number }

export interface EndpointLatency { endpoint: string; p95_duration_ms: number; calls: number }
export interface AccountDetailData {
  id: string;
  account_name: string;
  plan_name: string;
  included_calls: number;
  overage_cents_per_1000: number;
  monthly_base_fee_cents: number;
  calls: number;
  projected_overage_cents: number;
  endpoints: EndpointLatency[];
}

export interface Plan { id: string; name: string; included_calls: number; overage_cents_per_1000: number; monthly_base_fee_cents: number }

export interface InvoiceLine { description: string; quantity: number; amount_cents: number; source_period_start?: string | null }
export interface InvoicePreviewData {
  period_start: string;
  period_end: string;
  plan_name: string;
  calls: number;
  overage_calls: number;
  base_fee_cents: number;
  overage_cents: number;
  total_cents: number;
  lines: InvoiceLine[];
  pending_adjustments_cents: number;
  finalizable: boolean;
}
export interface FinalizedInvoice {
  id: string;
  account_id: string;
  period_start: string;
  period_end: string;
  status: 'draft' | 'final';
  base_fee_cents: number;
  overage_cents: number;
  total_cents: number;
  lines: InvoiceLine[];
}
export interface FinalizeResult { invoice_id: string; total_cents: number; created: boolean }

export interface ApiKeyInfo { id: string; prefix: string; created_at: string; revoked_at: string | null; overlap_expires_at: string | null }
export interface CreatedKey { id: string; prefix: string; secret: string }

export interface WhatIfResult {
  calls: number;
  current_plan_name: string;
  alternative_plan_name: string;
  current_cost_cents: number;
  alternative_cost_cents: number;
  difference_cents: number;
}
export interface PlanChangeResult { id: string; account_id: string; plan_id: string; effective_at: string }
