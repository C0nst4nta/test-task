import httpx

from .. import schemas


class ExternalSystemError(Exception):
    """Raised when an external system cannot complete an operation."""


def _external_error(system_name: str, error: Exception) -> ExternalSystemError:
    if isinstance(error, httpx.HTTPStatusError):
        return ExternalSystemError(
            f'{system_name} returned HTTP {error.response.status_code}',
        )
    return ExternalSystemError(f'{system_name} is unavailable')


class SystemAClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._owns_client = client is None

    async def fetch_employees(self) -> list[schemas.EmployeeRecord]:
        try:
            response = await self._client.get('/records')
            response.raise_for_status()
            payload = schemas.SystemAResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise _external_error('System A', error) from error
        return payload.items

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


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
        except (httpx.HTTPError, ValueError) as error:
            raise _external_error('System B', error) from error

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
