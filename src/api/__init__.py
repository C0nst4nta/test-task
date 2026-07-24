import contextlib
import logging

import fastapi

from ..core import conf
from ..core import postgres
from ..core import web
from . import mock
from . import providers
from . import schemas
from . import services
from . import v1


logger = logging.getLogger(__name__)


def _health_router(database) -> fastapi.APIRouter:
    router = fastapi.APIRouter()

    @router.get('/health', summary='Service health check', tags=['Service'])
    async def health():
        database_ok = await database.ping()
        if not database_ok:
            raise fastapi.HTTPException(status_code=503, detail='Database is unavailable')
        return {'status': 'ok'}

    return router


def create_app(
    settings: conf.Settings | None = None,
    database: postgres.Database | None = None,
    start_background_services: bool = True,
) -> fastapi.FastAPI:
    settings = settings or conf.get_settings()
    if database is None:
        database = postgres.Database.create(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
    elif isinstance(database, postgres.Database):
        postgres.Database.set_instance(database)

    source = providers.SystemAClient(
        settings.system_a_base_url,
        settings.external_api_timeout_seconds,
    )
    destination = providers.SystemBClient(
        settings.system_b_base_url,
        settings.external_api_timeout_seconds,
    )
    executor = services.SyncExecutor(
        handlers={
            schemas.SyncType.EMPLOYEES: services.EmployeeSyncHandler(source, destination),
        },
        max_retries=settings.external_api_max_retries,
        retry_delay_seconds=settings.external_api_retry_delay_seconds,
    )
    worker = services.SyncWorker(executor, settings.worker_poll_interval_seconds)
    scheduler = services.SyncScheduler(
        worker,
        interval_seconds=settings.schedule_interval_seconds,
        immediate=settings.schedule_on_start,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: fastapi.FastAPI):
        await database.connect()
        if start_background_services:
            await worker.start()
            if settings.schedule_enabled:
                await scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()
            await worker.stop()
            await source.close()
            await destination.close()
            await database.disconnect()

    app = web.create_app(
        title='Synchronization Service',
        debug=settings.debug,
        lifespan=lifespan,
        routers=[_health_router(database), v1.get_router(), mock.get_router()],
    )
    app.state.sync_worker = worker
    app.state.sync_scheduler = scheduler
    return app
