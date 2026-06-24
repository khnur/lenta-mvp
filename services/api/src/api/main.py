"""lenta-api entrypoint: serving funnel + ingestion + metrics + control plane."""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lenta_core.config import settings
from lenta_core.db import get_session, init_db
from lenta_core.logging_conf import get_logger, setup_logging

from .routers import (
    control,
    dashboard,
    events,
    feed,
    health,
    metrics,
    models,
    pipeline,
)
from .state import AppState

log = get_logger("lenta.api")


def _reload_once(app: FastAPI) -> None:
    s = get_session()
    try:
        app.state.svc.reload(s)
    finally:
        s.close()


async def _reload_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(settings.model_reload_seconds)
        try:
            await asyncio.to_thread(_reload_once, app)
        except Exception as exc:  # noqa: BLE001
            log.warning("model reload loop error: %s", exc)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        log.warning("init_db failed (will retry via trainer): %s", exc)

    app.state.svc = AppState()
    s = get_session()
    try:
        app.state.svc.reload(s, force=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("initial model load skipped: %s", exc)
    finally:
        s.close()

    task = asyncio.create_task(_reload_loop(app))
    log.info("api ready (active model v%s)", app.state.svc.model.version)
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="lenta-api", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (health, feed, events, metrics, models, control, pipeline, dashboard):
    app.include_router(module.router)
