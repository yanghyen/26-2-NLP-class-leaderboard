from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, auth, avatars, health, submissions, tasks
from app.core.config import get_settings
from app.db.base import create_all
from app.db.session import SessionLocal
from app.services.avatars import ensure_default_avatars


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    db = SessionLocal()
    try:
        ensure_default_avatars(db)
    finally:
        db.close()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(avatars.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(tasks.router)
app.include_router(submissions.router)



from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse


@app.exception_handler(RequestValidationError)
async def safe_request_validation(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/tasks") and any(
        "evaluator_key" in error["loc"] for error in exc.errors()
    ):
        from app.evaluators.errors import SAFE_EVALUATOR_MESSAGES
        code = "EVALUATOR_CONFIG_INVALID"
        return JSONResponse(status_code=400, content={"detail": {
            "code": code, "message": SAFE_EVALUATOR_MESSAGES[code],
        }})
    if request.url.path.startswith("/submissions"):
        return JSONResponse(status_code=422, content={"detail": "제출 입력 형식을 확인하세요."})
    return await request_validation_exception_handler(request, exc)
