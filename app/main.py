import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import auth, contests, leaderboard, problems, submissions
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_var

configure_logging(get_settings().log_level)
logger = logging.getLogger(__name__)
app = FastAPI(title="Shodh AI Coding Contest Backend", version="1.0.0")


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error", extra={"request_id": request_id})
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(contests.router)
app.include_router(problems.router)
app.include_router(submissions.router)
app.include_router(leaderboard.router)
