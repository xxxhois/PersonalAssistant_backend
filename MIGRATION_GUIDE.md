# 项目重新组织 - 完整变更总结

**时间**: 2026-04-20  
**状态**: 实施方案已准备  
**影响范围**: Prompt 管理、LLM 调用、API 路由层

---

## 🎯 核心问题与解决方案

### 问题 1: Prompt 管理分散
**症状**: Orchestrator 和 CompanionService 中的 Prompt 硬编码  
**解决方案**: 创建集中的 `core/prompts/` 层

✅ **新增文件**:
- `core/prompts/__init__.py` - 模块入口
- `core/prompts/system_prompts.py` - 系统级 Prompt（人格、约束）
- `core/prompts/dynamic_prompts.py` - 动态 Prompt 生成（上下文）
- `core/prompts/prompt_builder.py` - Prompt 编排器（核心）

### 问题 2: LLM 调用逻辑无处可写
**症状**: 业务层无法清晰地调用 LLM，Prompt 构建和 LLM 调用混在 Orchestrator 中  
**解决方案**: 创建 `LLMClient` 包装层

✅ **新增文件**:
- `services/llm_client.py` - LLM 客户端包装（处理 Prompt 构建和调用）

### 问题 3: API 路由层缺失
**症状**: `/routers/api_v1/` 目录为空，没有 HTTP 端点  
**解决方案**: 实现 API 路由层

✅ **新增文件**:
- `routers/api_v1/chat.py` - 聊天 API 端点
- `routers/api_v1/dependencies.py` - 依赖注入配置

### 问题 4: 不清楚 LLMStreamPort 和 OpenAIAdapter 的区别
**症状**: 担心两者重复  
**结论**: ✅ **不重复！** 这是标准的六边形架构
- `LLMStreamPort` = 接口定义（Port）
- `OpenAIAdapter` = 具体实现（Adapter）

---

## 📁 完整的文件变更列表

### 新增文件（8 个）

| 文件路径 | 描述 | 优先级 |
|---------|------|--------|
| `src/core/prompts/__init__.py` | Prompt 模块入口 | 🔴 必需 |
| `src/core/prompts/system_prompts.py` | 系统 Prompt 库 | 🔴 必需 |
| `src/core/prompts/dynamic_prompts.py` | 动态 Prompt 生成 | 🔴 必需 |
| `src/core/prompts/prompt_builder.py` | Prompt 编排器 | 🔴 必需 |
| `src/services/llm_client.py` | LLM 客户端包装 | 🔴 必需 |
| `src/routers/api_v1/chat.py` | 聊天 API 端点 | 🔴 必需 |
| `main_integration_example.py` | 集成示例 | 🟡 参考 |
| `QUICK_REFERENCE.py` | 快速参考指南 | 🟡 参考 |

### 修改文件（1 个）

| 文件路径 | 修改内容 | 详情 |
|---------|---------|------|
| `src/services/orchestrator.py` | 集成 LLMClient 和 PromptBuilder | 添加意图分析、简化 Prompt 构建 |

### 文档文件（2 个）

| 文件路径 | 描述 |
|---------|------|
| `ARCHITECTURE.md` | 完整的架构指南和调用流程 |
| `QUICK_REFERENCE.py` | 常见问题快速参考 |

### 无需修改的文件

- ✅ `src/core/ports/llm_client_port.py` - 接口定义
- ✅ `src/infra/llm_adapters/base_adapter.py` - 基类实现
- ✅ `src/infra/llm_adapters/openai_adapter.py` - OpenAI 适配
- ✅ `src/services/companion.py` - 陪伴服务
- ✅ `src/parsers/shadow_parser.py` - 解析器
- ✅ `src/adapters/chroma_adapter.py` - 向量库
- ✅ `src/adapters/pg_repo.py` - 数据库适配

---

## 🔄 调用链路变化

### 改进前
```
HTTP Request
  → Orchestrator.chat_stream()
    → 硬编码 Prompt
    → self.llm.stream(llm_request)
      → OpenAIAdapter.stream()
```

### 改进后
```
HTTP Request
  → routers/api_v1/chat.py (@router.post)
    → Orchestrator.chat_stream()
      ├─ 构建用户上下文
      ├─ 检索记忆
      ├─ 分析意图
      └─ llm_client.chat_stream()
        → PromptBuilder.build_chat_request()
          ├─ SystemPrompts.get_XXX()
          ├─ DynamicPromptBuilder.build_XXX()
          └─ 返回 LLMRequest
        → llm_adapter.stream(llm_request)
          → OpenAIAdapter.stream()
```

---

## 🎓 三个关键概念

### 1. Prompt 的三层结构

```
┌─────────────────────────────────┐
│ system_prompts.py               │ 系统级（不变）
│ - 人格指令                      │ 一次初始化
│ - 行为约束                      │
│ - 任务格式                      │
└─────────────────────────────────┘
             ↓ 组装
┌─────────────────────────────────┐
│ dynamic_prompts.py              │ 动态（每次请求）
│ - 用户上下文摘要                │ 运行时生成
│ - 记忆检索结果                  │
│ - 任务特定指令                  │
└─────────────────────────────────┘
             ↓ 编排
┌─────────────────────────────────┐
│ prompt_builder.py               │ 最终组件
│ - 组装完整 LLMRequest           │ 返回给 LLM
│ - 参数验证                      │
│ - 特殊分析请求                  │
└─────────────────────────────────┘
```

### 2. 三层 Service 架构

