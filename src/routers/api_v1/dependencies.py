import os

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.chroma_adapter import ChromaAdapter
from src.adapters.in_memory_memory_repo import InMemoryMemoryRepository
from src.adapters.in_memory_task_repo import InMemoryTaskRepository
from src.adapters.pg_repo import PGBackedMemoryRepository, PGMemoryRepository, PGTaskRepository
from src.core.ports.memory_port import MemoryPort
from src.core.prompts.prompt_builder import PromptBuilder
from src.infra.db.session import get_db_session
from src.infra.llm_router import llm_router
from src.services.llm_client import LLMClient
from src.services.orchestrator import Orchestrator
from src.services.planning import PlanningService, PlanningSessionStore
from src.services.proactive import ProactiveCompanionService

_memory_repo = InMemoryMemoryRepository()
_chat_task_repo = InMemoryTaskRepository()
_planning_session_store = PlanningSessionStore()


def get_memory_repository() -> MemoryPort:
    backend = os.getenv("MEMORY_BACKEND", "in_memory").lower()
    if backend in {"chroma", "pg"}:
        raise RuntimeError("PG-backed memory requires a database session")
    return _memory_repo


def get_pg_backed_memory_repository(
    session: AsyncSession = Depends(get_db_session),
) -> MemoryPort:
    backend = os.getenv("MEMORY_BACKEND", "in_memory").lower()
    if backend == "chroma":
        vector_index = ChromaAdapter(
            host=os.getenv("CHROMADB_HOST", "localhost"),
            port=int(os.getenv("CHROMADB_PORT", "8001")),
            collection_name=os.getenv("CHROMADB_COLLECTION", "memories"),
        )
        return PGBackedMemoryRepository(
            pg_repo=PGMemoryRepository(session=session),
            vector_index=vector_index,
        )
    if backend == "pg":
        return PGBackedMemoryRepository(
            pg_repo=PGMemoryRepository(session=session),
            vector_index=None,
        )
    return _memory_repo


def _get_llm_client() -> LLMClient:
    llm_port = llm_router.get_provider()
    return LLMClient(llm_adapter=llm_port, prompt_builder=PromptBuilder())


def get_task_repository(
    session: AsyncSession = Depends(get_db_session),
) -> PGTaskRepository:
    return PGTaskRepository(session=session)


def get_orchestrator(
    task_repo: PGTaskRepository = Depends(get_task_repository),
    memory_repo: MemoryPort = Depends(get_pg_backed_memory_repository),
) -> Orchestrator:
    llm_port = llm_router.get_provider()
    return Orchestrator(
        llm_port=llm_port,
        task_port=task_repo,
        memory_port=memory_repo,
    )


def build_companion_orchestrator(
    session: AsyncSession | None = None,
) -> Orchestrator:
    """Build chat orchestrator without touching planning persistence."""
    llm_port = llm_router.get_provider()
    backend = os.getenv("MEMORY_BACKEND", "in_memory").lower()
    if backend in {"chroma", "pg"}:
        if session is None:
            raise RuntimeError("PG-backed companion memory requires a database session")
        vector_index = None
        if backend == "chroma":
            vector_index = ChromaAdapter(
                host=os.getenv("CHROMADB_HOST", "localhost"),
                port=int(os.getenv("CHROMADB_PORT", "8001")),
                collection_name=os.getenv("CHROMADB_COLLECTION", "memories"),
            )
        memory_repo: MemoryPort = PGBackedMemoryRepository(
            pg_repo=PGMemoryRepository(session=session),
            vector_index=vector_index,
        )
    else:
        memory_repo = _memory_repo
    return Orchestrator(
        llm_port=llm_port,
        task_port=_chat_task_repo,
        memory_port=memory_repo,
    )


def get_planning_service(
    task_repo: PGTaskRepository = Depends(get_task_repository),
) -> PlanningService:
    return PlanningService(
        llm_client=_get_llm_client(),
        task_port=task_repo,
        session_store=_planning_session_store,
    )


def get_proactive_companion_service(
    session: AsyncSession = Depends(get_db_session),
) -> ProactiveCompanionService:
    task_repo = PGTaskRepository(session=session)
    memory_repo = get_pg_backed_memory_repository(session=session)
    return ProactiveCompanionService(
        llm_client=_get_llm_client(),
        memory_port=memory_repo,
        task_port=task_repo,
    )
