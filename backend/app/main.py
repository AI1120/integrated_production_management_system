"""IPMS application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routers import (
    auth,
    calendar,
    dashboard,
    equipment,
    inventory,
    master,
    optimization,
    production,
    quality,
    workflow,
)
from .config import settings
from .database import Base, engine
from .models import *  # noqa: F401,F403 - registers every table on Base.metadata
from .services.inventory_service import StockError
from .services.production_service import ProductionError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
logger = logging.getLogger("ipms")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # create_all is enough for the sample plant; the multi-site rollout should
    # switch to Alembic migrations before the first production deployment.
    Base.metadata.create_all(bind=engine)
    logger.info("IPMS ready - plant %s (%s)", settings.plant_code, settings.plant_name)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Integrated Production Management System - master data, production orders, "
        "inventory, quality and equipment/OEE for a discrete assembly plant."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StockError)
async def _stock_error(_request: Request, exc: StockError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


@app.exception_handler(ProductionError)
async def _production_error(_request: Request, exc: ProductionError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "version": settings.version,
        "plant_code": settings.plant_code,
        "plant_name": settings.plant_name,
    }


for router in (
    auth, master, production, inventory, quality, equipment, dashboard, workflow, optimization,
    calendar,
):
    app.include_router(router.router, prefix="/api")
