"""FollowupStateStore 持久化健壮性测试。"""

from pathlib import Path

from src.modules.messages.followup_store import FollowupStateStore


def test_followup_store_writes_backup_file(tmp_path: Path) -> None:
    path = tmp_path / "followup.json"
    store = FollowupStateStore(path=str(path), max_sessions=10)

    store.upsert("s1", {"value": 1})

    assert path.exists()
    assert Path(f"{path}.bak").exists()


def test_followup_store_loads_from_backup_when_primary_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "followup.json"
    store = FollowupStateStore(path=str(path), max_sessions=10)

    store.upsert("s1", {"value": 1})
    path.write_text("{not-json}", encoding="utf-8")

    loaded = store.get("s1")

    assert loaded.get("value") == 1
