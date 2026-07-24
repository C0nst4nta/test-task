.DEFAULT: help
.PHONY: help bootstrap migrate migration lint format test clean


VENV_DIR=.venv
PYTHON=$(VENV_DIR)/bin/python
ALEMBIC=$(VENV_DIR)/bin/alembic
ALEMBIC_CONFIG=src/migrations/postgres/alembic.ini
BOOTSTRAP_STAMP=$(VENV_DIR)/.bootstrap
LOCAL_DATABASE_URL?=postgresql+asyncpg://sync:sync@localhost:55432/sync


help:
	@echo "Please use \`$(MAKE) <target>' where <target> is one of the following:"
	@echo "  bootstrap  - create venv and install development dependencies with pip"
	@echo "  migrate    - apply PostgreSQL migrations"
	@echo "  migration  - create a migration; M argument is mandatory"
	@echo "  lint       - inspect project source code"
	@echo "  format     - format project source code"
	@echo "  test       - run tests"
	@echo "  clean      - remove venv, caches and build artifacts"

bootstrap: $(BOOTSTRAP_STAMP)
$(BOOTSTRAP_STAMP): pyproject.toml
	python3 -m venv $(VENV_DIR)
	$(PYTHON) -m pip install -e '.[test]'
	touch $(BOOTSTRAP_STAMP)

migrate: bootstrap
	SYNC_DATABASE_URL=$(LOCAL_DATABASE_URL) $(ALEMBIC) -c $(ALEMBIC_CONFIG) upgrade head

migration: bootstrap
	SYNC_DATABASE_URL=$(LOCAL_DATABASE_URL) $(ALEMBIC) -c $(ALEMBIC_CONFIG) revision --autogenerate -m "$(M)"

lint: bootstrap
	$(PYTHON) -m ruff check src tests

format: bootstrap
	$(PYTHON) -m ruff format src tests

test: bootstrap
	$(PYTHON) -m pytest

clean:
	rm -rf .venv build htmlcov sync_service.egg-info .pytest_cache .ruff_cache
	rm -f .coverage
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
	find src tests -type f -name '*.py[co]' -delete
