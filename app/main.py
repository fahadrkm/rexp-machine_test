import logging
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.settings import get_settings
from app.policy_loader import load_policy
from app.cache import get_cache
from app.reward_engine import RewardEngine
from app.reward_service import RewardService, PersonaService
from app.models import ErrorResponse
from app.reward_router import router


async def _on_validation_error(request, exc: RequestValidationError) -> JSONResponse:
    # FIX: Pydantic v2 ctx dicts may contain non-serializable objects
    #      sanitize each error to plain string-safe dict
    safe_errors = []
    for e in exc.errors():
        safe_errors.append({
            "type": e.get("type"),
            "loc": list(e.get("loc", [])),
            "msg": e.get("msg"),
            "input": str(e.get("input", "")),
        })
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="VALIDATION_ERROR",
            message="Request validation failed",
            detail=safe_errors,
        ).model_dump(),
    )


async def _on_server_error(request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).exception("Unhandled error: %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error="INTERNAL_SERVER_ERROR",
                              message="An unexpected error occurred").model_dump(),
    )


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    policy = load_policy(settings.policy_config_path)
    cache = get_cache(settings)
    persona_service = PersonaService(cache=cache, persona_path=settings.persona_config_path)
    engine = RewardEngine(policy=policy)
    service = RewardService(cache=cache, persona_service=persona_service,
                            engine=engine, policy=policy)

    app = FastAPI(title="Reward Decision Service", version="1.0.0")
    app.add_exception_handler(RequestValidationError, _on_validation_error)
    app.add_exception_handler(Exception, _on_server_error)
    app.state.reward_service = service
    app.include_router(router)

    @app.get("/", tags=["Health"])
    def root():
        return {"service": "reward-decision-service", "status": "running"}

    return app


app = create_app()