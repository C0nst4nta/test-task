.DEFAULT: help
.PHONY: help run stop postgres bootstrap build migrate migration lint format test clean


VENV_DIR=.venv
PYTHON=$(VENV_DIR)/bin/python
BOOTSTRAP_STAMP=$(VENV_DIR)/.bootstrap
LOCAL_DATABASE_URL?=postgresql+asyncpg://sync:sync@localhost:55432/sync


help:
	@echo "Please use \`$(MAKE) <target>' where <target> is one of the following:"
	@echo "  run        - start PostgreSQL and the API with Docker Compose"
	@echo "  stop       - stop Docker Compose services"
	@echo "  postgres   - start only PostgreSQL with Docker Compose"
	@echo "  bootstrap  - create venv and install development dependencies with pip"
	@echo "  build      - build the API image"
	@echo "  migrate    - apply PostgreSQL migrations"
	@echo "  migration  - create a migration; M argument is mandatory"
	@echo "  lint       - inspect project source code"
	@echo "  format     - format project source code"
	@echo "  test       - run tests"
	@echo "  clean      - stop services and remove Compose volumes"

run:
	docker compose up --build

stop:
	docker compose down

postgres:
	docker compose up -d postgres

build:
	docker compose build

bootstrap: $(BOOTSTRAP_STAMP)
$(BOOTSTRAP_STAMP):
	python3 -m venv $(VENV_DIR)
	$(PYTHON) -m pip install -e '.[test]'
	touch $(BOOTSTRAP_STAMP)

migrate: bootstrap postgres
	SYNC_DATABASE_URL=$(LOCAL_DATABASE_URL) $(PYTHON) -m src.cli upgrade head

migration: bootstrap postgres
	SYNC_DATABASE_URL=$(LOCAL_DATABASE_URL) $(PYTHON) -m src.cli revision --autogenerate -m "$(M)"

lint: bootstrap
	$(PYTHON) -m ruff check src tests

format: bootstrap
	$(PYTHON) -m ruff format src tests

test: bootstrap
	$(PYTHON) -m pytest

clean:
	docker compose down --volumes --remove-orphans
