"""AI 旧调用和越界 Prompt 只减棘轮。"""

from pathlib import Path

from scripts.check import check_ai_task_call_coverage as guard


def test_committed_baseline_covers_current_debt() -> None:
    baseline = guard.json.loads(guard.BASELINE.read_text(encoding="utf-8"))
    assert set(guard.scan_direct_calls()) <= set(guard._baseline_rows(baseline, "direct_calls"))
    assert set(guard.scan_prompt_debts()) <= set(guard._baseline_rows(baseline, "prompt_debts"))


def test_ast_scanner_detects_real_call_but_ignores_comment(tmp_path: Path, monkeypatch) -> None:
    app = tmp_path / "app"
    app.mkdir()
    source = app / "sample.py"
    source.write_text(
        "# chat_completion(messages) 只是注释\n"
        "async def run():\n"
        "    return await chat_completion([])\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "BACKEND", tmp_path)
    monkeypatch.setattr(guard, "APP", app)
    rows = guard.scan_direct_calls()
    assert rows == ["app/sample.py::run::chat_completion#1"]


def test_prompt_scanner_uses_dict_key_and_detects_professional_boundary(tmp_path: Path, monkeypatch) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "prompt.py").write_text(
        "PROMPTS = {'overall-opinion': '请生成某科目的总体审计意见'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "BACKEND", tmp_path)
    monkeypatch.setattr(guard, "APP", app)
    assert guard.scan_prompt_debts() == [
        "app/prompt.py::overall-opinion::generate_overall_opinion"
    ]
