from typing import Protocol, List, Optional, Dict, Any
from pydantic import BaseModel, Field
from src.schemas.htn import JsonValue

class MemoryChunk(BaseModel):
    """
    记忆块模型 (MemoryChunk)
    用于 RAG 上下文
    """
    content: str = Field(..., description="记忆文本内容")
    metadata: Dict[str, JsonValue] = Field(default_factory=dict, description="记忆元数据")
    score: float = Field(default=0.0, description="相似度评分")

class MemoryPort(Protocol):
    """
    异构记忆访问接口 (MemoryPort)
    遵循架构铁律：PG 为真相源，向量库仅为检索加速缓存
    """
    async def query_context(
        self, 
        query: str, 
        limit: int = 5, 
        filters: Optional[Dict[str, Any]] = None
    ) -> List[MemoryChunk]:
        """检索长期记忆上下文"""
        ...

    async def store(self, chunk: MemoryChunk) -> None:
        """存储单条记忆（必须保证 PG 与 Chroma 同步）"""
        ...

    async def batch_store(self, chunks: List[MemoryChunk]) -> None:
        """批量存储"""
        ...
