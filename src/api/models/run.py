import uuid

import sqlalchemy
import sqlalchemy.ext.asyncio

from ...core import postgres
from .. import schemas
from .item import SyncItem


class SyncRunDoesNotExist(Exception):
    """Raised when a synchronization run is not found."""


class SyncAlreadyActive(Exception):
    """Raised when a synchronization of the same type is already active."""


class SyncRunNotRetryable(Exception):
    """Raised when retry is requested for a non-terminal run."""


class SyncRunNotClaimable(Exception):
    """Raised when a synchronization run is no longer queued."""


SyncRun = sqlalchemy.Table(
    'sync_run',
    postgres.metadata,
    sqlalchemy.Column(
        'id',
        sqlalchemy.UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text('gen_random_uuid()'),
        nullable=False,
    ),
    sqlalchemy.Column('sync_type', sqlalchemy.Text, nullable=False),
    sqlalchemy.Column('trigger', sqlalchemy.Text, nullable=False),
    sqlalchemy.Column('status', sqlalchemy.Text, nullable=False),
    sqlalchemy.Column(
        'retry_of_id',
        sqlalchemy.UUID(as_uuid=True),
        sqlalchemy.ForeignKey('sync_run.id'),
        nullable=True,
    ),
    sqlalchemy.Column(
        'total_items',
        sqlalchemy.Integer,
        nullable=False,
        server_default=sqlalchemy.text('0'),
    ),
    sqlalchemy.Column(
        'succeeded_items',
        sqlalchemy.Integer,
        nullable=False,
        server_default=sqlalchemy.text('0'),
    ),
    sqlalchemy.Column(
        'failed_items',
        sqlalchemy.Integer,
        nullable=False,
        server_default=sqlalchemy.text('0'),
    ),
    sqlalchemy.Column('error_message', sqlalchemy.Text, nullable=True),
    sqlalchemy.Column(
        'queued_at',
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.func.now(),
    ),
    sqlalchemy.Column('started_at', sqlalchemy.DateTime(timezone=True), nullable=True),
    sqlalchemy.Column('finished_at', sqlalchemy.DateTime(timezone=True), nullable=True),
    sqlalchemy.CheckConstraint(
        "status IN ('queued', 'running', 'completed', 'partially_completed', 'failed')",
        name='status',
    ),
    sqlalchemy.CheckConstraint(
        "trigger IN ('manual', 'scheduled', 'retry')",
        name='trigger',
    ),
    sqlalchemy.CheckConstraint(
        'total_items >= 0 AND succeeded_items >= 0 AND failed_items >= 0',
        name='non_negative_counters',
    ),
)


sqlalchemy.Index('ix_sync_run_queued_at', SyncRun.c.queued_at.desc())
sqlalchemy.Index(
    'uq_sync_run_active_type',
    SyncRun.c.sync_type,
    unique=True,
    postgresql_where=SyncRun.c.status.in_([
        schemas.SyncRunStatus.QUEUED.value,
        schemas.SyncRunStatus.RUNNING.value,
    ]),
)


def _as_dict(row) -> dict:
    return dict(row)


def _as_optional_dict(row) -> dict | None:
    return dict(row) if row is not None else None


def _is_active_constraint_error(error: sqlalchemy.exc.IntegrityError) -> bool:
    original = error.orig
    cause = getattr(original, '__cause__', None)
    return (
        getattr(original, 'constraint_name', None) == 'uq_sync_run_active_type'
        or getattr(cause, 'constraint_name', None) == 'uq_sync_run_active_type'
        or 'uq_sync_run_active_type' in str(original)
    )


@postgres.session
async def sync_run_create(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    trigger: schemas.SyncTrigger,
    sync_type: schemas.SyncType = schemas.SyncType.EMPLOYEES,
    retry_of_id: uuid.UUID | None = None,
) -> dict:
    query = (
        SyncRun.insert()
        .values(
            sync_type=sync_type.value,
            trigger=trigger.value,
            status=schemas.SyncRunStatus.QUEUED.value,
            retry_of_id=retry_of_id,
        )
        .returning(SyncRun)
    )
    try:
        result = await session.execute(query)
    except sqlalchemy.exc.IntegrityError as error:
        if _is_active_constraint_error(error):
            raise SyncAlreadyActive from error
        raise
    return _as_dict(result.mappings().one())


@postgres.session
async def sync_run_retry(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    run_id: uuid.UUID,
) -> dict:
    parent = await sync_run_get(session, run_id)
    if parent['status'] not in {
        schemas.SyncRunStatus.FAILED.value,
        schemas.SyncRunStatus.PARTIALLY_COMPLETED.value,
    }:
        raise SyncRunNotRetryable
    return await sync_run_create(
        session,
        trigger=schemas.SyncTrigger.RETRY,
        sync_type=schemas.SyncType(parent['sync_type']),
        retry_of_id=run_id,
    )


@postgres.session
async def sync_run_get(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    run_id: uuid.UUID,
) -> dict:
    result = await session.execute(SyncRun.select().where(SyncRun.c.id == run_id))
    run = result.mappings().one_or_none()
    if run is None:
        raise SyncRunDoesNotExist
    return _as_dict(run)


@postgres.session
async def sync_run_detail(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    run_id: uuid.UUID,
) -> dict:
    run = await sync_run_get(session, run_id)
    result = await session.execute(
        SyncItem.select()
        .where(SyncItem.c.run_id == run_id)
        .order_by(SyncItem.c.external_id.asc()),
    )
    return {**run, 'items': [dict(row) for row in result.mappings().all()]}


