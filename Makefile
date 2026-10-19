.PHONY: check fmt integration

PROJECTS := backend lab frontend

# Run every quality gate that CI runs, for each project.
check:
	@set -e; for p in $(PROJECTS); do echo "== $$p"; \
	  if [ $$p = frontend ]; then (cd frontend && npm run check); \
	  else (cd $$p && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest); fi; \
	done

# Apply formatting and safe lint fixes.
fmt:
	@for p in $(PROJECTS); do \
	  if [ $$p = frontend ]; then (cd frontend && npm run fmt); \
	  else (cd $$p && uv run ruff format . && uv run ruff check --fix .); fi; \
	done

# Acceptance tests against the real Docker Compose lab (needs Docker). The backend venv is
# synced too, because the cleanup tests run the real fault CLI.
integration:
	cd backend && uv sync --locked -q
	cd lab && uv run pytest -m integration -v
