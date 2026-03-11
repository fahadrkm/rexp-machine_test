import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models import Persona, RewardType
from app.policy_loader import PolicyConfig

_NS = uuid.NAMESPACE_URL


@dataclass
class RewardDecision:
    # FIX: dataclass instead of raw tuple — adding fields never breaks callers
    decision_id: str
    policy_version: str
    reward_type: RewardType
    reward_value: int
    xp: int
    reason_codes: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


class RewardEngine:
    def __init__(self, policy: PolicyConfig) -> None:
        self._policy = policy

    def calculate(
        self,
        txn_id: str,
        user_id: str,
        merchant_id: str,
        amount: float,
        txn_type: str,
        persona: Persona,
        daily_cac_spent: float,           # FIX: was missing
        last_reward_age_seconds: Optional[float],  # FIX: was missing
    ) -> RewardDecision:
        p = self._policy
        reason_codes: List[str] = []
        meta: Dict[str, Any] = {}

        # Gate 1: Deterministic decision_id
        # FIX: was hashing only txn_id — now uses full idem_str
        idem_str = f"{txn_id}:{user_id}:{merchant_id}"
        decision_id = str(uuid.uuid5(_NS, idem_str))
        meta["idem_str"] = idem_str

        # Gate 2: Transaction type eligibility
        txn_multiplier = p.txn_type_multipliers.get(txn_type.lower(), 0.0)
        meta["txn_multiplier"] = txn_multiplier
        if txn_multiplier == 0.0:
            reason_codes.append("TXN_TYPE_INELIGIBLE")
            return RewardDecision(decision_id, p.policy_version, RewardType.XP, 0, 0,
                                  reason_codes, meta)

        # Gate 3: Minimum amount — FIX: was missing entirely
        if amount < p.min_amount_for_reward:
            reason_codes.append("AMOUNT_BELOW_MINIMUM")
            return RewardDecision(decision_id, p.policy_version, RewardType.XP, 0, 0,
                                  reason_codes, meta)

        # Gate 4: Cooldown — FIX: was missing entirely
        if (p.feature_flags.cooldown_enabled
                and last_reward_age_seconds is not None
                and last_reward_age_seconds < p.feature_flags.cooldown_seconds):
            remaining = round(p.feature_flags.cooldown_seconds - last_reward_age_seconds, 2)
            reason_codes.append("COOLDOWN_ACTIVE")
            meta["cooldown_remaining_seconds"] = remaining
            return RewardDecision(decision_id, p.policy_version, RewardType.XP, 0, 0,
                                  reason_codes, meta)

        # Gate 5: XP calculation
        # Formula: amount × xp_per_rupee × persona_multiplier × txn_multiplier (capped)
        persona_mult = p.persona_multipliers.get(persona.value, 1.0)
        raw_xp = amount * p.xp_per_rupee * persona_mult * txn_multiplier
        xp = int(min(raw_xp, p.max_xp_per_txn))
        meta["persona"] = persona.value
        meta["persona_multiplier"] = persona_mult

        # Gate 6: Reward type selection — FIX: now checks prefer_xp_mode
        if p.feature_flags.prefer_xp_mode:
            reward_type = RewardType.XP
            reason_codes.append("PREFER_XP_MODE")
        else:
            reward_type = self._pick_reward_type(idem_str)

        # Gate 7: Monetary value
        reward_value = self._calc_value(reward_type, amount, txn_multiplier)

        # Gate 8: CAC cap enforcement — FIX: was missing entirely
        daily_cap = p.daily_cac_cap.get(persona.value, 0.0)
        meta["daily_cap"] = daily_cap
        meta["daily_cac_spent"] = daily_cac_spent
        if reward_type != RewardType.XP and (daily_cac_spent + reward_value) > daily_cap:
            reason_codes.append("CAC_CAP_EXCEEDED")
            reward_type = RewardType.XP
            reward_value = 0

        reason_codes.append(f"GRANTED_{reward_type.value}")
        return RewardDecision(decision_id, p.policy_version, reward_type,
                              reward_value, xp, reason_codes, meta)

    def _pick_reward_type(self, idem_str: str) -> RewardType:
        # FIX: now receives full idem_str not just txn_id
        weights = self._policy.reward_type_weights
        total = sum(weights.values())
        normalized = {k: v / total for k, v in weights.items()}
        h = int(uuid.uuid5(_NS, idem_str)) % 10_000 / 10_000.0
        cumulative = 0.0
        for type_name, weight in normalized.items():
            cumulative += weight
            if h < cumulative:
                try:
                    return RewardType(type_name)
                except ValueError:
                    pass
        return RewardType.XP

    def _calc_value(self, reward_type: RewardType, amount: float, txn_mult: float) -> int:
        if reward_type == RewardType.CHECKOUT:
            return int(amount * 0.02 * txn_mult)
        if reward_type == RewardType.GOLD:
            return int(amount * 0.01 * txn_mult)
        return 0