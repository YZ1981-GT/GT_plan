# -*- coding: utf-8 -*-
"""工作簿级行变更传播 —— 计划 / 扫描 / 传播 / 收缩。

spec: excel-workbook-wide-row-change-propagation / Wave 1 Task 5
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
Properties: **P1** / **P2** / **P3**

═══ 这个模块把作用域从一张 sheet 提升到整个工作簿 ═══

上游的 `RowShiftPlan` 描述「受管 sheet 的第 N 行插入 count 行」，它对跨 sheet 引用的处理是
**逐字不动** —— 正确但不完整：正确在于不把引用改坏（表名不是坐标、别的 sheet 的行号不该跟
本 sheet 动），不完整在于**引用指向的那笔数据确实被推走了**，引用不跟着走就指向错行。

本模块引入 :class:`WorkbookRowChangePlan`：受管 sheet 的行变更 **+** 全工作簿引用侧的传播
条目清单，两者在同一份冻结声明里。

    受管 sheet 分量  ← 上游的 RowShiftPlan（insert）/ 本模块的收缩（delete）
    引用侧分量      ← PropagationEntry 清单（声明值，计划时算出）
    登记不传播       ← UnpropagatedCarrier 清单（显式计数，不静默跳过）

**静默指向错行比报错贵得多** —— 审计取数看着仍然"有值"，而值是错的。所以本模块一律
fail-closed：传播不了就抛错并放弃整次写入，绝不"传播不了就当没传播"。

═══ 为什么传播量必须是声明值 ═══

验证阶段用 `plan` 的**声明**传播量做归一化，不用实测差异（Requirement 5.1 / 5.2）。
用实测差异反推声明 = 让被检查对象自证合法 —— design.md 拒绝方案第 3 条。

═══ 零写入面 ═══

`plan_workbook_row_change` 是纯函数：不碰磁盘、不改入参、不建 DB 连接、不 commit
（Requirement 1.3 / Property 1）。冻结声明类全部 `frozen=True` 且经
`assert_no_mutation_surface` 实测无副作用能力面。
"""

from __future__ import annotations

import html
import io
import os
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Final, Iterable, Mapping

from app.services.workpaper_sync.excel_row_shift import (
    QualifiedReference,
    _rewrite_formula_refs,
    iter_qualified_references,
)
from app.services.workpaper_sync.models import SyncDomainError

