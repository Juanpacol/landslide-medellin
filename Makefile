.PHONY: test test-unit test-integration lint typecheck coverage docker-up docker-down migrate

BACKEND := platform/backend

test: test-unit test-integration

test-unit:
	cd $(BACKEND) && PYTHONPATH=. pytest tests/unit -v

test-integration:
	cd $(BACKEND) && PYTHONPATH=. pytest tests/integration -v

coverage:
	cd $(BACKEND) && PYTHONPATH=. pytest tests/unit --cov=. --cov-report=term-missing

lint:
	cd $(BACKEND) && ruff check . && ruff format --check .

typecheck:
	cd $(BACKEND) && mypy .

docker-up:
	docker compose up

docker-down:
	docker compose down

migrate:
	cd $(BACKEND) && PYTHONPATH=. alembic upgrade head
