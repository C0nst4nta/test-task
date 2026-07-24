.DEFAULT: help
.PHONY: help run stop bootstrap migrate migration lint format test clean


VENV_DIR=.venv
PYTHON=$(VENV_DIR)/bin/python


help:
	@echo "Please use \`$(MAKE) <target>' where <target> is one of the following:"
	@echo "  run        - start PostgreSQL and the API with Docker Compose"
	@echo "  stop       - stop Docker Compose services"
	@echo "  bootstrap  - create the virtual environment and install dependencies"
	@echo "  migrate    - apply PostgreSQL migrations"
	@echo "  migration  - create a migration; M argument is mandatory"
	@echo "  lint       - inspect project source code"
	@echo "  format     - format project source code"
	@echo "  test       - run tests"
	@echo "  clean      - remove local build and test artifacts"

run:
	docker compose up --build

stop:
	docker compose down

bootstrap: $(VENV_DIR)/bin/activate
$(VENV_DIR)/bin/activate:
	uv venv $(VENV_DIR)
	uv sync --all-extras --python $(PYTHON)

migrate: bootstrap
	$(PYTHON) -m src.cli upgrade head

migration: bootstrap
	$(PYTHON) -m src.cli revision --autogenerate -m "$(M)"

lint: bootstrap
	$(PYTHON) -m ruff check src tests

format: bootstrap
	$(PYTHON) -m ruff format src tests

test: bootstrap
	$(PYTHON) -m pytest

clean:
	rm -rf $(VENV_DIR) build htmlcov sync_service.egg-info .coverage .pytest_cache .ruff_cache
