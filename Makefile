.PHONY: dev dev-server dev-client install install-server install-client setup start build lint lint-server lint-client test test-server test-client clean onboard onboard-show demo-verify demo-prepare

PYTHON := server/.venv/bin/python

# ─── Development ────────────────────────────────────────
dev: ## Start both server and client in dev mode
	@./scripts/dev.sh

dev-server: ## Start Python backend
	cd server && SWIFTAGENT_DEV=1 SWIFTAGENT_NO_BROWSER=1 .venv/bin/python -m swiftagent.main

dev-client: ## Start Vite React frontend
	cd client && npm run dev

# ─── Install ────────────────────────────────────────────
install: install-server install-client ## Install all dependencies

install-server: ## Install Python dependencies
	cd server && python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -e ".[dev]"

install-client: ## Install Node dependencies
	cd client && npm ci

setup: install ## Install every development dependency

# ─── Onboard ────────────────────────────────────────────
onboard: ## Interactive local-agent setup wizard
	cd server && .venv/bin/python -m swiftagent.cli onboard

onboard-show: ## Show free local agent detection
	cd server && .venv/bin/python -m swiftagent.cli onboard --show

# ─── Reproducible demo ──────────────────────────────────
demo-verify: ## Verify the deterministic demo fixture without calling an agent
	$(PYTHON) scripts/demo_workspace.py verify

demo-prepare: ## Reset demo workspaces for Claude Code, Codex, and OpenCode
	$(PYTHON) scripts/demo_workspace.py prepare-all

# ─── Production ─────────────────────────────────────────
start: ## Start in production mode
	@$(MAKE) build-client
	cd server && .venv/bin/python -m swiftagent.main

build-client: ## Build frontend for production
	cd client && npm run build

build: build-client ## Build the production web bundle

# ─── Testing ────────────────────────────────────────────
lint: lint-server lint-client ## Run static quality checks

lint-server:
	cd server && .venv/bin/python -m ruff check swiftagent tests

lint-client:
	cd client && npm run lint

test: test-server test-client ## Run all automated checks

test-server: ## Run Python tests
	cd server && .venv/bin/python -m pytest tests/ -v

test-client: ## Typecheck and build the frontend
	cd client && npm run build

# ─── Cleanup ────────────────────────────────────────────
clean: ## Clean all build artifacts
	rm -rf client/dist client/node_modules
	find server -type d -name __pycache__ -exec rm -rf {} +
	find server -name "*.pyc" -delete
