from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.in_memory_memory_repo import InMemoryMemoryRepository
from src.adapters.pg_repo import PGTaskRepository
from src.core.prompts.prompt_builder import PromptBuilder
from src.infra.db.session import get_db_session
from src.infra.llm_router import llm_router
from src.services.llm_client import LLMClient
from src.services.orchestrator import Orchestrator
from src.services.planning import PlanningService, PlanningSessionStore

_memory_repo = InMemoryMemoryRepository()
_planning_session_store = PlanningSessionStore()


def _get_llm_client() -> LLMClient:
    llm_port = llm_router.get_provider()
    return LLMClient(llm_adapter=llm_port, prompt_builder=PromptBuilder())


def get_task_repository(
    session: AsyncSession = Depends(get_db_session),
) -> PGTaskRepository:
    return PGTaskRepository(session=session)


def get_orchestrator(
    task_repo: PGTaskRepository = Depends(get_task_repository),
) -> Orchestrator:
    llm_port = llm_router.get_provider()
    return Orchestrator(
        llm_port=llm_port,
        task_port=task_repo,
        memory_port=_memory_repo,
    )


def get_planning_service(
    task_repo: PGTaskRepository = Depends(get_task_repository),
) -> PlanningService:
    return PlanningService(
        llm_client=_get_llm_client(),
        task_port=task_repo,
        session_store=_planning_session_store,
    )
