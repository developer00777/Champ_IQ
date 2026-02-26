# ChampIQ V2 -- Implementation Plan

## Context

V1 has a flexible workflow system (manual/semi-auto/autonomous canvas) that is overengineered for the actual use case. The user wants a **single fixed pipeline** that every prospect goes through automatically, with no mode selection or canvas builder. V2 will be a new folder (`v2/`) in the same repo, reusing the same infrastructure (Postgres, Redis, Neo4j, Ollama) and same tech stack, but with a drastically simplified flow.

**Architecture:** `Frontend -> Gateway -> Redis Queue (BullMQ)`, `Frontend -> Gateway -> Workers -> AI Engine -> Neo4j`

The Gateway owns the pipeline state machine and drives all transitions via BullMQ. The AI Engine is a stateless worker that does the actual AI/ML work.

---

## V2 Fixed Pipeline Flow

```
1. New Prospect (frontend form)
2. Perplexity Sonar Research (company, prospect, pain points, triggers)
3. Embeddinggemma Embeddings + Graphiti ingestion (Neo4j)
4. Email Pitch (model selectable from frontend settings)
5. SMTP Send (email asks for availability)
6. IMAP Wait (wait time configurable from frontend)
7a. Reply received -> Lead Qualifier Agent call
    -> Interested -> Sales Agent call
    -> Not interested -> Nurturing Agent call -> Sales Agent call
7b. No reply -> Follow-up email (asks availability again)
    -> Reply -> Lead Qualifier call (same as 7a)
    -> Still no reply -> Automatic discovery call -> route like 7a
8. Sales Agent qualifies -> QUALIFIED LEAD (HIL handoff)
```

Every call: transcript -> pitch agent summarizes -> save to graph -> pass context to next agent via ElevenLabs dynamic_variables.

---

## Folder Structure

```
v2/
  CLAUDE.md
  .env
  docker-compose.v2.yml

  services/
    ai-engine/
      Dockerfile
      pyproject.toml
      champiq_v2/
        __init__.py
        main.py
        config.py
        llm/service.py
        graph/
          service.py, graphiti_service.py, entities.py, edges.py
        scoring/champ_scorer.py
        workers/
          base.py, research_worker.py, smtp_worker.py,
          imap_worker.py (NEW), voice_worker.py,
          pitch_worker.py (NEW), summary_worker.py (NEW),
          context_builder.py (NEW)
        agents/pitch/agent.py
        api/routes/
          health.py, research.py, pitch.py, email.py,
          call.py, pipeline.py, prospects.py, settings.py
        utils/timezone.py

    gateway/
      Dockerfile, package.json, tsconfig.json
      src/
        main.ts, app.module.ts, health.controller.ts
        auth/  (copy from V1)
        prospects/  (simplified entity + DTO + service + controller)
        pipeline/  (NEW - core of V2)
          pipeline.module.ts, pipeline.service.ts
          processors/
            research.processor.ts
            pitch.processor.ts
            email.processor.ts
            imap.processor.ts
            call.processor.ts
        ai-proxy/  (copy from V1, new base URL)
        websocket/  (copy from V1)
        utils/timezone.ts

    frontend/
      Dockerfile, package.json, vite.config.ts, tailwind.config.ts
      src/
        App.tsx, main.tsx, index.css
        api/client.ts
        types/index.ts
        stores/ (authStore.ts, activityStore.ts - from V1)
        lib/utils.ts
        pages/
          Login.tsx, Dashboard.tsx, AddProspect.tsx (NEW),
          ProspectDetail.tsx (NEW), Settings.tsx
        components/
          ui/ (shadcn - from V1)
          activity/ (from V1)
          pipeline/ (NEW)
            PipelineStatusBar.tsx, StageCard.tsx
```

---

## V2 Prospect States

```python
class ProspectState(str, Enum):
    NEW = "new"
    RESEARCHING = "researching"
    RESEARCHED = "researched"
    PITCHING = "pitching"
    EMAIL_SENT = "email_sent"
    WAITING_REPLY = "waiting_reply"
    FOLLOW_UP_SENT = "follow_up_sent"
    WAITING_FOLLOW_UP = "waiting_follow_up"
    QUALIFYING_CALL = "qualifying_call"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    SALES_CALL = "sales_call"
    NURTURE_CALL = "nurture_call"
    AUTO_CALL = "auto_call"
    QUALIFIED = "qualified"   # Terminal: HIL handoff
```

---

## Implementation Steps