```
┌──────────────────────────────────┐
│ routers/api_v1/chat.py           │ 表现层（HTTP）
│ - HTTP 请求/响应                │
│ - 参数验证                       │
└──────────────────────────────────┘
             ↓
┌──────────────────────────────────┐
│ Orchestrator                     │ 编排层
│ - 记忆检索                       │
│ - 意图分析                       │
│ - 调用 llm_client.chat_stream()  │
└──────────────────────────────────┘
             ↓
┌──────────────────────────────────┐
│ LLMClient                        │ 业务逻辑层
│ - Prompt 构建                    │
│ - LLM 调用编排                   │
│ - 特殊分析（情感、意图等）      │
└──────────────────────────────────┘
             ↓
┌──────────────────────────────────┐
│ OpenAIAdapter                    │ 基础设施层
│ - SDK 封装                       │
│ - 重试、超时                     │
│ - 错误处理                       │
└──────────────────────────────────┘
```

### 3. 依赖倒置（Ports & Adapters）

```
业务层依赖接口，不依赖具体实现

┌─────────────────────────────────┐
│ Orchestrator/LLMClient          │ 业务层
│ 依赖：LLMStreamPort (接口)     │
└─────────────────────────────────┘
             ↑
    ┌────────┴────────┬────────────────┐
    │                 │                │
┌───────────────┐ ┌──────────┐ ┌────────────┐
│ OpenAIAdapter │ │ Claude   │ │ MockAdapter│
│               │ │ Adapter  │ │            │
│ (实现)        │ │(实现)    │ │ (测试)    │
└───────────────┘ └──────────┘ └────────────┘

优点：
- 可轻松切换实现
- 便于单元测试
- 符合 SOLID 原则
```

---

## 🚀 快速集成步骤

### Step 1: 创建新文件（8 个）
复制所有新增文件到对应目录

### Step 2: 修改 Orchestrator
更新 `src/services/orchestrator.py`：
- 导入 `LLMClient` 和 `PromptBuilder`
- 在 `__init__` 中初始化它们
- 使用 `llm_client.chat_stream()` 替代直接调用

### Step 3: 注册 API 路由
在 `main.py` 中：
```python
from src.routers.api_v1 import chat
app.include_router(chat.router)
```

### Step 4: 配置依赖注入
修改 `main.py` 或创建 `dependencies.py`：
```python
from src.services.orchestrator import Orchestrator

async def get_orchestrator() -> Orchestrator:
    return orchestrator_instance

app.dependency_overrides[Orchestrator] = get_orchestrator
```

### Step 5: 测试
```bash
# 启动服务
python main.py

# 测试 API
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -d '{"user_message": "你好", "user_id": "test_user"}'
```

---

## 📊 优势对比表

| 方面 | 改进前 | 改进后 |
|------|--------|--------|
| **Prompt 管理** | 分散在多个文件 | ✅ 集中在 `core/prompts/` |
| **调用路径** | 不清晰 | ✅ 明确的层级关系 |
| **API 端点** | 不存在 | ✅ 完整的 REST API |
| **可维护性** | 低（Prompt 硬编码） | ✅ 高（可配置化） |
| **可扩展性** | 低（添加新功能困难） | ✅ 高（标准接口） |
| **可测试性** | 低（依赖耦合） | ✅ 高（依赖倒置） |
| **文档** | 无 | ✅ 完整的架构和快速参考 |

---

## ⚠️ 注意事项

1. **向后兼容性**
   - 修改后的 Orchestrator 接口保持不变
   - 现有的单元测试需要更新以使用新的组件

2. **环境变量**
   确保设置以下变量：
   ```bash
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4o  # 可选
   DATABASE_URL=postgresql://...
   CHROMA_PERSIST_DIR=./chroma_data
   ```

3. **依赖安装**
   确保已安装所有必要的包：
   ```bash
   pip install fastapi uvicorn openai pydantic
   ```

4. **数据库迁移**
   如果修改了 TaskPort 或 MemoryPort：
   ```bash
   # 运行数据库迁移（如果需要）
   alembic upgrade head
   ```

---

## 📚 文档导航

| 文档 | 用途 | 读者 |
|------|------|------|
| `ARCHITECTURE.md` | 完整架构理解 | 架构师、技术负责人 |
| `QUICK_REFERENCE.py` | 常见问题快速查找 | 开发者 |
| `main_integration_example.py` | 集成示例 | 实施者 |
| `README.md` | 项目概述 | 所有人 |

---

## 🎉 总结

这次重组实现了以下目标：

✅ **集中管理 Prompt**  
✅ **清晰的调用链路**  
✅ **完整的 API 层**  
✅ **标准的架构模式**  
✅ **易于扩展和维护**  

**下一步**: 选择合适的时机进行集成测试和上线。

---

## 📞 常见问题

**Q: 需要立即修改现有代码吗？**  
A: 不需要。新增的组件可以逐步集成。建议先在测试环境验证。

**Q: 现有的 openai_adapter.py 需要改吗？**  
A: 不需要。它的职责没有变化，仍然负责 OpenAI SDK 的具体实现。

**Q: 如何从 OpenAI 切换到其他 LLM？**  
A: 创建新的 Adapter（如 ClaudeAdapter），在 main.py 中修改一行配置。

**Q: 所有测试都需要重写吗？**  
A: 只需更新与 Orchestrator 相关的测试，使用新的组件初始化方式。

---

**作者**: AI Assistant  
**最后更新**: 2026-04-20
