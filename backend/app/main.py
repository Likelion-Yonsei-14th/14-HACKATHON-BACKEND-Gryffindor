from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.sessions import router as sessions_router
from app.core.config import get_settings
from app.errors import AppError


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Smart-glasses shopping support backend API",
    )
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(health_router)
    application.include_router(sessions_router)
    return application


app = create_app()
