.PHONY: dev dev-server dev-client install install-server install-client clean

# ─── Development ────────────────────────────────────────
dev: ## Start both server and client in dev mode
	@echo "Starting SwiftAgent..."
	@$(MAKE) dev-server &
	@sleep 2
	@$(MAKE) dev-client

dev-server: ## Start Python backend
	cd server && SWIFTAGENT_DEV=1 SWIFTAGENT_NO_BROWSER=1 python -m swiftagent.main

dev-client: ## Start Vite React frontend
	cd client && npm run dev

# ─── Install ────────────────────────────────────────────
install: install-server install-client ## Install all dependencies

install-server: ## Install Python dependencies
	cd server && pip install -r requirements.txt

install-client: ## Install Node dependencies
	cd client && npm install

# ─── Onboard ────────────────────────────────────────────
onboard: ## Interactive Claude setup wizard
	cd server && python -m swiftagent.cli onboard

onboard-show: ## Show current Claude readiness status
	cd server && python -m swiftagent.cli onboard --show

# ─── Production ─────────────────────────────────────────
start: ## Start in production mode
	cd server && python -m swiftagent.main

build-client: ## Build frontend for production
	cd client && npm run build

# ─── Testing ────────────────────────────────────────────
test: test-server test-client ## Run all tests

test-server: ## Run Python tests
	cd server && python -m pytest tests/ -v

test-client: ## Run frontend tests
	cd client && npm test

# ─── Cleanup ────────────────────────────────────────────
clean: ## Clean all build artifacts
	rm -rf client/dist client/node_modules
	find server -type d -name __pycache__ -exec rm -rf {} +
	find server -name "*.pyc" -delete
