"""
test_idempotency.py

Tests that repeated identical requests always return the exact same response.
Tested at service level (no HTTP) and API level (full stack).
"""
import pytest
from datetime import datetime, timezone

from app.cache import cac_key
from app.models import RewardRequest, TxnType
from tests.conftest import make_payload


# ── Service-level ──────────────────────────────────────────────────────────────

class TestIdempotencyService:

    def _req(self, txn_id="idem_001", user_id="user_001") -> RewardRequest:
        return RewardRequest(
            txn_id=txn_id,
            user_id=user_id,
            merchant_id="merch_A",
            amount=500.0,
            txn_type=TxnType.PURCHASE,
            ts=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
        )

    def test_same_decision_id_on_repeat(self, reward_service):
        """Two identical calls must return the same decision_id."""
        req = self._req()
        r1 = reward_service.decide(req)
        r2 = reward_service.decide(req)
        assert r1.decision_id == r2.decision_id

    def test_same_reward_values_on_repeat(self, reward_service):
        """All reward fields must be identical on repeat."""
        req = self._req(txn_id="idem_002", user_id="user_002")
        r1 = reward_service.decide(req)
        r2 = reward_service.decide(req)
        assert r1.reward_type == r2.reward_type
        assert r1.reward_value == r2.reward_value
        assert r1.xp == r2.xp
        assert r1.reason_codes == r2.reason_codes

    def test_different_txn_id_new_decision(self, reward_service):
        """Different txn_id → different idempotency key → fresh decision."""
        base = dict(user_id="user_001", merchant_id="merch_A", amount=500.0,
                    txn_type=TxnType.PURCHASE,
                    ts=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc))
        r1 = reward_service.decide(RewardRequest(txn_id="txn_X", **base))
        r2 = reward_service.decide(RewardRequest(txn_id="txn_Y", **base))
        assert r1.decision_id != r2.decision_id

    def test_different_user_id_new_decision(self, reward_service):
        """Different user_id → different idempotency key → fresh decision."""
        base = dict(txn_id="txn_shared", merchant_id="merch_A", amount=500.0,
                    txn_type=TxnType.PURCHASE,
                    ts=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc))
        r1 = reward_service.decide(RewardRequest(user_id="user_001", **base))
        r2 = reward_service.decide(RewardRequest(user_id="user_002", **base))
        assert r1.decision_id != r2.decision_id

    def test_cac_not_double_counted_on_retry(self, reward_service, cache):
        """
        The second (idempotent) call must NOT update CAC again.
        If it did, the user's daily budget would be incorrectly depleted.
        """
        from datetime import date

        req = self._req(txn_id="idem_cac_001", user_id="user_003")
        reward_service.decide(req)
        cac_after_first = cache.get(cac_key("user_003", date(2024, 6, 15)))

        reward_service.decide(req)  # idempotent repeat
        cac_after_second = cache.get(cac_key("user_003", date(2024, 6, 15)))

        assert cac_after_first == cac_after_second


# ── API-level ──────────────────────────────────────────────────────────────────

class TestIdempotencyAPI:

    @pytest.mark.asyncio
    async def test_repeated_call_same_decision_id(self, client):
        payload = make_payload(txn_id="api_idem_001", user_id="user_001")
        r1 = await client.post("/reward/decide", json=payload)
        r2 = await client.post("/reward/decide", json=payload)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["decision_id"] == r2.json()["decision_id"]

    @pytest.mark.asyncio
    async def test_10_identical_calls_same_decision_id(self, client):
        """10 identical calls all return the same decision_id."""
        payload = make_payload(txn_id="api_idem_10x", user_id="user_002")
        first_id = None
        for _ in range(10):
            r = await client.post("/reward/decide", json=payload)
            assert r.status_code == 200
            did = r.json()["decision_id"]
            if first_id is None:
                first_id = did
            else:
                assert did == first_id

    @pytest.mark.asyncio
    async def test_validation_error_422(self, client):
        """Blank user_id must return 422, not 200 or 500."""
        r = await client.post("/reward/decide", json=make_payload(user_id="   "))
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_amount_422(self, client):
        r = await client.post("/reward/decide", json=make_payload(amount=-100))
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_response_has_required_fields(self, client):
        r = await client.post("/reward/decide", json=make_payload())
        assert r.status_code == 200
        data = r.json()
        for field in ["decision_id", "policy_version", "reward_type",
                      "reward_value", "xp", "reason_codes", "meta"]:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_reward_type_is_valid_enum(self, client):
        r = await client.post("/reward/decide", json=make_payload())
        assert r.json()["reward_type"] in ["XP", "CHECKOUT", "GOLD"]

    @pytest.mark.asyncio
    async def test_reward_value_non_negative(self, client):
        r = await client.post("/reward/decide", json=make_payload())
        data = r.json()
        assert data["reward_value"] >= 0
        assert data["xp"] >= 0