"""共享 kit：整表重写 ``rows`` 时必须保留 ``report_row_code``。

拦的是**两个幂等脚本互相回退**这一类缺陷：

- `fix_note_k_report_row_codes.py` 按 `report_config` 连库对账后把段首码落到行上；
- `fix_note_*_structure.py` 对齐源模板结构时会**整表重写** `rows`，而它的行骨架
  （`data_row(...)`）里不带段首码。

两者都幂等、单独跑都「0 项欠账」，但交替跑就一个抹一个补，两个 `--check`
**永远不可能同时归零**。实测形态是 K1 listed `五、8 其他应收款` 的
``rows：4 → 4 项`` —— 行数一模一样，只差一个键，看日志极易忽略。

段首码是**行的语义归属标记**（哪几行归哪个循环，`split_segments` 的唯一依据），
与结构对齐正交，故由共享 kit 统一搬运，而不是让每个结构脚本各自记得。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 11.1 / Property 39
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_KIT = _ROOT / "backend/scripts/fix/_note_structure_kit.py"


def _kit():
    spec = importlib.util.spec_from_file_location("_nsk", _KIT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_nsk"] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop("_nsk", None)
    return mod


KIT = _kit()


def test_code_is_carried_over_by_label() -> None:
    old = [
        {"label": "应收利息", "row_type": "data"},
        {"label": "应收股利", "row_type": "data"},
        {"label": "其他应收款", "row_type": "data", "report_row_code": "BS-009"},
        {"label": "合计", "row_type": "total"},
    ]
    new = [
        {"label": "应收利息", "row_type": "data"},
        {"label": "应收股利", "row_type": "data"},
        {"label": "其他应收款", "row_type": "data"},
        {"label": "合计", "is_total": True, "row_type": "total"},
    ]
    got = KIT.carry_row_codes(old, new)
    assert got[2]["report_row_code"] == "BS-009"
    # 其余行不得被凭空塞码
    assert all("report_row_code" not in r for i, r in enumerate(got) if i != 2)
    # 结构侧的其他改动（`is_total`）要照常生效
    assert got[3].get("is_total") is True


def test_position_shift_does_not_break_pairing() -> None:
    """配对按 label 而非下标 —— 结构修订插行后仍要搬对。"""
    old = [{"label": "其他应付款", "report_row_code": "BS-050"}]
    new = [
        {"label": "应付利息"},
        {"label": "应付股利"},
        {"label": "其他应付款"},
    ]
    got = KIT.carry_row_codes(old, new)
    assert [r.get("report_row_code") for r in got] == [None, None, "BS-050"]


def test_duplicate_label_is_not_guessed() -> None:
    """同名行 >1 时不搬码，并记 warning（猜错段归属比不搬更糟）。"""
    old = [
        {"label": "项目", "report_row_code": "BS-001"},
        {"label": "项目"},
    ]
    warnings: list[str] = []
    got = KIT.carry_row_codes(old, [{"label": "项目"}], table_name="T", warnings=warnings)
    assert "report_row_code" not in got[0]
    assert warnings and "重名" in warnings[0]


def test_existing_code_in_new_rows_wins() -> None:
    """新骨架自己声明了码时不覆盖（结构脚本可显式指定）。"""
    old = [{"label": "X", "report_row_code": "BS-001"}]
    got = KIT.carry_row_codes(old, [{"label": "X", "report_row_code": "BS-002"}])
    assert got[0]["report_row_code"] == "BS-002"


def test_no_codes_returns_input_unchanged() -> None:
    """旧行无码时原样返回（同一对象，零拷贝开销）。"""
    new = [{"label": "A"}]
    assert KIT.carry_row_codes([{"label": "A"}], new) is new
    assert KIT.carry_row_codes(None, new) is new


def test_apply_plan_preserves_code_end_to_end() -> None:
    """端到端：走 `apply_plan` 重写 rows 后码仍在，且**第二次跑无变更**（幂等）。"""
    section = {
        "section_number": "五、8",
        "tables": [
            {
                "name": "其他应收款",
                "rows": [
                    {"label": "应收利息", "row_type": "data"},
                    {"label": "其他应收款", "row_type": "data", "report_row_code": "BS-009"},
                ],
            }
        ],
    }
    plan = [
        {
            "aliases": ["其他应收款"],
            "rows": [
                {"label": "应收利息", "row_type": "data"},
                {"label": "其他应收款", "row_type": "data"},
            ],
        }
    ]
    changes, warnings = KIT.apply_plan(section, plan)
    rows = section["tables"][0]["rows"]
    assert rows[1].get("report_row_code") == "BS-009", (
        f"码被结构对齐抹掉了（changes={changes} warnings={warnings}）"
    )
    changes2, _ = KIT.apply_plan(section, plan)
    assert not changes2, f"第二次仍报变更 ⇒ 与段首码脚本会互相回退：{changes2}"


def test_reverse_check_without_carry_would_drop_code() -> None:
    """🔴 反向自检：绕过搬运（直接整表替换）**必然**丢码。

    没有这条，上面几条会因为「新骨架恰好也带码」之类的巧合而空转。
    """
    old = [{"label": "其他应收款", "report_row_code": "BS-009"}]
    naive = [{"label": "其他应收款", "row_type": "data"}]  # 结构脚本的原始骨架
    assert "report_row_code" not in naive[0]
    carried = KIT.carry_row_codes(old, naive)
    assert carried[0]["report_row_code"] == "BS-009"
    assert naive[0] is not carried[0], "搬运必须产出新 dict，不得就地改调用方常量"


def test_apply_plan_actually_calls_the_carrier() -> None:
    """接线自检：`apply_plan` 必须真的经过 `carry_row_codes`。

    只测 `carry_row_codes` 本身是不够的 —— 它可以完全正确却**没人调用**
    （additive 注入即死代码）。这里打桩计数，确认 rows 分支真的走了它。
    """
    calls: list[str] = []
    original = KIT.carry_row_codes

    def spy(old, new, **kw):  # noqa: ANN001, ANN202
        calls.append(str(kw.get("table_name", "")))
        return original(old, new, **kw)

    KIT.carry_row_codes = spy  # type: ignore[assignment]
    try:
        section = {"tables": [{"name": "T", "rows": [{"label": "A"}]}]}
        KIT.apply_plan(section, [{"aliases": ["T"], "rows": [{"label": "A"}]}])
    finally:
        KIT.carry_row_codes = original  # type: ignore[assignment]
    assert calls == ["T"], f"apply_plan 没有经过 carry_row_codes（calls={calls}）"


# ─────────────────────────────────────────────────────────────────────────────
# 可扩位行搬运（Task 18 / Requirement 9.1~9.2）
# ─────────────────────────────────────────────────────────────────────────────


def test_expandable_row_is_carried_before_total() -> None:
    """可扩位行必须活过整表重写，且落在末尾合计行**之前**。"""
    old = [
        {"label": "押金", "row_type": "data"},
        {"label": "可无限量添加行", "row_type": "expandable"},
        {"label": "合计", "row_type": "total"},
    ]
    new = [
        {"label": "押金", "row_type": "data"},
        {"label": "保证金", "row_type": "data"},
        {"label": "合计", "row_type": "total"},
    ]
    got = KIT.carry_expandable_rows(old, new)
    labels = [r.get("label") for r in got]
    assert labels == ["押金", "保证金", "可无限量添加行", "合计"], labels


def test_expandable_row_appended_when_no_total() -> None:
    old = [{"label": "……", "row_type": "expandable"}]
    got = KIT.carry_expandable_rows(old, [{"label": "A", "row_type": "data"}])
    assert [r.get("label") for r in got] == ["A", "……"]


def test_expandable_carry_is_idempotent() -> None:
    """新骨架已含同名可扩位行时不重复插（否则每跑一次多一行）。"""
    old = [{"label": "……", "row_type": "expandable"}, {"label": "合计", "row_type": "total"}]
    new = [{"label": "……", "row_type": "expandable"}, {"label": "合计", "row_type": "total"}]
    got = KIT.carry_expandable_rows(old, new)
    assert [r.get("label") for r in got].count("……") == 1


def test_non_expandable_placeholder_is_not_carried() -> None:
    """`row_type='data'` 的同名占位行**不搬** —— 那是要被删的垃圾行。"""
    old = [{"label": "……", "row_type": "data"}, {"label": "合计", "row_type": "total"}]
    got = KIT.carry_expandable_rows(old, [{"label": "合计", "row_type": "total"}])
    assert [r.get("label") for r in got] == ["合计"]


def test_apply_plan_preserves_expandable_end_to_end() -> None:
    """端到端：走 `apply_plan` 重写后可扩位行仍在，且第二次跑无变更（幂等）。"""
    section = {
        "tables": [
            {
                "name": "T",
                "rows": [
                    {"label": "押金", "row_type": "data"},
                    {"label": "可无限量添加行", "row_type": "expandable"},
                    {"label": "合计", "row_type": "total"},
                ],
            }
        ]
    }
    plan = [
        {
            "aliases": ["T"],
            "rows": [
                {"label": "押金", "row_type": "data"},
                {"label": "合计", "row_type": "total"},
            ],
        }
    ]
    changes, warnings = KIT.apply_plan(section, plan)
    labels = [r.get("label") for r in section["tables"][0]["rows"]]
    assert "可无限量添加行" in labels, (
        f"可扩位行被结构重写弄丢（changes={changes} warnings={warnings}）"
    )
    changes2, _ = KIT.apply_plan(section, plan)
    assert not changes2, f"第二次仍报变更 ⇒ 与可扩位脚本互相回退：{changes2}"


def test_apply_plan_actually_calls_the_expandable_carrier() -> None:
    """接线自检：`apply_plan` 必须真的经过 `carry_expandable_rows`。"""
    calls: list[str] = []
    original = KIT.carry_expandable_rows

    def spy(old, new, **kw):  # noqa: ANN001, ANN202
        calls.append(str(kw.get("table_name", "")))
        return original(old, new, **kw)

    KIT.carry_expandable_rows = spy  # type: ignore[assignment]
    try:
        section = {"tables": [{"name": "T", "rows": [{"label": "A"}]}]}
        KIT.apply_plan(section, [{"aliases": ["T"], "rows": [{"label": "A"}]}])
    finally:
        KIT.carry_expandable_rows = original  # type: ignore[assignment]
    assert calls == ["T"], f"apply_plan 没有经过 carry_expandable_rows（calls={calls}）"


def test_mid_table_expandable_keeps_relative_position() -> None:
    """表**中间**的可扩位行按「前一行 label」还原相对位置。

    源模板一张表可能有多处「此处可增行」（K6 减值准备表两处、处置组表两处）。
    若一律插到合计之前，中间那处会被挤到表尾 —— 与
    `fix_note_k_expandable_rows.py` 的 `after_label` 落位打架，两个 `--check`
    永远互相回退。
    """
    # 🔴 形态照 K6 真实数据：`（二）…` 之后还有空白录入行再到 `合计`。
    #    若把可扩位行直接挨着 `（二）subtotal` 放，`_tail_total_start` 从尾部回溯时
    #    会把它也算成「表尾汇总块」⇒ 走的是 fallback 而不是锚点分支，
    #    本条就测不到锚点（实测踩过：变异掉锚点分支仍全绿）。
    old = [
        {"label": "（一）持有待售非流动资产", "row_type": "subtotal"},
        {"label": "无形资产", "row_type": "data"},
        {"label": "……", "row_type": "expandable"},
        {"label": "（二）持有待售处置组中的资产", "row_type": "subtotal"},
        {"label": "", "row_type": "data"},
        {"label": "合计", "row_type": "total"},
    ]
    new = [
        {"label": "（一）持有待售非流动资产", "row_type": "subtotal"},
        {"label": "其中：固定资产", "row_type": "data"},
        {"label": "无形资产", "row_type": "data"},
        {"label": "（二）持有待售处置组中的资产", "row_type": "subtotal"},
        {"label": "", "row_type": "data"},
        {"label": "合计", "row_type": "total"},
    ]
    got = [r.get("label") for r in KIT.carry_expandable_rows(old, new)]
    assert got.index("……") == got.index("无形资产") + 1, got
    assert got[-1] == "合计", got


def test_tail_expandable_stays_at_data_area_end() -> None:
    """贴在表尾合计之前的可扩位行，即便骨架新增了数据行，也仍留在数据区末尾。

    与上一条相反的分支：那种落位的语义是「数据区末尾可增行」，不是
    「紧跟某一行之后」，故不能按前一行 label 还原（会被新行挤到中间）。
    """
    old = [
        {"label": "装卸费", "row_type": "data"},
        {"label": "……", "row_type": "expandable"},
        {"label": "合计", "row_type": "total"},
    ]
    new = [
        {"label": "装卸费", "row_type": "data"},
        {"label": "新增的费用项", "row_type": "data"},
        {"label": "合计", "row_type": "total"},
    ]
    got = [r.get("label") for r in KIT.carry_expandable_rows(old, new)]
    assert got == ["装卸费", "新增的费用项", "……", "合计"], got


def test_multiple_expandables_all_survive() -> None:
    """一张表两处可扩位行都要活下来（K6 的真实形态）。"""
    old = [
        {"label": "无形资产", "row_type": "data"},
        {"label": "……", "row_type": "expandable"},
        {"label": "（二）处置组", "row_type": "subtotal"},
        {"label": "", "row_type": "data"},
        {"label": "……", "row_type": "expandable"},
        {"label": "合计", "row_type": "total"},
    ]
    new = [
        {"label": "无形资产", "row_type": "data"},
        {"label": "（二）处置组", "row_type": "subtotal"},
        {"label": "", "row_type": "data"},
        {"label": "合计", "row_type": "total"},
    ]
    got = [r.get("label") for r in KIT.carry_expandable_rows(old, new)]
    assert got.count("……") == 2, got
    assert got[-1] == "合计", got
