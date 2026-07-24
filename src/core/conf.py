import functools
import typing

import pydantic
import pydantic_settings


class Settings(pydantic_settings.BaseSettings):
    """Application settings loaded from environment variables or `.env`."""

    model_config = pydantic_settings.SettingsConfigDict(
        env_file='.env',
        env_prefix='SYNC_',
        extra='ignore',
    )

    app_host: str = '0.0.0.0'
    app_port: int = 8000
    log_level: str = 'info'
    debug: bool = False

    database_url: str = 'postgresql+asyncpg://sync:sync@localhost:55432/sync'
    database_pool_size: int = 5
    database_max_overflow: int = 10

    schedule_enabled: bool = True
    schedule_on_start: bool = False
    schedule_interval_seconds: pydantic.PositiveFloat = 300
    worker_poll_interval_seconds: pydantic.PositiveFloat = 1

    system_a_base_url: str = 'http://127.0.0.1:8000/mock/system-a'
    system_b_base_url: str = 'http://127.0.0.1:8000/mock/system-b'
    external_api_timeout_seconds: pydantic.PositiveFloat = 5
    external_api_max_retries: pydantic.PositiveInt = 3
    external_api_retry_delay_seconds: pydantic.NonNegativeFloat = 0.2

    mock_system_a_fail: bool = False
    mock_system_b_fail_ids: str = ''

    @property
    def mock_system_b_failed_ids(self) -> set[str]:
        return {
            external_id.strip()
            for external_id in self.mock_system_b_fail_ids.split(',')
            if external_id.strip()
        }


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    """Clear cached settings. Intended for tests."""
    get_settings.cache_clear()


def __getattr__(name: str) -> typing.Any:
    return getattr(get_settings(), name)
