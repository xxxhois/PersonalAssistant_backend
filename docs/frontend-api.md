# Personal Assistant Backend API

Base URL examples:

- Local: `http://localhost:8000`
- API prefix: `/api/v1`

All streaming APIs use Server-Sent Events with this wire format:

```text
data: {"id":"token_1","event":"token","data":{"token":"..."},"request_id":"...","seq":1,"recoverable":null}

```

Frontend should parse only lines starting with `data: ` and then `JSON.parse(line.slice(6))`.

## SSE Frame

```ts
type SSEEventType = "token" | "task_event" | "progress" | "error" | "done" | "heartbeat";

interface SSEFrame<T = unknown> {
  id: string;
  event: SSEEventType;
  data: T;
  request_id: string;
  seq: number;
  recoverable?: boolean | null;
}
```

For `event === "error"`, `recoverable` is always present.

## Health

### GET `/`

Checks whether the backend process is alive.

Response:

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

## Companion Chat

### POST `/api/v1/chat/stream`

Main chat endpoint for the shared frontend chat window when the UI is in companion mode.

This endpoint uses:

- long-term memory retrieval
- mental-state state machine
- Marlowe-style persona prompt
- selective memory storage after the assistant finishes

It does not perform formal goal decomposition. If the frontend wants decomposition, call the planning endpoints below.

Request:

```json
{
  "user_id": "user-1",
  "user_message": "我今天有点累，但还想推进毕业设计",
  "mode": "companion"
}
```

Fields:

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `user_id` | string | no | Defaults to `default_user`; use stable logged-in user id. |
| `user_message` | string | yes | 1-4000 chars. |
| `mode` | `"companion" | "planning"` | no | Defaults to `companion`. `planning` is rejected here by design. |

SSE events:

#### `token`

```json
{
  "event": "token",
  "data": {
    "token": "先把灯开小一点。"
  }
}
```

Append `data.token` to the assistant message.

#### `task_event`

Reserved for machine-readable task markers emitted by the model. In companion mode, frontend can ignore it unless a future UI wants to show extracted lightweight task hints.

```json
{
  "event": "task_event",
  "data": {
    "type": "TASK_CREATED",
    "id": "task_1"
  }
}
```

#### `done`

```json
{
  "event": "done",
  "data": {
    "request_id": "..."
  }
}
```

Stop loading state.

#### `error`

```json
{
  "event": "error",
  "data": {
    "code": "INTERNAL_ERROR",
    "message": "..."
  },
  "recoverable": false
}
```

If `recoverable` is true, frontend may show a retry action.

Planning mode rejection example:

```json
{
  "detail": "planning mode is handled by /api/v1/planning endpoints; companion chat intentionally stays decoupled from goal decomposition"
}
```

## Proactive Companion Outreach

### POST `/api/v1/companion/proactive/stream`

Generates a short proactive companion message. This endpoint may read the user's active goal and decomposed tasks, plus memory and persona state. It does not create, split, or mutate tasks.

Use this when frontend or a scheduler wants to show a gentle nudge such as morning check-in, task reminder, or comeback message.

Request:

```json
{
  "user_id": "user-1",
  "trigger_reason": "scheduled morning check-in before today's tasks"
}
```

Fields:

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `user_id` | string | yes | User to generate outreach for. |
| `trigger_reason` | string | yes | 1-1000 chars; explain why this message is being generated. |

SSE events:

- `token`: append `data.token`
- `done`: stop loading
- `error`: show failure/retry UI

Example token:

```json
{
  "event": "token",
  "data": {
    "token": "早上好。案子还在桌上，先拿最小的一件开刀。"
  }
}
```

## Planning Workflow

Planning is separate from companion chat. Frontend can still render it in the same chat window, but it should call these endpoints when `mode === "planning"`.

Recommended flow:

1. Call `POST /api/v1/planning/initialize`.
2. Render clarification questions.
3. Call `POST /api/v1/planning/stream` with selected answers.
4. Render generated atomic tasks.
5. Call `POST /api/v1/planning/confirm` with selected task ids.
6. Use list/detail/update endpoints for task management.

### POST `/api/v1/planning/initialize`

Starts a goal-decomposition session and returns clarification questions.

Request:

```json
{
  "user_id": "user-1",
  "goal_description": "三个月内完成毕业设计并准备答辩"
}
```

Response:

```json
{
  "session_id": "session-1",
  "goal_summary": "Complete the graduation project and prepare the defense.",
  "questions": [
    {
      "question_id": "q1",
      "question_text": "How much time can you spend each day?",
      "options": [
        {"key": "A", "label": "30 minutes"},
        {"key": "B", "label": "1 hour"}
      ],
      "allow_multiple": false
    }
  ]
}
```

Types:

```ts
interface GoalInitRequest {
  user_id: string;
  goal_description: string;
}

interface GoalInitResponse {
  session_id: string;
  goal_summary: string;
  questions: ClarifyQuestion[];
}

interface ClarifyQuestion {
  question_id: string;
  question_text: string;
  options: QuestionOption[];
  allow_multiple: boolean;
}

interface QuestionOption {
  key: string;
  label: string;
}
```

### POST `/api/v1/planning/stream`

Streams decomposition progress and final plan result.

Request:

```json
{
  "session_id": "session-1",
  "user_id": "user-1",
  "answers": [
    {"question_id": "q1", "selected_keys": ["B"]},
    {"question_id": "q2", "selected_keys": ["A"]}
  ]
}
```

SSE `progress` event:

```json
{
  "event": "progress",
  "data": {
    "depth": 1,
    "message": "Split the goal into milestones.",
    "subtask_count": 3
  }
}
```

