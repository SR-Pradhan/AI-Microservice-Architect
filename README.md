# AI Microservice Architect

Turns a plain-English system description into a complete, reviewable microservice architecture —
service boundaries, HLD, LLD, database schemas, Kafka event contracts and Docker/Kubernetes
manifests — then exports the whole thing as a runnable repo scaffold.

It is a **staged, human-checkpointed pipeline**, not a one-shot generator. Each stage produces an
artifact you review, edit and approve before the next one runs. That is a deliberate design choice:
service boundary decisions are architectural judgement calls, and a bad split at stage 1 would
poison everything downstream.

```
Your description
  → 1. Service Boundaries   which services exist, and why
  → 2. High-Level Design    service map, sync vs async, datastores
  → 3. Low-Level Design     entities, API contracts, internal logic
  → 4. DB Schemas           tables, columns, indexes, keys
  → 5. Kafka Events         topics, partitions, consumer groups, DLQ
  → 6. Docker / Kubernetes  images, ports, probes, resources
  → Downloadable scaffold
```

## What makes it more than a prompt wrapper

**Cross-stage consistency validation.** Schema-valid output can still be wrong. The pipeline checks
meaning, not just shape, and feeds any contradiction back to the model for repair:

| Stage | Caught |
|---|---|
| 2 | A service invented, or silently dropped, versus the approved boundaries |
| 3 | A sync call in the HLD that no endpoint on the callee can receive |
| 4 | A datastore engine that contradicts the HLD; an index on a column that doesn't exist |
| 5 | A topic claiming a consumer whose LLD never subscribed; two services sharing a consumer group |
| 6 | Two services bound to the same port; an unpinned base image; a missing datastore dependency |

**Deterministic generation.** The model supplies *facts*; the Dockerfiles, compose file, Kubernetes
manifests and SQL DDL are generated from those validated facts by code. Two exports of the same
project are byte-identical, and the YAML is always well-formed.

**Provider-agnostic.** Claude or Gemini, chosen with one environment variable. Everything above
`app/ai/llm.py` depends on a `StructuredLLM` protocol, not a vendor SDK.

## Verified output

Run on a "Flipkart-like e-commerce" description, the generated scaffold was checked, not assumed:

- `docker compose config` validates the compose file
- all 18 Kubernetes manifests parse, with probes and resource limits
- the generated DDL **executes against a real PostgreSQL** and creates every table
- no secret value ever reaches a ConfigMap

## Layout

```
backend/    FastAPI orchestrator — stages, validation, export  (Python 3.12+, SQLAlchemy 2.0 async)
frontend/   React + Vite + Tailwind review UI, Mermaid diagrams
docker-compose.yml   Postgres + Redis for local development
```

## Running it

```bash
docker compose up -d

cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add GEMINI_API_KEY (free) or ANTHROPIC_API_KEY
alembic upgrade head
uvicorn app.main:app --reload            # http://localhost:8000/docs

cd ../frontend
npm install
npm run dev                              # http://localhost:5180
```

`GET /health` reports the configured provider and whether a key is loaded.

## Tests

```bash
cd backend && .venv/bin/pytest -q        # 71 tests, no API key needed
```

The suite runs against a real Postgres test database with a fake LLM, so it costs nothing and
still exercises every consistency rule, the retry loop and the export generator.

## Docs

A full plain-English explanation of every file and concept lives in
`/Users/sr/AI Microservice Architect docs/PROJECT_EXPLAINED.md`, with a per-version changelog in
`VERSIONS.md`.
