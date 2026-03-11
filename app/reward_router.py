import logging
from fastapi import APIRouter, Depends, Request, status
from app.models import RewardRequest, RewardResponse, ErrorResponse
from app.reward_service import RewardService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reward", tags=["Reward"])


def get_service(request: Request) -> RewardService:
    return request.app.state.reward_service


@router.post("/decide", response_model=RewardResponse, status_code=status.HTTP_200_OK,
             responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def decide(req: RewardRequest, service: RewardService = Depends(get_service)) -> RewardResponse:
    logger.info("POST /reward/decide txn=%s user=%s", req.txn_id, req.user_id)
    return service.decide(req)


@router.get("/health", status_code=status.HTTP_200_OK)
def health(service: RewardService = Depends(get_service)) -> dict:
    return {
        "status": "ok",
        "policy_version": service._policy.policy_version,
        "cache_type": type(service._cache).__name__,
    }