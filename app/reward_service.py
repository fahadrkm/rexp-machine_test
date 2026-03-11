import json
import logging
import time
from datetime import timezone
from pathlib import Path
from typing import Optional

from app.cache import idem_key, persona_key, last_reward_key, cac_key
from app.models import Persona, RewardRequest, RewardResponse, RewardType
from app.policy_loader import PolicyConfig
from app.reward_engine import RewardEngine

logger = logging.getLogger(__name__)

PERSONA_TTL = 600
LAST_REWARD_TTL = 3_600
CAC_TTL = 90_000


class PersonaService:
    # FIX: was completely missing — persona was hardcoded "RETURNING" for everyone

    def __init__(self, cache, persona_path: str) -> None:
        self._cache = cache
        self._store: dict = self._load_store(persona_path)

    def _load_store(self, path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {}
        with open(p) as f:
            return json.load(f)

    def get_persona(self, user_id: str) -> Persona:
        key = persona_key(user_id)
        cached = self._cache.get(key)
        if cached is not None:
            try:
                return Persona(cached)
            except ValueError:
                pass
        raw = self._store.get(user_id) or self._store.get("default")
        try:
            persona = Persona(raw) if raw else Persona.RETURNING
        except ValueError:
            persona = Persona.RETURNING
        self._cache.set(key, persona.value, PERSONA_TTL)
        return persona


class RewardService:

    def __init__(self, cache, persona_service: PersonaService,
                 engine: RewardEngine, policy: PolicyConfig) -> None:
        self._cache = cache
        self._persona_service = persona_service
        self._engine = engine
        self._policy = policy

    def decide(self, req: RewardRequest) -> RewardResponse:
        # Step 1-2: Idempotency — return cached response immediately
        key = idem_key(req.txn_id, req.user_id, req.merchant_id)
        cached = self._cache.get(key)
        if cached is not None:
            return RewardResponse(**cached)

        # Step 3: Resolve real persona — FIX: was hardcoded "RETURNING"
        persona = self._persona_service.get_persona(req.user_id)

        # Step 4: Read daily CAC spend — FIX: was missing entirely
        txn_date = req.ts.astimezone(timezone.utc).date()
        cac_cache_key = cac_key(req.user_id, txn_date)
        raw_cac = self._cache.get(cac_cache_key)
        daily_cac_spent = float(raw_cac) if raw_cac is not None else 0.0

        # Step 5: Read last reward age for cooldown — FIX: was missing
        lr_key = last_reward_key(req.user_id)
        raw_ts = self._cache.get(lr_key)
        last_reward_age: Optional[float] = None
        if raw_ts is not None:
            last_reward_age = time.time() - float(raw_ts)

        # Step 6: Pure engine — no I/O inside
        decision = self._engine.calculate(
            txn_id=req.txn_id, user_id=req.user_id, merchant_id=req.merchant_id,
            amount=req.amount, txn_type=req.txn_type.value, persona=persona,
            daily_cac_spent=daily_cac_spent, last_reward_age_seconds=last_reward_age,
        )

        # Step 7: Update CAC — only for monetary rewards — FIX: was missing
        if decision.reward_type != RewardType.XP and decision.reward_value > 0:
            new_cac = daily_cac_spent + decision.reward_value
            self._cache.set(cac_cache_key, str(new_cac), CAC_TTL)

        # Step 8: Update last reward timestamp — FIX: was missing
        if decision.reward_value > 0 or decision.xp > 0:
            self._cache.set(lr_key, str(time.time()), LAST_REWARD_TTL)

        # Step 9-10: Build and cache response
        response = RewardResponse(
            decision_id=decision.decision_id,
            policy_version=decision.policy_version,
            reward_type=decision.reward_type,
            reward_value=decision.reward_value,
            xp=decision.xp,
            reason_codes=decision.reason_codes,
            meta=decision.meta,
        )
        self._cache.set(key, response.model_dump(), self._policy.idempotency_ttl_seconds)
        return response