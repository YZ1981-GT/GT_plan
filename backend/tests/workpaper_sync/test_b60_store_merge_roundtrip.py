"""B60-1 工时表的 OO→HTML 回方向判据。

═══ 这些判据为什么必须存在 ═══

B60 此前是 `store_item_registry.NON_STORE_BACKED_ADAPTERS` 的**唯一**成员，理由是
「契约无 `html_store`、字段 `store_item_id` 全 None ⇒ 纯 Excel entry，HTML 宿主不读
checklist store」。那描述的其实是「前端还没有 HTML 面」这个时点事实 ——
`b60/GtB60HourBudgetPanel.vue` 落地后同一句话就不成立了，而 OO→HTML 仍被提前跳过
⇒ 用户在 OnlyOffice 里改的行回不到结构化视图，面板空态甚至写着一句不成立的承诺
「打开在线编辑并 forcesave 后将镜像至此」。

2026-09-27 打通后，「代码写了」不等于「能工作」：`oo_to_html` 走
`getattr(bridge, plan.merge_rows_fn)`，只要符号在就不报错，**合并逻辑错了照样静默**。
所以本文件用合成 projection 真跑一遍合并，逐条钉住：

  1. 新行落库、行身份用 `rowUuid`（不是 H1 的 `rowId`、也不是 G4/G6 的 `id`）
  2. 已有行按行身份就地更新，不产生重复行
  3. `formula` 列（F `budget_cost`）**不**回写 —— 否则 Excel 算出的值会被固化成
     HTML 侧的"事实"，下次 C/D/E 变了就有两份不一致的数
  4. 幽灵行防护：只有杂散一个格的新行不落库（D4-2 用户实测缺陷的同源形态）
  5. 已存在行被清空是合法编辑，不按幽灵行剔除
  6. meta 表字段（无 `row_key`）不混进行数组
  7. `applied` 计数真实反映改动 —— `oo_to_html` 按 `applied <= 0 and base_rows`
     决定是否跳过写库，恒 0 会让回写永远不落盘
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import pilot_simple_checklist as B60  # noqa: E402

ROWS = B60.ROWS_TABLE_KEY
RID_KEY = B60.ROW_IDENTITY_STORE_KEY


@dataclass
class _FakeFieldValue:
    row_key: str | None
    value: Any
    is_protected: bool = False


class _FakeProjection:
    """最小 projection 替身：只实现 `stable_keys()` / `get()`（与既有幽灵行判据同型）。"""

    def __init__(self, items: dict[str, _FakeFieldValue]) -> None:
        self._items = items

    def stable_keys(self) -> tuple[str, ...]:
        return tuple(self._items)

    def get(self, key: str) -> _FakeFieldValue | None:
        return self._items.get(key)


def _projection(*triples: tuple[str | None, str, Any, bool]) -> _FakeProjection:
    return _FakeProjection(
        {
            f"{ROWS}/{row or '_'}/{field}": _FakeFieldValue(row, value, protected)
            for row, field, value, protected in triples
        }
    )


def test_row_identity_key_is_row_uuid_not_row_id_or_id() -> None:
    """行身份键必须是 `rowUuid` —— 三家 pilot 各不相同，照抄会静默写出不匹配的行。"""
    assert RID_KEY == "rowUuid"
    assert B60.STORE_ITEM_ID == "B60-1-hour-budget-rows"


def test_new_row_lands_with_row_uuid_identity() -> None:
    proj = _projection(
        ("u-1", "member_name", "张三", False),
        ("u-1", "budget_execution_hours", 40, False),
    )
    rows, applied, visited, touched = B60.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert len(rows) == 1
    assert rows[0][RID_KEY] == "u-1"
    assert rows[0]["member_name"] == "张三"
    assert rows[0]["budget_execution_hours"] == 40
    assert applied == 2 and visited == 2 and touched == {"u-1"}


def test_existing_row_is_updated_in_place_without_duplication() -> None:
    base = [{RID_KEY: "u-1", "member_name": "张三", "hourly_rate": 100}]
    proj = _projection(("u-1", "hourly_rate", 250, False))
    rows, applied, _visited, touched = B60.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert len(rows) == 1, "按行身份匹配失败会产生重复行"
    assert rows[0]["hourly_rate"] == 250
    assert rows[0]["member_name"] == "张三", "未被 OO 触及的字段必须原样保留"
    assert applied == 1 and touched == {"u-1"}


def test_formula_column_is_not_written_back() -> None:
    """F 列 `budget_cost`（=(C+D)*E）不得进 store —— 会造第二份事实。"""
    assert any(
        spec[0] == "budget_cost" and spec[2] == "formula"
        for spec in B60.MANAGED_FIELD_SPECS
    ), "前提变了：budget_cost 不再是 formula ⇒ 本判据须重写"

    base = [{RID_KEY: "u-1", "member_name": "张三"}]
    proj = _projection(("u-1", "budget_cost", 99999, False))
    rows, applied, visited, _touched = B60.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert "budget_cost" not in rows[0], "公式列被固化进 HTML store"
    assert applied == 0 and visited == 0


def test_protected_field_value_is_skipped() -> None:
    """`is_protected` 的格（受保护/公式）即便声明为 editable 也不回写。"""
    proj = _projection(("u-1", "member_name", "李四", True))
    rows, applied, _visited, _touched = B60.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert rows == [] and applied == 0


def test_ghost_row_dropped_when_only_a_stray_number_present() -> None:
    """只有杂散 `budget_execution_hours=0`、没有姓名的**新**行不落库。"""
    proj = _projection(("u-ghost", "budget_execution_hours", 0, False))
    rows, _applied, _visited, touched = B60.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert rows == [], "Excel Table 边界被扩展产生的空行不得进结构化视图"
    assert touched == set()


def test_ghost_row_defense_does_not_touch_pre_existing_rows() -> None:
    """已存在行被清空姓名是**合法编辑**，不得按幽灵行剔除。"""
    base = [{RID_KEY: "u-old", "member_name": "旧成员"}]
    proj = _projection(("u-old", "member_name", "", False))
    rows, applied, _visited, _touched = B60.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert len(rows) == 1 and rows[0]["member_name"] == ""
    assert applied == 1


def test_meta_fields_without_row_key_do_not_enter_rows() -> None:
    """meta 表（单位名称 / 会计期间 / 编制人…）无行身份，不得混进行数组。"""
    proj = _projection((None, "entity_name", "某公司", False))
    rows, applied, visited, _touched = B60.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert rows == [] and applied == 0 and visited == 0


def test_no_change_reports_zero_applied_so_oo_to_html_can_skip_write() -> None:
    """值未变时 `applied` 必须为 0 —— `oo_to_html` 据此跳过无意义的大 JSON 写库。"""
    base = [{RID_KEY: "u-1", "member_name": "张三"}]
    proj = _projection(("u-1", "member_name", "张三", False))
    _rows, applied, visited, touched = B60.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert applied == 0, "值相同却报 applied>0 会让每次 forcesave 都重写整个 JSON"
    assert visited == 1 and touched == set()


def test_row_order_is_preserved_with_new_rows_appended() -> None:
    base = [{RID_KEY: "u-1", "member_name": "甲"}, {RID_KEY: "u-2", "member_name": "乙"}]
    proj = _projection(("u-3", "member_name", "丙", False))
    rows, _applied, _visited, _touched = B60.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert [r[RID_KEY] for r in rows] == ["u-1", "u-2", "u-3"]


def test_all_editable_columns_are_writable_none_silently_dropped() -> None:
    """契约声明的每个 `editable` 列都真能回写 —— 漏一列就是静默丢数据。"""
    editable = [s[0] for s in B60.MANAGED_FIELD_SPECS if s[2] == "editable"]
    assert len(editable) == 8, f"editable 列数变了（实得 {len(editable)}）⇒ 本判据须复核"
    proj = _projection(
        ("u-1", "member_name", "张三", False),
        *[(("u-1"), field, f"v-{field}", False) for field in editable if field != "member_name"],
    )
    rows, applied, _visited, _touched = B60.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert len(rows) == 1
    missing = [f for f in editable if f not in rows[0]]
    assert missing == [], f"以下 editable 列未被回写（静默丢数据）：{missing}"
    assert applied == len(editable)
