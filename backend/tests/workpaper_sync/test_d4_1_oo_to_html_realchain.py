# -*- coding: utf-8 -*-
"""P4 真链判据：D4-1 OO 改动 → merge → HTML 读回等值（缺陷 A2 的反向锁）。

spec: d4-html-to-oo-store-contract-alignment · Task 11
Requirements 2.1 / 2.2 · Property 4 / Property 5

═══ 这条判据钉的是什么 ═══

缺陷 A2：OO 侧改的值经 `merge_projection_into_d41_rows` 写进 `D4-1-rows` 的**行对象**，
而旧前端从不读那里（只读 per-field item）⇒ OO 改动在 HTML 不可见。Task 8~10 把行对象
变成金额的权威载体、读侧行对象优先，本判据锁死「OO 改值 → 落行对象 → HTML 读回等于改后值」。

真链（不两端 mock —— A2 正是两端各自 mock 全绿而生产双向皆死的产物）：
  1. HTML 侧 `D4-1-rows`（含金额）→ `build_store_projection_d41` 得 projection；
  2. 模拟 OO 侧改某格金额 → 在 projection 里把该 FieldValue.value 改掉（等价 extract 出的新值）；
  3. `merge_projection_into_d41_rows(projection, base_rows=原行清单)` → 得回写后的行对象；
  4. **HTML 读侧等价**：前端 `readRowFieldWithFallback` 行对象顶层值优先 —— 后端这里断言
     行对象顶层 store_key == OO 改后的值（这就是前端会读到的值）。

同时锁 Property 5：merge 不丢 `source` / `accountCode` / 非受管 HTML-only 列
（`merge_projection_into_d41_rows` 先 `dict(row)` 整行拷贝再只覆写 7 个 store_key）。
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
from app.services.workpaper_sync.adapters.base import FieldValue, Projection  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402

_AMOUNT_KEYS = (
    "currentUnadjusted",
    "currentAje",
    "currentRje",
    "priorUnadjusted",
    "priorAje",
    "priorRje",
)
# store_key → column_key（stable_key 用 column_key）。
_STORE_TO_COL = {v: k for k, v in A._COLUMN_KEY_TO_STORE_KEY.items()}


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def _html_row(rid: str, section: str, label: str, code: str, amounts: dict) -> dict:
    """HTML 侧 D4-1-rows 的一行（含金额顶层键 + 结构键，模拟 Task 8 落库形态）。"""
    row = {
        "rowId": rid,
        "label": label,
        "source": "tb",
        "accountCode": code,
        A.SECTION_KEY_FIELD: section,
    }
    row.update(amounts)
    return row


def _stable_key_for(table_key: str, rid: str, store_key: str) -> str:
    col = _STORE_TO_COL[store_key]
    return f"{table_key}/{rid}/{col}"


def _mutate_projection_value(proj: Any, key: str, new_value: float) -> Any:
    """模拟 OO 侧改某格：在 projection 里把该 stable_key 的 FieldValue.value 换成 new_value。"""
    old = proj.values[key]
    new_values = dict(proj.values)
    new_values[key] = FieldValue(
        stable_key=old.stable_key,
        value=new_value,
        value_type=old.value_type,
        mode=old.mode,
        row_key=old.row_key,
    )
    return Projection(
        contract_id=proj.contract_id,
        semantic_version=proj.semantic_version,
        document_type=proj.document_type,
        values=new_values,
        row_keys=proj.row_keys,
    )


def _html_read_back(merged_rows: list[dict], rid: str, store_key: str):
    """前端 `readRowFieldWithFallback` 的等价读：行对象顶层值优先。

    这就是前端切回表格视图后会读到的值 —— 后端在此复刻其"行对象优先"口径。
    """
    for row in merged_rows:
        if row.get("rowId") == rid:
            return row.get(store_key, "MISSING")
    return "ROW_MISSING"


def test_oo_edit_flows_back_to_html_via_row_object(contract: Any) -> None:
    """P4：OO 改主营行 currentUnadjusted → merge → HTML 读回等于改后值。"""
    html_rows = [
        _html_row(
            "m-1", A.SECTION_KEY_MAIN, "批发收入", "6001",
            {"currentUnadjusted": 100.0, "currentAje": 0, "currentRje": 0,
             "priorUnadjusted": 0, "priorAje": 0, "priorRje": 0},
        ),
    ]
    proj = A.build_store_projection_d41(html_rows, contract=contract)

    # OO 侧把 currentUnadjusted 从 100 改成 153431246.16。
    key = _stable_key_for(A.ROWS_TABLE_KEY_MAIN, "m-1", "currentUnadjusted")
    mutated = _mutate_projection_value(proj, key, 153431246.16)

    merged, applied, _visited, touched = A.merge_projection_into_d41_rows(
        projection=mutated, base_rows=html_rows
    )
    assert applied >= 1
    assert "m-1" in touched
    # HTML 读侧（行对象优先）读回 = OO 改后值。
    got = _html_read_back(merged, "m-1", "currentUnadjusted")
    assert got != "MISSING" and got != "ROW_MISSING", "OO 改动未落进行对象 → HTML 读不回（缺陷 A2）"
    assert abs(float(got) - 153431246.16) <= 0.005, (
        f"HTML 读回 {got!r} ≠ OO 改后值 153431246.16 —— 回方向断裂"
    )


def test_oo_edit_preserves_html_only_fields(contract: Any) -> None:
    """P5：merge 回写后不丢 source / accountCode / sectionKey 等 HTML-only 列。"""
    html_rows = [
        _html_row(
            "o-1", A.SECTION_KEY_OTHER, "物流服务", "6051",
            {"currentUnadjusted": 50.0, "currentAje": 0, "currentRje": 0,
             "priorUnadjusted": 0, "priorAje": 0, "priorRje": 0},
        ),
    ]
    proj = A.build_store_projection_d41(html_rows, contract=contract)
    key = _stable_key_for(A.ROWS_TABLE_KEY_OTHER, "o-1", "currentAje")
    mutated = _mutate_projection_value(proj, key, 7.0)

    merged, _a, _v, _t = A.merge_projection_into_d41_rows(
        projection=mutated, base_rows=html_rows
    )
    row = next(r for r in merged if r.get("rowId") == "o-1")
    assert row.get("source") == "tb", "source 丢失"
    assert row.get("accountCode") == "6051", "accountCode 丢失"
    # sectionKey 由 merge 按 table_key 权威回填（其他区）。
    assert row.get(A.SECTION_KEY_FIELD) == A.SECTION_KEY_OTHER
    # 改的值到位、未改的值不动。
    assert abs(float(row["currentAje"]) - 7.0) <= 0.005
    assert abs(float(row["currentUnadjusted"]) - 50.0) <= 0.005


def test_oo_edit_derived_snapshot_survives_merge(contract: Any) -> None:
    """derivedSnapshot（HTML-only 键）必须穿过 merge 原样保留 —— 选项 b 状态机的结构依据。

    merge 先 `dict(row)` 整行拷贝、只覆写 7 个受管 store_key，故 derivedSnapshot 逐字保留。
    这条同时是裁决 D4 的结构前提：改前若 merge 会抹掉非受管键，S4 判定就无第三个量可依。
    """
    html_rows = [
        _html_row(
            "m-1", A.SECTION_KEY_MAIN, "批发", "6001",
            {"currentUnadjusted": 100.0, "currentAje": 0, "currentRje": 0,
             "priorUnadjusted": 0, "priorAje": 0, "priorRje": 0},
        ),
    ]
    # 附一个 derivedSnapshot（模拟 Task 12 写入的 snap）。
    html_rows[0]["derivedSnapshot"] = {"currentUnadjusted": 100.0}
    proj = A.build_store_projection_d41(html_rows, contract=contract)
    key = _stable_key_for(A.ROWS_TABLE_KEY_MAIN, "m-1", "currentUnadjusted")
    mutated = _mutate_projection_value(proj, key, 200.0)

    merged, _a, _v, _t = A.merge_projection_into_d41_rows(
        projection=mutated, base_rows=html_rows
    )
    row = next(r for r in merged if r.get("rowId") == "m-1")
    assert row.get("derivedSnapshot") == {"currentUnadjusted": 100.0}, (
        "derivedSnapshot 被 merge 抹掉 —— 选项 b 的 snap 第三个量丢失，S4 判定会失效"
    )
    # 覆盖值到位（stored 变 200，snap 仍 100 ⇒ 前端将判为 S2/S4）。
    assert abs(float(row["currentUnadjusted"]) - 200.0) <= 0.005
