"""受管 Excel sheet 的**结构性插行**与行位移 —— 纯函数层。

**Spec: excel-structural-row-insertion-and-shift-aware-verification**
Requirements: 1.1~1.6（位移敏感清单）、2.1~2.7（位移计划）、3.1~3.8（纯函数分阶段）、
4.1~4.8（共享公式位移与扩张）

═══ 为什么需要这一层 ══════════════════════════════════════════════════════════

`excel_materialize.plan_managed_writes` 原来对「merged projection 的行身份在 substrate
上没有物理行」**无条件** fail closed，模块 docstring 把它写成判据：「不做结构性插行」。
成因是四道门叠加 —— 逐格 digest 带 `r=`、结构块整段序列化、footer anchor 要求实测行等于
冻结行、footer 合计明令「共享公式主格不得被改写」。

后果是：**只有 HTML 侧行数恰好不超过模板骨架行数的底稿才能双向回写**。实测 D2 的
`D2-detail-rows` 有 729 行而骨架 `A13:AN25` 只有 13 行 —— 那不是例外，是常态。

本模块把「位移」从"必然是漂移"变成"可以是一份被冻结的声明"（:class:`RowShiftPlan`）。
verifier 拿同一份声明把行号反向归一化后再比对：与声明一致的位移判等价，声明外的任何
改动仍判漂移。**判据没有被放宽，只是变得能表达"预期"。**

═══ 本模块只做纯函数 ═════════════════════════════════════════════════════════

不碰磁盘、不改入参、不 commit、不发布。输入 sheet XML 字符串与计划，输出新 XML 与
:class:`ShiftReport`。所有 I/O 与发布由 `excel_materialize` / `ContentMutationService`
承担。

═══ 真实形态实测（权威模板，勿按想象改）══════════════════════════════════════

* `<dimension ref="A1:AA43"/>` 自闭合；每张 sheet 都有。
* `<mergeCells count="32"><mergeCell ref="S11:S12"/>…` —— K11 实测受管区域（A7:N25）
  **之下**有 `E30:F30`，任何行位移都会动它。
* `<dataValidation type="list" … sqref="D13:D24">` —— `sqref` 在**属性中间**位置，
  属性顺序不保证（H1 是 `sqref` 打头，D2 是 `type` 打头），故一律按属性名定位。
* `<row r="1" spans="1:39" ht="…" s="38" customFormat="1">` —— row 级有 `s=`；
  🔴 `spans` 是**列**范围（`1:39`），**不位移**。
* 共享公式主格三种 ref 形态：纵向 `H8:H25`、横向 `B26:G26`、单格 `H26`；
  公式文本里的区间是纵向（`SUM(B7:B25)`）。K11 还有跨 footer 的 `I7:I26` 与受管区
  **之下**的 `C28:G28`。
* H1 的受管 sheet **共享公式 0 个**（`<f>` 全裸）；D2 有 21 个主格 / 60 个自闭合成员。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Callable, Final, Iterable, Mapping, Sequence

from app.services.workpaper_sync.models import SyncDomainError

__all__ = [
    "ROW_BEARING_STRUCTURES",
    "HANDLED_BY_IDENTITY_RETENTION_GATE",
    "RowShiftError",
    "RowShiftPlanCountError",
    "RowShiftPlanRangeError",
    "RowShiftStyleSourceMissingError",
    "UnlistedRowBearingStructureError",
    "SharedFormulaSpanError",
    "SharedFormulaOrientationError",
    "RowShiftPlan",
    "ShiftReport",
    "SharedFormulaGroup",
    "shared_formula_groups",
    "scan_unlisted_row_bearing_elements",
    "assert_shift_handlers_cover_structures",
    "translate_formula_rows",
    "shift_sheet_rows",
    # ── 供 verifier 侧做 shift-aware 归一化（只读比对，不写盘）──────
    "remap_a1_rows",
    "unextend_total_formula",
    # ── 供工作簿级传播扫描（只读分词，与改写器同口径）────────────────
    "QualifiedReference",
    "iter_qualified_references",
    "STRUCTURE_ROW_BEARING_ATTRS",
    "STRUCTURE_BARE_ROW_ATTRS",
    "STRUCTURE_ROW_BEARING_TEXT_TAGS",
    "NORMALIZED_BY_CELL_DIGEST",
    "assert_structure_normalization_covers_structures",
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常 —— 一条禁令一个类型一个 error_code
# ═══════════════════════════════════════════════════════════════════════════


class RowShiftError(SyncDomainError):
    """结构性插行域基类。"""

    error_code = "excel_row_shift_failed"


class RowShiftPlanCountError(RowShiftError):
    """插入行数非法（<= 0）。零位移应表达为 ``plan is None``，不是 ``count=0``。"""

    error_code = "excel_row_shift_plan_count_invalid"


class RowShiftPlanRangeError(RowShiftError):
    """插入点或样式来源行越界。"""

    error_code = "excel_row_shift_plan_range_invalid"


class RowShiftStyleSourceMissingError(RowShiftError):
    """样式来源行在 sheet XML 里不存在 —— 新插入行无从继承样式。"""

    error_code = "excel_row_shift_style_source_missing"


class UnlistedRowBearingStructureError(RowShiftError):
    """受管 sheet 上出现清单外的、携带行号的元素。

    fail closed 而不是「不认识就不动它」：不动它意味着位移后它仍指向旧行号，
    产出一个**看起来正常但引用错行**的工作簿。
    """

    error_code = "excel_row_shift_unlisted_structure"


class SharedFormulaSpanError(RowShiftError):
    """共享公式组的成员跨度与主格 ``ref`` 不一致，位移后无法保证整组仍有效。"""

    error_code = "excel_row_shift_shared_formula_span_mismatch"


class SharedFormulaOrientationError(RowShiftError):
    """样式来源行上的共享公式成员属于**横向**组（主格在另一列）。

    新行要继承它就得把主格公式按**列**平移，而本 spec 只做行位移
    （design.md §Data Model 的清单里没有列位移项）。猜一个列偏移会产出一张
    每格都算错的表，故 fail closed。

    实测 K11 受管 sheet 上确有横向组（si=3 `B26:G26`、si=5 `C28:G28`），只是它们
    不落在 `style_from`=25 行上；换一个模板就可能落上去。
    """

    error_code = "excel_row_shift_shared_formula_orientation_unsupported"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 位移敏感结构清单（Requirement 1.1）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 这是「位移敏感结构」的**完整**清单，不是「本模块处理的清单」。两者的差集由
#    :data:`HANDLED_BY_IDENTITY_RETENTION_GATE` 显式登记 —— 写成清单而不是注释，
#    是为了让 :func:`assert_shift_handlers_cover_structures` 能按结构判据双向锁死。
#
#    写在注释里的清单不可执行；漏一项的后果是「位移后它仍指向旧行」，而那类缺陷
#    在 verifier 补齐 `_SHEET_STRUCTURE_BLOCKS` 之前**根本不会红**。

ROW_BEARING_STRUCTURES: Final[tuple[tuple[str, str], ...]] = (
    ("row", "@r"),
    ("c", "@r"),
    ("mergeCell", "@ref"),
    ("dataValidation", "@sqref"),
    ("conditionalFormatting", "@sqref"),
    ("hyperlink", "@ref"),
    ("autoFilter", "@ref"),
    ("brk", "@id"),
    ("dimension", "@ref"),
    ("f", "@ref"),
    ("f", "text-a1-ranges"),
    # ── 三个「元素文本里的 A1 引用」（首版漏登记，全库实测后补）──────────
    #
    # 🔴 `formula` 是 `<conditionalFormatting><cfRule><formula>` 的规则表达式；
    #    `formula1` / `formula2` 是 `<dataValidations><dataValidation>` 的取值来源。
    #    三者都可以是**带行号**的 A1 区间。全库 351 份 xlsx / 2722 张 sheet 实测：
    #
    #      标签       命中文件   元素数   其中含 A1 引用
    #      formula     34/351     552          72
    #      formula1   232/351    1081         108      （如 `$Q$36:$Q$40`、`$R$8:$R$91`）
    #      formula2     4/351      13           0
    #
    #    首版把 `formula1`/`formula2` 放进 `_ROW_AGNOSTIC_TAGS`（= 声明它们不携带行号）
    #    ⇒ 位移后数据验证仍指向旧行，**静默错行** 108 处；而 `formula` 两张清单里都没有
    #    ⇒ `scan_unlisted_row_bearing_elements` 对那 34 份模板整体 fail closed，
    #    位移功能在它们上面根本不可用。
    ("formula", "text-a1-ranges"),
    ("formula1", "text-a1-ranges"),
    ("formula2", "text-a1-ranges"),
    # `<xm:sqref>` 是 x14:dataValidation 的扩展子元素（Excel 2010+），内容是 A1 范围文本
    #（如 D13:D24 或 AN65539:AN65553），与 formula1 同性质。行位移时必须位移，否则数据
    #验证继续指向旧行。
    ("sqref", "text-a1-ranges"),
    ("table", "@ref"),
)

#: 清单里**登记但不由本模块处理**的项，每条写明由谁承接。
#:
#: `table@ref` 是 identity 载体本体：`excel_extract._classify_parts` 把 `xl/tables/**`
#: 整类排除（注释原文「插删行会合法改 ref」），`assert_identity_inventory_retained`
#: 只锁列跨度、「行区间随插删行变化属合法」。它在本模块之外被正确处理，因此这里
#: **不动它**，但必须登记 —— 否则清单就从"完整清单"退化成"我处理了什么"。
HANDLED_BY_IDENTITY_RETENTION_GATE: Final[Mapping[tuple[str, str], str]] = {
    ("table", "@ref"): (
        "Excel Table part 的 ref 由 identity 保留门承接："
        "`_classify_parts` 排除 `xl/tables/**`，"
        "`assert_identity_inventory_retained` 只锁列跨度、行区间随插删行变化属合法"
    ),
}

#: `<row>` 上**不得**被位移的属性 —— 它们携带的是列范围或样式，不是行号。
#:
#: 🔴 `spans="1:39"` 形如行号区间但实际是**列**索引范围。实测 D2/K11 的每个 `<row>`
#:    都有它；把它当行号位移会写出一个列范围错乱的工作簿，而 Excel 对 `spans` 容错，
#:    于是缺陷不会立刻暴露。
ROW_ATTRS_NOT_SHIFTED: Final[frozenset[str]] = frozenset(
    {"spans", "s", "ht", "customFormat", "customHeight", "thickBot", "thickTop", "outlineLevel", "hidden", "collapsed"}
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 正则（属性一律按名定位 —— 属性顺序不保证）
# ═══════════════════════════════════════════════════════════════════════════

_SHEETDATA_RE: Final[re.Pattern[str]] = re.compile(
    r"(?P<open><sheetData\b[^>]*>)(?P<body>.*?)(?P<close></sheetData>)", re.S
)
_SHEETDATA_EMPTY_RE: Final[re.Pattern[str]] = re.compile(r"<sheetData\b[^>]*/>")
_ROW_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"<row\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</row>)", re.S
)
_CELL_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"<c\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</c>)", re.S
)
_F_RE: Final[re.Pattern[str]] = re.compile(
    r"<f\b(?P<fattrs>[^>]*?)(?:/>|>(?P<text>.*?)</f>)", re.S
)
_COORD_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<col>[A-Z]{1,3})(?P<row>\d+)$")

# ── 公式文本分词所需的模式（详见 §7 的说明）─────────────────────────
#: 单个 A1 坐标（可带 `$` 锁定），用于逐段解析与重建。
_A1_PIECE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?P<abs_col>\$?)(?P<col>[A-Z]{1,3})(?P<abs_row>\$?)(?P<row>\d+)"
)

#: 剥引号后识别外部工作簿标记 `[n]` —— 见 :func:`_prefix_sheet_name` 的两种写法对照表。
_QUOTED_BOOK_RE: Final[re.Pattern[str]] = re.compile(r"^\[\d+\]")

#: **裸行**片段（`6` / `$6`）—— 无列标的行区间端点。
#:
#: 🔴 存在的理由是 `_REF_TOKEN_RE` 的第三个分支 `\$?\d+:\$?\d+` 会命中「整行区间」，
#: 而 `_A1_PIECE_RE` 要求列标、对它 `fullmatch` 返回 None。实测样本是 D2 受管 sheet 的
#: `_xlnm.Print_Titles` → `'明细表D2-2'!$2:$6`：不单独处理这一形态，definedNames 里
#: 整类「打印标题行」在传播时会被静默漏掉（Requirement 4.1 / 4.7）。
_ROW_ONLY_PIECE_RE: Final[re.Pattern[str]] = re.compile(r"(?P<abs_row>\$?)(?P<row>\d+)")

#: 字符串字面量 `"..."`（内部 `""` 是转义的双引号）。
_STRING_LITERAL_RE: Final[re.Pattern[str]] = re.compile(r'"(?:[^"]|"")*"')

#: **XML 实体形态**的字符串字面量 `&quot;...&quot;`。
#:
#: 🔴 存在的理由是实测：`<cfRule><formula>` 里 WPS/Excel 把引号写成实体
#: （样例 `A8=&quot;&quot;`）。不认它的话 `A8=&quot;K11&quot;` 里的 `K11` 会被当成
#: 「K 列第 11 行」位移 —— 而它是个字符串。`&quot;` 后面紧跟的字符是 `;`，
#: 而 `;` **不在** `_LEFT_BOUNDARY_BLOCK` 里，所以左边界断言拦不住它。
_ENTITY_LITERAL_RE: Final[re.Pattern[str]] = re.compile(r"&quot;(?:(?!&quot;).)*&quot;", re.S)

#: 单个 sheet 名：带引号（内部 `''` 转义）或不带引号。Excel 只在名字含空格、
#: 连字符等标点时才加引号，所以不带引号的形态字符集是受限的。
_SHEET_NAME_PART: Final[str] = (
    r"'(?:[^']|'')*'|[A-Za-z_\u4e00-\u9fff][\w.\u4e00-\u9fff]*"
)

#: 跨 sheet / 跨工作簿引用的**前缀**（到 `!` 为止）：`Sheet1!`、
#: `'明细表K11-2'!`、`[1]Sheet1!`（外部工作簿）、`Sheet1:Sheet3!`（3D 引用）。
_QUALIFIED_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?P<book>\[\d+\])?(?P<first>{_SHEET_NAME_PART})"
    rf"(?P<span>:(?:{_SHEET_NAME_PART}))?!"
)

#: 跨 sheet 前缀之后的目标 token：单格 / 区间 / 整列 / 整行。
_REF_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?"
    r"|\$?[A-Z]{1,3}:\$?[A-Z]{1,3}"
    r"|\$?\d+:\$?\d+"
)

#: 裸 A1 引用（单格或区间，不带 sheet 前缀）。右侧边界断言排除 `LOG10(`
#: 这类带数字的函数名与 `A1B2` 这类标识符；左侧边界由扫描器逐位检查。
_BARE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"(?P<head>\$?[A-Z]{1,3}\$?\d+)(?::(?P<tail>\$?[A-Z]{1,3}\$?\d+))?"
    r"(?![A-Za-z0-9_.(])"
)

#: 左侧边界黑名单：这些字符后面紧跟的 `A1` 形态**不是**一个裸引用的开头。
#: `!` 在内 ⇒ 任何紧跟 `!` 的引用按定义都是跨 sheet 的，绝不当裸引用位移；
#: `#` 在内 ⇒ `#REF!` 这类错误字面量不被当成 sheet 名；
#: `$` 在内 ⇒ `$A$1` 只在起始 `$` 处匹配一次，不会从中间的 `A` 再匹配。
_LEFT_BOUNDARY_BLOCK: Final[frozenset[str]] = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.$]#!"
)


def _attr(attrs: str, name: str) -> str | None:
    found = re.search(rf'\b{re.escape(name)}="([^"]*)"', attrs)
    return found.group(1) if found else None


def _set_attr(attrs: str, name: str, value: str) -> str:
    pattern = re.compile(rf'(\b{re.escape(name)}=")[^"]*(")')
    if pattern.search(attrs):
        return pattern.sub(lambda m: f"{m.group(1)}{value}{m.group(2)}", attrs, count=1)
    return f'{attrs} {name}="{value}"'


def _row_of(coord: str) -> int | None:
    found = _COORD_RE.match(coord.strip())
    return int(found.group("row")) if found else None


def _col_of(coord: str) -> str | None:
    found = _COORD_RE.match(coord.strip())
    return found.group("col") if found else None


# ═══════════════════════════════════════════════════════════════════════════
# 4. RowShiftPlan / ShiftReport（Requirements 2.1, 2.2, 3.6）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RowShiftPlan:
    """一次结构性插行的**冻结**声明。零写入面。

    `insert_at` 是**第一个新行**的行号；`insert_at..insert_at+count-1` 是新行区间，
    原来 `>= insert_at` 的行整体下移 `count`。

    `style_from` 是样式来源行（通常是受管区域内最后一个既有数据行）。新行从它按列
    继承 `s=`，并按 fill-down 语义翻译公式 —— 不给样式的新行在 Excel 里显示为默认
    字体无边框，那是一张"断裂"的表（AC 3.5 明令样式必须保留）。
    """

    insert_at: int
    count: int
    style_from: int
    table_key: str = ""

    def __post_init__(self) -> None:
        from app.services.workpaper_sync.content_mutation import (
            assert_no_mutation_surface,
        )

        assert_no_mutation_surface(self, label="RowShiftPlan")
        if self.count <= 0:
            raise RowShiftPlanCountError(
                f"插入行数必须 > 0，实得 {self.count} —— 「不插行」应表达为 "
                "`plan is None` 而不是 `count=0`：后者会让位移阶段被真实调用一次并"
                "产出一份「什么都没改但走过写入路径」的产物，把零位移与已位移混为一谈"
            )
        if self.insert_at < 1:
            raise RowShiftPlanRangeError(
                f"插入点行号必须 >= 1，实得 {self.insert_at}"
            )
        if self.style_from < 1:
            raise RowShiftPlanRangeError(
                f"样式来源行号必须 >= 1，实得 {self.style_from}"
            )
        if self.style_from >= self.insert_at:
            # 🔴 判据是 `>= insert_at` 而不是 `>= insert_at + count`：新行区间是
            #    `[insert_at, insert_at+count-1]`，写成后者时 `insert_at=26, count=2,
            #    style_from=27` 会被放过 —— 而 27 **正落在**新行区间内。首版实测就漏了
            #    这一例（探针报「style_from 落在新行区间 未抛」）。
            #
            #    语义上样式必须来自「位移后仍在原位」的行，即 `< insert_at` 的行；
            #    `>= insert_at` 的行位移后跑到别处去了，从它抄样式等于从一个坐标已变的
            #    行抄，插入点与样式源的相对关系无法解释。
            raise RowShiftPlanRangeError(
                f"样式来源行 {self.style_from} 不小于插入点 {self.insert_at} —— "
                f"新行区间是 {self.insert_at}..{self.insert_at + self.count - 1}，"
                "样式必须来自位移后仍在原位的行（即 `< insert_at`）"
            )

    # ── 派生 ──────────────────────────────────────────────────────

    @property
    def inserted_rows(self) -> range:
        return range(self.insert_at, self.insert_at + self.count)

    def shift(self, row: int) -> int:
        """位移前行号 → 位移后行号。"""
        return row + self.count if row >= self.insert_at else row

    def unshift(self, row: int) -> int:
        """位移后行号 → 位移前行号（verifier 的归一化用）。

        🔴 **新行区间上本函数是恒等映射**（`insert_at <= row < insert_at + count`
        全都不满足 `row >= insert_at + count`）。所以新行 unshift 后得到的是**它自己**
        的行号 —— 而那个行号在位移**前**属于另一行真实存在的数据行。

        后果是新行会与 before 侧的原始行**别名**：归一化后两侧拿同一个行号去比，
        digest 要么假红（新行样式继承但无值，内容当然不同），要么在内容恰好相同时
        假绿。两种都错。

        因此**新行不得进入需要归一化的集合** —— 它们属受管区域，由受管字段判据管
        （Requirement 6.5）。这不是"顺带的边界"，是本函数定义域的一部分。
        """
        return row - self.count if row >= self.insert_at + self.count else row

    def as_dict(self) -> dict[str, Any]:
        return {
            "insert_at": self.insert_at,
            "count": self.count,
            "style_from": self.style_from,
            "table_key": self.table_key,
            "inserted_rows": [self.insert_at, self.insert_at + self.count - 1],
        }


@dataclass(frozen=True)
class ShiftReport:
    """位移逐阶段的**实测**计数。

    存在的唯一理由是让守卫能断言「这条分支真的执行了」而不是「没报错」：一个
    什么都没做的位移函数在"产物能打开"这类判据下照样通过。
    """

    renumbered_rows: int = 0
    renumbered_cells: int = 0
    inserted_rows: int = 0
    shifted_refs: Mapping[str, int] = dataclass_field(default_factory=dict)
    shifted_shared_formulas: int = 0
    extended_shared_formulas: int = 0
    shifted_formula_text_ranges: int = 0
    dimension_updated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "renumbered_rows": self.renumbered_rows,
            "renumbered_cells": self.renumbered_cells,
            "inserted_rows": self.inserted_rows,
            "shifted_refs": dict(sorted(self.shifted_refs.items())),
            "shifted_shared_formulas": self.shifted_shared_formulas,
            "extended_shared_formulas": self.extended_shared_formulas,
            "shifted_formula_text_ranges": self.shifted_formula_text_ranges,
            "dimension_updated": self.dimension_updated,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 5. 共享公式 si 索引（Requirement 4.1)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SharedFormulaGroup:
    """一组共享公式：主格坐标 + `ref` 区间 + 成员坐标集。

    既有 `excel_materialize._cell_view` 只判 `shared_ref` 含不含冒号，**从不解析
    `si` 数值** —— 于是「这一格属于哪一组」「这一组有哪些成员」在代码里无从回答。
    位移要改主格 `ref` 就必须先能定位组，故本类补上该索引。
    """

    si: int
    master_coord: str
    ref: str
    member_coords: tuple[str, ...]
    #: 主格 `<f>` 的公式文本。成员格是自闭合的 `<f t="shared" si="N"/>`，自身**不带
    #: 文本** —— 新插入行要继承某个成员的公式，唯一的来源就是主格文本按 fill-down
    #: 翻译。不带这个字段时索引层无法回答「这一组的公式是什么」，:func:`_build_inserted_row`
    #: 只能把新行也做成成员，而那需要主格 `ref` 覆盖新行（实测正是那条路产出了
    #: 4 个落在 ref 之外的孤儿成员）。
    master_text: str = ""

    @property
    def ref_rows(self) -> tuple[int, int]:
        """`ref` 的首末行。单格 ref（如 `H26`）首末行相同。"""
        parts = self.ref.split(":")
        first = _row_of(parts[0]) or 0
        last = _row_of(parts[-1]) or first
        return (min(first, last), max(first, last))

    @property
    def master_column(self) -> str | None:
        return _col_of(self.master_coord)

    @property
    def is_vertical(self) -> bool:
        """主格与全部成员同列 ⇒ 纵向组，可按 fill-down 逐行翻译。

        横向组（如 K11 的 si=3 `B26:G26`）的成员公式相对主格有**列**偏移，
        本模块不做列位移，遇到它 fail closed（:class:`SharedFormulaOrientationError`）。
        """
        column = self.master_column
        if column is None:
            return False
        return all(_col_of(coord) == column for coord in self.member_coords)


def shared_formula_groups(sheet_xml: str) -> Mapping[int, SharedFormulaGroup]:
    """解析 `si` → :class:`SharedFormulaGroup`。

    主格判据 = `<f>` 同时带 `t="shared"`、`si` 与 **`ref`**；成员 = 带 `t="shared"` 与
    `si` 但**无** `ref`（实测多为自闭合 `<f t="shared" si="1"/>`）。

    实测形态（K11 受管 sheet）：si=0 `ref=I7:I26`（跨 footer）、si=1 `ref=H8:H25`（纵向）、
    si=3 `ref=B26:G26`（横向，文本是 `SUM(B7:B25)`）、si=4 `ref=H26`（单格）、
    si=5 `ref=C28:G28`（受管区域**之下**）。
    """
    masters: dict[int, tuple[str, str, str]] = {}
    members: dict[int, list[str]] = {}

    for row_match in _iter_row_blocks(sheet_xml):
        for cell in _CELL_BLOCK_RE.finditer(row_match.body or ""):
            coord = _attr(cell.group("attrs") or "", "r")
            if not coord:
                continue
            body = cell.group("body") or ""
            f_match = _F_RE.search(body)
            if f_match is None:
                continue
            fattrs = f_match.group("fattrs") or ""
            if _attr(fattrs, "t") != "shared":
                continue
            raw_si = _attr(fattrs, "si")
            if raw_si is None or not raw_si.isdigit():
                continue
            si = int(raw_si)
            ref = _attr(fattrs, "ref")
            if ref:
                masters[si] = (coord, ref, f_match.group("text") or "")
            else:
                members.setdefault(si, []).append(coord)

    out: dict[int, SharedFormulaGroup] = {}
    for si, (coord, ref, text) in sorted(masters.items()):
        out[si] = SharedFormulaGroup(
            si=si,
            master_coord=coord,
            ref=ref,
            member_coords=tuple(sorted(members.get(si, ()))),
            master_text=text,
        )
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 6. 清单外结构扫描与双向锁（Requirements 1.5, 1.6）
# ═══════════════════════════════════════════════════════════════════════════

#: 已知**不携带行号**的 sheet 级元素。出现在这里的 tag 不需要位移处理。
#:
#: 与 :data:`ROW_BEARING_STRUCTURES` 一起构成对受管 sheet 元素的完全划分：
#: 两边都不在的 tag ⇒ :func:`scan_unlisted_row_bearing_elements` fail closed。
_ROW_AGNOSTIC_TAGS: Final[frozenset[str]] = frozenset(
    {
        "worksheet", "sheetPr", "outlinePr", "pageSetUpPr", "tabColor",
        "sheetViews", "sheetView", "pane", "selection",
        "sheetFormatPr", "cols", "col",
        "sheetData",
        "sheetProtection", "protectedRanges", "protectedRange",
        "mergeCells", "dataValidations", "hyperlinks", "rowBreaks", "colBreaks",
        "phoneticPr", "printOptions", "pageMargins", "pageSetup",
        "headerFooter", "oddHeader", "oddFooter", "evenHeader", "evenFooter",
        "firstHeader", "firstFooter",
        "drawing", "legacyDrawing", "legacyDrawingHF", "picture", "oleObjects",
        "oleObject", "controls", "control", "controlPr",
        "tableParts", "tablePart", "extLst", "ext",
        "ignoredErrors", "ignoredError", "customProperties", "customProperty",
        "dimension", "autoFilter", "brk",
        # 🔴 `formula1` / `formula2` 曾在这里 —— 那是**错的**：它们可以是带行号的 A1
        #    区间（全库实测 108 处），已移入 `ROW_BEARING_STRUCTURES` 并真实位移。
        #    `formula`（cfRule 的）两张清单里原本都没有，同批补入。
        "v", "f", "is", "t", "r", "rPr",
        "c", "row",
        "customSheetViews", "customSheetView", "scenarios", "scenario",
        "dataConsolidate", "smartTags", "webPublishItems",
        "cellWatches", "cellWatch", "sortState", "filterColumn", "filters", "filter",
        "conditionalFormatting", "cfRule", "colorScale", "dataBar", "iconSet",
        "cfvo", "color", "sheetCalcPr", "rowBreaksExt",
    }
)


def scan_unlisted_row_bearing_elements(sheet_xml: str) -> tuple[str, ...]:
    """受管 sheet 上出现的、既不在位移清单也不在已知无行号清单里的 tag。

    非空即 fail closed 的依据（Requirement 1.6）：一个未登记的元素可能携带行号，
    位移后它仍指向旧行 —— 产出一个看起来正常但引用错行的工作簿。
    """
    listed = {tag for tag, _ in ROW_BEARING_STRUCTURES}
    seen: set[str] = set()
    for match in re.finditer(r"<(/?)([A-Za-z][A-Za-z0-9_.:-]*)", sheet_xml):
        if match.group(1):
            continue
        tag = match.group(2).rsplit(":", 1)[-1]
        if tag in listed or tag in _ROW_AGNOSTIC_TAGS:
            continue
        seen.add(tag)
    return tuple(sorted(seen))


def assert_shift_handlers_cover_structures() -> Mapping[str, tuple[str, ...]]:
    """清单与位移实现按**结构判据**双向锁死（Requirement 1.5）。

    判据不是「注释里写了」而是「函数里真有处理它的分支」：以 ``ast`` 扫本模块，
    收集 :func:`shift_sheet_rows` 及其私有 helper 里出现的
    ``_SHIFT_HANDLER_MARKERS`` 标记，与清单逐项比对。

    🔴 AST 扫描不用 ``strip_comments``：那会连带剥掉三引号包裹的文本块。

    Returns:
        ``{"handled": (...), "delegated": (...)}`` —— 供 evidence 现读。

    Raises:
        UnlistedRowBearingStructureError: 两侧不一致，并指出首个差异项。
    """
    import ast
    from pathlib import Path

    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=__file__)

    # 收集本模块所有函数体里出现的 `_handled(tag, attr)` 调用实参
    handled: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else ""
        )
        if name != "_handled" or len(node.args) != 2:
            continue
        tag_node, attr_node = node.args
        if (
            isinstance(tag_node, ast.Constant)
            and isinstance(tag_node.value, str)
            and isinstance(attr_node, ast.Constant)
            and isinstance(attr_node.value, str)
        ):
            handled.add((tag_node.value, attr_node.value))

    declared = set(ROW_BEARING_STRUCTURES)
    delegated = set(HANDLED_BY_IDENTITY_RETENTION_GATE)
    expected = declared - delegated

    missing = sorted(expected - handled)
    if missing:
        raise UnlistedRowBearingStructureError(
            f"位移敏感清单里的 {missing} 在 `shift_sheet_rows` 里没有对应处理分支"
            f"（首个 {missing[0]}）—— 清单登记了却不处理，位移后它仍指向旧行号"
        )
    extra = sorted(handled - declared)
    if extra:
        raise UnlistedRowBearingStructureError(
            f"`shift_sheet_rows` 处理了清单外的 {extra}（首个 {extra[0]}）—— "
            "实现走在清单前面时，清单就不再是「位移敏感结构的完整清单」"
        )
    overlap = sorted(handled & delegated)
    if overlap:
        raise UnlistedRowBearingStructureError(
            f"{overlap} 同时被本模块处理又被登记为「由 identity 保留门承接」—— "
            "两处都改会产生双重位移"
        )
    return {
        "handled": tuple(f"{tag}{attr}" for tag, attr in sorted(handled)),
        "delegated": tuple(f"{tag}{attr}" for tag, attr in sorted(delegated)),
    }


def _handled(tag: str, attr: str) -> None:
    """位移处理分支的**结构标记**。

    它不做任何事 —— 存在的唯一理由是让 :func:`assert_shift_handlers_cover_structures`
    能以 AST 判据（而不是 grep 字符串）确认某个清单项真的有处理分支。写成函数调用
    而不是注释，因为注释不可执行、grep 又会命中 docstring 里的举例。
    """
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 7. A1 引用与公式的行位移
# ═══════════════════════════════════════════════════════════════════════════


# 🔴 公式文本**不得**用朴素 A1 正则整体替换。全模板库（351 份）实测四类误命中，
#    每一类都会把公式改成错的或直接改死：
#
#    1. **跨 sheet 引用的表名里含「字母+数字」**。`'明细表K11-2'!F29` 的 `K11`
#       被当成「K 列第 11 行」，位移后整条变成 `'明细表K12-2'!F30` —— 指向一个
#       不存在的 sheet，公式当场死掉。实测 **188 份模板含跨 sheet 引用**
#       （占 53.6%）、引用总数 **81,955**，其中表名形如 A1 引用的达 **16,027 次**。
#
#    2. **跨 sheet 引用的目标格本身不该位移**。在本 sheet 插一行不改变别的 sheet
#       的行号，`'明细表K11-2'!F29` 必须逐字不变。朴素正则会把 `F29` 改成 `F30`，
#       静默指向错的源数据 —— 这类错比报错更贵，因为审计取数看着仍然"有值"。
#
#    3. **带数字的函数名**。`LOG10(A1)` 里 `LOG10` 会被匹配成「LOG 列第 10 行」，
#       位移后成 `LOG11(` —— 未知函数。
#
#    4. **字符串字面量**。`IF(A1="K11","是","否")` 引号内的 `K11` 不是引用。
#
#    因此统一走 `_rewrite_formula_refs` 分词扫描：逐段识别字符串字面量 / 跨 sheet
#    前缀 / 跨 sheet 目标格 / 裸 A1 引用，**只对最后一类**改行号。


def _left_boundary_ok(text: str, index: int) -> bool:
    """`index` 处能否作为「裸引用 / sheet 前缀」的起点（左侧边界断言）。"""
    return index == 0 or text[index - 1] not in _LEFT_BOUNDARY_BLOCK


def _prefix_sheet_name(match: re.Match[str]) -> str | None:
    """跨 sheet 前缀指向的 sheet 名；外部工作簿与 3D 引用返回 `None`。

    `None` 的语义是「**不是**本工作簿内某一张确定的 sheet」⇒ 调用侧一律按逐字不动
    处理（Requirement 2.6 / 9.4 / 10.3）。外部工作簿 `[1]…!` 的目标文件不在本系统
    管辖内；3D `Sheet1:Sheet3!` 跨多张 sheet，无法用单一计划表达。

    引号剥离与 `''` 转义还原在这里统一做一次 —— 两个调用方（自限定判定与「行号是否
    跟着改」判定）抄两份必然漂移。

    🔴 **3D 与外部工作簿各有两种写法，`span` / `book` 分组只认得不带引号的那种。**

    Excel 对含标点的名字加引号，而**分隔标记落在引号内**：

    | 形态 | 不带引号（分组命中 ✅） | 带引号（分组 🔴 永不命中） |
    |---|---|---|
    | 3D | `Sheet1:Sheet3!A1` | `'明细表K11-2:明细表K11-3'!F29` |
    | 外部工作簿 | `[1]底稿目录!A2` | `'[31]已审利润纵向分析A1-13-4'!$E$27` |

    带引号时整段被 `first` 分支的 `'(?:[^']|'')*'` 贪婪吃掉，于是剥引号后得到一个
    **含 `:` 或以 `[n]` 开头的假 sheet 名**。所以这里在剥引号**之后**再各查一次 ——
    真实 sheet 名两者都不允许（Excel 禁止 `: \\ / ? * [ ]`）。

    实测规模（全库 351 份）：带引号 3D **0** 处（3D 全库为 0）；带引号外部工作簿
    **2,971 处 / 150 份模板**。后者若不修，那 2,971 处会被当成本工作簿内的 sheet ——
    在 fill-down 下被平移（违反 AC 10.3），在扫描时被误登记成 `target_not_in_workbook`
    而不是 `external_workbook`。

    两个盲区都是**既有的**、非传播能力引入：此前所有带前缀的引用一律逐字不动，盲区
    不可见。`translate_qualified_rows=True`（Task 27）让 3D 那个显形，工作簿级扫描
    （Task 8）让外部工作簿这个显形。
    """
    if match.group("book") or match.group("span"):
        return None
    raw = match.group("first")
    if len(raw) >= 2 and raw.startswith("'") and raw.endswith("'"):
        raw = raw[1:-1].replace("''", "'")
    if ":" in raw:
        # 带引号的 3D 区间（`'A:B'!`）
        return None
    if _QUOTED_BOOK_RE.match(raw):
        # 带引号的外部工作簿（`'[31]名'!`）—— 真实 sheet 名不含 `[` `]`
        return None
    return raw


def _prefix_targets_sheet(match: re.Match[str], current_sheet: str | None) -> bool:
    """跨 sheet 前缀是否指向 `current_sheet` 本身（自限定引用 `'本表'!A1`）。

    外部工作簿 `[1]…!` 与 3D 引用 `Sheet1:Sheet3!` 一律判否 —— 前者根本不在本
    文件里，后者跨多个 sheet 无法用单一 plan 表达。判否即「逐字不动」，是保守侧。
    """
    if current_sheet is None:
        return False
    return _prefix_sheet_name(match) == current_sheet


def _prefix_rows_follow(
    match: re.Match[str],
    *,
    propagate_sheets: frozenset[str],
    translate_qualified_rows: bool,
) -> bool:
    """限定引用的目标格行号**是否要跟着改**。两种语义，各自显式。

    与 :func:`_prefix_targets_sheet` 是不同的问题：那个问「这前缀其实就是本表吗」
    （自限定引用等价于裸引用）；本函数问「这前缀指向**别的**表，那张表的行要跟着改吗」。

    | 触发者 | 语义 | 判定 |
    |---|---|---|
    | `propagate_sheets` | **被引用侧的行被推走了** —— 我指向它，我要跟着改 | 只有声明的那些 sheet |
    | `translate_qualified_rows` | **公式本身被复制到别的行** —— 相对引用随之平移 | 工作簿内**任何** sheet |

    两者的差别在「谁动了」：前者是目标 sheet 动了（插行/删行），所以只有真的动过的
    那些 sheet 才传播；后者是公式自己搬家了（fill-down），Excel 填充柄对**所有**相对
    引用一视同仁，不问目标 sheet 有没有动。混成一个开关会让 fill-down 需要先知道
    「目标 sheet 动没动」—— 而那与它无关。

    外部工作簿 `[1]…!` 与 3D `Sheet1:Sheet3!` 一律返回 `False`（`_prefix_sheet_name`
    对它们返回 `None`）：Requirement 2.6 / 9.4 / 10.3 三处都要求它们逐字不动。

    两个开关都关（默认）时恒假 ⇒ 行为与本 spec 前逐字相同（Requirement 7.4）。
    """
    name = _prefix_sheet_name(match)
    if name is None:
        return False
    if translate_qualified_rows:
        return True
    return name in propagate_sheets


def _rewrite_formula_refs(
    text: str,
    *,
    remap: Callable[[int], int],
    current_sheet: str | None = None,
    extend_end_at: int | None = None,
    extend_by: int = 0,
    freeze_absolute_rows: bool = False,
    propagate_sheets: frozenset[str] = frozenset(),
    translate_qualified_rows: bool = False,
    qualified_only: bool = False,
) -> tuple[str, int]:
    """公式文本行号重写器 —— 本模块**唯一**的 A1 改写入口。

    Args:
        text: 公式文本（`<f>` 的内容）或纯区间字符串（`ref=` / `sqref`）。
        remap: 行号映射（旧行 -> 新行）。
        current_sheet: 本 sheet 名。非空时 `'本表名'!A1` 这种自限定引用按同
            sheet 处理；为 None 时**所有**带前缀的引用逐字不动（保守默认）。
        extend_end_at: 非空时对「末行恰等于该值」的裸区间做扩张（末行 +=
            `extend_by`）。用于契约声明带合计公式的 footer。
        extend_by: 扩张量。
        freeze_absolute_rows: True 时 `$` 锁定的行不动（fill-down 语义）；
            False 时同样位移（插行语义 —— `$` 锁的是"这一行"，插行后那一行
            物理上被推下去了，Excel 自身的插行行为也会改写它）。
        propagate_sheets: **要传播的目标 sheet 名集合**（工作簿级行变更传播）。
            命中集合的跨 sheet 前缀，其后的目标格按 `remap` 改写；未命中的
            一律逐字不动。

            🔴 **空集（默认）时行为与本参数引入前逐字相同** —— 传播是**加法**
            而不是行为翻转。这一条由冻结基线锁死（`Property 28`：全库 351 份
            xlsx / 144,154 处跨 sheet 引用 / 三个情景的顺序敏感 digest），
            生成器 `generate_workbook_row_change_zero_regression_baseline.py`。

            语义与 `current_sheet` **正交**：`current_sheet` 处理的是「自限定
            引用 `'本表'!A1` 等价于裸引用」，本参数处理的是「**别的** sheet 的
            行确实被推走了，指向它的引用必须跟着走」。两者可同时生效。

            外部工作簿 `[1]Sheet1!A1` 与 3D `Sheet1:Sheet3!A1` **永不传播**
            （Requirement 2.6 / 9.4）：前者的目标文件不在本系统管辖内，后者跨
            多张 sheet 无法用单一计划表达。两者都由调用方登记计数，不在此静默
            跳过。
        translate_qualified_rows: True 时**工作簿内任何** sheet 的限定引用其行号
            都按 `remap` 改写 —— fill-down 语义（`translate_formula_rows` 用它）。

            🔴 与 `propagate_sheets` 的区别在「谁动了」：本参数是**公式自己被复制到
            别的行**，Excel 填充柄对所有相对引用一视同仁，不问目标 sheet 动没动；
            `propagate_sheets` 是**目标 sheet 的行被推走了**，所以只对声明过的那些
            sheet 生效。详见 :func:`_prefix_rows_follow` 的对照表。

            与 `freeze_absolute_rows=True` 配合时 `$` 锁定的行不动（AC 10.2）——
            那正是 `$` 的语义：公式搬家而锁定的格没搬。
        qualified_only: True 时**只**改带 sheet 前缀的引用，裸引用（`A20`）逐字不动。

            🔴 **改写引用侧 sheet 时必须开它。** 场景：受管 sheet `明细表D2-2` 插行，
            要改写引用侧 sheet `审定表D2-1` 上的公式 `=SUM(A20:B20)+'明细表D2-2'!F20`。
            正确结果是 `=SUM(A20:B20)+'明细表D2-2'!F21`：

            * `'明细表D2-2'!F20` → **该动**（它指向的那笔数据被推走了）；
            * `A20:B20` → **不该动**（那是 `审定表D2-1` 自己的坐标，没人在它上面插行）。

            不开这个开关时两者共用 `remap` ⇒ 裸引用被一起推成 `A21:B21`，把引用侧 sheet
            自己的坐标全部推错。恒等 `remap` 也绕不过（那样限定引用也不动了，等于没传播）。

            与 `propagate_sheets` 是**配套**的：前者说「哪些目标 sheet 要传播」，本参数说
            「别动引用侧 sheet 自己的坐标」。受管 sheet 自身的改写（`shift_sheet_rows`）
            不开它 —— 那里裸引用**正是**要位移的对象。

    Returns:
        `(新文本, 改动的引用个数)`
    """
    if not text:
        return text, 0

    changed = 0

    def _piece(raw: str, *, force_row: int | None = None) -> str:
        """重写一个 A1 坐标片段；命中改动时累加 `changed`。"""
        nonlocal changed
        found = _A1_PIECE_RE.fullmatch(raw)
        if found is None:
            return raw
        row = int(found.group("row"))
        if force_row is not None:
            new_row = force_row
        elif freeze_absolute_rows and found.group("abs_row"):
            new_row = row
        else:
            new_row = remap(row)
        if new_row == row:
            return raw
        changed += 1
        return (
            f"{found.group('abs_col')}{found.group('col')}"
            f"{found.group('abs_row')}{new_row}"
        )

    def _row_only_piece(raw: str) -> str:
        """重写一个**裸行**片段（`6` / `$6`）—— 整行区间的端点。

        只被传播路径调用（见 `_propagated_token`）。`$` 锁定在插行语义下**同样**
        位移：锁的是"这一行"，而那一行物理上被推下去了。
        """
        nonlocal changed
        found = _ROW_ONLY_PIECE_RE.fullmatch(raw)
        if found is None:
            return raw
        row = int(found.group("row"))
        new_row = row if (freeze_absolute_rows and found.group("abs_row")) else remap(row)
        if new_row == row:
            return raw
        changed += 1
        return f"{found.group('abs_row')}{new_row}"

    def _propagated_token(token: str) -> str:
        """按 token 形态分派重写 —— 传播路径专用。

        `_REF_TOKEN_RE` 有三种形态，三者的行号位置不同，必须分开处置：

        | 形态 | 样本 | 处置 |
        |---|---|---|
        | 单格 / 带列标区间 | `F20` / `$AI$13:$AI$25` | 逐端点走 `_piece` |
        | **整行区间**（无列标） | `$2:$6` | 逐端点走 `_row_only_piece` |
        | 整列区间（无行号） | `$A:$C` | 逐字不动 —— 它不含行号 |

        整列区间落进 `_piece` 时 `fullmatch` 返回 None 而被原样退回，看似也对；
        但那是**碰巧**对。写成显式分派，是为了让「整列区间不含行号所以不传播」
        成为一条可读的判断，而不是依赖另一个正则的失配副作用。
        """
        parts = token.split(":")
        if all(_A1_PIECE_RE.fullmatch(p) for p in parts):
            return ":".join(_piece(p) for p in parts)
        if all(_ROW_ONLY_PIECE_RE.fullmatch(p) for p in parts):
            return ":".join(_row_only_piece(p) for p in parts)
        return token

    out: list[str] = []
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        # (a) 字符串字面量 —— 逐字照抄（误命中类 4）
        if char == '"':
            literal = _STRING_LITERAL_RE.match(text, index)
            if literal is not None:
                out.append(literal.group(0))
                index = literal.end()
                continue
            out.append(char)
            index += 1
            continue

        # (a2) XML 实体形态的字符串字面量 `&quot;...&quot;`（cfRule 的 formula 实测形态）
        if char == "&":
            literal = _ENTITY_LITERAL_RE.match(text, index)
            if literal is not None:
                out.append(literal.group(0))
                index = literal.end()
                continue

        if _left_boundary_ok(text, index):
            # (b) 跨 sheet / 跨工作簿前缀 —— 表名逐字照抄（误命中类 1）；
            #     其后的目标格分三种处置：
            #       ① 自限定（`'本表'!A1`）  → 等价裸引用，位移
            #       ② 声明传播的目标 sheet   → 传播（工作簿级行变更，本 spec 新增）
            #       ③ 其余                   → 逐字不动（误命中类 2，保守默认）
            prefix = _QUALIFIED_PREFIX_RE.match(text, index)
            if prefix is not None:
                out.append(prefix.group(0))
                index = prefix.end()
                target = _REF_TOKEN_RE.match(text, index)
                if target is not None:
                    token = target.group(0)
                    if _prefix_targets_sheet(prefix, current_sheet):
                        out.append(
                            ":".join(_piece(part) for part in token.split(":"))
                        )
                    elif _prefix_rows_follow(
                        prefix,
                        propagate_sheets=propagate_sheets,
                        translate_qualified_rows=translate_qualified_rows,
                    ):
                        out.append(_propagated_token(token))
                    else:
                        out.append(token)
                    index = target.end()
                continue

            # (c) 裸 A1 引用（单格或区间）—— 唯一会改行号的分支。
            #     右侧边界断言已在 `_BARE_TOKEN_RE` 里排除 `LOG10(`（误命中类 3）。
            bare = _BARE_TOKEN_RE.match(text, index)
            if bare is not None:
                if qualified_only:
                    # 改写引用侧 sheet：裸引用是**它自己**的坐标，没人推它 ⇒ 逐字照抄。
                    # 仍要消费掉整个 token，否则下面会从 token 中间重新匹配。
                    out.append(bare.group(0))
                    index = bare.end()
                    continue
                head, tail = bare.group("head"), bare.group("tail")
                if tail is None:
                    out.append(_piece(head))
                else:
                    new_head = _piece(head)
                    new_tail = _piece(tail)
                    # 扩张只作用于「位移后末行恰等于 extend_end_at」的区间：
                    # 追加到受管区末尾时区间末行恰好是 `insert_at - 1`，普通位移
                    # 规则碰不到它，不扩张合计就漏算新行（Requirement 4.4 / 4.6）。
                    # 中间插入时末行 >= insert_at，普通规则已带到位，不得再扩一次。
                    if extend_end_at is not None and extend_by:
                        tail_row = _row_of(new_tail.replace("$", ""))
                        if tail_row == extend_end_at:
                            new_tail = _piece(new_tail, force_row=tail_row + extend_by)
                    out.append(f"{new_head}:{new_tail}")
                index = bare.end()
                continue

        out.append(char)
        index += 1

    return "".join(out), changed


def _shift_a1_rows_in_text(
    text: str,
    *,
    plan: RowShiftPlan,
    extend_end_at: int | None = None,
    current_sheet: str | None = None,
) -> tuple[str, int]:
    """位移文本里**裸** A1 引用的行号；返回 `(新文本, 改动数)`。

    `$` 前缀的绝对行**同样**位移 —— 绝对引用的语义是"锁定这一格"，插行时那一格
    物理上被推下去了，Excel 自身的插行行为也会改写它。不位移会让绝对引用指向别的格。

    跨 sheet 引用（`'明细表K11-2'!F29`）**逐字不动**：本 sheet 插行不改变别的
    sheet 的行号，表名也不是坐标。详见 §7 顶部的四类误命中说明。

    `extend_end_at` 非空时额外做**扩张**：区间末行恰等于该值的，末行 += count。
    这只用于契约声明带合计公式的 footer（Requirement 4.4）—— 追加到受管区域末尾时，
    区间末行恰好是 `insert_at - 1`，普通位移规则碰不到它，合计会漏算新行。
    """
    return _rewrite_formula_refs(
        text,
        remap=plan.shift,
        current_sheet=current_sheet,
        extend_end_at=extend_end_at,
        extend_by=plan.count,
    )


def translate_formula_rows(
    text: str, *, from_row: int, to_row: int, current_sheet: str | None = None
) -> str:
    """按 Excel fill-down 语义把公式从 `from_row` 翻译到 `to_row`。

    相对行引用整体加 `to_row - from_row`；`$` 锁定的绝对行**不动**（那正是 `$` 的
    语义，与 :func:`_shift_a1_rows_in_text` 的插行场景相反 —— 插行是"格被推走了"，
    填充是"公式被复制到别处"）。

    🔴 **跨 sheet 引用同样平移**（`excel-workbook-wide-row-change-propagation`
    Requirement 10 / Task 27 落地，2026-09-05）。`'明细表K11-2'!F29` 从行 25 填到
    行 26 得 `'明细表K11-2'!F30` —— 与 Excel 填充柄一致：**相对引用不论是否带 sheet
    前缀都随行平移**，`$` 锁定的不平移。

    ⚠ 本函数早先的 docstring 声称「Excel 的填充柄也是这个行为 —— 相对引用只在**本**
    sheet 内平移」。**那句与 Excel 实际语义相反**，且与上游 spec 测试里对同一现象的
    描述互相矛盾（AC 10.6 要求改正它，留着会让下一个人按错的描述写判据）。

    修之前的缺陷形态（Wave 0 实测）：新插入行**照抄**样式来源行的跨 sheet 引用，
    于是新行 26/27 与来源行 25 指向**同一个源格** ⇒ 静默重复取数。最隐蔽的是混合
    形态 `='明细表K11-2'!F29+G25` —— 裸引用平移了、跨 sheet 引用没平移，同一条公式
    里两个引用的行语义不一致，比统一不平移更难发现。

    与 `propagate_sheets`（Requirement 2）是**两个方向**，不可混用：

    * 本函数 —— 「我新增了行，新行的取数源要跟着走」（受管 sheet 新行 → 别的 sheet）；
    * `propagate_sheets` —— 「别人指向我，我插行了，别人要跟着改」（引用侧 → 受管 sheet）。

    外部工作簿与 3D 引用**不**平移（AC 10.3），由调用方登记计数。

    新插入行必须带公式，否则 `_patch_sheet_xml` 对 `formula` 模式字段抛
    「受保护公式格在 substrate 里不存在 —— 不得凭空造一个公式格」。
    """
    delta = to_row - from_row
    if delta == 0:
        return text
    shifted, _ = _rewrite_formula_refs(
        text,
        remap=lambda row: row + delta,
        current_sheet=current_sheet,
        freeze_absolute_rows=True,
        translate_qualified_rows=True,
    )
    return shifted


def _shift_sqref(value: str, plan: RowShiftPlan) -> str:
    """`sqref` 可含多个空格分隔的区间，逐区间位移。"""
    parts = [p for p in value.split() if p]
    shifted = [_shift_a1_rows_in_text(part, plan=plan)[0] for part in parts]
    return " ".join(shifted)


def unextend_total_formula(text: str, *, plan: RowShiftPlan) -> str:
    """把**合计区间扩张**反向还原（verifier 归一化用）。

    Spec: excel-structural-row-insertion-and-shift-aware-verification（Requirement 6.9）

    ═══ 为什么必须有这一条 ═══

    `plan.unshift` 还原不了扩张 —— 那正是扩张的语义：合计范围**真的变大了**，不是被推
    下去了。实测形态：`SUM(B7:B25)` 扩张成 `SUM(B7:B27)`，而 `unshift(27) == 27`
    （27 < `insert_at + count` = 28）⇒ 归一化后两侧仍不等 ⇒ 与计划一致的插行被判漂移。

    K11 上这一条无法用「让契约覆盖该合计格」绕开：合计行恰好**就在插入点上**（26），
    契约在那里声明静态字段会立刻撞第五类拒绝理由（静态行落在插入点及其之下）。
    ⇒ verifier 必须能表达「这一处扩张是被契约授权的」。

    这不是放宽判据：还原用的是**写盘之前冻结的声明**（`plan.count` + 契约的
    `carries_total_formula`），与 `unshift` 同源。扩张量与声明不符时还原不回去 ⇒ 仍判漂移。

    还原是扩张的**精确逆运算**：正向对「位移后末行 == `insert_at - 1`」的区间末行 `+count`，
    逆向对「末行 == `insert_at - 1 + count`」的区间末行 `-count`。
    """
    if not text:
        return text
    out, _ = _rewrite_formula_refs(
        text,
        remap=plan.unshift,
        extend_end_at=plan.insert_at - 1 + plan.count,
        extend_by=-plan.count,
    )
    return out


@dataclass(frozen=True)
class QualifiedReference:
    """公式文本里一处**带 sheet 前缀**的引用（分词结果，只读）。

    `kind` 的四个取值与 :func:`_rewrite_formula_refs` 的前缀分支处置**一一对应**：

    | kind | 样本 | 改写器怎么处置 |
    |---|---|---|
    | `sheet` | `'明细表D2-2'!F13` | 命中 `propagate_sheets` 时传播，否则不动 |
    | `three_d` | `'A:B'!F13` / `A:B!F13` | 永不动（跨多 sheet，单一计划表达不了） |
    | `external` | `[1]Sheet1!F13` | 永不动（目标文件不在本系统管辖内） |
    | `no_target` | `'明细表D2-2'!#REF!` | 前缀命中但取不到坐标 ⇒ 无从改写 |

    🔴 `no_target` 必须是**独立**取值而不是「`sheet` 且 token 为空」：D2 上有 10 处
    `'明细表D2-2'!#REF!`，把它并进 `sheet` 会让调用方以为那 10 处已被传播处理。
    """

    kind: str
    #: sheet 名（已剥引号、已还原 `''` 转义）。`three_d` / `external` 时为原始前缀文本。
    sheet_name: str
    #: 前缀之后的目标 token（`F13` / `$A$1:$AK$31` / `$2:$6` / `$A:$C`）。取不到时为空串。
    token: str
    #: 前缀在原文里的起始偏移（供定位与去重）。
    start: int
    #: 整段（前缀 + token）原文。
    raw: str

    @property
    def rows(self) -> tuple[int, ...]:
        """token 里**字面出现**的行号（升序去重）。整列区间 `$A:$C` 返回空元组。

        `$AI$13:$AI$25` 返回 `(13, 25)` —— **两个端点**，不是 13..25 全部。区间内部的行
        见 :attr:`covered_rows`。两者刻意分开，因为它们回答的是不同问题：

        * `rows` —— 「这处引用的行号是哪几个」⇒ 传播时要改的就是这些数字；
        * `covered_rows` —— 「这处引用覆盖了哪些行」⇒ 判某行是否被引用到时要用它。

        混用会出错：删掉 `$13:$25` 区间内部的行 18 时，Excel 语义是区间收缩成 `$13:$24`，
        端点变了但「引用没坏」；而按 `rows` 判会以为行 18 没被引用到。
        """
        if not self.token:
            return ()
        found: list[int] = []
        for part in self.token.split(":"):
            piece = _A1_PIECE_RE.fullmatch(part)
            if piece is not None:
                found.append(int(piece.group("row")))
                continue
            bare = _ROW_ONLY_PIECE_RE.fullmatch(part)
            if bare is not None:
                found.append(int(bare.group("row")))
        return tuple(sorted(set(found)))

    @property
    def covered_rows(self) -> tuple[int, ...]:
        """这处引用**覆盖**的全部行（区间内部展开）。

        单格 `F13` → `(13,)`；区间 `$AI$13:$AI$25` → `(13, 14, …, 25)`；整列 `$A:$C` → `()`。

        ⚠ 覆盖面可以很大：D2 的 `_xlnm.Print_Area` 是 `$A$1:$AM$34` ⇒ 覆盖 34 行。所以
        「被覆盖」不等于「不可删」—— 那个判断属 Requirement 3 的删行侧，本属性只提供事实。
        """
        marks = self.rows
        if not marks:
            return ()
        return tuple(range(marks[0], marks[-1] + 1))


def iter_qualified_references(
    text: str, *, current_sheet: str | None = None
) -> Iterable[QualifiedReference]:
    """分词出文本里全部**带前缀**的引用。工作簿级传播扫描的**唯一**分词入口。

    ═══ 为什么这个函数必须长在这里 ═══

    传播扫描要回答「哪些引用指向受管 sheet」，而这必须与 :func:`_rewrite_formula_refs`
    **同口径** —— 扫描认为某处是引用而改写器不认（或反之），就会出现「声明传播量与实测
    对不上」的假红，或更糟：漏扫一类载体 ⇒ 那类引用静默指向错行。

    做法是**共用同一批原语**（`_STRING_LITERAL_RE` / `_ENTITY_LITERAL_RE` /
    `_left_boundary_ok` / `_QUALIFIED_PREFIX_RE` / `_REF_TOKEN_RE` / `_prefix_sheet_name`），
    而不是另写一个扫描器。四类误命中防线（跨 sheet 表名 / 跨 sheet 目标格 / 带数字函数名 /
    字符串字面量含 `&quot;` 实体形态）因此自动继承。

    🔴 两个生成器（`generate_row_change_reachability.py` /
    `generate_workbook_row_change_zero_regression_baseline.py`）各有一份 `qualified_hits`，
    都注释「分支顺序与生产改写器逐一对应」—— 那已经是两份拷贝。本函数是权威版，新代码
    一律用它；两个生成器保留各自那份的理由是它们冻结的是**历史**口径（零回归基线的分母
    依赖它逐字不变），不能跟着生产演进。这一点由
    `test_scanner_agrees_with_rewriter_on_whole_corpus` 在全库上取证：本函数认定的
    `sheet` 类引用集合，必须与「把这些 sheet 全放进 `propagate_sheets` 后改写器真的改动
    的位置」逐一吻合。

    Args:
        text: 公式文本或纯区间字符串。
        current_sheet: 本 sheet 名。非空时自限定引用（`'本表'!A1`）的 `kind` 仍是
            `sheet`、`sheet_name` 等于它 —— **不**在这里过滤掉，因为「自限定算不算跨
            sheet」取决于调用方：可达性统计要排除它，传播扫描要保留它（目标 sheet 就是
            受管 sheet 自己时，自限定引用同样需要传播）。
    """
    if not text:
        return
    index, length = 0, len(text)
    while index < length:
        char = text[index]

        # 字符串字面量逐字跳过（两种形态，与改写器一致）
        if char == '"':
            literal = _STRING_LITERAL_RE.match(text, index)
            index = literal.end() if literal is not None else index + 1
            continue
        if char == "&":
            literal = _ENTITY_LITERAL_RE.match(text, index)
            if literal is not None:
                index = literal.end()
                continue

        if _left_boundary_ok(text, index):
            prefix = _QUALIFIED_PREFIX_RE.match(text, index)
            if prefix is not None:
                start = index
                index = prefix.end()
                target = _REF_TOKEN_RE.match(text, index)
                token = ""
                if target is not None:
                    token = target.group(0)
                    index = target.end()

                name = _prefix_sheet_name(prefix)
                raw_prefix = prefix.group(0).rstrip("!")
                if prefix.group("book") or _QUOTED_BOOK_RE.match(
                    raw_prefix.strip("'")
                ):
                    # 两种写法：`[1]Sheet1!` 与 `'[31]已审利润纵向分析A1-13-4'!`
                    kind, label = "external", raw_prefix
                elif name is None:
                    # `_prefix_sheet_name` 对 3D（两种写法）返回 None
                    kind, label = "three_d", raw_prefix
                elif not token:
                    # 🔴 前缀命中但取不到坐标（`'表'!#REF!`）—— 必须可分辨
                    kind, label = "no_target", name
                else:
                    kind, label = "sheet", name

                yield QualifiedReference(
                    kind=kind,
                    sheet_name=label,
                    token=token,
                    start=start,
                    raw=text[start:index],
                )
                continue
        index += 1


def remap_a1_rows(text: str, *, remap: Callable[[int], int]) -> str:
    """把文本里**裸** A1 引用的行号按 `remap` 改写。本模块 A1 改写的唯一公开出口。

    存在的理由是 verifier 侧要做 **shift-aware 归一化**（把位移后的行号反向映射回位移前
    口径再喂 hash），而那是 `remap = plan.unshift` 而不是 `plan.shift`。

    🔴 不让 verifier 自己写一份 A1 改写：那会变成本仓库第二个 A1 改写入口，四类误命中
    防线（跨 sheet 表名 / 跨 sheet 目标格 / 带数字函数名 / 字符串字面量含 `&quot;` 实体
    形态）就要各维护两份 —— 而两份必然漂移。Property 27 用 AST 锁死「只有一个入口」。

    归一化**只作用于比对**，不改动任何 artifact 字节（Requirement 6.7）。
    """
    if not text:
        return text
    out, _ = _rewrite_formula_refs(text, remap=remap)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 7b. 结构块归一化表 —— **从清单派生**，不手写第二份
# ═══════════════════════════════════════════════════════════════════════════
#
# verifier 的 `_sheet_structure_digest` 要把结构块里携带行号的属性/文本归一化后再序列化。
# 「哪些属性携带行号」这件事已经写在 :data:`ROW_BEARING_STRUCTURES` 里了 —— 在 verifier
# 侧再手抄一份清单，就是本仓库反复踩的「第二真源」：加一项结构时只改一处，另一处静默漏掉，
# 而漏掉的后果是那类结构的位移**不被归一化** ⇒ 与计划一致的插行被判成漂移（假红），
# 或者更糟：归一化多做了一项 ⇒ 真实漂移被抹平（假绿）。
#
# 所以三张表全部由清单**派生**，并用 :func:`assert_structure_normalization_covers_structures`
# 断言「清单里每一项恰好落进四个桶之一」。加新项时不做决定就会打红。

#: 清单里**不由结构块归一化承接**的项，每条写明由谁承接。
NORMALIZED_BY_CELL_DIGEST: Final[Mapping[tuple[str, str], str]] = {
    ("row", "@r"): "行号本体，由 `_managed_sheet_cell_digest` 的逐格归一化承接",
    ("c", "@r"): "格坐标本体，同上",
    ("f", "@ref"): "在 `<sheetData>` 内，属单元格内容，由逐格 digest 承接",
    ("f", "text-a1-ranges"): "同上",
}

#: 属性值是**裸行号整数**（不是 A1 引用）的项。
_BARE_ROW_NUMBER_KEYS: Final[frozenset[tuple[str, str]]] = frozenset({("brk", "@id")})

#: 携带行号的是元素**文本**而不是属性的项。
_TEXT_A1_MARKER: Final[str] = "text-a1-ranges"


def _derive_structure_tables() -> tuple[
    Mapping[str, tuple[str, ...]], Mapping[str, tuple[str, ...]], frozenset[str]
]:
    a1_attrs: dict[str, list[str]] = {}
    bare_attrs: dict[str, list[str]] = {}
    text_tags: set[str] = set()
    for tag, attr in ROW_BEARING_STRUCTURES:
        key = (tag, attr)
        if key in NORMALIZED_BY_CELL_DIGEST or key in HANDLED_BY_IDENTITY_RETENTION_GATE:
            continue
        if attr == _TEXT_A1_MARKER:
            text_tags.add(tag)
            continue
        if key in _BARE_ROW_NUMBER_KEYS:
            bare_attrs.setdefault(tag, []).append(attr.lstrip("@"))
            continue
        bare_name = attr.lstrip("@")
        a1_attrs.setdefault(tag, []).append(bare_name)
    return (
        {tag: tuple(sorted(names)) for tag, names in sorted(a1_attrs.items())},
        {tag: tuple(sorted(names)) for tag, names in sorted(bare_attrs.items())},
        frozenset(text_tags),
    )


(
    STRUCTURE_ROW_BEARING_ATTRS,
    STRUCTURE_BARE_ROW_ATTRS,
    STRUCTURE_ROW_BEARING_TEXT_TAGS,
) = _derive_structure_tables()


def assert_structure_normalization_covers_structures() -> Mapping[str, tuple[str, ...]]:
    """清单里每一项恰好落进四个桶之一（A1 属性 / 裸行号属性 / 元素文本 / 已委派）。

    Raises:
        UnlistedRowBearingStructureError: 有项未落桶或落进多个桶。
    """
    buckets: dict[tuple[str, str], list[str]] = {}
    for tag, attr in ROW_BEARING_STRUCTURES:
        key = (tag, attr)
        hits: list[str] = []
        if key in NORMALIZED_BY_CELL_DIGEST:
            hits.append("cell_digest")
        if key in HANDLED_BY_IDENTITY_RETENTION_GATE:
            hits.append("identity_retention_gate")
        if attr == _TEXT_A1_MARKER and tag in STRUCTURE_ROW_BEARING_TEXT_TAGS:
            hits.append("structure_text")
        if attr.lstrip("@") in STRUCTURE_BARE_ROW_ATTRS.get(tag, ()):
            hits.append("structure_bare_row_attr")
        if attr.lstrip("@") in STRUCTURE_ROW_BEARING_ATTRS.get(tag, ()):
            hits.append("structure_a1_attr")
        buckets[key] = hits

    unassigned = sorted(key for key, hits in buckets.items() if not hits)
    if unassigned:
        raise UnlistedRowBearingStructureError(
            f"位移敏感清单里的 {unassigned}（首个 {unassigned[0]}）没有落进任何归一化桶 —— "
            "那类结构位移后不会被 verifier 反向归一化，与计划一致的插行会被判成漂移"
        )
    ambiguous = sorted(key for key, hits in buckets.items() if len(hits) > 1)
    if ambiguous:
        raise UnlistedRowBearingStructureError(
            f"{ambiguous} 同时落进多个归一化桶（{[buckets[k] for k in ambiguous]}）—— "
            "会被归一化两次，等于把真实漂移抹平"
        )
    return {
        "a1_attrs": tuple(
            f"{tag}@{name}"
            for tag, names in STRUCTURE_ROW_BEARING_ATTRS.items()
            for name in names
        ),
        "bare_row_attrs": tuple(
            f"{tag}@{name}"
            for tag, names in STRUCTURE_BARE_ROW_ATTRS.items()
            for name in names
        ),
        "text_tags": tuple(sorted(STRUCTURE_ROW_BEARING_TEXT_TAGS)),
        "delegated": tuple(
            f"{tag}{attr}"
            for tag, attr in sorted(
                set(NORMALIZED_BY_CELL_DIGEST) | set(HANDLED_BY_IDENTITY_RETENTION_GATE)
            )
        ),
    }


#: import 期自检 —— 清单与四个归一化桶的对齐不能等到有人跑测试才发现。
assert_structure_normalization_covers_structures()


# ═══════════════════════════════════════════════════════════════════════════
# 8. sheetData 的行块解析
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _RowBlock:
    row: int
    attrs: str
    body: str | None
    raw: str


def _iter_row_blocks(sheet_xml: str) -> Iterable[_RowBlock]:
    for match in _ROW_BLOCK_RE.finditer(sheet_xml):
        attrs = match.group("attrs") or ""
        raw_row = _attr(attrs, "r")
        if raw_row is None or not raw_row.isdigit():
            continue
        yield _RowBlock(
            row=int(raw_row),
            attrs=attrs,
            body=match.group("body"),
            raw=match.group(0),
        )


def _render_row(block: _RowBlock) -> str:
    if block.body is None:
        return f"<row{block.attrs}/>"
    return f"<row{block.attrs}>{block.body}</row>"


# ═══════════════════════════════════════════════════════════════════════════
# 9. 位移主函数（Requirements 3.1~3.8, 4.2~4.8）
# ═══════════════════════════════════════════════════════════════════════════
#
# 分阶段而不是一遍正则扫完，理由是每阶段的判据不同：
#
#   A  行/格重编号        位移前 >= insert_at 的整体 +count
#   B  插入新行           从 style_from 继承样式 + fill-down 翻译公式
#   C  受管区外的 ref     mergeCell / dataValidation / conditionalFormatting
#   D  尾部元素           hyperlink / autoFilter / brk
#   E  共享公式           主格 ref 位移或扩张；成员随行走
#   F  dimension          末行不小于实际最大行号
#
# 🔴 A 用「重建 sheetData」而不是「就地正则替换」：就地替换在自顶向下时会让
#    `r="14"` 先变 `r="15"`，随后处理原始 `r="15"` 时无法区分它是原始行还是刚改过的
#    行（自底向上能绕开，但重建更直接且不依赖遍历顺序）。


def shift_sheet_rows(
    sheet_xml: str,
    plan: RowShiftPlan,
    *,
    total_formula_rows: Sequence[int] = (),
    managed_columns: Sequence[str] = (),
) -> tuple[str, ShiftReport]:
    """在受管 sheet XML 上执行结构性插行。**纯函数**。

    Args:
        sheet_xml: 位移前的 sheet XML。**不被修改**。
        plan: 冻结的位移声明。
        total_formula_rows: 契约声明「携带合计公式」的行号（位移**前**口径）。
            只有这些行上的公式区间会被**扩张**；其余一律只位移
            （Requirement 4.4 / 4.6）。
        managed_columns: 受管列。新插入行只在这些列上造格；给空则按 `style_from`
            行的全部列造。

    Returns:
        `(新 XML, ShiftReport)`。

    Raises:
        UnlistedRowBearingStructureError: 出现清单外携带行号的元素。
        RowShiftStyleSourceMissingError: 样式来源行不存在。
        SharedFormulaSpanError: 共享公式组成员跨度与主格 ref 不一致。
    """
    unlisted = scan_unlisted_row_bearing_elements(sheet_xml)
    if unlisted:
        raise UnlistedRowBearingStructureError(
            f"受管 sheet 上出现清单外元素 {list(unlisted)}（首个 {unlisted[0]!r}）—— "
            "它可能携带行号；位移后仍指向旧行会产出一个「看起来正常但引用错行」的"
            "工作簿。请先把它登记进 `ROW_BEARING_STRUCTURES` 或 `_ROW_AGNOSTIC_TAGS`"
        )

    groups = shared_formula_groups(sheet_xml)
    _assert_shared_formula_spans_consistent(groups)

    total_rows = frozenset(int(row) for row in total_formula_rows)
    body_match = _SHEETDATA_RE.search(sheet_xml)
    if body_match is None:
        if _SHEETDATA_EMPTY_RE.search(sheet_xml):
            raise RowShiftStyleSourceMissingError(
                f"sheet 的 <sheetData> 为空，样式来源行 {plan.style_from} 不存在"
            )
        raise RowShiftStyleSourceMissingError("sheet XML 缺 <sheetData>")

    blocks = list(_iter_row_blocks(body_match.group("body")))
    by_row = {block.row: block for block in blocks}
    if plan.style_from not in by_row:
        raise RowShiftStyleSourceMissingError(
            f"样式来源行 {plan.style_from} 在 sheet XML 里不存在"
            f"（实测行号 {sorted(by_row)[:8]}…共 {len(by_row)} 行）—— "
            "新插入行无从继承样式；不得产出无样式行（AC 3.5）"
        )

    # ── 阶段 A：重编号 ────────────────────────────────────────────
    _handled("row", "@r")
    _handled("c", "@r")
    renumbered_rows = 0
    renumbered_cells = 0
    shifted_shared = 0
    extended_shared = 0
    shifted_text_ranges = 0
    rebuilt: dict[int, str] = {}

    for block in blocks:
        new_row = plan.shift(block.row)
        attrs = block.attrs
        body = block.body
        if new_row != block.row:
            attrs = _set_attr(attrs, "r", str(new_row))
            renumbered_rows += 1
        if body:
            body, cells_changed, shared_delta, text_delta, extend_delta = _shift_row_body(
                body,
                plan=plan,
                source_row=block.row,
                target_row=new_row,
                groups=groups,
                is_total_row=block.row in total_rows,
            )
            renumbered_cells += cells_changed
            shifted_shared += shared_delta
            shifted_text_ranges += text_delta
            extended_shared += extend_delta
        rebuilt[new_row] = _render_row(
            _RowBlock(row=new_row, attrs=attrs, body=body, raw="")
        )

    # ── 阶段 E 的结构标记 ── 实际改写在 `_shift_cell_formula` 里逐格发生；
    #    `extended_shared` 是**实测**扩张处数（拿"扩张版"与"纯位移版"逐格比出来的），
    #    不是「主格行号落在 total_rows 里」这种按声明推的计数 —— 后者在扩张分支被
    #    短路后照样是非零，于是 ShiftReport 反而成了假绿的帮凶。
    _handled("f", "@ref")
    _handled("f", "text-a1-ranges")

    # ── 阶段 B：插入新行 ──────────────────────────────────────────
    source_block = by_row[plan.style_from]
    for offset, new_row in enumerate(plan.inserted_rows):
        rebuilt[new_row] = _build_inserted_row(
            source=source_block,
            new_row=new_row,
            managed_columns=managed_columns,
            groups=groups,
            plan=plan,
        )

    new_body = "".join(rebuilt[row] for row in sorted(rebuilt))
    out = (
        sheet_xml[: body_match.start()]
        + body_match.group("open")
        + new_body
        + body_match.group("close")
        + sheet_xml[body_match.end() :]
    )

    # ── 阶段 C/D：受管区外的 ref / 尾部元素 ──────────────────────
    out, ref_counts = _shift_outside_sheetdata(out, plan=plan)

    # ── 阶段 F：dimension ────────────────────────────────────────
    _handled("dimension", "@ref")
    out, dimension_updated = _update_dimension(out, plan=plan, max_row=max(rebuilt))

    # ── 出口自证：位移后的共享公式组必须仍然自洽 ──────────────────
    #
    # 🔴 入口也跑同一条判据，但只查入口是不够的：入口证明的是「原模板自洽」，
    #    而孤儿成员恰恰是**本函数自己造出来的**（首版实测 4 个）。判据只守在入口
    #    时，自产的不自洽无人查 —— 那是「守卫层级不够」的假绿形态。
    _assert_shared_formula_spans_consistent(
        shared_formula_groups(out), stage="位移后（本函数产物）"
    )

    return out, ShiftReport(
        renumbered_rows=renumbered_rows,
        renumbered_cells=renumbered_cells,
        inserted_rows=plan.count,
        shifted_refs=ref_counts,
        shifted_shared_formulas=shifted_shared,
        extended_shared_formulas=extended_shared,
        shifted_formula_text_ranges=shifted_text_ranges,
        dimension_updated=dimension_updated,
    )


def _assert_shared_formula_spans_consistent(
    groups: Mapping[int, SharedFormulaGroup], *, stage: str = "位移前（入参）"
) -> None:
    """每组成员必须落在主格 `ref` 的行区间内（Requirement 4.7）。

    不一致意味着这份 workbook 的共享公式组已经不自洽（主格 ref 与成员分布对不上），
    位移后无法保证整组仍有效 —— fail closed 而不是猜。

    Args:
        stage: 出现在失败消息里，区分「原模板本来就不自洽」与「本函数把它弄坏了」。
            两者的处置完全不同（前者拒绝该模板，后者是位移实现的缺陷），消息里不
            带这个区分时排查要从头复现一遍。
    """
    for si, group in sorted(groups.items()):
        first, last = group.ref_rows
        stray = [
            coord
            for coord in group.member_coords
            if not (first <= (_row_of(coord) or -1) <= last)
        ]
        if stray:
            raise SharedFormulaSpanError(
                f"[{stage}] 共享公式组 si={si}（主格 {group.master_coord}, "
                f"ref={group.ref}）的成员 {stray[:3]}（共 {len(stray)} 个）落在 ref "
                f"行区间 {first}..{last} 之外 —— 主格 ref 与成员分布不自洽，"
                "位移后无法保证整组仍有效"
            )


def _shift_row_body(
    body: str,
    *,
    plan: RowShiftPlan,
    source_row: int,
    target_row: int,
    groups: Mapping[int, SharedFormulaGroup],
    is_total_row: bool,
) -> tuple[str, int, int, int, int]:
    """位移一行里全部 `<c r>` 与其中的公式。

    Returns:
        `(新 body, 格数, 主格数, 文本区间数, 实测扩张处数)`
    """
    cells_changed = 0
    shared_changed = 0
    text_changed = 0
    extended = 0
    out: list[str] = []
    cursor = 0

    for cell in _CELL_BLOCK_RE.finditer(body):
        out.append(body[cursor : cell.start()])
        cursor = cell.end()
        attrs = cell.group("attrs") or ""
        cell_body = cell.group("body")
        coord = _attr(attrs, "r")
        if coord:
            row = _row_of(coord)
            col = _col_of(coord)
            if row is not None and col is not None and target_row != row:
                attrs = _set_attr(attrs, "r", f"{col}{target_row}")
                cells_changed += 1

        if cell_body:
            cell_body, shared_delta, text_delta, extend_delta = _shift_cell_formula(
                cell_body,
                plan=plan,
                groups=groups,
                is_total_row=is_total_row,
            )
            shared_changed += shared_delta
            text_changed += text_delta
            extended += extend_delta

        out.append(
            f"<c{attrs}/>" if cell_body is None else f"<c{attrs}>{cell_body}</c>"
        )

    out.append(body[cursor:])
    return "".join(out), cells_changed, shared_changed, text_changed, extended


def _shift_cell_formula(
    cell_body: str,
    *,
    plan: RowShiftPlan,
    groups: Mapping[int, SharedFormulaGroup],
    is_total_row: bool,
) -> tuple[str, int, int, int]:
    """位移一格里的 `<f>`：`ref` 与文本区间。

    Returns:
        `(新 body, 主格数, 文本区间数, 实测扩张处数)`
    """
    match = _F_RE.search(cell_body)
    if match is None:
        return cell_body, 0, 0, 0

    fattrs = match.group("fattrs") or ""
    text = match.group("text")
    shared_changed = 0
    text_changed = 0
    extended = 0

    ref = _attr(fattrs, "ref")
    if ref:
        new_ref, _ = _shift_a1_rows_in_text(ref, plan=plan)
        if new_ref != ref:
            fattrs = _set_attr(fattrs, "ref", new_ref)
            shared_changed += 1

    if text:
        # 🔴 扩张只对契约声明的合计行生效，且只动"末行恰等于 insert_at-1"的区间
        #    （Requirement 4.4 / 4.6）。中间插入时区间末行 >= insert_at，普通位移
        #    规则已把它带到正确位置，无需也不得再扩一次。
        plain, changed = _shift_a1_rows_in_text(text, plan=plan)
        if is_total_row:
            new_text, changed = _shift_a1_rows_in_text(
                text, plan=plan, extend_end_at=plan.insert_at - 1
            )
            # 🔴 扩张处数用「扩张版 vs 纯位移版」**实测**比出来，不按声明推：
            #    合计行上完全可能一处区间都不该扩（末行不等于 insert_at-1），
            #    此时报告必须是 0；反之扩张分支被短路时也必须掉到 0。
            if new_text != plain:
                extended += 1
        else:
            new_text = plain
        text_changed += changed
        new_f = f"<f{fattrs}>{new_text}</f>"
    else:
        new_f = f"<f{fattrs}/>"

    return (
        cell_body[: match.start()] + new_f + cell_body[match.end() :],
        shared_changed,
        text_changed,
        extended,
    )


def _build_inserted_row(
    *,
    source: _RowBlock,
    new_row: int,
    managed_columns: Sequence[str],
    groups: Mapping[int, SharedFormulaGroup],
    plan: RowShiftPlan,
) -> str:
    """造一个新行：按列继承 `s=`，公式按 fill-down 翻译，**不带业务值**。

    🔴 不带业务值是刻意的（Requirement 3.5）：值由随后的写格阶段按 projection 落入。
    在这里顺手填值会让「插行」与「写值」两个阶段的职责混在一起，roundtrip 反读时
    分不清某个值是 projection 来的还是这里造的。

    🔴 但**必须**带公式：`formula` 模式字段走 `cached_value_only` 写入，
    `_patch_sheet_xml` 对不存在的公式格抛「不得凭空造一个公式格」。
    """
    allowed = {col.upper() for col in managed_columns} if managed_columns else None
    row_attrs = _set_attr(source.attrs, "r", str(new_row))

    if not source.body:
        return f"<row{row_attrs}/>"

    cells: list[str] = []
    for cell in _CELL_BLOCK_RE.finditer(source.body):
        attrs = cell.group("attrs") or ""
        coord = _attr(attrs, "r")
        col = _col_of(coord or "")
        if col is None:
            continue
        if allowed is not None and col.upper() not in allowed:
            continue

        style = _attr(attrs, "s")
        style_attr = f' s="{style}"' if style else ""
        cell_body = cell.group("body") or ""
        f_match = _F_RE.search(cell_body)
        if f_match is None:
            # 无公式 ⇒ 空格，只留样式（值由写格阶段落）
            cells.append(f'<c r="{col}{new_row}"{style_attr}/>')
            continue

        fattrs = f_match.group("fattrs") or ""
        text = f_match.group("text")
        si = _attr(fattrs, "si")
        is_shared = _attr(fattrs, "t") == "shared"

        if is_shared and si is not None and not _attr(fattrs, "ref"):
            # ═══ 共享公式**成员** ⇒ 新行退化为独立公式，**不加入**那一组 ═══
            #
            # 🔴 首版实现把新行也做成 `<f t="shared" si="N"/>` 成员，注释写着「主格
            #    ref 已在阶段 A/E 扩到覆盖新行」—— 那句话是假的：K11 的 si=1
            #    `ref=H8:H25`、插入点 26，两端都 < 26，位移规则碰不到它；阶段 E 的
            #    `_count_extended_masters` 只计数、不改字节。真实模板实测因此产出
            #    **4 个孤儿成员**（H26/H27 属 si=1 但落在 ref=H8:H25 之外、
            #    I26/I27 属 si=2 同理）。openpyxl 不校验这一点，所以"能打开"完全
            #    掩盖了它。
            #
            #    不改成"扩张主格 ref"的理由：Requirement 4.6 把扩张限定在契约声明
            #    `carries_total_formula` 的 footer 行；si=1 是**逐行**公式不是合计，
            #    无门扩张它等于替审计师改公式（design.md 拒绝方案第 8 条）。
            #
            #    退化为独立公式与本函数下方主格分支的既有理由完全同源，且 Requirement
            #    4.8「主格永不被替换成字面量」照旧成立 —— 主格根本没被碰。
            group = groups.get(int(si)) if si.isdigit() else None
            if group is None:
                raise SharedFormulaSpanError(
                    f"样式来源行 {source.row} 的 {col}{source.row} 声明属共享公式组 "
                    f"si={si}，但索引里没有该组的主格 —— 无从取得公式文本，"
                    "不得把新行做成一个没有主格的成员"
                )
            if not group.is_vertical or group.master_column != col.upper():
                raise SharedFormulaOrientationError(
                    f"样式来源行 {source.row} 的 {col}{source.row} 属共享公式组 "
                    f"si={si}（主格 {group.master_coord}, ref={group.ref}）—— "
                    "主格不在同一列（横向组），新行继承它需要**列**平移，"
                    "而本模块只做行位移；猜一个列偏移会产出每格都算错的表"
                )
            master_row = _row_of(group.master_coord)
            if master_row is None or not group.master_text:
                raise SharedFormulaSpanError(
                    f"共享公式组 si={si} 的主格 {group.master_coord} 没有可用公式文本 —— "
                    "新插入行无从继承公式；`formula` 模式字段走 `cached_value_only` 写入，"
                    "缺公式格会让 `_patch_sheet_xml` 抛「不得凭空造一个公式格」"
                )
            translated = translate_formula_rows(
                group.master_text, from_row=master_row, to_row=new_row
            )
            cells.append(
                f'<c r="{col}{new_row}"{style_attr}><f>{translated}</f></c>'
            )
            continue

        if text:
            translated = translate_formula_rows(
                text, from_row=source.row, to_row=new_row
            )
            # 🔴 主格不复制：新行做成员会需要重算主格 ref 的横向跨度，而主格本身
            #    仍留在原行。这里退化成**独立公式**（去掉 t/si/ref），语义等价且
            #    不牵动整组（Requirement 4.8：主格永不被替换成字面量 —— 这里也没换，
            #    只是新行不加入那一组）。
            cells.append(
                f'<c r="{col}{new_row}"{style_attr}><f>{translated}</f></c>'
            )
            continue

        cells.append(f'<c r="{col}{new_row}"{style_attr}/>')

    return f"<row{row_attrs}>{''.join(cells)}</row>"


def _shift_outside_sheetdata(
    sheet_xml: str, *, plan: RowShiftPlan
) -> tuple[str, dict[str, int]]:
    """位移 `<sheetData>` 之外携带行号的元素（阶段 C/D）。"""
    counts: dict[str, int] = {}

    def _bump(tag: str, delta: int) -> None:
        if delta:
            counts[tag] = counts.get(tag, 0) + delta

    # ── 阶段 C ────────────────────────────────────────────────────
    _handled("mergeCell", "@ref")
    sheet_xml, delta = _shift_attr_everywhere(
        sheet_xml, tag="mergeCell", attr="ref", plan=plan
    )
    _bump("mergeCell@ref", delta)

    _handled("dataValidation", "@sqref")
    sheet_xml, delta = _shift_attr_everywhere(
        sheet_xml, tag="dataValidation", attr="sqref", plan=plan, sqref=True
    )
    _bump("dataValidation@sqref", delta)

    _handled("conditionalFormatting", "@sqref")
    sheet_xml, delta = _shift_attr_everywhere(
        sheet_xml, tag="conditionalFormatting", attr="sqref", plan=plan, sqref=True
    )
    _bump("conditionalFormatting@sqref", delta)

    # ── 阶段 D ────────────────────────────────────────────────────
    _handled("hyperlink", "@ref")
    sheet_xml, delta = _shift_attr_everywhere(
        sheet_xml, tag="hyperlink", attr="ref", plan=plan
    )
    _bump("hyperlink@ref", delta)

    _handled("autoFilter", "@ref")
    sheet_xml, delta = _shift_attr_everywhere(
        sheet_xml, tag="autoFilter", attr="ref", plan=plan
    )
    _bump("autoFilter@ref", delta)

    _handled("brk", "@id")
    sheet_xml, delta = _shift_brk_ids(sheet_xml, plan=plan)
    _bump("brk@id", delta)

    # ── 阶段 C2：元素**文本**里的 A1 引用 ─────────────────────────
    #
    # `<cfRule><formula>` 与 `<dataValidation><formula1|formula2>` 的文本可以是带行号的
    # A1 区间（全库实测 180 处）。它们不是属性，所以 `_shift_attr_everywhere` 碰不到。
    # 🔴 三个 `_handled` 必须写成**字面量**调用：`assert_shift_handlers_cover_structures`
    #    的 AST 判据只收 `_handled(<常量>, <常量>)`，写成 `_handled(tag, ...)` 在循环里
    #    会被整体漏掉 ⇒ 双向锁反而打红。标记是结构声明，循环是实现，两者刻意分开。
    _handled("formula", "text-a1-ranges")
    _handled("formula1", "text-a1-ranges")
    _handled("formula2", "text-a1-ranges")
    _handled("sqref", "text-a1-ranges")
    for tag in ("formula", "formula1", "formula2", "sqref"):
        sheet_xml, delta = _shift_element_text(sheet_xml, tag=tag, plan=plan)
        _bump(f"{tag}@text", delta)

    return sheet_xml, counts


def _shift_element_text(
    sheet_xml: str, *, tag: str, plan: RowShiftPlan
) -> tuple[str, int]:
    """位移某个元素**文本内容**里的 A1 引用（不是属性）。

    走 :func:`_rewrite_formula_refs` 这唯一入口 —— 不另写一套 A1 改写（Property 27 用
    AST 锁死「本模块只有一个 A1 改写入口」）。于是四类误命中防线（跨 sheet 表名 /
    跨 sheet 目标格 / 带数字函数名 / 字符串字面量，含 `&quot;` 实体形态）自动继承。

    🔴 `current_sheet` 不传 ⇒ **所有**带 sheet 前缀的引用逐字不动，包括
    `[1]Data!#REF!` 这类外部工作簿引用（全库实测存在）。这是保守侧。
    """
    changed = 0
    # 🔴 允许带命名空间前缀（如 `<xm:sqref>` / `<x14ac:sqref>`）。Excel 2010+ 的
    # `<dataValidation>` 扩展子元素都挂在 x14 前缀下，裸 `<sqref>` 在生产工作簿里
    # 实测不存在。不加前缀时，正则会把 `<xm:sqref>` 的尾巴匹配成 `<sqref>`、把文本
    # `A10:C12` 当成标签属性吞掉 ⇒ 位移 0 处（2026-09-07 D2-2 实测打红）。
    #
    # 前缀用**非捕获** `(?:\w+:)?` 而不是捕获组 + backreference：实测
    # `(?P<ns>\w+:)?<tag>...</(?P=ns)?tag>` 在 ns 为空时让 `<xm:sqref>` 整体匹配
    # 失败（Rust regex 对「未参与匹配的捕获组 + 可选 backreference」处理不稳定），
    # 反而把带前缀的场景全漏掉。同形前缀本身就是正确 XML，无需 backreference 约束；
    # 错配产生的坏 XML 会被下游 xlsx 解析拦住。
    pattern = re.compile(
        rf"(?P<open><(?:\w+:)?{re.escape(tag)}\b[^>]*>)"
        rf"(?P<text>.*?)"
        rf"(?P<close></(?:\w+:)?{re.escape(tag)}>)",
        re.S,
    )

    def _one(match: re.Match[str]) -> str:
        nonlocal changed
        text = match.group("text")
        if not text:
            return match.group(0)
        new_text, _ = _shift_a1_rows_in_text(text, plan=plan)
        if new_text == text:
            return match.group(0)
        changed += 1
        return f"{match.group('open')}{new_text}{match.group('close')}"

    return pattern.sub(_one, sheet_xml), changed


def _shift_attr_everywhere(
    sheet_xml: str, *, tag: str, attr: str, plan: RowShiftPlan, sqref: bool = False
) -> tuple[str, int]:
    """把某 tag 的某属性里的 A1 行号整体位移。属性一律**按名**定位。

    🔴 不按位置取属性：实测 `sqref` 在 H1 是打头、在 D2 是排在 `type` 之后，
    OOXML 不保证属性顺序。
    """
    changed = 0
    pattern = re.compile(rf"<{re.escape(tag)}\b(?P<attrs>[^>]*?)(/?)>")

    def _one(match: re.Match[str]) -> str:
        nonlocal changed
        attrs = match.group("attrs")
        value = _attr(attrs, attr)
        if value is None:
            return match.group(0)
        new_value = (
            _shift_sqref(value, plan) if sqref else _shift_a1_rows_in_text(value, plan=plan)[0]
        )
        if new_value == value:
            return match.group(0)
        changed += 1
        return f"<{tag}{_set_attr(attrs, attr, new_value)}{match.group(2)}>"

    return pattern.sub(_one, sheet_xml), changed


def _shift_brk_ids(sheet_xml: str, *, plan: RowShiftPlan) -> tuple[str, int]:
    """`<rowBreaks>` 里的 `<brk id="N">` 是**行号**（不是 A1 引用）。"""
    block = re.search(r"<rowBreaks\b[^>]*>(?P<body>.*?)</rowBreaks>", sheet_xml, re.S)
    if block is None:
        return sheet_xml, 0
    changed = 0

    def _one(match: re.Match[str]) -> str:
        nonlocal changed
        attrs = match.group("attrs")
        raw = _attr(attrs, "id")
        if raw is None or not raw.isdigit():
            return match.group(0)
        new_id = plan.shift(int(raw))
        if new_id == int(raw):
            return match.group(0)
        changed += 1
        return f'<brk{_set_attr(attrs, "id", str(new_id))}{match.group(2)}>'

    new_body = re.sub(
        r"<brk\b(?P<attrs>[^>]*?)(/?)>", _one, block.group("body")
    )
    if not changed:
        return sheet_xml, 0
    start, end = block.span("body")
    return sheet_xml[:start] + new_body + sheet_xml[end:], changed


def _update_dimension(
    sheet_xml: str, *, plan: RowShiftPlan, max_row: int
) -> tuple[str, bool]:
    """`dimension@ref` 的末行不得小于实际最大行号（Requirement 3.8）。"""
    match = re.search(r"<dimension\b(?P<attrs>[^>]*?)(/?)>", sheet_xml)
    if match is None:
        return sheet_xml, False
    attrs = match.group("attrs")
    ref = _attr(attrs, "ref")
    if not ref or ":" not in ref:
        return sheet_xml, False
    head, tail = ref.split(":", 1)
    tail_row = _row_of(tail)
    tail_col = _col_of(tail)
    if tail_row is None or tail_col is None:
        return sheet_xml, False
    target = max(plan.shift(tail_row), max_row)
    if target == tail_row:
        return sheet_xml, False
    new_ref = f"{head}:{tail_col}{target}"
    replaced = (
        f"<dimension{_set_attr(attrs, 'ref', new_ref)}{match.group(2)}>"
    )
    return sheet_xml[: match.start()] + replaced + sheet_xml[match.end() :], True
