from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from .config import settings
engine = create_async_engine(settings.database_url, pool_pre_ping=True, connect_args={"server_settings":{"statement_timeout":"2000"}})
Session = async_sessionmaker(engine, expire_on_commit=False)
