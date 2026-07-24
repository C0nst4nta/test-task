import httpx
import pytest

from src.api import providers
from src.api.providers import system_a
from src.api.providers import system_b


async def test_system_a_client_parses_records(employee, monkeypatch):
    async def handler(request):
        assert request.url.path == '/records'
        return httpx.Response(200, json={'items': [employee.model_dump(mode='json')]})

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(system_a.httpx, 'AsyncClient', lambda **kwargs: http_client)
    client = providers.SystemAClient('http://system-a.test', timeout=1)

    records = await client.fetch_employees()

    assert records == [employee]
    await client.aclose()
    assert http_client.is_closed


async def test_system_a_client_maps_http_error(monkeypatch):
    async def handler(request):
        return httpx.Response(503, json={'detail': 'unavailable'})

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(system_a.httpx, 'AsyncClient', lambda **kwargs: http_client)
    client = providers.SystemAClient('http://system-a.test', timeout=1)

    with pytest.raises(providers.ExternalSystemError, match='HTTP 503'):
        await client.fetch_employees()
    await client.aclose()


async def test_system_a_client_hides_connection_details(monkeypatch):
    async def handler(request):
        raise httpx.ConnectError('secret host details', request=request)

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(system_a.httpx, 'AsyncClient', lambda **kwargs: http_client)
    client = providers.SystemAClient('http://system-a.test', timeout=1)

    with pytest.raises(providers.ExternalSystemError, match='System A is unavailable'):
        await client.fetch_employees()
    await client.aclose()


async def test_system_b_client_maps_and_sends_record(employee, monkeypatch):
    async def handler(request):
        assert request.url.path == f'/records/{employee.external_id}'
        payload = __import__('json').loads(request.content)
        assert payload['source_updated_at'] == '2026-07-25T00:00:00Z'
        return httpx.Response(
            200,
            json={'external_id': employee.external_id, 'status': 'created'},
        )

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(system_b.httpx, 'AsyncClient', lambda **kwargs: http_client)
    client = providers.SystemBClient('http://system-b.test', timeout=1)

    response = await client.upsert_employee(employee)

    assert response.status == 'created'
    await client.aclose()


async def test_system_b_client_hides_connection_details(employee, monkeypatch):
    async def handler(request):
        raise httpx.ConnectError('secret host details', request=request)

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(system_b.httpx, 'AsyncClient', lambda **kwargs: http_client)
    client = providers.SystemBClient('http://system-b.test', timeout=1)

    with pytest.raises(providers.ExternalSystemError, match='System B is unavailable'):
        await client.upsert_employee(employee)
    await client.aclose()


async def test_owned_http_clients_are_closed():
    source = providers.SystemAClient('http://system-a.test', timeout=1)
    destination = providers.SystemBClient('http://system-b.test', timeout=1)

    await source.aclose()
    await destination.aclose()
