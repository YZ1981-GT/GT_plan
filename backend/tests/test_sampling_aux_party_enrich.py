"""辅助维度往来单位补全守卫（R6.5 客户名称自动带出）。

覆盖三件事：
1. **接线存在性**：`voucher-extract` 必须真的调用 `enrich_items_with_aux_party`，
   且调用形态是**模块级函数**而不是 `LedgerSamplingService.<方法名>` ——
   后者在运行时抛 `AttributeError`，被 fail-open 的 `except` 吞成 WARNING，
   表现为「客户名永远是空的」而测试与 `get_diagnostics` 全绿（2026-08-04 实测踩过）。
2. **匹配键语义**：金额必须归一为 2 位小数字符串（两表 numeric 精度声明可能不同，
   `12.10` vs `12.1` 直接比 Decimal 会漏匹配）。
3. **fail-open 契约**：查询失败/无数据时三个字段仍要存在且 `party_name` 为 None ——
   「查不到」与「查询炸了」对前端必须表现一致，且绝不阻断抽样。

不连库（纯函数 + 源码级断言），可进 CI。
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.ledger_sampling_service import (
    AUX_PARTY_TYPES,
    _aux_match_key,
    enrich_items_with_aux_party,
)

_BACKEND = Path(__file__).resolve().parents[1]
_ROUTER = _BACKEND / "app" / "routers" / "voucher_sampling.py"
_SERVICE = _BACKEND / "app" / "services" / "ledger_sampling_service.py"


def _strip_comments(src: str) -> str:
    """剥掉 # 行注释与三引号 docstring。

    守卫自己的说明注释里会写出被禁的错误形态（如 `LedgerSamplingService.enrich_...`），
    不剥注释会把说明文字数成真实调用 → 断言恒红/恒绿两种失效都可能发生。
    """
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return re.sub(r"(?m)#.*$", "", src)


# ─── 1. 接线存在性 ───────────────────────────────────────────────────────────


def test_extract_endpoint_actually_calls_enrich():
    """抽凭端点必须真的调用补全函数（否则后端算了前端也拿不到）。"""
    src = _strip_comments(_ROUTER.read_text(encoding="utf-8"))
    assert "await enrich_items_with_aux_party(" in src, (
        "voucher-extract 必须 await 调用 enrich_items_with_aux_party；"
        "只在 import 里出现不算接线"
    )


def test_enrich_is_imported_not_attribute_access():
    """🔴 必须按模块级函数调用，禁止写成 LedgerSamplingService.<x>。

    它是模块级 `async def`，不是 service 类的方法。写成属性访问会在运行时抛
    AttributeError → 被 fail-open 吞掉 → 客户名恒空且无任何报错线索。
    """
    src = _strip_comments(_ROUTER.read_text(encoding="utf-8"))
    bad = re.findall(r"LedgerSamplingService\.\s*enrich\w*", src)
    assert bad == [], f"补全函数是模块级函数，不得按 service 方法调用：{bad}"
    assert re.search(
        r"from app\.services\.ledger_sampling_service import \([^)]*enrich_items_with_aux_party",
        src,
        re.S,
    ), "必须从 ledger_sampling_service 显式 import enrich_items_with_aux_party"


def test_enrich_called_before_high_value_marking():
    """补全必须早于 marked_items 构造 —— 后者会 dict(it) 拷贝，之后再补就丢了。"""
    src = _strip_comments(_ROUTER.read_text(encoding="utf-8"))
    i_enrich = src.find("await enrich_items_with_aux_party(")
    i_marked = src.find("marked_items: list[dict] = []")
    assert i_enrich > 0 and i_marked > 0
    assert i_enrich < i_marked, (
        "补全须在 marked_items 构造之前：marked = dict(it) 之后再写 items 不会带到返回值"
    )


def test_reverse_selfcheck_attribute_form_is_detected():
    """反向自检：属性访问形态必须被上面的判据抓到（防判据写空）。"""
    stub = "x = await LedgerSamplingService.enrich_counterparty_names(db, pid, y, items)"
    assert re.findall(r"LedgerSamplingService\.\s*enrich\w*", stub) != []


def test_reverse_selfcheck_strip_comments_really_strips():
    stub = '# LedgerSamplingService.enrich_x()\ncode = 1\n"""LedgerSamplingService.enrich_y()"""\n'
    out = _strip_comments(stub)
    assert "enrich_x" not in out and "enrich_y" not in out
    assert "code = 1" in out


# ─── 2. 匹配键语义 ───────────────────────────────────────────────────────────


def test_amount_normalized_to_two_decimals():
    """12.1 与 12.10 必须归一为同一键（两表 numeric 精度声明可能不同）。"""
    a = _aux_match_key("V1", date(2025, 1, 1), "2203", Decimal("12.1"), None)
    b = _aux_match_key("V1", date(2025, 1, 1), "2203", Decimal("12.10"), None)
    assert a == b


def test_none_amount_distinct_from_zero():
    """None（该方向无金额）与 0.00 不是一回事，不能归并。"""
    k_none = _aux_match_key("V1", date(2025, 1, 1), "2203", None, Decimal("5"))
    k_zero = _aux_match_key("V1", date(2025, 1, 1), "2203", Decimal("0"), Decimal("5"))
    assert k_none != k_zero


def test_key_trims_and_handles_missing_date():
    k1 = _aux_match_key(" V1 ", None, " 2203 ", None, None)
    assert k1[0] == "V1" and k1[1] == "" and k1[2] == "2203"


def test_key_is_hashable_and_stable():
    k = _aux_match_key("V1", date(2025, 1, 1), "2203", Decimal("1"), None)
    assert {k: 1}[k] == 1
    assert k == _aux_match_key("V1", date(2025, 1, 1), "2203", Decimal("1.00"), None)


# ─── 3. fail-open 契约 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_items_returns_same_list_without_query():
    """空样本不查库（省一次往返），且原样返回同一列表对象。"""
    items: list[dict] = []
    out = await enrich_items_with_aux_party(None, None, 2025, items)  # type: ignore[arg-type]
    assert out is items


@pytest.mark.asyncio
async def test_failure_still_declares_all_three_keys():
    """db 为 None → 查询必炸 → 仍须三键齐备且 party_name 为 None。

    「查询失败」与「本项目无辅助明细」对前端表现必须一致：否则前端得写
    `?? {}` 兜底，反而把两种状态混成一种。
    """
    items = [{"voucher_no": "V1", "voucher_date": "2025-01-01", "account_code": "2203"}]
    out = await enrich_items_with_aux_party(None, None, 2025, items)  # type: ignore[arg-type]
    assert out[0]["party_name"] is None
    assert out[0]["party_aux_type"] is None
    assert out[0]["party_ambiguous"] is False


@pytest.mark.asyncio
async def test_existing_fields_not_overwritten():
    """不得覆盖 items 里既有字段（补全是加法）。"""
    items = [{"voucher_no": "V1", "summary": "原摘要", "party_name": "已填客户"}]
    out = await enrich_items_with_aux_party(None, None, 2025, items)  # type: ignore[arg-type]
    assert out[0]["summary"] == "原摘要"
    assert out[0]["party_name"] == "已填客户", "setdefault 语义：已有值不许被覆盖"


# ─── 4. 维度类型白名单 ───────────────────────────────────────────────────────


def test_aux_party_types_are_counterparty_dimensions_only():
    """白名单只放「往来单位」性质的维度。

    实测该库 21 种 aux_type 里「成本中心/业态/税率/医保类型/银行账户」等都不是
    往来单位 —— 混进来会把成本中心名填进「客户名称」列。
    """
    assert "客户" in AUX_PARTY_TYPES
    for forbidden in ("成本中心", "业态", "税率", "医保类型", "银行账户", "车牌号"):
        assert forbidden not in AUX_PARTY_TYPES, (
            f"{forbidden} 不是往来单位维度，不得进白名单"
        )


def test_service_declares_typed_columns_for_uuid_comparison():
    """🔴 sa.table() 的列必须带类型声明。

    裸 `sa.column("project_id")` 无类型 → asyncpg 按 VARCHAR 传参 →
    PG 报 `operator does not exist: uuid = character varying`，整个补全被
    fail-open 吞成 WARNING（2026-08-04 真实库实测踩过；替身 session 查不出）。
    """
    src = _strip_comments(_SERVICE.read_text(encoding="utf-8"))
    i = src.find("tb_aux_ledger")
    assert i > 0, "未找到 tb_aux_ledger 表声明"
    block = src[i : i + 1200]
    assert re.search(r'sa\.column\(\s*"project_id"\s*,\s*(?:sa\.)?\w*UUID', block) or \
        re.search(r'sa\.column\(\s*"project_id"\s*,[^)]+\)', block), (
        "project_id 列必须带类型声明（否则 asyncpg 按 VARCHAR 传参，PG 拒绝 uuid 比较）"
    )
