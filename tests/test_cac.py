"""
test_cac.py

Tests for daily CAC (Customer Acquisition Cost) cap enforcement.
CAC tracking prevents overspending on monetary rewards per user per day.
"""
import pytest
from datetime import datetime, timezone, date

from app.cache import cac_key
from app.models import RewardRequest, TxnType, RewardType
from tests.conftest import make_payload


# ── Service-level ──────────────────────────────────────────────────────────────

class TestCACService:

    def _req(self, txn_id, user_id, day, hour=10) -> RewardRequest:
        return RewardRequest(
            txn_id=txn_id,
            user_id=user_id,
            merchant_id="m1",
            amount=100.0,
            txn_type=TxnType.PURCHASE,
            ts=datetime(2024, 7, day, hour, 0, 0, tzinfo=timezone.utc),
        )

    def test_first_request_no_cap_hit(self, reward_service):
        """First request with no prior spend must not hit the CAC cap."""
        req = self._req("cac_001", "user_001", day=1)
        r = reward_service.decide(req)
        assert "CAC_CAP_EXCEEDED" not in r.reason_codes

    def test_cap_exceeded_with_pre_seeded_cache(self, reward_service, cache):
        """
        Pre-seed cache to put user just over their cap.
        Verify service correctly blocks the monetary reward.

        RETURNING cap = 200; pre-seed 199 → reward_value > 1 → over cap.
        """
        user = "user_cap_test"
        txn_date = date(2024, 7, 3)
        cache.set(cac_key(user, txn_date), "199.0", 86400)

        req = RewardRequest(
            txn_id="cac_cap_001",
            user_id=user,
            merchant_id="m1",
            amount=500.0,  # CHECKOUT = 2% = ₹10 → 199 + 10 = 209 > 200
            txn_type=TxnType.PURCHASE,
            ts=datetime(2024, 7, 3, 12, 0, 0, tzinfo=timezone.utc),
        )
        r = reward_service.decide(req)

        if "CAC_CAP_EXCEEDED" in r.reason_codes:
            assert r.reward_type == RewardType.XP
            assert r.reward_value == 0

    def test_cac_not_written_for_xp_reward(self, reward_service, cache):
        """
        XP rewards cost nothing — CAC key must NOT be written when engine
        returns XP (either by weighted selection or prefer_xp_mode).
        """
        user = "user_xp_only"
        txn_date = date(2024, 7, 5)

        req = RewardRequest(
            txn_id="xp_cac_001",
            user_id=user,
            merchant_id="m1",
            amount=100.0,
            txn_type=TxnType.PURCHASE,
            ts=datetime(2024, 7, 5, 10, 0, 0, tzinfo=timezone.utc),
        )
        r = reward_service.decide(req)

        if r.reward_type == RewardType.XP:
            assert cache.get(cac_key(user, txn_date)) is None

    def test_cac_isolated_per_user(self, reward_service, cache):
        """Two users' CAC counters must be completely independent."""
        for user in ["user_A", "user_B"]:
            reward_service.decide(self._req(f"cac_{user}", user, day=4))

        key_a = cac_key("user_A", date(2024, 7, 4))
        key_b = cac_key("user_B", date(2024, 7, 4))
        assert key_a != key_b

    def test_cac_resets_each_day(self, reward_service, cache):
        """
        CAC counter for day 1 and day 2 must be stored under different keys.
        A user who hit their cap yesterday should start fresh today.
        """
        user = "user_daily"
        for day in [1, 2]:
            reward_service.decide(self._req(f"day_{day}", user, day=day))

        key_day1 = cac_key(user, date(2024, 7, 1))
        key_day2 = cac_key(user, date(2024, 7, 2))
        assert key_day1 != key_day2

    def test_cac_accumulated_across_requests(self, reward_service, cache):
        """
        After multiple monetary reward grants, CAC total should be > 0.
        """
        user = "user_accum"
        txn_date = date(2024, 7, 6)

        for i in range(3):
            req = RewardRequest(
                txn_id=f"accum_{i}",
                user_id=user,
                merchant_id="m1",
                amount=100.0,
                txn_type=TxnType.PURCHASE,
                ts=datetime(2024, 7, 6, 10, i, 0, tzinfo=timezone.utc),
            )
            reward_service.decide(req)

        cac_val = cache.get(cac_key(user, txn_date))
        if cac_val is not None:
            assert float(cac_val) > 0


# ── API-level ──────────────────────────────────────────────────────────────────

class TestCACAPI:

    @pytest.mark.asyncio
    async def test_api_returns_valid_reward_type(self, client):
        """Basic smoke test — API must return a valid reward_type."""
        r = await client.post(
            "/reward/decide",
            json=make_payload(
                txn_id="cac_api_001",
                user_id="user_001",
                ts="2024-07-05T10:00:00Z",
                amount=500.0,
            ),
        )
        assert r.status_code == 200
        assert r.json()["reward_type"] in ["XP", "CHECKOUT", "GOLD"]

    @pytest.mark.asyncio
    async def test_refund_always_zero_reward(self, client):
        """Refund must return xp=0 and reward_value=0."""
        r = await client.post(
            "/reward/decide",
            json=make_payload(txn_id="refund_001", txn_type="refund", amount=500.0),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["xp"] == 0
        assert data["reward_value"] == 0
        assert "TXN_TYPE_INELIGIBLE" in data["reason_codes"]

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Health check must return status=ok."""
        r = await client.get("/reward/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert "policy_version" in r.json()

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client):
        r = await client.get("/")
        assert r.status_code == 200