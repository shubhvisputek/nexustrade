.PHONY: help setup dev test test-unit test-integration test-cov lint lint-fix type-check build up up-full down logs clean deploy

COMPOSE := docker compose
COMPOSE_CPU := $(COMPOSE) -f docker-compose.yml -f docker-compose.cpu-only.yml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies (uv sync --extra all)
	uv sync --extra agents --extra data --extra execution --extra ml --extra web --extra notifications

dev: ## Start development services (Redis + Ollama only)
	docker run -d --name nexus-redis -p 6379:6379 redis:7-alpine 2>/dev/null || docker start nexus-redis
	@echo "Redis started on localhost:6379"
	@echo "Start Ollama separately with: ollama serve"

test: ## Run all tests
	uv run pytest tests/ -v --tb=short

test-unit: ## Run unit tests only
	uv run pytest tests/ -v --tb=short -m unit

test-integration: ## Run integration tests
	uv run pytest tests/ -v --tb=short -m integration

test-cov: ## Run tests with coverage
	uv run pytest tests/ --cov=nexustrade --cov-report=term-missing

lint: ## Run linting (ruff check + format check)
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

lint-fix: ## Auto-fix linting issues
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

type-check: ## Run mypy type checking
	uv run mypy src/nexustrade/

build: ## Build all Docker images
	$(COMPOSE_CPU) --profile cpu-only build

up: ## Start all services (cpu-only profile)
	$(COMPOSE_CPU) --profile cpu-only up -d

up-full: ## Start all services including GPU (full profile)
	$(COMPOSE) --profile full up -d

down: ## Stop all services
	$(COMPOSE) --profile cpu-only --profile full down

logs: ## Tail service logs
	$(COMPOSE) --profile cpu-only logs -f

clean: ## Remove containers, volumes, and caches
	$(COMPOSE) --profile cpu-only --profile full down -v --remove-orphans 2>/dev/null || true
	docker rm -f nexus-redis 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .mypy_cache .ruff_cache dist build

deploy: ## Build + start (production-like)
	$(COMPOSE_CPU) --profile cpu-only build
	$(COMPOSE_CPU) --profile cpu-only up -d
	@echo "Waiting for services to become healthy..."
	@sleep 10
	$(COMPOSE) ps
