import httpx

from .. import schemas


class ExternalSystemError(Exception):
    """Raised when an external system cannot complete an operation."""


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
        except httpx.HTTPStatusError as error:
            raise ExternalSystemError(
                f'System A returned HTTP {error.response.status_code}',
            )
        except (httpx.HTTPError, ValueError):
            raise ExternalSystemError('System A is unavailable')
        return payload.items

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
