# Personal Assistant Backend

FastAPI backend for persona-aware companion chat, long-term memory, planning, task persistence, proactive reminders, and SSE streaming.

## Current Implementation

The backend currently implements these Chapter 4/5 paths:

- Companion chat via `/api/v1/chat/stream`.
- Persona state machine prompt generation.
- Long-term memory with PostgreSQL as the source of truth and ChromaDB as the semantic index.
- Selective memory write, duplicate detection, and update-by-upsert.
- Planning workflow with initialize, stream, confirm, list, detail, active-plan, and task update endpoints.
- Progressive planning: the first planning stream returns coarse container tasks, and the user can choose which part to decompose next.
- Persisted active plans keep a recursive task tree; unfinished container tasks can be decomposed later from the active plan.
- Unified `SSEFrame` event output for streaming routes.

## Architecture Map

Core modules:

- `src/main.py`: FastAPI app creation, CORS, exception handling, router registration.
- `src/routers/api_v1/chat.py`: companion chat SSE endpoint.
- `src/routers/api_v1/planning.py`: planning and task endpoints.
- `src/routers/api_v1/companion.py`: proactive companion endpoint.
- `src/routers/api_v1/dependencies.py`: repository and service wiring.
- `src/services/orchestrator.py`: chat stream orchestration and `SSEFrame` creation.
- `src/services/companion.py`: persona-aware companion chat flow.
- `src/services/mental_state.py`: deterministic mental state machine.
- `src/services/memory_service.py`: memory retrieval policy and selective write policy.
- `src/services/planning.py`: goal clarification, plan generation, recursive plan confirmation, persisted-plan decomposition, task updates.
- `src/adapters/pg_repo.py`: PostgreSQL repositories for plans, tasks, memory, and outbox.
- `src/adapters/chroma_adapter.py`: ChromaDB semantic index adapter.
- `src/core/ports/memory_port.py`: `MemoryPort.query_context()`, `store()`, and `batch_store()`.
- `src/core/ports/task_port.py`: task and plan persistence boundary.
- `src/core/prompts/persona_profiles.py`: structured persona profile definitions.

## Local Services

The development setup can use a remote PostgreSQL instance through `DATABASE_URL` while keeping ChromaDB local.

Required runtime pieces:

- `uv`: Python dependency and command runner.
- PostgreSQL: durable source of truth. This can be remote through `DATABASE_URL` or local through Docker Compose.
- ChromaDB: local semantic memory index, normally started by Docker Compose.
- LLM provider credentials in `.env`.
- Redis is optional for current core chat/planning flows; start it only when testing Redis-backed extensions.

Start local Chroma:

```powershell
docker compose up -d chroma
```

Check Chroma:

```powershell
docker compose ps chroma
```

If you want local PostgreSQL and Redis as well:

```powershell
docker compose up -d db redis chroma
```

## Environment

