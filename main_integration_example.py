"""
项目集成示例 - 如何在 main.py 中组装所有组件
展示完整的依赖注入和初始化流程
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ===== 导入所有组件 =====

# 核心 Port 和模型
from src.core.ports.llm_client_port import LLMStreamPort
from src.core.ports.task_port import TaskPort
from src.core.ports.memory_port import MemoryPort

# 基础设施层
from src.infra.llm_adapters.openai_adapter import OpenAIAdapter
from src.adapters.pg_repo import PostgreSQLTaskRepository  # 假设存在
from src.adapters.chroma_adapter import ChromaMemoryAdapter

# 核心 Prompt 层
from src.core.prompts.prompt_builder import PromptBuilder
from src.core.prompts.system_prompts import PersonalityType

# 业务服务层
from src.services.llm_client import LLMClient
from src.services.orchestrator import Orchestrator
from src.services.companion import CompanionService

# API 路由
from src.routers.api_v1 import chat


# ===== 初始化函数 =====

def create_llm_adapter() -> LLMStreamPort:
    """
    创建 LLM 适配器
    目前使用 OpenAI，可轻松切换到其他实现（Claude、LLaMA 等）
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    
    return OpenAIAdapter(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL"),  # 支持自定义端点
        model=os.getenv("OPENAI_MODEL", "gpt-4o")
    )


def create_task_repository() -> TaskPort:
    """创建任务存储实现"""
    # 假设 PostgreSQL 数据库连接
    db_url = os.getenv("DATABASE_URL", "postgresql://localhost/personal_assistant")
    return PostgreSQLTaskRepository(db_url)


def create_memory_repository() -> MemoryPort:
    """创建混合记忆实现（PG + Chroma）"""
    # 返回实现了 MemoryPort 接口的混合适配器
    return ChromaMemoryAdapter(
        collection_name="personal_assistant",
        persist_directory=os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
    )


def create_orchestrator(
    llm_adapter: LLMStreamPort,
    task_repo: TaskPort,
    memory_repo: MemoryPort
) -> Orchestrator:
    """创建编排层"""
    return Orchestrator(
        llm_port=llm_adapter,
        task_port=task_repo,
        memory_port=memory_repo
    )


def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用
    """
    app = FastAPI(
        title="Personal Assistant API",
        description="AI-powered personal assistant with emotional intelligence",
        version="1.0.0"
    )
    
    # ===== 配置 CORS =====
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # ===== 初始化所有依赖 =====
    print("🔧 初始化依赖...")
    
    # 1. 创建基础设施层
    llm_adapter = create_llm_adapter()
    task_repo = create_task_repository()
    memory_repo = create_memory_repository()
    print("✅ 基础设施初始化完成")
    
    # 2. 创建业务层
    orchestrator = create_orchestrator(llm_adapter, task_repo, memory_repo)
    print("✅ 业务服务初始化完成")
    
    # ===== 注册 API 路由 =====
    print("🛣️  注册 API 路由...")
    
    # 方式 1：使用 dependency override（FastAPI 推荐）
    async def get_orchestrator() -> Orchestrator:
        return orchestrator
    
    app.dependency_overrides[Orchestrator] = get_orchestrator
    
    # 方式 2：直接导入路由（简单场景）
    # 修改 routers/api_v1/chat.py 中的 get_orchestrator() 函数
    app.include_router(chat.router)
    
    print("✅ 路由注册完成")
    
    # ===== 配置生命周期事件 =====
    @app.on_event("startup")
    async def startup():
        """应用启动时的初始化"""
        print("🚀 应用启动中...")
        # 可以在这里进行数据库连接、缓存预热等操作
    
    @app.on_event("shutdown")
    async def shutdown():
        """应用关闭时的清理"""
        print("🛑 应用关闭中...")
        # 可以在这里进行数据库连接关闭、资源释放等操作
    
    # ===== 健康检查端点 =====
    @app.get("/health")
    async def health_check():
        """健康检查端点"""
        return {
            "status": "healthy",
            "version": "1.0.0",
            "components": {
                "llm_adapter": "ok",
                "database": "ok",
                "memory_store": "ok"
            }
        }
    
    # ===== 根端点 =====
    @app.get("/")
    async def root():
        """API 文档"""
        return {
            "message": "Personal Assistant API",
            "docs": "/docs",
            "health": "/health"
        }
    
    return app


# ===== 应用实例 =====
app = create_app()


# ===== 使用示例 =====
if __name__ == "__main__":
    import uvicorn
    
    # 配置
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("DEBUG", "false").lower() == "true"
    
    # 运行
    print(f"🌐 服务器启动在 http://{host}:{port}")
    print(f"📚 API 文档: http://{host}:{port}/docs")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


# ===== 快速测试脚本 =====
"""
# 在终端运行：
python -m backend.main

# 在另一个终端测试 API：

# 1. 检查健康状态
curl -X GET http://localhost:8000/health

# 2. 发送聊天请求（SSE 流）
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"user_message": "请帮我制定今天的工作计划", "user_id": "user_123"}'

# 3. 使用 Python 测试客户端
import httpx
import json

async with httpx.AsyncClient() as client:
    async with client.stream(
        "POST",
        "http://localhost:8000/api/v1/chat/stream",
        json={"user_message": "你好", "user_id": "user_123"}
    ) as response:
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                print(f"[{data['type']}] {data['data']}")
"""
