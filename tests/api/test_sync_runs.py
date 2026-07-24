import uuid

import fastapi
import httpx

from src.api import controllers
from src.api import schemas
from src.api import v1


def _app() -> fastapi.FastAPI:
    app = fastapi.FastAPI()
    app.include_router(v1.get_router())
    return app


async def test_manual_sync_returns_accepted(sync_run, monkeypatch):
    async def create(request):
        assert request.sync_type == schemas.SyncType.EMPLOYEES
        return sync_run

    monkeypatch.setattr(controllers, 'create_sync_run', create)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url='http://test',
    ) as client:
        response = await client.post('/v1/sync-runs', json={})

    assert response.status_code == 202
    assert response.json()['status'] == 'queued'


async def test_manual_sync_rejects_unknown_type():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url='http://test',
    ) as client:
        response = await client.post('/v1/sync-runs', json={'sync_type': 'unknown'})

    assert response.status_code == 422


async def test_list_sync_runs(sync_run, monkeypatch):
    async def list_runs(query):
        assert query.limit == 5
        return {
            'sync_runs': [sync_run],
            'pagination': {'limit': 5, 'offset': 0, 'total': 1},
        }

    monkeypatch.setattr(controllers, 'list_sync_runs', list_runs)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url='http://test',
    ) as client:
        response = await client.get('/v1/sync-runs?limit=5')

    assert response.status_code == 200
    assert response.json()['pagination']['total'] == 1


async def test_get_current_sync(sync_run, monkeypatch):
    async def current():
        return {'active_run': sync_run, 'last_run': None}

    monkeypatch.setattr(controllers, 'get_current_sync', current)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url='http://test',
    ) as client:
        response = await client.get('/v1/sync-runs/current')

    assert response.status_code == 200
    assert response.json()['active_run']['id'] == str(sync_run['id'])


async def test_get_sync_run_includes_items(sync_run, employee, monkeypatch):
    run_id = sync_run['id']
    item_id = uuid.uuid4()

    async def get(requested_id):
        assert requested_id == run_id
        return {
            **sync_run,
            'items': [{
                'id': item_id,
                'external_id': employee.external_id,
                'status': 'succeeded',
                'attempts': 1,
                'source_payload': employee.model_dump(mode='json'),
                'destination_response': {'status': 'created'},
                'error_message': None,
                'started_at': sync_run['queued_at'],
                'finished_at': sync_run['queued_at'],
            }],
        }

    monkeypatch.setattr(controllers, 'get_sync_run', get)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url='http://test',
    ) as client:
        response = await client.get(f'/v1/sync-runs/{run_id}')

    assert response.status_code == 200
    assert response.json()['items'][0]['external_id'] == employee.external_id
