import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.sessions import router as sessions_router
from app.api.stores import router as stores_router
from app.api.trips import router as trips_router
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.errors import AppError
from app.providers.frankfurter import FrankfurterExchangeRateProvider
from app.providers.openclip_embedding import OpenCLIPImageEmbedder
from app.services.exchange_rates import ExchangeRateService, ExchangeRateUnavailableError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    if application.state.exchange_rate_startup_enabled:
        _refresh_exchange_rates_on_startup(settings)
    if settings.recognition_provider == "openclip":
        await OpenCLIPImageEmbedder(
            model_name=settings.openclip_model,
            pretrained=settings.openclip_pretrained,
            device=settings.openclip_device,
            expected_dimension=settings.openclip_embedding_dimension,
        ).warmup()
    yield


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def request_validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_REQUEST",
                "message": "The request payload is invalid.",
            }
        },
    )


def create_app(*, enable_exchange_rate_startup: bool = True) -> FastAPI:
    settings = get_settings()
    logging.getLogger("app").setLevel(settings.log_level)
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Smart-glasses shopping support backend API",
        lifespan=lifespan,
    )
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
    application.include_router(health_router)
    application.include_router(stores_router)
    application.include_router(sessions_router)
    application.include_router(me_router)
    application.include_router(trips_router)
    application.state.exchange_rate_startup_enabled = enable_exchange_rate_startup
    return application


def _refresh_exchange_rates_on_startup(settings: Settings) -> None:
    provider = FrankfurterExchangeRateProvider(
        base_url=settings.frankfurter_base_url,
        timeout_seconds=settings.frankfurter_timeout_seconds,
    )
    try:
        with SessionLocal() as db:
            usd_rate, cny_rate = ExchangeRateService(db, provider).get_rates()
        logger.info(
            "exchange_rate_startup_check_completed usd_rate_date=%s cny_rate_date=%s",
            usd_rate.rate_date,
            cny_rate.rate_date,
        )
    except (ExchangeRateUnavailableError, SQLAlchemyError):
        logger.warning(
            "exchange_rate_startup_check_failed_server_will_continue",
            exc_info=True,
        )


app = create_app()
