from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # FIX: default False — no Redis in test/dev environments
    redis_enabled: bool = False
    redis_host: str = "localhost"
    redis_port: int = 6379

    policy_config_path: str = "config/policy.yaml"
    persona_config_path: str = "config/personas.json"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()