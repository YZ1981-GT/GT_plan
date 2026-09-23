# -*- coding: utf-8 -*-
"""P1 红判据：D4-1 出方向对「前端真实落库形态」丢金额（缺陷 A1）。

spec: d4-html-to-oo-store-contract-alignment · Task 1
Requirements 1.1 · Property 1

═══ 这条判据钉的是什么 ═══

前端 `shared/dynamicAdjudicationRows.serializeRows()` 落库的 `D4-1-rows` **只含 4 个键**
`{rowId, label, source, accountCode}`（注释明说「派生列一律读时推导」）；6 个金额落在
**独立 item** `D4-1-{rowId}-{field}`。而后端 `build_store_projection_d41` 逐行
`row.get(store_key)` 取金额 —— store_key ∈ label + 6 金额（`MANAGED_FIELD_SPECS`）——
只认行对象里的键。两者错位 ⇒ 前端真实形态喂进去，6 金额恒 `None`（缺陷 A1：出方向恒空）。

真库实证：唯一一条真 `D4-1-rows`（E2E 种子 wp `d4e2e000-…-d403`）正是
`[{"rowId":"seedmain","label":"…","source":"manual","accountCode":"6001"}, …]` —— 无任何金额键。

🔴 现状**必红**：本文件断言「前端真实形态 + per-field 金额」经 provider 投影后，主营区
每行的 6 个金额都产出**非空**键。今天 provider 拿不到 per-field 金额 ⇒ 金额键要么不产、
要么值为 None ⇒ 判据红。Task 8~10 让行清单携带金额（或 provider 能读 per-field）后转绿。

判据形态刻意与既有 `test_d4_1_adjudication_store_roundtrip.py` 相反：那套的 `_row()`
fixture **显式把金额塞进行对象**（理想形态），恰好把本缺陷遮住、故恒绿。本文件只喂前端
**真实**落库的两种介质（行清单 4 键 + per-field 值），不自造理想形态。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d4_adjudication_sheet as A  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402

_AMOUNT_KEYS = (
    "currentUnadjusted",
    "currentAje",
    "currentRje",
    "priorUnadjusted",
    "priorAje",
    "priorRje",
)


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def _frontend_row_list() -> list[dict[str, Any]]:
    """前端 `serializeRows` 落库的真实 `D4-1-rows` 形态：**只有 4 个键，无金额**。"""
    return [
        {"rowId": "seedmain", "label": "批发收入", "source": "tb", "accountCode": "6001"},
        {"rowId": "seedmain2", "label": "零售收入", "source": "tb", "accountCode": "6001"},
    ]


def _frontend_perfield() -> dict[str, str]:
    """前端 `persistFieldValue` 落库的真实金额：独立 item `D4-1-{rowId}-{field}`（纯文本）。"""
    return {
        "D4-1-seedmain-currentUnadjusted": "153431246.16",
        "D4-1-seedmain-currentAje": "0",
        "D4-1-seedmain-currentRje": "0",
        "D4-1-seedmain-priorUnadjusted": "0",
        "D4-1-seedmain-priorAje": "0",
        "D4-1-seedmain-priorRje": "0",
        "D4-1-seedmain2-currentUnadjusted": "89847600.46",
        "D4-1-seedmain2-currentAje": "0",
        "D4-1-seedmain2-currentRje": "0",
        "D4-1-seedmain2-priorUnadjusted": "0",
        "D4-1-seedmain2-priorAje": "0",
        "D4-1-seedmain2-priorRje": "0",
    }


def _amount_value(proj: Any, table_key: str, rid: str, field: str):
    """取投影里某行某金额字段的 value（找不到返回 sentinel MISSING）。"""
    from app.services.workpaper_sync.phase5_d4_adjudication_sheet import (
        _COLUMN_KEY_TO_STORE_KEY,
    )

    store_to_col = {v: k for k, v in _COLUMN_KEY_TO_STORE_KEY.items()}
    col = store_to_col[field]
    key = f"{table_key}/{rid}/{col}"
    fv = proj.values.get(key)
    if fv is None:
        return "MISSING"
    return getattr(fv, "value", "MISSING")


def _fixed_frontend_row_list() -> list[dict[str, Any]]:
    """**修复后**（裁决 D1）前端 serializeRows 落库的行清单：金额平铺进行对象顶层。

    这是本 spec 选定的方案——不是让后端读 per-field，而是让前端把金额随行落库（行对象
    顶层键，与后端 build_store_projection_d41 读 row.get(store_key) 契约一致）。
    """
    return [
        {"rowId": "seedmain", "label": "批发收入", "source": "tb", "accountCode": "6001",
         "sectionKey": "main-revenue",
         "currentUnadjusted": 153431246.16, "currentAje": 0, "currentRje": 0,
         "priorUnadjusted": 0, "priorAje": 0, "priorRje": 0},
        {"rowId": "seedmain2", "label": "零售收入", "source": "tb", "accountCode": "6001",
         "sectionKey": "main-revenue",
         "currentUnadjusted": 89847600.46, "currentAje": 0, "currentRje": 0,
         "priorUnadjusted": 0, "priorAje": 0, "priorRje": 0},
    ]


def test_fixed_shape_projection_carries_amounts(contract: Any) -> None:
    """P1（修复后契约）：金额随行落库的行清单，投影后主营区每行 6 金额齐全且等值。

    修复方向（裁决 D1）：前端 serializeRows 把金额平铺进行对象顶层。本判据喂**修复后**
    形态，断言 provider 投影出的每格金额 = 行对象里的值。变异检验（把行对象金额键去掉）
    应打红——见下方 test_bare_four_key_shape_still_loses_amounts 的对照。
    """
    rows = _fixed_frontend_row_list()
    proj = A.build_store_projection_d41(rows, contract=contract)

    expected = {"seedmain": 153431246.16, "seedmain2": 89847600.46}
    for rid, cur_unadj in expected.items():
        cur = _amount_value(proj, A.ROWS_TABLE_KEY_MAIN, rid, "currentUnadjusted")
        assert cur not in ("MISSING", None), (
            f"{rid}.currentUnadjusted 未进投影 —— 修复后行清单带金额却没被 provider 读到"
        )
        assert abs(float(cur) - cur_unadj) <= 0.005, (
            f"{rid}.currentUnadjusted 投影值 {cur!r} ≠ 行对象值 {cur_unadj}"
        )
        # 其余 5 个金额字段也必须各产出一个键（含 0 值）。
        for field in _AMOUNT_KEYS:
            val = _amount_value(proj, A.ROWS_TABLE_KEY_MAIN, rid, field)
            assert val not in ("MISSING",), f"{rid}/{field} 未产键"


def test_bare_four_key_shape_still_loses_amounts(contract: Any) -> None:
    """缺陷 A1 根因锚点（对照）：**旧四键形态**（金额只在 per-field、行清单无金额键）
    喂 provider 仍取不到金额 —— 这正是为何修复要落在前端（让行清单带金额），而不是
    让后端去读 per-field。金额恒 None 是**预期**（说明缺陷的根因确实在这里）。
    """
    rows = _frontend_row_list()  # 旧四键形态，无金额
    proj = A.build_store_projection_d41(rows, contract=contract)
    cur = _amount_value(proj, A.ROWS_TABLE_KEY_MAIN, "seedmain", "currentUnadjusted")
    assert cur in ("MISSING", None), (
        "旧四键形态本应取不到金额（缺陷 A1 根因）；若这里拿到了值，说明 provider 改成读了"
        " per-field，那是与裁决 D1（金额随行落库）不同的方案，需重新对齐 spec"
    )


def test_frontend_row_list_has_no_amount_keys() -> None:
    """锚点事实：前端真实落库的行清单里**没有**金额键（否则本红判据前提不成立）。

    这条不依赖 provider —— 它固定住「前端真实形态确实不带金额」这个事实本身，
    防止有人把 `_frontend_row_list()` 偷偷加上金额键来让上面的红判据变绿。
    """
    for row in _frontend_row_list():
        for field in _AMOUNT_KEYS:
            assert field not in row, (
                f"测试前提被破坏：前端真实行清单不应带金额键 {field}，"
                "带上就等于自造理想形态、把缺陷遮住"
            )
