TIME_SERIES_SQL = """
WITH buckets AS (
  SELECT generate_series(date_trunc(:bucket, CAST(:start AS timestamptz)), :end - (:interval)::interval, (:interval)::interval) AS bucket
), usage AS (
  SELECT date_trunc(:bucket, hour_start) AS bucket, sum(billable_calls) AS calls
  FROM hourly_usage_rollups
  WHERE account_id=:account_id AND hour_start >= :start AND hour_start < :end
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
WITH plan AS (SELECT p.* FROM account_plans ap JOIN plans p ON p.id=ap.plan_id WHERE ap.account_id=:account_id AND ap.effective_from <= now() AND (ap.effective_to IS NULL OR ap.effective_to > now()) LIMIT 1),
used AS (SELECT COALESCE(sum(billable_calls),0)::bigint calls FROM hourly_usage_rollups WHERE account_id=:account_id AND hour_start >= date_trunc('month', now()) AND hour_start < now())
SELECT used.calls, plan.included_calls, GREATEST(used.calls-plan.included_calls,0)::bigint AS overage_calls,
 ((used.calls::numeric / GREATEST(EXTRACT(EPOCH FROM now()-date_trunc('month',now())),1)) * EXTRACT(EPOCH FROM (date_trunc('month',now()) + interval '1 month' - now())))::bigint AS projected_remaining_calls,
 plan.overage_cents_per_1000 FROM used CROSS JOIN plan
"""

TOP_OVERAGE_SQL = """
WITH current_month AS (SELECT account_id,COALESCE(sum(billable_calls),0)::bigint calls FROM hourly_usage_rollups WHERE hour_start>=date_trunc('month',now()) AND hour_start<date_trunc('month',now())+interval '1 month' GROUP BY account_id),
previous_month AS (SELECT account_id,COALESCE(sum(billable_calls),0)::bigint calls FROM hourly_usage_rollups WHERE hour_start>=date_trunc('month',now())-interval '1 month' AND hour_start<date_trunc('month',now()) GROUP BY account_id),
costed AS (SELECT a.id,a.name,GREATEST(COALESCE(c.calls,0)-p.included_calls,0)*p.overage_cents_per_1000/1000 AS overage_cents,GREATEST(COALESCE(pr.calls,0)-p.included_calls,0)*p.overage_cents_per_1000/1000 AS previous_overage_cents FROM accounts a LEFT JOIN current_month c ON c.account_id=a.id LEFT JOIN previous_month pr ON pr.account_id=a.id JOIN account_plans ap ON ap.account_id=a.id AND ap.effective_from<=now() AND (ap.effective_to IS NULL OR ap.effective_to>now()) JOIN plans p ON p.id=ap.plan_id),
ranked AS (SELECT *,DENSE_RANK() OVER(ORDER BY overage_cents DESC) rank FROM costed) SELECT *,overage_cents-previous_overage_cents AS month_over_month_change_cents FROM ranked WHERE rank<=10 ORDER BY rank,id
"""
