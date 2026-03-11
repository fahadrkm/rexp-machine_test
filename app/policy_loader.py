import yaml
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class FeatureFlags:
    # FIX: was completely missing — now loaded from policy.yaml
    prefer_xp_mode: bool
    cooldown_enabled: bool
    cooldown_seconds: int


@dataclass(frozen=True)
class PolicyConfig:
    policy_version: str
    xp_per_rupee: float
    max_xp_per_txn: int
    reward_type_weights: dict
    persona_multipliers: dict
    daily_cac_cap: dict
    idempotency_ttl_seconds: int
    feature_flags: FeatureFlags  # FIX: added
    txn_type_multipliers: dict
    min_amount_for_reward: float


@lru_cache()
def load_policy(path: str) -> PolicyConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Policy config not found: {path}")

    with open(p) as f:
        raw = yaml.safe_load(f)

    return PolicyConfig(
        policy_version=str(raw["policy_version"]),
        xp_per_rupee=float(raw["xp"]["xp_per_rupee"]),
        max_xp_per_txn=int(raw["xp"]["max_xp_per_txn"]),
        reward_type_weights=raw["reward_type_weights"],
        persona_multipliers=raw["persona_multipliers"],
        daily_cac_cap=raw["daily_cac_cap"],
        idempotency_ttl_seconds=int(raw["idempotency_ttl_seconds"]),
        feature_flags=FeatureFlags(           # FIX: now reads from YAML
            prefer_xp_mode=bool(raw["feature_flags"]["prefer_xp_mode"]),
            cooldown_enabled=bool(raw["feature_flags"]["cooldown_enabled"]),
            cooldown_seconds=int(raw["feature_flags"]["cooldown_seconds"]),
        ),
        txn_type_multipliers=raw["txn_type_multipliers"],
        min_amount_for_reward=float(raw["min_amount_for_reward"]),
    )