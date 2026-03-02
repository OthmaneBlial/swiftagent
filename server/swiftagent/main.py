"""
SwiftAgent — FastAPI application entry point.

Replaces the Electron main process (apps/desktop/src/main/index.ts).
Serves REST + WebSocket on a single port.
"""

from __future__ import annotations

import os
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from swiftagent.api.routes import router as api_router
from swiftagent.api.websocket import router as ws_router
from swiftagent.config import load_dotenv, auto_import_env_keys
from swiftagent.storage.database import init_database, close_database
from swiftagent.storage.secure import SecureStorage


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

    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Store on app state so routes can access it
    app.state.data_dir = data_dir

    # 2. Initialize database
    db_path = data_dir / "swiftagent.db"
    init_database(str(db_path))

    # 3. Auto-import API keys from env into SecureStorage
    secure = SecureStorage(storage_path=str(data_dir))
    imported = auto_import_env_keys(secure)
    if imported:
        print(f"[startup] Auto-imported API keys from env: {', '.join(imported)}")

    yield

    # Cleanup
    close_database()


app = FastAPI(
    title="SwiftAgent",
    version="0.1.0",
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


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


def main():
    """CLI entry point: start server + open browser."""
    # Load .env early for SWIFTAGENT_* vars
    load_dotenv()

    port = int(os.environ.get("SWIFTAGENT_PORT", "8000"))
    host = os.environ.get("SWIFTAGENT_HOST", "127.0.0.1")

    # Open browser to the frontend
    if os.environ.get("SWIFTAGENT_NO_BROWSER") != "1":
        webbrowser.open(f"http://localhost:5173")

    uvicorn.run(
        "swiftagent.main:app",
        host=host,
        port=port,
        reload=os.environ.get("SWIFTAGENT_DEV") == "1",
    )


if __name__ == "__main__":
    main()
