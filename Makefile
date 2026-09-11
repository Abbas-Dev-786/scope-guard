sync:
	uv sync --locked --dev

api:
	uv run uvicorn services.api.app:app --reload --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

migrate:
	uv run alembic upgrade head
