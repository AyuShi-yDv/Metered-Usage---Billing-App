from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    # timestamptz values are always UTC; the session zone only affects display.
    connect_args={"server_settings": {"statement_timeout": "3000", "timezone": "UTC"}},
)
Session = async_sessionmaker(engine, expire_on_commit=False)