### Step 1: Scaffold V2 directory + config files
- Create `v2/` folder structure
- Write `v2/CLAUDE.md` with V2 conventions
- Write `v2/.env` derived from existing `.env` (ports: AI=8001, GW=4001, FE=3001)
- Write `v2/docker-compose.v2.yml` (V2 services connecting to shared infra)

### Step 2: AI Engine -- foundation
- **Copy unchanged from V1:** `graph/edges.py`, `graph/graphiti_service.py`, `scoring/champ_scorer.py`, `utils/timezone.py`, `workers/base.py`, `workers/research_worker.py`
- **Copy + modify:**
  - `config.py` -- remove `AutonomyLevel`/decision engine settings, add `imap_wait_hours`, `pitch_model`, separate ElevenLabs agent IDs per call type, port 8001
  - `graph/entities.py` -- replace `ProspectState` with V2 states, remove `Decision`/`DecisionType`
  - `graph/service.py` -- remove `create_decision()`/`get_decision_context()`, add `get_context_summary()` (builds text summary of all interactions for ElevenLabs agents), add `save_call_summary()`
  - `llm/service.py` -- add `complete_with_model(model, prompt)` for frontend-selectable model, add `summarize_transcript()` method, add `generate_email_with_availability()` wrapper
  - `workers/smtp_worker.py` -- ensure all emails append availability CTA, add `send_followup()` method
  - `workers/voice_worker.py` -- accept `agent_type` param to select qualifier/sales/nurture/auto agent, accept `context_summary` via `dynamic_variables`, remove `_trigger_reevaluation()` (gateway handles routing)
  - `agents/pitch/agent.py` -- append availability CTA to all email variants
- **Create new:**
  - `workers/imap_worker.py` -- standalone IMAP reply checker endpoint
  - `workers/pitch_worker.py` -- wraps PitchAgent with model selection from request body
  - `workers/summary_worker.py` -- transcript -> LLM summary -> save to Neo4j graph via Graphiti
  - `workers/context_builder.py` -- assembles full context (research + emails + call summaries) for passing to ElevenLabs agents

### Step 3: AI Engine -- API routes
- `api/routes/health.py` -- `/health`, `/ready`
- `api/routes/prospects.py` -- copy from V1 (create/get/list/context), use V2 states
- `api/routes/research.py` -- `POST /api/v2/research/{id}` runs ResearchWorker
- `api/routes/pitch.py` -- `POST /api/v2/pitch/{id}` with `{model?: string}` body
- `api/routes/email.py` -- `POST /api/v2/email/send`, `/followup`, `/check-reply`
- `api/routes/call.py` -- `POST /api/v2/call/qualifier|sales|nurture|auto`, `POST /api/v2/call/summarize`
- `api/routes/pipeline.py` -- `GET /api/v2/prospect/{id}/pipeline-status`, `/context-summary`
- `api/routes/settings.py` -- `GET/POST /api/v2/settings` (runtime config for SMTP, model, wait time)
- `main.py` -- FastAPI app, include all V2 routers, lifespan (Neo4j + Graphiti init), port 8001

### Step 4: Gateway -- foundation
- Copy `package.json` from V1 (same deps)
- `app.module.ts` -- import Auth, Prospects, Pipeline, AiProxy, Websocket modules only
- Copy unchanged: `auth/`, `websocket/`, `utils/timezone.ts`, `health.controller.ts`
- Copy + modify: `ai-proxy/` (base URL -> `http://ai-engine-v2:8001`)
- `prospects/entity` -- add `pipeline_state` + `pipeline_data` JSONB columns
- `prospects/dto` -- simplified `CreateProspectDto: {name, email, phone, title, company_domain}`
- `prospects/service` -- on `create()`: save to Postgres, enqueue `v2-pipeline:start-pipeline`
- `prospects/controller` -- CRUD + `GET /:id/pipeline` for pipeline status
- `main.ts` -- port 4001

### Step 5: Gateway -- Pipeline Orchestrator (core of V2)
- `pipeline/pipeline.module.ts` -- register BullMQ queues: `v2-pipeline`, `v2-research`, `v2-pitch`, `v2-email`, `v2-imap`, `v2-call`
- `pipeline/pipeline.service.ts` -- state machine:
  - `startPipeline(prospectId)` -- enqueue research
  - `advanceState(prospectId, newState, data?)` -- update Postgres `pipeline_state`, append to `pipeline_data.stages[]`, broadcast WebSocket event
  - `getStatus(prospectId)` -- return full pipeline state + stage history
  - `getSettings()` -- read IMAP wait hours + pitch model from Postgres/Redis
