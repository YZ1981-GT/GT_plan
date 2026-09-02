# -*- coding: utf-8 -*-
"""Excel identity-aware **materializer**（Task 38 的写入侧核心）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 38
Requirements: 3.4, 3.5, 6.3, 6.4, 6.5, 6.6, 6.9, 6.11, 6.15, 6.16, 6.17, 6.18, 8.10, 8.11, 8.12
Properties: **P9** / **P22** / **P23** / **P24** / **P29** / **P65** / **P66** / **P67**

═══ 一、方向只能是 38 → 37 ═══

Task 37（:mod:`app.services.workpaper_sync.excel_extract`）先于本模块落地，并用
:func:`~app.services.workpaper_sync.excel_extract.assert_no_materializer_dependency`
以**真实 import 图**断言它不 import 本模块。本模块反过来大量复用它：

* identity 定位（`resolve_managed_region` / `managed_tables_of` / `RowIdentityScan`）—— 本
  模块**不**自己解析 Excel Table ↔ sheet 关联，也不自己判空/重复/tombstone UUID；
* 受管字段列解析（`_resolve_field_column` 的语义由 Task 37 的 `ExcelIdentityBinding`
  承载，动态列缺实测绑定即 fail closed）；
* 三个共用 verifier 与唯一 commit 前置门 `verify_before_commit`（在
  :mod:`excel_rematerialize` 里调用）。

具体做法：materialize 的**第一件事**就是对 substrate 跑一次 Task 37 的
:func:`extract_projection`。它一次给齐四样本模块必需的东西 —— `region`（受管矩形与
sheet part）、`scan`（Excel 行号 ↔ row identity，含为 OO 新增行 minted 的新 ID）、
`formula_inventory`（受管格的公式文本）、`identity_inventory`。于是「哪一行是哪个身份」
在整条链上只有一份实现，写入侧不可能与读取侧对不上。

═══ 二、写入语义按 `FieldMode` 分四支，四支各自可达且各有专属异常 ═══

=====================  ==========================================  ==========================
mode                   写什么                                       写不了时
=====================  ==========================================  ==========================
``editable``           projection 值取代整格内容（含模板里原有公式）    :class:`EditableCellWriteError`
``auto_source``        服务端值写成字面量；模板里若是公式即契约漂移       :class:`ProtectedRegionWriteError`
``formula``            **只**改缓存 ``<v>``，``<f>`` 逐字保留          :class:`ProtectedRegionWriteError`
``word_only``          xlsx 不适用，跳过                              —
=====================  ==========================================  ==========================

`formula` 这一支的写法是被两侧夹出来的，不是随便选的：

* Task 15 的 `_assert_roundtrip_equivalent` 比对**全部**受管字段（不只 editable），所以
  公式格反读出来的缓存值必须等于 merged projection 的值 ⇒ 必须写 ``<v>``；
* AC 6.6 要求公式结果不得被覆盖、公式本体受保护 ⇒ 不得动 ``<f>``；
* Task 37 的 `_classify_protected_tamper` 在「公式文本未变」时把缓存值差异判为重算结果，
  所以只改 ``<v>`` 不会被误报成篡改。

三者叠起来只剩「保 ``<f>``、改 ``<v>``」一条路。design §Materialize 第 7 条
「formula/auto-source 写服务端值并保护」说的就是这件事。

═══ 三、zip-level 定点修改是默认，openpyxl 要 capability 证明 ═══

design §Materialize 末段：「优先使用 zip-level OOXML 定点修改。只有 template capability
manifest 明确 ``openpyxl_safe`` 且探针覆盖所有关键部件时才允许 openpyxl roundtrip；含
drawing/chart/pivot/macro 的文件默认禁止全量重写。」

:func:`select_write_strategy` 把这句话做成**可执行判据**，而且两边都用实测事实：

* 「这个文件里有没有 drawing/chart/pivot/macro」——
  :func:`measure_part_facts` 直接扫 zip 条目名，不信任任何声明；
* 「探针覆盖了哪些关键部件」—— :func:`probe_uncovered_aspects` 从 Task 5 的载体契约
  ``visible_equivalence.not_covered`` 读，不在本模块抄第二份清单。

实测结论（`backend/wp_templates` 全量 351 个 xlsx 里 182 个含 drawing、1 个含 chart，
探针本身对 pivot/VBA/外链/条件格式四项是 ``not_covered``）：**生产上没有一个模板能通过
这道门**，openpyxl 全量重写在真实模板上恒被拒。这不是把分支写死成不可达 —— 它由
capability + 实测部件双条件构成，两个条件都能被单独 falsify（守卫各测一条）。

═══ 四、不做什么（以及为什么这些拒绝是判据而不是偷懒）═══

1. **不做结构性插行/删行**。Task 37 的 `verify_unmanaged_regions` 把受管 sheet 的
   ``mergeCells``/``cols``/``dataValidations``/``conditionalFormatting``/``sheetProtection``
   逐字节锁死；而 K11 受管 sheet 实测在受管区域**之下**还有一处 merge（``E30:F30``），
   footer 的 ``SUM(B7:B25)`` 还是 ``t="shared" si="3"`` 的共享公式主格。任何行位移都会改动
   这些块 ⇒ 必然被 Task 37 判成未管理区域漂移。所以本模块对「merged projection 里有
   substrate 中不存在的行身份」**fail closed**（:class:`RowSetDivergenceError`），把结构
   编辑的支持登记为后续任务的前置，而不是悄悄写坏文件再指望 verifier 兜住。
   注意 OO 侧插行**不**走这条路：OO 已经把物理行建好了，Task 37 会给它 mint 一个新
   identity，本模块只负责把那个 UUID 字面量落到隐藏列里。
2. **不改共享公式主格**。``<f t="shared" ref="H8:H25" si="1">`` 的主格一旦被换成字面量，
   H9..H25 全组失效。契约把这种格声明成 editable 时直接拒
   （:class:`SharedFormulaMasterWriteError`），因为「写坏 18 行公式」不该由反读门事后
   发现。
3. **不 commit、不切 pointer、不递增 revision**。本模块只产出 staged 文件与
   :class:`~app.services.workpaper_sync.adapters.base.MaterializeResult`；发布由
   `ContentMutationService` / `RepresentationService` 唯一控制。
4. **不写模板库**。:func:`materialize_projection` 只吃 substrate 路径与输出路径，并在
   写盘前用 :func:`assert_output_outside_template_library` 实测输出不落在
   ``backend/wp_templates/`` 之下（Requirement 9.9）。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass, field as dataclass_field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from openpyxl.utils import column_index_from_string

from app.services.workpaper_sync.adapters.base import (
    FieldValue,
    MaterializeResult,
    Projection,
    SubstrateRole,
    assert_substrate_usable,
)
from app.services.workpaper_sync.contracts import (
    FieldMode,
    FieldSpec,
    SyncContract,
    TableSpec,
    ValueType,
)
from app.services.workpaper_sync.excel_entry_gate import FrozenEntryDefinitions
from app.services.workpaper_sync.excel_instrumentation import normalized_structure_hash
from app.services.workpaper_sync.excel_extract import (
    ExcelIdentityBinding,
    ExcelExtractOutcome,
    ManagedRegion,
    RowIdentityScan,
    RuntimeIdentityInventory,
    assert_engine_entry_definitions,
    extract_projection,
    managed_tables_of,
    read_runtime_binding_pairs,
    read_runtime_identity_inventory,
    resolve_managed_region,
)
from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.merge import ValueNormalizationError, normalize_value
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState, SyncDomainError

__all__ = [
    # 异常
    "ExcelMaterializeError",
    "EditableCellWriteError",
    "ProtectedRegionWriteError",
    "SharedFormulaMasterWriteError",
    "RowIdentityWriteError",
    "DynamicColumnWriteError",
    "FooterAnchorDriftError",
    "FooterFormulaRangeError",
    "RowSetDivergenceError",
    "WriteStrategyForbiddenError",
    "TemplateLibraryWriteError",
    "FAILURE_KINDS",
    # capability 与写入策略
    "ExcelWriteStrategy",
    "WorkbookPartFacts",
    "ExcelWriteCapability",
    "PROTECTED_PART_ASPECTS",
    "CAPABILITY_REQUIRED_PROBE_ASPECTS",
    "measure_part_facts",
    "probe_uncovered_aspects",
    "select_write_strategy",
    "WriteStrategyDecision",
    # 计划
    "CellWriteKind",
    "CellWrite",
    "MaterializePlan",
    "plan_managed_writes",
    "assert_dynamic_column_binding_usable",
    "assert_footer_anchor_stable",
    "assert_footer_formula_covers_managed_rows",
    # 写盘
    "apply_plan_zip",
    "apply_plan_openpyxl",
    "assert_output_outside_template_library",
    "TEMPLATE_LIBRARY_MARKER",
    # 入口
    "ExcelMaterializeOutcome",
    "materialize_projection",
]


# ═══════════════════════════════════════════════════════════════════════════
# 0. 常量
# ═══════════════════════════════════════════════════════════════════════════

#: 运行时**不得**写入的目录标记（Requirement 9.9：模板库只读）。
TEMPLATE_LIBRARY_MARKER: Final[str] = "wp_templates"

#: Task 5 载体契约 `visible_equivalence.not_covered` 的取值文件（单一真源）。
_CARRIER_CONTRACT: Final[Path] = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "onlyoffice_excel_identity_carrier_contract.json"
)

#: 「含这些部件即禁止全量重写」——design §Materialize 末段列的四类。
PROTECTED_PART_ASPECTS: Final[tuple[str, ...]] = ("drawing", "chart", "pivot", "macro")

#: openpyxl 全量重写要求探针**已覆盖**的关键部件。任一条在 Task 5 契约里是
#: `not_covered` 就不许开门 —— 「未取证」与「已证明安全」不是一回事。
CAPABILITY_REQUIRED_PROBE_ASPECTS: Final[tuple[str, ...]] = (
    "pivot_table",
    "vba_macro",
    "external_link_workbooks",
    "conditional_formatting_and_data_validation",
)

#: zip 条目名 → part aspect 的判据（实测部件名，不看任何声明）。
_PART_ASPECT_PATTERNS: Final[Mapping[str, re.Pattern[str]]] = {
    "drawing": re.compile(r"^xl/(drawings/|media/)"),
    "chart": re.compile(r"^xl/charts/"),
    "pivot": re.compile(r"^xl/pivot(Tables|Cache)/"),
    "macro": re.compile(r"^xl/vbaProject\.bin$"),
    "external_link": re.compile(r"^xl/externalLinks/"),
    "table": re.compile(r"^xl/tables/"),
}

#: 单个 `<c r="COORD" .../>` / `<c r="COORD" ...>…</c>`。
#:
#: 🔴 自闭合分支必须在前、属性段必须**惰性**（`[^>]*?`）。Task 37 的 fixture 已经实测过
#: 贪心写法的后果：`[^>]*` 会吃掉 `s="56"/`，随后 `>.*?</c>` 从下一格开始一路吞到**下一个**
#: `</c>`，把紧邻的隐藏 UUID 格整个吃掉。
_CELL_RE_TPL: Final[str] = (
    '(?:<c r="{coord}"(?P<selfattrs>(?:\\s[^>]*?)?)/>)'
    '|(?:<c r="{coord}"(?P<attrs>(?:\\s[^>]*?)?)>(?P<body>.*?)</c>)'
)
#: 「这个渲染结果是数值字面量吗」——决定公式格要不要带 `t="str"`。
_NUMERIC_LITERAL_RE: Final[re.Pattern[str]] = re.compile(
    r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
)
_ANY_CELL_RE: Final[re.Pattern[str]] = re.compile(
    r'<c r="([A-Z]+)(\d+)"(?:\s[^>]*?)?/>|<c r="([A-Z]+)(\d+)"(?:\s[^>]*?)?>.*?</c>',
    re.S,
)
_ROW_RE_TPL: Final[str] = r'(<row r="{row}"(?:\s[^>]*?)?>)(?P<body>.*?)(</row>)'
_ROW_SELF_CLOSING_TPL: Final[str] = r'<row r="{row}"(?:\s[^>]*?)?/>'
_FORMULA_RE: Final[re.Pattern[str]] = re.compile(r"<f(?P<fattrs>(?:\s[^>]*?)?)(?:/>|>(?P<text>.*?)</f>)", re.S)
_VALUE_RE: Final[re.Pattern[str]] = re.compile(r"<v>.*?</v>|<v/>", re.S)
_INLINE_RE: Final[re.Pattern[str]] = re.compile(r"<is>.*?</is>", re.S)
#: 公式里的 A1 区间（`SUM(B7:B25)` 的 `B7:B25`）。绝对引用的 `$` 一并吃掉。
_RANGE_IN_FORMULA_RE: Final[re.Pattern[str]] = re.compile(
    r"\$?(?P<c1>[A-Z]{1,3})\$?(?P<r1>\d+):\$?(?P<c2>[A-Z]{1,3})\$?(?P<r2>\d+)"
)
_XML_ESCAPES: Final[tuple[tuple[str, str], ...]] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
)


def _xml_escape(text: str) -> str:
    out = text
    for raw, encoded in _XML_ESCAPES:
        out = out.replace(raw, encoded)
    return out


#: 🔴 Task 42 新增：XML **数字字符引用**（`&#21512;` / `&#x5408;`）。
#:
#: 存在的理由是一条实测缺陷：`backend/wp_templates/` 下 369 个工作簿里有 **10 个**（含
#: Task 40 的 `B60-1 审计项目工时预算与控制表.xlsx`、Task 43 的 `G7 长期股权投资.xlsx`
#: 与 Task 42 的 `H1 固定资产.xlsx`）**没有** `sharedStrings.xml`，把非 ASCII 内联文本
#: 一律写成数字字符引用 —— 例如 footer 那格是
#: `<c r="A28" t="inlineStr"><is><t>&#21512;&#35745;</t></is></c>`。
#: :func:`_xml_unescape` 原本只还原五个具名实体，对这类文本原样返回 `'&#21512;&#35745;'`，
#: 于是 :func:`_find_marker_row` 在列 A 上找不到 marker `合计`，
#: :func:`assert_footer_anchor_stable` 抛 `FooterAnchorDriftError` ⇒ 这 10 个工作簿的
#: materialize 全线不可用（footer 合计公式区间覆盖判据也就无从执行）。
_NUMERIC_CHAR_REF: Final[re.Pattern[str]] = re.compile(r"&#(x[0-9a-fA-F]+|\d+);")


def _decode_numeric_char_refs(text: str) -> str:
    """还原 XML 数字字符引用（Task 42 新增；见 :data:`_NUMERIC_CHAR_REF` 的实测理由）。

    刻意**不**用 `html.unescape`：它还会把 `&nbsp;` 之类 HTML 专有实体一起换掉，而那些在
    XML 里是未定义实体，静默替换会让「文档非法」这一事实消失。
    """

    def _one(match: re.Match[str]) -> str:
        token = match.group(1)
        try:
            code = int(token[1:], 16) if token[0] in "xX" else int(token)
        except ValueError:  # pragma: no cover - 正则已限定形态
            return match.group(0)
        # 超出 Unicode 范围/非法码位一律原样保留：静默丢字符比留下引用更难查。
        return chr(code) if 0 < code <= 0x10FFFF else match.group(0)

    return _NUMERIC_CHAR_REF.sub(_one, text)


def _xml_unescape(text: str) -> str:
    # 🔴 Task 42 追加的一行：数字字符引用必须先还原（`&amp;#39;` 不会被误判 —— 它的 `#`
    #    前面是 `;` 而不是 `&`，正则匹配不上，随后具名实体那一趟才把它还原成字面
    #    `&#39;`）。
    out = _decode_numeric_char_refs(text)
    for raw, encoded in reversed(_XML_ESCAPES):
        out = out.replace(encoded, raw)
    return out.replace("&apos;", "'")


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常 —— 一条禁令一个类型一个 error_code
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本 spec 已三次实测「多条判据共用一个 error code ⇒ 靠前的分支永久不可达 ⇒ 只断言
#    类型的守卫判 GREEN」。Task 37 因此把三条 verifier 失败拆成三个类型；写入侧同样
#    不许合并：「写 editable 失败 / 动态 UUID 写入失败 / footer 位移 / 公式区被覆盖」
#    在生产诊断里是四件完全不同的事。


class ExcelMaterializeError(SyncDomainError):
    """Task 38 写入侧域基类。"""

    error_code = "excel_materialize_failed"


class EditableCellWriteError(ExcelMaterializeError):
    """editable 受管格写不进去（行/格在 sheet XML 里定位不到、值无法规范化）。"""

    error_code = "excel_materialize_editable_write_failed"


class ProtectedRegionWriteError(ExcelMaterializeError):
    """受保护区域（formula / auto-source）与契约声明不符，或将被非法覆盖（AC 6.6）。"""

    error_code = "excel_materialize_protected_region_violation"


class SharedFormulaMasterWriteError(ExcelMaterializeError):
    """契约要求写入的格是共享公式**主格**，写它会让整组成员失效。

    与 :class:`ProtectedRegionWriteError` 严格分开：后者是「契约说受保护却被改」，
    本类是「契约说 editable，但 OOXML 上这一格是别人的公式源」—— 两种成因、两种修法
    （改契约 vs 改模板）。合并成一个类型后其中一条永远不可分辨。
    """

    error_code = "excel_materialize_shared_formula_master_write"


class RowIdentityWriteError(ExcelMaterializeError):
    """动态行 identity（含 Task 37 minted 的新 ID）写不进隐藏 UUID 列。"""

    error_code = "excel_materialize_row_identity_write_failed"


class DynamicColumnWriteError(ExcelMaterializeError):
    """动态列 `{slot}_{seq}` 绑定不可用（键不符契约 identity 模板、或两个 slot 撞同一列）。"""

    error_code = "excel_materialize_dynamic_column_binding_unusable"


class FooterAnchorDriftError(ExcelMaterializeError):
    """footer 标记行与 representation 冻结的 `GT_FOOTER_ROW` 不符（footer 下移）。"""

    error_code = "excel_materialize_footer_anchor_drift"


class FooterFormulaRangeError(ExcelMaterializeError):
    """footer 合计公式的区间没覆盖当前受管行区间（插行后合计漏算）。"""

    error_code = "excel_materialize_footer_formula_range_stale"


class RowSetDivergenceError(ExcelMaterializeError):
    """merged projection 的行集与 substrate 的物理行集不一致，需结构性插删行。"""

    error_code = "excel_materialize_row_set_divergence"


class WriteStrategyForbiddenError(ExcelMaterializeError):
    """要求 openpyxl 全量重写，但 capability / 探针覆盖两条件未同时满足。"""

    error_code = "excel_materialize_write_strategy_forbidden"


class TemplateLibraryWriteError(ExcelMaterializeError):
    """输出路径落在 `backend/wp_templates/` 之下（Requirement 9.9：模板库运行时只读）。"""

    error_code = "excel_materialize_template_library_write"


#: 写入侧失败形态的**登记清单**：`error_code` → 触发条件（一句话，用于运维诊断）。
#:
#: 🔴 它存在的唯一理由是让「共享错误码让较早分支永久不可达」这个假绿形态可被 falsify。
#: 守卫的做法（Task 58 `test_failure_kinds_are_reachable_and_mutually_distinct` 范式）：
#: 把每一种 kind 在真实模板上**各真触发一次**，收集实际抛出的 `error_code` 集合，然后
#: 与本清单**双向等值** + 断言基数 == 登记条数。
#:
#: 这比「每类各测一遍」强：后者在两类被合并成同一个 code 时**全部仍绿**（两条用例都只
#: 断言「抛了 ExcelMaterializeError」或「抛了某个类型」，而合并后靠前的分支永不可达）。
#:
#: 本清单**手写**而不是从类反推 —— 从类反推就成了自证式同义反复（改类也自动改期望）。
FAILURE_KINDS: Final[Mapping[str, str]] = {
    "excel_materialize_editable_write_failed": (
        "editable 受管格定位不到或 projection 值无法按契约 value_type 规范化"
    ),
    "excel_materialize_protected_region_violation": (
        "契约与模板对受保护格（formula / auto_source）的声明不符，继续写会覆盖公式"
    ),
    "excel_materialize_shared_formula_master_write": (
        "契约声明 editable 的格在 OOXML 上是共享公式主格，覆盖它会让整组成员失效"
    ),
    "excel_materialize_row_identity_write_failed": (
        "Task 37 minted 的新行身份不在 merged projection 行集里，写入侧不得自行决定去留"
    ),
    "excel_materialize_dynamic_column_binding_unusable": (
        "动态列缺实测绑定、键不符 `{slot}_{seq}` identity 模板，或两个 slot 撞同一列"
    ),
    "excel_materialize_footer_anchor_drift": (
        "footer marker 实测行号与 representation 冻结的 GT_FOOTER_ROW 不一致（footer 下移）"
    ),
    "excel_materialize_footer_formula_range_stale": (
        "footer 合计公式的区间没覆盖当前受管行区间（插行后合计漏算）"
    ),
    "excel_materialize_row_set_divergence": (
        "merged projection 的行身份在 substrate 上没有物理行，需要结构性插行"
    ),
    "excel_materialize_write_strategy_forbidden": (
        "openpyxl 全量重写未获 capability + 探针覆盖双条件放行却被调用"
    ),
    "excel_materialize_template_library_write": (
        "输出路径落在 `backend/wp_templates/` 之下（模板库运行时只读）"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# 2. capability 与写入策略门
# ═══════════════════════════════════════════════════════════════════════════


class ExcelWriteStrategy(str, Enum):
    """写入方式。默认恒为 :attr:`zip_patch`。"""

    #: zip 级定点改字节：只碰受管格所在的 sheet part 与隐藏 UUID 列。
    zip_patch = "zip_patch"
    #: openpyxl 全量 roundtrip：只有 capability 清单证明安全的模板才开放。
    openpyxl_roundtrip = "openpyxl_roundtrip"


@dataclass(frozen=True)
class WorkbookPartFacts:
    """一份 artifact 的**实测**部件事实。判据来源是 zip 条目名，不是任何声明。"""

    entry_count: int
    aspect_counts: Mapping[str, int]

    @property
    def protected_aspects_present(self) -> tuple[str, ...]:
        return tuple(
            aspect
            for aspect in PROTECTED_PART_ASPECTS
            if self.aspect_counts.get(aspect, 0) > 0
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_count": self.entry_count,
            "aspect_counts": dict(sorted(self.aspect_counts.items())),
            "protected_aspects_present": list(self.protected_aspects_present),
        }


def measure_part_facts(artifact: Path) -> WorkbookPartFacts:
    """扫 zip 条目名得出「这个文件里到底有什么部件」。

    刻意**不**接受调用方传入的声明：capability manifest 说「没有 drawing」而文件里有
    一个 `xl/drawings/vmlDrawing1.vml` 时，必须以文件为准。
    """
    counts: dict[str, int] = {aspect: 0 for aspect in _PART_ASPECT_PATTERNS}
    with zipfile.ZipFile(artifact) as zf:
        names = [name for name in zf.namelist() if not name.endswith("/")]
    for name in names:
        for aspect, pattern in _PART_ASPECT_PATTERNS.items():
            if pattern.match(name):
                counts[aspect] += 1
    return WorkbookPartFacts(entry_count=len(names), aspect_counts=counts)


@dataclass(frozen=True)
class ExcelWriteCapability:
    """一个模板的写入 capability 声明。

    刻意做成**必须由调用方显式给出的值对象**而不是一份可选数据文件：数据文件缺省时
    「openpyxl 分支在生产上不可达」会退化成「分支恒不可达」（假绿第④源）。做成值对象后
    两个条件（声明 + 实测部件）各自都能被守卫单独 falsify。
    """

    template_relative_path: str
    openpyxl_safe: bool = False
    #: 该模板的探针已覆盖的关键部件（取值必须来自真实 probe 证据）。
    probe_covered_aspects: frozenset[str] = dataclass_field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not str(self.template_relative_path or "").strip():
            raise WriteStrategyForbiddenError(
                "ExcelWriteCapability.template_relative_path 不得为空 —— capability 必须"
                "绑定到具体模板，不得声明成「所有模板都安全」"
            )


def probe_uncovered_aspects(path: Path | None = None) -> frozenset[str]:
    """Task 5 载体契约里 `probe_verdict != passed` 的 `visible_equivalence.not_covered` 项。

    这是「探针覆盖了什么」的**唯一真源**（`backend/data/
    onlyoffice_excel_identity_carrier_contract.json`）。本模块不抄第二份清单 —— 抄一份
    就会出现「契约里改成 not_covered、代码里还是老样子」的第二真源。
    """
    target = path or _CARRIER_CONTRACT
    payload = json.loads(target.read_text(encoding="utf-8"))
    not_covered = payload.get("visible_equivalence", {}).get("not_covered", [])
    return frozenset(
        str(item.get("aspect"))
        for item in not_covered
        if str(item.get("probe_verdict")) != "passed" and item.get("aspect")
    )


@dataclass(frozen=True)
class WriteStrategyDecision:
    """策略裁决 + 逐条理由。理由进 operation error detail 与 evidence。"""

    strategy: ExcelWriteStrategy
    facts: WorkbookPartFacts
    refusals: tuple[str, ...]

    @property
    def openpyxl_allowed(self) -> bool:
        return self.strategy is ExcelWriteStrategy.openpyxl_roundtrip

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "openpyxl_allowed": self.openpyxl_allowed,
            "refusals": list(self.refusals),
            "facts": self.facts.as_dict(),
        }


def select_write_strategy(
    *,
    artifact: Path,
    capability: ExcelWriteCapability | None = None,
    uncovered_probe_aspects: frozenset[str] | None = None,
) -> WriteStrategyDecision:
    """zip-level 定点修改是默认；openpyxl 全量重写要同时满足三条。

    三条判据各自独立、各自可被 falsify：

    1. capability 清单必须**显式**声明 `openpyxl_safe`（缺 capability 即拒）；
    2. 文件里实测**没有** drawing / chart / pivot / macro（design 明列的四类）；
    3. Task 5 探针对 :data:`CAPABILITY_REQUIRED_PROBE_ASPECTS` 的每一项都不是
       `not_covered`，且 capability 自己声明覆盖了它们。

    任一条不满足即回落 zip patch，并把原因逐条记下来 —— 「静默回落」会让「以为开了
    openpyxl 其实没开」这类问题查不出来。
    """
    facts = measure_part_facts(artifact)
    uncovered = (
        uncovered_probe_aspects
        if uncovered_probe_aspects is not None
        else probe_uncovered_aspects()
    )
    refusals: list[str] = []
    if capability is None or not capability.openpyxl_safe:
        refusals.append(
            "capability 未声明 openpyxl_safe —— 全量重写默认禁止"
            "（design §Materialize：含 drawing/chart/pivot/macro 的文件默认禁止全量重写）"
        )
    present = facts.protected_aspects_present
    if present:
        refusals.append(
            f"实测含受保护部件 {list(present)}（部件计数 "
            f"{ {k: v for k, v in sorted(facts.aspect_counts.items()) if v} }）—— "
            "openpyxl 全量重写会丢失/重写它们"
        )
    blocked = sorted(set(CAPABILITY_REQUIRED_PROBE_ASPECTS) & set(uncovered))
    if blocked:
        refusals.append(
            f"Task 5 探针对 {blocked} 仍是 not_covered —— 「未取证」不等于「已证明安全」"
        )
    if capability is not None:
        missing = sorted(
            aspect
            for aspect in CAPABILITY_REQUIRED_PROBE_ASPECTS
            if aspect not in capability.probe_covered_aspects
        )
        if missing:
            refusals.append(f"capability 未声明已覆盖关键部件 {missing}")
    strategy = (
        ExcelWriteStrategy.zip_patch if refusals else ExcelWriteStrategy.openpyxl_roundtrip
    )
    return WriteStrategyDecision(
        strategy=strategy, facts=facts, refusals=tuple(refusals)
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 写入计划
# ═══════════════════════════════════════════════════════════════════════════


class CellWriteKind(str, Enum):
    """一处写入的形态。四类各自对应一条 OOXML 写法，互不重叠。"""

    #: 整格取代成数值字面量（`<v>`，无 `t`）。
    number_literal = "number_literal"
    #: 整格取代成内联字符串（`t="inlineStr"` + `<is><t>`；刻意不动 sharedStrings）。
    inline_text = "inline_text"
    #: **只**改缓存值，`<f>` 逐字保留（受保护公式格）。
    cached_value_only = "cached_value_only"
    #: 隐藏 UUID 列的 row identity 字面量。
    row_identity = "row_identity"


@dataclass(frozen=True)
class CellWrite:
    """一处受管写入。`stable_field_key` 空串表示这是 identity 列写入。"""

    coord: str
    kind: CellWriteKind
    value: Any
    stable_field_key: str = ""
    row_key: str = ""
    mode: FieldMode | None = None
    #: 仅 :attr:`CellWriteKind.cached_value_only` 用：`<f>` 的 **应有**文本。
    #:
    #: 🔴 非空表示「substrate 上这一格的公式文本与 intended 不符，必须还原」。OO→HTML 方向的
    #: substrate 是 incoming，公式文本可能已被 OO 改写（`=G7-D7` → `=G7-D7+1`，缓存值不变）。
    #: 只改 `<v>` 会把被改写的 `<f>` 逐字带进 staged result，而 `verify_formula_regions` 用
    #: 同一份 incoming 当 baseline 时是「篡改比篡改」⇒ 恒通过。AC 6.6 要求 current 公式与值
    #: 都不变，所以受保护格的 `<f>` 必须由 **base representation** 的 intended 文本决定。
    formula_text: str = ""

    @property
    def is_identity(self) -> bool:
        return self.kind is CellWriteKind.row_identity


@dataclass(frozen=True)
class MaterializePlan:
    """一次 materialize 要落的全部写入 + 必须保持不变的公式清册。"""

    sheet_part: str
    sheet_name: str
    writes: tuple[CellWrite, ...]
    #: stable key → 必须逐字保留的公式文本（受保护 formula 格）。
    preserved_formulas: Mapping[str, str]
    #: `table_key` → (`{slot}_{seq}` → Excel 列)。只作审计记录，解析由 Task 37 承担。
    dynamic_column_columns: Mapping[str, Mapping[str, str]]
    footer_marker_row: int | None = None

    @property
    def field_writes(self) -> tuple[CellWrite, ...]:
        return tuple(w for w in self.writes if not w.is_identity)

    @property
    def identity_writes(self) -> tuple[CellWrite, ...]:
        return tuple(w for w in self.writes if w.is_identity)

    @property
    def coords(self) -> tuple[str, ...]:
        return tuple(w.coord for w in self.writes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sheet_part": self.sheet_part,
            "sheet_name": self.sheet_name,
            "write_count": len(self.writes),
            "field_write_count": len(self.field_writes),
            "identity_write_count": len(self.identity_writes),
            "kind_counts": {
                kind.value: sum(1 for w in self.writes if w.kind is kind)
                for kind in CellWriteKind
            },
            "preserved_formula_count": len(self.preserved_formulas),
            "footer_marker_row": self.footer_marker_row,
            "dynamic_column_columns": {
                table: dict(sorted(mapping.items()))
                for table, mapping in sorted(self.dynamic_column_columns.items())
            },
        }


# ─────────────────────────────────────────────────────────────────────────
# 3.1 zip 级 sheet XML 读取（写入侧自己的 XML 访问层）
# ─────────────────────────────────────────────────────────────────────────


def _read_entries(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _write_entries(entries: Mapping[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name, payload in entries.items():
            out.writestr(name, payload)
    return buf.getvalue()


@dataclass(frozen=True)
class _CellView:
    """一格的原样切片：整段 XML、属性串、body、公式文本与共享公式 ref。"""

    coord: str
    raw: str
    attrs: str
    body: str
    formula_text: str | None
    shared_ref: str | None
    #: `<f ...>` 的属性串（含前导空格）。还原公式文本时逐字保留它。
    formula_attrs: str = ""

    @property
    def style(self) -> str:
        found = re.search(r'\bs="(\d+)"', self.attrs)
        return found.group(1) if found else ""

    @property
    def has_formula(self) -> bool:
        return "<f" in self.body


def _cell_view(xml: str, coord: str) -> _CellView | None:
    pattern = re.compile(_CELL_RE_TPL.format(coord=re.escape(coord)), re.S)
    found = pattern.search(xml)
    if found is None:
        return None
    attrs = found.group("selfattrs") or found.group("attrs") or ""
    body = found.group("body") or ""
    formula = _FORMULA_RE.search(body)
    text: str | None = None
    shared_ref: str | None = None
    formula_attrs = ""
    if formula is not None:
        raw_text = formula.group("text")
        text = _xml_unescape(raw_text) if raw_text else ""
        formula_attrs = formula.group("fattrs") or ""
        ref = re.search(r'\bref="([^"]+)"', formula_attrs)
        shared_ref = ref.group(1) if ref else None
    return _CellView(
        coord=coord,
        raw=found.group(0),
        attrs=attrs,
        body=body,
        formula_text=text,
        shared_ref=shared_ref,
        formula_attrs=formula_attrs,
    )


def _cell_xml(*, coord: str, style: str, write: CellWrite) -> str:
    """按写入形态渲染一格。**恒带回原样式 `s=`**（AC 3.5：样式必须保留）。"""
    style_attr = f' s="{style}"' if style else ""
    if write.kind is CellWriteKind.inline_text:
        text = _xml_escape("" if write.value is None else str(write.value))
        return (
            f'<c r="{coord}"{style_attr} t="inlineStr">'
            f'<is><t xml:space="preserve">{text}</t></is></c>'
        )
    if write.kind is CellWriteKind.row_identity:
        text = _xml_escape(str(write.value))
        return (
            f'<c r="{coord}"{style_attr} t="inlineStr">'
            f"<is><t>{text}</t></is></c>"
        )
    return f'<c r="{coord}"{style_attr}><v>{_render_number(write.value)}</v></c>'


def _render_number(value: Any) -> str:
    if value is None:
        return "0"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return repr(value) if value != int(value) else str(int(value))
    return str(value)


def _replace_cached_value(view: _CellView, value: Any, formula_text: str = "") -> str:
    """把 `<v>` 换成服务端值；`<f>` 的**属性**（含 `t="shared" si=`）逐字保留。

    `formula_text` 非空时额外把 `<f>` 的**文本**还原成它 —— 见
    :attr:`CellWrite.formula_text` 的注释：OO 改写过的公式文本不得进 staged result。
    属性保留是刻意的：共享公式的 `ref`/`si` 决定整组成员的翻译关系，换掉它们会让 H9..H25
    全组失效，而那是「写坏 18 行公式」而不是「还原一格」。
    """
    rendered = f"<v>{_render_number(value)}</v>"
    body = view.body
    if formula_text:
        replacement = f"<f{view.formula_attrs}>{_xml_escape(formula_text)}</f>"
        patched, count = _FORMULA_RE.subn(replacement, body, count=1)
        if count != 1:
            raise ProtectedRegionWriteError(
                f"受保护格 {view.coord} 的 `<f>` 还原失败（未命中）—— 不得把被改写的公式"
                "带进 staged result（AC 6.6）"
            )
        body = patched
    if _VALUE_RE.search(body):
        body = _VALUE_RE.sub(rendered, body, count=1)
    else:
        # OO 有时把公式格写成只有 `<f>` 而没有缓存 `<v>`（尚未重算）。此时必须**补**一个，
        # 否则 Task 15 的全字段等值门反读不到值，整次发布被挡掉。
        body = body + rendered
    # 结果是数值 ⇒ 去掉 `t="str"` 之类的过期文本标记，否则 Excel 把数字当字符串。
    attrs = re.sub(r'\s+t="[^"]*"', "", view.attrs)
    if not _NUMERIC_LITERAL_RE.fullmatch(_render_number(value)):
        # 反过来：结果是文本时必须**带上** `t="str"`。模板里确实存在文本型公式格
        # （K11 实测 A7 是 `s="47" t="str"` + `<f>'明细表K11-2'!B11</f>`），无条件剥掉
        # 类型标记会让 Excel 把中文项目名当数字解析 ⇒ 打开即报错。
        attrs = f'{attrs} t="str"'
    return f'<c r="{view.coord}"{attrs}>{body}</c>'


def _patch_sheet_xml(xml: str, writes: Sequence[CellWrite]) -> str:
    """在 sheet XML 上定点写受管格。缺格按列序插入、缺行按行序插入。"""
    for write in writes:
        column = re.match(r"[A-Z]+", write.coord)
        row_match = re.search(r"\d+$", write.coord)
        if column is None or row_match is None:
            raise EditableCellWriteError(f"非法坐标 {write.coord!r}")
        row = int(row_match.group(0))
        view = _cell_view(xml, write.coord)
        if view is not None:
            if write.kind is CellWriteKind.cached_value_only:
                new = _replace_cached_value(view, write.value, write.formula_text)
            else:
                new = _cell_xml(coord=write.coord, style=view.style, write=write)
            xml = xml.replace(view.raw, new, 1)
            continue
        if write.kind is CellWriteKind.cached_value_only:
            raise ProtectedRegionWriteError(
                f"受保护公式格 {write.coord} 在 substrate 里不存在 —— 不得凭空造一个公式格"
                f"（stable key {write.stable_field_key!r}）"
            )
        new = _cell_xml(coord=write.coord, style="", write=write)
        xml = _insert_cell(xml, row=row, column=column.group(0), cell_xml=new)
    return xml


def _insert_cell(xml: str, *, row: int, column: str, cell_xml: str) -> str:
    self_closing = re.search(_ROW_SELF_CLOSING_TPL.format(row=row), xml)
    if self_closing is not None:
        raw = self_closing.group(0)
        return xml.replace(raw, raw[:-2] + ">" + cell_xml + "</row>", 1)
    row_pat = re.compile(_ROW_RE_TPL.format(row=row), re.S)
    found = row_pat.search(xml)
    if found is None:
        return _insert_row(xml, row=row, cell_xml=cell_xml)
    body = found.group("body")
    target = column_index_from_string(column)
    out: list[str] = []
    inserted = False
    for match in _ANY_CELL_RE.finditer(body):
        letters = match.group(1) or match.group(3)
        if not inserted and column_index_from_string(letters) > target:
            out.append(cell_xml)
            inserted = True
        out.append(match.group(0))
    if not inserted:
        out.append(cell_xml)
    start, end = found.span("body")
    return xml[:start] + "".join(out) + xml[end:]


def _insert_row(xml: str, *, row: int, cell_xml: str) -> str:
    """按行序插入一整行。**不位移**任何既有行（结构性插行见模块 docstring 第四节）。"""
    new_row = f'<row r="{row}">{cell_xml}</row>'
    rows = [(int(m.group(1)), m.start()) for m in re.finditer(r'<row r="(\d+)"', xml)]
    for number, offset in rows:
        if number > row:
            return xml[:offset] + new_row + xml[offset:]
    if "</sheetData>" not in xml:
        raise EditableCellWriteError(
            f"sheet XML 缺 </sheetData>，无法插入第 {row} 行"
        )
    return xml.replace("</sheetData>", f"{new_row}</sheetData>", 1)


# ─────────────────────────────────────────────────────────────────────────
# 3.2 动态列 / footer 的写入前置判据
# ─────────────────────────────────────────────────────────────────────────


def assert_dynamic_column_binding_usable(
    *, contract: SyncContract, binding: ExcelIdentityBinding
) -> Mapping[str, Mapping[str, str]]:
    """动态列绑定的两条写入前置判据（Property 22）。

    1. **键必须符合契约声明的 identity 模板**（默认 `{slot}_{seq}`）。可改的公司 label
       绝不能当键 —— 那是 Requirement 6.4 明令禁止的；
    2. **同一张表的两个 slot 不得映射到同一列**。重复 label 是合法输入（两家单位可能
       同名），但两个 slot 落进一列会让后写的静默覆盖先写的，审计上表现为「一家单位的
       数据凭空消失」。

    返回实际生效的绑定，供 :class:`MaterializePlan` 记录。
    """
    out: dict[str, Mapping[str, str]] = {}
    for sheet in contract.sheets:
        for table in sheet.tables:
            if table.dynamic_columns is None:
                continue
            bound = dict(binding.dynamic_column_columns.get(table.table_key, {}))
            if not bound:
                raise DynamicColumnWriteError(
                    f"契约表 {table.table_key!r} 声明了 dynamic_columns "
                    f"(identity={table.dynamic_columns.identity!r})，但 identity binding "
                    "没给 `{slot}_{seq}` → Excel 列的实测绑定 —— 写入侧不得按声明列右移猜"
                )
            pattern = _identity_pattern(table.dynamic_columns.identity)
            bad_keys = sorted(key for key in bound if not pattern.fullmatch(key))
            if bad_keys:
                raise DynamicColumnWriteError(
                    f"契约表 {table.table_key!r} 的动态列键 {bad_keys} 不符契约声明的 identity "
                    f"模板 {table.dynamic_columns.identity!r} —— 可改的公司/单位 label 不得作"
                    "列 identity（Requirement 6.4 / Property 22）"
                )
            by_column: dict[str, list[str]] = {}
            for key, column in sorted(bound.items()):
                by_column.setdefault(column, []).append(key)
            collided = {c: k for c, k in by_column.items() if len(k) > 1}
            if collided:
                first_column = sorted(collided)[0]
                raise DynamicColumnWriteError(
                    f"契约表 {table.table_key!r} 的动态列 {collided[first_column]} 都绑定到列 "
                    f"{first_column} —— 两个 `{{slot}}_{{seq}}` 落进同一列时后写的会静默覆盖"
                    "先写的（重复 label 合法，重复列不合法）"
                )
            out[table.table_key] = bound
    return out


def _identity_pattern(identity: str) -> re.Pattern[str]:
    """把契约的 identity 模板（如 `{slot}_{seq}`）编译成键校验正则。

    `{slot}` = 非空的小写标识片段；`{seq}` = 十进制序号。刻意不接受任意字符 —— 否则
    `公司甲_1` 这种带 label 的键也会通过，Property 22 的判据就空转了。
    """
    escaped = re.escape(identity)
    escaped = escaped.replace(re.escape("{slot}"), r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*?")
    escaped = escaped.replace(re.escape("{seq}"), r"\d+")
    return re.compile(escaped)


def assert_footer_anchor_stable(
    *,
    entries: Mapping[str, bytes],
    sheet_part: str,
    contract: SyncContract,
    runtime_binding: Mapping[str, str],
) -> int | None:
    """footer 标记行必须与 representation 冻结的 `GT_FOOTER_ROW` 一致（AC 6.9 / 6.3）。

    判据用两个**互相独立**的载体交叉验证：

    * 可见侧 —— 契约 `footer_anchor` 的 marker 在 `search_column` 上的实际行号；
    * 冻结侧 —— Task 17 写进隐藏 `_GT_SYNC` 的 `GT_FOOTER_ROW`，由 Task 37 的
      :func:`~app.services.workpaper_sync.excel_extract.read_runtime_binding_pairs`
      读出后作为 `runtime_binding` 传进来（本模块不自己解析那张 sheet —— 首版抄了一份
      `r:id="(rId\\d+)"` 的 sheet 定位，而 Task 17 的关系 id 是 `rIdGTSYNC`，于是恒读空、
      把「sheet 定位失败」误报成「缺 GT_FOOTER_ROW」）。

    两者不一致即 footer 已下移（OO 在受管区域内插了行）。此时**fail closed**而不是跟着
    marker 写：Task 37 的 extract 仍按契约 `static_row` 反读，跟着写会让「写在 28 行、
    反读 27 行」这条静默错值路径出现。跟随 footer 需要读写两侧一起改，登记为后续任务。

    契约没声明 footer_anchor 的表返回 `None`（不是判据空转 —— 没有 footer 就没有下移
    问题；守卫用「声明了 footer 的契约」这一支）。
    """
    anchors = [
        table.footer_anchor
        for sheet in contract.sheets
        for table in sheet.tables
        if table.footer_anchor is not None
    ]
    if not anchors:
        return None
    anchor = anchors[0]
    xml = entries[sheet_part].decode("utf-8")
    shared = _shared_strings(entries)
    observed = _find_marker_row(
        xml, column=anchor.search_column, marker=anchor.marker, shared=shared
    )
    if observed is None:
        raise FooterAnchorDriftError(
            f"契约声明的 footer marker {anchor.marker!r} 在列 {anchor.search_column} 上"
            "一处都找不到 —— footer anchor 是 AC 6.3 要求契约表达的结构之一，"
            "定位不到即结构漂移，不得按固定行号继续写"
        )
    frozen = runtime_binding.get("GT_FOOTER_ROW")
    if frozen is None:
        raise FooterAnchorDriftError(
            "runtime binding 里没有 GT_FOOTER_ROW（实测键 "
            f"{sorted(runtime_binding)[:8]}）—— footer 位置缺冻结预期，"
            "无法判断它有没有下移"
        )
    if str(observed) != str(frozen).strip():
        raise FooterAnchorDriftError(
            f"footer marker {anchor.marker!r} 实测在第 {observed} 行，representation 冻结的 "
            f"GT_FOOTER_ROW={frozen} —— footer 已下移。写入侧 fail closed：Task 37 的 extract "
            "仍按契约 static_row 反读，跟着 marker 写会造成「写在新行、反读旧行」的静默错值"
        )
    return observed


def _shared_strings(entries: Mapping[str, bytes]) -> list[str]:
    blob = entries.get("xl/sharedStrings.xml")
    if blob is None:
        return []
    xml = blob.decode("utf-8")
    out: list[str] = []
    for item in re.findall(r"<si>(.*?)</si>", xml, re.S):
        out.append(_xml_unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", item, re.S))))
    return out


def _find_marker_row(
    xml: str, *, column: str, marker: str, shared: Sequence[str]
) -> int | None:
    """在指定列上找 marker 文本所在行（支持 sharedString / inlineStr / str 三种载体）。"""
    for match in re.finditer(
        r'<c r="' + re.escape(column) + r'(\d+)"(?P<attrs>(?:\s[^>]*?)?)>(?P<body>.*?)</c>',
        xml,
        re.S,
    ):
        row = int(match.group(1))
        attrs = match.group("attrs") or ""
        body = match.group("body")
        text: str | None = None
        if 't="s"' in attrs:
            index = re.search(r"<v>(\d+)</v>", body)
            if index is not None and int(index.group(1)) < len(shared):
                text = shared[int(index.group(1))]
        elif 't="inlineStr"' in attrs:
            inline = re.search(r"<t[^>]*>(.*?)</t>", body, re.S)
            text = _xml_unescape(inline.group(1)) if inline else None
        else:
            value = re.search(r"<v>(.*?)</v>", body, re.S)
            text = _xml_unescape(value.group(1)) if value else None
        if text is not None and text.strip() == marker:
            return row
    return None


def assert_footer_formula_covers_managed_rows(
    *,
    entries: Mapping[str, bytes],
    sheet_part: str,
    footer_row: int,
    region: ManagedRegion,
) -> tuple[str, ...]:
    """footer 合计公式的区间必须覆盖当前受管行区间（design §Materialize 第 7 条）。

    真实形态（K11 实测）：footer 的 `SUM(B7:B25)` 是 `t="shared" si="3"` 的主格，
    C26..G26 是无文本的组成员。OO 在受管区域**末尾**插行时 Table ref 会从 `A7:N25` 长到
    `A7:N26`，而 `SUM(B7:B25)` **不会**跟着长 —— 合计从此漏算新行。这是一条真实的审计
    缺陷类，必须打红而不是发布出去。

    只检查**有公式文本**的格（共享公式主格）：组成员的区间由主格 translation 决定，行跨度
    与主格一致，因此主格覆盖到了，成员也覆盖到了。

    返回被检查过的坐标清单 —— 空清单意味着这条判据本次没检查任何东西，调用方据此
    区分「通过」与「空转」。
    """
    xml = entries[sheet_part].decode("utf-8")
    row_match = re.search(_ROW_RE_TPL.format(row=footer_row), xml, re.S)
    if row_match is None:
        raise FooterFormulaRangeError(
            f"footer 行 {footer_row} 在 sheet XML 里不存在 —— 合计行缺失，无法证明合计覆盖"
            f"受管行区间 {region.first_row}..{region.last_row}"
        )
    checked: list[str] = []
    for match in _ANY_CELL_RE.finditer(row_match.group("body")):
        coord = f"{match.group(1) or match.group(3)}{footer_row}"
        view = _cell_view(xml, coord)
        if view is None or not view.formula_text:
            continue
        checked.append(coord)
        for span in _RANGE_IN_FORMULA_RE.finditer(view.formula_text):
            first, last = int(span.group("r1")), int(span.group("r2"))
            if first > region.first_row or last >= region.last_row:
                continue
            raise FooterFormulaRangeError(
                f"footer 格 {coord} 的公式 {view.formula_text!r} 区间只到第 {last} 行，"
                f"而受管行区间已到第 {region.last_row} 行 —— 合计漏算 "
                f"{region.last_row - last} 行。共享公式主格不得在此处被改写"
                "（会让整组成员失效），故 fail closed 交人工处理"
            )
    return tuple(checked)


# ─────────────────────────────────────────────────────────────────────────
# 3.3 计划构造
# ─────────────────────────────────────────────────────────────────────────


def _instantiate(stable_key: str, row_identity: str) -> str:
    return stable_key.replace("{row_uuid}", row_identity)


def _formula_body(text: str) -> str:
    """公式的 OOXML 形态：去掉**一个**前导 `=`。

    Task 37 的 `formula_inventory` 走 openpyxl（`data_only=False`），值形如 ``=G7-D7``（这是
    openpyxl 的用户可见形态，也是它筛选公式格的判据：`startswith("=")`）；而 OOXML 的
    ``<f>`` 内容**不带** `=`。两侧不换算就会写出 ``<f>=G7-D7</f>``，Excel 打开后是
    ``==G7-D7``。本任务首轮实测踩过（守卫
    `test_reported_tamper_proceeds_and_keeps_the_template_formula` 当场打红）。
    """
    return text[1:] if text.startswith("=") else text


def _write_kind_for(spec: FieldSpec) -> CellWriteKind:
    if spec.mode is FieldMode.formula:
        return CellWriteKind.cached_value_only
    if spec.value_type in (
        ValueType.amount,
        ValueType.integer,
        ValueType.rate,
        ValueType.ratio,
        ValueType.boolean,
    ):
        return CellWriteKind.number_literal
    return CellWriteKind.inline_text


def _normalised_write_value(field: FieldValue, spec: FieldSpec, coord: str) -> Any:
    """把 projection 值规范化成落盘值。规范化失败即 fail visible。

    复用 `merge.normalize_value` 的**同一套**口径：写入侧若自己写一套，「merge 认为等值、
    反读认为不等值」就会变成无法解释的发布失败。
    """
    try:
        return normalize_value(field.value, spec.value_type)
    except ValueNormalizationError as exc:
        raise EditableCellWriteError(
            f"受管格 {coord}（{spec.stable_field_key}）的值 {field.value!r} 无法按 "
            f"{spec.value_type.value} 规范化: {exc} —— 不得写一个自己都读不懂的值"
        ) from exc


def plan_managed_writes(
    *,
    projection: Projection,
    contract: SyncContract,
    binding: ExcelIdentityBinding,
    region: ManagedRegion,
    scan: RowIdentityScan,
    substrate_entries: Mapping[str, bytes],
    substrate_formulas: Mapping[str, str],
    runtime_binding: Mapping[str, str],
    intended_formulas: Mapping[str, str] | None = None,
) -> MaterializePlan:
    """算出「往哪些格写什么」。纯函数：不碰磁盘、不改 `substrate_entries`。

    执行顺序即判据（不可交换）：

    1. 动态列绑定前置判据（Property 22）；
    2. footer anchor 与冻结 `GT_FOOTER_ROW` 交叉验证（footer 下移 fail closed）；
    3. footer 合计公式区间覆盖当前受管行区间；
    4. 行集一致性（merged projection 的行身份必须都有物理行）；
    5. 逐字段按 mode 生成写入，并对受保护格/共享公式主格施加禁令；
    6. minted row identity 落隐藏 UUID 列。

    2/3 放在字段写入**之前**：结构漂移时一格都不该写。

    `intended_formulas` 是受保护格 `<f>` 的**应有**文本（OO→HTML 方向取 application 冻结的
    base representation）。缺省为 `substrate_formulas`，即 HTML→OO 方向「substrate 自己就是
    权威」。给了它之后，substrate 上被改写过的公式会被还原 —— 见 :attr:`CellWrite.formula_text`。
    """
    dynamic_columns = assert_dynamic_column_binding_usable(
        contract=contract, binding=binding
    )
    footer_row = assert_footer_anchor_stable(
        entries=substrate_entries,
        sheet_part=region.sheet_part,
        contract=contract,
        runtime_binding=runtime_binding,
    )
    if footer_row is not None:
        assert_footer_formula_covers_managed_rows(
            entries=substrate_entries,
            sheet_part=region.sheet_part,
            footer_row=footer_row,
            region=region,
        )

    dynamic_table, static_tables = managed_tables_of(contract, binding=binding)
    physical = dict(scan.row_identity_by_row)
    row_of_identity: dict[str, int] = {}
    for row, identity in sorted(physical.items()):
        row_of_identity.setdefault(identity, row)

    wanted = tuple(projection.row_keys.get(dynamic_table.table_key, ()))
    orphan = [identity for identity in wanted if identity not in row_of_identity]
    if orphan:
        raise RowSetDivergenceError(
            f"merged projection 的行身份 {orphan[:3]}（共 {len(orphan)} 个）在 substrate 上"
            "没有物理行 —— 需要结构性插行。Task 37 的 `verify_unmanaged_regions` 把受管 sheet 的 "
            "mergeCells/cols/dataValidations/conditionalFormatting/sheetProtection 逐字节锁死，"
            "而受管区域之下还存在 merge 与共享公式主格（K11 实测 E30:F30 与 "
            "SUM(B7:B25) si=3），任何行位移都会被判成未管理区域漂移。故此处 fail closed，"
            "结构性插删行留给后续任务连同 unmanaged-region policy 一起扩"
        )

    xml = substrate_entries[region.sheet_part].decode("utf-8")
    intended_map: Mapping[str, str] = (
        substrate_formulas if intended_formulas is None else intended_formulas
    )
    writes: list[CellWrite] = []
    preserved: dict[str, str] = {}

    def _emit(spec: FieldSpec, table: TableSpec, row: int, identity: str) -> None:
        column = _resolve_column(spec, table=table, region=region, binding=binding)
        coord = f"{column}{row}"
        key = _instantiate(spec.stable_field_key, identity)
        field = projection.get(key)
        if field is None:
            return
        view = _cell_view(xml, coord)
        restore = ""
        if spec.mode is FieldMode.formula:
            if view is None or not view.has_formula:
                raise ProtectedRegionWriteError(
                    f"契约把 {key!r} 声明为 formula，但 substrate 的 {coord} 没有公式 —— "
                    "契约/模板漂移，不得凭空写一个公式或把它当字面量覆盖（AC 6.6）"
                )
            observed = substrate_formulas.get(key, view.formula_text or "")
            intended = intended_map.get(key, observed)
            preserved[key] = intended
            if intended and _formula_body(intended) != _formula_body(observed):
                if not (view.formula_text or ""):
                    raise ProtectedRegionWriteError(
                        f"受保护格 {coord}（{key}）的公式与 base representation 不符"
                        f"（应为 {intended!r}，实测 {observed!r}），但它在 OOXML 上是共享公式"
                        f"组的**成员**（`<f t=\"shared\" si=...` 无文本）—— 成员的公式由主格"
                        "翻译而来，逐格还原不了；这种形态意味着主格被改写、整组已失效，"
                        "必须人工裁决而不是悄悄写回一格（AC 6.6）"
                    )
                restore = _formula_body(intended)
        elif spec.mode is FieldMode.auto_source:
            if view is not None and view.has_formula:
                raise ProtectedRegionWriteError(
                    f"契约把 {key!r} 声明为 auto_source（服务端字面量），但 substrate 的 "
                    f"{coord} 是公式 {view.formula_text!r} —— 写字面量会毁掉模板公式；"
                    "契约与模板必须先对齐（AC 6.6 / 3.5）"
                )
        elif view is not None and view.shared_ref and ":" in (view.shared_ref or ""):
            raise SharedFormulaMasterWriteError(
                f"契约把 {key!r} 声明为 {spec.mode.value}，但 {coord} 是共享公式主格 "
                f"(ref={view.shared_ref})—— 覆盖主格会让整组成员失效；"
                "该格要么改契约声明成 formula，要么先在模板里解开共享公式"
            )
        writes.append(
            CellWrite(
                coord=coord,
                kind=_write_kind_for(spec),
                value=_normalised_write_value(field, spec, coord),
                stable_field_key=key,
                row_key=identity,
                mode=spec.mode,
                formula_text=restore,
            )
        )

    for static_table in static_tables:
        for spec in static_table.fields:
            if spec.cell is None or spec.cell.static_row is None:
                continue
            _emit(spec, static_table, spec.cell.static_row, "")

    for identity in wanted:
        row = row_of_identity[identity]
        for spec in dynamic_table.fields:
            if spec.cell is None or spec.cell.row_from != "row_identity":
                continue
            _emit(spec, dynamic_table, row, identity)

    for row, minted in sorted(scan.minted_by_row.items()):
        if minted not in set(wanted):
            raise RowIdentityWriteError(
                f"Task 37 为第 {row} 行 minted 了 identity {minted!r}，但 merged projection "
                "的行集里没有它 —— OO 新增行的身份必须先经三方 merge 进入 projection，"
                "写入侧不得自行决定要不要保留它"
            )
        writes.append(
            CellWrite(
                coord=f"{region.uuid_column}{row}",
                kind=CellWriteKind.row_identity,
                value=minted,
                row_key=minted,
            )
        )

    return MaterializePlan(
        sheet_part=region.sheet_part,
        sheet_name=region.sheet_name,
        writes=tuple(writes),
        preserved_formulas=dict(sorted(preserved.items())),
        dynamic_column_columns=dynamic_columns,
        footer_marker_row=footer_row,
    )


def _resolve_column(
    spec: FieldSpec,
    *,
    table: TableSpec,
    region: ManagedRegion,
    binding: ExcelIdentityBinding,
) -> str:
    """受管字段的 Excel 列。

    动态列走 `binding.dynamic_column_columns` 的**实测绑定**（`{slot}_{seq}` → 列），
    静态列走契约声明列。与 Task 37 `_resolve_field_column` 同一套语义 —— 两侧若各写一套
    就会出现「写在 E 列、反读 F 列」。本函数只在 Task 38 需要的形态上实现，并由
    `test_column_resolution_agrees_with_extractor` 与 Task 37 双向锁死。
    """
    cell = spec.cell
    if cell is None:
        raise EditableCellWriteError(
            f"受管字段 {spec.stable_field_key!r} 缺 cell 声明 —— 契约校验器本应拦住"
        )
    if table.dynamic_columns is None or spec.column_key is None:
        return cell.column
    bound = binding.dynamic_column_columns.get(table.table_key, {})
    column = bound.get(spec.column_key)
    if not column:
        raise DynamicColumnWriteError(
            f"契约表 {table.table_key!r} 的动态列 {spec.column_key!r} 没有实测列绑定"
            f"（已绑定 {sorted(bound)}）—— 不得按声明列右移猜（Requirement 6.4）"
        )
    if not region.contains_column(column):
        raise DynamicColumnWriteError(
            f"动态列 {spec.column_key!r} 绑定到 {column}，落在 Table ref "
            f"{region.table_ref} 的列跨度之外"
        )
    return column


# ═══════════════════════════════════════════════════════════════════════════
# 4. 写盘
# ═══════════════════════════════════════════════════════════════════════════


def assert_output_outside_template_library(output: Path) -> None:
    """输出路径不得落在 `backend/wp_templates/` 之下（Requirement 9.9）。

    判据是**解析后的绝对路径分量**，不是字符串前缀比较：`..` 拼出来的路径靠字符串比较
    看不出来。
    """
    resolved = output.resolve()
    if TEMPLATE_LIBRARY_MARKER in resolved.parts:
        raise TemplateLibraryWriteError(
            f"materialize 输出 {resolved} 落在模板库（路径分量含 "
            f"{TEMPLATE_LIBRARY_MARKER!r}）—— 运行时不得写回 `backend/wp_templates/`，"
            "它是唯一权威源（Requirement 9.9 / 6.13）"
        )


def apply_plan_zip(source_bytes: bytes, plan: MaterializePlan) -> bytes:
    """zip 级定点修改：只改受管 sheet part，其它条目**逐字节原样搬运**。"""
    entries = _read_entries(source_bytes)
    if plan.sheet_part not in entries:
        raise EditableCellWriteError(
            f"受管 sheet part {plan.sheet_part!r} 不在 substrate zip 里"
        )
    xml = entries[plan.sheet_part].decode("utf-8")
    entries[plan.sheet_part] = _patch_sheet_xml(xml, plan.writes).encode("utf-8")
    return _write_entries(entries)


def apply_plan_openpyxl(
    source: Path,
    plan: MaterializePlan,
    output: Path,
    *,
    decision: WriteStrategyDecision,
) -> None:
    """openpyxl 全量 roundtrip。**只有** :func:`select_write_strategy` 放行时才可调用。

    保留这条路径的理由：策略门若指向一个未实现的分支，那道门就是装饰品 —— 「被允许时
    会发生什么」必须真实可测（守卫用它证明「被放行的模板上这条路径真的能写出受管格」）。

    🔴 `decision` 是**必填**参数并在函数入口 fail closed，不是靠调用方自觉：把「只有放行
    时才可调用」写在 docstring 里等于没有判据 —— 任何新调用点漏判就直接全量重写一个含
    drawing/chart/pivot 的工作簿，而那类丢失要等未管理区域比对才发现（且 openpyxl 重写
    连 `verify_unmanaged_regions` 的 before/after 都会一起变，诊断指向完全错误的地方）。
    """
    if not decision.openpyxl_allowed:
        raise WriteStrategyForbiddenError(
            "openpyxl 全量重写未获放行，却被直接调用 —— 拒绝理由："
            + "；".join(decision.refusals or ("(策略未给出理由)",))
        )
    import openpyxl

    wb = openpyxl.load_workbook(source, data_only=False)
    try:
        if plan.sheet_name not in wb.sheetnames:
            raise EditableCellWriteError(
                f"受管 sheet {plan.sheet_name!r} 不在 workbook 里（{wb.sheetnames}）"
            )
        ws = wb[plan.sheet_name]
        for write in plan.writes:
            cell = ws[write.coord]
            if write.kind is CellWriteKind.cached_value_only:
                # openpyxl 不保留「公式 + 缓存值」两者 ⇒ 公式格只能保公式本体。
                continue
            cell.value = write.value
        wb.save(output)
    finally:
        wb.close()


# ═══════════════════════════════════════════════════════════════════════════
# 5. 入口
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ExcelMaterializeOutcome:
    """一次 materialize 的全部产物。**不含**任何发布/提交面。"""

    result: MaterializeResult
    plan: MaterializePlan
    strategy: WriteStrategyDecision
    substrate_view: ExcelExtractOutcome
    staged_identity_inventory: RuntimeIdentityInventory
    #: 交给 Task 37 `verify_before_commit` 的 `baseline_formulas`：substrate 侧受保护格的
    #: 公式文本。它是「staged result 里这些格**应该**还是什么公式」的唯一依据。
    intended_formulas: Mapping[str, str]

    @property
    def output_path(self) -> Path:
        return self.result.output_path

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_sha256": self.result.artifact_sha256,
            "structure_hash": self.result.structure_hash,
            "identity_inventory_sha256": self.result.identity_inventory_sha256,
            "managed_field_count": self.result.managed_field_count,
            "plan": self.plan.as_dict(),
            "strategy": self.strategy.as_dict(),
            "intended_formula_count": len(self.intended_formulas),
            "substrate_identity_inventory_sha256": (
                self.substrate_view.identity_inventory.inventory_digest
            ),
            "staged_identity_inventory_sha256": (
                self.staged_identity_inventory.inventory_digest
            ),
        }


def materialize_projection(
    *,
    substrate: Path,
    projection: Projection,
    output: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    substrate_role: SubstrateRole | str,
    substrate_kind: ArtifactKind | str,
    substrate_state: ArtifactState | str,
    capability: ExcelWriteCapability | None = None,
    intended_formulas: Mapping[str, str] | None = None,
    limits: SyncLimits | None = None,
) -> ExcelMaterializeOutcome:
    """把 projection 写进 substrate 的**副本**，产出 staged 文件。

    执行顺序即判据（不可交换）：

    1. **frozen 身份门**（Task 36 `assert_engine_entry_definitions`）—— candidate /
       unapproved bundle / contract digest 漂移在写第一个字节之前就被拒；
    2. **substrate 准入**（Task 13 `assert_substrate_usable`）—— quarantined incoming 与
       upgrade candidate 在 engine 入口拒绝（AC 8.10）；
    3. **输出路径不得落在模板库**；
    4. **读 substrate 的 identity 与公式**（Task 37 `extract_projection`）；
    5. **写入策略裁决**（zip patch 默认）；
    6. **算写入计划**（含 footer / 动态列 / 行集三道结构判据）；
    7. **写临时文件再原子改名**成 `output` —— 校验失败时盘上不会留半成品
       （Property 9 的文件侧）；
    8. **反读 staged 产物的 identity inventory**，证明 minted UUID 真的落盘了。

    1 与 2 的先后是有意的：身份门失败时连 substrate 都不该被打开。
    """
    lim = limits or load_limits()
    assert_engine_entry_definitions(definitions)
    assert_substrate_usable(
        role=substrate_role, artifact_kind=substrate_kind, artifact_state=substrate_state
    )
    assert_output_outside_template_library(output)

    substrate_view = extract_projection(
        artifact=substrate,
        definitions=definitions,
        binding=binding,
        substrate_role=substrate_role,
        artifact_kind=substrate_kind,
        artifact_state=substrate_state,
        limits=lim,
    )
    strategy = select_write_strategy(artifact=substrate, capability=capability)
    source_bytes = substrate.read_bytes()
    entries = _read_entries(source_bytes)
    with zipfile.ZipFile(substrate) as zf:
        runtime_binding = read_runtime_binding_pairs(
            zf, metadata_sheet=binding.metadata_sheet
        )
    plan = plan_managed_writes(
        projection=projection,
        contract=definitions.contract,
        binding=binding,
        region=substrate_view.region,
        scan=substrate_view.scan,
        substrate_entries=entries,
        substrate_formulas=substrate_view.formula_inventory,
        runtime_binding=runtime_binding,
        intended_formulas=intended_formulas,
    )

    tmp = output.with_name(output.name + ".materializing")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if strategy.strategy is ExcelWriteStrategy.openpyxl_roundtrip:
            apply_plan_openpyxl(substrate, plan, tmp, decision=strategy)
        else:
            tmp.write_bytes(apply_plan_zip(source_bytes, plan))
        os.replace(tmp, output)
    finally:
        if tmp.exists():
            tmp.unlink()

    staged_bytes = output.read_bytes()
    staged_inventory = _staged_identity_inventory(
        staged_bytes=staged_bytes,
        output=output,
        definitions=definitions,
        binding=binding,
        limits=lim,
    )
    return ExcelMaterializeOutcome(
        result=MaterializeResult(
            output_path=output,
            document_type=definitions.contract.document_type,
            artifact_sha256=hashlib.sha256(staged_bytes).hexdigest(),
            structure_hash=normalized_structure_hash(staged_bytes),
            identity_inventory_sha256=staged_inventory.inventory_digest,
            managed_field_count=len(plan.field_writes),
        ),
        plan=plan,
        strategy=strategy,
        substrate_view=substrate_view,
        staged_identity_inventory=staged_inventory,
        intended_formulas=dict(sorted(plan.preserved_formulas.items())),
    )


def _staged_identity_inventory(
    *,
    staged_bytes: bytes,
    output: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    limits: SyncLimits,
) -> RuntimeIdentityInventory:
    """反读 staged 产物的 identity 清册（Property 66 在写入侧的收口）。

    刻意**实测**而不是「拿 substrate 的清册加上我 minted 的那几个」：后者是自证式推导，
    「UUID 根本没写进去」时它照样给出正确答案。
    """
    entries = _read_entries(staged_bytes)
    with zipfile.ZipFile(output) as zf:
        region = resolve_managed_region(zf, contract=definitions.contract, binding=binding)
        xml = entries[region.sheet_part].decode("utf-8")
        raw: dict[int, str] = {}
        shared = _shared_strings(entries)
        for row in region.row_span:
            view = _cell_view(xml, f"{region.uuid_column}{row}")
            raw[row] = "" if view is None else _cell_text(view, shared)
        return read_runtime_identity_inventory(
            zf,
            region=region,
            binding=binding,
            raw_uuid_by_row=raw,
            limits=limits,
        )


def _cell_text(view: _CellView, shared: Sequence[str]) -> str:
    if 't="s"' in view.attrs:
        index = re.search(r"<v>(\d+)</v>", view.body)
        if index is not None and int(index.group(1)) < len(shared):
            return shared[int(index.group(1))].strip()
        return ""
    inline = re.search(r"<t[^>]*>(.*?)</t>", view.body, re.S)
    if inline is not None:
        return _xml_unescape(inline.group(1)).strip()
    value = re.search(r"<v>(.*?)</v>", view.body, re.S)
    return _xml_unescape(value.group(1)).strip() if value else ""
