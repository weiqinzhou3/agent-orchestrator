from __future__ import annotations

from agent_orchestrator.infra.fs.artifact_store import InMemoryArtifactStore


def test_in_memory_artifact_store_reads_seeded_json_and_text() -> None:
    store = InMemoryArtifactStore()
    store.seed_json("/artifacts/review.json", {"decision": "PASS", "later_items": [{"id": "later-1"}]})
    store.seed_text("/artifacts/note.txt", "hello")

    assert store.exists("/artifacts/review.json") is True
    assert store.read_json("/artifacts/review.json")["decision"] == "PASS"
    assert store.read_text("/artifacts/note.txt") == "hello"
