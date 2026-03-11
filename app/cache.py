import json
import time
from datetime import date
from typing import Any, Optional
import redis as redis_lib


class InMemoryCache:
    def __init__(self):
        self._store: dict = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:          # Asfter FIX: was `if not entry` — wrong for falsy values
            return None
        value_json, expiry = entry
        if time.monotonic() > expiry:
            del self._store[key]
            return None
        return json.loads(value_json)

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._store[key] = (json.dumps(value), time.monotonic() + ttl)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None


class RedisCache:
    def __init__(self, host: str, port: int):
        self.client = redis_lib.Redis(
            host=host, port=port,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    def get(self, key: str) -> Optional[Any]:
        val = self.client.get(key)
        return json.loads(val) if val is not None else None

    def set(self, key: str, value: Any, ttl: int) -> None:
        self.client.setex(key, ttl, json.dumps(value))

    def exists(self, key: str) -> bool:
        return bool(self.client.exists(key))


def get_cache(settings):
    if settings.redis_enabled:
        try:
            r = RedisCache(settings.redis_host, settings.redis_port)
            r.client.ping()
            return r
        except Exception:
            pass
    return InMemoryCache()


# Key builders — single place to change key format
def idem_key(txn_id: str, user_id: str, merchant_id: str) -> str:
    return f"idem:{txn_id}:{user_id}:{merchant_id}"

def persona_key(user_id: str) -> str:
    return f"persona:{user_id}"

def last_reward_key(user_id: str) -> str:
    return f"last_reward:{user_id}"

def cac_key(user_id: str, day: date) -> str:
    return f"cac:{user_id}:{day.isoformat()}"