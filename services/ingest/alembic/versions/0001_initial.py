"""initial ingest schema"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    statements = """
    CREATE TABLE api_keys (
      id uuid PRIMARY KEY, account_id uuid NOT NULL, prefix varchar(16) UNIQUE NOT NULL,
      secret_hash varchar(512) NOT NULL, revoked_at timestamptz, overlap_expires_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE usage_events (
      event_id uuid PRIMARY KEY, account_id uuid NOT NULL, api_key_id uuid NOT NULL REFERENCES api_keys(id),
      endpoint varchar(256) NOT NULL, occurred_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
      duration_ms integer NOT NULL CHECK(duration_ms >= 0 AND duration_ms <= 3600000),
      status_code smallint NOT NULL CHECK(status_code BETWEEN 100 AND 599)
    );
    CREATE INDEX usage_events_account_occurred_idx ON usage_events(account_id, occurred_at);
    CREATE TABLE outbox_messages (
      id uuid PRIMARY KEY, topic varchar(128) NOT NULL, schema_version smallint NOT NULL DEFAULT 1,
      payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz,
      attempts integer NOT NULL DEFAULT 0, last_error text
    );
    CREATE INDEX outbox_unpublished_idx ON outbox_messages(created_at) WHERE published_at IS NULL;
    CREATE TABLE ingest_rate_limits (
      account_id uuid PRIMARY KEY, window_started_at timestamptz NOT NULL, request_count integer NOT NULL CHECK(request_count >= 0)
    );
    """
    for statement in statements.split(";"):
        if statement.strip(): op.execute(statement)

def downgrade():
    for statement in ["DROP TABLE ingest_rate_limits", "DROP TABLE outbox_messages", "DROP TABLE usage_events", "DROP TABLE api_keys"]:
        op.execute(statement)
