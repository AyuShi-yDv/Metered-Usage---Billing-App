"""rate limiting moved in-process; drop the unused table"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS ingest_rate_limits")


def downgrade():
    op.execute(
        "CREATE TABLE ingest_rate_limits (account_id uuid PRIMARY KEY, window_started_at timestamptz NOT NULL, "
        "request_count integer NOT NULL CHECK(request_count >= 0))"
    )
