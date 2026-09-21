"""D4-30 访谈客户行缺 `fields` 嵌套段的容错回归守卫。

spec: 逐层修复 D4 双向回写 apply（本会话）· 第3层-C

🔴 根因（真栈 D4-25~29 L1 全 422 复现）：D4-30 provider 的字段 spec 里
   `("time", "C", "editable", "text", "fields/time", ...)` 等**嵌套 scalar** 路径，用
   `resolve_json_path(row, "fields/time")` 取值。而真实 store 里一条访谈客户行可能只填了
   `{id, name}`、尚未填 `fields` 子对象（合法半成品）。`resolve_json_path` fail-closed 抛
   `JsonPathMissingSegmentError` → 冒泡成 combined store-projection **422
   json_path_missing_segment**，连累整个 `gt-d4-operating-revenue` entry（D4-2..36 全部
   无法进在线编辑）。

修复：interview provider 对**嵌套 scalar** 字段缺失段 → None（未填），与主 provider
   `_resolve_store_path`「标量缺失段 → None、数组路径 fail closed」同口径（interview 无数组字段）。

本守卫：D4-30 只有 {id,name} 的客户行必须能投影（fields/* → None），不抛。
变异反证：把 provider 的 try/except 去掉（恢复无条件 resolve_json_path）本测试即打红。
"""
from __future__ import annotations

import pytest

from app.services.workpaper_sync import phase5_d4_ipo_interview_sheets as IV
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync import phase5_d4_revenue_detail as provider


@pytest.fixture
def contract():
    return parse_contract(provider.build_contract_payload(), adapter_id=provider.ADAPTER_ID)


def test_d4_30_customer_without_fields_segment_projects_as_none(contract):
    """D4-30 客户行只有 id/name（无 fields 子对象）→ 投影不抛，fields/* 字段为 None。"""
    payload = {
        "customers": [
            {"id": "GTROW-D430-0007", "name": "客户甲"},  # 无 fields —— 半成品
            {"id": "GTROW-D430-0008", "name": "客户乙"},
        ],
        "customDimensions": [],
    }
    proj = IV.build_store_projection("D4-30", payload, contract=contract)

    # 两行都进投影（row_keys 齐全）
    assert set(proj.row_keys["d4_30_customers"]) == {"GTROW-D430-0007", "GTROW-D430-0008"}

    # fields/* 嵌套 scalar 字段缺失 → None（未填），不抛
    time_key = IV.stable_key_for("D4-30", "time", "GTROW-D430-0007")
    assert time_key in proj.values
    assert proj.values[time_key].value is None, "缺 fields 段的 time 字段应投空(None)，不是报错"

    # name（顶层字段）照常读到
    name_key = IV.stable_key_for("D4-30", "name", "GTROW-D430-0007")
    assert proj.values[name_key].value == "客户甲"


def test_d4_30_customer_with_fields_segment_reads_nested_value(contract):
    """对照：客户行有 fields 子对象时，fields/* 正常读到嵌套值（容错不误伤正常路径）。"""
    payload = {
        "customers": [
            {"id": "GTROW-D430-0007", "name": "客户甲",
             "fields": {"time": "2025-06-01", "reason": "新增大客户", "method": "实地走访"}},
        ],
        "customDimensions": [],
    }
    proj = IV.build_store_projection("D4-30", payload, contract=contract)
    time_key = IV.stable_key_for("D4-30", "time", "GTROW-D430-0007")
    assert proj.values[time_key].value == "2025-06-01"


def test_combined_projection_survives_d4_30_without_fields(contract):
    """整册 combined store-projection 在 D4-30 缺 fields 时不 422（真栈事故的最小复现）。"""
    payloads = {
        "D4-30-customers": '{"customers": [{"id": "GTROW-D430-0007", "name": "客户甲"}], "customDimensions": []}',
    }
    # 不抛即通过（此前抛 JsonPathMissingSegmentError → 422）
    proj = provider.build_combined_store_projection(payloads, contract=contract)
    d30 = [k for k in proj.values if str(k).startswith("d4_30_customers/")]
    assert d30, "D4-30 字段应进 combined 投影"
