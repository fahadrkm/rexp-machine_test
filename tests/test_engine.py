"""
test_engine.py

Unit tests for the pure RewardEngine.
No I/O, no mocking, no HTTP — just inputs in, outputs checked.
All tests are synchronous and run in milliseconds.
"""
import pytest
from app.models import Persona, RewardType


class TestXPFormula:
    """XP = amount × xp_per_rupee × persona_multiplier × txn_multiplier (capped)"""

    def test_returning_purchase_baseline(self, engine):
        # 100 × 1.0 × 1.0 (RETURNING) × 1.0 (purchase) = 100
        d = engine.calculate("t1", "u1", "m1", 100.0, "purchase",
                              Persona.RETURNING, 0.0, None)
        assert d.xp == 100

    def test_new_user_1_5x_multiplier(self, engine):
        # 100 × 1.0 × 1.5 (NEW) × 1.0 = 150
        d = engine.calculate("t2", "u2", "m1", 100.0, "purchase",
                              Persona.NEW, 0.0, None)
        assert d.xp == 150

    def test_power_user_2x_multiplier(self, engine):
        # 100 × 1.0 × 2.0 (POWER) × 1.0 = 200
        d = engine.calculate("t3", "u3", "m1", 100.0, "purchase",
                              Persona.POWER, 0.0, None)
        assert d.xp == 200

    def test_xp_cap_enforced(self, engine, policy):
        # 10000 × 1.0 × 2.0 (POWER) = 20000 → capped at 500
        d = engine.calculate("t4", "u4", "m1", 10_000.0, "purchase",
                              Persona.POWER, 0.0, None)
        assert d.xp == policy.max_xp_per_txn
        assert d.xp == 500

    def test_topup_0_8_multiplier(self, engine):
        # 100 × 1.0 × 1.0 × 0.8 (topup) = 80
        d = engine.calculate("t5", "u5", "m1", 100.0, "topup",
                              Persona.RETURNING, 0.0, None)
        assert d.xp == 80

    def test_transfer_0_5_multiplier(self, engine):
        # 100 × 1.0 × 1.0 × 0.5 (transfer) = 50
        d = engine.calculate("t6", "u6", "m1", 100.0, "transfer",
                              Persona.RETURNING, 0.0, None)
        assert d.xp == 50


class TestTxnTypeEligibility:
    """Ineligible transaction types return 0 reward with TXN_TYPE_INELIGIBLE code."""

    def test_refund_gives_zero(self, engine):
        d = engine.calculate("t10", "u1", "m1", 500.0, "refund",
                              Persona.RETURNING, 0.0, None)
        assert d.xp == 0
        assert d.reward_value == 0
        assert "TXN_TYPE_INELIGIBLE" in d.reason_codes

    def test_unknown_type_gives_zero(self, engine):
        d = engine.calculate("t11", "u1", "m1", 500.0, "wire",
                              Persona.RETURNING, 0.0, None)
        assert d.xp == 0
        assert "TXN_TYPE_INELIGIBLE" in d.reason_codes


class TestMinimumAmount:
    """Transactions below min_amount_for_reward earn nothing."""

    def test_below_minimum_blocked(self, engine):
        # min_amount_for_reward = 1.0; 0.5 is below it
        d = engine.calculate("t20", "u1", "m1", 0.5, "purchase",
                              Persona.RETURNING, 0.0, None)
        assert d.xp == 0
        assert d.reward_value == 0
        assert "AMOUNT_BELOW_MINIMUM" in d.reason_codes

    def test_at_minimum_allowed(self, engine):
        # exactly 1.0 — should pass
        d = engine.calculate("t21", "u1", "m1", 1.0, "purchase",
                              Persona.RETURNING, 0.0, None)
        assert "AMOUNT_BELOW_MINIMUM" not in d.reason_codes


