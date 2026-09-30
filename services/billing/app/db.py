from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    # All timestamptz math (date_trunc, generate_series) must bucket on UTC boundaries.
    connect_args={"server_settings": {"statement_timeout": "10000", "timezone": "UTC"}},
)
Session = async_sessionmaker(engine, expire_on_commit=False)
