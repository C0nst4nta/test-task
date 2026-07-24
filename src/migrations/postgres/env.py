import asyncio
import logging.config

import alembic.context
import sqlalchemy.ext.asyncio

import src.api.models  # noqa: F401
from src.core import conf
from src.core import postgres


config = alembic.context.config
logging.config.fileConfig(config.config_file_name)


def apply_migrations(connection) -> None:
    alembic.context.configure(
        connection=connection,
        target_metadata=postgres.metadata,
        compare_type=True,
    )
    with alembic.context.begin_transaction():
        alembic.context.run_migrations()


async def run_migrations() -> None:
    engine = sqlalchemy.ext.asyncio.create_async_engine(conf.get_settings().database_url)
    async with engine.begin() as connection:
        await connection.run_sync(apply_migrations)
    await engine.dispose()


asyncio.run(run_migrations())
