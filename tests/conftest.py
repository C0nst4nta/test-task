import datetime
import uuid

import pytest

from src.api import schemas


@pytest.fixture
def employee() -> schemas.EmployeeRecord:
    return schemas.EmployeeRecord(
        external_id='employee-test',
        full_name='Test Employee',
        email='employee@example.com',
        department='Engineering',
        updated_at=datetime.datetime(2026, 7, 25, tzinfo=datetime.UTC),
    )


@pytest.fixture
def sync_run() -> dict:
    now = datetime.datetime(2026, 7, 25, tzinfo=datetime.UTC)
    return {
        'id': uuid.uuid4(),
        'sync_type': 'employees',
        'trigger': 'manual',
        'status': 'queued',
        'retry_of_id': None,
        'total_items': 0,
        'succeeded_items': 0,
        'failed_items': 0,
        'error_message': None,
        'queued_at': now,
        'started_at': None,
        'finished_at': None,
    }
