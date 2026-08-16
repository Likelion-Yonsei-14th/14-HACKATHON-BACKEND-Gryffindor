import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.sessions import router as sessions_router
from app.core.config import get_settings
from app.errors import AppError
from app.providers.openclip_embedding import OpenCLIPImageEmbedder


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
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


def create_app() -> FastAPI:
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
    application.include_router(sessions_router)
    return application


app = create_app()
