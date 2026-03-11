import os
os.environ["POLICY_CONFIG_PATH"] = "config/policy.yaml"
os.environ["PERSONA_CONFIG_PATH"] = "config/personas.json"
os.environ["REDIS_ENABLED"] = "false"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager

from app.cache import InMemoryCache
from app.main import create_app
from app.policy_loader import load_policy, PolicyConfig
from app.reward_engine import RewardEngine
from app.reward_service import RewardService, PersonaService


@pytest.fixture(scope="session")
def policy() -> PolicyConfig:
    return load_policy("config/policy.yaml")

@pytest.fixture
def cache() -> InMemoryCache:
    return InMemoryCache()

@pytest.fixture
def persona_service(cache) -> PersonaService:
    return PersonaService(cache=cache, persona_path="config/personas.json")

@pytest.fixture
def engine(policy) -> RewardEngine:
    return RewardEngine(policy=policy)

@pytest.fixture
def reward_service(cache, persona_service, engine, policy) -> RewardService:
    return RewardService(cache=cache, persona_service=persona_service,
                         engine=engine, policy=policy)

@pytest_asyncio.fixture
async def client():
    # FIX: LifespanManager triggers FastAPI startup so app.state is populated
    app = create_app()
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as ac:
            yield ac

def make_payload(**overrides) -> dict:
    base = {"txn_id": "txn_test_001", "user_id": "user_001",
            "merchant_id": "merchant_A", "amount": 500.0,
            "txn_type": "purchase", "ts": "2024-06-15T10:00:00Z"}
    base.update(overrides)
    return base