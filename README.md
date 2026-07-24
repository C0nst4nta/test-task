# Synchronization Service

Backend-прототип сервиса синхронизации данных из системы A в систему B.

Стек: Python 3.12+ · FastAPI · PostgreSQL · SQLAlchemy Core · asyncpg · Alembic ·
Celery · Redis · Pydantic v2 · httpx.

## Быстрый запуск

Нужен Docker с Compose plugin.

```bash
cp .env.example .env
docker compose up --build
```

Перед запуском укажите в `.env` доступные из Docker network адреса внешних систем:

```dotenv
SYNC_SYSTEM_A_BASE_URL=http://system-a:8000
SYNC_SYSTEM_B_BASE_URL=http://system-b:8000
```

Compose запускает `postgres`, `redis`, `api`, `worker` и `beat`. API применяет
Alembic-миграции и запускает web-сервер, worker исполняет задачи Celery, а beat
публикует периодические запуски. После этого доступны:

- Swagger UI: <http://localhost:8000/docs>
- health check: <http://localhost:8000/health>

Ручной запуск синхронизации:

```bash
curl -X POST http://localhost:8000/v1/sync-runs \
  -H 'Content-Type: application/json' \
  -d '{"sync_type":"employees"}'
```

Endpoint сразу возвращает `202 Accepted` и запуск в состоянии `queued`. Сама работа
выполняется Celery worker. Состояние можно проверить так:

```bash
curl http://localhost:8000/v1/sync-runs/current
curl http://localhost:8000/v1/sync-runs
curl http://localhost:8000/v1/sync-runs/<run_id>
```

Повторить неуспешную синхронизацию:

```bash
curl -X POST http://localhost:8000/v1/sync-runs/<run_id>/retry
```

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
src/api/services/            executor и публикация задач Celery
src/api/v1/endpoints/        тонкие FastAPI endpoints
src/worker/                  Celery application, worker tasks и beat schedule
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

HTTP endpoint вставляет `sync_run(status=queued)` и публикует UUID запуска в Redis.
Celery worker атомарно переводит именно этот запуск из `queued` в `running` и выполняет
обработку. Поэтому долгий внешний вызов не живёт внутри HTTP request, а повторная
доставка того же сообщения не запускает уже начатую работу второй раз.

Celery beat публикует задачу планирования каждые 300 секунд. Интервал настраивается
через `SYNC_SCHEDULE_INTERVAL_SECONDS`. При старте worker незавершённые `running`
запуски возвращаются в очередь, а все `queued` задачи публикуются повторно; успешные
items не отправляются повторно.

Семантика доставки — at least once, поэтому endpoint системы B должен реализовывать
идемпотентный upsert по `external_id`.

### Ошибки

- Временные ошибки A/B повторяются заданное число раз с exponential backoff.
- Ошибка получения списка из A завершает весь запуск как `failed`.
- Ошибка отдельной записи в B сохраняется в `sync_item`; остальные записи продолжают
  обрабатываться. Итог — `partially_completed` или `failed`.
- Наружу не возвращаются traceback и детали драйвера БД.
- Retry создаёт новый аудируемый запуск и обрабатывает failed snapshots исходного.
- Ограничение БД защищает от гонки двух ручных/периодических запусков одного типа.

### Подключение внешних API

Бизнес-логика зависит от `SystemAClient` и `SystemBClient`. Оба клиента работают по
HTTP, а их base URL задаются через `SYNC_SYSTEM_A_BASE_URL` и
`SYNC_SYSTEM_B_BASE_URL`. Система A должна отдавать записи через `GET /records`, а
система B принимать idempotent upsert через `PUT /records/{external_id}`. Авторизация
и mapping конкретного внешнего контракта добавляются в provider-адаптеры.

### Добавление новых типов синхронизации

`SyncExecutor` использует registry `sync_type → handler`. Новый тип добавляется как
отдельный handler с операциями `fetch/send`, Pydantic-контракт и запись в registry.
Общие Celery worker, beat, история, retry и таблицы остаются без изменений. Если у типа
появится собственная политика расписания, её следует хранить в таблице конфигураций и
планировать независимо по `sync_type`.

## Разработка через Docker Compose

PostgreSQL, Redis, API, Celery worker и beat запускаются через Docker Compose. Локальные
проверки используют стандартный `venv` и `pip`.

```bash
cp .env.example .env
make bootstrap
docker compose up --build
```

Проверки запускаются локально через Makefile:

```bash
make lint
make test
make format
```

Применить или сгенерировать миграцию:

```bash
make migrate
make migration M=add_new_field
```

Alembic запускается локально из `.venv` и подключается к уже запущенному PostgreSQL
через `localhost:55432`.

Остановить сервисы можно через `docker compose down`. Команда `make clean` удаляет
локальное виртуальное окружение, Python/test-кэши, coverage и build artifacts.

## Что изменить для production

- заменить Redis на отказоустойчивый Redis/Sentinel или RabbitMQ при требованиях к HA;
- запускать ровно один экземпляр beat либо использовать распределённый scheduler;
- настроить OAuth2/RBAC для внутренней админ-системы;
- хранить secrets в secret manager и включить TLS для внешних API;
- добавить OpenTelemetry, Prometheus-метрики, correlation ID и alerting;
- определить retention/архивацию больших payload и маскирование персональных данных;
- добавить rate limiting, circuit breaker и jitter к retry;
- зафиксировать SLA внешних систем и политику reconciliation;
- добавить CI, integration/contract tests и zero-downtime migration policy.

## Не включено

Авторизация и production deployment намеренно не реализованы по условиям задания.
Публикация в GitHub также остаётся за владельцем репозитория: после создания remote
достаточно закоммитить проект и отправить ветку.
