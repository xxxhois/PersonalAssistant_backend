from typing import List, Optional, Dict, Any
from src.core.ports.memory_port import MemoryPort, MemoryChunk
from src.schemas.htn import JsonValue

class ChromaAdapter(MemoryPort):
    """
    ChromaDB 记忆适配器 (ChromaAdapter)
    遵循架构约束：ChromaDB 仅为检索加速缓存，PG 为真相源。
    所有写入必须是幂等的。
    """
    def __init__(self, host: str, port: int, collection_name: str = "memories") -> None:
        self.host = host
        self.port = port
        self.collection_name = collection_name
        # 实际实现需初始化 chromadb.HttpClient

    async def query_context(
        self, 
        query: str, 
        limit: int = 5, 
        filters: Optional[Dict[str, Any]] = None
    ) -> List[MemoryChunk]:
        """检索长期记忆上下文"""
        # 占位实现
        return []

    async def store(self, chunk: MemoryChunk) -> None:
        """
        存储单条记忆 (幂等 upsert)
        遵循架构铁律：以 task_id 为 document id，存在则 update
        """
        # 占位实现
        ...

    async def batch_store(self, chunks: List[MemoryChunk]) -> None:
        """批量存储"""
        # 占位实现
        ...
