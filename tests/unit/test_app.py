import contextlib
import uuid

import fastapi
import httpx
import pytest

from src import api
from src.api import controllers
from src.api import models
from src.api import services
from src.core import conf
from src.core import web


class DatabaseStub:
    def __init__(self, healthy=True):
        self.healthy = healthy
        self.connected = False
        self.disconnected = False

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.disconnected = True

    async def ping(self):
        return self.healthy


async def test_create_app_lifecycle_and_health():
    database = DatabaseStub()
    settings = conf.Settings(schedule_enabled=False)
    app = api.create_app(
        settings=settings,
        database=database,
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://test',
        ) as client:
            response = await client.get('/health')

    assert response.status_code == 200
    assert database.connected is True
    assert database.disconnected is True


async def test_health_returns_unavailable():
    database = DatabaseStub(healthy=False)
    app = api.create_app(
        settings=conf.Settings(schedule_enabled=False),
        database=database,
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://test',
        ) as client:
            response = await client.get('/health')

    assert response.status_code == 503


async def test_custom_validation_handler():
    router = fastapi.APIRouter()

    @router.post('/values')
    async def values(value: int):
        return {'value': value}

    @contextlib.asynccontextmanager
    async def lifespan(app):
        yield

    app = web.create_app(title='Test', lifespan=lifespan, routers=[router])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url='http://test',
    ) as client:
        response = await client.post('/values?value=invalid')

    assert response.status_code == 422
    assert response.json()['detail'][0]['type'] == 'int_parsing'


@pytest.mark.parametrize(
    ('error', 'status_code'),
    [
        (models.SyncAlreadyActive(), 409),
        (models.SyncRunDoesNotExist(), 404),
        (models.SyncRunNotRetryable(), 409),
        (services.SyncDispatchError(), 503),
    ],
)
async def test_sync_exception_handler(error, status_code, monkeypatch):
    async def get(run_id):
        raise error

    monkeypatch.setattr(controllers, 'get_sync_run', get)
    database = DatabaseStub()
    app = api.create_app(
        settings=conf.Settings(schedule_enabled=False),
        database=database,
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://test',
        ) as client:
            response = await client.get(f'/v1/sync-runs/{uuid.uuid4()}')

    assert response.status_code == status_code