- `processors/research.processor.ts` -- sync prospect to AI Engine, call `/api/v2/research/{id}`, on complete: enqueue pitch
- `processors/pitch.processor.ts` -- call `/api/v2/pitch/{id}` with model setting, on complete: enqueue email send
- `processors/email.processor.ts` -- call `/api/v2/email/send`, on complete: enqueue delayed IMAP check. Also handles `send-followup` job.
- `processors/imap.processor.ts` -- call `/api/v2/email/check-reply`. If reply: enqueue qualifier call. If no reply + attempt 1: enqueue followup. If no reply + attempt 2: enqueue auto call.
- `processors/call.processor.ts` -- handles `call-qualifier`, `call-sales`, `call-nurture`, `call-auto`. Each: call AI Engine endpoint, call `/api/v2/call/summarize`, route to next step based on `summary.interested`. Sales call marks prospect as `qualified`.

### Step 6: Frontend
- Copy unchanged: `components/ui/*`, `stores/*`, `lib/utils.ts`, `pages/Login.tsx`
- `types/index.ts` -- V2 pipeline states, remove Workflow types, add `PipelineStage` + `ProspectPipeline` interfaces
- `api/client.ts` -- remove workflow/decision APIs, add `pipelineApi`, simplify `prospectApi`
- `App.tsx` -- routes: `/login`, `/`, `/prospect/:id`, `/add`, `/settings`. Sidebar: Dashboard, Settings only.
- `pages/Dashboard.tsx` -- prospect table with pipeline state badges, filters, activity feed, stats (total, by stage, qualified)
- `pages/AddProspect.tsx` (NEW) -- form: name, email, phone, title, company_domain. Submit auto-starts pipeline.
- `pages/ProspectDetail.tsx` (NEW) -- vertical stepper showing pipeline progress, research data, emails, call transcripts/summaries, qualification badge
- `pages/Settings.tsx` -- SMTP/IMAP config, LLM model dropdown/text input, IMAP wait hours, ElevenLabs agents (qualifier/sales/nurture IDs + API key + phone)
- `components/pipeline/PipelineStatusBar.tsx` (NEW) -- horizontal stage indicator
- `components/pipeline/StageCard.tsx` (NEW) -- stage detail card

### Step 7: Docker + Integration
- `v2/docker-compose.v2.yml` -- defines `ai-engine-v2` (8001), `gateway-v2` (4001), `frontend-v2` (3001) on same `backend`/`frontend` networks
- AI Engine `Dockerfile` (copy V1, change package name)
- Gateway `Dockerfile` (copy V1)
- Frontend `Dockerfile` (copy V1, change port)

---

## Files Reused Unchanged (import paths only)

| V1 File | Purpose |
|---------|---------|
| `workers/base.py` | BaseWorker, ActivityStream, GatewayBridge |
| `workers/research_worker.py` | Perplexity Sonar research |
| `graph/graphiti_service.py` | Graphiti + embeddinggemma |
| `graph/edges.py` | Edge models |
| `scoring/champ_scorer.py` | CHAMP scoring |
| `utils/timezone.py` | IST helpers |
| Gateway `auth/*` | JWT auth |
| Gateway `websocket/*` | Socket.IO events |
| Frontend `components/ui/*` | shadcn/ui |
| Frontend `stores/*` | Zustand (auth + activity) |

## Files Created New

| File | Purpose |
|------|---------|
| `workers/imap_worker.py` | Standalone IMAP reply check |
| `workers/pitch_worker.py` | Pitch with model selection |
| `workers/summary_worker.py` | Transcript -> summary -> graph |
| `workers/context_builder.py` | Context assembly for ElevenLabs |
| Gateway `pipeline/*` (6 files) | Pipeline orchestrator + 5 processors |
| Frontend `AddProspect.tsx` | Prospect creation form |
| Frontend `ProspectDetail.tsx` | Pipeline progress view |
| Frontend `pipeline/` (2 files) | Pipeline visualization |

---

## Verification

1. **Unit test:** Create prospect via frontend form, verify it appears in Postgres + pipeline state = `new`
2. **Research:** Verify Perplexity Sonar runs, data appears in Neo4j, Graphiti entities created with embeddings
3. **Pitch:** Verify email generated using selected model (not "Unknown" name bug), availability CTA present
4. **Email:** Verify SMTP sends, IMAP check returns reply status
5. **Follow-up:** If no reply after wait, verify follow-up email sent automatically
6. **Call:** Verify ElevenLabs call initiated with correct agent + context summary in dynamic_variables
7. **Summary:** Verify transcript summarized, saved to graph, passed to next agent
8. **Qualification:** Verify `qualified` state reached, frontend shows qualified badge
9. **End-to-end:** Create prospect -> watch pipeline progress in real-time via WebSocket on ProspectDetail page
