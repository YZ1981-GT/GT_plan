# -*- coding: utf-8 -*-
"""`check_known_failing_registry.py` 的自测（结构 + 解析 + 变异）。

spec: d1-sync-row-table-engine-and-d1-coverage · X5-h

═══ 分层理由 ═══

门禁本身要真跑 pytest（声明口径下约 270 秒），不适合放进快速判据集。所以分层：
门禁负责「跑并比对」，本文件负责「清册结构正确 + nodeid 解析正确 + 变异能打红」，
stdlib-only、秒级。与平台既有的门禁/自测分层一致。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_CHECK = _REPO / "backend" / "scripts" / "check" / "check_known_failing_registry.py"


def _load():
    spec = importlib.util.spec_from_file_location("_kfr", _CHECK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_registry_entries_all_have_lane_commit_and_reason() -> None:
    """每条必须写明归属 lane、首见 commit、原因摘要 —— 缺一条就不可判读。"""
    mod = _load()
    assert mod.KNOWN_FAILING, "清册为空 —— 要么全修好了（该删本门）要么清册被误清"
    for nodeid, value in mod.KNOWN_FAILING.items():
        assert isinstance(value, tuple) and len(value) == 3, f"{nodeid} 结构不对"
        lane, since, why = value
        assert lane and lane.strip(), f"{nodeid} 缺归属 lane"
        assert since and len(since) >= 7, f"{nodeid} 的首见 commit 看起来不是 sha：{since!r}"
        assert why and len(why) >= 6, f"{nodeid} 的原因摘要过短，不足以判读"


def test_registry_nodeids_point_at_existing_files() -> None:
    """nodeid 的文件部分必须真实存在 —— 文件删了就该删登记。"""
    mod = _load()
    missing = []
    for nodeid in mod.KNOWN_FAILING:
        rel = nodeid.split("::")[0]
        if not (_REPO / "backend" / rel).exists():
            missing.append(nodeid)
    assert not missing, (
        "清册指向不存在的测试文件（文件已删 ⇒ 请删登记）：\n"
        + "\n".join(f"  {n}" for n in missing)
    )


def test_registry_nodeids_are_inside_the_declared_caliber() -> None:
    """清册条目必须落在声明的收集目标内 —— 否则本门永远比对不到它。"""
    mod = _load()
    outside = [
        n for n in mod.KNOWN_FAILING
        if not any(n.startswith(t) for t in mod._DEFAULT_TARGETS)
    ]
    assert not outside, (
        f"这些条目不在声明口径 {mod._DEFAULT_TARGETS} 内，门跑不到它们：\n"
        + "\n".join(f"  {n}" for n in outside)
    )


def test_cli_flags_match_the_sibling_ledger_gate(monkeypatch, capsys) -> None:
    """🔴 与同族门禁 `check_template_index_drift_ledger.py` 的 flag 必须一致。

    实测踩到：本门原先没有 `--quiet`，调用时带上 ⇒ argparse 直接返回 **2**，
    而调用方按 0/1 判断，看起来像「门失败」，实际只是参数不认识。
    同族脚本 flag 不一致就会出这种误判。
    """
    mod = _load()
    registry = set(mod.KNOWN_FAILING)
    monkeypatch.setattr(mod, "_run_pytest", lambda *a, **k: (registry, ""))

    # --quiet 必须被接受且返回 0（不是 argparse 的 2）
    assert mod.main(["--quiet"]) == 0
    quiet_out = capsys.readouterr().out
    assert mod.main([]) == 0
    verbose_out = capsys.readouterr().out
    # quiet 只给结论，不逐条列
    assert "预存失败清册一致" in quiet_out
    assert len(quiet_out) < len(verbose_out), (
        "--quiet 没有真的减少输出 —— flag 被接受了但没接到行为上"
    )

    sibling = (
        _REPO / "backend" / "scripts" / "check" / "check_template_index_drift_ledger.py"
    )
    if sibling.exists():
        sib_src = sibling.read_text(encoding="utf-8")
        for flag in ('"--json"', '"--quiet"'):
            assert flag in sib_src, f"同族门禁缺 {flag}"
            assert flag in _CHECK.read_text(encoding="utf-8"), f"本门缺 {flag}"


def test_caliber_is_explicit_and_not_empty() -> None:
    """口径必须显式写死（换口径要改代码，制造有意的摩擦）。"""
    mod = _load()
    assert mod._DEFAULT_TARGETS, "收集目标为空"
    assert mod._DEFAULT_K and mod._DEFAULT_K.strip(), "默认 -k 表达式为空"


# ─────────────────────────────────────────────────────────────────────────────
# nodeid 转义还原（pytest -q 把非 ASCII 参数化 id 转成 `\uXXXX`）
# ─────────────────────────────────────────────────────────────────────────────


def test_unescape_restores_non_ascii_param_id() -> None:
    """实测形态：`[\\u4f59\\u989d\\u660e\\u7ec6\\u8868G5-2]` 必须还原成中文。"""
    mod = _load()
    escaped = (
        "tests/workpaper_sync/test_sibling_table_ref_row_shift.py"
        "::test_all_multi_region_sheets_shift_sibling_table_refs"
        "[\\u4f59\\u989d\\u660e\\u7ec6\\u8868G5-2]"
    )
    assert mod._unescape_nodeid(escaped).endswith("[余额明细表G5-2]"), (
        f"还原失败：{mod._unescape_nodeid(escaped)!r}"
    )


def test_unescape_is_identity_for_plain_and_for_real_chinese() -> None:
    """反向变异：不含 `\\uXXXX` 的输入必须原样返回（含已是真中文的）。

    🔴 少了这条，实现里无条件 `unicode_escape` 解码会把真中文 nodeid 变成 mojibake，
    而「还原那条」仍然绿 —— 单向变异会漏掉整个反向缺陷。
    """
    mod = _load()
    plain = "tests/workpaper_sync/test_x.py::TestA::test_b"
    chinese = "tests/workpaper_sync/test_x.py::test_y[余额明细表G5-2]"
    assert mod._unescape_nodeid(plain) == plain
    assert mod._unescape_nodeid(chinese) == chinese


# ─────────────────────────────────────────────────────────────────────────────
# 失败行解析
# ─────────────────────────────────────────────────────────────────────────────


def test_failed_and_error_lines_are_both_collected(monkeypatch) -> None:
    """`FAILED` 与 `ERROR`（collection error）两种行都要收进失败集。

    只认 `FAILED` 会漏掉「整个文件 import 崩」的情形 —— 那恰恰是最严重的一类。
    """
    mod = _load()
    fake_out = (
        "some noise\n"
        "FAILED tests/workpaper_sync/test_a.py::test_one - AssertionError: x\n"
        "ERROR tests/workpaper_sync/test_b.py\n"
        "FAILED tests/workpaper_sync/test_c.py::test_two[\\u4f59]\n"
        "1 failed, 2 passed\n"
    )

    class _Proc:
        returncode = 1
        stdout = fake_out
        stderr = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Proc())
    failed, _tail = mod._run_pytest(("tests/workpaper_sync/",), None)
    assert "tests/workpaper_sync/test_a.py::test_one" in failed
    assert "tests/workpaper_sync/test_b.py" in failed, "ERROR 行（collection error）被漏了"
    assert "tests/workpaper_sync/test_c.py::test_two[余]" in failed, "解析时未还原转义"


def test_new_failure_and_zombie_are_both_reported(monkeypatch, capsys) -> None:
    """双向变异：多出一条 ⇒ 报新增；少一条 ⇒ 报僵尸。两个方向都必须非零退出。"""
    mod = _load()
    registry = set(mod.KNOWN_FAILING)
    assert len(registry) >= 2, "清册太短，本条失去覆盖面"

    # 方向一：多出一条不在册的
    monkeypatch.setattr(
        mod, "_run_pytest",
        lambda *a, **k: (registry | {"tests/workpaper_sync/test_zz.py::test_new"}, ""),
    )
    assert mod.main([]) == 1
    out = capsys.readouterr().out
    assert "新增" in out and "test_zz.py::test_new" in out

    # 方向二：少一条（清册里有但已不红）
    shrunk = set(sorted(registry)[1:])
    monkeypatch.setattr(mod, "_run_pytest", lambda *a, **k: (shrunk, ""))
    assert mod.main([]) == 1
    out = capsys.readouterr().out
    assert "僵尸" in out

    # 方向三（正面）：完全相符 ⇒ 0
    monkeypatch.setattr(mod, "_run_pytest", lambda *a, **k: (registry, ""))
    assert mod.main([]) == 0
