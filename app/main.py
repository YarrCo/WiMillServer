from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.activity import router as activity_router
from app.allowed_devices import router as allowed_devices_router
from app.database import init_db
from app.devices import router as devices_router
from app.files import router as files_router
from app.jobs import router as jobs_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="WiMill Server MVP", lifespan=lifespan)

app.include_router(devices_router)
app.include_router(jobs_router)
app.include_router(activity_router)
app.include_router(allowed_devices_router)
app.include_router(files_router)
