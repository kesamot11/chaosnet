.PHONY: check fmt

PROJECTS := backend lab

# Run every quality gate that CI runs, for each Python project.
check:
	@set -e; for p in $(PROJECTS); do echo "== $$p"; \
	  (cd $$p && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest); \
	done

# Apply formatting and safe lint fixes.
fmt:
	@for p in $(PROJECTS); do (cd $$p && uv run ruff format . && uv run ruff check --fix .); done
