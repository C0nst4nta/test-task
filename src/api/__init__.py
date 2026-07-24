import contextlib
import logging

import fastapi

from ..core import conf
from ..core import postgres
from ..core import web
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

    @contextlib.asynccontextmanager
    async def lifespan(app: fastapi.FastAPI):
        await database.connect()
        try:
            yield
        finally:
            await database.disconnect()

    app = web.create_app(
        title='Synchronization Service',
        debug=settings.debug,
        lifespan=lifespan,
        routers=[_health_router(database), v1.get_router()],
    )
    return app
