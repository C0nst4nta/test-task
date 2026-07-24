import pytest

from src.core import retries


async def test_retry_retries_async_operation():
    calls = 0

    @retries.retry(exception=ValueError, max_retries=3, max_value=0)
    async def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ValueError
        return 'done'

    assert await operation() == 'done'
    assert calls == 3


async def test_retry_wrap_wraps_async_operation():
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError
        return 'done'

    wrapped = retries.retry_wrap(
        operation,
        exception=ValueError,
        max_retries=2,
        max_value=0,
    )

    assert await wrapped() == 'done'
    assert calls == 2


@pytest.mark.parametrize('exception', [str, (ValueError, str)])
def test_retry_rejects_non_exception_types(exception):
    with pytest.raises(RuntimeError):
        retries.retry(exception=exception)
