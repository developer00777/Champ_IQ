# ChampIQ V2 -- Project Conventions

## Overview

ChampIQ V2 is an AI-powered **fixed-pipeline** lead qualification and outreach engine for LakeB2B. Every prospect goes through the same automated pipeline: Research -> Pitch -> Email -> Wait -> Qualify -> Sales. No mode selection, no canvas builder -- just a single deterministic flow.

**Architecture:** `Frontend -> Gateway -> Redis Queue (BullMQ)`, `Frontend -> Gateway -> Workers -> AI Engine -> Neo4j`

The **Gateway owns the pipeline state machine** and drives all transitions via BullMQ. The AI Engine is a stateless worker that does the actual AI/ML work.

## SOLID Principles

This codebase strictly follows SOLID principles:

- **S - Single Responsibility:** Each worker, service, and processor handles exactly one concern. Workers do AI work. Processors handle queue jobs. Services manage state.
- **O - Open/Closed:** New pipeline stages or call types can be added by creating new processors/workers without modifying existing ones. The base worker class is extended, not modified.
- **L - Liskov Substitution:** All workers extend BaseWorker and are interchangeable via the WorkerRegistry. All processors follow the same BullMQ processor contract.
- **I - Interface Segregation:** API routes are split per domain (research, pitch, email, call, pipeline, settings). No fat interfaces.
- **D - Dependency Inversion:** Services depend on abstractions (get_graph_service(), get_llm_service()) not concrete implementations. Config is injected via Pydantic Settings.

## Project Structure

```
v2/
  services/
    ai-engine/       # Python FastAPI -- AI/ML, Graphiti, Research, Pitch, CHAMP scoring
    gateway/         # Node.js NestJS -- Pipeline orchestrator, BullMQ, auth, WebSocket
    frontend/        # React + TypeScript + Vite -- UI
```

## Key Technologies

- **LLM:** Ollama (llama3) with OpenRouter fallback (MiniMax M2.5)
- **Knowledge Graph:** Graphiti (by Zep) + Neo4j (:7474/:7687)
- **Relational DB:** PostgreSQL (:5432)
- **Job Queue:** BullMQ + Redis (:6379)
- **Embeddings:** embeddinggemma via Ollama
- **Voice Calls:** ElevenLabs Conversational AI (4 agent types)
- **Frontend:** React + TypeScript + Vite + Zustand + TanStack Query + shadcn/ui

## Ports

- AI Engine: **8001** (V1 uses 8000)
- Gateway: **4001** (V1 uses 4000)
- Frontend: **3001** (V1 uses 3000)
- Infrastructure (shared with V1): Postgres 5432, Redis 6379, Neo4j 7474/7687, Ollama 11434

## V2 Pipeline Flow

```
1. New Prospect (frontend form)
2. Perplexity Sonar Research
3. Embeddinggemma Embeddings + Graphiti ingestion
4. Email Pitch (model selectable from frontend)
5. SMTP Send (asks for availability)
6. IMAP Wait (configurable duration)
7a. Reply -> Lead Qualifier Agent -> Interested/Not Interested
7b. No reply -> Follow-up email -> Reply or Auto discovery call
8. Sales Agent qualifies -> QUALIFIED LEAD (HIL handoff)
```

## Commands

```bash
# Development (V2)
docker compose -f docker-compose.v2.yml up --build

# AI Engine
cd services/ai-engine
pip install -e ".[dev]"
uvicorn champiq_v2.main:app --reload --port 8001

# Gateway
cd services/gateway
npm install
npm run start:dev    # Port 4001

# Frontend
cd services/frontend
npm install
npm run dev          # Port 3001
```

## Coding Conventions

### Python (ai-engine)
- Python 3.12+, package name: `champiq_v2`
- FastAPI with Pydantic v2 for all request/response schemas
- Async throughout (httpx, asyncio)
- Config via Pydantic Settings, loaded from env vars
- All workers extend BaseWorker (Single Responsibility)
- Graph operations through GraphService abstraction (Dependency Inversion)

### Node.js (gateway)
- NestJS with TypeScript strict mode
- TypeORM for PostgreSQL
- BullMQ for pipeline job orchestration
- Pipeline state machine in PipelineService (Single Responsibility)
- Each processor handles one pipeline stage (Open/Closed)

### React (frontend)
- Vite + TypeScript strict mode
- Zustand for state, TanStack Query for server state
- shadcn/ui components
- React Hook Form + Zod for forms

## Pipeline States

```
NEW -> RESEARCHING -> RESEARCHED -> PITCHING -> EMAIL_SENT ->
WAITING_REPLY -> FOLLOW_UP_SENT -> WAITING_FOLLOW_UP ->
QUALIFYING_CALL -> INTERESTED/NOT_INTERESTED ->
SALES_CALL / NURTURE_CALL / AUTO_CALL -> QUALIFIED
```

## Service Communication

- Frontend -> Gateway (4001): REST + WebSocket (Socket.IO)
- Gateway -> AI Engine (8001): REST proxy
- Gateway -> Redis: BullMQ queues (v2-pipeline, v2-research, v2-pitch, v2-email, v2-imap, v2-call)
- AI Engine -> Neo4j: Graphiti SDK via bolt://:7687
- AI Engine -> Ollama: OpenAI-compatible API via :11434
