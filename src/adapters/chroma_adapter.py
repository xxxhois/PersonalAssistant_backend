import asyncio
from typing import Any, Optional
from uuid import uuid4

from src.core.ports.memory_port import MemoryChunk, MemoryPort


class ChromaAdapter(MemoryPort):
    """
    ChromaDB memory index over an HTTP Chroma server.

    Recommended deployment for this project:
    - Local development: a sibling Docker container on the same compose network.
    - Production: a private internal service beside the backend, not exposed publicly.
    - Persist Chroma's data volume separately; keep Postgres as the future source of truth.

    This adapter is intentionally an index adapter. Application code should normally
    depend on PGBackedMemoryRepository, which writes PG first and uses Chroma only
    for candidate retrieval.
    """

    def __init__(self, host: str, port: int, collection_name: str = "memories") -> None:
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self._collection: Any = None

    async def query_context(
        self,
        query: str,
        limit: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[MemoryChunk]:
        collection = await self._get_collection()
        result = await asyncio.to_thread(
            collection.query,
            query_texts=[query],
            n_results=limit,
            where=filters,
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        chunks: list[MemoryChunk] = []
        for index, document in enumerate(documents):
            distance = float(distances[index]) if index < len(distances) else 0.0
            chunks.append(
                MemoryChunk(
                    content=str(document),
                    metadata=dict(metadatas[index] or {}) if index < len(metadatas) else {},
                    score=max(0.0, 1.0 - distance),
                )
            )
        return chunks

    async def store(self, chunk: MemoryChunk) -> None:
        await self.batch_store([chunk])

    async def batch_store(self, chunks: list[MemoryChunk]) -> None:
        if not chunks:
            return

        collection = await self._get_collection()
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for chunk in chunks:
            metadata = dict(chunk.metadata)
            document_id = str(metadata.get("id") or metadata.get("memory_id") or uuid4())
            metadata["id"] = document_id
            ids.append(document_id)
            documents.append(chunk.content)
            metadatas.append(metadata)

        await asyncio.to_thread(
            collection.upsert,
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    async def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection

        def connect() -> Any:
            import chromadb

            client = chromadb.HttpClient(host=self.host, port=self.port)
            return client.get_or_create_collection(name=self.collection_name)

        self._collection = await asyncio.to_thread(connect)
        return self._collection
