"""wired 由读取入口派生（ADR-FHIC-22）。

1. ``READER_ENTRIES`` 覆盖全部 7 域。
2. ``wired_domains()`` 返回集合与 AST 独立扫描一致。
3. ``tb_detail`` 因无读者，不在 ``wired_domains()`` 结果中。
4. 假读者变异：给 ``tb_detail`` 加假入口 ⇒ 变异后它被 AST 判定为 wired。
5. ``effective_slots`` 调用不计。
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from app.services.formula_settings.consumers import READER_ENTRIES, wired_domains
from app.services.formula_settings.definitions import DOMAINS


# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _app_root() -> Path:
    """``backend/app``。"""
    return Path(__file__).resolve().parent.parent.parent / "app"


def _ast_scan_for_names(names: frozenset[str], app_root: Path) -> set[str]:
    """独立 AST 扫描：在 backend/app 下（排除 formula_settings 包与路由）
    找到引用了 *names* 中任一名字的 .py 文件路径集合。
    """
    excluded_dir = app_root / "services" / "formula_settings"
    excluded_file = app_root / "routers" / "formula_settings.py"
    hit_files: set[str] = set()
    for dirpath, _dirnames, filenames in os.walk(app_root):
        dp = Path(dirpath)
        if dp == excluded_dir or excluded_dir in dp.parents:
            continue
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = dp / fname
            if fpath == excluded_file:
                continue
            try:
                tree = ast.parse(fpath.read_bytes(), filename=str(fpath))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in names:
                    hit_files.add(str(fpath))
                    break
                if isinstance(node, ast.Attribute) and node.attr in names:
                    hit_files.add(str(fpath))
                    break
    return hit_files


# ── 测试 ──────────────────────────────────────────────────────────────────────


def test_reader_entries_covers_all_domains():
    """READER_ENTRIES 的键集合 == DOMAINS 的键集合（7 域）。"""
    assert set(READER_ENTRIES) == set(DOMAINS), (
        f"READER_ENTRIES 缺少或多出域：缺 {set(DOMAINS) - set(READER_ENTRIES)}, "
        f"多 {set(READER_ENTRIES) - set(DOMAINS)}"
    )


def test_tb_detail_has_no_reader():
    """tb_detail 的入口为空元组。"""
    assert READER_ENTRIES["tb_detail"] == ()


def test_tb_detail_not_in_wired():
    """tb_detail 无读者 ⇒ wired_domains() 不包含它。"""
    wired = wired_domains(app_root=_app_root())
    assert "tb_detail" not in wired


def test_wired_domains_consistent_with_independent_scan():
    """wired_domains() 的结果与独立 AST 扫描一致。

    对每个入口非空的域，独立扫描其函数名是否在 backend/app（排除区）中出现；
    两种方法的结论必须一致。
    """
    app_root = _app_root()
    wired = wired_domains(app_root=app_root)
    for domain, entries in READER_ENTRIES.items():
        if not entries:
            # 入口为空 ⇒ 不可能 wired
            assert domain not in wired, f"{domain} 入口为空却在 wired 中"
            continue
        names = frozenset(name for _, name in entries)
        hits = _ast_scan_for_names(names, app_root)
        if hits:
            assert domain in wired, f"{domain} 有调用方 {hits} 却不在 wired 中"
        else:
            assert domain not in wired, f"{domain} 无调用方却在 wired 中"


def test_wired_domains_exclude_effective_slots():
    """effective_slots 作为通用目录读入口，不应计为任何域的读者。

    即使 effective_slots 在 backend/app 下被大量调用，它不在任何域的
    READER_ENTRIES 中，因此不影响 wired 判定。
    """
    for domain, entries in READER_ENTRIES.items():
        names = {name for _, name in entries}
        assert "effective_slots" not in names, (
            f"{domain} 的 READER_ENTRIES 不应包含 effective_slots"
        )


def test_fake_reader_mutation_makes_tb_detail_wired(tmp_path: Path):
    """变异：给 tb_detail 加一个假读者（引用 backend/app 中真实存在的函数名）
    ⇒ wired_domains() 包含 tb_detail。

    通过在 tmp_path 下建一个调用该假函数名的 .py 文件来模拟。
    """
    # 挑一个已知在 backend/app 中被调用的函数名作为假读者
    fake_name = "load_effective_report_configs"

    # 临时写一个 .py，里面引用该名字
    fake_module = tmp_path / "fake_consumer.py"
    fake_module.write_text(f"result = {fake_name}(db, standard='enterprise')\n", encoding="utf-8")

    # 猴子补丁 READER_ENTRIES 给 tb_detail 加假入口
    import app.services.formula_settings.consumers as consumers_mod
    original = consumers_mod.READER_ENTRIES["tb_detail"]
    try:
        consumers_mod.READER_ENTRIES["tb_detail"] = (
            ("fake.module", fake_name),
        )
        # 把扫描范围设为 tmp_path（里面有假消费者文件）
        wired = wired_domains(app_root=tmp_path)
        assert "tb_detail" in wired, "给 tb_detail 加假读者后应出现在 wired 中"
    finally:
        consumers_mod.READER_ENTRIES["tb_detail"] = original


@pytest.mark.parametrize("domain", [d for d, e in READER_ENTRIES.items() if e])
def test_each_nonempty_domain_reader_exists_in_codebase(domain: str):
    """每个入口非空域的函数名在 backend/app 下至少被一个模块引用。

    这保证 READER_ENTRIES 不是写死但过时的清单。
    """
    entries = READER_ENTRIES[domain]
    names = frozenset(name for _, name in entries)
    hits = _ast_scan_for_names(names, _app_root())
    assert hits, f"{domain} 的读取入口函数 {names} 在 backend/app 中无调用方"
