# 项目架构指南与代码调用流程

## 📋 项目完整结构（重新组织后）

```
backend/
├── src/
│   ├── core/                           # 核心层（业务无关的抽象）
│   │   ├── ports/                      # 接口定义（依赖倒置）
│   │   │   ├── llm_client_port.py      # LLM 流式调用接口 ✅ 不改
│   │   │   ├── task_port.py            # 任务存储接口 ✅ 不改
│   │   │   ├── memory_port.py          # 记忆查询接口 ✅ 不改
│   │   │   └── tool_port.py            # 工具调用接口 ✅ 不改
│   │   ├── prompts/                    # 🆕 Prompt 管理层（新增）
│   │   │   ├── __init__.py
│   │   │   ├── system_prompts.py       # 系统级 Prompt 模板
│   │   │   ├── dynamic_prompts.py      # 动态 Prompt 生成
│   │   │   └── prompt_builder.py       # Prompt 构建器（核心编排）
│   │   ├── exceptions/
│   │   │   └── app_exception.py        # 统一异常类 ✅ 不改
│   │   ├── models/                     # 业务模型
│   │   └── security/
│   │
│   ├── infra/                          # 基础设施层（技术实现）
│   │   ├── llm_adapters/               # LLM 适配器（SDK 集成）
│   │   │   ├── base_adapter.py         # 基类实现 ✅ 不改
│   │   │   ├── openai_adapter.py       # OpenAI 具体实现 ✅ 不改
│   │   │   ├── claude_adapter.py       # 🆕 Claude 适配（可选）
│   │   │   └── mock_adapter.py         # 🆕 Mock 适配（测试）
│   │   ├── cache/                      # 缓存实现
│   │   ├── db/                         # 数据库实现
│   │   └── llm_router.py               # 🆕 LLM 路由选择器
│   │
│   ├── services/                       # 业务服务层
│   │   ├── llm_client.py               # 🆕 LLM 客户端包装（Prompt 构建 + 调用）
│   │   ├── companion.py                # 人格化陪伴逻辑（可调用 llm_client）
│   │   ├── orchestrator.py             # 编排层（集成记忆 + Prompt + LLM）
│   │   └── task_manager.py             # 🆕 任务管理器
│   │
│   ├── routers/                        # API 路由层
│   │   └── api_v1/
│   │       ├── __init__.py
│   │       ├── chat.py                 # 🆕 聊天 API 端点
│   │       ├── dependencies.py         # 🆕 依赖注入配置
│   │       └── tasks.py                # 🆕 任务管理 API
│   │
│   ├── parsers/
│   │   └── shadow_parser.py            # Chunk 解析器 ✅ 不改
│   │
│   ├── schemas/                        # 数据模型
│   │   ├── common.py
│   │   ├── htn.py
│   │   └── sse.py                      # SSE 事件模型 ✅ 不改
│   │
│   └── adapters/
│       ├── chroma_adapter.py           # 向量库适配 ✅ 不改
│       └── pg_repo.py                  # PostgreSQL 适配 ✅ 不改
│
├── tests/
│   ├── unit/
│   │   └── test_shadow_parser.py       # ✅ 不改
│   └── integration/
│       ├── test_orchestrator.py        # 应更新测试
│       └── test_llm_client.py          # 🆕 新增测试
│
├── docker-compose.yml                  # ✅ 不改
├── pyproject.toml                      # ✅ 不改
├── main.py                             # 应添加 API 路由注册
└── README.md
```

---

## 🔄 调用流程图

### 完整的数据流

```
客户端请求
    ↓
HTTP POST /api/v1/chat/stream
    ↓
[routers/api_v1/chat.py]
  └─ 解析请求参数 (user_id, user_message)
    ↓
[Orchestrator.chat_stream()]
  ├─ 1️⃣ 构建用户上下文 (_build_user_context)
  │    └─ 查询用户信息、偏好、历史
  ├─ 2️⃣ 检索记忆上下文 (_retrieve_memory_context)
  │    └─ 调用 memory_port.query_context()
  ├─ 3️⃣ 分析用户意图 (_analyze_intent)
  │    └─ 调用 llm_client.analyze_intent()
  │        └─ 构建分析 LLMRequest → 调用 llm_adapter.stream()
  ├─ 4️⃣ 主流程：调用 llm_client.chat_stream()
  │    ↓
  │    [LLMClient.chat_stream()]
  │    └─ 调用 prompt_builder.build_chat_request()
  │        ↓
  │        [PromptBuilder.build_chat_request()]
  │        ├─ 获取系统提示 (system_prompts.py)
  │        ├─ 构建用户上下文摘要
  │        ├─ 组装最终 Prompt
  │        └─ 创建 LLMRequest 对象
  │    └─ 流式调用 llm_adapter.stream(llm_request)
  │        ↓
  │        [openai_adapter.stream()]
  │        ├─ 重试逻辑（指数退避）
  │        ├─ 超时处理（30s）
  │        ├─ 错误降级
  │        └─ 逐 Token 返回
  ├─ 5️⃣ 解析响应 (shadow_parser.feed())
  │    └─ 提取任务、标记等
  ├─ 6️⃣ 生成 SSE 事件
  │    └─ 每个 event 转换为 SSEFrame
  └─ 7️⃣ 发送完成 & 错误处理
    ↓
SSE 流返回给客户端
```

