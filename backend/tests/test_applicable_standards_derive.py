"""`derive_applicable_standards` 守卫（applicable_standards 前端全链接通 R1.3/R1.4）。

背景：披露 Tab 的门控在前端**恒为空**，一部分循环（D3）对所有项目显示
「当前项目不适用上市公司附注披露格式」→ 用户不可达；另一部分门控恒开，
允许在国企项目上编辑上市披露 Tab，而 `sync_from_workpaper` 的定位键不含
`current_standard` → 数据写进错误章节。

根因之一：DB 里是 `{entity_type, scope, stage}` 结构化对象，前端判定要的是
`soe_standalone` 这类字符串。本函数负责这层派生，且必须与前端
`normalizeApplicableStandards` 同口径（共享样本表见 `SHARED_SAMPLES`，
前端 spec `normalizeApplicableStandards.spec.ts` 用同一组样本反向锁死）。
"""
from __future__ import annotations

import pytest

from app.services.standard_unification_service import (
    DEFAULT_STANDARD,
    VALID_ENTITY_TYPES,
    VALID_SCOPES,
    derive_applicable_standards,
)

# 🔴 与前端 `normalizeApplicableStandards.spec.ts` 的 SHARED_SAMPLES 逐条对应
SHARED_SAMPLES: list[tuple[dict, list[str]]] = [
    (
        {"entity_type": "soe", "scope": "standalone", "stage": "normal"},
        ["soe_standalone", "soe", "standalone"],
    ),
    (
        {"entity_type": "listed", "scope": "consolidated", "stage": "ipo"},
        ["listed_consolidated", "listed", "consolidated"],
    ),
    (
        {"entity_type": "private", "scope": "standalone", "stage": "normal"},
        ["private_standalone", "private", "standalone"],
    ),
    # 缺 scope → 按默认补齐 standalone
    ({"entity_type": "listed"}, ["listed_standalone", "listed", "standalone"]),
    # 非法 entity_type → 回退默认 soe
    (
        {"entity_type": "foobar", "scope": "consolidated"},
        ["soe_consolidated", "soe", "consolidated"],
    ),
]


@pytest.mark.parametrize(("standard", "expected"), SHARED_SAMPLES)
def test_derive_matches_shared_samples(standard: dict, expected: list[str]) -> None:
    assert derive_applicable_standards(standard) == expected


@pytest.mark.parametrize("bad", [None, {}, {"stage": "ipo"}, {"entity_type": ""}, 123, "soe"])
def test_never_empty_and_falls_back_to_default(bad: object) -> None:
    """Property 1：任意输入都返回长度 ≥ 2 的列表（缺字段按 DEFAULT_STANDARD 补齐）。"""
    out = derive_applicable_standards(bad)  # type: ignore[arg-type]
    assert len(out) >= 2, out
    if not isinstance(bad, dict) or not bad.get("entity_type"):
        assert out[0] == f"{DEFAULT_STANDARD['entity_type']}_{DEFAULT_STANDARD['scope']}"


@pytest.mark.parametrize("entity", VALID_ENTITY_TYPES)
@pytest.mark.parametrize("scope", VALID_SCOPES)
def test_combo_first_and_deduped(entity: str, scope: str) -> None:
    """Property 2：组合值首项 + 元素去重。"""
    out = derive_applicable_standards({"entity_type": entity, "scope": scope})
    assert out[0] == f"{entity}_{scope}"
    assert len(out) == len(set(out))
    assert entity in out and scope in out


def test_stage_not_included() -> None:
    """stage 只影响 S 专项循环，不参与附注版本判定 → 不得进列表。"""
    out = derive_applicable_standards(
        {"entity_type": "listed", "scope": "standalone", "stage": "fraud_response"}
    )
    assert "fraud_response" not in out
    assert not any("fraud" in x for x in out)


def test_case_insensitive_input() -> None:
    """DB 里可能存大写（历史向导写入）→ 归一后仍命中合法枚举。"""
    assert derive_applicable_standards({"entity_type": "SOE", "scope": "CONSOLIDATED"}) == [
        "soe_consolidated", "soe", "consolidated",
    ]


def test_all_values_are_plain_strings() -> None:
    """🔴 下发给前端的必须是字符串列表 —— 原始 v2 对象会让归一函数返回 []。"""
    out = derive_applicable_standards({"entity_type": "soe", "scope": "standalone"})
    assert all(isinstance(x, str) and x for x in out)
