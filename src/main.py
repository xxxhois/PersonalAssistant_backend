import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.exceptions.app_exception import AppException, ErrorCode
from src.routers.api_v1.chat import router as chat_router
from src.routers.api_v1.planning import router as planning_router
from src.schemas.common import ErrorResponse


def create_app() -> FastAPI:
    app = FastAPI(title="Personal Assistant Backend")

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        del request
        content = ErrorResponse(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            request_id=str(uuid.uuid4()),
            recoverable=exc.recoverable,
        ).model_dump(mode="json")

        status_code = 400
        if exc.code == ErrorCode.INTERNAL_ERROR:
            status_code = 500
        elif exc.code == ErrorCode.UNAUTHORIZED:
            status_code = 401
        elif exc.code == ErrorCode.FORBIDDEN:
            status_code = 403
        elif exc.code == ErrorCode.NOT_FOUND:
            status_code = 404

        return JSONResponse(status_code=status_code, content=content)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    app.include_router(chat_router)
    app.include_router(planning_router)
    return app


app = create_app()