---

## 🎯 核心问题解答

### 1️⃣ API 调用代码应该在哪里写？

**答案：在 `routers/api_v1/chat.py` 中**

```python
@router.post("/api/v1/chat/stream")
async def chat_stream(
    user_message: str,
    user_id: str = "default_user",
    orchestrator: Orchestrator = Depends(get_orchestrator)
):
    """
    入口点：接收 HTTP 请求 → 调用 Orchestrator → 返回 SSE 流
    """
    request_id = str(uuid.uuid4())
    
    async def event_generator():
        async for frame in orchestrator.chat_stream(
            user_id=user_id,
            user_input=user_message,
            request_id=request_id
        ):
            yield f"data: {json.dumps(frame.to_dict())}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

### 2️⃣ Prompt 应该在哪里写？

**答案：分三个层级**

#### 📍 系统 Prompt（系统指令、人格化）
位置：`core/prompts/system_prompts.py`

```python
class SystemPrompts:
    @staticmethod
    def get_personality_instruction(personality: PersonalityType) -> str:
        # 返回人格化系统提示
        return "You are a balanced personal assistant..."
    
    @staticmethod
    def get_behavior_constraints() -> str:
        # 返回行为约束
        return "NEVER pretend to have emotions..."
```

**何时写：** 
- 定义助手的核心人格和行为规范
- 需要 A/B 测试不同的指令风格

#### 📍 动态 Prompt（上下文相关）
位置：`core/prompts/dynamic_prompts.py`

```python
class DynamicPromptBuilder:
    @staticmethod
    def build_user_context_summary(context: UserContext, memory_chunks: List[str]) -> str:
        # 根据用户信息和历史动态生成上下文
        summary = f"User: {context.user_name}\nEmotional state: {context.emotional_state}"
        return summary
```

**何时写：**
- 需要根据运行时信息（用户状态、历史记录）调整 Prompt
- 实现个性化、上下文感知的对话

#### 📍 Prompt 组装（编排）
位置：`core/prompts/prompt_builder.py`

```python
class PromptBuilder:
    def build_chat_request(
        self,
        user_message: str,
        user_context: UserContext,
        memory_chunks: Optional[List[str]] = None,
        task_type: str = "general",
    ) -> LLMRequest:
        # 将系统 Prompt + 动态上下文 + 用户消息组装成完整的 LLMRequest
        system_prompt = SYSTEM_PROMPT_TEMPLATES[personality]
        context_summary = DynamicPromptBuilder.build_user_context_summary(...)
        return LLMRequest(
            prompt=f"{context_summary}\n\n{user_message}",
            system_prompt=system_prompt
        )
```

**何时写：**
- 调用 LLM 时，通过此类创建所有 LLMRequest
- 遵循架构铁律：所有 LLMRequest 必须通过此类创建

---

### 3️⃣ `/core/llm_client_port.py` 和 `openai_adapter.py` 重复吗？

**答案：不重复！这是标准的六边形架构**

| 组件 | 位置 | 职责 | 是否重复？ |
|------|------|------|-----------|
| **LLMStreamPort** | `core/ports/llm_client_port.py` | 接口定义（"应该怎么调用"） | ❌ 独特 |
| **LLMRequest** | `core/ports/llm_client_port.py` | 请求模型 | ❌ 独特 |
| **OpenAIAdapter** | `infra/llm_adapters/openai_adapter.py` | 具体实现（"怎么真正调用 OpenAI"） | ❌ 独特 |

**关系图：**
```
LLMStreamPort (接口)
       ↑
       │ 实现
       │
OpenAIAdapter (具体实现)
    │
    ├─ 调用 openai.ChatCompletion
    ├─ 处理重试逻辑
    ├─ 处理超时 (30s)
    └─ 处理错误降级
