# One command per thing worth doing, and one that does all of them.
#
# `make test-all` exists because "reproducible setup" is a claim somebody has to
# be able to check in under five minutes from a clean checkout. It runs the lint
# and the unit suite offline and for free, then — only if Docker is up — the
# full local drill against emulators: upload, extract, reconcile, conflict, an
# unprompted market flip, and a redelivery that must not duplicate anything.
#
# Nothing here touches Google Cloud or spends a cent on a model. The deployed
# drill is `make verify-deployed`, kept separate on purpose: it costs money and
# mutates a real workspace, so it is never what a stranger runs by accident.

SHELL := /bin/bash
VENV  := api/.venv
PY    := $(VENV)/bin/python

.DEFAULT_GOAL := help
.PHONY: help install lint test test-local test-all verify-deployed diagram run clean

help: ## Show the commands
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk -F':.*?## ' '{printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'

$(VENV):
	python3.12 -m venv $(VENV) || python3 -m venv $(VENV)

install: $(VENV) ## Create the venv and install API dependencies
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -r api/requirements-dev.txt
	@(cd web && npm install --silent)

lint: ## ruff over the API, tsc over the web app
	@(cd api && ../$(PY) -m ruff check .)
	@(cd web && npx --no-install tsc --noEmit)

test: ## Unit tests — offline, no GCP, no model calls
	@(cd api && ../$(PY) -m pytest -q)

test-local: ## Full pipeline drill against the local emulator stack (needs Docker)
	@bash scripts/verify_local.sh

# The table is the point. A suite that prints five hundred lines and one
# traceback somewhere in the middle is a suite nobody reads to the end.
test-all: ## Everything runnable offline, with a pass/fail table
	@fail=0; \
	printf '\n%-28s %s\n' "STEP" "RESULT"; \
	printf '%-28s %s\n' "----" "------"; \
	run() { \
	  slug="$$1"; label="$$2"; cmd="$$3"; log="/tmp/regulens-$$slug.log"; \
	  if eval "$$cmd" >"$$log" 2>&1; then \
	    printf '%-28s \033[32mPASS\033[0m\n' "$$label"; \
	  else \
	    printf '%-28s \033[31mFAIL\033[0m  (%s)\n' "$$label" "$$log"; \
	    tail -n 12 "$$log" | sed 's/^/    /'; \
	    fail=1; \
	  fi; \
	}; \
	run ruff  "ruff (api)"       "(cd api && ../$(PY) -m ruff check .)"; \
	run pytest "pytest (api)"    "(cd api && ../$(PY) -m pytest -q)"; \
	run tsc   "tsc (web)"        "(cd web && npx --no-install tsc --noEmit)"; \
	run build "next build (web)" "(cd web && NEXT_PUBLIC_API_URL=http://localhost:8080 npx --no-install next build)"; \
	if docker info >/dev/null 2>&1; then \
	  run e2e "local e2e drill"  "bash scripts/verify_local.sh"; \
	else \
	  printf '%-28s \033[33mSKIP\033[0m  (Docker is not running)\n' "local e2e drill"; \
	fi; \
	echo; \
	if [ $$fail -eq 0 ]; then echo "All green."; else echo "Something failed — see the logs above."; exit 1; fi

verify-deployed: ## The same drill against the deployed stack (costs money, mutates a real workspace)
	@bash scripts/verify_e2e.sh

diagram: ## Regenerate docs/architecture.png (needs Graphviz)
	@$(PY) docs/architecture.py && echo "wrote docs/architecture.png"

run: ## Bring the whole stack up locally on Docker
	@docker compose up --build

clean: ## Remove build and test artefacts
	@rm -rf api/.ruff_cache api/.pytest_cache web/.next
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
