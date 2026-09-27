"""Application lifecycle tasks for sandbox cleanup."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

from fastapi import FastAPI

from src.api.dependencies import get_sandbox_manager
from src.sandbox.controller import SandboxError


logger = logging.getLogger(__name__)
_CLEANUP_INTERVAL_SECONDS = 60.0


async def _cleanup_loop(stop_event: asyncio.Event) -> None:
    manager = get_sandbox_manager()
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_CLEANUP_INTERVAL_SECONDS)
        except TimeoutError:
            try:
                expired = await asyncio.to_thread(manager.cleanup_expired)
                if expired:
                    logger.info("Destroyed %s expired sandbox session(s)", len(expired))
            except (SandboxError, OSError):
                logger.exception("Sandbox expiration cleanup failed")


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start idle cleanup and destroy active sandboxes during shutdown."""
    stop_event = asyncio.Event()
    cleanup_task = asyncio.create_task(_cleanup_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        try:
            await asyncio.to_thread(get_sandbox_manager().shutdown)
        except SandboxError:
            logger.exception("One or more sandbox sessions failed to shut down")