```

**为什么这样设计：**
- 业务层依赖 **接口** (`LLMStreamPort`)，不依赖具体实现
- 可以轻松切换到 Claude、LLaMA、自定义模型，只需新增 Adapter
- 测试时可用 MockAdapter 替代真实的 OpenAI

---

## 🔌 依赖注入流程（Orchestrator 如何获得 LLM 适配器）

```python
# 在主应用启动时（main.py 或 dependencies.py）

from src.infra.llm_adapters.openai_adapter import OpenAIAdapter
from src.services.orchestrator import Orchestrator
import os

# 步骤 1：创建 OpenAI 适配器
openai_adapter = OpenAIAdapter(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o"
)

# 步骤 2：创建 Orchestrator（通过 DI 注入）
orchestrator = Orchestrator(
    llm_port=openai_adapter,  # 注入适配器
    task_port=pg_task_repo,
    memory_port=hybrid_memory_repo
)

# 步骤 3：在路由中使用
@app.post("/api/v1/chat/stream")
async def chat_stream(...):
    async for frame in orchestrator.chat_stream(...):
        ...
```

---

## 📚 代码调用位置总结表

| 需求 | 位置 | 示例 |
|------|------|------|
| 定义人格和系统指令 | `core/prompts/system_prompts.py` | `SystemPrompts.get_personality_instruction()` |
| 构建动态上下文 | `core/prompts/dynamic_prompts.py` | `DynamicPromptBuilder.build_user_context_summary()` |
| 组装完整 Prompt | `core/prompts/prompt_builder.py` | `PromptBuilder.build_chat_request()` |
| 调用 LLM（含 Prompt） | `services/llm_client.py` | `LLMClient.chat_stream()` |
| 编排完整对话流 | `services/orchestrator.py` | `Orchestrator.chat_stream()` |
| 处理 HTTP 请求 | `routers/api_v1/chat.py` | `@router.post("/api/v1/chat/stream")` |
| 实现 OpenAI 细节 | `infra/llm_adapters/openai_adapter.py` | `OpenAIAdapter.stream()` |
| 分析情感/意图 | `services/llm_client.py` | `LLMClient.analyze_emotion/intent()` |
| 人格化陪伴逻辑 | `services/companion.py` | 可调用 `llm_client` 来补充对话 |

---

## 🚀 快速开始：如何添加新功能？

### 场景 1：修改系统 Prompt

**不需要改 openai_adapter.py！** 只需改 `system_prompts.py`：

```python
# src/core/prompts/system_prompts.py
@staticmethod
def get_personality_instruction(personality: PersonalityType = PersonalityType.BALANCED) -> str:
    return "Your new prompt here..."
```

### 场景 2：添加新的分析功能

在 `llm_client.py` 中添加新方法：

```python
# src/services/llm_client.py
async def analyze_priority(self, text: str) -> dict:
    """分析任务优先级"""
    llm_request = self.prompt_builder.build_system_analysis_request(
        analysis_target=text,
        analysis_type="priority"  # 在 prompt_builder.py 中定义规则
    )
    ...
```

### 场景 3：切换到 Claude

无需改任何业务代码，只需新增 Adapter：

```python
# src/infra/llm_adapters/claude_adapter.py
class ClaudeAdapter(BaseLLMAdapter):
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        # 调用 Claude SDK
        ...

# 在 main.py 中切换
orchestrator = Orchestrator(
    llm_port=ClaudeAdapter(...),  # 改成 Claude
    ...
)
```

---

## 🏛️ 架构铁律总结

1. **业务层严禁直接 import openai SDK**
   - ✅ 应该用：`from src.core.ports.llm_client_port import LLMStreamPort`
   - ❌ 禁止：`import openai`

2. **所有 LLMRequest 必须通过 PromptBuilder 创建**
   - ✅ 应该用：`prompt_builder.build_chat_request()`
   - ❌ 禁止：`LLMRequest(prompt="...")`

3. **所有 Prompt 集中在 `core/prompts/` 中管理**
   - 便于 A/B 测试、版本控制
   - 便于多语言支持

4. **Adapter 负责重试、超时、错误处理**
   - 业务层无需关心这些细节

5. **错误必须转为统一的 AppException**
   - 包含错误码和可恢复性标志

---

## 📖 后续优化建议

1. **Prompt 版本管理**
   - 考虑用 Git 或数据库保存 Prompt 版本
   - 实现 Prompt 灰度发布

2. **Token 计数和成本优化**
   - 添加 Token 计数到 LLMRequest
   - 定期审查和优化 Prompt

3. **Prompt 工程最佳实践**
   - 定期对 Prompt 进行 A/B 测试
   - 收集用户反馈来优化指令

4. **缓存 Prompt**
   - 相同 Prompt 的重复请求可以缓存
   - 减少 API 调用和成本

