"""reporting indexes: drop the redundant endpoint index, add rollup hour index for cross-account reports"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # (account_id, occurred_at, endpoint) INCLUDE (duration_ms) was never chosen by the planner for the
    # time series and cannot give p95's ORDER BY duration_ms an index order; it only slowed ingestion writes.
    op.execute("DROP INDEX IF EXISTS billing_events_account_time_endpoint_idx")
    # Account list and top-overage aggregate all accounts for the current month: filter on hour_start alone.
    op.execute("CREATE INDEX IF NOT EXISTS hourly_usage_rollups_hour_idx ON hourly_usage_rollups(hour_start)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS hourly_usage_rollups_hour_idx")
    op.execute("CREATE INDEX IF NOT EXISTS billing_events_account_time_endpoint_idx ON billing_events(account_id, occurred_at, endpoint) INCLUDE(duration_ms)")
