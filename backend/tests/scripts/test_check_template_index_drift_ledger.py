# -*- coding: utf-8 -*-
"""`check_template_index_drift_ledger.py` 与账本 `INDEX_DRIFT_LEDGER` 的自测。

spec: d1-sync-row-table-engine-and-d1-coverage · X5-j
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_CHECK = (
    _REPO / "backend" / "scripts" / "check" / "check_template_index_drift_ledger.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_tidl", _CHECK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _registry():
    import sys

    backend = _REPO / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from tests.workpaper_sync import _template_index_drift_registry as reg

    return reg


def test_every_ledger_entry_has_cycle_nature_and_numbers() -> None:
    reg = _registry()
    assert reg.INDEX_DRIFT_LEDGER, "账本为空"
    for rel, e in reg.INDEX_DRIFT_LEDGER.items():
        assert e.cycle and len(e.cycle) <= 3, f"{rel} 的 cycle 不像循环代号：{e.cycle!r}"
        assert e.nature in ("committed", "worktree"), f"{rel} 的 nature 非法：{e.nature!r}"
        assert e.index_kb > 0 and e.disk_kb > 0, f"{rel} 的 KB 值不合法"
        assert abs(e.index_kb - e.disk_kb) > 0.05, (
            f"{rel} 账本里两值几乎相等 —— 它本来就不该在漂移账本里"
        )
        assert rel.split("\\")[0] == e.cycle, (
            f"{rel} 的目录前缀与 cycle 字段不一致（{e.cycle}）"
        )


def test_frozenset_is_derived_from_the_ledger_not_maintained_twice() -> None:
    """🔴 `INDEX_SIZE_DRIFTED_FILES` 必须由账本派生 —— 两处手工维护必然漂移。"""
    reg = _registry()
    assert reg.INDEX_SIZE_DRIFTED_FILES == frozenset(reg.INDEX_DRIFT_LEDGER)
    src = (
        _REPO / "backend" / "tests" / "workpaper_sync"
        / "_template_index_drift_registry.py"
    ).read_text(encoding="utf-8")
    assert "INDEX_SIZE_DRIFTED_FILES = frozenset(INDEX_DRIFT_LEDGER)" in src, (
        "派生关系被改成手写字面量了 —— 两张表会各走各的"
    )


def test_worktree_nature_entries_are_also_in_the_dirty_path_registry() -> None:
    """交叉一致：`nature="worktree"` 的条目必须同时登记在未提交路径表里。

    两张表记的是同一件事的两个面（索引数值漂移 / 文件有未提交改动），
    只登一边会让另一边的反向断言失去线索。
    """
    reg = _registry()
    for rel, e in reg.INDEX_DRIFT_LEDGER.items():
        if e.nature != "worktree":
            continue
        expect = "backend/wp_templates/" + rel.replace("\\", "/")
        assert expect in reg.KNOWN_DIRTY_AUTHORITATIVE_PATHS, (
            f"{rel} 标了 nature=worktree 但不在 KNOWN_DIRTY_AUTHORITATIVE_PATHS 里：\n"
            f"  期望条目 {expect}"
        )


def test_group_counts_sum_to_total() -> None:
    mod = _load()
    report = mod.run()
    assert sum(report["by_cycle"].values()) == report["total"]
    assert report["committed"] + report["worktree"] == report["total"]


def test_ledger_matches_现算() -> None:
    """台账声明值必须与现算一致（过期即红）。"""
    mod = _load()
    report = mod.run()
    assert report["ok"], (
        f"{len(report['problems'])} 份与现算不符：{report['problems'][:6]}"
    )


def test_index_json_field_path_is_the_real_one() -> None:
    """🔴 钉住踩过的坑：路径字段是 `files[*].relative_path`，不是 `templates[*].path`。

    首版按后者猜，30 条全报「索引缺失」。本条让「解析口径退回猜测」立刻可见。
    """
    mod = _load()
    declared = mod._index_declared()
    assert len(declared) > 400, f"只解析出 {len(declared)} 条 —— 字段路径可能又猜错了"
    reg = _registry()
    missing = [rel for rel in reg.INDEX_DRIFT_LEDGER if rel not in declared]
    assert not missing, f"账本里这些路径在索引中找不到（key 归一化有问题）：{missing[:5]}"


def test_stale_ledger_value_is_reported(monkeypatch) -> None:
    """变异：把一条账本声明值改掉 ⇒ 必须报「账本值已过期」并非零退出。"""
    mod = _load()
    reg = _registry()
    victim = sorted(reg.INDEX_DRIFT_LEDGER)[0]
    orig = reg.INDEX_DRIFT_LEDGER[victim]
    mutated = dict(reg.INDEX_DRIFT_LEDGER)
    mutated[victim] = orig._replace(index_kb=orig.index_kb + 12.5)
    monkeypatch.setattr(mod, "INDEX_DRIFT_LEDGER", mutated)
    report = mod.run()
    assert not report["ok"]
    assert victim in report["problems"]
    row = next(r for r in report["rows"] if r["path"] == victim)
    assert row["stale_index"] is True


def test_entry_that_no_longer_drifts_is_reported(monkeypatch) -> None:
    """变异（反向）：若某条现算已不漂移 ⇒ 必须要求从账本移除。

    模拟方式：让 `_disk_kb` 返回与索引声明相同的值。
    """
    mod = _load()
    reg = _registry()
    victim = sorted(reg.INDEX_DRIFT_LEDGER)[0]
    declared = mod._index_declared()
    real_disk_kb = mod._disk_kb

    def _patched(rel: str):
        return declared[victim] if rel == victim else real_disk_kb(rel)

    monkeypatch.setattr(mod, "_disk_kb", _patched)

    report = mod.run()
    row = next(r for r in report["rows"] if r["path"] == victim)
    assert row["still_drifted"] is False, "现算已不漂移却没被识别"
    assert not report["ok"] and victim in report["problems"], (
        "不再漂移的条目必须被点名要求从账本移除"
    )
    # 其余条目不受影响 —— 证明 patch 没把整张表都改掉（否则本条会假绿）
    others = [r for r in report["rows"] if r["path"] != victim]
    assert all(r["still_drifted"] for r in others), "patch 影响了其他条目，变异不纯"


def test_tolerance_is_tight_enough_to_catch_real_edits() -> None:
    """容差只覆盖一位小数的四舍五入，不得放大到能吞掉真实改动。"""
    mod = _load()
    assert mod._TOLERANCE_KB <= 0.05, (
        f"容差 {mod._TOLERANCE_KB}KB 过大 —— 会掩盖真实的模板改动"
    )
