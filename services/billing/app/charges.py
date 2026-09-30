"""Invoice-period calculations. Amounts stay numeric cents until final invoice rounding."""
from sqlalchemy import text


PERIOD_CHARGES_SQL = text("""
WITH period AS (
  SELECT CAST(:start AS timestamptz) AS period_start,
         CAST(:end AS timestamptz) AS period_end
), segments AS (
  SELECT p.id AS plan_id, p.name AS plan_name, p.included_calls,
         p.overage_cents_per_1000, p.monthly_base_fee_cents,
         GREATEST(ap.effective_from, period.period_start) AS segment_start,
         LEAST(COALESCE(ap.effective_to, period.period_end), period.period_end) AS segment_end,
         EXTRACT(EPOCH FROM period.period_end - period.period_start) AS period_seconds
  FROM account_plans ap
  JOIN plans p ON p.id = ap.plan_id
  CROSS JOIN period
  WHERE ap.account_id = :account
    AND ap.effective_from < period.period_end
    AND COALESCE(ap.effective_to, period.period_end) > period.period_start
), usage AS (
  SELECT segments.*,
         (SELECT count(*) FILTER (WHERE e.status_code BETWEEN 200 AND 499)
          FROM billing_events e
          WHERE e.account_id = :account
            AND e.occurred_at >= segments.segment_start
            AND e.occurred_at < segments.segment_end) AS calls,
         EXTRACT(EPOCH FROM segments.segment_end - segments.segment_start) AS segment_seconds
  FROM segments
), amounts AS (
  SELECT COALESCE(sum(calls), 0)::bigint AS calls,
    sum(monthly_base_fee_cents::numeric * segment_seconds / period_seconds) AS base_amount,
    sum(GREATEST(calls::numeric - included_calls::numeric * segment_seconds / period_seconds, 0)
      * overage_cents_per_1000 / 1000) AS overage_amount,
    sum(GREATEST(calls::numeric - included_calls::numeric * segment_seconds / period_seconds, 0)) AS overage_calls,
    jsonb_agg(jsonb_build_object('plan_name', plan_name, 'calls', calls,
      'segment_start', segment_start, 'segment_end', segment_end)) AS plan_segments
  FROM usage
)
SELECT calls,
       round(base_amount)::integer AS base_fee_cents,
       (round(base_amount + overage_amount) - round(base_amount))::integer AS overage_cents,
       round(base_amount + overage_amount)::integer AS total_cents,
       COALESCE(ceil(overage_calls), 0)::bigint AS overage_calls, plan_segments
FROM amounts
""")


WHAT_IF_SQL = text("""
WITH bounds AS (
  SELECT now() - interval '30 days' AS period_start, now() AS period_end,
         EXTRACT(EPOCH FROM interval '30 days') AS period_seconds
), usage AS (
  SELECT count(*) FILTER (WHERE status_code BETWEEN 200 AND 499)::bigint AS calls
  FROM billing_events, bounds
  WHERE account_id = :account
    AND occurred_at >= bounds.period_start AND occurred_at < bounds.period_end
), current_plan AS (
  SELECT p.* FROM account_plans ap JOIN plans p ON p.id = ap.plan_id
  WHERE ap.account_id = :account AND ap.effective_from <= now()
    AND (ap.effective_to IS NULL OR ap.effective_to > now())
  ORDER BY ap.effective_from DESC LIMIT 1
), alternative AS (SELECT * FROM plans WHERE id = :plan_id), costed AS (
  SELECT usage.calls,
    round(current_plan.monthly_base_fee_cents::numeric * 30 / extract(day FROM date_trunc('month',now()) + interval '1 month' - date_trunc('month',now()))
      + GREATEST(usage.calls::numeric - current_plan.included_calls::numeric * 30 / extract(day FROM date_trunc('month',now()) + interval '1 month' - date_trunc('month',now())),0) * current_plan.overage_cents_per_1000 / 1000) AS current_cost_cents,
    round(alternative.monthly_base_fee_cents::numeric * 30 / extract(day FROM date_trunc('month',now()) + interval '1 month' - date_trunc('month',now()))
      + GREATEST(usage.calls::numeric - alternative.included_calls::numeric * 30 / extract(day FROM date_trunc('month',now()) + interval '1 month' - date_trunc('month',now())),0) * alternative.overage_cents_per_1000 / 1000) AS alternative_cost_cents,
    current_plan.name AS current_plan_name, alternative.name AS alternative_plan_name
  FROM usage CROSS JOIN current_plan CROSS JOIN alternative
)
SELECT calls, current_plan_name, alternative_plan_name,
       current_cost_cents::integer, alternative_cost_cents::integer,
       (alternative_cost_cents-current_cost_cents)::integer AS difference_cents
FROM costed
""")
