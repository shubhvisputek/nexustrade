.PHONY: dev test lint type-check build docker-up docker-down clean

dev:
	uv sync --extra dev

test:
	uv run pytest tests/ -v --tb=short

test-unit:
	uv run pytest tests/unit/ -v --tb=short -m unit

test-integration:
	uv run pytest tests/integration/ -v --tb=short -m integration

test-cov:
	uv run pytest tests/ --cov=nexustrade --cov-report=term-missing

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

lint-fix:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

type-check:
	uv run mypy src/nexustrade/

build:
	uv build

docker-up:
	docker compose --profile cpu-only up -d

docker-up-full:
	docker compose --profile full up -d

docker-down:
	docker compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist/ build/ *.egg-info
