"""
SwiftAgent — FastAPI application entry point.

Replaces the Electron main process (apps/desktop/src/main/index.ts).
Serves REST + WebSocket on a single port.
"""

from __future__ import annotations

import logging
import os
import uuid
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from swiftagent.api.routes import router as api_router
from swiftagent.api.websocket import router as ws_router
from swiftagent.config import load_dotenv
from swiftagent.storage import settings as settings_repo
from swiftagent.storage.database import close_database, init_database

logger = logging.getLogger(__name__)
VERSION = "0.3.0"


def _configure_logging() -> None:
    level = (
        logging.DEBUG
        if os.environ.get("SWIFTAGENT_LOG_LEVEL", "INFO").upper() == "DEBUG"
        else logging.INFO
    )
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _data_dir() -> Path:
    """Resolve the data directory for SwiftAgent storage."""
    base = os.environ.get("SWIFTAGENT_DATA_DIR")
    if base:
        return Path(base)
    return Path.home() / ".swiftagent"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # 1. Load .env file
    load_dotenv()
    _configure_logging()

    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Store on app state so routes can access it
    app.state.data_dir = data_dir

    # 2. Initialize database
    db_path = data_dir / "swiftagent.db"
    init_database(str(db_path))
    from swiftagent.adapter_sdk.loader import load_external_adapters
    from swiftagent.agents.registry import agent_registry

    adapter_errors = load_external_adapters(agent_registry, data_dir)
    for error in adapter_errors:
        logger.warning("external_adapter_load_failed error=%s", error)
    from swiftagent.storage import tasks as task_repo

    recovered = task_repo.recover_interrupted_tasks()
    if recovered:
        logger.warning("recovered_interrupted_tasks count=%s", recovered)

    # 3. Ensure configured workspace exists
    workspace = Path(settings_repo.get_workspace_dir()).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)

    yield

    # Cleanup active processes before releasing persistent storage.
    from swiftagent.engine.manager import task_manager

    await task_manager.shutdown()
    close_database()


app = FastAPI(
    title="SwiftAgent",
    version=VERSION,
    lifespan=lifespan,
)

# CORS — allow the Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(api_router, prefix="/api")
app.include_router(ws_router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("http_request_failed request_id=%s path=%s", request_id, request.url.path)
        raise
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "version": VERSION}


@app.get("/ready")
async def ready():
    """Readiness probe for local process supervisors."""
    workspace = Path(settings_repo.get_workspace_dir()).expanduser()
    return {
        "status": "ready",
        "version": VERSION,
        "workspace_exists": workspace.is_dir(),
    }


_project_root = Path(__file__).resolve().parents[2]
_client_dist = _project_root / "client" / "dist"


class SPAStaticFiles(StaticFiles):
    """Serve the SPA entry point for client-side routes in production."""

    async def get_response(self, path: str, scope):  # type: ignore[no-untyped-def]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # Let broken asset URLs remain a real 404. Client-side routes such as
            # /settings need the SPA shell so refreshing them stays functional.
            if exc.status_code == 404 and not Path(path).suffix:
                return await super().get_response("index.html", scope)
            raise


if _client_dist.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(_client_dist), html=True), name="client")


def _is_loopback_host(host: str) -> bool:
    return host.strip().lower() in {"127.0.0.1", "localhost", "::1"}


def main():
    """CLI entry point: start server + open browser."""
    # Load .env early for SWIFTAGENT_* vars
    load_dotenv()

    port = int(os.environ.get("SWIFTAGENT_PORT", "8000"))
    host = os.environ.get("SWIFTAGENT_HOST", "127.0.0.1")
    if not 1 <= port <= 65535:
        raise RuntimeError("SWIFTAGENT_PORT must be between 1 and 65535")
    if not _is_loopback_host(host) and os.environ.get("SWIFTAGENT_ALLOW_REMOTE") != "1":
        raise RuntimeError(
            "Refusing to expose SwiftAgent remotely without authentication. "
            "Keep SWIFTAGENT_HOST on loopback, or set SWIFTAGENT_ALLOW_REMOTE=1 only behind a trusted access layer."
        )

    # Open browser to the frontend
    if os.environ.get("SWIFTAGENT_NO_BROWSER") != "1":
        browser_port = port if _client_dist.is_dir() else 5173
        webbrowser.open(f"http://localhost:{browser_port}")

    uvicorn.run(
        "swiftagent.main:app",
        host=host,
        port=port,
        reload=os.environ.get("SWIFTAGENT_DEV") == "1",
    )


if __name__ == "__main__":
    main()
