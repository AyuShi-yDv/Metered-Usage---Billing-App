from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from .config import settings
engine = create_async_engine(settings.database_url, pool_pre_ping=True, connect_args={"server_settings":{"statement_timeout":"5000"}})
Session = async_sessionmaker(engine, expire_on_commit=False)