__all__ = [
    # ── 异常（7 个，error_code 两两不同）──────────────────────────
    "WorkbookRowChangeError",
    "RowChangeKindError",
    "RowChangeOutOfRegionError",
    "DanglingReferenceError",
    "MissingRowIdentityError",
    "PropagationDriftError",
    "UnpropagatedCarrierError",
    # ── 类型 ────────────────────────────────────────────────────
    "RowChangeKind",
    "PROPAGATION_CARRIERS",
    "UNPROPAGATED_REASONS",
    "PropagationEntry",
    "UnpropagatedCarrier",
    "WorkbookRowChangePlan",
    "PropagationReport",
    "CARRIER_COUNTER_NAMES",
    # ── 扫描 ────────────────────────────────────────────────────
    "CarrierSite",
    "ReferenceScan",
    "scan_reference_carriers",
    # ── 声明构造（扫描 → 计划的唯一入口）──────────────────────────
    "build_propagation_entry",
    "build_insert_plan",
    "build_delete_plan",
    "plan_workbook_row_change_for_insert",
    # ── 删行侧 ──────────────────────────────────────────────────
    "DanglingSite",
    "find_undeletable_rows",
    "find_dangling_sites",
    "resolve_deleted_row_keys",
    "shrink_sheet_rows",
    # ── 应用（insert / delete 两分支）───────────────────────────
    "propagate_reference_side",
    "propagate_defined_names",
    "apply_workbook_row_change",
    "apply_workbook_row_change_to_path",
    # ── 验证侧归一化（Requirement 5）────────────────────────────
    "normalise_propagated_part",
    "assert_propagation_declared_exactly",
    # ── 结构判据入口 ────────────────────────────────────────────
    "assert_carrier_tables_consistent",
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常 —— 每个都带独立 error_code，禁止被宽泛 except 吞掉
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 **禁止 fail-open。** 每一条的「为什么不能降级」写在 docstring 里，不是注释里 ——
#    降级的诱惑总在赶工时出现，那时读的是 docstring。


class WorkbookRowChangeError(SyncDomainError):
    """工作簿级行变更域基类。"""

    error_code = "workbook_row_change_failed"


class RowChangeKindError(WorkbookRowChangeError):
    """`kind` 非 insert/delete，或 `count <= 0`。

    零变更必须表达为 `plan is None` 而不是 `count=0`：后者会让传播阶段被真实调用一次并
    产出一份「什么都没改但走过写入路径」的产物，把「没改」与「改过」混为一谈。
    """

    error_code = "workbook_row_change_kind_invalid"


class RowChangeOutOfRegionError(WorkbookRowChangeError):
    """删除区间越过受管区边界。

    越界删行会删掉未管理区的行 —— 那是 projection 无权处置的数据。
    """

    error_code = "workbook_row_change_out_of_region"


class DanglingReferenceError(WorkbookRowChangeError):
    """有引用指向被删行，且契约未声明允许。

    静默改写成别的行号会让引用指向别的数据；写 `#REF!` 会打断取数链。两者都必须由人裁决，
    不得由代码替人选（Requirement 3.4）。异常必须携带**完整**悬空清单 —— 只报第一条会让
    人以为修掉它就好了。
    """

    error_code = "workbook_row_change_dangling_reference"


class MissingRowIdentityError(WorkbookRowChangeError):
    """删行但取不到稳定业务键。

    删除是不可逆的数据丢失，无留痕不得执行（Requirement 3.7）。
    """

    error_code = "workbook_row_change_missing_row_identity"


class PropagationDriftError(WorkbookRowChangeError):
    """实测传播量 ≠ 声明传播量。

    用实测反推声明 = 让被检查对象自证合法（design.md 拒绝方案第 3 条）。
    """

    error_code = "workbook_row_change_propagation_drift"


class UnpropagatedCarrierError(WorkbookRowChangeError):
    """出现未在登记清单里的引用载体形态。

    未登记载体 = 有一类引用被静默漏改。宁可打红也不能放过 —— 漏改的后果是那类引用
    静默指向错行，而这正是本 spec 要消除的东西。
    """

    error_code = "workbook_row_change_unpropagated_carrier"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 行变更种类与载体词表（Wave 0 Gate 2 实测后的清单）
# ═══════════════════════════════════════════════════════════════════════════


class RowChangeKind(str, Enum):
    """行变更只有两种。零变更表达为 `plan is None`（Requirement 1.4）。"""

    INSERT = "insert"
    DELETE = "delete"


#: **会被传播**的载体形态 —— 封闭词表。
#:
#: 🔴 **刻意不含** `sqref` / `merge` / `hyperlink_ref`。Wave 0 Gate 2 全库 351 份实测这四类
#: 属性含跨 sheet 引用的条数为 `0/440`（`conditionalFormatting@sqref`）、`0/1223`
#: （`dataValidation@sqref`）、`0/37456`（`mergeCell@ref`）、`0/3950`（`hyperlink@ref`）——
#: 不是「样本不够」而是 **OOXML 结构性不可能**：它们的 schema 类型是 `ST_Sqref` / `ST_Ref`，
#: 语义上就是**所在 worksheet 内**的区间，表达不了 sheet 前缀。实测取值形态逐一印证
#: （`H7:M7 C7:F7 J7:J48` / `A1:R1` / `X3`，无一带 `!`）。
#:
#: 留一个恒为 0 的取值等于给「空集上恒真」留位置 —— 那类判据永远绿，且没人会发现它从未
#: 真正执行过。所以宁可让未登记载体撞 :class:`UnpropagatedCarrierError`（AC 4.2）。
PROPAGATION_CARRIERS: Final[frozenset[str]] = frozenset(
    {
        #: 引用侧 sheet 的 `<f>` 文本 —— 主载体
        "formula",
        #: `<hyperlink @location>`（实测 3,138 条工作簿内跨 sheet / 158 份模板，AC 4.5）
        "hyperlink_location",
        #: `<dataValidation>` 的 `<formula1>` / `<formula2>`（实测 8 条 / 4 份，AC 4.6）
        #: 🔴 只扫**子元素内容**，不扫整个元素 —— `error=` 属性里有中文提示文本
        #: （实测样本「请从G7-14名称列表…」），扫整个元素会把提示里的 `G7-14` 当跨 sheet
        #: 引用。这个假阳性在 Wave 0 实测中真实发生过一次。
        "data_validation",
        #: `<conditionalFormatting>` 的 `<formula>`（实测 6 条 / 1 份，AC 4.6）
        "conditional_format",
        #: `xl/workbook.xml` 的 `<definedName>`（实测 5,002 条 / 341 份，四分类见 AC 4.7）
        "defined_name",
    }
)

#: **登记但不传播**的理由 —— 封闭词表。每一类都必须显式计数，不得静默跳过。
UNPROPAGATED_REASONS: Final[frozenset[str]] = frozenset(
    {
        #: 3D 引用 `Sheet1:Sheet3!A1` —— 跨多张 sheet，无法用单一计划表达（AC 2.6）。
        #: 全库实测 **0** 处 ⇒ 该分支判据必须用注入变体，否则空集恒真。
        "three_d_reference",
        #: 外部工作簿 `[1]Sheet1!A1` —— 目标文件不在本系统管辖内（AC 9.4）。实测 2,908 处。
        "external_workbook",
        #: `xl/charts/**`（实测 8 个部件 / 1 份模板，可用真实样本，AC 4.3）
        "chart",
        #: `xl/pivotCache/**` / `xl/pivotTables/**`（全库实测 **0** 部件 ⇒ 判据须用注入变体）
        "pivot",
        #: 目标 sheet 不在本工作簿内 —— 权威模板里**已坏**的引用。
        #: 实测 definedNames 2,001 条 + `hyperlink@location` 321 条；`<f>` 侧 3,428 处 / 18 份。
        "target_not_in_workbook",
        #: 🔴 限定前缀命中、但紧随其后**取不到 A1 坐标**。
        #:
        #: 实测形态是 `'明细表D2-2'!#REF!`（D2 首要判据载体上有 **10 处**）：
        #: `_QUALIFIED_PREFIX_RE` 会命中前缀，但 `_REF_TOKEN_RE` 对 `#REF!` 返回 None。
        #: 传播器不动它是对的，但**必须登记**—— 静默跳过会让「有 10 处引用没被处理」
        #: 这件事不可见。这一类是 Task 9 实测捞出来的，原设计清单里没有。
        "prefix_without_coordinate",
    }
)

#: `PropagationReport` 的计数器名 ↔ `PropagationEntry.carrier` 的一一对应表。
#:
#: 存在的理由是让「报告字段与载体取值域一致」成为一条可执行判据，而不是靠人记 ——
#: 少一个计数器就有一类传播的处数不可见，多一个就有一个恒为 0 的字段假装被覆盖了。
CARRIER_COUNTER_NAMES: Final[Mapping[str, str]] = {
    "formula": "formulas_changed",
    "hyperlink_location": "hyperlink_locations_changed",
    "data_validation": "data_validations_changed",
    "conditional_format": "conditional_formats_changed",
    "defined_name": "defined_names_changed",
}

#: 受管 sheet 的 zip part 形态 —— `xl/worksheets/sheetN.xml`。
#:
#: 判据用它断言 part 是**解析**得来的而不是拼出来的（Property 3）。sheet 名 → part 必须走
#: `excel_structure_fingerprint._parse_workbook_xml` + `_normalise_part`：手搓正则对含中文
#: 括号、属性顺序不定的模板实测**全部失败**（B60 / H1 / G7 三份）。
_SHEET_PART_RE: Final[re.Pattern[str]] = re.compile(
    r"^xl/(?:worksheets|chartsheets)/[^/]+\.xml$"
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 冻结声明：一处传播 / 一条登记
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PropagationEntry:
    """一处引用侧改写的**冻结声明**（Requirement 1.2）。

    它是「计划时算出、验证时据以归一化」的那个值。验证阶段拿实测传播量与它比对，
    不符即 :class:`PropagationDriftError` —— 所以这里的每个字段都必须是**改写之前**就能
    确定的，不能有任何「事后填」的余地。
    """

    #: 载体形态，取值必须落在 :data:`PROPAGATION_CARRIERS` 内。
    carrier: str
    #: zip part（`defined_name` 时是 `xl/workbook.xml`）。
    part: str
    #: 载体内定位：单元格坐标 / 定义名 name / 属性所在元素序号。
    locator: str
    #: 改前引用文本，如 `'审定表K11-1'!F20`。
    ref_before: str
    #: 改后引用文本，如 `'审定表K11-1'!F21`。
    ref_after: str
    #: 🔴 **第一个真的发生位移的行号**，不是"最小行号"、也不是"唯一行号"。
    #:
    #: 这个定义是 Task 13 实测逼出来的。区间引用可以**首端点不动、末端点动**：
    #: D2 的 `_xlnm._FilterDatabase` 是 `'明细表D2-2'!$A$1:$AK$31`，`at=13` 时
    #: 行 1 不动、行 31 → 32。若按"最小行号"填就得到 `1 → 1`，于是这条**确实发生了改动**
    #: 的条目被空操作守卫拦掉（首次实测就撞在这里）。
    #:
    #: 按"第一个位移的行"填则得到 `31 → 32`，:attr:`delta` 恒等于 `±count`，
    #: 空操作守卫的语义也回到正确的「一个片段都没动」。
    #:
    #: ⚠ 不要手填这两个字段 —— 用 :func:`build_propagation_entry`，它同时保证
    #: `ref_after` 由**执行时的同一个改写器**生成。
    #:
    #: 想知道"这条 entry 含几个会被改的片段"用 :attr:`piece_count` —— 那才是与改写器
    #: `changed` 同单位的量。
    row_before: int
    row_after: int

    def __post_init__(self) -> None:
        if self.carrier not in PROPAGATION_CARRIERS:
            raise UnpropagatedCarrierError(
                f"未登记的传播载体 {self.carrier!r} —— 合法取值 "
                f"{sorted(PROPAGATION_CARRIERS)}。出现新载体形态时必须先在词表里登记并"
                "补对应判据，否则那一类引用会被静默漏改（Requirement 4.3）"
            )
        if not self.part:
            raise UnpropagatedCarrierError(
                f"传播条目缺 part（carrier={self.carrier!r}, locator={self.locator!r}）"
                " —— 没有 part 就无法定点改写，也无法在验证阶段核对"
            )
        if self.row_before < 1 or self.row_after < 1:
            raise RowChangeKindError(
                f"引用行号必须 >= 1，实得 {self.row_before} → {self.row_after}"
                f"（carrier={self.carrier!r}, locator={self.locator!r}）"
            )
        if self.row_before == self.row_after:
            # 🔴 「没改的引用」不该进传播清单：它会让声明传播量虚高，而验证阶段按声明
            #    核对实测 ⇒ 实测数对不上声明数 ⇒ 与计划一致的传播被判漂移（假红）。
            raise PropagationDriftError(
                f"传播条目的改前后行号相同（{self.row_before}）—— 未发生改动的引用不得进入"
                f"传播清单（carrier={self.carrier!r}, locator={self.locator!r}, "
                f"ref={self.ref_before!r}）"
            )
        if self.ref_before == self.ref_after:
            raise PropagationDriftError(
                f"传播条目声明行号 {self.row_before} → {self.row_after} 变了，但引用文本"
                f"逐字相同（{self.ref_before!r}）—— 两者必有一个是错的"
            )

    @property
    def delta(self) -> int:
        """行号增量。insert 为正、delete 为负。"""
        return self.row_after - self.row_before

    @property
    def piece_count(self) -> int:
        """这条 entry 含**几个行号真的变了**的 A1 片段 —— 与改写器 `changed` 同单位。

        ═══ 为什么需要这个量（Task 8 实测撞出来的）═══

        `_rewrite_formula_refs` 返回的 `changed` 是**按 A1 片段**数的：每个 `_piece` 命中
        改动就 +1。而本类是「一处引用一条」。两者单位不同，实测形态：

        | 引用 | entry 条数 | changed |
        |---|---|---|
        | `'T'!E10` | 1 | 1 |
        | `'T'!E10:F10` | 1 | **2**（两个端点都是行 10，各改一次） |
        | `'T'!$A$1:$C$34`（at=7） | 1 | **1**（只有行 34 >= 7） |

        直接用 `len(propagations)` 与 `changed` 对账，在区间引用上必然对不上 —— 那会让
        与计划完全一致的传播被判漂移（假红）。所以逐条按片段数求和。

        实现上比较 `ref_before` / `ref_after` 里逐位置的数字：不重新解析 A1 结构，因为
        「哪些片段变了」这件事**已经**由两份文本的差异完整表达了。
        """
        before = re.findall(r"\d+", self.ref_before)
        after = re.findall(r"\d+", self.ref_after)
        if len(before) != len(after):
            # 位数不同（`F9` → `F10`）不影响个数；个数不同说明两份文本结构不同
            raise PropagationDriftError(
                f"传播条目的改前后文本数字个数不同（{len(before)} vs {len(after)}）："
                f"{self.ref_before!r} → {self.ref_after!r} —— 传播只改行号，不改结构"
            )
        return sum(1 for b, a in zip(before, after) if b != a)

    def as_dict(self) -> dict[str, Any]:
        return {
            "carrier": self.carrier,
            "part": self.part,
            "locator": self.locator,
            "ref_before": self.ref_before,
            "ref_after": self.ref_after,
            "row_before": self.row_before,
            "row_after": self.row_after,
        }


@dataclass(frozen=True)
class UnpropagatedCarrier:
    """登记但**不**传播的载体 —— 必须显式计数，不得静默跳过（AC 2.6 / 4.3）。

    存在的唯一理由是让「有一类引用没被处理」这件事**可见**。静默跳过与正确处理在产物上
    分辨不出来（两者都"没报错"），只有登记计数能把两者区分开。
    """

    #: 取值必须落在 :data:`UNPROPAGATED_REASONS` 内。
    reason: str
    part: str
    #: 人可读的样本或说明 —— 供人判断「这一类真的该不传播吗」。
    detail: str
    count: int

    def __post_init__(self) -> None:
        if self.reason not in UNPROPAGATED_REASONS:
            raise UnpropagatedCarrierError(
                f"未登记的不传播理由 {self.reason!r} —— 合法取值 "
                f"{sorted(UNPROPAGATED_REASONS)}"
            )
        if self.count < 1:
            raise UnpropagatedCarrierError(
                f"不传播登记的处数必须 >= 1，实得 {self.count}（reason={self.reason!r}）"
                " —— 处数为 0 的登记等于没有这一类，留着会让空集看起来被覆盖了"
            )
        if not self.detail:
            raise UnpropagatedCarrierError(
                f"不传播登记缺 detail（reason={self.reason!r}, part={self.part!r}）—— "
                "缺样本时人无法判断这一类是否真的该不传播"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "part": self.part,
            "detail": self.detail,
            "count": self.count,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 4. 工作簿级计划（Requirement 1.1 / 1.5）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WorkbookRowChangePlan:
    """一次工作簿级行变更的**冻结**声明。零写入面。

    受管 sheet 分量 + 引用侧传播条目 + 不传播登记，三者在同一份声明里 —— 那正是本 spec 的
    要点：传播不能是事后推断（Requirement 1.1 / 1.2）。

    ═══ `at` 的语义随 `kind` 变 ═══

    * `insert` —— `at` 是**第一个新行**的行号，`at..at+count-1` 是新行区间，原来 `>= at`
      的行整体下移 `count`；
    * `delete` —— `at` 是**第一个被删行**的行号，`at..at+count-1` 是被删区间，原来
      `> at+count-1` 的行整体上移 `count`。
    """

    kind: RowChangeKind
    #: 受管 sheet 的**稳定标识**（Requirement 1.5）—— 传播必须能指明「传播的是谁的变更」。
    managed_sheet_name: str
    managed_sheet_part: str
    at: int
    count: int
    #: 仅 insert：样式来源行。delete 时必须为 None。
    style_from: int | None
    region_first_row: int
    region_last_row: int
    #: 仅 delete：被删行的业务键，供审计留痕（Requirement 3.7）。
    deleted_row_keys: tuple[str, ...] = ()
    #: 受管区内**被引用侧引用到**的行 = 删不了的行（AC 3.8 / Property 35）。
    #:
    #: 🔴 它与 `DanglingReferenceError` 是**同一条 fail-closed 语义的两个面**：后者是最后
    #: 一道拦，本字段是把拦的位置前移到 HTML 侧发起删行**之前**。理由是实测数据 ——
    #: K11 受管区 `A7:N25` 共 19 行、被引用行落在区内 19/19 = **100%**，若只有 fail-closed
    #: 抛错，删行功能表现为「永远失败」。全库 172 个组合中 82 个（47.7%）是 100% 密度。
    #:
    #: SHALL NOT 用它替代后端拦截 —— 前端标记可被绕过。
    undeletable_rows: tuple[int, ...] = ()
    propagations: tuple[PropagationEntry, ...] = ()
    unpropagated: tuple[UnpropagatedCarrier, ...] = ()

    def __post_init__(self) -> None:
        # 零副作用面实测：本类不得握有写库/提交/发事件的能力（Property 1）
        from app.services.workpaper_sync.adapters.base import (
            assert_no_mutation_surface,
        )

        assert_no_mutation_surface(self, label="WorkbookRowChangePlan")

        if not isinstance(self.kind, RowChangeKind):
            raise RowChangeKindError(
                f"kind 必须是 RowChangeKind，实得 {type(self.kind).__name__}"
                f"（{self.kind!r}）—— 用裸字符串会让 typo 静默通过"
            )
        if self.count <= 0:
            raise RowChangeKindError(
                f"行变更行数必须 > 0，实得 {self.count} —— 「不变更」应表达为 "
                "`plan is None` 而不是 `count=0`：后者会让传播阶段被真实调用一次并产出"
                "一份「什么都没改但走过写入路径」的产物，把零变更与已变更混为一谈"
                "（Requirement 1.4）"
            )
        if self.at < 1:
            raise RowChangeKindError(f"行变更起点必须 >= 1，实得 {self.at}")

        # ── 受管 sheet 标识（Requirement 1.5 / Property 3）──────────
        if not self.managed_sheet_name:
            raise RowChangeKindError(
                "计划缺 managed_sheet_name —— 传播条目无从指明「传播的是谁的变更」"
            )
        if not _SHEET_PART_RE.match(self.managed_sheet_part):
            raise RowChangeKindError(
                f"受管 sheet part 形态非法：{self.managed_sheet_part!r} —— 应形如 "
                "`xl/worksheets/sheetN.xml`。part 必须由 "
                "`excel_structure_fingerprint._parse_workbook_xml` + `_normalise_part` "
                "解析得来，不得按 sheet 顺序拼（手搓正则对 B60/H1/G7 三份模板实测全失败）"
            )

        # ── 受管区边界 ────────────────────────────────────────────
        if self.region_first_row < 1 or self.region_last_row < self.region_first_row:
            raise RowChangeOutOfRegionError(
                f"受管区行区间非法：{self.region_first_row}..{self.region_last_row}"
            )

        if self.kind is RowChangeKind.INSERT:
            self._validate_insert()
        else:
            self._validate_delete()

        self._validate_propagations()

    # ── 分 kind 校验 ──────────────────────────────────────────────

    def _validate_insert(self) -> None:
        if self.style_from is None:
            raise RowChangeKindError(
                "insert 计划必须声明 style_from —— 不给样式的新行在 Excel 里显示为默认字体"
                "无边框，那是一张「断裂」的表"
            )
        if self.style_from < 1:
            raise RowChangeKindError(f"样式来源行必须 >= 1，实得 {self.style_from}")
        if self.style_from >= self.at:
            # 判据是 `>= at` 而非 `>= at + count`：新行区间是 [at, at+count-1]，写成后者时
            # `at=26, count=2, style_from=27` 会被放过 —— 而 27 **正落在**新行区间内。
            raise RowChangeKindError(
                f"样式来源行 {self.style_from} 不小于插入点 {self.at} —— 新行区间是 "
                f"{self.at}..{self.at + self.count - 1}，样式必须来自位移后仍在原位的行"
                "（即 `< at`）"
            )
        if self.deleted_row_keys:
            raise RowChangeKindError(
                f"insert 计划不得携带 deleted_row_keys（实得 {len(self.deleted_row_keys)} 个）"
            )
        if self.undeletable_rows:
            raise RowChangeKindError(
                "insert 计划不得携带 undeletable_rows —— 那是 delete 专用的前置声明"
            )

    def _validate_delete(self) -> None:
        if self.style_from is not None:
            raise RowChangeKindError(
                f"delete 计划不得声明 style_from（实得 {self.style_from}）—— 删行不产生新行"
            )
        last_deleted = self.at + self.count - 1
        if self.at < self.region_first_row or last_deleted > self.region_last_row:
            raise RowChangeOutOfRegionError(
                f"删除区间 {self.at}..{last_deleted} 越出受管区 "
                f"{self.region_first_row}..{self.region_last_row} —— 越界删行会删掉未管理区"
                "的行，那是 projection 无权处置的数据（Requirement 3.6）"
            )
        if not self.deleted_row_keys:
            raise MissingRowIdentityError(
                f"delete 计划缺 deleted_row_keys（删除 {self.at}..{last_deleted}）—— "
                "删除是不可逆的数据丢失，无留痕不得执行（Requirement 3.7）"
            )
        if len(self.deleted_row_keys) != self.count:
            raise MissingRowIdentityError(
                f"业务键数 {len(self.deleted_row_keys)} 与被删行数 {self.count} 不符 —— "
                "留痕必须与被删行一一对应，否则事后无从复原删了哪几笔"
            )
        if len(set(self.deleted_row_keys)) != len(self.deleted_row_keys):
            raise MissingRowIdentityError(
                f"业务键有重复：{self.deleted_row_keys} —— 重复键无法一一对应到被删行"
            )
        if any(not key for key in self.deleted_row_keys):
            raise MissingRowIdentityError(
                f"业务键含空值：{self.deleted_row_keys}"
            )
        outside = sorted(
            r
            for r in self.undeletable_rows
            if not (self.region_first_row <= r <= self.region_last_row)
        )
        if outside:
            raise RowChangeOutOfRegionError(
                f"undeletable_rows 含受管区外的行 {outside} —— 该字段的定义域是受管区内"
                f"（{self.region_first_row}..{self.region_last_row}）被引用到的行"
            )

    def _validate_propagations(self) -> None:
        """传播条目的方向必须与 `kind` 一致 —— 方向错了等于把数据指到反方向。"""
        want = self.count if self.kind is RowChangeKind.INSERT else -self.count
        wrong = [e for e in self.propagations if e.delta != want]
        if wrong:
            first = wrong[0]
            raise PropagationDriftError(
                f"{len(wrong)} 条传播条目的行号增量与计划不符（应为 {want:+d}）—— "
                f"首条：{first.carrier} {first.locator} "
                f"{first.row_before} → {first.row_after}（增量 {first.delta:+d}）。"
                f"kind={self.kind.value} / count={self.count}"
            )
        duplicated = self._duplicate_locators()
        if duplicated:
            raise PropagationDriftError(
                f"传播条目出现重复定位 {duplicated[:5]}（共 {len(duplicated)} 处）—— "
                "同一处被声明两次会让声明传播量虚高，验证阶段据此核对实测必然对不上"
            )

    def _duplicate_locators(self) -> list[tuple[str, str, str]]:
        seen: set[tuple[str, str, str]] = set()
        dupes: list[tuple[str, str, str]] = []
        for entry in self.propagations:
            key = (entry.carrier, entry.part, entry.locator)
            if key in seen:
                dupes.append(key)
            seen.add(key)
        return dupes

    # ── 派生：声明值映射 ──────────────────────────────────────────

    @property
    def changed_rows(self) -> range:
        """insert 的新行区间 / delete 的被删行区间。"""
        return range(self.at, self.at + self.count)

    @property
    def region_rows(self) -> range:
        return range(self.region_first_row, self.region_last_row + 1)

    def is_deleted_row(self, row: int) -> bool:
        """`row` 是否落在被删区间内（insert 恒为 False）。"""
        return self.kind is RowChangeKind.DELETE and row in self.changed_rows

    def shift(self, row: int) -> int | None:
        """变更前行号 → 变更后行号。**被删行返回 `None`**。

        🔴 返回 `int | None` 而不是 `int`，是为了让「这一行没了」在类型上就不可忽略。
        被删行没有"变更后行号"可言：返回它自己会说谎（那个行号已被别的行占用），返回 0
        或 -1 会被当成有效行号继续参与计算。`None` 逼调用方显式处置 —— 而「显式处置悬空
        引用」正是 Requirement 3.4 的要求。

        * `insert` —— `>= at` 的行 `+count`，其余不动。**永不**返回 `None`。
        * `delete` —— 被删区间内返回 `None`；区间之后的行 `-count`；之前的不动。
        """
        if self.kind is RowChangeKind.INSERT:
            return row + self.count if row >= self.at else row
        if row in self.changed_rows:
            return None
        return row - self.count if row > self.changed_rows[-1] else row

    def unshift(self, row: int) -> int:
        """变更后行号 → 变更前行号（verifier 归一化用，Requirement 5.1）。

        🔴 **insert 的新行区间上本函数是恒等映射** —— 新行 unshift 后得到的是它自己的行号，
        而那个行号在变更**前**属于另一行真实存在的数据行。于是新行会与 before 侧的原始行
        **别名**：归一化后两侧拿同一个行号去比，digest 要么假红（新行样式继承但无值），
        要么在内容恰好相同时假绿。两种都错。

        ⇒ **新行不得进入需要归一化的集合**。它们属受管区，由受管字段判据管。这不是
        「顺带的边界」，是本函数定义域的一部分。

        delete 侧同理：被删行在变更后**不存在**，不可能出现在 after 侧的归一化输入里。
        """
        if self.kind is RowChangeKind.INSERT:
            return row - self.count if row >= self.at + self.count else row
        return row + self.count if row >= self.at else row

    # ── 派生：传播清单的聚合视图 ──────────────────────────────────

    def propagation_counts(self) -> dict[str, int]:
        """按载体统计声明的**引用处数**（entry 条数）。

        ⚠ 这**不是**与改写器 `changed` 对账用的量 —— 用它对账会在区间引用上必然对不上。
        对账用 :meth:`propagation_piece_counts`。本方法的用途是人读的规模概览
        （「D2 上有 42 处公式引用」）。
        """
        counts = {carrier: 0 for carrier in sorted(PROPAGATION_CARRIERS)}
        for entry in self.propagations:
            counts[entry.carrier] += 1
        return counts

    def propagation_piece_counts(self) -> dict[str, int]:
        """按载体统计声明的**A1 片段**数 —— 与改写器 `changed` 同单位（Requirement 5.2）。

        🔴 Task 8 实测撞出来的必要区分：`'T'!E10:F10` 是 **1 处**引用但 **2 个**片段
        （两个端点都是行 10，改写器各改一次）。`assert_matches_plan` 必须按本方法对账，
        否则区间引用会让与计划一致的传播被判漂移（假红）。
        """
        counts = {carrier: 0 for carrier in sorted(PROPAGATION_CARRIERS)}
        for entry in self.propagations:
            counts[entry.carrier] += entry.piece_count
        return counts

    def unpropagated_counts(self) -> dict[str, int]:
        counts = {reason: 0 for reason in sorted(UNPROPAGATED_REASONS)}
        for carrier in self.unpropagated:
            counts[carrier.reason] += carrier.count
        return counts

    @property
    def touched_parts(self) -> tuple[str, ...]:
        """传播会改到的 part 清单（不含受管 sheet 自身）。

        验证阶段用它判「引用侧除声明条目外是否有额外字节变化」（Requirement 5.4）——
        传播不是「允许这张 sheet 随便改」的通行证。
        """
        return tuple(
            sorted({e.part for e in self.propagations} - {self.managed_sheet_part})
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "managed_sheet_name": self.managed_sheet_name,
            "managed_sheet_part": self.managed_sheet_part,
            "at": self.at,
            "count": self.count,
            "style_from": self.style_from,
            "region": [self.region_first_row, self.region_last_row],
            "changed_rows": [self.at, self.at + self.count - 1],
            "deleted_row_keys": list(self.deleted_row_keys),
            "undeletable_rows": list(self.undeletable_rows),
            "propagation_counts": self.propagation_counts(),
            "propagation_piece_counts": self.propagation_piece_counts(),
            "unpropagated_counts": self.unpropagated_counts(),
            "touched_parts": list(self.touched_parts),
            "propagations": [e.as_dict() for e in self.propagations],
            "unpropagated": [c.as_dict() for c in self.unpropagated],
        }


# ═══════════════════════════════════════════════════════════════════════════
# 5. 实测报告（与计划的声明值对账）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PropagationReport:
    """传播逐载体的**实测**计数。

    存在的唯一理由是让守卫能断言「这条分支真的执行了」而不是「没报错」—— 一个什么都没做的
    传播函数在「产物能打开」这类判据下照样通过。

    🔴 字段与 :data:`CARRIER_COUNTER_NAMES` 一一对应，**刻意没有** `sqrefs_changed` /
    `merges_changed`：那两类结构性不可能带跨 sheet 引用（Gate 2 实测 0/440、0/1223、
    0/37456、0/3950），留一个恒为 0 的计数器等于给「空集上恒真」留位置。
    """

    formulas_changed: int = 0
    hyperlink_locations_changed: int = 0
    data_validations_changed: int = 0
    conditional_formats_changed: int = 0
    defined_names_changed: int = 0
    unpropagated_total: int = 0
    #: 悬空引用清单（delete 专用）。非空即必须已抛 :class:`DanglingReferenceError`，
    #: 或契约显式声明允许写 `#REF!`。
    dangling: tuple[str, ...] = ()
    #: 按 `UNPROPAGATED_REASONS` 分类的实测处数。
    unpropagated_by_reason: Mapping[str, int] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        negative = {
            name: getattr(self, name)
            for name in CARRIER_COUNTER_NAMES.values()
            if getattr(self, name) < 0
        }
        if negative or self.unpropagated_total < 0:
            raise PropagationDriftError(
                f"实测计数出现负值：{negative or self.unpropagated_total} —— "
                "计数器只应递增，负值说明有分支在做减法补偿"
            )
        unknown = sorted(set(self.unpropagated_by_reason) - UNPROPAGATED_REASONS)
        if unknown:
            raise UnpropagatedCarrierError(
                f"实测报告里出现未登记的不传播理由 {unknown} —— 合法取值 "
                f"{sorted(UNPROPAGATED_REASONS)}"
            )

    @property
    def total_changed(self) -> int:
        return sum(getattr(self, name) for name in CARRIER_COUNTER_NAMES.values())

    def counts_by_carrier(self) -> dict[str, int]:
        """与 `WorkbookRowChangePlan.propagation_counts()` 同形，便于逐载体对账。"""
        return {
            carrier: getattr(self, counter)
            for carrier, counter in sorted(CARRIER_COUNTER_NAMES.items())
        }

    def assert_matches_plan(self, plan: WorkbookRowChangePlan) -> None:
        """实测 ≠ 声明即 fail-closed（Requirement 5.2 / Property 21）。

        🔴 这是本 spec 「不许被检查对象自证合法」的落点：归一化用的是**计划时冻结的声明
        值**，本函数确认实测确实等于它。反过来（用实测反推声明）等于让被检查对象自己声明
        自己合法 —— design.md 拒绝方案第 3 条。

        逐载体比对而不只比总数：两个载体一个多改一个少改，总数会互相抵消。

        🔴 用 `propagation_piece_counts()`（**A1 片段**数）而不是 `propagation_counts()`
        （引用处数）—— 报告的计数器来自改写器的 `changed`，那是按片段计的。用引用处数
        对账会在区间引用（`E10:F10` = 1 处 / 2 片段）上必然对不上，把与计划完全一致的
        传播判成漂移。这是 Task 8 在全库一致性取证时实测撞出来的，12 处不吻合全是这个形态。
        """
        declared = plan.propagation_piece_counts()
        measured = self.counts_by_carrier()
        mismatched = {
            carrier: (declared[carrier], measured[carrier])
            for carrier in sorted(PROPAGATION_CARRIERS)
            if declared[carrier] != measured[carrier]
        }
        if mismatched:
            detail = ", ".join(
                f"{c}: 声明 {d} / 实测 {m}" for c, (d, m) in mismatched.items()
            )
            raise PropagationDriftError(
                f"实测传播量与声明不符（{detail}）—— 传播量必须是计划时的声明值，"
                "用实测反推声明等于让被检查对象自证合法（Requirement 5.2）"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.counts_by_carrier(),
            "total_changed": self.total_changed,
            "unpropagated_total": self.unpropagated_total,
            "unpropagated_by_reason": dict(sorted(self.unpropagated_by_reason.items())),
            "dangling": list(self.dangling),
        }


def assert_carrier_tables_consistent() -> Mapping[str, tuple[str, ...]]:
    """载体词表与报告字段**双向**锁死 —— 结构判据，不是靠人记。

    三条同时成立才返回，否则抛：

    1. :data:`CARRIER_COUNTER_NAMES` 的键集 == :data:`PROPAGATION_CARRIERS`；
    2. 每个计数器名都是 :class:`PropagationReport` 的真实字段；
    3. `PropagationReport` 没有多出「像计数器但不在表里」的 `*_changed` 字段。

    第 3 条防的是本仓库反复踩的形态：加一类载体时只改一处，另一处静默漏掉。漏在报告侧
    ⇒ 那类传播的处数不可见；漏在词表侧 ⇒ 报告里多一个恒为 0 的字段假装被覆盖了。
    """
    from dataclasses import fields as dataclass_fields

    missing_carrier = sorted(PROPAGATION_CARRIERS - set(CARRIER_COUNTER_NAMES))
    if missing_carrier:
        raise UnpropagatedCarrierError(
            f"载体 {missing_carrier} 在 CARRIER_COUNTER_NAMES 里没有对应计数器 —— "
            "那一类传播的处数将不可见"
        )
    extra_carrier = sorted(set(CARRIER_COUNTER_NAMES) - PROPAGATION_CARRIERS)
    if extra_carrier:
        raise UnpropagatedCarrierError(
            f"CARRIER_COUNTER_NAMES 里的 {extra_carrier} 不在 PROPAGATION_CARRIERS 内 —— "
            "计数器走在词表前面时，词表就不再是「传播载体的完整清单」"
        )

    report_fields = {f.name for f in dataclass_fields(PropagationReport)}
    absent = sorted(set(CARRIER_COUNTER_NAMES.values()) - report_fields)
    if absent:
        raise UnpropagatedCarrierError(
            f"计数器 {absent} 不是 PropagationReport 的字段 —— 表与类型已漂移"
        )
    stray = sorted(
        name
        for name in report_fields
        if name.endswith("_changed") and name not in set(CARRIER_COUNTER_NAMES.values())
    )
    if stray:
        raise UnpropagatedCarrierError(
            f"PropagationReport 有未登记的计数器字段 {stray} —— 要么它对应的载体没进词表"
            "（那类传播不受判据保护），要么它是个恒为 0 的死字段（给空集恒真留位置）"
        )
    return {
        "carriers": tuple(sorted(PROPAGATION_CARRIERS)),
        "counters": tuple(sorted(CARRIER_COUNTER_NAMES.values())),
        "unpropagated_reasons": tuple(sorted(UNPROPAGATED_REASONS)),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. 扫描：全工作簿找指向受管 sheet 的引用（Requirement 4）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 **分词一律走 `iter_qualified_references`**（`excel_row_shift` 的权威分词器），本模块
#    不另写一个扫描器。理由是扫描与改写必须**同口径**：扫描认为某处是引用而改写器不认
#    （或反之）会产出「声明传播量与实测对不上」的假红；漏扫一类载体更糟 —— 那类引用会
#    静默指向错行，而这正是本 spec 要消除的东西。
#
#    `test_scanner_agrees_with_rewriter_on_whole_corpus` 在全库 351 份上取证这一致性。

_F_TEXT_RE: Final[re.Pattern[str]] = re.compile(
    r"<f\b[^>]*?(?:/>|>(?P<text>.*?)</f>)", re.S
)
_CELL_RE: Final[re.Pattern[str]] = re.compile(
    r"<c\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</c>)", re.S
)
_HYPERLINK_RE: Final[re.Pattern[str]] = re.compile(r"<hyperlink\b(?P<attrs>[^>]*?)/?>")
#: 🔴 只取 `<formula1>` / `<formula2>` 的**内容**，不是整个 `<dataValidation>` 元素。
#:
#: 全库 351 份实测的两类风险，规模差别很大，别搞混：
#:
#: | 风险 | 载体 | 实测规模 | 谁挡住它 |
#: |---|---|---|---|
#: | 提示文本里有 sheet 名样子的串 | `prompt=` / `error=` 属性 | **0** 处会被误判 | 只扫 `<formula*>` 内容 |
#: | 字符串字面量里的中文感叹号 | `<formula>` 内容本身 | **32 / 41** 处 | 分词器跳字面量 |
#:
#: 第一类是**结构性预防**：`prompt=` 里确实有「根据D2-2 审计调整前的账龄数据填写」这种
#: 含 sheet 名（`D2-2`）的中文提示（实测 14 处），但它后面没有 `!`，`_QUALIFIED_PREFIX_RE`
#: 不会命中 ⇒ 分词器实测误判 0 处。只扫子元素内容是为了不依赖这个巧合。
#:
#: 第二类是**真实发生的**：`<conditionalFormatting><formula>` 里 41 处含 `!` 的，有
#: **32 处**是 `"报表未调平!"` / `"调整事项未全部链入试算平衡表…!"` 这类中文感叹号 ——
#: 按 `!` 粗暴 grep 会把它们全算成跨 sheet 引用。真跨 sheet 的只有 9 处
#: （`Data!$B$2` 一类 + `[1]Data!#REF!` 外部工作簿）。挡住它的是分词器跳字符串字面量，
#: 而那正是「扫描必须走 `iter_qualified_references`、不得自己 grep」的实证理由。
_DV_FORMULA_RE: Final[re.Pattern[str]] = re.compile(
    r"<formula(?P<idx>[12])\b[^>]*>(?P<text>.*?)</formula(?P=idx)>", re.S
)
_CF_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"<conditionalFormatting\b(?P<attrs>[^>]*)>(?P<body>.*?)</conditionalFormatting>",
    re.S,
)
_CF_FORMULA_RE: Final[re.Pattern[str]] = re.compile(
    r"<formula\b[^>]*>(?P<text>.*?)</formula>", re.S
)
_DV_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"<dataValidation\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</dataValidation>)", re.S
)
_ATTR_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _attr(attrs: str, name: str) -> str | None:
    pattern = _ATTR_RE_CACHE.get(name)
    if pattern is None:
        pattern = re.compile(rf'\b{re.escape(name)}="([^"]*)"')
        _ATTR_RE_CACHE[name] = pattern
    found = pattern.search(attrs)
    return found.group(1) if found else None


def _unescape(raw: str) -> str:
    """XML 实体还原，**含数字字符引用**（`&#22351;`）。

    🔴 必须认数字字符引用，否则 sheet 名会被当成实体串。实测（全库 351 份）：**2,591 处**
    公式的 sheet 名写成 `&#24213;&#31295;&#30446;&#24405;!A2`（= `底稿目录!A2`），
    分布在 6 份模板（G4 / G5 / G6 / G7 / H1 / H10）。其中 **1,842 处**在不还原时
    取到的名字**命中不到**任何真实 sheet 名 ⇒ 与 `propagate_sheets` 比对必然失配
    ⇒ 那些引用被静默漏传播。

    用 `html.unescape` 而不是手写五个 `.replace()`：手写版认不出 `&#\\d+;` / `&#x..;`，
    而这正是上面那 2,591 处的形态。`&amp;` 的顺序问题也由标准库处理。
    """
    return html.unescape(raw)


def _escape(text: str) -> str:
    """回写公式文本时的最小转义 —— 只处理 XML 必须转义的三个字符。

    ⚠ **不**把中文重新写成数字字符引用：那是 Excel 生成器的历史习惯，不是语义的一部分。
    还原后的中文以 UTF-8 直接写入，Excel 读得出来（part 声明的就是 UTF-8）。

    代价是「被改写的那条公式」的字节形态与原文不同（`&#24213;` → `底`）。这是可接受的：
    那条公式**本来就要改**。未被改写的公式一律**原样保留**，不经过本函数
    —— 见 :func:`_rewrite_text_preserving_unchanged`。
    """
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _rewrite_text_preserving_unchanged(
    escaped: str, rewrite: Callable[[str], tuple[str, int]]
) -> tuple[str, int]:
    """在**还原后**的文本上改写；没改动时把**原始字节**原样退回。

    🔴 这个「没改就退回原文」的动作是本函数存在的唯一理由。若无条件走
    「还原 → 改写 → 重新转义」，那些**没有任何改动**的公式也会因转义风格变化而产生字节
    差异（`&#24213;` → `底`、`&apos;` → `'`）—— 于是「除声明条目外零字节变化」这条
    验证判据（Requirement 5.4）会对一大批无关公式报警，把真正的越权改动淹掉。
    """
    plain = _unescape(escaped)
    rewritten, changed = rewrite(plain)
    if changed == 0:
        return escaped, 0
    return _escape(rewritten), changed


@dataclass(frozen=True)
class CarrierSite:
    """扫到的一处引用位置（尚未决定怎么改）。

    与 :class:`PropagationEntry` 的区别：本类是**观测**（扫描产出），后者是**声明**
    （计划产出）。观测里含「指向别的 sheet」「取不到坐标」这些不会变成声明的位置，
    所以两者不能合并 —— 合并会让「扫到了」与「要改」混为一谈。
    """

    carrier: str
    part: str
    locator: str
    #: 分词结果本体。
    reference: QualifiedReference

    @property
    def rows(self) -> tuple[int, ...]:
        """字面行号（区间端点）—— 传播时要改的数字。"""
        return self.reference.rows

    @property
    def covered_rows(self) -> tuple[int, ...]:
        """覆盖的全部行（区间内部展开）—— 判「某行是否被引用到」时用它。"""
        return self.reference.covered_rows

    def as_dict(self) -> dict[str, Any]:
        return {
            "carrier": self.carrier,
            "part": self.part,
            "locator": self.locator,
            "kind": self.reference.kind,
            "sheet_name": self.reference.sheet_name,
            "token": self.reference.token,
            "raw": self.reference.raw,
            "rows": list(self.rows),
        }


@dataclass(frozen=True)
class ReferenceScan:
    """一次全工作簿扫描的结果。只读，不含任何改写决定。"""

    #: 指向**目标 sheet**、且能定位到行号的引用 —— 传播候选。
    sites: tuple[CarrierSite, ...]
    #: 登记不传播的载体（按 reason 聚合）。
    unpropagated: tuple[UnpropagatedCarrier, ...]
    #: 目标 sheet 上被引用到的行 —— **字面**行号（区间端点），升序去重。
    #:
    #: 与清册 `referenced_rows` 同口径（D2 实测 `[13, 25, 26]`），便于两侧对账。
    referenced_rows: tuple[int, ...]
    #: 被引用**覆盖**的行（区间内部展开），升序去重。
    #:
    #: ⚠ 它**不是** `undeletable_rows`。覆盖面可以很大（D2 的 `Print_Area` 是 `$A$1:$AM$34`
    #: ⇒ 覆盖 34 行），把它直接当不可删行会让删行功能表现为「永远失败」。「哪些行真的不可
    #: 删」由 Requirement 3 的删行侧裁决（Wave 3 Task 16），本字段只提供事实。
    covered_rows: tuple[int, ...]
    #: 分母：扫过的 part 数 / 分词出的限定引用总数。用于判「扫描面没有被悄悄改小」。
    parts_scanned: int
    qualified_total: int

    def counts_by_carrier(self) -> dict[str, int]:
        counts = {carrier: 0 for carrier in sorted(PROPAGATION_CARRIERS)}
        for site in self.sites:
            counts[site.carrier] += 1
        return counts

    def counts_by_reason(self) -> dict[str, int]:
        counts = {reason: 0 for reason in sorted(UNPROPAGATED_REASONS)}
        for carrier in self.unpropagated:
            counts[carrier.reason] += carrier.count
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "sites": len(self.sites),
            "counts_by_carrier": self.counts_by_carrier(),
            "counts_by_reason": self.counts_by_reason(),
            "referenced_rows": list(self.referenced_rows),
            "covered_rows": list(self.covered_rows),
            "parts_scanned": self.parts_scanned,
            "qualified_total": self.qualified_total,
        }


def plan_workbook_row_change_for_insert(
    entries: Mapping[str, bytes],
    *,
    managed_sheet_name: str,
    managed_sheet_part: str,
    insert_at: int,
    count: int,
    style_from: int,
    region_first_row: int,
    region_last_row: int,
) -> WorkbookRowChangePlan | None:
    """从 zip **entries** 直接生成插行的工作簿级计划。计划期入口（Requirement 1.1）。

    `plan_managed_writes` 手上是 `Mapping[str, bytes]` 而不是 `ZipFile`，所以需要这个
    门面。它把 entries 装回内存 zip 再走 :func:`scan_reference_carriers` ——
    **不**另写一份扫描逻辑（抄第二份必然与执行侧漂移）。

    Returns:
        计划；若工作簿里**没有**任何跨 sheet 引用指向受管 sheet 则返回 `None`
        ⇒ 调用方据此保持「与本 spec 之前逐字节相同」的零传播路径。
    """
    from app.services.excel_structure_fingerprint import (
        _normalise_part,
        _parse_workbook_xml,
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as out:
        for name, payload in entries.items():
            out.writestr(name, payload)
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as zf:
        sheets, defined = _parse_workbook_xml(zf)
        sheet_parts = {s["name"]: _normalise_part(s["rel_target"]) for s in sheets}
        scan = scan_reference_carriers(
            zf,
            target_sheet=managed_sheet_name,
            sheet_parts=sheet_parts,
            defined_names=defined,
        )
    if not scan.sites:
        return None
    plan = build_insert_plan(
        scan,
        managed_sheet_name=managed_sheet_name,
        managed_sheet_part=managed_sheet_part,
        at=insert_at,
        count=count,
        style_from=style_from,
        region_first_row=region_first_row,
        region_last_row=region_last_row,
    )
    if not plan.propagations:
        # 有引用但一条都不需要改（全在插入点之上）⇒ 同样走零传播路径。
        return None
    return plan


def scan_reference_carriers(
    zf: zipfile.ZipFile,
    *,
    target_sheet: str,
    sheet_parts: Mapping[str, str],
    defined_names: Iterable[Mapping[str, Any]] = (),
) -> ReferenceScan:
    """扫全工作簿，找出指向 `target_sheet` 的引用（Requirement 4.1）。

    ═══ 载体清单（Wave 0 Gate 2 全库 351 份实测后定稿）═══

    **传播**（5 类，见 :data:`PROPAGATION_CARRIERS`）：

    | 载体 | 实测规模 |
    |---|---|
    | `<f>` 文本 | 主载体，144,154 处限定引用 |
    | `hyperlink@location` | 3,138 条工作簿内跨 sheet / 158 份模板 |
    | `definedName` | 5,002 条跨 sheet（四分类见下） |
    | `dataValidation/formula1|2` | 8 条 / 4 份 |
    | `conditionalFormatting/formula` | 6 条 / 1 份 |

    **不是载体**（结构性不可能，AC 4.2）：`conditionalFormatting@sqref`（0/440）、
    `dataValidation@sqref`（0/1223）、`mergeCell@ref`（0/37456）、`hyperlink@ref`
    （0/3950）—— OOXML 类型是 `ST_Sqref` / `ST_Ref`，语义上就是所在 worksheet 内的区间，
    表达不了 sheet 前缀。**本函数刻意不扫它们**：扫一个恒为 0 的地方等于给「空集上恒真」
    留位置。

    🔴 `dataValidation` / `conditionalFormatting` 只扫 `<formula*>` 子元素的**内容**，
    绝不扫整个元素；且分词一律走 `iter_qualified_references`（它跳字符串字面量）。
    两条防线各挡一类实测风险，见 :data:`_DV_FORMULA_RE` 上方的对照表 —— 其中「字符串
    字面量里的中文感叹号」是**真实发生**的（41 处含 `!` 的 cf 公式里 32 处是它）。

    Args:
        zf: 已打开的 xlsx（只读）。
        target_sheet: 受管 sheet 名 —— 只有指向它的引用才进 `sites`。
        sheet_parts: `{sheet 名: zip part}`，**必须**由
            `excel_structure_fingerprint._parse_workbook_xml` + `_normalise_part` 解析得来
            （AC 6.5 禁止按 sheet 名或顺序猜）。
        defined_names: `_parse_workbook_xml` 的第二个返回值。

    Returns:
        :class:`ReferenceScan`。指向别的 sheet 的引用**不进** `sites` 也**不**登记为
        不传播 —— 它们与本次变更无关，登记它们会让不传播计数被无关项淹没。
    """
    names_in_zip = set(zf.namelist())
    known_sheets = set(sheet_parts)
    sites: list[CarrierSite] = []
    reasons: Counter[str] = Counter()
    samples: dict[str, str] = {}
    reason_parts: dict[str, str] = {}
    qualified_total = 0
    parts_scanned = 0

    def _note(reason: str, part: str, sample: str) -> None:
        reasons[reason] += 1
        samples.setdefault(reason, sample)
        reason_parts.setdefault(reason, part)

    def _classify(
        ref: QualifiedReference, *, carrier: str, part: str, locator: str
    ) -> None:
        """把一处分词结果归入 sites / 不传播登记 / 无关三者之一。"""
        nonlocal qualified_total
        qualified_total += 1

        if ref.kind == "three_d":
            _note("three_d_reference", part, ref.raw)
            return
        if ref.kind == "external":
            _note("external_workbook", part, ref.raw)
            return
        if ref.kind == "no_target":
            # 🔴 前缀命中但取不到坐标（`'明细表D2-2'!#REF!`，D2 上 10 处）。
            #    只登记指向**目标 sheet** 的那些 —— 指向别的 sheet 的坏引用与本次变更无关。
            if ref.sheet_name == target_sheet:
                _note("prefix_without_coordinate", part, ref.raw)
            return
        if ref.sheet_name not in known_sheets:
            # 权威模板里**已坏**的引用（目标 sheet 不在本工作簿内）
            _note("target_not_in_workbook", part, ref.raw)
            return
        if ref.sheet_name != target_sheet:
            return  # 指向别的 sheet：与本次变更无关，不登记
        if not ref.rows:
            return  # 整列区间 `$A:$C`：不含行号，传播它无意义也无从传播

        sites.append(
            CarrierSite(carrier=carrier, part=part, locator=locator, reference=ref)
        )

    # ── ① 逐 sheet 扫 <f> / hyperlink@location / dv / cf ────────────
    for sheet_name, part in sorted(sheet_parts.items()):
        if part not in names_in_zip:
            continue
        parts_scanned += 1
        xml = zf.read(part).decode("utf-8", "replace")

        for cell in _CELL_RE.finditer(xml):
            body = cell.group("body")
            if not body or "<f" not in body:
                continue
            coord = _attr(cell.group("attrs") or "", "r") or "?"
            for fmatch in _F_TEXT_RE.finditer(body):
                text = _unescape(fmatch.group("text") or "")
                for ref in iter_qualified_references(text, current_sheet=sheet_name):
                    _classify(ref, carrier="formula", part=part, locator=coord)

        for link in _HYPERLINK_RE.finditer(xml):
            attrs = link.group("attrs") or ""
            location = _attr(attrs, "location")
            if not location:
                continue
            anchor = _attr(attrs, "ref") or "?"
            for ref in iter_qualified_references(
                _unescape(location), current_sheet=sheet_name
            ):
                _classify(
                    ref, carrier="hyperlink_location", part=part, locator=anchor
                )

        for dv in _DV_BLOCK_RE.finditer(xml):
            body = dv.group("body") or ""
            anchor = _attr(dv.group("attrs") or "", "sqref") or "?"
            for f in _DV_FORMULA_RE.finditer(body):
                text = _unescape(f.group("text") or "")
                for ref in iter_qualified_references(text, current_sheet=sheet_name):
                    _classify(
                        ref,
                        carrier="data_validation",
                        part=part,
                        locator=f"{anchor}/formula{f.group('idx')}",
                    )

        for block in _CF_BLOCK_RE.finditer(xml):
            anchor = _attr(block.group("attrs") or "", "sqref") or "?"
            for f in _CF_FORMULA_RE.finditer(block.group("body") or ""):
                text = _unescape(f.group("text") or "")
                for ref in iter_qualified_references(text, current_sheet=sheet_name):
                    _classify(
                        ref,
                        carrier="conditional_format",
                        part=part,
                        locator=f"{anchor}/formula",
                    )

    # ── ② definedNames（在 xl/workbook.xml 上）─────────────────────
    for dn in defined_names:
        raw_ref = str(dn.get("ref") or "")
        if not raw_ref:
            continue
        name = str(dn.get("name") or "?")
        for ref in iter_qualified_references(_unescape(raw_ref)):
            _classify(
                ref, carrier="defined_name", part="xl/workbook.xml", locator=name
            )

    # ── ③ 登记不传播的部件类（chart / pivot）───────────────────────
    charts = sorted(n for n in names_in_zip if n.startswith("xl/charts/"))
    if charts:
        reasons["chart"] += len(charts)
        samples.setdefault("chart", charts[0])
        reason_parts.setdefault("chart", charts[0])
    pivots = sorted(
        n
        for n in names_in_zip
        if n.startswith("xl/pivotCache/") or n.startswith("xl/pivotTables/")
    )
    if pivots:
        reasons["pivot"] += len(pivots)
        samples.setdefault("pivot", pivots[0])
        reason_parts.setdefault("pivot", pivots[0])

    unpropagated = tuple(
        UnpropagatedCarrier(
            reason=reason,
            part=reason_parts.get(reason, "xl/workbook.xml"),
            detail=samples.get(reason, reason),
            count=count,
        )
        for reason, count in sorted(reasons.items())
        if count
    )
    return ReferenceScan(
        sites=tuple(sites),
        unpropagated=unpropagated,
        referenced_rows=tuple(sorted({r for s in sites for r in s.rows})),
        covered_rows=tuple(sorted({r for s in sites for r in s.covered_rows})),
        parts_scanned=parts_scanned,
        qualified_total=qualified_total,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. 引用侧定点改写（Requirement 2.1 的写入半）
# ═══════════════════════════════════════════════════════════════════════════


def propagate_reference_side(
    xml: str,
    *,
    target_sheet: str,
    remap: Callable[[int], int],
) -> tuple[str, dict[str, int]]:
    """在一张**引用侧** sheet 的 XML 上改写指向 `target_sheet` 的引用。

    ═══ 三条纪律 ═══

    1. **`qualified_only=True`** —— 只改带前缀的引用。裸引用（`A20`）属于这张 sheet
       自己，没人在它上面插行；一起推走会让它自己的坐标全部错位（产物仍能打开 ⇒
       静默错行）。Task 10 实测撞出来的，见该参数的 docstring。
    2. **先还原实体再改写** —— 见 :func:`_unescape`：2,591 处公式把 sheet 名写成
       `&#24213;&#31295;&#30446;&#24405;`，不还原就命中不到 `target_sheet`。
    3. **没改动的载体原样退回** —— 见 :func:`_rewrite_text_preserving_unchanged`。

    ⚠ 只碰 :data:`PROPAGATION_CARRIERS` 里的五类，且 `dataValidation` /
    `conditionalFormatting` 只碰 `<formula*>` 子元素的**内容**（不碰 `prompt=` /
    `error=` 属性，也不碰任何 `sqref` / `ref`）。

    Returns:
        `(新 XML, {载体: 改动的 A1 片段数})`。片段数与
        `_rewrite_formula_refs` 的 `changed` 同单位，供与声明对账。
    """
    propagate = frozenset({target_sheet})
    counts: dict[str, int] = {c: 0 for c in PROPAGATION_CARRIERS}

    def _rewrite(plain: str) -> tuple[str, int]:
        return _rewrite_formula_refs(
            plain,
            remap=remap,
            propagate_sheets=propagate,
            qualified_only=True,
        )

    def _sub_formula_text(body: str, carrier: str, pattern: re.Pattern[str]) -> str:
        def _one(match: re.Match[str]) -> str:
            escaped = match.group("text") or ""
            if not escaped:
                return match.group(0)
            new_text, changed = _rewrite_text_preserving_unchanged(escaped, _rewrite)
            if changed == 0:
                return match.group(0)
            counts[carrier] += changed
            whole = match.group(0)
            start, end = match.span("text")
            offset = match.start()
            return whole[: start - offset] + new_text + whole[end - offset :]

        return pattern.sub(_one, body)

    # ── ① 单元格 `<f>` ────────────────────────────────────────────
    def _one_cell(match: re.Match[str]) -> str:
        body = match.group("body")
        if not body or "<f" not in body:
            return match.group(0)
        new_body = _sub_formula_text(body, "formula", _F_TEXT_RE)
        if new_body == body:
            return match.group(0)
        whole = match.group(0)
        start, end = match.span("body")
        offset = match.start()
        return whole[: start - offset] + new_body + whole[end - offset :]

    out = _CELL_RE.sub(_one_cell, xml)

    # ── ② `<hyperlink @location>` ────────────────────────────────
    def _one_link(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        location = _attr(attrs, "location")
        if not location:
            return match.group(0)
        new_location, changed = _rewrite_text_preserving_unchanged(location, _rewrite)
        if changed == 0:
            return match.group(0)
        counts["hyperlink_location"] += changed
        # 只替换 `location="..."` 的值，其余属性逐字不动
        new_attrs = attrs.replace(
            f'location="{location}"', f'location="{new_location}"', 1
        )
        return match.group(0).replace(attrs, new_attrs, 1)

    out = _HYPERLINK_RE.sub(_one_link, out)

    # ── ③ `<dataValidation>` 的 `<formula1|2>` 内容 ───────────────
    def _one_dv(match: re.Match[str]) -> str:
        body = match.group("body")
        if not body:
            return match.group(0)
        new_body = _sub_formula_text(body, "data_validation", _DV_FORMULA_RE)
        if new_body == body:
            return match.group(0)
        whole = match.group(0)
        start, end = match.span("body")
        offset = match.start()
        return whole[: start - offset] + new_body + whole[end - offset :]

    out = _DV_BLOCK_RE.sub(_one_dv, out)

    # ── ④ `<conditionalFormatting>` 的 `<formula>` 内容 ───────────
    def _one_cf(match: re.Match[str]) -> str:
        body = match.group("body") or ""
        new_body = _sub_formula_text(body, "conditional_format", _CF_FORMULA_RE)
        if new_body == body:
            return match.group(0)
        whole = match.group(0)
        start, end = match.span("body")
        offset = match.start()
        return whole[: start - offset] + new_body + whole[end - offset :]

    out = _CF_BLOCK_RE.sub(_one_cf, out)
    return out, counts


#: `<definedName>` 元素 —— 在 `xl/workbook.xml` 上。
_DEFINED_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"<definedName\b(?P<attrs>[^>]*?)(?:/>|>(?P<text>.*?)</definedName>)", re.S
)


def propagate_defined_names(
    workbook_xml: str,
    *,
    target_sheet: str,
    remap: Callable[[int], int],
) -> tuple[str, int]:
    """改写 `xl/workbook.xml` 里指向 `target_sheet` 的 `<definedName>`。

    definedNames 是**唯一**不在 worksheet part 上的传播载体（全库 5,002 条跨 sheet /
    341 份模板）。它的 `<definedName>` 元素内容就是引用文本，形态含
    `$A$1:$AM$34`（Print_Area）、`$2:$6`（Print_Titles，**整行区间**无列标）。
    """
    changed_total = 0

    def _one(match: re.Match[str]) -> str:
        escaped = match.group("text")
        if not escaped:
            return match.group(0)
        new_text, changed = _rewrite_text_preserving_unchanged(
            escaped,
            lambda plain: _rewrite_formula_refs(
                plain,
                remap=remap,
                propagate_sheets=frozenset({target_sheet}),
                qualified_only=True,
            ),
        )
        if changed == 0:
            return match.group(0)
        nonlocal changed_total
        changed_total += changed
        whole = match.group(0)
        start, end = match.span("text")
        offset = match.start()
        return whole[: start - offset] + new_text + whole[end - offset :]

    return _DEFINED_NAME_RE.sub(_one, workbook_xml), changed_total


# ═══════════════════════════════════════════════════════════════════════════
# 8. apply —— 受管 sheet + 引用侧，一次原子写入
# ═══════════════════════════════════════════════════════════════════════════

WORKBOOK_PART: Final[str] = "xl/workbook.xml"


def build_propagation_entry(
    site: CarrierSite, *, remap: Callable[[int], int]
) -> PropagationEntry | None:
    """由扫到的一处引用生成**声明**条目。没有任何行号变动时返回 `None`。

    ═══ 为什么必须有这个构造器 ═══

    🔴 让调用方手搓 `PropagationEntry` 会引入两类错误，Task 13 首次实测两类都撞上了：

    1. **`ref_after` 手算** —— 与执行时用的改写器不是同一份代码 ⇒ 声明与实测天然可能
       不一致。本函数用 `_rewrite_formula_refs` 生成 `ref_after`，与
       :func:`propagate_reference_side` **同一个入口**，从构造上排除这类漂移。
    2. **`row_before` 填成"最小行号"** —— 区间可以首端点不动、末端点动
       （`$A$1:$AK$31` 在 `at=13` 时行 1 不动、31→32），按最小行号填会得到 `1 → 1`
       而被空操作守卫拦掉。本函数取**第一个真的位移的行**。

    Returns:
        条目；若该处引用一个片段都不动（如 `$2:$6` 全在插入点之上）则返回 `None`
        —— 不进传播清单，否则声明量虚高会让对账失败。
    """
    ref = site.reference
    if ref.kind != "sheet" or not ref.token:
        return None
    after_text, changed = _rewrite_formula_refs(
        ref.raw,
        remap=remap,
        propagate_sheets=frozenset({ref.sheet_name}),
        qualified_only=True,
    )
    if changed == 0 or after_text == ref.raw:
        return None

    shifted = [(row, remap(row)) for row in ref.rows]
    moved = [(before, after) for before, after in shifted if after != before]
    if not moved:  # pragma: no cover - changed>0 时必有位移
        return None
    row_before, row_after = moved[0]
    return PropagationEntry(
        carrier=site.carrier,
        part=site.part,
        locator=f"{site.locator}#{ref.start}",
        ref_before=ref.raw,
        ref_after=after_text,
        row_before=row_before,
        row_after=row_after,
    )


def build_insert_plan(
    scan: ReferenceScan,
    *,
    managed_sheet_name: str,
    managed_sheet_part: str,
    at: int,
    count: int,
    style_from: int,
    region_first_row: int,
    region_last_row: int,
) -> WorkbookRowChangePlan:
    """由扫描结果生成插行计划 —— 声明的**唯一**构造入口（Requirement 1.1 / 1.2）。

    把「扫描 → 声明」这一步收在一个函数里，是为了让声明**不可能**与执行漂移：
    `ref_after` 由执行时的同一个改写器生成，位移量由同一个 `remap` 决定。
    """

    def remap(row: int) -> int:
        return row + count if row >= at else row

    entries = [
        entry
        for entry in (build_propagation_entry(site, remap=remap) for site in scan.sites)
        if entry is not None
    ]
    return WorkbookRowChangePlan(
        kind=RowChangeKind.INSERT,
        managed_sheet_name=managed_sheet_name,
        managed_sheet_part=managed_sheet_part,
        at=at,
        count=count,
        style_from=style_from,
        region_first_row=region_first_row,
        region_last_row=region_last_row,
        propagations=tuple(entries),
        unpropagated=scan.unpropagated,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. 删行侧：不可删行、悬空引用、业务键（Requirement 3）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 **「被引用」不等于「不可删」。** 这是 Wave 3 Task 16 实测更正的判据，也是本节
#    全部逻辑的地基。三种引用形态在删行下的 Excel 语义完全不同：
#
#    | 形态 | 样本 | 删掉被指的那行 |
#    |---|---|---|
#    | **单格** | `'表'!AC26` | 🔴 变 `#REF!` —— 真的坏了 |
#    | 区间**端点** | `'表'!$AI$13:$AI$25` 删第 13 或 25 行 | ✅ 收缩成 `$AI$13:$AI$24`，仍有效 |
#    | 区间**内部** | 同上，删第 20 行 | ✅ 同样收缩 |
#    | 区间被**删光** | 13..25 全删 | 🔴 变 `#REF!` |
#
#    删掉区间内部的一行，Excel 的语义就是「那笔数据没了，合计少算一笔」—— 这正是删行
#    **应有**的效果。把区间端点/内部也判成不可删（即用 `referenced_rows` 或
#    `covered_rows` 当判据）会让删行功能在几乎所有底稿上表现为「永远失败」：
#    D2 数据区 13 行会全被锁死，而实测它一行单格引用都没有。


@dataclass(frozen=True)
class DanglingSite:
    """一处**会因删行而坏掉**的引用。

    与 :class:`CarrierSite` 的区别：那个是「扫到的引用」，本类是「删了会 `#REF!` 的引用」。
    `reason` 只有两个取值，对应上表里两种真会坏的形态。
    """

    site: CarrierSite
    #: `single_cell`（单格引用指向被删行）/ `range_emptied`（区间被删光）。
    reason: str
    #: 被删掉的、导致这处引用坏掉的行。
    broken_rows: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.site.as_dict(),
            "reason": self.reason,
            "broken_rows": list(self.broken_rows),
        }


def _range_rows_of(site: CarrierSite) -> tuple[int, ...] | None:
    """区间引用返回它覆盖的行；单格引用返回 `None`。"""
    return site.covered_rows if ":" in site.reference.token else None


def find_undeletable_rows(
    scan: ReferenceScan,
    *,
    region_first_row: int,
    region_last_row: int,
    count: int = 1,
) -> tuple[int, ...]:
    """受管区内**删 `count` 行会坏掉**的行（Requirement 3.8 / Property 35）。

    判据 = ① 有**单格**引用指向该行 ∪ ② 该行属于某个**只覆盖 ≤ count 行**的区间。

    ═══ 🔴 第②条为什么是「≤ count 行」而不是「完全落在受管区内」═══

    首版写的是后者，实测**当场打红**：D2 的 `'明细表D2-2'!$AI$13:$AI$25` 覆盖的
    13..25 恰好**就是**整个数据区 ⇒ 判成「完全在区内」⇒ 13 行全部被锁，而 D2 数据区内
    实测**一处单格引用都没有**。那等于让 D2 的删行功能永远失败 —— 正是本条要避免的事。

    错在把「区间恰好等于数据区」当成了「删任何一行都会让区间消失」。Excel 的实际语义：
    删 1 行只让区间**收缩**（`$AI$13:$AI$25` → `$AI$13:$AI$24`），只有**删光**才 `#REF!`。
    所以只有当区间覆盖的行数 **≤ 本次要删的行数**时，删它才可能整体消失。

    `count` 默认 1（HTML 侧逐行删的默认粒度）。要一次删多行时传真实值，锁定集会相应变大
    —— 这是正确的：删 13 行确实会让 `$AI$13:$AI$25` 消失。

    ⚠ 本函数是「把拦的位置**前移**到用户能看见的地方」（AC 3.8），**不替代**
    :func:`find_dangling_sites` 的后端拦截（AC 3.4）—— 前端标记可被绕过。

    实测（2026-09-05，`count=1`）：
    * **D2** 数据区 `13..25` ⇒ **∅**，13 行全部可删。13/25 只是区间端点；那 24 处单格
      引用全指向**第 26 行合计行**，而合计行不在数据区内（删数据行时它上移，属 AC 3.3）。
    * **K11** 数据区 `7..25` ⇒ **19 行全部**，每行各 6 处单格引用（`A7`/`G7`/`D7` 逐行）
      ⇒ 100% 阻断，这正是本条存在的理由。
    """
    region = range(region_first_row, region_last_row + 1)
    blocked: set[int] = set()
    for site in scan.sites:
        covered = _range_rows_of(site)
        if covered is None:
            # ① 单格引用 —— 指向区内则该行不可删（删了必然 #REF!）
            blocked.update(row for row in site.rows if row in region)
            continue
        # ② 区间：只有「覆盖的行数 <= 本次删除行数」时才可能被删光
        if len(covered) <= count:
            blocked.update(row for row in covered if row in region)
    return tuple(sorted(blocked))


def find_dangling_sites(
    scan: ReferenceScan, *, delete_at: int, count: int
) -> tuple[DanglingSite, ...]:
    """删 `delete_at..delete_at+count-1` 会坏掉的引用（Requirement 3.4）。

    与 :func:`find_undeletable_rows` 的分工：那个不知道要删哪几行（发起之前的声明），
    本函数知道（计划阶段的实际拦截）。所以本函数的判据更**精确**：

    * 单格引用落在被删区间内 ⇒ `single_cell`；
    * 区间引用的**全部**覆盖行都落在被删区间内 ⇒ `range_emptied`；
    * 区间引用只有**部分**行被删 ⇒ **不算坏**（Excel 会收缩区间，那是正确语义）。
    """
    deleted = set(range(delete_at, delete_at + count))
    found: list[DanglingSite] = []
    for site in scan.sites:
        covered = _range_rows_of(site)
        if covered is None:
            hit = tuple(row for row in site.rows if row in deleted)
            if hit:
                found.append(
                    DanglingSite(site=site, reason="single_cell", broken_rows=hit)
                )
            continue
        if covered and set(covered) <= deleted:
            found.append(
                DanglingSite(site=site, reason="range_emptied", broken_rows=covered)
            )
    return tuple(found)


def resolve_deleted_row_keys(
    rows: Iterable[int],
    *,
    row_uuids: Mapping[int, str] | None = None,
    stable_ordinals: Mapping[int, str] | None = None,
) -> tuple[str, ...]:
    """按优先级取被删行的业务键：`row_uuid` → 契约稳定序号 → 抛（Requirement 3.7）。

    🔴 **优先级不可颠倒。** `row_uuid` 是行的**身份**，在行移动后仍指同一笔业务数据；
    稳定序号只是**位置**的稳定表达，删行后它会指到另一笔上。两者都缺时必须抛 ——
    删除是不可逆的数据丢失，没有留痕就无从审计（`MissingRowIdentityError`）。

    Args:
        rows: 被删行号（位移**前**口径）。
        row_uuids: `{行号: row_uuid}`，来自契约的 `row_identity`。
        stable_ordinals: `{行号: 稳定序号}`，退路。
    """
    uuids = dict(row_uuids or {})
    ordinals = dict(stable_ordinals or {})
    keys: list[str] = []
    missing: list[int] = []
    for row in rows:
        key = str(uuids.get(row) or "").strip() or str(ordinals.get(row) or "").strip()
        if not key:
            missing.append(row)
            continue
        keys.append(key)
    if missing:
        raise MissingRowIdentityError(
            f"第 {missing} 行既无 row_uuid 也无稳定序号 —— 删除是不可逆的数据丢失，"
            "无留痕不得执行（Requirement 3.7）"
        )
    if len(set(keys)) != len(keys):
        raise MissingRowIdentityError(
            f"业务键有重复：{keys} —— 重复键无法一一对应到被删行，事后无从复原"
        )
    return tuple(keys)


#: `<row>` 元素（用于删行时按行号重建 sheetData）。
_ROW_ELEMENT_RE: Final[re.Pattern[str]] = re.compile(
    r'<row\b[^>]*?\br="(?P<row>\d+)"[^>]*?(?:/>|>.*?</row>)', re.S
)
_SHEET_DATA_RE: Final[re.Pattern[str]] = re.compile(
    r"(?P<open><sheetData\b[^>]*>)(?P<body>.*?)(?P<close></sheetData>)", re.S
)
_DIMENSION_RE: Final[re.Pattern[str]] = re.compile(
    r'<dimension\s+ref="(?P<ref>[^"]+)"\s*/>'
)


def shrink_sheet_rows(xml: str, *, delete_at: int, count: int) -> tuple[str, int]:
    """受管 sheet 内删行：移除被删行，其后行**上移** `count`（Requirement 3.1 / 3.2）。

    与插行的 `shift_sheet_rows` 对称，但**不复用**它 —— 那个函数的语义是「造新行 +
    下移」，删行是「移除 + 上移」，共用一个实现会让两边的边界条件互相干扰。

    ⚠ 本函数只改 `<row r=>` 与其中单元格的 `r=` 坐标，以及 `<dimension>`。公式文本里的
    行号由 :func:`propagate_reference_side`（带负 delta 的 remap）处理 —— 分开是因为
    「结构」与「引用」是两件事，混在一起时任何一边的 bug 都会被另一边掩盖。

    Returns:
        `(新 XML, 被移除的行数)`
    """
    if count <= 0:
        raise RowChangeKindError(f"删行的 count 必须为正，实得 {count}")
    deleted = set(range(delete_at, delete_at + count))
    removed = 0

    def _remap(row: int) -> int | None:
        if row in deleted:
            return None
        return row - count if row > max(deleted) else row

    def _rewrite_rows(match: re.Match[str]) -> str:
        nonlocal removed
        body = match.group("body")
        out: list[str] = []
        for row_match in _ROW_ELEMENT_RE.finditer(body):
            row_no = int(row_match.group("row"))
            new_row = _remap(row_no)
            if new_row is None:
                removed += 1
                continue
            chunk = row_match.group(0)
            if new_row != row_no:
                chunk = re.sub(
                    r'(<row\b[^>]*?\br=")\d+(")',
                    rf"\g<1>{new_row}\g<2>",
                    chunk,
                    count=1,
                )
                chunk = re.sub(
                    r'(<c\b[^>]*?\br="[A-Z]+)\d+(")',
                    rf"\g<1>{new_row}\g<2>",
                    chunk,
                )
            out.append(chunk)
        return match.group("open") + "".join(out) + match.group("close")

    result = _SHEET_DATA_RE.sub(_rewrite_rows, xml, count=1)

    def _shrink_dimension(match: re.Match[str]) -> str:
        ref = match.group("ref")
        if ":" not in ref:
            return match.group(0)
        head, tail = ref.split(":", 1)
        tail_row = "".join(ch for ch in tail if ch.isdigit())
        if not tail_row:
            return match.group(0)
        tail_col = "".join(ch for ch in tail if ch.isalpha())
        new_tail = max(int(tail_row) - count, delete_at)
        return f'<dimension ref="{head}:{tail_col}{new_tail}"/>'

    result = _DIMENSION_RE.sub(_shrink_dimension, result, count=1)
    return result, removed


def build_delete_plan(
    scan: ReferenceScan,
    *,
    managed_sheet_name: str,
    managed_sheet_part: str,
    at: int,
    count: int,
    region_first_row: int,
    region_last_row: int,
    row_uuids: Mapping[int, str] | None = None,
    stable_ordinals: Mapping[int, str] | None = None,
    allow_ref_errors: bool = False,
) -> WorkbookRowChangePlan:
    """由扫描结果生成删行计划。**悬空引用在计划阶段就抛**（Requirement 3.4）。

    Args:
        allow_ref_errors: 仅当契约**显式**声明允许写 `#REF!` 时置 True。默认 False ⇒
            fail closed。这个开关刻意做成必须显式打开：静默写 `#REF!` 会让底稿在用户
            打开时才暴露损坏，而那时已经无从追溯是哪次同步造成的。

    Raises:
        DanglingReferenceError: 有引用会因删行而坏掉，且未获显式放行。携带**完整清单**
            —— 只报第一处会让调用方逐个试错。
        MissingRowIdentityError: 被删行缺业务键。
    """

    def remap(row: int) -> int:
        return row - count if row >= at + count else row

    dangling = find_dangling_sites(scan, delete_at=at, count=count)
    if dangling and not allow_ref_errors:
        detail = "; ".join(
            f"{d.site.part.rsplit('/', 1)[-1]}!{d.site.locator} "
            f"{d.site.reference.raw}（{d.reason}，坏在第 {list(d.broken_rows)} 行）"
            for d in dangling[:12]
        )
        raise DanglingReferenceError(
            f"删除第 {at}..{at + count - 1} 行会让 {len(dangling)} 处引用变成 #REF!："
            f"{detail}"
            + ("…" if len(dangling) > 12 else "")
            + " —— 删行拒绝执行（Requirement 3.4）。若确需写 #REF!，"
            "须在契约里显式声明后传 allow_ref_errors=True"
        )

    keys = resolve_deleted_row_keys(
        range(at, at + count), row_uuids=row_uuids, stable_ordinals=stable_ordinals
    )
    entries = [
        entry
        for entry in (
            build_propagation_entry(site, remap=remap)
            for site in scan.sites
            # 被删光的区间与被删的单格不进传播清单 —— 它们不是「改行号」而是「坏了」
            if not any(d.site is site for d in dangling)
        )
        if entry is not None
    ]
    return WorkbookRowChangePlan(
        kind=RowChangeKind.DELETE,
        managed_sheet_name=managed_sheet_name,
        managed_sheet_part=managed_sheet_part,
        at=at,
        count=count,
        style_from=None,
        region_first_row=region_first_row,
        region_last_row=region_last_row,
        propagations=tuple(entries),
        unpropagated=scan.unpropagated,
        deleted_row_keys=keys,
        undeletable_rows=find_undeletable_rows(
            scan,
            region_first_row=region_first_row,
            region_last_row=region_last_row,
            count=count,
        ),
    )


def normalise_propagated_part(
    text: str, plan: WorkbookRowChangePlan, *, part: str
) -> tuple[str, int]:
    """把一张引用侧 sheet 的**改后**文本按计划的**声明**逆归一化回改前口径。

    ═══ 🔴 为什么是「逐条逆替换声明」而不是「整体反向 remap」═══

    这是 Requirement 5.1 与 5.4 的交汇点，也是本函数唯一存在的理由。

    * **逐条逆替换**（本实现）：只把 `ref_after` → `ref_before` 各替换一次。声明之外的
      任何字节变化**留在原处** ⇒ 归一化后与 before 侧不等 ⇒ 判漂移。
    * **整体反向 remap**（错）：对这张 sheet 上**所有**引用做 `row + count`。那样任何
      未声明的改动只要形态上像位移就会被一起归一化掉 —— 等于让被检查对象自己声明自己
      合法（design.md 明确拒绝的方案）。

    差别在一个具体场景上就能看出来：若传播器**多改了一处**没进声明的引用，逐条逆替换
    留下那处差异（打红，正确）；整体 remap 会把它一并还原（放过，错）。

    ⚠ 只给 **after 侧**。before 侧本来就是改前口径，两侧都归一化等于什么都没归一化
    —— 与 `verify_unmanaged_regions` 的 `row_shift` 同一条纪律。

    Args:
        text: 引用侧 sheet part 的**改后** XML 文本。
        plan: 冻结的计划。归一化只认 `plan.propagations` 里 `part` 命中的条目。
        part: 这段文本对应的 zip part 名。

    Returns:
        `(逆归一化后的文本, 实际逆替换的**出现次数**)`。第二个值供调用方与声明的条目数
        对账 —— 不等说明产物里缺了某条声明的改动、或多出了形态相同但未声明的改动
        （两者都是漂移）。⚠ 计量单位是**文本出现次数**而不是「不同文本段数」，
        理由见实现里的注释。
    """
    entries = [e for e in plan.propagations if e.part == part]
    if not entries:
        return text, 0

    # 🔴 **按文本归并，按出现次数计量**，不是按条目计量。
    #
    # 多条条目可以共用同一段文本：D2 的 `SUMIF('明细表D2-2'!$AI$13:$AI$25,…)` 在
    # `sheet3.xml` 上出现在 18 个不同单元格里 ⇒ 18 条条目、但只有 4 段**不同**的文本。
    # 首版按条目逐条 `replace` 并 `reverted += 1`，实测 18 条只数出 4 —— 因为
    # `str.replace()` 一次就把同一段文本的全部出现都换掉了。
    #
    # 改为「按出现次数计量」之后，判据反而**更强**：它不只要求「这段文本出现过」，
    # 还要求它出现的**次数**恰好等于声明的条目数。少一处 = 有条目没做；多一处 =
    # 有未声明的改动被写成了与声明相同的形态。
    pairs: dict[tuple[str, str], int] = {}
    for entry in entries:
        key = (entry.ref_after, entry.ref_before)
        pairs[key] = pairs.get(key, 0) + 1

    out = text
    reverted = 0
    # 长的先替换：短的 ref_after 可能是长的子串（`!A2` ⊂ `!A25`），先替短的会切坏长的
    for after, before in sorted(pairs, key=lambda kv: len(kv[0]), reverse=True):
        # 两种文本形态各试一次：产物里可能是转义后的，也可能保留了原始实体写法
        for candidate_after, candidate_before in (
            (_escape(after), _escape(before)),
            (after, before),
        ):
            hits = out.count(candidate_after)
            if hits:
                out = out.replace(candidate_after, candidate_before)
                reverted += hits
                break
    return out, reverted


def assert_propagation_declared_exactly(
    before_text: str, after_text: str, plan: WorkbookRowChangePlan, *, part: str
) -> None:
    """一张引用侧 sheet：逆归一化后必须与改前**逐字节**相等（Requirement 5.4）。

    🔴 「传播」不是「允许这张 sheet 随便改」的通行证。本函数把这句话变成可执行判据：
    把声明的改动逆替换回去之后，剩下的任何差异都是**未声明的改动** ⇒ 漂移。
    """
    normalised, reverted = normalise_propagated_part(after_text, plan, part=part)
    declared = len([e for e in plan.propagations if e.part == part])
    if reverted != declared:
        raise PropagationDriftError(
            f"{part}：声明了 {declared} 条传播条目，但产物里只找到 {reverted} 条 —— "
            "缺失的那些声明改动没有真的发生（或产物里的文本形态与声明不符）"
        )
    if normalised != before_text:
        # 定位首个差异，避免只报「不等」
        limit = min(len(normalised), len(before_text))
        at = next((i for i in range(limit) if normalised[i] != before_text[i]), limit)
        raise PropagationDriftError(
            f"{part}：把声明的 {declared} 条传播逆归一化后仍与改前不等 —— "
            f"存在**未声明**的改动。首个差异在第 {at} 字符附近："
            f"改前 {before_text[max(0, at - 40) : at + 40]!r} / "
            f"归一化后 {normalised[max(0, at - 40) : at + 40]!r}"
        )


def _repack(data: bytes, replacements: Mapping[str, bytes]) -> bytes:
    """只替换 `replacements` 里的部件，其余连 `ZipInfo` 一起原样搬过去。

    保留每个部件的 `date_time` / `compress_type` / 属性位 —— 让「除声明部件外一个字节
    都没动」这句话在 zip 元数据层面也成立。

    🔴 与 `excel_sheet_visibility._replace_workbook_part` 同形（那里只换一个部件）。
    没有直接复用它是因为本函数要换**多个**部件；两者的 ZipInfo 克隆逻辑逐字相同，
    由 `test_repack_preserves_zipinfo_like_visibility_module` 锁死不漂移。
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        with zipfile.ZipFile(buffer, "w") as out:
            for info in src.infolist():
                payload = replacements.get(info.filename, src.read(info.filename))
                clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                clone.compress_type = info.compress_type
                clone.external_attr = info.external_attr
                clone.internal_attr = info.internal_attr
                clone.create_system = info.create_system
                clone.flag_bits = info.flag_bits & ~0x08  # 不用 data descriptor
                out.writestr(clone, payload)
    return buffer.getvalue()


def _assert_only_declared_parts_changed(
    before: bytes, after: bytes, *, allowed: frozenset[str]
) -> None:
    """结构性自检：部件集合逐位相等 + 只有 `allowed` 里的部件字节变了。

    🔴 这道自检是本模块存在的**主要理由之一**。上游 openpyxl 那版之所以能长期在生产
    路径上丢 20 个部件、把 12 个共享公式组展平，就是因为没有任何判据在看「除了我要改的
    那几处，别的动了没有」。传播的作用面比插行更大（跨多张 sheet + workbook.xml），
    所以这道自检更要紧。
    """
    with zipfile.ZipFile(io.BytesIO(before)) as a, zipfile.ZipFile(
        io.BytesIO(after)
    ) as b:
        names_before, names_after = a.namelist(), b.namelist()
        if names_before != names_after:
            lost = [n for n in names_before if n not in set(names_after)]
            gained = [n for n in names_after if n not in set(names_before)]
            raise PropagationDriftError(
                f"zip 部件集合变了：丢 {len(lost)} 个 {lost[:8]}、多 {len(gained)} 个 "
                f"{gained[:8]} —— 工作簿级行变更只许改受管 sheet 与传播条目所在部件"
            )
        unexpected = [
            name
            for name in names_before
            if name not in allowed and a.read(name) != b.read(name)
        ]
        if unexpected:
            raise PropagationDriftError(
                f"{len(unexpected)} 个未声明部件的字节被改动：{unexpected[:8]} —— "
                "传播不是「允许随便改」的通行证（Requirement 5.4）。"
                f"声明可改的部件：{sorted(allowed)}"
            )


def apply_workbook_row_change(
    data: bytes,
    plan: WorkbookRowChangePlan,
    *,
    sheet_parts: Mapping[str, str],
    total_formula_rows: Iterable[int] = (),
    managed_columns: Iterable[str] = (),
) -> tuple[bytes, PropagationReport]:
    """执行一次工作簿级行变更（insert / delete 两个分支）。纯函数：不碰磁盘。

    ═══ 两半各走各的入口 ═══

    | 半 | insert | delete | 裸引用 |
    |---|---|---|---|
    | 受管 sheet | `shift_sheet_rows`（上游，复用） | :func:`shrink_sheet_rows` | **位移** |
    | 引用侧 | :func:`propagate_reference_side` | 同左（负 delta） | **不动**（`qualified_only=True`） |

    insert 的受管 sheet 那半整个复用上游的 `shift_sheet_rows`：它已经处理了行重编号、
    共享公式组、新行造格与样式继承、`dimension`、受管区外 ref、以及「清单外携带行号元素」
    的 fail-closed。本模块不重做其中任何一件。

    ⚠ delete 分支**没有**复用 `shift_sheet_rows` —— 那个函数的语义是「造新行 + 下移」，
    删行是「移除 + 上移」，共用一个实现会让两边的边界条件互相干扰。悬空引用的拦截在
    :func:`build_delete_plan`（**计划阶段**，不等写盘）。

    ═══ 失败即零产物 ═══

    本函数**返回字节**而不落盘 —— 落盘由调用方用临时文件 + `os.replace` 完成
    （见 :func:`apply_workbook_row_change_to_path`）。任何一步抛错都在返回之前，
    所以原文件不可能被半成品覆盖。

    Args:
        data: 原 xlsx 字节。**不被修改**。
        plan: 冻结的工作簿级计划（`kind` 必须是 `insert`）。
        sheet_parts: `{sheet 名: zip part}`，必须由
            `excel_structure_fingerprint._parse_workbook_xml` + `_normalise_part` 解析。
        total_formula_rows: 契约声明携带合计公式的行（位移**前**口径），透传给
            `shift_sheet_rows`。
        managed_columns: 受管列，透传给 `shift_sheet_rows`。

    Returns:
        `(新字节, PropagationReport)`。报告里的计数是**实测**值，调用方应当用
        `report.assert_matches_plan(plan)` 与声明对账。

    Raises:
        RowChangeOutOfRegionError: 受管 part 不在 zip 里。
        PropagationDriftError: 部件集合变化 / 未声明部件被改动。
    """
    from app.services.workpaper_sync.excel_row_shift import (
        RowShiftPlan,
        shift_sheet_rows,
    )

    managed_part = plan.managed_sheet_part
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        if managed_part not in names:
            raise RowChangeOutOfRegionError(
                f"受管 sheet part {managed_part} 不在 zip 里 —— part 必须由 "
                "`_parse_workbook_xml` + `_normalise_part` 解析得来，不得按顺序拼"
            )
        parts: dict[str, str] = {
            part: zf.read(part).decode("utf-8")
            for part in sorted(set(sheet_parts.values()) & names)
        }
        workbook_xml = (
            zf.read(WORKBOOK_PART).decode("utf-8") if WORKBOOK_PART in names else None
        )

    # ── ① 受管 sheet：insert 复用上游的结构性插行 / delete 走 shrink ──
    if plan.kind is RowChangeKind.INSERT:
        shift_plan = RowShiftPlan(
            insert_at=plan.at,
            count=plan.count,
            style_from=plan.style_from or 0,
        )
        shifted_managed, _shift_report = shift_sheet_rows(
            parts[managed_part],
            shift_plan,
            total_formula_rows=tuple(total_formula_rows),
            managed_columns=tuple(managed_columns),
        )
        remap: Callable[[int], int] = shift_plan.shift
    else:
        shifted_managed, _removed = shrink_sheet_rows(
            parts[managed_part], delete_at=plan.at, count=plan.count
        )
        last_deleted = plan.at + plan.count - 1

        def _delete_remap(row: int) -> int:
            # 被删行本身不该出现在传播条目里（它们是 dangling，已在 build_delete_plan
            # 拦下或显式放行）；这里对区间端点做上移。
            return row - plan.count if row > last_deleted else row

        remap = _delete_remap

    # ── ② 引用侧：逐 sheet 定点改写 ────────────────────────────────
    replacements: dict[str, bytes] = {}
    totals: Counter[str] = Counter()

    for sheet_name, part in sorted(sheet_parts.items()):
        if part not in parts:
            continue
        source = shifted_managed if part == managed_part else parts[part]
        rewritten, counts = propagate_reference_side(
            source, target_sheet=plan.managed_sheet_name, remap=remap
        )
        if part == managed_part:
            # 受管 sheet 上**自限定**引用（`'本表'!A1` 写在本表上）已由
            # `shift_sheet_rows` 的自限定分支位移过。这里再跑一次传播是为了
            # 覆盖「受管 sheet 引用自己但写成非自限定形态」的可能，实测通常为 0；
            # 若真有改动，计数照记，不静默。
            replacements[part] = rewritten.encode("utf-8")
        elif rewritten != source:
            replacements[part] = rewritten.encode("utf-8")
        for carrier, n in counts.items():
            totals[carrier] += n

    if managed_part not in replacements:
        replacements[managed_part] = shifted_managed.encode("utf-8")

    # ── ③ definedNames（在 workbook.xml 上）───────────────────────
    if workbook_xml is not None:
        new_workbook, dn_changed = propagate_defined_names(
            workbook_xml, target_sheet=plan.managed_sheet_name, remap=remap
        )
        if dn_changed:
            totals["defined_name"] += dn_changed
            replacements[WORKBOOK_PART] = new_workbook.encode("utf-8")

    # ── ④ 重打包 + 结构性自检 ─────────────────────────────────────
    produced = _repack(data, replacements)
    _assert_only_declared_parts_changed(
        data, produced, allowed=frozenset(replacements)
    )

    report = PropagationReport(
        formulas_changed=totals["formula"],
        hyperlink_locations_changed=totals["hyperlink_location"],
        data_validations_changed=totals["data_validation"],
        conditional_formats_changed=totals["conditional_format"],
        defined_names_changed=totals["defined_name"],
        unpropagated_total=sum(c.count for c in plan.unpropagated),
        unpropagated_by_reason=plan.unpropagated_counts(),
    )
    return produced, report


def apply_workbook_row_change_to_path(
    path: Path | str,
    plan: WorkbookRowChangePlan,
    *,
    sheet_parts: Mapping[str, str],
    total_formula_rows: Iterable[int] = (),
    managed_columns: Iterable[str] = (),
) -> PropagationReport:
    """落盘版：临时文件 + `os.replace`，**传播失败整次放弃**。

    🔴 顺序是「先算完整字节 → 再落临时文件 → 再顶替」。任何一步抛错都发生在
    `os.replace` **之前** ⇒ 原文件完好无损，不存在「改了一半」的产物。

    与 `excel_sheet_visibility._apply` 同形（同卷临时文件 + 原子顶替）。
    """
    target = Path(path)
    data = target.read_bytes()
    produced, report = apply_workbook_row_change(
        data,
        plan,
        sheet_parts=sheet_parts,
        total_formula_rows=total_formula_rows,
        managed_columns=managed_columns,
    )
    report.assert_matches_plan(plan)

    tmp = target.with_name(f"{target.name}.rowchange.tmp")
    try:
        tmp.write_bytes(produced)
        os.replace(tmp, target)
    finally:
        if tmp.exists():  # pragma: no cover - 仅异常路径
            tmp.unlink()
    return report
