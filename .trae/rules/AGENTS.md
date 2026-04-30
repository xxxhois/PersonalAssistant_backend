---
alwaysApply: false
---
# 🤖 Project Context for AI Agents

## 阅读顺序与优先级
- 本文件是后端 Agent 的唯一入口与默认约束来源
- 当本文件与代码实现冲突：以代码为准，并在本文件补充“已实现的事实”与后续收敛计划
- 当不同约束之间冲突：按「架构约定」>「技术栈约束」>「开发守则」优先级执行
- 详细铁律位于 `docs/agents/do-dont.md`；当同一主题出现更细粒度且可执行的约束时，以该文件为准

## 项目定位
以“人格化 Agent”为核心的个人助手后端，面向自律与成长的任务管理与日常陪伴。核心能力围绕两条主线构建：情感化陪伴与目标规划执行，并通过流式结构化输出与异构记忆实现可持续迭代。

## 产品目标与范围
- 目标用户: 需要自律管理与长期成长规划的个人用户
- 核心体验: 可对话、可记忆、可拆解、可执行、可追踪
- 输出形态: 对话 + SSE 流式事件（用于 UI 渐进渲染、任务勾选、状态跟踪）

## 核心功能一：人格化情感陪伴
- 人格模型: 以心智状态机驱动对话风格与回应策略（默认参考大五人格维度与情绪状态），通过 Prompt Engineering 约束语气、同理心与边界
- 长期记忆: 必须通过 RAG 机制形成对用户的长期偏好/重要事件/目标上下文记忆；PG 为真相源，向量库仅为检索加速缓存
- 陪伴触达: 白天定时触发（默认每 2 小时一次）向用户推送一条“情感化陪伴”或“与近期目标相关的知识/建议”，触达内容必须可追溯到记忆或目标上下文

## 核心功能二：宏大目标原子化拆分与结构化任务
- 目标拆分: 将用户的宏大目标分解为可执行的原子任务与子任务树，并维护依赖关系、完成条件与验收标准
- 任务结构化: 通过 MCP Tool 将任务输出为可勾选的结构化清单（checkbox 语义），并在流式输出中持续增量更新任务状态
- 约束扩展: 逐步纳入时间限制、用户可投入时间/精力与资源约束，形成可执行的计划与编排策略（例如优先级、节奏、重排、延期与回滚）

## 关键非目标（边界）
- 不做“无需用户确认的外部副作用执行”：编排层不直接执行不受控外部动作（例如任意网络写操作/第三方账号操作）
- 不把非结构化口语文本混入结构化通道：结构化事件用于机器处理，陪伴文本用于展示，二者严格分流（详见 `docs/agents/do-dont.md`）

## 技术栈约束
- 语言: Python 3.11+ (严格类型注解)
- 框架: FastAPI (异步优先) + Uvicorn
- 数据: PostgreSQL (pgvector) + ChromaDB
- 通信: SSE (Server-Sent Events) + MCP Protocol
- 校验: Pydantic V2 (所有 LLM 输出必须经 schema 验证)
- ⛔ 禁止: LangChain, LlamaIndex, 同步 requests, 全局变量存状态

## 架构约定
- 分层: `core/`(领域模型) → `services/`(业务逻辑) → `routers/`(API) → `parsers/`(流解析) → `infra/`(DB/LLM客户端)
- HTN 实现: LLM 模拟分解，非符号规划器；后端负责编排（状态跟踪、步骤调度、重试/回滚策略），不在编排层直接执行不受控外部副作用
- HTN 契约: 混合模式；核心稳定字段用于对外 API，扩展字段仅用于内部编排/实验演进；所有结构以 `schemas/htn.py` 为单一校验源，API 可在路由层做收敛/映射
- ShadowParser: 标记块格式 `<!--TASK_START-->{"type":"..."}<!--TASK_END-->`；真相源仅为标记块内 JSON，块外文本仅用于展示与日志，不参与业务决策
- SSE 帧: 多 event 类型（`token`/`task_event`/`progress`/`error`/`done`/`heartbeat`）；每帧 data 为 JSON 且携带 `request_id`、单调递增 `seq`、幂等 `id={type}_{seq}`；`error` 必含 `recoverable: bool`
- LLM 客户端: 采用 Port/Adapter；业务层只依赖 `core/ports/` 下的接口与 Pydantic 输出模型，不直接依赖具体 SDK；`infra/` 负责多提供商适配与路由
- 记忆同步: PG 为唯一真相源，ChromaDB 为异步只读缓存；Outbox 事件由独立 worker 进程消费，API 请求路径不直接写入/查询 ChromaDB
- 错误模型: 业务/领域异常必须继承 `AppException` 且使用 `ErrorCode` 强类型枚举定义语义；统一错误包 `ErrorResponse={code,message,details,request_id,recoverable}`，由异常处理器集中映射 HTTP 状态码

## 开发守则
1. 所有 async I/O 必须显式设置超时，并处理 `TimeoutError`, `ConnectionError`, `ValidationError`
2. 流式路由禁止执行阻塞操作与长耗时 await；通过 `asyncio.Queue` 或 async generator 逐帧推送，保证可持续输出 `heartbeat`
3. 任何 LLM 输出进入业务前必须通过 Pydantic V2 schema 校验；校验失败走统一错误包并可回传可诊断的 `details`
4. 每次改动 Schema、SSE 帧结构、ShadowParser 状态机、ErrorCode 语义前，先在本文件补齐“契约变更点”并同步更新对应代码
5. 代码质量工具链固定为 `ruff`（lint/format）+ `pyright`（类型检查）；新增代码必须通过类型检查，禁止用 `Any` 逃逸关键路径
