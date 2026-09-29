TIME_SERIES_SQL = """
WITH buckets AS (
  SELECT generate_series(date_trunc(:bucket, CAST(:start AS timestamptz)), date_trunc(:bucket, CAST(:end AS timestamptz) - interval '1 microsecond'), (:interval)::interval) AS bucket
), usage AS (
  SELECT date_trunc(:bucket, occurred_at) AS bucket, count(*) FILTER (WHERE status_code BETWEEN 200 AND 499) AS calls
  FROM billing_events
  WHERE account_id=:account_id AND occurred_at >= :start AND occurred_at < :end
  GROUP BY 1
)
SELECT buckets.bucket, COALESCE(usage.calls, 0)::bigint AS billable_calls
FROM buckets LEFT JOIN usage USING(bucket) ORDER BY buckets.bucket
"""

P95_SQL = """
SELECT endpoint, percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_duration_ms
FROM billing_events
WHERE account_id=:account_id AND occurred_at >= :start AND occurred_at < :end
GROUP BY endpoint ORDER BY endpoint
"""

MTD_SQL = """
WITH plan AS (
  SELECT p.* FROM account_plans ap JOIN plans p ON p.id=ap.plan_id
  WHERE ap.account_id=:account_id AND ap.effective_from <= now()
    AND (ap.effective_to IS NULL OR ap.effective_to > now()) LIMIT 1
), used AS (
  SELECT COALESCE(sum(billable_calls),0)::bigint AS calls
  FROM hourly_usage_rollups
  WHERE account_id=:account_id AND hour_start >= date_trunc('month', now()) AND hour_start < now()
), projection AS (
  SELECT used.calls, plan.included_calls, plan.overage_cents_per_1000,
    CEIL((used.calls::numeric / GREATEST(EXTRACT(EPOCH FROM now()-date_trunc('month',now())),1))
      * EXTRACT(EPOCH FROM (date_trunc('month',now()) + interval '1 month' - now())))::bigint AS projected_remaining_calls
  FROM used CROSS JOIN plan
)
SELECT calls, included_calls, GREATEST(calls-included_calls,0)::bigint AS overage_calls,
       projected_remaining_calls,
       GREATEST(calls+projected_remaining_calls-included_calls,0)::bigint AS projected_overage_calls,
       ((GREATEST(calls+projected_remaining_calls-included_calls,0)::numeric * overage_cents_per_1000 + 500) / 1000)::bigint AS projected_overage_cents,
       overage_cents_per_1000
FROM projection
"""

TOP_OVERAGE_SQL = """
WITH bounds AS (
  SELECT date_trunc('month', now()) AS current_start,
         date_trunc('month', now()) - interval '1 month' AS previous_start,
         LEAST(EXTRACT(day FROM now())::integer,
               EXTRACT(day FROM date_trunc('month', now()) - interval '1 day')::integer) AS previous_day,
         now() - date_trunc('day', now()) AS time_today
), current_month AS (
  SELECT r.account_id, sum(r.billable_calls)::bigint AS calls
  FROM hourly_usage_rollups r CROSS JOIN bounds b
  WHERE r.hour_start >= b.current_start AND r.hour_start < now()
  GROUP BY r.account_id
), previous_month AS (
  SELECT r.account_id, sum(r.billable_calls)::bigint AS calls
  FROM hourly_usage_rollups r CROSS JOIN bounds b
  WHERE r.hour_start >= b.previous_start
    AND r.hour_start < date_trunc('hour', b.previous_start + (b.previous_day - 1) * interval '1 day' + b.time_today) + interval '1 hour'
  GROUP BY r.account_id
), costed AS (
  SELECT a.id, a.name,
         ((GREATEST(COALESCE(c.calls,0)-p.included_calls,0)::numeric * p.overage_cents_per_1000 + 500) / 1000)::bigint AS overage_cents,
         ((GREATEST(COALESCE(pr.calls,0)-p.included_calls,0)::numeric * p.overage_cents_per_1000 + 500) / 1000)::bigint AS previous_overage_cents
  FROM accounts a
  LEFT JOIN current_month c ON c.account_id=a.id
  LEFT JOIN previous_month pr ON pr.account_id=a.id
  JOIN account_plans ap ON ap.account_id=a.id
    AND ap.effective_from<=now() AND (ap.effective_to IS NULL OR ap.effective_to>now())
  JOIN plans p ON p.id=ap.plan_id
), ranked AS (
  SELECT *, DENSE_RANK() OVER (ORDER BY overage_cents DESC) AS rank
  FROM costed
)
SELECT *, overage_cents-previous_overage_cents AS month_over_month_change_cents
FROM ranked WHERE rank<=10 ORDER BY rank,id
"""
