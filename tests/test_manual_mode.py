from src.modules.messages.manual_mode import ManualModeStore


def test_manual_mode_toggle_and_persist(tmp_path) -> None:
    db_path = tmp_path / "manual_mode.db"
    store = ManualModeStore(db_path=db_path)

    first = store.process_message("s1", "。", now=1000)
    assert first.toggled is True
    assert first.state.enabled is True

    restored = ManualModeStore(db_path=db_path).get_state("s1", now=1001)
    assert restored.state.enabled is True

    second = store.process_message("s1", "。", now=1002)
    assert second.state.enabled is False


def test_manual_mode_timeout_auto_recover(tmp_path) -> None:
    store = ManualModeStore(db_path=tmp_path / "manual_mode.db", timeout_seconds=10)

    store.set_state("s1", True, now=100)
    before = store.get_state("s1", now=109)
    assert before.state.enabled is True

    after = store.get_state("s1", now=111)
    assert after.state.enabled is False
    assert after.timeout_recovered is True


def test_manual_mode_isolated_by_session(tmp_path) -> None:
    store = ManualModeStore(db_path=tmp_path / "manual_mode.db")

    store.process_message("s1", "。", now=100)
    s1 = store.get_state("s1", now=101)
    s2 = store.get_state("s2", now=101)

    assert s1.state.enabled is True
    assert s2.state.enabled is False


def test_manual_mode_process_message_returns_baseline_when_not_toggle(tmp_path) -> None:
    store = ManualModeStore(db_path=tmp_path / "manual_mode.db")
    out = store.process_message("s-non-toggle", "hello", now=100)
    assert out.toggled is False
    assert out.state.enabled is False
