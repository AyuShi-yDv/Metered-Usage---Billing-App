import asyncio
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from app.config import settings
config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = None
def run_migrations(connection: Connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction(): context.run_migrations()
async def run_async_migrations():
    engine = async_engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with engine.connect() as connection: await connection.run_sync(run_migrations)
    await engine.dispose()
asyncio.run(run_async_migrations())