@postgres.session
async def sync_run_list(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    limit: int,
    offset: int,
    status: schemas.SyncRunStatus | None = None,
    trigger: schemas.SyncTrigger | None = None,
    sync_type: schemas.SyncType | None = None,
) -> tuple[list[dict], int]:
    filters = []
    if status is not None:
        filters.append(SyncRun.c.status == status.value)
    if trigger is not None:
        filters.append(SyncRun.c.trigger == trigger.value)
    if sync_type is not None:
        filters.append(SyncRun.c.sync_type == sync_type.value)

    query = (
        SyncRun.select()
        .where(*filters)
        .order_by(SyncRun.c.queued_at.desc(), SyncRun.c.id.desc())
        .limit(limit)
        .offset(offset)
    )
    count_query = (
        sqlalchemy.select(sqlalchemy.func.count())
        .select_from(SyncRun)
        .where(*filters)
    )
    rows = (await session.execute(query)).mappings().all()
    total = await session.scalar(count_query)
    return [dict(row) for row in rows], total or 0


@postgres.session
async def sync_current(session: sqlalchemy.ext.asyncio.AsyncSession) -> dict:
    active_query = (
        SyncRun.select()
        .where(SyncRun.c.status.in_([
            schemas.SyncRunStatus.QUEUED.value,
            schemas.SyncRunStatus.RUNNING.value,
        ]))
        .order_by(SyncRun.c.queued_at.desc())
        .limit(1)
    )
    last_query = (
        SyncRun.select()
        .where(SyncRun.c.status.not_in([
            schemas.SyncRunStatus.QUEUED.value,
            schemas.SyncRunStatus.RUNNING.value,
        ]))
        .order_by(SyncRun.c.finished_at.desc())
        .limit(1)
    )
    active = (await session.execute(active_query)).mappings().one_or_none()
    last = (await session.execute(last_query)).mappings().one_or_none()
    return {
        'active_run': _as_optional_dict(active),
        'last_run': _as_optional_dict(last),
    }


@postgres.session
async def sync_run_claim(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    run_id: uuid.UUID,
) -> dict:
    query = (
        SyncRun.update()
        .where(
            SyncRun.c.id == run_id,
            SyncRun.c.status == schemas.SyncRunStatus.QUEUED.value,
        )
        .values(
            status=schemas.SyncRunStatus.RUNNING.value,
            started_at=sqlalchemy.func.coalesce(SyncRun.c.started_at, sqlalchemy.func.now()),
            finished_at=None,
            error_message=None,
        )
        .returning(SyncRun)
    )
    run = (await session.execute(query)).mappings().one_or_none()
    if run is None:
        raise SyncRunNotClaimable
    return _as_dict(run)


@postgres.session
async def sync_runs_requeue_interrupted(
    session: sqlalchemy.ext.asyncio.AsyncSession,
) -> list[dict]:
    result = await session.execute(
        SyncRun.update()
        .where(SyncRun.c.status == schemas.SyncRunStatus.RUNNING.value)
        .values(status=schemas.SyncRunStatus.QUEUED.value)
        .returning(SyncRun),
    )
    return [dict(row) for row in result.mappings().all()]


@postgres.session
async def sync_runs_queued(
    session: sqlalchemy.ext.asyncio.AsyncSession,
) -> list[dict]:
    result = await session.execute(
        SyncRun.select()
        .where(SyncRun.c.status == schemas.SyncRunStatus.QUEUED.value)
        .order_by(SyncRun.c.queued_at.asc()),
    )
    return [dict(row) for row in result.mappings().all()]


@postgres.session
async def sync_run_finish(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    run_id: uuid.UUID,
) -> dict:
    counts_query = sqlalchemy.select(
        sqlalchemy.func.count().label('total'),
        sqlalchemy.func.count().filter(
            SyncItem.c.status == schemas.SyncItemStatus.SUCCEEDED.value,
        ).label('succeeded'),
        sqlalchemy.func.count().filter(
            SyncItem.c.status == schemas.SyncItemStatus.FAILED.value,
        ).label('failed'),
    ).where(SyncItem.c.run_id == run_id)
    counts = (await session.execute(counts_query)).mappings().one()

    if counts['failed'] == 0:
        status = schemas.SyncRunStatus.COMPLETED
    elif counts['succeeded'] > 0:
        status = schemas.SyncRunStatus.PARTIALLY_COMPLETED
    else:
        status = schemas.SyncRunStatus.FAILED

    result = await session.execute(
        SyncRun.update()
        .where(SyncRun.c.id == run_id)
        .values(
            status=status.value,
            total_items=counts['total'],
            succeeded_items=counts['succeeded'],
            failed_items=counts['failed'],
            finished_at=sqlalchemy.func.now(),
        )
        .returning(SyncRun),
    )
    return _as_dict(result.mappings().one())


@postgres.session
async def sync_run_fail(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    run_id: uuid.UUID,
    error_message: str,
) -> dict:
    result = await session.execute(
        SyncRun.update()
        .where(SyncRun.c.id == run_id)
        .values(
            status=schemas.SyncRunStatus.FAILED.value,
            error_message=error_message,
            finished_at=sqlalchemy.func.now(),
        )
        .returning(SyncRun),
    )
    return _as_dict(result.mappings().one())
