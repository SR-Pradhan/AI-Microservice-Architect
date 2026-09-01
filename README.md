<div align="center">

# 🏗️ AI Microservice Architect

**Describe a system in plain English. Get a microservice architecture you can actually ship.**

Service boundaries → HLD → LLD → DB schemas → Kafka contracts → Docker/K8s manifests → a downloadable repo scaffold.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Tests](https://img.shields.io/badge/tests-87%20passing-brightgreen)](#-tests)

</div>

---

## 🎯 What it does

You type: *"A Flipkart-like e-commerce platform."*

You get back a complete architecture — which services should exist, how they talk to each other, their API contracts, their database tables, the Kafka topics between them, and the Docker and Kubernetes files to run it all.

It is a **staged, human-checkpointed pipeline**, not a one-shot generator. Each stage produces an artifact you review, edit and approve before the next one runs.

That is a deliberate design decision. Service boundary decisions are architectural judgement calls — if the split at stage 1 is wrong, everything downstream is wrong with it. One human checkpoint at the top stops garbage from cascading.

| | Stage | Produces | |
|:--:|:--|:--|:--:|
| 1️⃣ | **Service Boundaries** | Which services exist, and why each split was made | ⬇️ |
| 2️⃣ | **High-Level Design** | Service map, sync vs async, per-service datastores | ⬇️ |
| 3️⃣ | **Low-Level Design** | Entities, API contracts, internal logic notes | ⬇️ |
| 4️⃣ | **DB Schemas** | Tables, columns, indexes, keys | ⬇️ |
| 5️⃣ | **Kafka Events** | Topics, partitions, consumer groups, DLQ policy | ⬇️ |
| 6️⃣ | **Docker / Kubernetes** | Images, ports, probes, resource limits | 📦 |

Between every stage: **review ✏️ → edit → approve ✅**. A stage physically cannot run until you've signed off on the one before it.

---

## 🧠 Why it's more than a prompt wrapper

### 1. Cross-stage consistency validation

Schema-valid output can still be *wrong*. If stage 1 approved `OrderService` and stage 2 returns a beautiful design featuring `GhostService`, the JSON is perfectly valid — the shape is right, only the meaning is wrong. Pydantic has no way to know.

So every stage is checked against the ones before it, and any contradiction is **fed back to the model for repair**:

| Stage | What gets caught |
|:--|:--|
| 2️⃣ HLD | A service invented, or silently dropped, versus the approved boundaries |
| 3️⃣ LLD | A sync call in the HLD that **no endpoint on the callee can receive** |
| 4️⃣ Schemas | A datastore engine contradicting the HLD; an index on a column that doesn't exist |
| 5️⃣ Events | A topic claiming a consumer whose LLD never subscribed; **two services sharing a consumer group** |
| 6️⃣ Infra | An SDK image shipped as a runtime; a start command whose artifact nothing builds; credentials in a non-secret env var; two services on one port |

> 💡 That consumer-group check is a good example. Kafka delivers each message to *one* member of a group — two different services in the same group don't both receive the event, they steal it from each other and half your notifications silently vanish. It looks completely fine in JSON.

### 2. Deterministic generation

The model supplies **facts**; the Dockerfiles, compose file, Kubernetes manifests and SQL DDL are generated from those validated facts **by code**.

An LLM asked to emit YAML will eventually produce a subtly broken indent. A generator cannot. Two exports of the same project are byte-identical.

### 3. Provider-agnostic

Claude or Gemini, switched with **one environment variable**. Everything above `app/ai/llm.py` depends on a `StructuredLLM` protocol, never a vendor SDK — adding a second provider cost one class and changed nothing else.

---

## ✅ Verified output, not assumed

Run on a *"Flipkart-like e-commerce"* description, the generated scaffold was actually checked:

| Check | Result |
|:--|:--|
| `docker compose config` on the generated compose file | ✅ validates |
| 18 Kubernetes manifests, with probes and resource limits | ✅ all parse |
| Generated DDL executed against a **real PostgreSQL** | ✅ 7 tables created |
| Secrets in any ConfigMap | ✅ none — moved to a `kubectl create secret` hint |
| Compiled services get true multi-stage Dockerfiles | ✅ `golang` builder → `alpine` runtime |

---

## 🛠️ Tech stack

**Backend** — Python 3.12+ · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · Alembic · PostgreSQL · Redis

**Frontend** — React 18 · Vite · TypeScript · Tailwind CSS v4 · Mermaid.js

**AI** — Anthropic Claude *or* Google Gemini, both in structured-output mode

> 🧩 **Pydantic does triple duty.** Each stage's output shape is defined once as a Pydantic model. That single definition becomes the JSON schema the model must produce, validates what comes back, and documents the stage — instead of maintaining the same schema in three places.

---

## 🚀 Getting started

### 1. Infrastructure

```bash
docker compose up -d          # Postgres :5434 · Redis :6380
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add a key to `.env` — **Gemini has a free tier, no card required**:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=...            # https://aistudio.google.com/apikey
# or
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...  # https://console.anthropic.com
```

```bash
alembic upgrade head
uvicorn app.main:app --reload      # 📖 http://localhost:8000/docs
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                        # 🖥️ http://localhost:5180
```

> 🔎 `GET /health` reports which provider and model are configured and whether a key is loaded — the fastest way to diagnose a 503.

---

## 🧪 Tests

```bash
cd backend && .venv/bin/pytest -q     # 87 tests, no API key needed, zero cost
```

The suite runs against a real Postgres test database with a **fake LLM**, so it costs nothing and still exercises every consistency rule, the retry-with-error-feedback loop, and the export generator.

---

## 📁 Project structure

```
backend/
├── app/
│   ├── ai/
│   │   ├── contracts.py        📐 output shape of each stage (Pydantic)
│   │   ├── prompts.py          💬 one focused prompt per stage
│   │   ├── llm.py              🔌 the LLM boundary — Claude + Gemini
│   │   └── gemini_schema.py    🔄 Pydantic schema → Gemini's dialect
│   ├── services/
│   │   ├── stage_executor.py   ⚙️ the pipeline engine + retry loop
│   │   ├── consistency.py      🛡️ cross-stage contradiction checks
│   │   ├── diagram.py          📊 stage JSON → Mermaid
│   │   └── export.py           📦 artifacts → repo scaffold zip
│   ├── models/ · schemas/ · api/routes/
│   └── main.py
├── alembic/                    🗄️ migrations
└── tests/                      ✅ 87 tests
frontend/
└── src/
    ├── components/             🎨 UI primitives, diagrams, stage panels
    ├── pages/ · lib/
    └── index.css               🌗 design tokens + light/dark themes
docker-compose.yml
```

---

## 🌗 Interface

- **Light, dark and system themes** — the theme is resolved to a concrete `data-theme` before first paint, so there's no flash on load. Mermaid diagrams are re-rendered on theme change, since they bake colours into the SVG.
- **Real feedback during generation** — a stage takes 30–200 seconds, so it shows elapsed time against a *measured* typical duration for that stage, and warns when the model is likely retrying after a failed validation.
- **Diagrams** — service map, ER diagram and event flow, rendered server-side into Mermaid and drawn with zoom and pan.
- **Everything is editable** — your edits are validated against the same contract as the model's output, and the export builds from *your* version.

---

## 🗺️ Roadmap

Deliberately **not** built in v1:

- [ ] Version diffing — the `version` counter increments and `input_snapshot` records every input, but there's no side-by-side diff UI
- [ ] Background job queue — stage 3 holds a ~55s HTTP request; Celery/RQ only if latency becomes a real problem
- [ ] Critique agent — a stage that re-validates every artifact against the others. The cross-stage checks are a deterministic subset of this idea
- [ ] Authentication — every project is currently public
- [ ] Deployment — it runs locally only

---

## 📚 Documentation

A full plain-English explainer of every file and concept, plus a per-version changelog, lives alongside this repo in `AI Microservice Architect docs/`:

- **`PROJECT_EXPLAINED.md`** — every module, every decision, and why
- **`VERSIONS.md`** — what shipped in each version, what was verified, and what broke along the way

---

<div align="center">

Built by **[Sruti Ranjan Pradhan](https://github.com/SR-Pradhan)**

</div>
