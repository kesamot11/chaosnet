.PHONY: check fmt integration demo-export

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

# Save recorded runs for the public demo (#233, ADR-012): the controller's own answer for
# each experiment, byte for byte, never edited. The index, demo/runs.json, is written by hand.
#   make demo-export IDS="41 42"
demo-export:
	@test -n "$(IDS)" || { echo 'usage: make demo-export IDS="41 42"'; exit 1; }
	@mkdir -p frontend/public/demo
	@for id in $(IDS); do \
	  curl -fsS http://127.0.0.1:8476/experiments/$$id -o frontend/public/demo/$$id.json || exit 1; \
	  echo "frontend/public/demo/$$id.json"; \
	done
