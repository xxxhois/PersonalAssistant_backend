import asyncio
from src.infra.db.repository import SQLTaskRepository
from src.infra.cache.chroma_client import ChromaClient

class OutboxWorker:
    """
    Outbox Worker 架构约束
    消费逻辑独立于 FastAPI 进程。严禁在 lifespan 或 background_tasks 中实现核心同步逻辑。
    严禁在 Worker 中调用 LLM 或外部 HTTP API，仅负责 PG → Chroma 的确定性数据搬运。
    """
    def __init__(self, db_repo: SQLTaskRepository, chroma_client: ChromaClient) -> None:
        self.db = db_repo
        self.chroma = chroma_client

    async def run(self) -> None:
        """
        必须使用 SELECT ... FOR UPDATE SKIP LOCKED 实现安全批量消费
        重试策略：指数退避 (1s → 2s → 4s → 8s → 16s)，5 次失败转死信表
        """
        while True:
            # 消费逻辑
            await asyncio.sleep(1)
