import uuid

import sqlalchemy
import sqlalchemy.dialects.postgresql
import sqlalchemy.ext.asyncio

from ...core import postgres
from .. import schemas


SyncItem = sqlalchemy.Table(
    'sync_item',
    postgres.metadata,
    sqlalchemy.Column(
        'id',
        sqlalchemy.UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text('gen_random_uuid()'),
        nullable=False,
    ),
    sqlalchemy.Column(
        'run_id',
        sqlalchemy.UUID(as_uuid=True),
        sqlalchemy.ForeignKey('sync_run.id', ondelete='CASCADE'),
        nullable=False,
    ),
    sqlalchemy.Column('external_id', sqlalchemy.Text, nullable=False),
    sqlalchemy.Column('status', sqlalchemy.Text, nullable=False),
    sqlalchemy.Column(
        'attempts',
        sqlalchemy.Integer,
        nullable=False,
        server_default=sqlalchemy.text('0'),
    ),
    sqlalchemy.Column(
        'source_payload',
        sqlalchemy.dialects.postgresql.JSONB,
        nullable=False,
    ),
    sqlalchemy.Column(
        'destination_response',
        sqlalchemy.dialects.postgresql.JSONB,
        nullable=True,
    ),
    sqlalchemy.Column('error_message', sqlalchemy.Text, nullable=True),
    sqlalchemy.Column('started_at', sqlalchemy.DateTime(timezone=True), nullable=True),
    sqlalchemy.Column('finished_at', sqlalchemy.DateTime(timezone=True), nullable=True),
    sqlalchemy.CheckConstraint(
        "status IN ('pending', 'processing', 'succeeded', 'failed')",
        name='status',
    ),
    sqlalchemy.CheckConstraint('attempts >= 0', name='non_negative_attempts'),
    sqlalchemy.UniqueConstraint('run_id', 'external_id'),
)


sqlalchemy.Index('ix_sync_item_run_status', SyncItem.c.run_id, SyncItem.c.status)


def _as_dict(row) -> dict | None:
    return dict(row) if row is not None else None


@postgres.session
async def sync_item_upsert(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    run_id: uuid.UUID,
    external_id: str,
    source_payload: dict,
) -> dict:
    query = (
        sqlalchemy.dialects.postgresql.insert(SyncItem)
        .values(
            run_id=run_id,
            external_id=external_id,
            status=schemas.SyncItemStatus.PENDING.value,
            source_payload=source_payload,
        )
        .on_conflict_do_update(
            constraint='uq_sync_item_run_id',
            set_={'source_payload': source_payload},
        )
        .returning(SyncItem)
    )
    result = await session.execute(query)
    return _as_dict(result.mappings().one())


@postgres.session
async def sync_item_list_for_run(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    run_id: uuid.UUID,
) -> list[dict]:
    result = await session.execute(
        SyncItem.select()
        .where(SyncItem.c.run_id == run_id)
        .order_by(SyncItem.c.external_id.asc()),
    )
    return [dict(row) for row in result.mappings().all()]


@postgres.session
async def sync_failed_payloads(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    run_id: uuid.UUID,
) -> list[dict]:
    result = await session.execute(
        sqlalchemy.select(SyncItem.c.source_payload)
        .where(
            SyncItem.c.run_id == run_id,
            SyncItem.c.status == schemas.SyncItemStatus.FAILED.value,
        )
        .order_by(SyncItem.c.external_id.asc()),
    )
    return list(result.scalars().all())


@postgres.session
async def sync_item_start_attempt(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    item_id: uuid.UUID,
) -> None:
    await session.execute(
        SyncItem.update()
        .where(SyncItem.c.id == item_id)
        .values(
            status=schemas.SyncItemStatus.PROCESSING.value,
            attempts=SyncItem.c.attempts + 1,
            started_at=sqlalchemy.func.coalesce(SyncItem.c.started_at, sqlalchemy.func.now()),
            error_message=None,
        ),
    )


@postgres.session
async def sync_item_succeed(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    item_id: uuid.UUID,
    destination_response: dict,
) -> None:
    await session.execute(
        SyncItem.update()
        .where(SyncItem.c.id == item_id)
        .values(
            status=schemas.SyncItemStatus.SUCCEEDED.value,
            destination_response=destination_response,
            error_message=None,
            finished_at=sqlalchemy.func.now(),
        ),
    )


@postgres.session
async def sync_item_fail(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    item_id: uuid.UUID,
    error_message: str,
) -> None:
    await session.execute(
        SyncItem.update()
        .where(SyncItem.c.id == item_id)
        .values(
            status=schemas.SyncItemStatus.FAILED.value,
            error_message=error_message,
            finished_at=sqlalchemy.func.now(),
        ),
    )
