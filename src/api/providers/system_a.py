import httpx

from .. import schemas


class ExternalSystemError(Exception):
    """Raised when an external system cannot complete an operation."""


class SystemAClient:
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
                f'System A returned HTTP {error.response.status_code}',
            )
        except httpx.HTTPError:
            raise ExternalSystemError('System A is unavailable')

    async def fetch_employees(self) -> list[schemas.EmployeeRecord]:
        raw = await self._request('GET', '/records')
        payload = schemas.SystemAResponse.model_validate(raw)
        return payload.items

    async def aclose(self) -> None:
        await self._session.aclose()
