# pb-api

PB Platform core API service (FastAPI + SQLAlchemy + Alembic).

Quick start (from repo root):

```bash
make setup-api      # uv sync --all-groups
make migrate        # alembic upgrade head
make dev-api        # uvicorn on :8000
```

Quality gates:

```bash
make lint-api typecheck-api test-api
```

See `docs/DEVELOPER_GUIDE.md` at the repo root for full documentation:
configuration reference, auth flows, and how to add endpoints, models and
migrations.
