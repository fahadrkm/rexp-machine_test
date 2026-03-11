# Reward Decision Service

A FastAPI-based microservice that evaluates a transaction and returns a deterministic reward decision.  
The service demonstrates backend fundamentals such as idempotency handling, configuration-driven logic, caching strategies, and unit testing.

---

## Overview

This service receives a transaction request and determines what reward should be granted.  
The decision is deterministic and driven by configurable business rules defined in a policy file.

The system is designed as a stateless service with a cache-first architecture to ensure low latency and prevent duplicate reward issuance.

---

## Key Features

- FastAPI microservice
- Deterministic reward decision engine
- Idempotent request handling
- Config-driven policy evaluation
- Persona-based reward multipliers
- Daily CAC cap enforcement
- Redis cache support with in-memory fallback
- Unit tests using pytest

---

## API Endpoint

### POST `/reward/decide`

Evaluates a transaction and returns a reward decision.

### Request Body

```json
{
  "txn_id": "txn_001",
  "user_id": "user_001",
  "merchant_id": "merchant_A",
  "amount": 200,
  "txn_type": "purchase",
  "ts": "2026-03-11T10:00:00Z"
}
```

### Response Example

```json
{
  "decision_id": "724ff8bb-0411-5a63-813b-f028322fbb48",
  "policy_version": "v1",
  "reward_type": "CHECKOUT",
  "reward_value": 4,
  "xp": 300,
  "reason_codes": [
    "GRANTED_CHECKOUT"
  ],
  "meta": {
    "persona": "NEW",
    "persona_multiplier": 1.5
  }
}
```

### Swagger Documentation

- [Swagger UI](http://localhost:8000/docs)

---

## Project Structure

```
.
├── app/
│   ├── main.py
│   ├── settings.py
│   ├── models.py
│   ├── cache.py
│   ├── policy_loader.py
│   ├── reward_engine.py
│   ├── reward_service.py
│   └── reward_router.py
│
├── config/
│   ├── policy.yaml
│   └── personas.json
│
├── tests/
│   ├── conftest.py
│   ├── test_engine.py
│   ├── test_idempotency.py
│   └── test_cac.py
│
├── .env
└── requirements.txt
```

---

## Configuration

### Policy Configuration

Reward rules are defined in `config/policy.yaml`

This configuration controls:

- XP calculation rules
- reward type weights
- persona multipliers
- daily CAC caps
- cooldown rules
- idempotency TTL

### Persona Configuration

Persona mapping is defined in `config/personas.json`

---

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <repository-url>
cd reward_service
```

### 2. Create Virtual Environment

**Windows**

```bash
python -m venv venv
venv\Scripts\activate
```

**Linux / Mac**

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```
REDIS_ENABLED=false
REDIS_HOST=localhost
REDIS_PORT=6379
POLICY_CONFIG_PATH=config/policy.yaml
PERSONA_CONFIG_PATH=config/personas.json
```

### 5. Start the API Server

```bash
uvicorn app.main:app --reload
```

Server will run at:

- [http://localhost:8000](http://localhost:8000)

Swagger UI:

- [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Redis (Optional)

The service supports Redis caching if Redis is available.

Run Redis locally using Docker:

```bash
docker run -p 6379:6379 redis
```

Then update `.env`:

```
REDIS_ENABLED=true
```

If Redis is not available, the service automatically falls back to an in-memory cache.

---

## Idempotency Handling

Idempotency is enforced using the key:

```
txn_id + user_id + merchant_id
```

Repeated requests with the same key return the cached response instead of recalculating the reward decision.

---

## XP Calculation

XP is calculated using the following formula:

```
xp = min(
    amount × xp_per_rupee × persona_multiplier × txn_multiplier,
    max_xp_per_txn
)
```

---

## Daily CAC Cap

Each persona has a daily CAC cap defined in the policy configuration.

If a monetary reward exceeds the cap, the service automatically returns XP instead of a monetary reward.

---

## Running Tests

Run unit tests using:

```bash
pytest -v
```

Tests cover:

- reward decision logic
- idempotency behavior
- CAC cap enforcement

---

## Assumptions

- Persona information is mocked using a local JSON file.
- Reward policies are configuration-driven and loaded from YAML.
- Redis is optional; in-memory cache is used if Redis is unavailable.
- The service acts as a stateless decision engine and does not persist data in a database.