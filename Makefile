.PHONY: dev dev-server dev-client install install-server install-client setup start build lint lint-server lint-client test test-server test-client clean onboard onboard-show

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
onboard: ## Interactive Claude setup wizard
	cd server && .venv/bin/python -m swiftagent.cli onboard

onboard-show: ## Show current Claude readiness status
	cd server && .venv/bin/python -m swiftagent.cli onboard --show

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
