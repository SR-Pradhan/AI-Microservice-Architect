# AI Microservice Architect

Turns a plain-English system description ("Flipkart-like e-commerce platform") into a complete
microservice architecture through a **staged, human-checkpointed pipeline**: service boundaries →
HLD → LLD → DB schemas → Kafka event contracts → Docker/K8s manifests. Each stage produces an
artifact you review and edit before it feeds the next one.

**Current version: v0.1.0** — orchestrator skeleton, Postgres schema, project CRUD, frontend shell.
No AI calls yet.

## Layout

```
backend/    FastAPI orchestrator (Python 3.12+, SQLAlchemy 2.0 async, Alembic)
frontend/   React + Vite + Tailwind review UI
docker-compose.yml   Postgres + Redis for local dev
```

## Running locally

```bash
# 1. infrastructure
docker compose up -d

# 2. backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload          # http://localhost:8000/docs

# 3. frontend (new terminal)
cd frontend
npm install
npm run dev                            # http://localhost:5173
```

## Docs

Full plain-English explanation of every file and concept lives in
`/Users/sr/AI Microservice Architect docs`.
