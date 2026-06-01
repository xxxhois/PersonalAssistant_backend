from src.adapters.chroma_adapter import ChromaAdapter


def test_chroma_adapter_sanitizes_metadata_for_index_storage() -> None:
    adapter = ChromaAdapter(host="localhost", port=8001)

    sanitized = adapter._sanitize_metadata(
        {
            "id": "memory-1",
            "user_id": "user-1",
            "importance": 0.8,
            "active": True,
            "ignored": None,
            "nested": {"source": "chat"},
        }
    )

    assert sanitized == {
        "id": "memory-1",
        "user_id": "user-1",
        "importance": 0.8,
        "active": True,
        "nested": "{'source': 'chat'}",
    }


def test_chroma_adapter_builds_chroma_where_filter() -> None:
    adapter = ChromaAdapter(host="localhost", port=8001)

    where = adapter._build_where(
        {
            "user_id": "user-1",
            "scope": "companion",
            "memory_type": ["fact", "preference"],
            "ignored": None,
        }
    )

    assert where == {
        "$and": [
            {"user_id": {"$eq": "user-1"}},
            {"scope": {"$eq": "companion"}},
            {"memory_type": {"$in": ["fact", "preference"]}},
        ]
    }
