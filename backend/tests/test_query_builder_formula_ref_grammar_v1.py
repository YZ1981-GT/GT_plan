# Feature: acnr-consumer-wiring, Task 34.2 / Property 26: Formula-Ref Grammar Closure (backend producer)
"""Contract test: query_builder.py::_derive_formula_refs 产出的 formula_ref 全部 grammar_v1-parseable.

**Validates: Requirements 14.7, 21.3**

背景（design Property 26 / Req 21.3）:
    `query_builder.py::_derive_formula_refs` 为高级查询结果每行派生结构化公式引用：
      - trial_balance → ``TB('{standard_account_code}','审定数')``
      - 其余表（含 tb_balance）→ None
    这些是 **非 wp 域**（TB）ref，故 catalog ``_formula_ref_to_addr_id``（只解析 WP/PREV）
    对其返回 None —— 它们的 grammar_v1 解析入口是 ``acnr.resolver.full_resolve`` 的 V1
    委托（``_detect_non_wp_domain`` → "tb" → ``_delegate_v1`` →
    ``address_registry.formula_ref_to_uri`` → ``tb://{code}#{col}`` → ``parse_uri`` →
    ``found=True``）。

契约断言:
    1. ``_derive_formula_refs`` 对含 code 的试算表行产出非 None ref；无 code 行产出 None（不产畸形）。
    2. 每个非 None ref 经 ``full_resolve(formula_ref=...)`` 解析为 ``found=True``（非 null）。
    3. ``_formula_ref_to_addr_id`` 对这些 TB ref 返回 None（记录：TB 走 V1 委托而非 WP 解析器），
       畸形 WP ref 同样返回 None（解析器不过宽）。
    4. 非可定位表（tb_balance、working_paper 等）产出全 None（不产畸形 ref）。

本文件测的是写法闭包（能否解析成统一契约），故以只建身份的口径调用（``verify_existence=False``）；
按项目数据判存在是另一件事（spec formula-fetch-followup-defect-closure R5.1，见 ``tests/test_formula_ref_check.py``）。

2026-10-27 advanced-query-linkage-closure 任务 11（R3.7，ADR-AQL-18；AQ-27 / AQ-32）：原文件把 tb_balance 的
``TB('{客户科目码}','期末')`` 锁成期望，并用「两种列名都能解析成 URI」证明它可用——``#cell`` 段原样透传，解析恒成立，
是假绿：地址库校验判它无效（TB 域按标准科目码取数、「期末」不是试算表列名）。现 tb_balance 行不再生成引用；
「审定数有效 / 期末无效」改到真 PG 用 ``address_registry.validate_formula_refs`` 断言（
``tests/advanced_query_linkage/test_aql_builder_total_refs_pg.py``）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 确保 backend 目录在 path（与 tests/acnr 同风格）
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.routers.query_builder import _derive_formula_refs
from app.services.acnr.catalog import _formula_ref_to_addr_id
from app.services.acnr.resolver import full_resolve


# ─── _derive_formula_refs 产出形态 ─────────────────────────────────────────────

def test_derive_formula_refs_trial_balance_shape():
    """trial_balance → TB('{code}','审定数')；无 code 行 → None。"""
    rows = [
        {"standard_account_code": "1001"},
        {"standard_account_code": "1122"},
        {"standard_account_code": None},  # 无 code → None
        {},  # 缺列 → None
    ]
    refs = _derive_formula_refs("trial_balance", rows)
    assert refs == [
        "TB('1001','审定数')",
        "TB('1122','审定数')",
        None,
        None,
    ]


def test_derive_formula_refs_tb_balance_shape():
    """tb_balance → 全 None：客户科目码不属于 TB 域，「期末」也不是试算表列名（AQ-27）。"""
    rows = [
        {"standard_account_code": "1001"},
        {"account_code": "6001"},
        {"standard_account_code": None, "account_code": None},
    ]
    assert _derive_formula_refs("tb_balance", rows) == [None, None, None]


def test_derive_formula_refs_non_locatable_table_all_none():
    """非可定位表（working_paper 等）→ 全 None（不产畸形 ref）。"""
    rows = [{"id": 1}, {"id": 2}]
    assert _derive_formula_refs("working_paper", rows) == [None, None]
    assert _derive_formula_refs("report_config", rows) == [None, None]


# ─── grammar_v1 解析：full_resolve V1 委托对每个产出 ref 返回 found=True ──────────

@pytest.mark.parametrize(
    "table,rows",
    [
        ("trial_balance", [{"standard_account_code": c} for c in ("1001", "1122", "6001", "222101")]),
    ],
)
async def test_query_builder_refs_resolve_under_grammar_v1(table, rows):
    """query_builder 产出的每个 TB ref 经 full_resolve V1 委托 → found=True（非 null）。"""
    refs = _derive_formula_refs(table, rows)
    assert refs and all(r is not None for r in refs)
    for ref in refs:
        result = await full_resolve(formula_ref=ref, verify_existence=False)
        assert result.found is True, f"grammar_v1 未能解析 query_builder ref: {ref!r}"
        # V1 委托产出统一契约：tb 域 URI + 非空 addr_id
        assert result.addr_id, f"{ref!r} 解析结果缺 addr_id"
        assert result.uri and result.uri.startswith("tb://"), f"{ref!r} → {result.uri!r} 非 tb 域 URI"


# ─── _formula_ref_to_addr_id 语义记录 + 解析器不过宽 ───────────────────────────

def test_tb_refs_not_handled_by_wp_addr_id_parser():
    """记录性断言：TB ref 走 V1 委托，非 catalog._formula_ref_to_addr_id（仅 WP/PREV）。

    这解释了为何 grammar_v1 入口对 query_builder 产出必须用 full_resolve 而非
    _formula_ref_to_addr_id —— 后者对 TB ref 返回 None（非畸形，是域外）。
    """
    assert _formula_ref_to_addr_id("TB('1001','审定数')") is None
    assert _formula_ref_to_addr_id("TB('1001','期末')") is None


def test_wp_addr_id_parser_rejects_malformed():
    """WP 解析器对畸形 ref 返回 None（不过宽），对合法 WP ref 非 null。"""
    # 合法 WP 3 参 / custom_flat → 非 null
    assert _formula_ref_to_addr_id("WP('D2','明细表D2-2','E100')") is not None
    assert _formula_ref_to_addr_id("WP('CUST-01','CUST-01','B7')") is not None
    # 畸形 → None
    assert _formula_ref_to_addr_id("not-a-ref") is None
    assert _formula_ref_to_addr_id("SUM(A1:A2)") is None