SSE final `done` event:

```json
{
  "event": "done",
  "data": {
    "plan": {
      "session_id": "session-1",
      "goal_summary": "Complete the graduation project.",
      "total_tasks": 2,
      "total_estimated_hours": 3.0,
      "tasks": [
        {
          "task_id": "11111111-1111-1111-1111-111111111111",
          "title": "整理需求文档",
          "description": "把核心功能和接口边界整理出来。",
          "estimated_duration_minutes": 60,
          "scheduled_date": "2026-04-30",
          "scheduled_time": "09:00-10:00",
          "order": 1,
          "parent_goal": "Phase 1",
          "checked": false
        }
      ]
    }
  }
}
```

Frontend should keep generated tasks in local state until the user confirms.

### POST `/api/v1/planning/confirm`

Persists selected generated tasks as an active plan.

Request:

```json
{
  "session_id": "session-1",
  "user_id": "user-1",
  "confirmed_task_ids": [
    "11111111-1111-1111-1111-111111111111"
  ]
}
```

Response:

```json
{
  "plan_id": "33333333-3333-3333-3333-333333333333",
  "confirmed_count": 1,
  "message": "Plan saved",
  "plan": {
    "plan_id": "33333333-3333-3333-3333-333333333333",
    "user_id": "user-1",
    "goal": "三个月内完成毕业设计并准备答辩",
    "goal_summary": "Complete the graduation project.",
    "status": "active",
    "total_tasks": 1,
    "total_estimated_hours": 1.0,
    "source_session_id": "session-1",
    "created_at": "2026-04-30T10:00:00",
    "updated_at": "2026-04-30T10:00:00",
    "tasks": []
  }
}
```

### GET `/api/v1/planning/users/{user_id}/plans`

Lists plans for a user.

Query params:

| Param | Type | Default |
|---|---:|---:|
| `limit` | number | `20` |
| `offset` | number | `0` |

Response:

```json
{
  "items": [
    {
      "plan_id": "33333333-3333-3333-3333-333333333333",
      "user_id": "user-1",
      "goal": "三个月内完成毕业设计并准备答辩",
      "goal_summary": "Complete the graduation project.",
      "status": "active",
      "total_tasks": 10,
      "total_estimated_hours": 18.5,
      "source_session_id": "session-1",
      "created_at": "2026-04-30T10:00:00",
      "updated_at": "2026-04-30T10:00:00"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### GET `/api/v1/planning/users/{user_id}/active-plan`

Returns the latest active plan for a user, or `null` if no active plan exists.

Response:

```json
{
  "plan_id": "33333333-3333-3333-3333-333333333333",
  "user_id": "user-1",
  "goal": "三个月内完成毕业设计并准备答辩",
  "goal_summary": "Complete the graduation project.",
  "status": "active",
  "total_tasks": 10,
  "total_estimated_hours": 18.5,
  "source_session_id": "session-1",
  "created_at": "2026-04-30T10:00:00",
  "updated_at": "2026-04-30T10:00:00",
  "tasks": []
}
```

### GET `/api/v1/planning/plans/{plan_id}`

Returns full persisted plan detail.

Response shape is `PersistedPlanResponse`, same as `active-plan`.

### PATCH `/api/v1/planning/tasks/{task_id}`

Updates task checked/status state.

Request:

```json
{
  "checked": true
}
```

Alternative:

```json
{
  "status": "completed"
}
```

Supported status values:

- `pending`
- `in_progress`
- `completed`
- `failed`
- `cancelled`

Response:

```json
{
  "message": "Task updated",
  "task": {
    "task_id": "11111111-1111-1111-1111-111111111111",
    "plan_id": "33333333-3333-3333-3333-333333333333",
    "title": "整理需求文档",
    "description": "把核心功能和接口边界整理出来。",
    "status": "completed",
    "estimated_duration_minutes": 60,
    "scheduled_date": "2026-04-30",
    "scheduled_time": "09:00-10:00",
    "order": 1,
    "parent_goal": "Phase 1",
    "checked": true,
    "created_at": "2026-04-30T10:00:00",
    "updated_at": "2026-04-30T11:00:00"
  }
}
```

### DELETE `/api/v1/planning/plans/{plan_id}`

Deletes a plan and its tasks.

Response:

```json
{
  "message": "Plan deleted",
  "plan_id": "33333333-3333-3333-3333-333333333333"
}
```

## Legacy Stream Endpoint

### GET `/streams/chat?user_input=...`

Registered for compatibility. It streams the same companion chat frame shape, but it always uses `default_user`.

Frontend should prefer `POST /api/v1/chat/stream` because it supports explicit `user_id` and `mode`.

## Error Response

Non-SSE JSON errors from normal HTTP endpoints use:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "No valid confirmed tasks were provided",
  "details": null,
  "request_id": "...",
  "recoverable": false
}
```

FastAPI validation errors may still use FastAPI's default `422` validation shape.

## Frontend SSE Helper

```ts
async function consumeSSE(response: Response, onFrame: (frame: SSEFrame) => void) {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const line = part.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      onFrame(JSON.parse(line.slice(6)));
    }
  }
}
```

## Frontend Mode Routing

Suggested frontend behavior for the shared chat window:

- `mode="companion"`: call `POST /api/v1/chat/stream`.
- `mode="planning"`:
  - if starting a new goal, call `POST /api/v1/planning/initialize`;
  - after questions are answered, call `POST /api/v1/planning/stream`;
  - after user chooses tasks, call `POST /api/v1/planning/confirm`.
- proactive message: call `POST /api/v1/companion/proactive/stream` from scheduler or UI trigger.
