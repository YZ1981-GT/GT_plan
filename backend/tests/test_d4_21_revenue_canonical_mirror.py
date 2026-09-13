# -*- coding: utf-8 -*-
"""D4-21 营业收入审定数 canonical 镜像（Req 3.3）单测 + 变异检验锚点。

spec: d4-21-24-oo-bidirectional-and-cross-sheet-formula · Wave 4 Task 4.2

被测：`_mirror_d4_1_revenue_to_d421` —— 把 D4-1 canonical 审定营业收入(6001) 镜像到
规范键 `D4-21-revenue-audited`，供 D4-21 前端消费（不读旧键 `D4-1-adj-tb-6001`）。
"""
from __future__ import annotations

from app.routers.wp_render_strategies._d4_operating_revenue import (
    _mirror_d4_1_revenue_to_d421,
)


def test_mirrors_d4_1_audited_revenue_to_canonical_key():
    """D4-1 已 seed 6001 ⇒ 镜像到 D4-21-revenue-audited，值一致、带溯源。"""
    snap = {"D4-1-adj-tb-6001": {"item_id": "D4-1-adj-tb-6001", "remark": "12345678.90"}}
    assert _mirror_d4_1_revenue_to_d421(snap) is True
    mirror = snap["D4-21-revenue-audited"]
    assert mirror["remark"] == "12345678.90"
    assert mirror["item_id"] == "D4-21-revenue-audited"
    # 溯源指向 D4-1 canonical，不是 D4-21 自算
    assert "D4-1" in mirror["_source_ref"] and "6001" in mirror["_source_ref"]


def test_accepts_scalar_remark_shape():
    """兼容标量形态（seed 可能直接给字符串/数值）。"""
    snap = {"D4-1-adj-tb-6001": "999.00"}
    assert _mirror_d4_1_revenue_to_d421(snap) is True
    assert snap["D4-21-revenue-audited"]["remark"] == "999.00"


def test_no_mirror_when_d4_1_missing():
    """D4-1 未 seed ⇒ 不镜像（宁缺勿造，Req 3.3 / 前端呈现「—」）。"""
    snap: dict = {}
    assert _mirror_d4_1_revenue_to_d421(snap) is False
    assert "D4-21-revenue-audited" not in snap


def test_no_mirror_when_d4_1_empty():
    """D4-1 seed 为空 ⇒ 不镜像。"""
    snap = {"D4-1-adj-tb-6001": {"remark": ""}}
    assert _mirror_d4_1_revenue_to_d421(snap) is False
    assert "D4-21-revenue-audited" not in snap
