# Performance measurement

Run the dashboard time-series query against at least 500,000 seeded facts using `EXPLAIN (ANALYZE, BUFFERS)`. Record the unindexed plan, add `hourly_usage_rollups(account_id, hour_start)`, rerun it, and record elapsed time, buffers, scan change, and row-estimate accuracy. Do not claim benchmark figures that were not measured on the target machine.
