---
alwaysApply: true
---
# 类型检查与代码质量铁律

1. 所有 Python 文件必须通过 `ruff check/format` 与 `pyright --strict`。禁止提交带 `# type: ignore` 的代码，除非经架构评审并注释原因。
2. 函数签名必须完整标注参数/返回值类型，包括 `async def`、`Generator`/`AsyncIterator`、`Optional`、`Protocol`。
3. 严禁使用裸 `dict`/`list`/`Any` 作为 HTN 状态、SSE 事件、Outbox Payload 的类型。必须使用 Pydantic Model 或 TypedDict/Protocol。
4. AI 生成代码后，必须附带 `pyright` 验证结果。若出现 `reportUnknown*` 或 `reportAttributeAccessIssue`，需补全类型或重构。
5. 测试文件允许适度放宽（`typeCheckingMode = "standard"`），但核心 `src/` 必须 `strict`。

# 异常处理架构铁律

1. 严禁在路由/编排器/Worker 中直接 raise FastAPI HTTPException 或裸抛 openai/asyncio 异常。
2. 所有业务/领域异常必须继承 AppException，使用 ErrorCode 枚举定义 code。
3. 外部捕获器（FastAPI exception_handler / SSE finally）必须统一包装为 ErrorResponse 结构：`{code,message,details,request_id,recoverable}`。
4. recoverable 字段必须显式赋值：网络/限流/临时故障为 True；校验/权限/逻辑死锁为 False。
5. 开发环境 details 可含 traceback，生产环境必须脱敏。若 AI 生成代码暴露 DB 连接串或完整堆栈，立即拒绝。

# SSE 帧定义铁律

1. 严格使用多 Event 类型：token / task_event / progress / error / done / heartbeat。禁止使用 event: message 或纯文本 data。
2. 所有 data 字段必须为合法 JSON。若 LLM 输出含非法字符，需在服务端转义或包装为 {"text":"..."}。
3. 每个事件必须携带 id 字段（格式：{type}_{seq}），用于断线重连与幂等去重。
4. error 事件必须包含 recoverable 布尔值。true 触发自动重试，false 终止流并推送 done。
5. 严禁在 task_event 中混入人格化文本。若 AI 生成代码将口语放入 data.payload，立即拒绝。

# LLM 客户端层架构铁律

1. 业务层（services/orchestrator, parsers, routers）严禁直接 import openai, anthropic, transformers 等 SDK。
2. 所有 LLM 调用必须通过 `core/ports/` 下的 `LLMStreamPort` 接口（建议路径：`core/ports/llm_client_port.py`）。
3. Adapter 必须继承基类，统一处理：重试（指数退避）、超时（默认 30s）、Chunk 拼接、错误降级。
4. 配置驱动：`.env` 定义 `LLM_PROVIDER` 与密钥，由 `infra/` 中的 Provider Router 负责实例化。禁止硬编码。
5. 若需更换模型，仅允许新增 `infra/llm_adapters/xxx_adapter.py` 并注册到 Router，禁止修改已有业务代码。

# Outbox Worker 架构约束

1. 消费逻辑必须独立于 FastAPI 进程。禁止在 lifespan 或 background_tasks 中实现核心同步逻辑。
2. 必须使用 `SELECT ... FOR UPDATE SKIP LOCKED` 或 `pgmq` 实现安全批量消费，严禁无锁全表扫描。
3. 所有 ChromaDB 写入必须幂等：以 `task_id` 为 document id，存在则 `update`，失败则标记 `dead_letter`。
4. 重试策略：指数退避 (1s → 2s → 4s → 8s → 16s)，5 次失败转死信表，禁止无限重试阻塞队列。
5. 严禁在 Worker 中调用 LLM 或外部 HTTP API，仅负责 PG → Chroma 的确定性数据搬运。

# 架构铁律：外部操作隔离规范

1. services/orchestrator.py 只能导入 ports/ 下的接口，严禁 import sqlalchemy, httpx, chromadb, openai 等具体实现。
2. 所有数据库写入必须通过 TaskPort.update_status() 完成，且必须包含 within_transaction 上下文管理器。
3. 工具调用必须封装在 adapters/mcp_client.py 中，返回标准化 ToolExecutionResult(data=None, error=None, retryable=False)。
4. ChromaDB 写入绝对禁止出现在主请求链路。必须通过发布 "task.completed" 事件，由 workers/ 下的 Consumer 异步处理。
5. 若 AI 生成代码时在 Orchestrator 中直接写 await db.session.execute() 或 await client.call()，立即拒绝并要求重构为 Port/Adapter 模式。
