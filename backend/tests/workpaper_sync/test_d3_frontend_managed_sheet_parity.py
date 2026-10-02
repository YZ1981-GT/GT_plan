# -*- coding: utf-8 -*-
"""D3 Property 12：前端受管 sheet 集合与后端 provider `all_managed_sheet_names()` 逐字一致。

spec: d3-sync-coverage-via-row-table-engine · Task 16 · Requirements 6.6
design.md Property 12：前端受管 sheet 集合从 provider 派生、不前端硬编码字面量清单。

═══ 这条判据守的是什么 ═══

Task 16 要求前端受管判定「从 provider 受管清单派生、不前端硬编码」。平台当前没有把受管 sheet
的**短码集合**下发到前端的运行时通路（manifest 生成物只带 AST 抽出的 sheet 字面量/表达式，
render-config/store-projection 也不下发），故前端集中声明一份清单
（`sync/d3ManagedSheets.ts` 的 `D3_MANAGED_SHEETS`），由**本契约测试**逐字守护它与后端权威源
`phase5_d3_expansion.all_managed_sheet_names()` 一致。

design.md Property 12 明文给出的可接受形态正是二选一：「受管 sheet 集合从 provider 派生」**或**
「断言前端受管判定与后端 `all_managed_sheet_names()` 一致」。本文件取后者。

守护的两件事：
  ① 前端 `D3_MANAGED_SHEETS` 的 `excelName` 集合 == 后端 `all_managed_sheet_names()`（逐字）。
     ⇒ 往前端硬编码一张假 sheet、或后端增删受管 sheet 而前端没跟上，必红。
  ② 前端 rows 类 sheet 的 `sheetKey` 集合 == 后端行表 spec 的 `sheet_key` 集合；
     前端 adjudication 类的 `sheetKey` == 后端审定表 spec 的 `sheet_key`。
     ⇒ 前端 kind 分类（决定分派到哪套桥）与后端受管形态一致。

变异检验（任务原文「Property 12 钉住」）：
  · `test_mutation_inject_fake_sheet_name_makes_parity_red`：往前端清单注入一张假 sheet 名
    ⇒ 一致性断言必抛 AssertionError（证明判据有牙齿，不是恒真装饰）。
  · `test_mutation_frontend_drops_a_managed_sheet_makes_parity_red`：前端漏一张受管 sheet
    ⇒ 必红（后端增了前端没跟上的场景）。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d3_expansion as EXP

_ROOT = _BACKEND.parent
_FRONTEND_MODULE = (
    _ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "d3ManagedSheets.ts"
)

#: 解析 `D3_MANAGED_SHEETS` 数组里每个条目的 code/sheetKey/kind/excelName 字面量。
_ENTRY_RE = re.compile(
    r"\{\s*code:\s*'(?P<code>[^']+)'\s*,"
    r"\s*sheetKey:\s*'(?P<sheetKey>[^']+)'\s*,"
    r"\s*kind:\s*'(?P<kind>rows|adjudication)'\s*,"
    r"\s*excelName:\s*'(?P<excelName>[^']+)'\s*,?\s*\}"
)


def _parse_frontend_managed_sheets(src: str | None = None) -> list[dict[str, str]]:
    """从前端 `d3ManagedSheets.ts` 解析 `D3_MANAGED_SHEETS` 条目（纯字面量正则，不执行 TS）。"""
    text = src if src is not None else _FRONTEND_MODULE.read_text(encoding="utf-8")
    # 只取 D3_MANAGED_SHEETS = Object.freeze([...]) 那一块，避免误吃文档注释里的示例。
    block = re.search(
        r"D3_MANAGED_SHEETS[^\[]*\[(?P<body>.*?)\]\s*as const\)",
        text,
        re.DOTALL,
    )
    assert block is not None, "未在前端模块里定位到 D3_MANAGED_SHEETS 数组"
    return [m.groupdict() for m in _ENTRY_RE.finditer(block.group("body"))]


def _assert_parity(entries: list[dict[str, str]]) -> None:
    """一致性断言核心：前端 excelName 集合 == 后端 all_managed_sheet_names()。"""
    frontend_excel = {e["excelName"] for e in entries}
    backend_names = set(EXP.all_managed_sheet_names())
    assert frontend_excel == backend_names, (
        f"前端受管 sheet 集合与后端 all_managed_sheet_names() 不一致："
        f"前端有而后端无={sorted(frontend_excel - backend_names)}；"
        f"后端有而前端无={sorted(backend_names - frontend_excel)}"
    )


def test_frontend_module_exists() -> None:
    assert _FRONTEND_MODULE.is_file(), f"前端受管清单模块不存在：{_FRONTEND_MODULE}"


def test_frontend_managed_sheet_names_match_backend() -> None:
    """Property 12 主判据：前端 excelName 集合逐字 == 后端 all_managed_sheet_names()。"""
    entries = _parse_frontend_managed_sheets()
    assert len(entries) == 6, f"前端应声明 6 张受管 sheet，实得 {len(entries)}：{entries}"
    _assert_parity(entries)


def test_frontend_rows_sheet_keys_match_backend_row_table_specs() -> None:
    """前端 rows 类 sheetKey 集合 == 后端行表 spec 的 sheet_key 集合（D3-2 自身 + 扩容面）。"""
    from app.services.workpaper_sync.phase5_d3_prepaid_receipts import (
        MANAGED_SHEET,
        instrumentation_spec as _d32_spec,
    )

    entries = _parse_frontend_managed_sheets()
    frontend_rows_keys = {e["sheetKey"] for e in entries if e["kind"] == "rows"}

    # 后端行表 sheet_key：D3-2 自身单数 spec + 扩容面 managed_row_table_specs()
    backend_rows_keys = {_d32_spec().resolved_sheet_key}
    for spec in EXP.managed_row_table_specs():
        backend_rows_keys.add(spec.sheet_key)

    assert frontend_rows_keys == backend_rows_keys, (
        f"前端 rows sheetKey 与后端行表 sheet_key 不一致："
        f"前端={sorted(frontend_rows_keys)} 后端={sorted(backend_rows_keys)}"
    )
    # D3-2 自身受管 sheet 名应在前端清单里（回归 sanity）。
    assert MANAGED_SHEET in {e["excelName"] for e in entries}


def test_frontend_adjudication_sheet_key_matches_backend() -> None:
    """前端 adjudication 类 sheetKey == 后端审定表 spec 的 sheet_key（d31-managed）。"""
    entries = _parse_frontend_managed_sheets()
    frontend_adj = [e for e in entries if e["kind"] == "adjudication"]
    adj_spec = EXP.adjudication_spec()
    assert adj_spec is not None, "后端审定表 spec 应已接入（_INCLUDE_D301 开关为 True）"
    assert len(frontend_adj) == 1, f"前端应恰 1 张 adjudication sheet，实得 {frontend_adj}"
    assert frontend_adj[0]["sheetKey"] == adj_spec.sheet_key
    assert frontend_adj[0]["excelName"] == adj_spec.managed_sheet


# ═══════════════════════════════════════════════════════════════════════════
# 变异检验：判据要有牙齿（Property 12 钉住）
# ═══════════════════════════════════════════════════════════════════════════
class TestMutationParityHasTeeth:
    def test_mutation_inject_fake_sheet_name_makes_parity_red(self) -> None:
        """往前端清单注入一张后端没有的假 sheet ⇒ 一致性断言必抛 AssertionError。"""
        entries = _parse_frontend_managed_sheets()
        # 先确认真实清单是通过的（对照）。
        _assert_parity(entries)
        # 变异：前端硬编码一张假 sheet（正是 Task 16 要消灭的反模式）。
        mutated = entries + [
            {"code": "D3-99", "sheetKey": "d399-managed", "kind": "rows", "excelName": "伪造检查表D3-99"}
        ]
        with pytest.raises(AssertionError):
            _assert_parity(mutated)

    def test_mutation_frontend_drops_a_managed_sheet_makes_parity_red(self) -> None:
        """前端漏声明一张后端已受管的 sheet ⇒ 一致性断言必抛 AssertionError。"""
        entries = _parse_frontend_managed_sheets()
        assert len(entries) >= 2
        # 变异：前端删掉最后一张（模拟后端增了受管 sheet 而前端没跟上）。
        mutated = entries[:-1]
        with pytest.raises(AssertionError):
            _assert_parity(mutated)

    def test_mutation_regex_parser_would_catch_hardcoded_string_literal(self) -> None:
        """反证：解析器确实读的是数组字面量 —— 注入一个不在数组里的字面量不应被解析进来。

        证明「前端受管判定是从集中声明的数组派生、不是散落的字符串字面量」——
        往模块源码里加一个游离的 `'D3-2'` 字面量（模拟宿主内联硬编码）不会被
        `_parse_frontend_managed_sheets` 计入 D3_MANAGED_SHEETS 条目数。
        """
        src = _FRONTEND_MODULE.read_text(encoding="utf-8")
        polluted = src + "\n// 游离字面量污染：const stray = 'D3-2'\n"
        # 解析结果不受游离字面量影响（仍恰 6 条）。
        assert len(_parse_frontend_managed_sheets(polluted)) == 6
