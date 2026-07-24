import httpx

from .. import schemas
from .system_a import ExternalSystemError


class SystemBClient:
    def __init__(self, base_url: str, timeout: float):
        self._base_url = (base_url or '').rstrip('/')
        self._base_headers = {'Accept': 'application/json'}
        self._session = httpx.AsyncClient(timeout=timeout)

    async def _request(
        self,
        method: str,
        path: str,
        headers: dict | None = None,
        *,
        json: dict | None = None,
        params: dict | None = None,
        **kwargs,
    ) -> dict | list:
        url = f'{self._base_url}/{path.lstrip("/")}'
        merged_headers = {**self._base_headers, **(headers or {})}
        try:
            response = await self._session.request(
                method,
                url,
                headers=merged_headers,
                json=json,
                params=params,
                **kwargs,
            )
            response.raise_for_status()
            return response.json() if response.content else None
        except httpx.HTTPStatusError as error:
            raise ExternalSystemError(
                f'System B returned HTTP {error.response.status_code}',
            )
        except httpx.HTTPError:
            raise ExternalSystemError('System B is unavailable')

    async def upsert_employee(
        self,
        employee: schemas.EmployeeRecord,
    ) -> schemas.SystemBResponse:
        payload = schemas.SystemBRecord(
            full_name=employee.full_name,
            email=employee.email,
            department=employee.department,
            source_updated_at=employee.updated_at,
        )
        raw = await self._request(
            'PUT',
            f'/records/{employee.external_id}',
            json=payload.model_dump(mode='json'),
        )
        return schemas.SystemBResponse.model_validate(raw)

    async def aclose(self) -> None:
        await self._session.aclose()
