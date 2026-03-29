from __future__ import annotations

from pathlib import Path

from agent_orchestrator.infra.fs.artifact_store import FileArtifactStore, InMemoryArtifactStore


def test_in_memory_artifact_store_reads_seeded_json_and_text() -> None:
    store = InMemoryArtifactStore()
    store.seed_json("/artifacts/review.json", {"decision": "PASS", "later_items": [{"id": "later-1"}]})
    store.seed_text("/artifacts/note.txt", "hello")

    assert store.exists("/artifacts/review.json") is True
    assert store.read_json("/artifacts/review.json")["decision"] == "PASS"
    assert store.read_text("/artifacts/note.txt") == "hello"


def _assert_write_read_contract(store) -> None:
    text_path = store.write_text("/artifacts/runs/demo-project/note.txt", "worker-note")
    json_path = store.write_json(
        "/artifacts/runs/demo-project/review.json",
        {"decision": "PASS", "important_items": [{"id": "important-1"}]},
    )

    assert text_path == "/artifacts/runs/demo-project/note.txt"
    assert json_path == "/artifacts/runs/demo-project/review.json"
    assert store.exists(text_path) is True
    assert store.exists(json_path) is True
    assert store.read_text(text_path) == "worker-note"
    assert store.read_json(json_path)["decision"] == "PASS"


def test_in_memory_artifact_store_writes_and_reads_text_and_json() -> None:
    _assert_write_read_contract(InMemoryArtifactStore())


def test_file_artifact_store_writes_and_reads_text_and_json(tmp_path: Path) -> None:
    store = FileArtifactStore(tmp_path)

    _assert_write_read_contract(store)

    assert (tmp_path / "artifacts/runs/demo-project/note.txt").read_text(encoding="utf-8") == "worker-note"
    assert store.read_json("/artifacts/runs/demo-project/review.json")["important_items"] == [{"id": "important-1"}]
