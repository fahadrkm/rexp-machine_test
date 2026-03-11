from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class RewardType(str, Enum):
    XP = "XP"
    CHECKOUT = "CHECKOUT"
    GOLD = "GOLD"


class Persona(str, Enum):
    NEW = "NEW"
    RETURNING = "RETURNING"
    POWER = "POWER"


class TxnType(str, Enum):
    PURCHASE = "purchase"
    REFUND = "refund"
    TRANSFER = "transfer"
    TOPUP = "topup"


class RewardRequest(BaseModel):
    # FIX: min_length=1 on ALL three ID fields
    txn_id: str = Field(..., min_length=1, max_length=128)
    user_id: str = Field(..., min_length=1, max_length=128)
    merchant_id: str = Field(..., min_length=1, max_length=128)
    amount: float = Field(..., gt=0)
    txn_type: TxnType
    ts: datetime

    # FIX: reject whitespace-only strings that pass min_length=1
    @field_validator("txn_id", "user_id", "merchant_id", mode="before")
    @classmethod
    def reject_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be blank or whitespace only")
        return v.strip()

    model_config = {"str_strip_whitespace": True}


class RewardResponse(BaseModel):
    decision_id: str
    policy_version: str
    reward_type: RewardType
    reward_value: int = Field(..., ge=0)
    xp: int = Field(..., ge=0)
    # FIX: default_factory prevents shared mutable defaults
    reason_codes: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    message: str
    detail: Optional[Any] = None