Required database and memory settings:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/personal_assistant
MEMORY_BACKEND=chroma
CHROMADB_HOST=localhost
CHROMADB_PORT=8001
CHROMADB_COLLECTION=memories
CHROMA_ONNX_MODEL_PATH=.chroma-cache/onnx_models/all-MiniLM-L6-v2
```

Supported memory backends:

- `chroma`: PostgreSQL truth source plus Chroma semantic index.
- `pg`: PostgreSQL only, without vector recall.
- `in_memory`: test/local fallback only.

LLM settings are loaded from `.env`; supported providers are wired through `src/infra/llm_router.py`.

## Database

Run migrations when pointing at a new PostgreSQL database:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Main tables:

- `plans`: persisted user plans.
- `tasks`: persisted task tree rows.
- `memories`: durable long-term memory facts.
- `outbox`: asynchronous event records.
- `alembic_version`: migration state.

## Long-Term Memory

The memory path follows the Chapter 4 design:

- PostgreSQL is the source of truth for memory facts.
- ChromaDB is a semantic retrieval index only.
- Chroma stores document text and scalar metadata; full metadata stays in PostgreSQL.
- Writes go to PostgreSQL first, then synchronize the Chroma index.
- Reads use Chroma for candidate recall, then hydrate complete records from PostgreSQL.

Retrieval ranking:

```text
final_score = 0.60 * semantic_score + 0.25 * importance + 0.15 * freshness
```

The companion read path also applies:

- low-signal query skipping,
- expanded Chroma recall before PostgreSQL hydration,
- prompt context character budgeting.

The default Chroma embedding function is `ONNXMiniLM_L6_V2`. Model files are cached under `.chroma-cache/`, which is ignored by Git.

## Memory Write Policy

Companion turns are not written blindly. `MemoryService.store_turn_summary()` first classifies the turn and writes only high-value candidates:

- preferences,
- facts,
- project context,
- goals,
- salient emotional episodes.

Before insertion, it searches existing memories with the same `user_id`, `scope`, and `memory_type`.

- No similar memory: insert a new row with `write_policy=insert`.
- Similar memory found: reuse the existing memory id and upsert with `write_policy=update`.
- The upsert path keeps PostgreSQL authoritative and refreshes the Chroma index with the same id.

This prevents repeated preferences or facts from creating unbounded duplicate rows.

## Persona State Machine

Companion prompts use a structured persona state machine instead of one fixed persona paragraph.

The generated system prompt has three layers:

- `STABLE PERSONA LAYER`: role identity, stable traits, language style, and value boundaries.
- `DYNAMIC STATE LAYER`: detected mental state, confidence, evidence, response strategy, and state transition constraints.
- `SCENE BOUNDARY LAYER`: companion-mode boundaries that keep casual support separate from formal planning.

`MentalStateMachine` maps the current user message and retrieved memory state into `MentalStateSnapshot`.

Current response strategies:

- `balanced_continuity`
- `pressure_reduction`
- `low_friction_action`
- `clarify_and_structure`
- `momentum_to_action`
- `emotional_safety`

This keeps stable persona parameters consistent while allowing local state constraints to adjust the current response.

## API Summary

Companion:

- `POST /api/v1/chat/stream`: companion chat stream.
- `POST /api/v1/companion/proactive/stream`: proactive companion stream.

Planning:

- `POST /api/v1/planning/initialize`: create a planning session and clarification questions.
- `POST /api/v1/planning/stream`: stream first-layer coarse decomposition and final candidate plan.
- `POST /api/v1/planning/decompose-task/stream`: continue decomposing one selected container task. It can operate on an in-progress planning session or on a persisted active plan when `plan_id` is supplied.
- `POST /api/v1/planning/confirm`: persist confirmed plan through `TaskPort.save_plan()`.
- `GET /api/v1/planning/users/{user_id}/plans`: list plans.
- `GET /api/v1/planning/users/{user_id}/active-plan`: get most recent active plan.
- `GET /api/v1/planning/plans/{plan_id}`: get plan detail.
- `PATCH /api/v1/planning/tasks/{task_id}`: update task checked/status fields.

## Progressive Planning Tasks

Planning tasks now use two task granularities in the same `PlanResult.tasks` list:

- `task_type=atomic`: directly executable task, usually scheduled and checkable.
- `task_type=container`: coarse long-horizon task that should remain broad until the user chooses to continue decomposition.

Relevant task fields:

```json
{
  "task_type": "atomic | container",
  "can_decompose": true,
  "decomposition_ref": "task id to pass into /planning/decompose-task/stream",
  "estimated_duration_minutes": "5..10080"
}
```

The default `/planning/stream` endpoint stops after the first coarse layer. The frontend should show `container` tasks as expandable long-term tasks and call `/planning/decompose-task/stream` only for the selected task. This avoids generating an overly long full task tree before the user decides which branch matters.

Confirmed container tasks are valid persisted tasks. A user can save a coarse task before it has been decomposed into atomic tasks. The persisted plan keeps the task as `task_type=container`, `can_decompose=true`, and can later continue decomposition from the active-plan view.

Continuing decomposition from a persisted plan:

```json
{
  "session_id": "original planning session id",
  "user_id": "default_user",
  "task_id": "container task id",
  "plan_id": "persisted plan id"
}
```

When `plan_id` is present, `/planning/decompose-task/stream` appends/replaces the selected task's persisted subtree through `TaskPort.replace_task_subtree()`. This keeps PostgreSQL and the active-plan response aligned after refresh.

Duration bounds:

- `AtomicTaskItem.estimated_duration_minutes` is capped at `10080` minutes.
- First-layer container estimates from `estimated_days` are clamped before validation.
- Later long-task estimates from `estimated_hours` are clamped before validation.

This prevents long-horizon milestones such as 14-day tasks from failing Pydantic validation while still allowing the task to remain a decomposable container.

## Run The Server

Recommended one-command startup on Windows:

```powershell
.\scripts\start-backend.ps1
```

Or use the command wrapper from the backend directory:

```cmd
start-backend.cmd
```

This script:

- runs `uv sync`,
- starts local Chroma with Docker Compose,
- optionally starts local PostgreSQL and Redis,
- runs Alembic migrations,
- starts Uvicorn on `127.0.0.1:8000`.

Useful variants:

```powershell
# Use local PostgreSQL from docker-compose.yml in addition to Chroma
.\scripts\start-backend.ps1 -WithLocalPostgres

# Also start Redis
.\scripts\start-backend.ps1 -WithRedis

# Chroma/PostgreSQL are already available, only start backend
.\scripts\start-backend.ps1 -SkipDocker

# Skip dependency sync and migrations for faster repeat startup
.\scripts\start-backend.ps1 -NoSync -SkipMigrations

# Use another port
.\scripts\start-backend.ps1 -Port 8010
```

Manual startup:

```powershell
uv run python -m uvicorn src.main:app --reload
```

Default local URL:

```text
http://127.0.0.1:8000
```

## Verification

Run unit tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit
```

Run integration tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration
```

Run all tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Known local warning: pytest may warn that `.pytest_cache` cannot be written if the directory is locked or permission-restricted. This does not affect test results.

## Current Test Coverage

Unit tests cover:

- Chroma metadata sanitation and filter conversion.
- PG-backed memory write/read behavior.
- Chroma failure fallback to PG.
- Memory retrieval skipping and context budget.
- Selective memory insert/update policy.
- Persona state machine prompt structure.
- Mental state detection and response strategy.
- Progressive planning container generation, recursive persistence, persisted active-plan continuation, and duration capping.
- Shadow parser event extraction.

Integration tests cover:

- Planning API workflow.
- Chat stream routing behavior.
- Proactive companion stream behavior.

## Troubleshooting

Docker engine not running:

```powershell
Start-Process -FilePath "C:\Program Files\Docker\Docker\Docker Desktop.exe"
docker version
```

Chroma port check:

```powershell
Test-NetConnection -ComputerName localhost -Port 8001
```

Remote PostgreSQL check:

```powershell
.\.venv\Scripts\python.exe -m alembic current
```

If Chroma embedding configuration changes, delete and rebuild only the local Chroma collection. PostgreSQL remains the source of truth.
