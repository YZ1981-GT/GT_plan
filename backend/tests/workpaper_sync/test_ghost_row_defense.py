"""D1/D3/D4-2/D4-3/D5/D6/D7 `merge_projection_into_store_rows` 的幽灵行防护回归。

═══ 缺陷 ═══

用户实测（2026-09-22）：D4-2 结构化视图第 12-14 行出现「只有 rowId、没有任何客户
数据」的空行。根因：Excel Table 在最后一行边界被 Tab/Enter/拖拽扩展时，若该新行
只有**一个**杂散的 editable 格非空（复制格式带下来的 0、被顶掉的空字符串……），
这一个字段就足以让该行的 identity 通过 shell 创建关卡——而 product/customer_name/
item 等命名字段因从未在 Excel 里写入内容、根本不产出 FieldValue，永久停在初始
空值。用户在结构化视图里看到的正是这样「有 rowId、没数据」的行。

已确认排除的原因（不是本文件要挡的东西）：
  * 纯粹全空的新行（一个字段都没有值）本来就不会进 store —— 这条路径本就正确，
    不在本文件测试范围内。
  * 公式列（period_total 等 formula mode）已由 `is_protected` 挡住，不会单独
    触发 shell 创建 —— 已在生产代码验证，不需要额外测试。

═══ 修复形状 ═══

只对**本次新增**的 identity（不在 base_rows 里）加「命名字段非空」门槛；已存在
的行（无论后续被清空多少字段）永不受影响 —— 清空是合法编辑，不是幽灵行。

spec: 无独立 spec（bugfix，2026-09-22 用户实测直接定位修复）
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

import pytest  # noqa: E402

from app.services.workpaper_sync import phase5_d1_notes_receivable as D1  # noqa: E402
from app.services.workpaper_sync import phase5_d3_prepaid_receipts as D3  # noqa: E402
from app.services.workpaper_sync import phase5_d4_other_revenue_sheet as D43  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D42  # noqa: E402
from app.services.workpaper_sync import phase5_d5_receivables_financing as D5  # noqa: E402
from app.services.workpaper_sync import phase5_d6_contract_assets as D6  # noqa: E402
from app.services.workpaper_sync import phase5_d7_contract_liabilities as D7  # noqa: E402


@dataclass
class _FakeFieldValue:
    row_key: str
    value: Any
    is_protected: bool = False


class _FakeProjection:
    """最小 projection 替身：只实现 `stable_keys()` / `get()`（与既有 D2 测试同型）。"""

    def __init__(self, items: dict[str, _FakeFieldValue]) -> None:
        self._items = items

    def stable_keys(self) -> tuple[str, ...]:
        return tuple(self._items)

    def get(self, key: str) -> _FakeFieldValue | None:
        return self._items.get(key)


def _projection(table_key: str, *triples: tuple[str, str, Any, bool]) -> _FakeProjection:
    return _FakeProjection(
        {
            f"{table_key}/{row}/{field}": _FakeFieldValue(row, value, protected)
            for row, field, value, protected in triples
        }
    )


# ═══════════════════════════════════════════════════════════════════
# D4-2：主营业务收入明细表（product 命名字段，months 位置数组）
# ═══════════════════════════════════════════════════════════════════


def test_d42_ghost_row_dropped_when_only_a_stray_zero_present() -> None:
    """只有一个杂散 audit_adjustment=0 的新行不得落进 store（原缺陷复现场景）。"""
    proj = _projection(
        D42.ROWS_TABLE_KEY,
        ("rGhost", "audit_adjustment", 0, False),
    )
    rows, applied, visited, touched = D42.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert rows == [], "product 空、其余全空的新行不得落进 D4-2-rows"
    assert touched == set(), "幽灵行不得算作真正被触碰"
    assert applied == 1 and visited == 1, "遍历/应用计数不变——幽灵行只是不落库，不是没处理"


def test_d42_row_with_any_product_text_is_kept_even_if_it_looks_like_garbage() -> None:
    """product 一旦非空（即便像乱码），门槛只判「有没有」不判「像不像乱码」。

    截图第 12 行的乱码文本本身**不是**幽灵行防护要挡的东西：引擎无法区分「用户手误
    粘贴了一串乱码」与「客户名称本来就长这样」，这是业务判断，不是同步层该做的事。
    幽灵行防护只挡「命名字段完全没写过内容」这一种情况（见上面 stray_zero 场景）。
    """
    proj = _projection(
        D42.ROWS_TABLE_KEY,
        ("rFrag", "product", "g5e4628f05", False),
    )
    rows, _applied, _visited, touched = D42.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert len(rows) == 1 and rows[0]["product"] == "g5e4628f05"
    assert touched == {"rFrag"}


def test_d42_legit_new_row_with_real_product_name_is_kept() -> None:
    """OO 侧真实新增（product 有名字）必须进 store —— 幽灵行门不得误伤合法新增。"""
    proj = _projection(
        D42.ROWS_TABLE_KEY,
        ("rReal", "product", "华东经销商", False),
        ("rReal", "month_01", 1000.0, False),
    )
    rows, applied, visited, touched = D42.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert len(rows) == 1
    assert rows[0]["product"] == "华东经销商"
    assert rows[0]["months"][0] == 1000.0
    assert touched == {"rReal"}
    assert applied == 2 and visited == 2


def test_d42_existing_row_cleared_to_empty_is_preserved_not_dropped() -> None:
    """已存在的行即使被用户清空全部字段也必须原样保留——清空是合法编辑，不是幽灵行。"""
    base = [{D42.ROW_IDENTITY_STORE_KEY: "rOld", "product": "老客户", "months": [0.0] * 12}]
    proj = _projection(
        D42.ROWS_TABLE_KEY,
        ("rOld", "product", "", False),
    )
    rows, applied, _visited, touched = D42.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert len(rows) == 1, "已存在行不得因命名字段被清空而被剔除"
    assert rows[0][D42.ROW_IDENTITY_STORE_KEY] == "rOld"
    assert rows[0]["product"] == ""
    assert applied == 1 and touched == {"rOld"}


def test_d42_fully_blank_row_still_never_enters_store() -> None:
    """回归锚点：纯全空新行本就不会创建 shell（is_protected 挡住唯一的 formula 值）。"""
    proj = _projection(
        D42.ROWS_TABLE_KEY,
        ("rBlank", "period_total", 0.0, True),  # is_protected=True，模拟 formula
    )
    rows, applied, visited, touched = D42.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert rows == [] and applied == 0 and visited == 0 and touched == set()


# ═══════════════════════════════════════════════════════════════════
# D4-3：其他业务收入明细表（item 命名字段，扁平字段）
# ═══════════════════════════════════════════════════════════════════


def test_d43_ghost_row_dropped_and_legit_row_kept() -> None:
    ghost_proj = _projection(
        D43.ROWS_TABLE_KEY_D43,
        ("rGhost", "current_adjustment", 0, False),
    )
    ghost_rows, *_ = D43.merge_projection_into_d43_store_rows(
        projection=ghost_proj, base_rows=[]
    )
    assert ghost_rows == []

    real_proj = _projection(
        D43.ROWS_TABLE_KEY_D43,
        ("rReal", "item", "出租房产", False),
    )
    real_rows, applied, visited, touched = D43.merge_projection_into_d43_store_rows(
        projection=real_proj, base_rows=[]
    )
    assert len(real_rows) == 1 and real_rows[0]["item"] == "出租房产"
    assert touched == {"rReal"} and applied == 1 and visited == 1


def test_d43_existing_row_cleared_is_preserved() -> None:
    base = [{D43.ROW_IDENTITY_STORE_KEY_D43: "rOld", "item": "旧项目"}]
    proj = _projection(D43.ROWS_TABLE_KEY_D43, ("rOld", "item", "", False))
    rows, *_ = D43.merge_projection_into_d43_store_rows(projection=proj, base_rows=base)
    assert len(rows) == 1 and rows[0]["item"] == ""


# ═══════════════════════════════════════════════════════════════════
# D1：应收票据客户明细（customer_name 命名字段，flat + store_key 写法）
# ═══════════════════════════════════════════════════════════════════


def test_d1_ghost_row_dropped_and_legit_row_kept() -> None:
    ghost_proj = _projection(D1.ROWS_TABLE_KEY, ("rGhost", "current_increase", 0, False))
    ghost_rows, *_ = D1.merge_projection_into_store_rows(projection=ghost_proj, base_rows=[])
    assert ghost_rows == []

    real_proj = _projection(D1.ROWS_TABLE_KEY, ("rReal", "customer_name", "甲公司", False))
    real_rows, applied, visited, touched = D1.merge_projection_into_store_rows(
        projection=real_proj, base_rows=[]
    )
    assert len(real_rows) == 1 and real_rows[0]["customerName"] == "甲公司"
    assert touched == {"rReal"} and applied == 1 and visited == 1


def test_d1_existing_row_cleared_is_preserved() -> None:
    base = [{D1.ROW_IDENTITY_STORE_KEY: "rOld", "customerName": "旧客户"}]
    proj = _projection(D1.ROWS_TABLE_KEY, ("rOld", "customer_name", "", False))
    rows, *_ = D1.merge_projection_into_store_rows(projection=proj, base_rows=base)
    assert len(rows) == 1 and rows[0]["customerName"] == ""


# ═══════════════════════════════════════════════════════════════════
# D3：预付/预收明细（customer_name 命名字段，json_path 写法）
# ═══════════════════════════════════════════════════════════════════


def test_d3_ghost_row_dropped_and_legit_row_kept() -> None:
    ghost_proj = _projection(D3.ROWS_TABLE_KEY, ("rGhost", "debit", 0, False))
    ghost_rows, *_ = D3.merge_projection_into_store_rows(projection=ghost_proj, base_rows=[])
    assert ghost_rows == []

    real_proj = _projection(D3.ROWS_TABLE_KEY, ("rReal", "customer_name", "乙公司", False))
    real_rows, applied, visited, touched = D3.merge_projection_into_store_rows(
        projection=real_proj, base_rows=[]
    )
    assert len(real_rows) == 1 and real_rows[0]["customerName"] == "乙公司"
    assert touched == {"rReal"} and applied == 1 and visited == 1


# ═══════════════════════════════════════════════════════════════════
# D5：应收款项融资明细（item_name 命名字段在 [1]，[0] 是枚举 category）
# ═══════════════════════════════════════════════════════════════════


def test_d5_ghost_row_dropped_and_category_alone_is_not_enough() -> None:
    """只填枚举 category、不填 item_name 的新行也要按幽灵行剔除——枚举不是名称。"""
    proj = _projection(D5.ROWS_TABLE_KEY, ("rGhost", "category", "应收账款", False))
    rows, *_ = D5.merge_projection_into_store_rows(projection=proj, base_rows=[])
    assert rows == [], "只有类别没有明细项目名称的行仍是幽灵行"


def test_d5_legit_row_with_item_name_is_kept() -> None:
    proj = _projection(D5.ROWS_TABLE_KEY, ("rReal", "item_name", "应收票据贴现", False))
    rows, applied, visited, touched = D5.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert len(rows) == 1 and rows[0]["itemName"] == "应收票据贴现"
    assert touched == {"rReal"} and applied == 1 and visited == 1


# ═══════════════════════════════════════════════════════════════════
# D6：合同资产明细（contract_name 命名字段在 [1]，[0] 是整数 seq_no）
# ═══════════════════════════════════════════════════════════════════


def test_d6_ghost_row_dropped_and_seq_no_alone_is_not_enough() -> None:
    """只填 seq_no=1（合法整数真值）、不填合同名称的新行也要按幽灵行剔除。"""
    proj = _projection(D6.ROWS_TABLE_KEY, ("rGhost", "seq_no", 1, False))
    rows, *_ = D6.merge_projection_into_store_rows(projection=proj, base_rows=[])
    assert rows == [], "seq_no 是整数序号，0/1 都是合法真值，不能当命名字段用"


def test_d6_legit_row_with_contract_name_is_kept() -> None:
    proj = _projection(D6.ROWS_TABLE_KEY, ("rReal", "contract_name", "某合同", False))
    rows, applied, visited, touched = D6.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert len(rows) == 1 and rows[0]["contractName"] == "某合同"
    assert touched == {"rReal"} and applied == 1 and visited == 1


# ═══════════════════════════════════════════════════════════════════
# D7：合同负债明细（contract_name 命名字段在 [0]）
# ═══════════════════════════════════════════════════════════════════


def test_d7_ghost_row_dropped_and_legit_row_kept() -> None:
    ghost_proj = _projection(D7.ROWS_TABLE_KEY, ("rGhost", "debit_amount", 0, False))
    ghost_rows, *_ = D7.merge_projection_into_store_rows(projection=ghost_proj, base_rows=[])
    assert ghost_rows == []

    real_proj = _projection(D7.ROWS_TABLE_KEY, ("rReal", "contract_name", "某项目合同", False))
    real_rows, applied, visited, touched = D7.merge_projection_into_store_rows(
        projection=real_proj, base_rows=[]
    )
    assert len(real_rows) == 1 and real_rows[0]["contractName"] == "某项目合同"
    assert touched == {"rReal"} and applied == 1 and visited == 1


def test_d7_existing_row_cleared_is_preserved() -> None:
    base = [{D7.ROW_IDENTITY_STORE_KEY: "rOld", "contractName": "旧合同"}]
    proj = _projection(D7.ROWS_TABLE_KEY, ("rOld", "contract_name", "", False))
    rows, *_ = D7.merge_projection_into_store_rows(projection=proj, base_rows=base)
    assert len(rows) == 1 and rows[0]["contractName"] == ""
