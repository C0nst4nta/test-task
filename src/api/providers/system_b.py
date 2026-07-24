import httpx

from .. import schemas
from .system_a import ExternalSystemError


class SystemBClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._owns_client = client is None

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
        try:
            response = await self._client.put(
                f'/records/{employee.external_id}',
                json=payload.model_dump(mode='json'),
            )
            response.raise_for_status()
            return schemas.SystemBResponse.model_validate(response.json())
        except httpx.HTTPStatusError as error:
            raise ExternalSystemError(
                f'System B returned HTTP {error.response.status_code}',
            )
        except (httpx.HTTPError, ValueError):
            raise ExternalSystemError('System B is unavailable')

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
