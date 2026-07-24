# Synchronization Service

Backend-прототип сервиса синхронизации данных из системы A в систему B.

Стек: Python 3.12+ · FastAPI · PostgreSQL · SQLAlchemy Core · asyncpg · Alembic ·
Pydantic v2 · httpx.

## Быстрый запуск

Нужен Docker с Compose plugin.

```bash
cp .env.example .env
docker compose up --build
```

При старте контейнер API применит миграции. После этого доступны:

- Swagger UI: <http://localhost:8000/docs>
- health check: <http://localhost:8000/health>
- mock системы A: <http://localhost:8000/mock/system-a/records>
- содержимое mock системы B: <http://localhost:8000/mock/system-b/records>

Ручной запуск синхронизации:

```bash
curl -X POST http://localhost:8000/v1/sync-runs \
  -H 'Content-Type: application/json' \
  -d '{"sync_type":"employees"}'
```

Endpoint сразу возвращает `202 Accepted` и запуск в состоянии `queued`. Сама работа
выполняется фоновым worker. Состояние можно проверить так:

```bash
curl http://localhost:8000/v1/sync-runs/current
curl http://localhost:8000/v1/sync-runs
curl http://localhost:8000/v1/sync-runs/<run_id>
```

Повторить неуспешную синхронизацию:

```bash
curl -X POST http://localhost:8000/v1/sync-runs/<run_id>/retry
```

Для демонстрации частичной ошибки можно запустить сервис с fault injection:

```bash
SYNC_MOCK_SYSTEM_B_FAIL_IDS=employee-003 docker compose up --build
```

После исчерпания retry один элемент будет `failed`, а весь запуск —
`partially_completed`. Отказ системы A включается переменной
`SYNC_MOCK_SYSTEM_A_FAIL=true`.

## API

| Метод и путь | Назначение |
| --- | --- |
| `POST /v1/sync-runs` | Поставить ручную синхронизацию в очередь |
| `GET /v1/sync-runs/current` | Текущий активный и последний завершённый запуск |
| `GET /v1/sync-runs` | История с пагинацией и фильтрами |
| `GET /v1/sync-runs/{id}` | Запуск и результаты по каждому объекту |
| `POST /v1/sync-runs/{id}/retry` | Повторить failed-объекты отдельным запуском |
| `GET /health` | Проверить API и соединение с PostgreSQL |

История фильтруется по `status`, `trigger` и `sync_type`; поддерживает `limit` и
`offset`.

## Структура

```text
src/core/                    конфигурация, PostgreSQL, фабрика web-приложения
src/api/schemas/             входные и выходные Pydantic-схемы
src/api/models/              таблицы SQLAlchemy Core и запросы к БД
src/api/controllers/         orchestration и преобразование ошибок в HTTP
src/api/providers/           заменяемые HTTP-клиенты систем A и B
src/api/services/            executor, DB-backed worker и scheduler
src/api/v1/endpoints/        тонкие FastAPI endpoints
src/api/mock/                mock HTTP API систем A и B
src/migrations/postgres/     Alembic-миграции
tests/                       unit/API tests
```

Структура и стиль повторяют подход проекта `1wash`: src-layout, слои
`schemas → models → controllers → endpoints`, async I/O, SQLAlchemy Core, отдельные
provider-адаптеры, один импорт на строку, одинарные кавычки и длина строки 95 символов.

## Архитектурные решения и допущения

### Сущности и структура БД

Выделены две основные сущности.

`sync_run` — один запуск. Хранит тип синхронизации, причину запуска (`manual`,
`scheduled`, `retry`), общий статус, счётчики, общую ошибку и временные метки. Поле
`retry_of_id` связывает новую попытку с исходным запуском. Частичный уникальный индекс
не разрешает одновременно иметь два `queued`/`running` запуска одного `sync_type`.

`sync_item` — результат обработки одного объекта в рамках запуска. Здесь находятся
external ID, исходный snapshot, ответ системы B, status, число попыток, ошибка и
временные метки. Snapshot нужен для аудита и позволяет повторять только failed-объекты,
не полагаясь на изменившееся состояние системы A.

Отдельная локальная таблица сотрудников не создавалась: сервис оркестрирует передачу,
а владельцами данных остаются A и B. Дублирование доменной модели без отдельного
бизнес-требования создало бы третий источник истины.

### Фоновая обработка

HTTP endpoint только вставляет `sync_run(status=queued)`. Worker атомарно забирает
следующий запуск через `SELECT ... FOR UPDATE SKIP LOCKED`, переводит его в `running`
и выполняет обработку. Поэтому долгий внешний вызов не живёт внутри HTTP request.

Планировщик использует ту же команду постановки в очередь каждые 300 секунд. Интервал
настраивается через `SYNC_SCHEDULE_INTERVAL_SECONDS`. При рестарте незавершённый
`running` запуск возвращается в очередь; успешные items не отправляются повторно.

Семантика доставки — at least once. Mock B, как и ожидаемый реальный endpoint,
реализует idempotent upsert по `external_id`.

### Ошибки

- Временные ошибки A/B повторяются заданное число раз с exponential backoff.
- Ошибка получения списка из A завершает весь запуск как `failed`.
- Ошибка отдельной записи в B сохраняется в `sync_item`; остальные записи продолжают
  обрабатываться. Итог — `partially_completed` или `failed`.
- Наружу не возвращаются traceback и детали драйвера БД.
- Retry создаёт новый аудируемый запуск и обрабатывает failed snapshots исходного.
- Ограничение БД защищает от гонки двух ручных/периодических запусков одного типа.

### Замена mock на реальные API

Бизнес-логика зависит от `SystemAClient` и `SystemBClient`, а не от mock-хранилища.
Оба клиента уже работают по HTTP. Для интеграции достаточно изменить base URL и при
необходимости добавить в provider авторизацию и mapping реального контракта. Mock API
находится в отдельном router и не импортируется executor.

### Добавление новых типов синхронизации

`SyncExecutor` использует registry `sync_type → handler`. Новый тип добавляется как
отдельный handler с операциями `fetch/send`, Pydantic-контракт и запись в registry.
Общие worker, scheduler, история, retry и таблицы остаются без изменений. Если у типа
появится собственная политика расписания, её следует хранить в таблице конфигураций и
планировать независимо по `sync_type`.

## Локальная разработка

```bash
make bootstrap
cp .env.example .env
docker compose up -d postgres
make migrate
make lint
make test
python -m src.api
```

Сгенерировать миграцию:

```bash
make migration M=add_new_field
```

## Что изменить для production

- вынести API, scheduler и worker в отдельные процессы/контейнеры;
- использовать полноценный task broker (RabbitMQ/Kafka) либо оставить PostgreSQL queue
  с отдельным процессом и `LISTEN/NOTIFY` вместо polling;
- добавить distributed scheduler leader election;
- настроить OAuth2/RBAC для внутренней админ-системы;
- хранить secrets в secret manager, включить TLS и ограничить mock endpoints;
- добавить OpenTelemetry, Prometheus-метрики, correlation ID и alerting;
- определить retention/архивацию больших payload и маскирование персональных данных;
- добавить rate limiting, circuit breaker и jitter к retry;
- зафиксировать SLA внешних систем и политику reconciliation;
- добавить CI, integration/contract tests и zero-downtime migration policy.

## Не включено

Авторизация и production deployment намеренно не реализованы по условиям задания.
Публикация в GitHub также остаётся за владельцем репозитория: после создания remote
достаточно закоммитить проект и отправить ветку.
