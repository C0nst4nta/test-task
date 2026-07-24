# Synchronization Service

A backend prototype that synchronizes employee data from System A to System B.

Stack: Python 3.12+ · FastAPI · PostgreSQL · SQLAlchemy Core · asyncpg · Alembic ·
Celery · Redis · Pydantic v2 · httpx.

## Quick start

Docker with the Compose plugin is required.

```bash
cp .env.example .env
docker compose up --build
```

Before starting the application, configure external system addresses in `.env`. The
addresses must be reachable from the Docker network:

```dotenv
SYNC_SYSTEM_A_BASE_URL=http://system-a:8000
SYNC_SYSTEM_B_BASE_URL=http://system-b:8000
```

Docker Compose starts `postgres`, `redis`, `api`, `worker`, and `beat`. The API service
applies Alembic migrations before starting the web server. The worker executes Celery
tasks, while beat schedules periodic synchronization runs.

The following endpoints are then available:

- Swagger UI: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>

Start a synchronization manually:

```bash
curl -X POST http://localhost:8000/v1/sync-runs \
  -H 'Content-Type: application/json' \
  -d '{"sync_type":"employees"}'
```

The endpoint immediately returns `202 Accepted` with a run in the `queued` state. A
Celery worker performs the actual synchronization. Check its state with:

```bash
curl http://localhost:8000/v1/sync-runs/current
curl http://localhost:8000/v1/sync-runs
curl http://localhost:8000/v1/sync-runs/<run_id>
```

Retry an unsuccessful synchronization:

```bash
curl -X POST http://localhost:8000/v1/sync-runs/<run_id>/retry
```

## API

| Method and path | Description |
| --- | --- |
| `POST /v1/sync-runs` | Queue a manual synchronization run |
| `GET /v1/sync-runs/current` | Return the active and most recent finished runs |
| `GET /v1/sync-runs` | Return paginated and filtered run history |
| `GET /v1/sync-runs/{id}` | Return a run and its per-item results |
| `POST /v1/sync-runs/{id}/retry` | Retry failed items in a separate run |
| `GET /health` | Check the API and PostgreSQL connection |

Run history can be filtered by `status`, `trigger`, and `sync_type`. Pagination uses
`limit` and `offset`.

## Project structure

```text
src/core/                    configuration, PostgreSQL, and web application factory
src/api/schemas/             Pydantic request, response, and provider schemas
src/api/models/              SQLAlchemy Core tables and database queries
src/api/controllers/         API use-case orchestration
src/api/providers/           HTTP clients for Systems A and B
src/api/services/            synchronization logic and Celery task dispatch
src/api/v1/endpoints/        thin FastAPI endpoints
src/worker/                  Celery application, worker tasks, and beat schedule
src/migrations/postgres/     Alembic migrations
tests/                       unit and API tests
```

The structure and style follow the `1wash` approach: a `src` layout, separated
`schemas → models → controllers → endpoints` layers, asynchronous I/O, SQLAlchemy
Core, dedicated provider adapters, one import per line, single quotes, and a 95-character
line limit.

## Architecture and assumptions

### Database entities

The service has two main entities.

`sync_run` represents one synchronization run. It stores the synchronization type,
trigger (`manual`, `scheduled`, or `retry`), status, counters, run-level error, and
timestamps. `retry_of_id` links a retry to its original run. A partial unique index
prevents two `queued` or `running` runs of the same `sync_type` from existing at the
same time.

`sync_item` represents one employee processed within a run. It stores the external ID,
source snapshot, System B response, status, attempt count, error, and timestamps. The
snapshot provides an audit trail and allows the service to retry only failed items
without depending on the current state of System A.

There is no separate local employee table. The service orchestrates data transfer,
while Systems A and B remain the data owners. A duplicated domain model would create a
third source of truth without a supporting business requirement.

### Background processing

The HTTP endpoint inserts a `sync_run` with the `queued` status and publishes its UUID
to Redis. The Celery worker atomically changes that specific run from `queued` to
`running` before processing it. Long-running external calls therefore do not happen
inside an HTTP request, and repeated delivery of the same message cannot start an
already claimed run twice.

Celery beat publishes a scheduling task every 300 seconds. The interval is configured
with `SYNC_SCHEDULE_INTERVAL_SECONDS`. When a worker starts, interrupted `running` runs
are returned to the queue and all `queued` runs are published again. Items that already
succeeded are not sent again.

Delivery semantics are at least once. System B must therefore implement an idempotent
upsert by `external_id`.

### Synchronization flow

`EmployeeSyncService` coordinates one complete run:

1. For a regular run, it fetches employees from System A.
2. For a retry, it loads failed snapshots from the original run.
3. It stores one `sync_item` snapshot for every employee.
4. It sends each pending item to System B.
5. It records the response or error for every item.
6. It calculates and stores the final `sync_run` status and counters.

A completed run receives one of these statuses:

- `completed` when every item succeeded;
- `partially_completed` when only some items succeeded;
- `failed` when the source request failed or every processed item failed.

### Error handling and retries

- Temporary System A and System B errors use exponential backoff.
- Failure to fetch employees from System A fails the entire run.
- Failure to send one employee to System B is stored in `sync_item`; processing
  continues for the remaining employees.
- Tracebacks and database driver details are not exposed through the API.
- A retry creates a new auditable run and processes failed snapshots from the original.
- A database constraint prevents concurrent manual and scheduled runs of the same type.

### External API contracts

The synchronization service depends on `SystemAClient` and `SystemBClient`. Their base
URLs are configured with `SYNC_SYSTEM_A_BASE_URL` and `SYNC_SYSTEM_B_BASE_URL`.

System A must expose:

```http
GET /records
```

System B must expose an idempotent upsert endpoint:

```http
PUT /records/{external_id}
```

The current prototype does not use API keys. Provider adapters are the appropriate
place to add authentication or map a different external contract in the future.

### Adding synchronization types

The service currently supports employee synchronization only. Add another type as a
separate service with its own Pydantic contract and provider adapters. The Celery
worker, beat scheduler, history, retry mechanism, and database tables can be reused.

## Development

PostgreSQL, Redis, the API, Celery worker, and beat run through Docker Compose. Local
checks use a standard virtual environment and pip.

```bash
cp .env.example .env
make bootstrap
docker compose up --build
```

Run local checks through the Makefile:

```bash
make lint
make test
make format
```

Apply migrations or generate a new migration:

```bash
make migrate
make migration M=add_new_field
```

Alembic runs locally from `.venv` and connects to the Docker PostgreSQL instance at
`localhost:5432`.

Stop the services with `docker compose down`. `make clean` removes the local virtual
environment, Python and test caches, coverage data, and build artifacts.

## Production considerations

- Use a highly available Redis deployment, Redis Sentinel, or RabbitMQ when required.
- Run exactly one beat instance or use a distributed scheduler.
- Add OAuth2/RBAC for the internal administration API.
- Store secrets in a secret manager and enable TLS for external APIs.
- Add OpenTelemetry, Prometheus metrics, correlation IDs, and alerting.
- Define retention, payload archival, and personal data masking policies.
- Add rate limiting and a circuit breaker for external systems.
- Define external system SLAs and a reconciliation policy.
- Add CI, integration and contract tests, and a zero-downtime migration policy.

## Out of scope

Authentication and production deployment are intentionally excluded from this
prototype. Publishing the repository to GitHub is also left to the repository owner.