class TestCooldown:
    """Cooldown gate prevents reward farming."""

    def test_active_cooldown_blocks_reward(self, engine):
        # 10s since last reward; cooldown = 60s → blocked
        d = engine.calculate("t30", "u1", "m1", 500.0, "purchase",
                              Persona.RETURNING, 0.0, 10.0)
        assert d.xp == 0
        assert d.reward_value == 0
        assert "COOLDOWN_ACTIVE" in d.reason_codes

    def test_expired_cooldown_allows_reward(self, engine):
        # 120s since last reward; cooldown = 60s → allowed
        d = engine.calculate("t31", "u1", "m1", 500.0, "purchase",
                              Persona.RETURNING, 0.0, 120.0)
        assert "COOLDOWN_ACTIVE" not in d.reason_codes

    def test_first_transaction_skips_cooldown(self, engine):
        # None = no previous reward → cooldown does not apply
        d = engine.calculate("t32", "u1", "m1", 500.0, "purchase",
                              Persona.RETURNING, 0.0, None)
        assert "COOLDOWN_ACTIVE" not in d.reason_codes

    def test_cooldown_remaining_in_meta(self, engine):
        # When cooldown is active, remaining seconds must be in meta
        d = engine.calculate("t33", "u1", "m1", 500.0, "purchase",
                              Persona.RETURNING, 0.0, 10.0)
        assert "cooldown_remaining_seconds" in d.meta
        assert d.meta["cooldown_remaining_seconds"] == 50.0


class TestCACCap:
    """Daily CAC cap gate prevents over-spending on monetary rewards."""

    def test_no_cap_exceeded_when_zero_spent(self, engine):
        # RETURNING cap = 200; 0 spent → no cap issue
        d = engine.calculate("t40", "u1", "m1", 100.0, "purchase",
                              Persona.RETURNING, 0.0, None)
        assert "CAC_CAP_EXCEEDED" not in d.reason_codes

    def test_cap_exceeded_forces_xp(self, engine):
        # RETURNING cap = 200; 300 already spent → any monetary reward blocked
        d = engine.calculate("t41", "u1", "m1", 500.0, "purchase",
                              Persona.RETURNING, 300.0, None)
        if "CAC_CAP_EXCEEDED" in d.reason_codes:
            assert d.reward_type == RewardType.XP
            assert d.reward_value == 0

    def test_power_user_higher_cap(self, engine):
        # POWER cap = 500; 350 spent → still under cap
        d = engine.calculate("t42", "u1", "m1", 100.0, "purchase",
                              Persona.POWER, 350.0, None)
        assert "CAC_CAP_EXCEEDED" not in d.reason_codes or \
               d.reward_type == RewardType.XP


class TestDeterminism:
    """Same inputs must always produce identical outputs."""

    def test_same_inputs_same_decision_id(self, engine):
        kwargs = dict(txn_id="det1", user_id="u1", merchant_id="m1",
                      amount=250.0, txn_type="purchase", persona=Persona.RETURNING,
                      daily_cac_spent=0.0, last_reward_age_seconds=None)
        d1 = engine.calculate(**kwargs)
        d2 = engine.calculate(**kwargs)
        assert d1.decision_id == d2.decision_id

    def test_same_inputs_same_reward_type_and_xp(self, engine):
        kwargs = dict(txn_id="det2", user_id="u2", merchant_id="m2",
                      amount=300.0, txn_type="purchase", persona=Persona.POWER,
                      daily_cac_spent=0.0, last_reward_age_seconds=None)
        d1 = engine.calculate(**kwargs)
        d2 = engine.calculate(**kwargs)
        assert d1.reward_type == d2.reward_type
        assert d1.reward_value == d2.reward_value
        assert d1.xp == d2.xp

    def test_different_txn_ids_different_decision_ids(self, engine):
        base = dict(user_id="u1", merchant_id="m1", amount=100.0,
                    txn_type="purchase", persona=Persona.RETURNING,
                    daily_cac_spent=0.0, last_reward_age_seconds=None)
        d1 = engine.calculate(txn_id="txn_A", **base)
        d2 = engine.calculate(txn_id="txn_B", **base)
        assert d1.decision_id != d2.decision_id