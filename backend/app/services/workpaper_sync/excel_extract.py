# -*- coding: utf-8 -*-
"""Excel identity-aware **extractor** 与 materializer/rematerializer 共用 verifier（Task 37）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 37
Requirements: 6.5, 6.6, 6.7, 6.8, 6.9, 6.11, 6.12, 6.15, 6.16, 6.20, 8.11, 14.11, 14.12
Properties: **P23** / **P24** / **P27** / **P29** / **P60** / **P66**

═══ 一、本模块在链条里的位置（以及**不**做什么）═══

Task 36 的 `ExcelEntryDefinitionLoader.load()` 产出 :class:`FrozenEntryDefinitions` ——
本模块的 contract/identity/adapter 身份**只**来自那个 frozen bundle，没有任何 alias
入口，也不按 `entry_id` 反查「现在该用哪个 bundle」。

本模块**先于** Task 38，因此：

* 不 import 任何 materializer/rematerializer 模块（:func:`assert_no_materializer_dependency`
  用**真实 import 图**实测这一点，而不是 grep 源码字符串）；
* 不写任何字节：openpyxl 只以 ``read_only=True`` 打开，zip 只读；
* 不 commit、不递增 revision、不切 pointer —— :class:`ExcelExtractOutcome` 是纯数据。

Task 38 反过来依赖本模块的三个 verifier（:func:`verify_roundtrip_equivalence` /
:func:`verify_formula_regions` / :func:`verify_unmanaged_regions`），并且必须经
:meth:`ExcelVerificationBundle.assert_publishable` 才能交 `ContentMutationService`
（Requirement 8.11：反读不等值或未管理区域异动时 application 失败，projection /
pointer / last-applied / client-confirmed base 一个都不许推进）。

═══ 二、identity 只走 `excel_table_sheet_association` ═══

Task 5 的真实 OO 9.4 黑盒探针**证伪**了两类锚点：``sheet_id``（OO 每次保存按 tab 顺序
重编号 ⇒ 解析到另一张 sheet）与 ``sheet_display_name``（用户可改名）。当前唯一通过的
载体锚点是 Excel Table 与其所属 sheet 的关联关系。

本模块因此：

1. sheet 定位**只**由 `xl/workbook.xml` + `xl/worksheets/*.xml` 的 ``<tableParts>`` →
   `xl/tables/tableN.xml` 关联求解（:func:`resolve_managed_region`），复用
   `excel_structure_fingerprint` 的同一份解析实现，不在这里抄第二份；
2. 运行时反读出的 ``resolved_sheet_by`` 若不是 :data:`TABLE_SHEET_ANCHOR`，抛
   :class:`ForbiddenSheetAnchorError`；
3. 「UUID 列整列被删」必须**先**归类成 :class:`IdentityCarrierMissingError`（
   Requirement 6.15 的「拒绝」形态），**再**判锚点路径 —— 顺序反了会把「列没了」报成
   「锚点用错」，真正的锚点误用分支从此不可分辨（Task 17 已实测过这个坑）。

═══ 三、五类身份/保护异常各有专属、各自可达的判据 ═══

本 spec 已经三次踩到同一个坑：多条判据共用一个 error code / conflict kind 时，靠前的
分支被短路后靠后的分支会抛同一类型把它遮蔽 ⇒ 只断言类型的守卫判 GREEN。所以：

=========================  ===========================================  =====================
形态                       判据                                          出口
=========================  ===========================================  =====================
空 row UUID                :func:`classify_empty_row_identity` 三分类     ``empty_row_identity``
                                                                        或 minted 新 ID
重复 row UUID（值相同）      同 UUID 落在 ≥2 个 Excel 行                   ``duplicate_row_identity``
重复 row UUID（值不同）      同 stable key 在多位置取到不同值                额外 ``multi_location_divergence``
已删除 UUID 复现            UUID ∈ 冻结 tombstone 清册                     ``reused_tombstoned_row_identity``
identity 列/载体缺失         Table 覆盖数据行却读不到一个 UUID               :class:`IdentityCarrierMissingError`
类型规范化失败              `merge.normalize_value` 抛错                   ``type_normalization_failure``
公式/auto-source 被改        与 frozen baseline 比对                       protected 冲突 + 专属 tamper kind
=========================  ===========================================  =====================

「重复 UUID」与「多位置异值」刻意是**两条**：前者是身份问题（复制行），后者是值问题
（连取哪个值都无法决定）。值相同的复制行只触发前者，值不同的同时触发两者，于是两条
判据都可达、都能被变异 falsify。

保护字段的 tamper 走 **projection 值**而不是旁路信号：受保护单元格的 projection 值
= 「若该格是公式则取公式文本，否则取字面量」。于是「把 `=SUM(...)` 敲成一个恰好等于
计算结果的字面量」也会让 incoming ≠ base，Task 14 的 merge 照常生成 protected 冲突
（Property 24），不需要在 merge 之外再开一条能被绕过的通路。:class:`ProtectedCellFinding`
只是把「为什么变了」分类出来供诊断与 :func:`verify_formula_regions` 使用。

═══ 四、流式与预算（Requirement 6.12 / 14.11 / Property 60）═══

* zip/压缩/展开/entry 预算全部委派 Task 11 的 :func:`validate_ooxml_artifact` ——
  它已经是「越界立即中止」的单一实现，本模块不复制阈值数字；
* 行/field 预算由 :class:`StreamingProjectionBudget` 在**每读一行/一字段时**判定，
  不是读完整表再统计：后者在 100000 行的表上已经把内存吃掉了；
* 单表按 :func:`rows_per_chunk` 分块；块大小由 `SyncLimits` 的
  ``peak_memory_budget_bytes // chunk_bytes`` **派生**，本模块不写死数字；
* projection sidecar 走 gzip **流式**写（逐块 flush），不先拼一个完整 JSON 字符串。
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from pathlib import Path
from typing import Any, Final, Iterable, Iterator, Mapping, Sequence
from xml.etree import ElementTree as ET

from openpyxl.utils import column_index_from_string, get_column_letter

from app.services.excel_metadata_sheet_policy import is_platform_metadata_sheet
from app.services.excel_structure_fingerprint import (
    GT_SYNC_SHEET_NAME,
    FingerprintError,
)
from app.services.excel_structure_fingerprint import (
    _PROTECTED_PART_PATTERNS as PROTECTED_PART_PATTERNS,
)
from app.services.excel_structure_fingerprint import (
    _normalise_part as normalise_part,
)
from app.services.excel_structure_fingerprint import (
    _parse_tables as parse_tables,
)
from app.services.excel_structure_fingerprint import (
    _parse_workbook_xml as parse_workbook_xml,
)
from app.services.workpaper_sync.adapters.base import (
    FieldValue,
    Projection,
    SubstrateRole,
    UnmanagedRegionDriftError,
    UnmanagedRegionReport,
    assert_substrate_usable,
)
from app.services.workpaper_sync.adapters.registry import (
    assert_authority_model_contract_pairing,
    assert_bundle_usable,
    assert_contract_identity_frozen,
)
from app.services.workpaper_sync.conflicts import (
    ConflictKind,
    ConflictRecord,
    SchemaAnomalyKind,
    SuggestedAction,
    ValueEnvelope,
)
from app.services.workpaper_sync.contracts import (
    ExtractCarrierTier,
    FieldMode,
    FieldSpec,
    SyncContract,
    TableSpec,
    ValueType,
    parse_a1_range,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.excel_entry_gate import (
    EntryIdentityInventory,
    FrozenEntryDefinitions,
    assert_metadata_sheet_excluded,
)

# 🔴 `excel_row_shift` 是**纯函数层**（零 I/O、零写入面、模块级只 import `models`），
#    不在 `FORBIDDEN_DOWNSTREAM_MODULES` 里 ⇒ 本模块可以依赖它而不违反
#    `assert_no_materializer_dependency`（那条禁的是 materializer / rematerializer /
#    adapters.excel 三个**写入侧**模块）。方向是 verifier → 纯函数，不是 verifier → 写入侧。
from app.services.workpaper_sync.excel_row_shift import (
    STRUCTURE_BARE_ROW_ATTRS,
    STRUCTURE_ROW_BEARING_ATTRS,
    STRUCTURE_ROW_BEARING_TEXT_TAGS,
    RowShiftPlan,
    remap_a1_rows,
    unextend_total_formula,
)
from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.merge import (
    ContractIndex,
    StructuralAnomaly,
    ValueNormalizationError,
    normalize_value,
)
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState, SyncDomainError
from app.services.workpaper_sync.ooxml_security import validate_ooxml_artifact

__all__ = [
    # 异常
    "ExcelExtractError",
    "IdentityCarrierMissingError",
    "ForbiddenSheetAnchorError",
    "ManagedRegionResolutionError",
    "DynamicColumnBindingMissingError",
    "IdentityRetentionError",
    "RoundtripEquivalenceError",
    "FormulaRegionDriftError",
    "VerificationNotPassedError",
    # 常量
    "TABLE_SHEET_ANCHOR",
    "DISPROVED_SHEET_ANCHORS",
    "UNMANAGED_ASPECTS",
    "DERIVED_PARTS",
    "MINTED_ROW_IDENTITY_PREFIX",
    # 行身份
    "EmptyRowIdentityDisposition",
    "classify_empty_row_identity",
    "mint_row_identity",
    "RowIdentityScan",
    # identity inventory
    "RuntimeIdentityInventory",
    "read_runtime_identity_inventory",
    "read_runtime_binding_pairs",
    "assert_identity_carriers_usable",
    "assert_identity_inventory_retained",
    "RETENTION_CHECKED_FIELDS",
    "RETENTION_EXEMPT_FIELDS",
    # 受管区域
    "ManagedRegion",
    "ExcelIdentityBinding",
    "resolve_managed_region",
    "managed_tables_of",
    # 预算与分块
    "StreamingProjectionBudget",
    "rows_per_chunk",
    # 未管理区域
    "UnmanagedRegionDigest",
    "unmanaged_region_digest",
    "verify_unmanaged_regions",
    # extract
    "FormulaTamperKind",
    "ProtectedCellFinding",
    "ExtractStats",
    "ExcelExtractOutcome",
    "assert_engine_entry_definitions",
    "extract_projection",
    "write_projection_sidecar",
    "read_projection_sidecar",
    # verifier
    "RoundtripReport",
    "verify_roundtrip_equivalence",
    "assert_roundtrip_equivalent",
    "FormulaRegionReport",
    "verify_formula_regions",
    "assert_formula_regions_intact",
    "protected_conflicts_for_findings",
    "assert_protected_tamper_fully_reported",
    "ExcelVerificationBundle",
    "verify_before_commit",
    "assert_no_materializer_dependency",
]


# ═══════════════════════════════════════════════════════════════════════════
# 0. 常量
# ═══════════════════════════════════════════════════════════════════════════

#: Task 5 唯一通过真实 OO 9.4 探针的载体锚点。
TABLE_SHEET_ANCHOR: Final[str] = "excel_table_sheet_association"

#: Task 5 已**证伪**的两类 sheet 锚点。运行时反读命中任一即 fail closed。
DISPROVED_SHEET_ANCHORS: Final[frozenset[str]] = frozenset(
    {"sheet_id", "sheet_name", "sheet_display_name"}
)

#: minted row identity 的前缀。与 Task 17 的 `GTROW-{template}-{row:04d}` 刻意不同域，
#: 这样「运行期新分配」与「模板预生成」在审计上可分辨。
MINTED_ROW_IDENTITY_PREFIX: Final[str] = "GTROW-MINTED-"

#: 未管理区域的 aspect 顺序（报告「首个差异」时按此序）。最后一项是**catch-all**：
#: 没有它，新出现的部件类别会悄悄不被任何 aspect 覆盖 —— 那正是「只检查了列出来的东西」
#: 这类假绿的入口。
UNMANAGED_ASPECTS: Final[tuple[str, ...]] = (
    "managed_sheet_unmanaged_cells",
    "managed_sheet_structure",
    "other_sheet_parts",
    "protected_parts",
    "shared_strings_prefix",
    "workbook_and_styles",
    "relationships",
    "other_parts",
)

#: 派生缓存部件：Excel / OnlyOffice 每次保存都会重算，逐字节比对必然假红。
#: 刻意用**显式清单**而不是「凡是变了就放过」，加一项就要在这里留痕。
DERIVED_PARTS: Final[frozenset[str]] = frozenset({"xl/calcChain.xml"})

_MAIN_NS: Final[str] = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

#: `<cols>` 里的单个 `<col .../>` 声明。属性顺序**不作假设**（OOXML 不保证顺序，
#: openpyxl / Excel / OO 三家写出来的顺序各不相同），min/max/hidden 各自单独取。
_COL_ELEMENT_RE: Final[re.Pattern[str]] = re.compile(r"<col\b[^>]*/?>")
_COL_ATTR_RE: Final[re.Pattern[str]] = re.compile(r"\b(?P<key>[A-Za-z]+)=\"(?P<value>[^\"]*)\"")

#: 受管 sheet 上要逐元素锁死的结构块。
#:
#: 前六项是原始清单（merge / 列宽隐藏 / 数据验证 / 条件格式 / 保护 / sheet 属性）。
#:
#: ═══ 后四项：`dimension` / `hyperlinks` / `autoFilter` / `rowBreaks` ══════════
#:
#: 它们在本 spec 之前**不在任何 aspect 里** —— 既不在这六个 tag 内，而受管 sheet part
#: 又被 `_classify_parts` 的 `managed_parts` 整件排除。后果不是「它们被允许改」，而是
#: 「改了没人看」：任何往受管 sheet 里插行的实现都会顺手改动它们（四项全部携带行号），
#: 而 verifier 一声不响 —— 那是假绿的入口，不是通行证。
#:
#: 补进来的顺序是刻意的（spec §Rollout 第 1 步）：**先让它们能红，再让位移函数动它们**。
#: 反过来做就等于「先改后补检查」，中间那段时间的产物无人复核。
#:
#: 实测存在性（`backend/wp_templates/` 权威模板，各自的受管 sheet）：
#:
#:   模板  受管 sheet              sheet part   dimension  hyperlinks  autoFilter  rowBreaks
#:   K11   审定表K11-1              sheet3.xml       1           1          0         0
#:   B60   B60-1工时预算与控制表      sheet2.xml       1           1          0         0
#:   D2    明细表D2-2               sheet8.xml       1           1          0         0
#:   H1    减少检查表H1-8            sheet12.xml      1           1          0         0
#:   G7    附注披露信息（国企）        sheet5.xml       1           0          0         0
#:
#: 🔴 上表 K11 一行**首版记错过两处**，已复测更正：受管 sheet 是
#:   `审定表K11-1` = `xl/worksheets/sheet3.xml`（sheet4 是「附注披露信息（上市公司）」，
#:   不是受管 sheet），且它的 `hyperlinks` 实测为 **1** 不是 0。冻结事实写错的代价不是
#:   注释不准，而是会把「该结构需不需要造注入变体」的判断整个带偏。
#:
#: ⇒ `dimension` 五个模板各 1 个、`hyperlinks` 除 G7 外各 1 个 ⇒ 这两项可直接用真实模板
#:   做非空验证；`autoFilter` / `rowBreaks` 在全部实测模板上都是 0，其判据必须用**真实
#:   模板的合法变体**（zip 级注入该元素）验证，不得手搓最小 xlsx —— 那会让判据在空集上恒真。
#:
#: 🔴 扩充本身会改变 `managed_sheet_structure` 的 digest 值与 coverage 计数。这是**预期**：
#:   digest 是比对用的中间值，before/after 两侧同时变化不影响等价性判定；受影响的只有
#:   「断言具体 coverage 数值」的用例（实测恰一处：`test_task42_h1_grouped_dynamic_pilot`
#:   的 `"managed_sheet_structure": 4` → 6）。
#:
#: Spec: excel-structural-row-insertion-and-shift-aware-verification（Requirement 1.3 / 1.4）
_SHEET_STRUCTURE_BLOCKS: Final[tuple[str, ...]] = (
    "sheetPr",
    "cols",
    "mergeCells",
    "dataValidations",
    "conditionalFormatting",
    "sheetProtection",
    # ── 本 spec 新增（Requirement 1.3）────────────────────────────
    "dimension",
    "hyperlinks",
    "autoFilter",
    "rowBreaks",
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常 —— 一条禁令一个类型一个 error_code
# ═══════════════════════════════════════════════════════════════════════════


class ExcelExtractError(SyncDomainError):
    """Task 37 的域基类。"""

    error_code = "excel_extract_failed"


class IdentityCarrierMissingError(ExcelExtractError):
    """identity 载体缺失（UUID 列被删、Table 不在、隐藏 metadata sheet 丢失）。

    Requirement 6.20：instrumented identity 与已验证原生锚点**均**不存在时 extract
    必须 fail closed —— 不得降级到中文标题或单元格位置猜测。
    """

    error_code = "excel_extract_identity_carrier_missing"


class ForbiddenSheetAnchorError(ExcelExtractError):
    """运行时用到了 Task 5 已证伪的 sheet 锚点（`sheet_id` / sheet 展示名）。

    与 :class:`IdentityCarrierMissingError` 严格分开：前者是「载体没了」，后者是
    「载体在但用错了定位路径」。合并成一个类型后，「用户删掉整列 UUID」会被报成锚点
    误用，而真正的锚点误用分支不可分辨（Task 17 实测）。
    """

    error_code = "excel_extract_forbidden_sheet_anchor"


class ManagedRegionResolutionError(ExcelExtractError):
    """受管区域（Table ref / sheet part / 列跨度）解析不出来或与契约不符。"""

    error_code = "excel_extract_managed_region_unresolvable"


class DynamicColumnBindingMissingError(ExcelExtractError):
    """契约声明了 `dynamic_columns` 但调用方没给 `{slot}_{seq}` → Excel 列的实测绑定。

    刻意 fail closed 而不是「按声明列右移一格猜」：猜错会把某公司的金额读到另一家
    名下，而 Requirement 6.4 明令不得用可改 label 或写死列数推 identity。
    """

    error_code = "excel_extract_dynamic_column_binding_missing"


class IdentityRetentionError(ExcelExtractError):
    """运行时 identity inventory 与 representation 冻结的预期不符（Property 66）。"""

    error_code = "excel_extract_identity_not_retained"


class RoundtripEquivalenceError(ExcelExtractError):
    """反读出的受管 projection 与期望 projection 不类型化等值（Property 29 / AC 8.11）。"""

    error_code = "excel_extract_roundtrip_not_equivalent"


class FormulaRegionDriftError(ExcelExtractError):
    """公式 / auto-source 受保护区域被改动（AC 6.6 / Property 24 的 verifier 侧）。"""

    error_code = "excel_extract_formula_region_drift"


class VerificationNotPassedError(ExcelExtractError):
    """三个 verifier 未全过就要求交 commit（AC 8.11：不得推进任何指针）。"""

    error_code = "excel_extract_verification_not_passed"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 行身份：空 UUID 三分类 / 确定性 mint / 扫描结果
# ═══════════════════════════════════════════════════════════════════════════


class EmptyRowIdentityDisposition(str, Enum):
    """Requirement 6.15 对「OO 内新增动态行的空 UUID」的三种 contract 处置。"""

    #: 契约声明了行身份且删除走 tombstone ⇒ 删除被追踪，可安全分配新 ID。
    assign_new_id = "assign_new_id"
    #: 契约声明了行身份但删除策略是 reject ⇒ 该表不接受结构编辑，落结构冲突。
    structural_conflict = "structural_conflict"
    #: 契约没声明行身份（静态表）⇒ 出现空 UUID 本身就是非法 structural edit，拒绝。
    reject = "reject"


def classify_empty_row_identity(table: TableSpec) -> EmptyRowIdentityDisposition:
    """按 **contract** 判定空 row UUID 的处置，不按「看起来合理」猜。

    判据只用契约已有的两个字段（`row_identity` / `delete_policy`），不新增 schema：

    * 有 `row_identity` + `delete_policy=tombstone` → :attr:`assign_new_id`
      （tombstone 意味着删除被登记，新 ID 不可能复用已删 UUID）；
    * 有 `row_identity` + `delete_policy=reject` → :attr:`structural_conflict`
      （该表明确拒绝行级结构变更，交人工裁决）；
    * 无 `row_identity`（静态表）→ :attr:`reject`。

    三条互不重叠且都由真实契约变体触发，因此都可达、都能被变异 falsify。
    """
    if not table.has_dynamic_rows:
        return EmptyRowIdentityDisposition.reject
    if table.delete_policy is None:
        # 契约校验器的 CS-14 已强制「动态行表必须声明 delete_policy」，所以在合法契约上
        # 走不到这里 —— 走到了说明上游被绕过（手工构造的 `TableSpec`）。
        #
        # 🔴 这里**抛**而不是「保守返回 reject」：返回 reject 会让它与上一条
        # `not has_dynamic_rows` 在合法契约上完全等价 ⇒ 把 `has_dynamic_rows` 判据删掉
        # 行为不变 ⇒ 它的变异恒 GREEN（实测 M07 就是这么绿的）。抛异常让两条判据可分辨。
        raise ExcelExtractError(
            f"契约表 {table.table_key!r} 声明了 row_identity 却没有 delete_policy —— "
            "契约校验器的 CS-14 本应拦住；空 row UUID 的处置不得留给运行时猜测"
            "（Requirement 6.9 / 6.15）"
        )
    if table.delete_policy.value == "tombstone":
        return EmptyRowIdentityDisposition.assign_new_id
    return EmptyRowIdentityDisposition.structural_conflict


def mint_row_identity(
    *, table_key: str, artifact_sha256: str, excel_row: int, taken: Iterable[str]
) -> str:
    """为 OO 新增行分配**确定性**新 row identity，且永不与既有/已删 UUID 相同。

    确定性（同一 artifact + 同一行恒得同一 ID）是刻意的：同一个 operation 被 retry 时
    必须得到相同的 projection，否则「重试产生不同结果」这类最难查的问题就出现了。
    盐随碰撞次数递增，所以即使 12 位前缀撞上 `taken`（含 tombstone 清册）也能收敛。
    """
    blocked = {str(item) for item in taken}
    for salt in range(64):
        seed = f"{table_key}|{artifact_sha256}|{excel_row}|{salt}".encode("utf-8")
        candidate = MINTED_ROW_IDENTITY_PREFIX + hashlib.sha256(seed).hexdigest()[:12]
        if candidate not in blocked:
            return candidate
    raise ExcelExtractError(
        f"为 {table_key} 第 {excel_row} 行分配 row identity 连续 64 次撞上已占用集合"
        f"（{len(blocked)} 项）—— 不得复用已删除 UUID，也不得放弃分配"
    )


@dataclass(frozen=True)
class RowIdentityScan:
    """一张受管表的行身份扫描结果。**永不含数组下标**（Requirement 6.5 / Property 23）。"""

    table_key: str
    sheet_name: str
    uuid_column: str
    #: Excel 行号 → row identity（含 minted）。顺序按行号，只用于定位，不作身份。
    row_identity_by_row: Mapping[int, str]
    #: Excel 行号 → minted identity（`row_identity_by_row` 的子集）。
    minted_by_row: Mapping[int, str]
    #: 原本为空、且按契约判为 `structural_conflict` / `reject` 的行号。
    empty_rows: tuple[int, ...]
    #: row identity → 它出现的全部 Excel 行号（长度 >1 即重复）。
    rows_by_identity: Mapping[str, tuple[int, ...]]
    #: 命中冻结 tombstone 清册的 identity。
    reused_tombstones: tuple[str, ...]
    disposition: EmptyRowIdentityDisposition

    @property
    def duplicate_identities(self) -> tuple[str, ...]:
        return tuple(
            sorted(key for key, rows in self.rows_by_identity.items() if len(rows) > 1)
        )

    @property
    def ordered_identities(self) -> tuple[str, ...]:
        """按 Excel 行号排出的 identity 序列（`Projection.row_keys` 用）。

        重复 identity 只保留首次出现，避免 `row_keys` 里出现重复键。
        """
        seen: list[str] = []
        for _, identity in sorted(self.row_identity_by_row.items()):
            if identity not in seen:
                seen.append(identity)
        return tuple(seen)


def _scan_row_identities(
    *,
    table: TableSpec,
    sheet_name: str,
    uuid_column: str,
    raw_by_row: Mapping[int, str],
    artifact_sha256: str,
    tombstoned: Sequence[str],
) -> RowIdentityScan:
    """把「Excel 行号 → UUID 列原始值」投影成 :class:`RowIdentityScan`。

    空值按 :func:`classify_empty_row_identity` 处置；非空值按原值保留（**不 strip 成
    另一个值**、不按位置补齐）。已删除 UUID 的复现独立记录。
    """
    disposition = classify_empty_row_identity(table)
    tombstone_set = {str(item) for item in tombstoned}
    identity_by_row: dict[int, str] = {}
    minted: dict[int, str] = {}
    empty_rows: list[int] = []

    taken = {value for value in raw_by_row.values() if value} | tombstone_set
    for row in sorted(raw_by_row):
        value = raw_by_row[row]
        if value:
            identity_by_row[row] = value
            continue
        if disposition is EmptyRowIdentityDisposition.assign_new_id:
            new_id = mint_row_identity(
                table_key=table.table_key,
                artifact_sha256=artifact_sha256,
                excel_row=row,
                taken=taken,
            )
            taken.add(new_id)
            identity_by_row[row] = new_id
            minted[row] = new_id
        else:
            empty_rows.append(row)

    rows_by_identity: dict[str, list[int]] = {}
    for row, identity in sorted(identity_by_row.items()):
        rows_by_identity.setdefault(identity, []).append(row)

    reused = tuple(sorted(set(identity_by_row.values()) & tombstone_set))
    return RowIdentityScan(
        table_key=table.table_key,
        sheet_name=sheet_name,
        uuid_column=uuid_column,
        row_identity_by_row=dict(sorted(identity_by_row.items())),
        minted_by_row=dict(sorted(minted.items())),
        empty_rows=tuple(empty_rows),
        rows_by_identity={k: tuple(v) for k, v in sorted(rows_by_identity.items())},
        reused_tombstones=reused,
        disposition=disposition,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 受管区域绑定与解析（只走 excel_table_sheet_association）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ExcelIdentityBinding:
    """representation 固定下来的 Excel identity 绑定。

    这些值属于**表示层身份**（写在 `_GT_SYNC` runtime binding 与 instrumentation
    definition 里），不是语义契约的一部分，所以不放进 `SyncContract`。调用方从
    application/representation 冻结的 bundle 取出后原样传进来 —— 本模块不去 registry
    现查，也不接受「留空就按当前 alias 取」。
    """

    #: Excel Table displayName（唯一通过探针的区域边界锚点）。
    table_name: str
    #: 隐藏 row UUID 列列标。
    uuid_column: str
    #: 受管表在契约里的 `table_key`。绑定与契约表一一对应。
    table_key: str
    metadata_sheet: str = GT_SYNC_SHEET_NAME
    defined_name_prefix: str = "GT_"
    #: 该 entry 已 tombstone 的 row identity 清册（Requirement 6.15：不得复用）。
    tombstoned_row_keys: tuple[str, ...] = ()
    #: `table_key` → (`{slot}_{seq}` → Excel 列标) 的实测绑定。契约声明 dynamic_columns
    #: 的表必须给，否则 :class:`DynamicColumnBindingMissingError`。
    dynamic_column_columns: Mapping[str, Mapping[str, str]] = dataclass_field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        for name, value in (
            ("table_name", self.table_name),
            ("uuid_column", self.uuid_column),
            ("table_key", self.table_key),
            ("metadata_sheet", self.metadata_sheet),
        ):
            if not str(value or "").strip():
                raise ManagedRegionResolutionError(
                    f"ExcelIdentityBinding.{name} 不得为空 —— frozen identity 必须显式"
                )
        try:
            column_index_from_string(self.uuid_column)
        except ValueError as exc:
            raise ManagedRegionResolutionError(
                f"ExcelIdentityBinding.uuid_column 形态非法: {self.uuid_column!r}"
            ) from exc


@dataclass(frozen=True)
class ManagedRegion:
    """受管矩形区域 + 它所在的 sheet part。全部由 Table 关联求得，不含展示名判据。"""

    table_key: str
    table_name: str
    sheet_name: str
    sheet_part: str
    table_ref: str
    first_row: int
    last_row: int
    first_column: str
    last_column: str
    uuid_column: str

    @property
    def row_span(self) -> range:
        return range(self.first_row, self.last_row + 1)

    def contains_column(self, column: str) -> bool:
        return (
            column_index_from_string(self.first_column)
            <= column_index_from_string(column)
            <= column_index_from_string(self.last_column)
        )


def _sheet_part_map(zf: zipfile.ZipFile) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(sheets, defined_names)` —— 复用 `excel_structure_fingerprint` 的同一份解析。

    不用 openpyxl：这里只要磁盘上的原始 sheet/rel/definedName 事实，openpyxl 会丢属性。
    也不在本模块抄一份 XML 解析 —— 抄一份就是第二真源。
    """
    return parse_workbook_xml(zf)


def resolve_managed_region(
    zf: zipfile.ZipFile, *, contract: SyncContract, binding: ExcelIdentityBinding
) -> ManagedRegion:
    """由 **Excel Table ↔ sheet 关联**求受管区域；命中 0 或 >1 个同名 Table 都 fail closed。

    * 0 个 → :class:`IdentityCarrierMissingError`（区域边界锚点没了，禁止按中文表头猜）；
    * >1 个 → :class:`ManagedRegionResolutionError`（同一 displayName 落在多张 sheet 上，
      连「哪一份是受管区域」都无法确定；上游 `identity_inventory` 用 `next(...)` 取第一个
      是 fail-open，本模块不复制那个行为）。
    """
    sheets, _ = _sheet_part_map(zf)
    tables = parse_tables(zf, sheets)
    matched = [
        t
        for t in tables
        if binding.table_name in (t.get("name"), t.get("display_name"))
    ]
    if not matched:
        raise IdentityCarrierMissingError(
            f"Excel Table {binding.table_name!r} 反读不到（实测 Table: "
            f"{[t.get('display_name') for t in tables]}）—— 它是 sheet 改名后唯一可用的"
            "区域边界锚点，缺它即无锚点可用，extract 必须 fail closed"
            "（Requirement 6.20）"
        )
    if len(matched) > 1:
        raise ManagedRegionResolutionError(
            f"Excel Table {binding.table_name!r} 在 {len(matched)} 张 sheet 上都存在"
            f"（{[t.get('sheet') for t in matched]}）—— 受管区域不唯一，禁止取第一个继续"
        )
    table = matched[0]
    ref = str(table.get("ref") or "")
    if not ref:
        raise ManagedRegionResolutionError(
            f"Excel Table {binding.table_name!r} 没有 ref —— 受管行区间无法确定"
        )
    first_col, first_row, last_col, last_row = parse_a1_range(
        ref, location=f"table[{binding.table_name}].ref"
    )
    sheet_name = str(table.get("sheet") or "")
    sheet = next((s for s in sheets if s["name"] == sheet_name), None)
    if sheet is None:
        raise ManagedRegionResolutionError(
            f"Table {binding.table_name!r} 声明的 sheet {sheet_name!r} 不在 workbook 清册里"
        )
    sheet_part = normalise_part(sheet["rel_target"])
    if sheet_part not in zf.namelist():
        raise ManagedRegionResolutionError(
            f"受管 sheet part {sheet_part!r} 不在 zip 里"
        )
    if is_platform_metadata_sheet(sheet_name):
        raise ManagedRegionResolutionError(
            f"受管 Table 落在平台隐藏 metadata sheet {sheet_name!r} 上 —— "
            "隐藏元数据表永不得作为受管业务 sheet（Requirement 6.13 / 6.17）"
        )
    declared = _contract_table(contract, binding.table_key)
    if declared is None:
        raise ManagedRegionResolutionError(
            f"契约 {contract.contract_id} 没有 table_key={binding.table_key!r} —— "
            "identity 绑定与契约表必须一一对应"
        )
    region = ManagedRegion(
        table_key=binding.table_key,
        table_name=binding.table_name,
        sheet_name=sheet_name,
        sheet_part=sheet_part,
        table_ref=ref,
        first_row=first_row,
        last_row=last_row,
        first_column=first_col,
        last_column=last_col,
        uuid_column=binding.uuid_column,
    )
    if not region.contains_column(binding.uuid_column):
        raise ManagedRegionResolutionError(
            f"隐藏 UUID 列 {binding.uuid_column} 落在 Table ref {ref} 的列跨度之外 —— "
            "identity 列必须被 Table 覆盖，否则插删行时会与数据行错位"
        )
    return region


def _contract_table(contract: SyncContract, table_key: str) -> TableSpec | None:
    for sheet in contract.sheets:
        for table in sheet.tables:
            if table.table_key == table_key:
                return table
    return None


def managed_tables_of(
    contract: SyncContract, *, binding: ExcelIdentityBinding
) -> tuple[TableSpec, tuple[TableSpec, ...]]:
    """`(动态表, 静态表清册)` —— 都必须落在 `binding.table_key` 所在的那张 sheet 上。

    一份审定表契约通常是「一张动态行表 + 若干静态格块（TB 数据 / 差异 / 合计）」。动态表
    由 Excel Table 锚点定界，静态块靠**同一张 sheet** 上的固定行列定位（它们没有行身份，
    也就不需要 Table 锚点）。

    第二张**动态**表 fail closed：每张动态表都需要自己的 Table 锚点与 UUID 列绑定，而
    :class:`ExcelIdentityBinding` 只声明了一组 —— 静默沿用第一组会把 B 表的行读到 A 表的
    identity 上。
    """
    sheet = next(
        (
            s
            for s in contract.sheets
            for t in s.tables
            if t.table_key == binding.table_key
        ),
        None,
    )
    if sheet is None:
        raise ManagedRegionResolutionError(
            f"契约 {contract.contract_id} 没有 table_key={binding.table_key!r} —— "
            "identity 绑定与契约表必须一一对应"
        )
    dynamic = next(t for t in sheet.tables if t.table_key == binding.table_key)
    if not dynamic.has_dynamic_rows:
        raise ManagedRegionResolutionError(
            f"binding.table_key={binding.table_key!r} 指向的契约表没有 row_identity —— "
            "Excel Table 锚点只用于定界动态行区域"
        )
    statics: list[TableSpec] = []
    for table in sheet.tables:
        if table.table_key == dynamic.table_key:
            continue
        if table.has_dynamic_rows:
            raise ManagedRegionResolutionError(
                f"契约 {contract.contract_id} 的 sheet {sheet.sheet_key!r} 上还有第二张动态行表 "
                f"{table.table_key!r}，但 identity binding 只声明了一组 Table/UUID 列 —— "
                "沿用同一组会把它的行读到 "
                f"{dynamic.table_key!r} 的 identity 上"
            )
        statics.append(table)
    others = [
        t.table_key
        for s in contract.sheets
        if s.sheet_key != sheet.sheet_key
        for t in s.tables
    ]
    if others:
        raise ManagedRegionResolutionError(
            f"契约 {contract.contract_id} 在受管 sheet {sheet.sheet_key!r} 之外还声明了表 "
            f"{sorted(others)} —— 一次 extract 只覆盖一张 sheet 的受管区域，"
            "跨 sheet 必须各自有 Table 锚点与绑定，不得让一次反读静默漏掉它们"
        )
    return dynamic, tuple(statics)





# ═══════════════════════════════════════════════════════════════════════════
# 4. 运行时 identity inventory 与保留门（Requirement 6.15/6.16/6.20 · Property 66）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RuntimeIdentityInventory:
    """extract 当次从 artifact 反读出的 identity 清册。

    与 Task 36 的 :class:`EntryIdentityInventory`（representation 冻结的**预期**）同构，
    :func:`assert_identity_inventory_retained` 逐项比对二者 —— 那就是 Property 66 在
    engine 侧的判据：任一载体缺失即阻断 engine gate。
    """

    hidden_sheet_present: bool
    hidden_sheet_is_hidden: bool
    excluded_from_business_enumeration: bool
    defined_names: tuple[str, ...]
    table_present: bool
    table_ref: str
    table_sheet: str
    resolved_sheet_by: str | None
    uuid_column: str
    uuid_column_hidden: bool
    #: Excel 行号（字符串）→ row identity。**与 Task 36
    #: `EntryIdentityInventory.row_uuids` 同向**（行号在键）—— 反向存会让两侧 digest
    #: 永远不可能相等，比对退化成恒不通过。
    row_uuids: Mapping[str, str]
    duplicate_row_uuids: tuple[str, ...]
    empty_row_uuids: tuple[str, ...]
    business_sheets: tuple[str, ...]

    @property
    def digest_input(self) -> Mapping[str, Any]:
        """与 Task 36 `EntryIdentityInventory.inventory_digest_input` **同构**。

        同构不是巧合：representation 上记的 `identity_inventory_sha256` 是用那一份算的，
        运行时若换一种结构算 digest，两边永远不可能相等 ⇒ 比对退化成恒不通过。
        """
        return {
            "defined_names": sorted(self.defined_names),
            "row_uuids": dict(sorted(self.row_uuids.items())),
            "table_ref": self.table_ref,
        }

    @property
    def inventory_digest(self) -> str:
        return canonical_digest(self.digest_input)

    @property
    def identities(self) -> frozenset[str]:
        return frozenset(self.row_uuids.values())


def _hidden_columns_of(zf: zipfile.ZipFile, part: str, *, limits: SyncLimits) -> frozenset[str]:
    """从 sheet part 的 `<cols>` 块读被隐藏的列（有界流式，不建 DOM）。

    `<cols>` 在 `<sheetData>` **之前**，因此按块读到 `<sheetData` 就停 —— 对 100000 行的
    sheet 也只读前几十 KB。读不到 `<cols>` 时返回空集（=「没有隐藏列」），调用方据此
    对「UUID 列未隐藏」fail closed；这条方向是安全的（缺信息 ⇒ 判不通过）。
    """
    prefix = bytearray()
    with zf.open(part, "r") as src:
        while len(prefix) < limits.chunk_bytes * 8:
            chunk = src.read(limits.chunk_bytes)
            if not chunk:
                break
            prefix.extend(chunk)
            if b"<sheetData" in prefix:
                break
    text = prefix.decode("utf-8", errors="replace")
    head = text.split("<sheetData", 1)[0]
    hidden: set[str] = set()
    for element in _COL_ELEMENT_RE.finditer(head):
        attrs = {
            m.group("key"): m.group("value")
            for m in _COL_ATTR_RE.finditer(element.group(0))
        }
        if attrs.get("hidden") not in ("1", "true"):
            continue
        try:
            low = int(attrs["min"])
            high = int(attrs["max"])
        except (KeyError, ValueError):
            continue
        for index in range(low, high + 1):
            hidden.add(get_column_letter(index))
    return frozenset(hidden)


def read_runtime_identity_inventory(
    zf: zipfile.ZipFile,
    *,
    region: ManagedRegion,
    binding: ExcelIdentityBinding,
    raw_uuid_by_row: Mapping[int, str],
    limits: SyncLimits,
) -> RuntimeIdentityInventory:
    """反读三类载体的运行时清册。

    ``resolved_sheet_by`` 恒为 :data:`TABLE_SHEET_ANCHOR` 或 ``None``：本函数结构上
    只有 Table 关联一条求解路径（`region` 已由 :func:`resolve_managed_region` 求出），
    于是「用了被证伪的锚点」在这里**构造上不可能** —— 判据由
    :func:`assert_identity_carriers_usable` 对任意来源的 inventory 施加，那样两条分支
    都可达。
    """
    sheets, defined_names = _sheet_part_map(zf)
    meta = next((s for s in sheets if s["name"] == binding.metadata_sheet), None)
    visible = [s["name"] for s in sheets if s["state"] == "visible"]
    business = tuple(name for name in visible if not is_platform_metadata_sheet(name))
    names = tuple(
        sorted(
            d["name"]
            for d in defined_names
            if str(d["name"]).startswith(binding.defined_name_prefix)
        )
    )
    hidden_cols = _hidden_columns_of(zf, region.sheet_part, limits=limits)
    non_empty = {row: value for row, value in raw_uuid_by_row.items() if value}
    values = list(non_empty.values())
    return RuntimeIdentityInventory(
        hidden_sheet_present=meta is not None,
        hidden_sheet_is_hidden=bool(meta and meta["state"] in ("hidden", "veryHidden")),
        excluded_from_business_enumeration=binding.metadata_sheet not in business,
        defined_names=names,
        table_present=True,
        table_ref=region.table_ref,
        table_sheet=region.sheet_name,
        resolved_sheet_by=TABLE_SHEET_ANCHOR if non_empty else None,
        uuid_column=region.uuid_column,
        uuid_column_hidden=region.uuid_column in hidden_cols,
        row_uuids={str(row): value for row, value in sorted(non_empty.items())},
        duplicate_row_uuids=tuple(
            sorted({v for v in values if values.count(v) > 1})
        ),
        empty_row_uuids=tuple(
            str(row) for row in sorted(raw_uuid_by_row) if not raw_uuid_by_row[row]
        ),
        business_sheets=business,
    )


def assert_identity_carriers_usable(
    inventory: RuntimeIdentityInventory, *, contract: SyncContract, entry_id: str
) -> ExtractCarrierTier:
    """运行时载体准入门，返回 extract 实际用的载体层级（Requirement 6.20）。

    🔴 判定顺序不可交换，理由与 Task 17 `read_back_identity` 同源：

    1. **载体缺失优先**（隐藏 metadata sheet / defined name / Table / UUID 列）——
       这是 Requirement 6.15 的「用户删除 identity 列 ⇒ 拒绝」形态；
    2. **再判锚点路径**：`resolved_sheet_by` 不是 Table 关联即
       :class:`ForbiddenSheetAnchorError`。

    反过来写时，「整列 UUID 被删」（`resolved_sheet_by is None`）会先撞上锚点判据，被报成
    「锚点用错」，于是真正的锚点误用分支不可分辨、它的变异恒 GREEN。
    """
    where = f"entry {entry_id}"
    if not inventory.hidden_sheet_present or not inventory.hidden_sheet_is_hidden:
        raise IdentityCarrierMissingError(
            f"{where}: 隐藏 metadata sheet 反读失败（present="
            f"{inventory.hidden_sheet_present} is_hidden={inventory.hidden_sheet_is_hidden}）"
            " —— instrumented identity 载体缺失，extract fail closed"
        )
    if not inventory.excluded_from_business_enumeration:
        raise IdentityCarrierMissingError(
            f"{where}: 隐藏 metadata sheet 未被业务 sheet 枚举排除（Requirement 6.17）"
        )
    if not inventory.defined_names:
        raise IdentityCarrierMissingError(
            f"{where}: 一个 `{'GT_'}` defined name 都没反读到 —— 区域锚点缺失"
        )
    if not inventory.table_present or not inventory.table_ref:
        raise IdentityCarrierMissingError(
            f"{where}: Excel Table 反读不到（table_ref={inventory.table_ref!r}）"
        )
    dynamic_tables = [
        (sheet.sheet_key, table.table_key)
        for sheet in contract.sheets
        for table in sheet.tables
        if table.has_dynamic_rows
    ]
    if dynamic_tables and inventory.resolved_sheet_by is None:
        first_sheet, first_table = dynamic_tables[0]
        raise IdentityCarrierMissingError(
            f"{where}: 契约声明动态行的首张表 sheet={first_sheet!r} table={first_table!r} "
            "一个 row identity 都没反读到 —— 对应 Requirement 6.15 的「用户删除 identity "
            "列」形态，contract 处置为拒绝，不得按中文表头或位置猜（Requirement 6.20）"
        )
    if (
        inventory.resolved_sheet_by is not None
        and inventory.resolved_sheet_by != TABLE_SHEET_ANCHOR
    ):
        raise ForbiddenSheetAnchorError(
            f"{where}: UUID 列的 sheet 由 {inventory.resolved_sheet_by!r} 解析 —— "
            f"生产反读只能走 {TABLE_SHEET_ANCHOR}；"
            f"{sorted(DISPROVED_SHEET_ANCHORS)} 已被 Task 5 真实 OO 9.4 探针证伪"
        )
    if dynamic_tables and not inventory.uuid_column_hidden:
        raise IdentityCarrierMissingError(
            f"{where}: row UUID 列 {inventory.uuid_column} 未隐藏 —— 隐藏 identity 列"
            "一旦可见就会被审计师当业务列编辑"
        )
    assert_metadata_sheet_excluded(inventory.business_sheets, where=where)
    return (
        ExtractCarrierTier.instrumented_identity
        if inventory.resolved_sheet_by == TABLE_SHEET_ANCHOR
        else ExtractCarrierTier.native_structural_anchor
    )


def _column_span_of(table_ref: str, *, where: str) -> tuple[str, str]:
    first_col, _, last_col, _ = parse_a1_range(table_ref, location=where)
    return (first_col, last_col)


#: :func:`assert_identity_inventory_retained` 逐条比对的 `EntryIdentityInventory` 字段。
#:
#: 与 :data:`RETENTION_EXEMPT_FIELDS` 的并集**必须**等于 `EntryIdentityInventory` 的全部
#: 字段 —— 守卫据此断言。这样往那个 dataclass 加字段时必须显式裁决「它参不参与保留判据」，
#: 而不是悄悄漏掉一项（「逐条清单漏项」是本模块唯一可能的漏检形态；用一个总 digest 兜底
#: 在**子集语义**下做不到：`expected ⊆ observed` 无法表达成两个 digest 相等，硬写出来
#: 就是与逐条判据同义反复的自证式判据）。
RETENTION_CHECKED_FIELDS: Final[tuple[str, ...]] = (
    "defined_names",
    "table_present",
    "table_ref",
    "row_uuids",
    "hidden_sheet_present",
)

#: 刻意不参与保留判据的字段，每条都写明理由。
RETENTION_EXEMPT_FIELDS: Final[Mapping[str, str]] = {
    "hidden_sheet_is_hidden": (
        "运行时准入门 assert_identity_carriers_usable 已无条件要求它为真；"
        "在保留门里重复一遍会让两处判据互为遮蔽"
    ),
    "excluded_from_business_enumeration": (
        "同上，属运行时准入门；隐藏 metadata sheet 是否被业务枚举排除与「载体有没有丢」无关"
    ),
    "resolved_sheet_by": "属锚点路径判据（ForbiddenSheetAnchorError），不是载体保留",
    "uuid_column_hidden": (
        "同上，属运行时准入门；列是否隐藏是「能不能用」而不是「有没有丢」"
    ),
    "empty_row_uuids": "OO 新增行必然产生空 UUID，是合法输入 ⇒ 走 anomaly 分类而非保留门",
    "duplicate_row_uuids": "复制行产生的重复 UUID 是合法输入 ⇒ 走 anomaly 分类",
}


def assert_identity_inventory_retained(
    *,
    expected: EntryIdentityInventory,
    observed: RuntimeIdentityInventory,
    entry_id: str,
) -> None:
    """Property 66：representation 冻结的 identity 预期在 OO 往返后必须仍然成立。

    判据语义是**子集**（`expected ⊆ observed`）而不是相等：OO 合法地插行、排序、复制行
    会新增 identity 并改变行号与 Table ref 的行区间，那些不是漂移 —— Property 23 要求的
    恰恰是「按 identity 而不是位置判定」。因此本门只判「有没有丢」与「列跨度有没有变」，
    行号与行区间一概不进判据；漏项风险由 :data:`RETENTION_CHECKED_FIELDS` /
    :data:`RETENTION_EXEMPT_FIELDS` 的并集守卫兜住。
    """
    where = f"entry {entry_id}"
    lost_names = sorted(set(expected.defined_names) - set(observed.defined_names))
    if lost_names:
        raise IdentityRetentionError(
            f"{where}: OO 往返后丢失 defined name {lost_names} —— identity 载体未保留，"
            "阻断 engine gate（Property 66）"
        )
    if expected.table_present and not observed.table_present:
        raise IdentityRetentionError(
            f"{where}: Excel Table 在 OO 往返后消失 —— 区域边界锚点没了"
        )
    expected_span = _column_span_of(expected.table_ref, where=f"{where}.frozen_table_ref")
    observed_span = _column_span_of(observed.table_ref, where=f"{where}.observed_table_ref")
    if expected_span != observed_span:
        raise IdentityRetentionError(
            f"{where}: Excel Table 列跨度由 {expected_span} 漂到 {observed_span} —— "
            "受管矩形的列边界变了，受管字段不可再按旧列解析"
            "（行区间随插删行变化属合法，不在此判）"
        )
    lost_rows = sorted(set(expected.row_uuids.values()) - observed.identities)
    if lost_rows:
        raise IdentityRetentionError(
            f"{where}: OO 往返后丢失 {len(lost_rows)} 个 row identity，首个 "
            f"{lost_rows[0]!r} —— 原行数据不得按位置串到新行（Property 23 / 66）"
        )
    if expected.hidden_sheet_present and not observed.hidden_sheet_present:
        raise IdentityRetentionError(
            f"{where}: 隐藏 metadata sheet 在 OO 往返后消失"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 流式预算与分块（Requirement 6.12 / 14.11 · Property 60）
# ═══════════════════════════════════════════════════════════════════════════


def rows_per_chunk(limits: SyncLimits) -> int:
    """单表分块的行数，由 `SyncLimits` **派生**而不是写死数字。

    ``peak_memory_budget_bytes // chunk_bytes`` 的语义是「峰值内存预算能装下多少个流式
    读取块」，用它当行块大小的含义是：一块行的驻留量与一次流式读取的驻留量同阶。改预算
    时两者一起动，不会出现「预算调小了但分块还是老样子」的第二真源。
    """
    return max(1, limits.peak_memory_budget_bytes // limits.chunk_bytes)


class StreamingProjectionBudget:
    """Requirement 14.11 的行/field 预算，**边读边判**。

    与 `ooxml_security.assert_projection_budget` 的分工：那一支是「拿到完整 payload 后
    统计」，用于 HTML store 侧的既有载荷；本类是 extract 侧的流式对偶 —— 100000 行的表
    等读完再统计时内存已经吃掉了，Requirement 14.11 要求的是「不得 OOM 或截断」。

    越界立即 `raise BudgetExceededError`（复用 Task 11 的异常与阈值，本类不含任何数字）。
    """

    __slots__ = ("_limits", "_field_count", "_rows")

    def __init__(self, limits: SyncLimits) -> None:
        self._limits = limits
        self._field_count = 0
        self._rows: dict[str, int] = {}

    @property
    def field_count(self) -> int:
        return self._field_count

    @property
    def table_row_counts(self) -> Mapping[str, int]:
        return dict(sorted(self._rows.items()))

    def add_row(self, table_key: str) -> None:
        self._rows[table_key] = self._rows.get(table_key, 0) + 1
        self._limits.assert_table_rows(self._rows[table_key], table_key=table_key)

    def add_field(self, count: int = 1) -> None:
        self._field_count += count
        self._limits.assert_projection_fields(self._field_count)


def _chunked(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


# ═══════════════════════════════════════════════════════════════════════════
# 6. 未管理区域 digest 与 verifier（Requirement 6.17 / 8.11）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class UnmanagedRegionDigest:
    """未管理区域的逐 aspect digest + 总 digest。"""

    aspects: Mapping[str, str]
    #: 每个 aspect 覆盖到的部件/单元格计数，用于证明「不是空集恒等」。
    coverage: Mapping[str, int]
    part_count: int

    def __post_init__(self) -> None:
        missing = [name for name in UNMANAGED_ASPECTS if name not in self.aspects]
        if missing:
            raise UnmanagedRegionDriftError(
                f"未管理区域 digest 缺 aspect {missing} —— 缺项等于那一类没被检查"
            )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema_version": "excel-unmanaged-region:v1",
                "aspects": dict(sorted(self.aspects.items())),
            }
        )


def _managed_coordinates(
    *,
    contract: SyncContract,
    region: ManagedRegion,
    binding: ExcelIdentityBinding,
    scan: RowIdentityScan | None,
) -> frozenset[str]:
    """受管单元格坐标集合（`列+行`）。未管理区域 = 受管 sheet 上**除此之外**的格。

    刻意按**单元格**而不是按行排除：按行排除时，同一行里一个未管理格被改动就看不见了。
    """
    coords: set[str] = set()
    dynamic, statics = managed_tables_of(contract, binding=binding)
    rows = sorted(scan.row_identity_by_row) if scan is not None else list(region.row_span)
    for table in (dynamic, *statics):
        for spec in table.fields:
            cell = spec.cell
            if cell is None:
                continue
            column = _resolve_field_column(
                spec, table=table, region=region, binding=binding
            )
            if cell.row_from == "row_identity":
                for row in rows:
                    coords.add(f"{column}{row}")
            elif cell.static_row is not None:
                coords.add(f"{column}{cell.static_row}")
    for row in region.row_span:
        coords.add(f"{region.uuid_column}{row}")
    for row in rows:
        coords.add(f"{region.uuid_column}{row}")
    return frozenset(coords)


def _iter_zip_chunks(zf: zipfile.ZipFile, name: str, *, limits: SyncLimits) -> Iterator[bytes]:
    with zf.open(name, "r") as src:
        while True:
            chunk = src.read(limits.chunk_bytes)
            if not chunk:
                return
            yield chunk


def _part_digest(zf: zipfile.ZipFile, name: str, *, limits: SyncLimits) -> str:
    digest = hashlib.sha256()
    for chunk in _iter_zip_chunks(zf, name, limits=limits):
        digest.update(chunk)
    return digest.hexdigest()


def _propagation_normalised_digest(
    zf: zipfile.ZipFile, name: str, *, plan: Any, limits: SyncLimits
) -> str:
    """引用侧 sheet 的 **propagation-aware** digest（Requirement 5.1）。

    把计划**声明**的传播条目逐条逆替换回改前口径后再算 digest。于是三条同时成立
    （与 `row_shift` 归一化同一条纪律）：

    * 实测传播 == 声明 ⇒ 逆归一化后与 before 侧逐字节相等 ⇒ 判等价；
    * 实测传播 != 声明 ⇒ 有条目找不到或有残留差异 ⇒ 仍判漂移；
    * 传播之外的任何改动（值 / 样式 / 别的公式）⇒ 逆替换碰不到它们 ⇒ 仍判漂移。

    🔴 归一化的**单一真源**是 N1 的 `normalise_propagated_part` —— 这里不重写一份
    逆替换逻辑。抄第二份必然与执行侧漂移。
    """
    from app.services.workpaper_sync.excel_workbook_row_change import (
        normalise_propagated_part,
    )

    raw = b"".join(_iter_zip_chunks(zf, name, limits=limits))
    text = raw.decode("utf-8", "replace")
    normalised, _reverted = normalise_propagated_part(text, plan, part=name)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _sheet_parts(zf: zipfile.ZipFile) -> dict[str, str]:
    """`sheet 名 → sheet part`（含隐藏 sheet）。"""
    sheets, _ = _sheet_part_map(zf)
    out: dict[str, str] = {}
    for sheet in sheets:
        part = normalise_part(sheet["rel_target"])
        if part in zf.namelist():
            out[sheet["name"]] = part
    return out


#: `_GT_SYNC` 的一对 key/value 行（Task 17 `_gt_sync_sheet_xml` 写的 A 列 key、B 列 value）。
#:
#: 🔴 属性段必须**惰性**且不得假设 `r:id` 形如 `rId\d+` —— Task 17 的隐藏 sheet 关系 id 是
#: `rIdGTSYNC`。Task 38 首版在 materializer 里抄了一份 `r:id="(rId\d+)"` 的 sheet 定位，
#: 于是本 sheet 永远定位不到、读出空 dict，`GT_FOOTER_ROW` 被报成「缺冻结预期」——
#: 真因（sheet 定位失败）与表象（缺某个键）完全不同。故此处只经
#: :func:`_sheet_parts`（→ `parse_workbook_xml`）解析关系，不在任何模块里第二次手写。
_GT_PAIR_RE: Final[re.Pattern[str]] = re.compile(
    r'<c r="A(\d+)"(?:\s[^>]*?)?><is><t[^>]*>(?P<key>.*?)</t></is></c>'
    r'<c r="B\1"(?:\s[^>]*?)?><is><t[^>]*>(?P<value>.*?)</t></is></c>',
    re.S,
)


def read_runtime_binding_pairs(
    zf: zipfile.ZipFile, *, metadata_sheet: str = GT_SYNC_SHEET_NAME
) -> Mapping[str, str]:
    """读隐藏 metadata sheet 的 runtime binding `key → value`（Requirement 6.14）。

    这是「instrumentation/representation 冻结了什么」的**唯一**读侧入口。写侧真源是
    Task 17 的 :func:`~app.services.workpaper_sync.excel_instrumentation._gt_sync_sheet_xml`，
    读侧只有本函数 —— Task 38 需要 `GT_FOOTER_ROW` 来判 footer 有没有下移，但它不得在
    materializer 里抄第二份 XML 解析（抄一份就会出现「Task 17 改了载体形态、Task 38 还是
    老正则」的第二真源，且症状是静默读空）。

    三条定位失败**各抛自己的语义**而不是返回空 dict：返回空 dict 会让调用方把「sheet 没
    了 / 关系断了 / 部件缺失」全部误诊成「某个键没写」——那正是 fail-open 最贵的形态。
    """
    parts = _sheet_parts(zf)
    part = parts.get(metadata_sheet)
    if part is None:
        raise IdentityCarrierMissingError(
            f"隐藏 metadata sheet {metadata_sheet!r} 在 workbook 清册里定位不到"
            f"（实测 sheet: {sorted(parts)}）—— runtime binding 是 representation 身份的"
            "一部分，读不到即 fail closed"
        )
    xml = zf.read(part).decode("utf-8", errors="replace")
    pairs = {
        _xml_unescape(m.group("key")): _xml_unescape(m.group("value"))
        for m in _GT_PAIR_RE.finditer(xml)
    }
    if not pairs:
        raise IdentityCarrierMissingError(
            f"隐藏 metadata sheet {metadata_sheet!r}（部件 {part}）里一对 key/value 都读不到"
            " —— 载体形态与 Task 17 写侧不符，不得当成「这份文件没有冻结任何绑定」继续"
        )
    return pairs


def _xml_unescape(text: str) -> str:
    out = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return out.replace("&apos;", "'").replace("&amp;", "&")


#: 单个单元格坐标（`列+行`）。归一化只动行号，列标逐字保留。
_CELL_COORD_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<col>[A-Z]{1,3})(?P<row>\d+)$")


def _is_total_row(
    normalised_ref: str, row_shift: RowShiftPlan, total_rows: frozenset[int]
) -> bool:
    """该格（**已归一化**的坐标）是否落在契约声明「携带合计公式」的行上。

    `total_formula_rows` 是位移**前**口径，而归一化后的坐标也是位移前口径 ⇒ 直接比。
    """
    if not total_rows:
        return False
    found = _CELL_COORD_RE.match(normalised_ref)
    return found is not None and int(found.group("row")) in total_rows


def _normalise_cell_ref(
    ref: str, *, row_shift: RowShiftPlan, inserted: frozenset[int]
) -> str:
    """after 侧格坐标 → before 侧口径。新插入行返回空串（= 调用方跳过它）。"""
    found = _CELL_COORD_RE.match(ref)
    if found is None:
        return ref
    row = int(found.group("row"))
    if row in inserted:
        return ""
    return f"{found.group('col')}{row_shift.unshift(row)}"


def _normalise_structure_element(element: Any, *, row_shift: RowShiftPlan) -> None:
    """把一个结构块元素（含后代）里携带行号的属性/文本**就地**归一化回位移前口径。

    🔴 就地改的是 `ET.iterparse` 产出的**内存中**元素，随后只用于算 digest；
    artifact 字节一个都不动（Requirement 6.7 / Property 19）。

    「哪些属性/文本携带行号」不在本模块手写第二份 —— 三张表由
    `excel_row_shift.ROW_BEARING_STRUCTURES` **派生**，且该模块 import 期自检
    「每一项恰好落进一个归一化桶」。加新结构时不做决定就会打红。
    """

    def _remap(row: int) -> int:
        return row_shift.unshift(row)

    for node in element.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        for name in STRUCTURE_ROW_BEARING_ATTRS.get(tag, ()):
            value = node.attrib.get(name)
            if value:
                node.attrib[name] = remap_a1_rows(value, remap=_remap)
        for name in STRUCTURE_BARE_ROW_ATTRS.get(tag, ()):
            value = node.attrib.get(name)
            if value and value.isdigit():
                node.attrib[name] = str(_remap(int(value)))
        if tag in STRUCTURE_ROW_BEARING_TEXT_TAGS and node.text:
            node.text = remap_a1_rows(node.text, remap=_remap)


def _managed_sheet_cell_digest(
    zf: zipfile.ZipFile,
    part: str,
    *,
    managed: frozenset[str],
    row_shift: RowShiftPlan | None = None,
    total_formula_rows: Sequence[int] = (),
) -> tuple[str, int]:
    """受管 sheet 上**非受管**单元格的 digest（流式 iterparse，逐格喂 hash）。

    只保留 `<c>` 的 `r` / `t` / `s` 属性与 `<v>` / `<f>` 文本 —— 这些就是「这个格是什么」
    的全部；不建整棵 DOM，也不把 sheet 读进一个大字符串。

    ═══ `row_shift`：shift-aware 归一化（Requirement 6.1~6.5）═══

    非空时按 `plan.unshift` 把 after 侧的行号**反向归一化**回位移前口径再喂 hash，于是
    「与声明一致的插行」两侧 digest 相等。三条边界写成代码而不是注释：

    1. **新插入行的格整体跳过** —— 它们属受管区域（Requirement 6.5）。不跳过的后果不是
       「多算一点」：`plan.unshift` 在新行区间上是**恒等映射**，于是新行会与 before 侧
       同号的原始行**别名**，两侧拿同一个行号比不同的内容 ⇒ 必假红。
    2. **`managed` 判定用归一化后的坐标** —— `managed` 是 before 侧口径（由 before 侧的
       region/scan 算出），after 侧的坐标必须先归一化再查表。
    3. **只归一化行号**，`t` / `s` / `f` / `v` 四项照旧逐字喂 hash（Requirement 6.6）——
       归一化救不了「值被改了」「样式被改了」「公式被改了」。

    `row_shift=None` 时行为与本 spec 之前**逐字节相同**（纯增量，Requirement 6.4）。
    """
    digest = hashlib.sha256()
    counted = 0
    inserted = frozenset(row_shift.inserted_rows) if row_shift is not None else frozenset()
    total_rows = frozenset(int(row) for row in total_formula_rows)
    with zf.open(part, "r") as src:
        for event, element in ET.iterparse(src, events=("end",)):
            if not element.tag.endswith("}c") and element.tag != "c":
                continue
            ref = element.attrib.get("r", "")
            if ref and row_shift is not None:
                ref = _normalise_cell_ref(ref, row_shift=row_shift, inserted=inserted)
            if ref and ref not in managed:
                value = ""
                formula = ""
                for child in element:
                    tag = child.tag.rsplit("}", 1)[-1]
                    if tag == "v":
                        value = child.text or ""
                    elif tag == "f":
                        formula = child.text or ""
                    elif tag == "is":
                        value = "".join(node.text or "" for node in child.iter())
                if formula and row_shift is not None and _is_total_row(ref, row_shift, total_rows):
                    # 🔴 契约授权扩张的合计行：先还原扩张，再按 unshift 归一化行号。
                    #    只 unshift 还原不了扩张 —— 那正是扩张的语义（区间真的变大了）。
                    formula = unextend_total_formula(formula, plan=row_shift)
                elif formula and row_shift is not None:
                    # 🔴 公式文本里的 A1 **行号**同样要归一化（Requirement 6.2 说的是
                    #    「行号」，不是「`r` 属性」）。位移会把非受管格的公式一起带走 ——
                    #    K11 实测 `C28` 的 `C26-C27` → `C28-C29`、`H26` 的 `G26-D26` →
                    #    `G28-D28`。只归一化 `r` 的话这些格必判漂移，Property 17
                    #    （与计划一致的插行使全部 aspect 判等价）根本不可能成立。
                    #
                    #    归一化走 `excel_row_shift.remap_a1_rows` 这唯一入口 ⇒ 跨 sheet
                    #    引用、带数字函数名、字符串字面量三类不会被误改；列标也不动，
                    #    所以「把 B 列改成 C 列」照旧判漂移（Requirement 6.6）。
                    formula = remap_a1_rows(formula, remap=row_shift.unshift)
                digest.update(
                    "|".join(
                        [
                            ref,
                            element.attrib.get("t", ""),
                            element.attrib.get("s", ""),
                            formula,
                            value,
                        ]
                    ).encode("utf-8")
                )
                counted += 1
            element.clear()
    return digest.hexdigest(), counted


def _sheet_structure_digest(
    zf: zipfile.ZipFile, part: str, *, row_shift: RowShiftPlan | None = None
) -> tuple[str, int]:
    """受管 sheet 的结构块（merge / cols / 数据验证 / 条件格式 / 保护 / …）digest。

    `row_shift` 非空时，结构块里携带行号的属性与元素文本先按 `plan.unshift` 归一化再
    序列化（Requirement 6.2）。`None` 时行为逐字节不变。
    """
    digest = hashlib.sha256()
    found = 0
    with zf.open(part, "r") as src:
        for event, element in ET.iterparse(src, events=("end",)):
            tag = element.tag.rsplit("}", 1)[-1]
            if tag in _SHEET_STRUCTURE_BLOCKS:
                if row_shift is not None:
                    _normalise_structure_element(element, row_shift=row_shift)
                digest.update(tag.encode("utf-8"))
                digest.update(ET.tostring(element, encoding="utf-8"))
                found += 1
            if tag == "sheetData":
                # `<sheetData>` 之后只剩尾部元素，但它本身可能极大 —— 清掉以免驻留。
                element.clear()
    return digest.hexdigest(), found


def _shared_strings_prefix_digest(
    zf: zipfile.ZipFile, *, limit_count: int | None
) -> tuple[str, int]:
    """`xl/sharedStrings.xml` 的**前 N 个** `<si>` digest。

    追加新字符串（materialize 写入新文本时必然发生）不算未管理区域异动；改动**已有**条目
    会让既有单元格的显示值变化 ⇒ 必须打红。`limit_count=None` 表示取全部（before 侧）。
    """
    name = "xl/sharedStrings.xml"
    if name not in zf.namelist():
        return (canonical_digest({"shared_strings": None}), 0)
    digest = hashlib.sha256()
    seen = 0
    with zf.open(name, "r") as src:
        for event, element in ET.iterparse(src, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] != "si":
                continue
            if limit_count is not None and seen >= limit_count:
                element.clear()
                continue
            digest.update("".join(node.text or "" for node in element.iter()).encode("utf-8"))
            digest.update(b"\x00")
            seen += 1
            element.clear()
    return (digest.hexdigest(), seen)


def _classify_parts(
    zf: zipfile.ZipFile, *, region: ManagedRegion, metadata_sheet: str
) -> dict[str, list[str]]:
    """把 zip 全部条目分到 aspect 桶里。**最后一个桶是 catch-all**。

    分类顺序即优先级；`DERIVED_PARTS` 与「受管部件」先被摘掉，剩下的必须落进某个桶 ——
    :func:`unmanaged_region_digest` 会断言「已分类 + 已摘除 == 全部条目」，于是新出现的
    部件类别不可能悄悄逃过检查。
    """
    sheet_parts = _sheet_parts(zf)
    metadata_part = sheet_parts.get(metadata_sheet)
    managed_parts = {region.sheet_part}
    if metadata_part:
        managed_parts.add(metadata_part)

    buckets: dict[str, list[str]] = {name: [] for name in UNMANAGED_ASPECTS}
    other_sheet_parts = {
        part for name, part in sheet_parts.items() if part not in managed_parts
    }
    for name in sorted(zf.namelist()):
        if name.endswith("/"):
            continue
        if name in DERIVED_PARTS or name in managed_parts:
            continue
        if name.startswith("xl/tables/"):
            # Table part 是 identity 载体本体：插删行会合法改 ref ⇒ 由 identity 保留门
            # 判定，不进「逐字节不变」的未管理桶。
            continue
        if name == "xl/sharedStrings.xml":
            buckets["shared_strings_prefix"].append(name)
            continue
        if name in other_sheet_parts:
            buckets["other_sheet_parts"].append(name)
            continue
        if any(pattern.match(name) for pattern in PROTECTED_PART_PATTERNS.values()):
            buckets["protected_parts"].append(name)
            continue
        if name in ("xl/workbook.xml", "xl/styles.xml") or name.startswith("xl/theme/"):
            buckets["workbook_and_styles"].append(name)
            continue
        if name.endswith(".rels"):
            buckets["relationships"].append(name)
            continue
        buckets["other_parts"].append(name)
    return buckets


def unmanaged_region_digest(
    path: Path,
    *,
    contract: SyncContract,
    region: ManagedRegion,
    binding: ExcelIdentityBinding,
    scan: RowIdentityScan | None = None,
    limits: SyncLimits | None = None,
    shared_strings_limit: int | None = None,
    row_shift: RowShiftPlan | None = None,
    total_formula_rows: Sequence[int] = (),
    propagation: Any | None = None,
) -> UnmanagedRegionDigest:
    """算一份 artifact 的未管理区域 digest（供 rematerialize 前后比对）。

    `shared_strings_limit` 由 before 侧的 `<si>` 计数决定：after 侧只比前 N 个，于是
    「追加新字符串」合法、「改动已有条目」打红。

    `row_shift` 非空时对受管 sheet 的两个 aspect 做 **shift-aware 归一化**
    （逐格坐标 + 结构块里的行号）。它只能给 **after 侧**：before 侧本来就是位移前口径，
    两侧都归一化等于什么都没归一化。

    `propagation`（`WorkbookRowChangePlan`）非空时对 **`other_sheet_parts`** 桶里被
    传播触及的 part 做 **propagation-aware 归一化**：按计划**声明**的条目逐条逆替换回
    改前口径。同样只给 after 侧。

    🔴 没有这个参数时，工作簿级传播会让引用侧 sheet 的字节变化被判成漂移 —— 那不是
    「安全的保守」，而是让传播功能**永远无法通过验证**。而归一化必须按**声明**做，
    不能按观测：见 `normalise_propagated_part` 的 docstring。
    """
    lim = limits or load_limits()
    managed_coords = _managed_coordinates(
        contract=contract, region=region, binding=binding, scan=scan
    )
    with zipfile.ZipFile(path) as zf:
        buckets = _classify_parts(zf, region=region, metadata_sheet=binding.metadata_sheet)
        aspects: dict[str, str] = {}
        coverage: dict[str, int] = {}

        cell_digest, cell_count = _managed_sheet_cell_digest(
            zf,
            region.sheet_part,
            managed=managed_coords,
            row_shift=row_shift,
            total_formula_rows=total_formula_rows,
        )
        aspects["managed_sheet_unmanaged_cells"] = cell_digest
        coverage["managed_sheet_unmanaged_cells"] = cell_count

        struct_digest, struct_count = _sheet_structure_digest(
            zf, region.sheet_part, row_shift=row_shift
        )
        aspects["managed_sheet_structure"] = struct_digest
        coverage["managed_sheet_structure"] = struct_count

        shared_digest, shared_count = _shared_strings_prefix_digest(
            zf, limit_count=shared_strings_limit
        )
        aspects["shared_strings_prefix"] = shared_digest
        coverage["shared_strings_prefix"] = shared_count

        # 🔴 归一化必须覆盖计划点名的**每一个** part，不能只覆盖 `other_sheet_parts`。
        #
        #    首版只归一化了引用侧 sheet 那一桶，接到真实入口后 K11 端到端**当场打红**：
        #    definedNames 的传播改的是 `xl/workbook.xml`，它落在 **`workbook_and_styles`**
        #    桶里 ⇒ 那一桶仍按逐字节比对 ⇒ 判漂移。
        #
        #    这个缺口只有在真实入口上才暴露：N1 的 helper 判据只喂引用侧 sheet，
        #    永远碰不到 workbook.xml。
        propagated_parts = (
            {entry.part for entry in propagation.propagations}
            if propagation is not None
            else set()
        )
        for aspect in UNMANAGED_ASPECTS:
            if aspect in aspects:
                continue
            parts = buckets[aspect]
            aspects[aspect] = canonical_digest(
                {
                    part: (
                        _propagation_normalised_digest(
                            zf, part, plan=propagation, limits=lim
                        )
                        if part in propagated_parts
                        else _part_digest(zf, part, limits=lim)
                    )
                    for part in sorted(parts)
                }
            )
            coverage[aspect] = len(parts)

        classified = {p for parts in buckets.values() for p in parts}
        skipped = (
            set(DERIVED_PARTS)
            | {region.sheet_part}
            | {
                part
                for name, part in _sheet_parts(zf).items()
                if name == binding.metadata_sheet
            }
            | {n for n in zf.namelist() if n.startswith("xl/tables/")}
        )
        all_entries = {n for n in zf.namelist() if not n.endswith("/")}
        unaccounted = sorted(all_entries - classified - skipped)
        if unaccounted:
            raise UnmanagedRegionDriftError(
                f"未管理区域分类漏了 {len(unaccounted)} 个部件，首个 {unaccounted[0]!r} —— "
                "catch-all 桶必须兜住全部剩余条目，否则新部件类别会悄悄不被检查"
            )
        return UnmanagedRegionDigest(
            aspects=aspects, coverage=coverage, part_count=len(all_entries)
        )


def verify_unmanaged_regions(
    *,
    before: Path,
    after: Path,
    contract: SyncContract,
    region: ManagedRegion,
    binding: ExcelIdentityBinding,
    scan: RowIdentityScan | None = None,
    limits: SyncLimits | None = None,
    row_shift: RowShiftPlan | None = None,
    total_formula_rows: Sequence[int] = (),
    propagation: Any | None = None,
) -> UnmanagedRegionReport:
    """Task 38 的 `verify_unmanaged_regions` 的**共用实现**。

    返回 Task 13 的 :class:`UnmanagedRegionReport`（不另立一套报告类型），`equivalent=False`
    时必须给出首个差异位置（该类型的 `__post_init__` 会强制这一点）。

    ═══ `row_shift`：为什么这不是放宽判据（Requirement 6.9）═══

    归一化用的是 **materialize 之前冻结的声明值** `plan.count`，不是从 diff 事后推断出的
    观测值。于是三条同时成立：

    * 实测位移量 == 声明 ⇒ 归一化后行号对得上 ⇒ 判等价；
    * 实测位移量 != 声明 ⇒ 归一化后行号对不上 ⇒ 仍判漂移；
    * 非位移性改动（值 / 样式 / 公式 / 别的部件）⇒ 归一化碰不到它们 ⇒ 仍判漂移。

    事后推断位移量等于让被检查对象自己声明自己合法，那才是放宽（design.md 拒绝方案第 3 条）。
    """
    lim = limits or load_limits()
    base = unmanaged_region_digest(
        before,
        contract=contract,
        region=region,
        binding=binding,
        scan=scan,
        limits=lim,
    )
    target = unmanaged_region_digest(
        after,
        contract=contract,
        region=region,
        binding=binding,
        scan=scan,
        limits=lim,
        shared_strings_limit=base.coverage["shared_strings_prefix"],
        # 🔴 只给 after 侧：before 侧本来就是位移前口径。两侧都归一化 = 什么都没归一化。
        row_shift=row_shift,
        # 契约授权扩张的合计行 —— 同样是**写盘之前冻结的声明**，不是从 diff 观测的。
        total_formula_rows=total_formula_rows,
        # 工作簿级传播的**声明**条目 —— 同上，只给 after 侧。
        propagation=propagation,
    )
    for aspect in UNMANAGED_ASPECTS:
        if base.aspects[aspect] != target.aspects[aspect]:
            return UnmanagedRegionReport(
                equivalent=False,
                inspected_aspects=UNMANAGED_ASPECTS,
                first_difference=(
                    f"{aspect}: {base.aspects[aspect][:12]}… → "
                    f"{target.aspects[aspect][:12]}…"
                    f"（before 覆盖 {base.coverage[aspect]} 项，"
                    f"after 覆盖 {target.coverage[aspect]} 项）"
                ),
                details={
                    "before_digest": base.digest,
                    "after_digest": target.digest,
                    "before_coverage": dict(base.coverage),
                    "after_coverage": dict(target.coverage),
                    "managed_sheet": region.sheet_name,
                    "managed_table": region.table_name,
                },
            )
    return UnmanagedRegionReport(
        equivalent=True,
        inspected_aspects=UNMANAGED_ASPECTS,
        details={
            "digest": base.digest,
            "coverage": dict(base.coverage),
            "part_count": base.part_count,
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. extract（identity-aware，只读）
# ═══════════════════════════════════════════════════════════════════════════


class FormulaTamperKind(str, Enum):
    """受保护单元格（公式 / auto-source）被改动的形态。

    四类各有独立触发条件，因此都可达、都能被变异 falsify。它们**不替代** protected
    冲突：冲突由 Task 14 的 merge 从 projection 值差异生成（Property 24），本枚举只回答
    「为什么变了」，供 :func:`verify_formula_regions` 与 operation error detail 使用。
    """

    #: 公式被替换成字面量（用户直接往公式格里敲了个数）。
    formula_replaced_by_literal = "formula_replaced_by_literal"
    #: 公式文本被改写。
    formula_text_changed = "formula_text_changed"
    #: 原本是 auto-source 字面量的格被写进了公式。
    formula_added_to_literal_cell = "formula_added_to_literal_cell"
    #: auto-source 字面量被改成另一个字面量。
    literal_value_changed = "literal_value_changed"


@dataclass(frozen=True)
class ProtectedCellFinding:
    """一处受保护单元格的篡改观测。"""

    stable_field_key: str
    oo_location: str
    kind: FormulaTamperKind
    baseline: Any
    observed: Any
    row_key: str = ""
    table_key: str | None = None


@dataclass(frozen=True)
class ExtractStats:
    """本次 extract 的可审计观测量（进 operation error detail / evidence trace）。"""

    field_count: int
    table_row_counts: Mapping[str, int]
    chunk_count: int
    rows_per_chunk: int
    archive_bytes: int
    expanded_bytes: int
    carrier_tier: ExtractCarrierTier


@dataclass(frozen=True)
class ExcelExtractOutcome:
    """一次 extract 的全部产物。**纯数据** —— 不含任何写入面。"""

    projection: Projection
    anomalies: tuple[StructuralAnomaly, ...]
    protected_findings: tuple[ProtectedCellFinding, ...]
    identity_inventory: RuntimeIdentityInventory
    unmanaged: UnmanagedRegionDigest
    stats: ExtractStats
    region: ManagedRegion
    scan: RowIdentityScan
    #: stable key → 该受管格当前的**公式文本**。随 representation 持久化后，下一次 extract
    #: 把它当 `baseline_formulas` 传回来，于是「公式被改写成等值字面量」这类值比较看不见的
    #: 篡改也能被 :func:`verify_formula_regions` 抓到。
    formula_inventory: Mapping[str, str] = dataclass_field(default_factory=dict)
    sidecar_path: Path | None = None

    def merge_inputs(self) -> tuple[Projection, tuple[StructuralAnomaly, ...]]:
        """喂给 `merge.merge_projections(incoming=..., structural_anomalies=...)`。"""
        return (self.projection, self.anomalies)

    @property
    def minted_row_identities(self) -> Mapping[int, str]:
        return self.scan.minted_by_row

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.projection.contract_id,
            "field_count": self.stats.field_count,
            "table_row_counts": dict(self.stats.table_row_counts),
            "chunk_count": self.stats.chunk_count,
            "rows_per_chunk": self.stats.rows_per_chunk,
            "carrier_tier": self.stats.carrier_tier.value,
            "identity_inventory_sha256": self.identity_inventory.inventory_digest,
            "unmanaged_region_digest": self.unmanaged.digest,
            "unmanaged_region_coverage": dict(self.unmanaged.coverage),
            "formula_inventory_sha256": canonical_digest(
                {
                    "schema_version": "excel-formula-inventory:v1",
                    "formulas": dict(sorted(self.formula_inventory.items())),
                }
            ),
            "formula_inventory_size": len(self.formula_inventory),
            "anomalies": [
                {
                    "kind": a.kind.value,
                    "stable_field_key": a.stable_field_key,
                    "row_key": a.row_key,
                    "table_key": a.table_key,
                    "oo_location": a.oo_location,
                }
                for a in self.anomalies
            ],
            "protected_findings": [
                {
                    "stable_field_key": f.stable_field_key,
                    "kind": f.kind.value,
                    "oo_location": f.oo_location,
                }
                for f in self.protected_findings
            ],
            "minted_row_identities": dict(sorted(self.scan.minted_by_row.items())),
        }


def assert_engine_entry_definitions(definitions: FrozenEntryDefinitions) -> None:
    """engine 入口的 frozen 身份门（design §Extract 第 1 条）。

    三条判据**全部委派**给既有单一真源，本函数只负责「在 extract 入口真的跑一遍」：

    * `assert_bundle_usable` —— bundle 必须 approved、四 slot 齐全（candidate /
      unapproved 在这里就被拒）；
    * `assert_authority_model_contract_pairing` —— `projection_contract` 必须有 approved
      contract child，typed null marker 不得冒充；
    * `assert_contract_identity_frozen` —— contract canonical digest 必须等于 bundle 的
      contract slot digest，并顺带比对 template/instrumentation slot（alias 漂移）。

    委派而不是重写：重写一份会让任一侧被短路都不改变行为 ⇒ 变异检验判 GREEN。
    `bundle is None` 单独拒 —— 那意味着调用方绕过了 Task 36 的 loader 自己拼了一个
    `FrozenEntryDefinitions`。
    """
    if definitions.bundle is None:
        raise ExcelExtractError(
            f"entry {definitions.entry_id}: FrozenEntryDefinitions 没有 frozen definition "
            "bundle —— extract 只接受 Task 36 `ExcelEntryDefinitionLoader.load()` 的产物，"
            "不接受手工拼装的身份（否则 bundle/contract/authority 三向锁死全部落空）"
        )
    assert_bundle_usable(definitions.bundle, entry_id=definitions.entry_id)
    assert_authority_model_contract_pairing(
        authority_model=definitions.bundle.authority_model,
        contract=definitions.contract,
        bundle=definitions.bundle,
        entry_id=definitions.entry_id,
    )
    assert_contract_identity_frozen(
        contract=definitions.contract,
        bundle=definitions.bundle,
        entry_id=definitions.entry_id,
    )


def _instantiate(stable_key: str, row_identity: str) -> str:
    return stable_key.replace("{row_uuid}", row_identity)


def _classify_protected_tamper(
    *,
    stable_key: str,
    oo_location: str,
    observed_value: Any,
    observed_formula: str | None,
    baseline: Projection | None,
    baseline_formulas: Mapping[str, str] | None,
    value_type: ValueType,
    row_identity: str,
    table_key: str | None,
) -> ProtectedCellFinding | None:
    """受保护格的四类篡改分类。**公式层先判、值层后判**，四条互不重叠。

    公式层优先的理由：把 `=SUM(...)` 换成一个恰好等于计算结果的字面量时，值层看不出任何
    差异（这正是最容易被漏掉的形态）；反过来，公式文本没变而缓存值变了只可能是重算结果，
    那才该归到值层。两层都没有 baseline 时返回 `None`（不猜「原本是什么」）。
    """
    base_formula = (baseline_formulas or {}).get(stable_key)
    if baseline_formulas is not None:
        if base_formula and not observed_formula:
            return ProtectedCellFinding(
                stable_field_key=stable_key,
                oo_location=oo_location,
                kind=FormulaTamperKind.formula_replaced_by_literal,
                baseline=base_formula,
                observed=observed_value,
                row_key=row_identity,
                table_key=table_key,
            )
        if base_formula and observed_formula and base_formula != observed_formula:
            return ProtectedCellFinding(
                stable_field_key=stable_key,
                oo_location=oo_location,
                kind=FormulaTamperKind.formula_text_changed,
                baseline=base_formula,
                observed=observed_formula,
                row_key=row_identity,
                table_key=table_key,
            )
        if not base_formula and observed_formula:
            return ProtectedCellFinding(
                stable_field_key=stable_key,
                oo_location=oo_location,
                kind=FormulaTamperKind.formula_added_to_literal_cell,
                baseline=baseline.get(stable_key).value
                if baseline is not None and baseline.get(stable_key) is not None
                else None,
                observed=observed_formula,
                row_key=row_identity,
                table_key=table_key,
            )
    if baseline is None:
        return None
    before = baseline.get(stable_key)
    if before is None:
        return None
    if observed_formula and base_formula == observed_formula:
        # 公式文本未变 ⇒ 缓存值差异只是重算结果，不构成篡改。
        return None
    try:
        unchanged = normalize_value(before.value, value_type) == normalize_value(
            observed_value, value_type
        )
    except ValueNormalizationError:
        unchanged = before.value == observed_value
    if unchanged:
        return None
    return ProtectedCellFinding(
        stable_field_key=stable_key,
        oo_location=oo_location,
        kind=FormulaTamperKind.literal_value_changed,
        baseline=before.value,
        observed=observed_value,
        row_key=row_identity,
        table_key=table_key,
    )


def _resolve_field_column(
    spec: FieldSpec, *, table: TableSpec, region: ManagedRegion, binding: ExcelIdentityBinding
) -> str:
    """受管字段的 Excel 列。动态列必须有**实测绑定**，绝不按声明列右移猜。"""
    cell = spec.cell
    if cell is None:
        raise ManagedRegionResolutionError(
            f"xlsx 受管字段 {spec.stable_field_key!r} 缺 cell 声明 —— 契约校验器本应拦住"
        )
    if table.dynamic_columns is None or spec.column_key is None:
        return cell.column
    bound = binding.dynamic_column_columns.get(table.table_key)
    if not bound:
        raise DynamicColumnBindingMissingError(
            f"契约表 {table.table_key!r} 声明了 dynamic_columns，但 identity binding 未提供"
            "`{slot}_{seq}` → Excel 列的实测绑定 —— 按声明列右移猜会把某单位的金额读到"
            "另一家名下（Requirement 6.4）"
        )
    column = bound.get(spec.column_key)
    if not column:
        raise DynamicColumnBindingMissingError(
            f"契约表 {table.table_key!r} 的动态列 {spec.column_key!r} 没有实测列绑定"
            f"（已绑定 {sorted(bound)}）"
        )
    if not region.contains_column(column):
        raise ManagedRegionResolutionError(
            f"动态列 {spec.column_key!r} 绑定到 {column}，落在 Table ref "
            f"{region.table_ref} 的列跨度之外"
        )
    return column


def _read_cell_view(
    path: Path,
    *,
    sheet_name: str,
    columns: frozenset[str],
    rows: range,
    data_only: bool,
) -> dict[str, Any]:
    """一遍 `read_only` 流式读出需要的格。返回 `{坐标: 值}`（只含非空）。

    ``read_only=True`` 让 openpyxl 逐行流式解析而不建整表对象。两个视图各读一遍：

    * ``data_only=True`` → **缓存/计算值**。它才是 projection 的值（受保护格的值也是它），
      因为 Task 14 的三方 merge 要按 `value_type` 规范化后比较 —— 把公式文本当
      `amount` 值塞进去会让每个公式字段都变成 `type_normalization_failure`
      schema 冲突，protected 冲突（Property 24）永远不可达。
    * ``data_only=False`` → **公式文本**。它进独立的 formula inventory，供
      :func:`verify_formula_regions` 检测「公式被改写 / 被替换成恰好等于计算结果的字面量」
      这类值比较看不见的篡改。

    只读打开，不写任何字节。
    """
    import openpyxl

    wanted = {column_index_from_string(col) for col in columns}
    out: dict[str, Any] = {}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
    try:
        if sheet_name not in wb.sheetnames:
            raise IdentityCarrierMissingError(
                f"受管 sheet {sheet_name!r} 打不开（workbook 里有 {wb.sheetnames}）—— "
                "Table 关联指向的 sheet 必须存在"
            )
        ws = wb[sheet_name]
        min_col = min(wanted) if wanted else 1
        max_col = max(wanted) if wanted else 1
        for row_cells in ws.iter_rows(
            min_row=rows.start, max_row=rows.stop - 1, min_col=min_col, max_col=max_col
        ):
            # 🔴 `read_only=True` 下空格是 `EmptyCell`，**没有** `.row` / `.column` 属性。
            # 按位置推列（`min_col + 偏移`）、从任一实格取行号；全空行直接跳过。
            row_number = next(
                (getattr(c, "row", None) for c in row_cells if getattr(c, "row", None)),
                None,
            )
            if row_number is None:
                continue
            for offset, cell in enumerate(row_cells):
                column_index = min_col + offset
                if column_index not in wanted:
                    continue
                value = getattr(cell, "value", None)
                if value is None:
                    continue
                out[f"{get_column_letter(column_index)}{row_number}"] = value
    finally:
        wb.close()
    return out


def _needed_columns_and_rows(
    *,
    contract: SyncContract,
    region: ManagedRegion,
    binding: ExcelIdentityBinding,
) -> tuple[frozenset[str], range]:
    dynamic, statics = managed_tables_of(contract, binding=binding)
    columns = {region.uuid_column}
    first = region.first_row
    last = region.last_row
    for table in (dynamic, *statics):
        for spec in table.fields:
            columns.add(
                _resolve_field_column(spec, table=table, region=region, binding=binding)
            )
            if spec.cell is not None and spec.cell.static_row is not None:
                first = min(first, spec.cell.static_row)
                last = max(last, spec.cell.static_row)
    return frozenset(columns), range(first, last + 1)


def extract_projection(
    *,
    artifact: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    substrate_role: SubstrateRole | str,
    artifact_kind: ArtifactKind | str,
    artifact_state: ArtifactState | str,
    baseline: Projection | None = None,
    baseline_formulas: Mapping[str, str] | None = None,
    limits: SyncLimits | None = None,
    sidecar_path: Path | None = None,
) -> ExcelExtractOutcome:
    """按 representation 固定的 stable identity 反读受管字段。

    执行顺序即判据（不可交换）：

    1. **substrate 准入**（Task 13 `assert_substrate_usable`）—— quarantined incoming /
       upgrade candidate 在 engine 入口就拒；
    2. **OOXML 安全与容量门**（Task 11 `validate_ooxml_artifact`）—— ZIP magic / entry 名 /
       entry 数 / 压缩体积 / 流式展开量与压缩比，全部在任何解析之前；
    3. **受管区域**由 Excel Table ↔ sheet 关联求解（禁 `sheet_id` / 展示名）；
    4. **identity 扫描**（空 / 重复 / tombstone 复现分类）；
    5. **运行时载体准入 + 保留门**（Property 66，`definitions` 冻结的预期）；
    6. **逐块读受管字段**，行/field 预算边读边判（Property 60）；
    7. **未管理区域 digest**，供 rematerialize 反读比对。

    `baseline` / `baseline_formulas` 给了才计算受保护格的 tamper 分类：没有 baseline 时
    **不猜**「原本是什么」。两条分支都是真实调用点 —— HTML→OO 首次读当前 representation
    无 baseline，OO→HTML 读 incoming 时必然有 client-confirmed base 与它的 formula
    inventory（后者由上一次 extract 产出并随 representation 持久化）。
    """
    lim = limits or load_limits()
    contract = definitions.contract
    entry_id = definitions.entry_id

    assert_engine_entry_definitions(definitions)
    assert_substrate_usable(
        role=substrate_role, artifact_kind=artifact_kind, artifact_state=artifact_state
    )
    ooxml = validate_ooxml_artifact(artifact, document_type="xlsx", limits=lim)

    try:
        with zipfile.ZipFile(artifact) as zf:
            region = resolve_managed_region(zf, contract=contract, binding=binding)
            columns, rows = _needed_columns_and_rows(
                contract=contract, region=region, binding=binding
            )
    except FingerprintError as exc:
        # 窄类型转译：结构采集失败绝不降级成「本项目无此数据」。
        raise IdentityCarrierMissingError(
            f"entry {entry_id}: workbook 结构采集失败，无法定位受管区域: {exc}"
        ) from exc

    cells = _read_cell_view(
        artifact,
        sheet_name=region.sheet_name,
        columns=columns,
        rows=rows,
        data_only=True,
    )
    formula_cells = {
        coord: str(value)
        for coord, value in _read_cell_view(
            artifact,
            sheet_name=region.sheet_name,
            columns=columns,
            rows=rows,
            data_only=False,
        ).items()
        if isinstance(value, str) and value.startswith("=")
    }
    raw_uuid_by_row = {
        row: str(cells.get(f"{region.uuid_column}{row}") or "").strip()
        for row in region.row_span
    }
    dynamic_table, static_tables = managed_tables_of(contract, binding=binding)
    scan = _scan_row_identities(
        table=dynamic_table,
        sheet_name=region.sheet_name,
        uuid_column=region.uuid_column,
        raw_by_row=raw_uuid_by_row,
        artifact_sha256=_file_sha256(artifact, limits=lim),
        tombstoned=binding.tombstoned_row_keys,
    )

    with zipfile.ZipFile(artifact) as zf:
        inventory = read_runtime_identity_inventory(
            zf,
            region=region,
            binding=binding,
            raw_uuid_by_row=raw_uuid_by_row,
            limits=lim,
        )
    tier = assert_identity_carriers_usable(
        inventory, contract=contract, entry_id=entry_id
    )
    assert_identity_inventory_retained(
        expected=definitions.identity_inventory, observed=inventory, entry_id=entry_id
    )

    budget = StreamingProjectionBudget(lim)
    values: dict[str, FieldValue] = {}
    formula_inventory: dict[str, str] = {}
    anomalies: list[StructuralAnomaly] = []
    findings: list[ProtectedCellFinding] = []
    chunk_count = 0
    sidecar_writer = (
        _SidecarWriter(sidecar_path, contract=contract, region=region)
        if sidecar_path is not None
        else None
    )

    try:
        # ── 7.1 静态受管块（不按行展开）──────────────────────────────
        for static_table in static_tables:
            _collect_fields(
                specs=[
                    spec for spec in static_table.fields if spec.cell is not None
                ],
                row_identity="",
                excel_rows=(),
                cells=cells,
                formula_cells=formula_cells,
                table=static_table,
                region=region,
                binding=binding,
                values=values,
                formula_inventory=formula_inventory,
                anomalies=anomalies,
                findings=findings,
                baseline=baseline,
                baseline_formulas=baseline_formulas,
                budget=budget,
                sidecar=sidecar_writer,
            )

        # ── 7.2 行域字段按 identity 分块 ─────────────────────────────
        identities = scan.ordered_identities
        chunk_size = rows_per_chunk(lim)
        for chunk in _chunked(identities, chunk_size):
            chunk_count += 1
            for identity in chunk:
                budget.add_row(dynamic_table.table_key)
                _collect_fields(
                    specs=list(dynamic_table.fields),
                    row_identity=identity,
                    excel_rows=scan.rows_by_identity[identity],
                    cells=cells,
                    formula_cells=formula_cells,
                    table=dynamic_table,
                    region=region,
                    binding=binding,
                    values=values,
                    formula_inventory=formula_inventory,
                    anomalies=anomalies,
                    findings=findings,
                    baseline=baseline,
                    baseline_formulas=baseline_formulas,
                    budget=budget,
                    sidecar=sidecar_writer,
                )
        anomalies.extend(
            _identity_anomalies(
                scan=scan, table=dynamic_table, region=region, contract=contract
            )
        )
    except BaseException:
        # 🔴 越界/异常中止时删掉半成品 sidecar：留一个被截断的 gzip 在盘上，就是
        # Requirement 14.11 明令禁止的「静默截断」—— 下游会把它当完整 projection 读。
        if sidecar_writer is not None:
            sidecar_writer.close()
            sidecar_writer = None
            sidecar_path.unlink(missing_ok=True)  # type: ignore[union-attr]
        raise
    finally:
        if sidecar_writer is not None:
            sidecar_writer.close()

    projection = Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={dynamic_table.table_key: identities},
    )
    projection.assert_matches_contract(contract)

    unmanaged = unmanaged_region_digest(
        artifact,
        contract=contract,
        region=region,
        binding=binding,
        scan=scan,
        limits=lim,
    )
    return ExcelExtractOutcome(
        projection=projection,
        anomalies=tuple(anomalies),
        protected_findings=tuple(findings),
        identity_inventory=inventory,
        unmanaged=unmanaged,
        stats=ExtractStats(
            field_count=budget.field_count,
            table_row_counts=budget.table_row_counts,
            chunk_count=chunk_count,
            rows_per_chunk=chunk_size,
            archive_bytes=ooxml.archive_bytes,
            expanded_bytes=ooxml.expanded_bytes,
            carrier_tier=tier,
        ),
        region=region,
        scan=scan,
        formula_inventory=dict(sorted(formula_inventory.items())),
        sidecar_path=sidecar_path,
    )


def _file_sha256(path: Path, *, limits: SyncLimits) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(limits.chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _collect_fields(
    *,
    specs: Sequence[FieldSpec],
    row_identity: str,
    excel_rows: Sequence[int],
    cells: Mapping[str, Any],
    formula_cells: Mapping[str, str],
    table: TableSpec,
    region: ManagedRegion,
    binding: ExcelIdentityBinding,
    values: dict[str, FieldValue],
    formula_inventory: dict[str, str],
    anomalies: list[StructuralAnomaly],
    findings: list[ProtectedCellFinding],
    baseline: Projection | None,
    baseline_formulas: Mapping[str, str] | None,
    budget: StreamingProjectionBudget,
    sidecar: "_SidecarWriter | None",
) -> None:
    """把一组受管字段读进 projection，并就地分类结构/保护异常。

    行域字段的 `excel_rows` 可能有多个（复制行造成同 identity 落在多行）：这时逐位置取值，
    **值一致**只留一份、**值不一致**额外记 ``multi_location_divergence`` 并列出全部 OO 地址。
    这两条是不同的事实，故不合并成一条。
    """
    for spec in specs:
        column = _resolve_field_column(
            spec, table=table, region=region, binding=binding
        )
        stable_key = _instantiate(spec.stable_field_key, row_identity)
        if spec.row_scoped:
            coords = [f"{column}{row}" for row in excel_rows]
        else:
            cell = spec.cell
            assert cell is not None and cell.static_row is not None
            coords = [f"{column}{cell.static_row}"]
        observations = [(coord, cells.get(coord)) for coord in coords]
        present = [(coord, value) for coord, value in observations if value is not None]
        if not present:
            # 键缺失即 MISSING（Task 14 用键缺失区分「不存在」与「存在但为空」）。
            continue

        distinct = {_normalised_or_raw(value, spec.value_type) for _, value in present}
        if len(distinct) > 1:
            anomalies.append(
                StructuralAnomaly(
                    kind=SchemaAnomalyKind.multi_location_divergence,
                    stable_field_key=stable_key,
                    detail=(
                        f"同一 stable key 在 {len(present)} 个位置取到不同值 "
                        f"{[coord for coord, _ in present]} —— 连取哪一个都无法决定，"
                        "交人工裁决；不得按第一个位置静默胜出"
                    ),
                    row_key=row_identity,
                    table_key=table.table_key,
                    oo_location=f"{region.sheet_name}!{','.join(c for c, _ in present)}",
                    blocks_stable_keys=(stable_key,),
                )
            )
        coord, raw = present[0]
        oo_location = f"{region.sheet_name}!{coord}"
        observed_formula = formula_cells.get(coord)
        if observed_formula:
            formula_inventory[stable_key] = observed_formula

        try:
            normalize_value(raw, spec.value_type)
        except ValueNormalizationError as exc:
            anomalies.append(
                StructuralAnomaly(
                    kind=SchemaAnomalyKind.type_normalization_failure,
                    stable_field_key=stable_key,
                    detail=(
                        f"{oo_location} 的值 {raw!r} 无法按 value_type="
                        f"{spec.value_type.value} 规范化: {exc} —— 保留原值供裁决"
                    ),
                    row_key=row_identity,
                    table_key=table.table_key,
                    oo_location=oo_location,
                    blocks_stable_keys=(stable_key,),
                )
            )

        values[stable_key] = FieldValue(
            stable_key=stable_key,
            value=raw,
            value_type=spec.value_type,
            mode=spec.mode,
            row_key=row_identity or None,
        )
        budget.add_field()
        if sidecar is not None:
            sidecar.write_field(values[stable_key], oo_location=oo_location)

        if spec.is_protected:
            finding = _classify_protected_tamper(
                stable_key=stable_key,
                oo_location=oo_location,
                observed_value=raw,
                observed_formula=observed_formula,
                baseline=baseline,
                baseline_formulas=baseline_formulas,
                value_type=spec.value_type,
                row_identity=row_identity,
                table_key=table.table_key,
            )
            if finding is not None:
                findings.append(finding)


def _normalised_or_raw(value: Any, value_type: ValueType) -> Any:
    """比较用的键：能规范化就用规范化值，否则退回原值的字符串形态。

    退回**字符串**而不是原对象：`Decimal('1')` 与 `1` 在集合里是同一个元素，但两个无法
    规范化的不同对象可能都不可 hash（如 openpyxl 的 ArrayFormula），直接进集合会抛。
    """
    try:
        normalised = normalize_value(value, value_type)
    except ValueNormalizationError:
        return f"<raw:{value!r}>"
    try:
        hash(normalised)
    except TypeError:  # pragma: no cover - 规范化结果理应可 hash
        return f"<raw:{normalised!r}>"
    return normalised


def _identity_anomalies(
    *,
    scan: RowIdentityScan,
    table: TableSpec,
    region: ManagedRegion,
    contract: SyncContract,
) -> list[StructuralAnomaly]:
    """把行身份扫描结果翻成 :class:`StructuralAnomaly`（Requirement 6.15 三形态）。

    三类各有专属 `SchemaAnomalyKind`，且触发条件互不重叠：

    * 空 UUID 且契约不许分配新 ID → ``empty_row_identity``；
    * 同 UUID 落在 ≥2 行 → ``duplicate_row_identity``（值是否相同都算）；
    * UUID 命中 tombstone 清册 → ``reused_tombstoned_row_identity``。

    第一个受管字段的 stable key 用来给异常挂 locator（merge 侧要能在 contract 里解析），
    因此契约没有字段时直接抛而不是伪造一个 key。
    """
    anchors = [spec for spec in table.fields if spec.row_scoped] or list(table.fields)
    if not anchors:
        raise ManagedRegionResolutionError(
            f"契约表 {table.table_key!r} 一个受管字段都没有 —— 无法为身份异常挂可追溯定位"
        )
    anchor = anchors[0]
    out: list[StructuralAnomaly] = []

    for row in scan.empty_rows:
        out.append(
            StructuralAnomaly(
                kind=SchemaAnomalyKind.empty_row_identity,
                stable_field_key=_instantiate(anchor.stable_field_key, f"row{row}"),
                detail=(
                    f"{region.sheet_name}!{region.uuid_column}{row} 的 row identity 为空，"
                    f"契约处置={scan.disposition.value} —— 不得静默按位置猜行身份，"
                    "也不得复用已删除 UUID（Requirement 6.15）"
                ),
                row_key=f"row{row}",
                table_key=table.table_key,
                oo_location=f"{region.sheet_name}!{region.uuid_column}{row}",
                business_label=f"{table.table_key} 第 {row} 行",
                json_pointer=anchor.json_pointer,
                blocks_row_key=f"row{row}",
            )
        )
    for identity in scan.duplicate_identities:
        rows = scan.rows_by_identity[identity]
        out.append(
            StructuralAnomaly(
                kind=SchemaAnomalyKind.duplicate_row_identity,
                stable_field_key=_instantiate(anchor.stable_field_key, identity),
                detail=(
                    f"row identity {identity!r} 同时出现在 Excel 行 {list(rows)} —— "
                    "复制行产生的重复 UUID 默认为结构冲突，不得按位置拆分"
                ),
                row_key=identity,
                table_key=table.table_key,
                oo_location=(
                    f"{region.sheet_name}!"
                    + ",".join(f"{region.uuid_column}{row}" for row in rows)
                ),
                blocks_row_key=identity,
            )
        )
    for identity in scan.reused_tombstones:
        rows = scan.rows_by_identity.get(identity, ())
        out.append(
            StructuralAnomaly(
                kind=SchemaAnomalyKind.reused_tombstoned_row_identity,
                stable_field_key=_instantiate(anchor.stable_field_key, identity),
                detail=(
                    f"row identity {identity!r} 已在 tombstone 清册中却又出现在 Excel 行 "
                    f"{list(rows)} —— 已删除 UUID 永不复用（Requirement 6.15）"
                ),
                row_key=identity,
                table_key=table.table_key,
                oo_location=(
                    f"{region.sheet_name}!"
                    + ",".join(f"{region.uuid_column}{row}" for row in rows)
                ),
                blocks_row_key=identity,
            )
        )
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 8. projection sidecar（streaming gzip，Requirement 6.12）
# ═══════════════════════════════════════════════════════════════════════════

#: sidecar 的 schema 版本。行式（NDJSON）而不是一个大 JSON 对象：后者必须先在内存里拼出
#: 完整结构才能序列化，正是 Requirement 6.12 要防的「复制多份 866KB+ 结构」。
SIDECAR_SCHEMA_VERSION: Final[str] = "excel-projection-sidecar:v1"


class _SidecarWriter:
    """流式 gzip NDJSON 写出器。逐字段 flush，不在内存里拼完整 JSON。"""

    __slots__ = ("_path", "_raw", "_gz", "_count")

    def __init__(self, path: Path, *, contract: SyncContract, region: ManagedRegion) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._raw = path.open("wb")
        # `mtime=0` + `filename=""`：sidecar 的字节要可复现。
        # 🔴 只给 `mtime=0` 不够 —— `GzipFile(fileobj=...)` 会把 `fileobj.name`（也就是
        # 落盘路径）写进 gzip 头的 FNAME 字段，于是同一份 projection 导到两个不同文件名下
        # 字节就不同了，evidence digest 随之漂移。
        self._gz = gzip.GzipFile(
            filename="", fileobj=self._raw, mode="wb", mtime=0, compresslevel=9
        )
        self._count = 0
        self._emit(
            {
                "schema_version": SIDECAR_SCHEMA_VERSION,
                "contract_id": contract.contract_id,
                "semantic_version": contract.semantic_version,
                "document_type": contract.document_type,
                "sheet": region.sheet_name,
                "table_key": region.table_key,
                "table_ref": region.table_ref,
            }
        )

    def _emit(self, payload: Mapping[str, Any]) -> None:
        self._gz.write(
            (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        )

    def write_field(self, value: FieldValue, *, oo_location: str) -> None:
        self._emit(
            {
                "stable_key": value.stable_key,
                "value": value.value if _json_safe(value.value) else repr(value.value),
                "value_type": value.value_type.value,
                "mode": value.mode.value,
                "row_key": value.row_key,
                "oo_location": oo_location,
            }
        )
        self._count += 1
        # 每个字段落一次，峰值驻留 = 一个字段的字节数 + gzip 窗口，而不是整份 projection。
        self._gz.flush()

    def close(self) -> None:
        try:
            self._gz.close()
        finally:
            self._raw.close()


def _json_safe(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def write_projection_sidecar(
    outcome: ExcelExtractOutcome, path: Path, *, region: ManagedRegion | None = None
) -> Path:
    """把已有 :class:`ExcelExtractOutcome` 的 projection 流式写成 gzip sidecar。

    `extract_projection(sidecar_path=...)` 是**边读边写**的首选路径（真正的一次流式）；
    本函数是「已经拿到 outcome 之后再补一份 sidecar」的入口，例如 evidence 归档。
    """
    writer = _SidecarWriter(
        path,
        contract=_contract_stub(outcome.projection),
        region=region or outcome.region,
    )
    try:
        for key in outcome.projection.stable_keys():
            value = outcome.projection.values[key]
            writer.write_field(value, oo_location="")
    finally:
        writer.close()
    return path


@dataclass(frozen=True)
class _ContractStub:
    contract_id: str
    semantic_version: str
    document_type: str


def _contract_stub(projection: Projection) -> Any:
    return _ContractStub(
        contract_id=projection.contract_id,
        semantic_version=projection.semantic_version,
        document_type=projection.document_type,
    )


def read_projection_sidecar(path: Path) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    """流式读回 sidecar，返回 `(header, fields)`。守卫用它证明写出的内容可完整还原。"""
    header: Mapping[str, Any] | None = None
    fields: list[Mapping[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if header is None:
                header = payload
                continue
            fields.append(payload)
    if header is None:
        raise ExcelExtractError(f"projection sidecar 是空文件: {path}")
    if header.get("schema_version") != SIDECAR_SCHEMA_VERSION:
        raise ExcelExtractError(
            f"projection sidecar schema 版本不符: {header.get('schema_version')!r}"
        )
    return header, tuple(fields)


# ═══════════════════════════════════════════════════════════════════════════
# 9. 共用 verifier（Task 38 materialize / rematerialize 的反读门）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RoundtripReport:
    """反读等值报告（Property 29 / AC 6.11 / AC 8.11）。"""

    equivalent: bool
    compared_keys: tuple[str, ...]
    missing_keys: tuple[str, ...] = ()
    unexpected_keys: tuple[str, ...] = ()
    first_difference: str | None = None

    def __post_init__(self) -> None:
        if not self.equivalent and not (self.first_difference or "").strip():
            raise RoundtripEquivalenceError(
                "RoundtripReport.equivalent=False 时必须给出 first_difference —— "
                "只报「不等值」无法定位（Requirement 6.10）"
            )
        if self.equivalent and (self.first_difference or "").strip():
            raise RoundtripEquivalenceError(
                "RoundtripReport.equivalent=True 时不得同时给出 first_difference"
            )


def verify_roundtrip_equivalence(
    *, expected: Projection, extracted: Projection, contract: SyncContract
) -> RoundtripReport:
    """受管 **editable** 字段逐条类型化比对（Property 29）。

    比较范围刻意只含 `mode=editable`：公式 / auto-source 的值由服务端写、由 OO 重算，
    逐字节相等不是它们的正确性判据（那一格由 :func:`verify_formula_regions` 管）。把它们
    混进来会让 verifier 在真实数据上恒不通过 ⇒ 调用方只能整体关掉它。

    比对用 `merge.normalize_value` 的**同一套**规范化：verifier 与 merge 若各用一套口径，
    「merge 认为等值、verifier 认为不等值」就会变成无法解释的发布失败。
    """
    editable = {
        key
        for key in set(expected.values) | set(extracted.values)
        if _is_editable(key, contract)
    }
    missing = tuple(sorted(k for k in editable if k not in extracted.values))
    unexpected = tuple(sorted(k for k in editable if k not in expected.values))
    first: str | None = None
    if missing:
        first = (
            f"缺失受管 editable 字段 {missing[0]!r} —— materialize 写下去的字段反读不回来"
        )
    elif unexpected:
        first = (
            f"多出受管 editable 字段 {unexpected[0]!r} —— 反读出了期望 projection 里没有的键"
        )
    else:
        for key in sorted(editable):
            want = expected.values[key]
            got = extracted.values[key]
            if not _typed_equal(want, got):
                first = (
                    f"{key}: 期望 {want.value!r}（{want.value_type.value}）"
                    f" != 反读 {got.value!r}（{got.value_type.value}）"
                )
                break
    return RoundtripReport(
        equivalent=first is None,
        compared_keys=tuple(sorted(editable)),
        missing_keys=missing,
        unexpected_keys=unexpected,
        first_difference=first,
    )


def _is_editable(stable_key: str, contract: SyncContract) -> bool:
    """按契约模板判断某个**已实例化**的 key 是否 editable。"""
    for spec in contract.all_fields():
        if spec.mode is not FieldMode.editable:
            continue
        template = spec.stable_field_key
        if template == stable_key:
            return True
        if "{row_uuid}" not in template:
            continue
        expected_parts = template.split("/")
        actual_parts = stable_key.split("/")
        if len(expected_parts) != len(actual_parts):
            continue
        if all(
            exp == act or exp == "{row_uuid}"
            for exp, act in zip(expected_parts, actual_parts)
        ):
            return True
    return False


def _typed_equal(left: FieldValue, right: FieldValue) -> bool:
    if left.value_type is not right.value_type:
        return False
    try:
        return normalize_value(left.value, left.value_type) == normalize_value(
            right.value, right.value_type
        )
    except ValueNormalizationError:
        # 规范化失败时退回**原值**严格相等：不得把「两个都读不懂的值」判成相等。
        return left.value == right.value


def assert_roundtrip_equivalent(
    *, expected: Projection, extracted: Projection, contract: SyncContract
) -> RoundtripReport:
    report = verify_roundtrip_equivalence(
        expected=expected, extracted=extracted, contract=contract
    )
    if not report.equivalent:
        raise RoundtripEquivalenceError(
            f"contract {contract.contract_id}: 反读受管 projection 与期望不等值 —— "
            f"{report.first_difference}；application 必须失败，"
            "HTML projection / current pointer / last-applied / client-confirmed base "
            "一个都不得推进（AC 8.11）"
        )
    return report


@dataclass(frozen=True)
class FormulaRegionReport:
    """公式 / auto-source 受保护区域报告。"""

    intact: bool
    inspected_keys: tuple[str, ...]
    findings: tuple[ProtectedCellFinding, ...] = ()
    first_difference: str | None = None

    def __post_init__(self) -> None:
        if not self.intact and not (self.first_difference or "").strip():
            raise FormulaRegionDriftError(
                "FormulaRegionReport.intact=False 时必须给出 first_difference"
            )


def verify_formula_regions(
    findings: Sequence[ProtectedCellFinding], *, declared_protected_keys: Sequence[str]
) -> FormulaRegionReport:
    """把 extract 的受保护格观测翻成 verifier 报告。

    `declared_protected_keys` 取 `contract.protected_field_keys()`（**契约声明**的模板键，
    不是实际读到的键）：契约没声明受保护字段时 `intact=True` 是正确结论而不是空转；反过来
    「有 finding 却一条声明都没有」是结构性矛盾（extractor 自己算错了受保护集），必须抛。
    """
    declared = tuple(sorted({str(key) for key in declared_protected_keys}))
    if findings and not declared:
        raise FormulaRegionDriftError(
            f"报出了 {len(findings)} 处受保护格篡改，但契约一个受保护字段都没声明 —— "
            "extractor 的受保护集算错了，不得据此给出任何结论"
        )
    if not findings:
        return FormulaRegionReport(intact=True, inspected_keys=declared)
    first = findings[0]
    return FormulaRegionReport(
        intact=False,
        inspected_keys=declared,
        findings=tuple(findings),
        first_difference=(
            f"{first.oo_location} ({first.stable_field_key}) {first.kind.value}: "
            f"{first.baseline!r} → {first.observed!r}"
        ),
    )


def protected_conflicts_for_findings(
    *,
    findings: Sequence[ProtectedCellFinding],
    contract: SyncContract,
    base: Projection,
    current: Projection,
    incoming: Projection,
    existing: Sequence[ConflictRecord] = (),
    label_overrides: Mapping[str, str] | None = None,
) -> tuple[ConflictRecord, ...]:
    """把公式层 tamper 补成 `protected` 冲突（Property 24 的补齐项）。

    ═══ 为什么必须有这一步 ═══

    Task 14 的 merge 只能从 **projection 值**差异推出 protected 冲突。但「把 `=G7-D7`
    改写成 `=G7-D7+1`」在缓存值未重算时**值完全相同** ⇒ merge 看不到任何差异 ⇒ Property 24
    要求的 protected 冲突不会出现。这一类只能由公式 inventory 比对发现，因此在这里补齐。

    只补 `existing` 里**没有**的键：值层已经生成过 protected 冲突的键不再重复，否则
    `ConflictSet` 的 `UNIQUE(stable_field_key,row_key,oo_location)` 会被自己撞破。
    """
    index = ContractIndex(contract, label_overrides=label_overrides)
    seen = {
        (record.locator.stable_field_key, record.locator.row_key)
        for record in existing
        if record.kind is ConflictKind.protected
    }
    out: list[ConflictRecord] = []
    for finding in findings:
        key = (finding.stable_field_key, finding.row_key or "")
        if key in seen:
            continue
        seen.add(key)
        locator = index.resolve(
            finding.stable_field_key,
            declared_row_key=finding.row_key or "",
        )
        out.append(
            ConflictRecord(
                locator=locator,
                kind=ConflictKind.protected,
                base=_envelope_of(base, finding.stable_field_key),
                current=_envelope_of(current, finding.stable_field_key),
                incoming=_envelope_of(incoming, finding.stable_field_key),
                suggested_action=SuggestedAction.keep_current,
                reason=(
                    f"受保护字段（{locator.protection_policy.value}）在 OO 侧被改动："
                    f"{finding.kind.value} @ {finding.oo_location} —— 公式/auto-source 结果"
                    "不得被覆盖（AC 6.6）；incoming 值只用于篡改检测"
                ),
            )
        )
    return tuple(out)


def _envelope_of(projection: Projection, stable_key: str) -> ValueEnvelope:
    field = projection.get(stable_key)
    return ValueEnvelope.absent() if field is None else ValueEnvelope.of(field.value)


def assert_protected_tamper_fully_reported(
    *,
    findings: Sequence[ProtectedCellFinding],
    conflicts: Sequence[ConflictRecord],
) -> None:
    """每一处受保护格 tamper 都必须对应一条 `protected` 冲突（Property 24 的闭合判据）。

    这条判据的价值在于**跨层**：extract 侧发现了 tamper、merge 侧却没有 protected 冲突时
    打红。少了它，「值层看不见的公式改写」会静默通过 —— 而 `verify_formula_regions` 只在
    rematerialize 反读时跑，OO→HTML 这一侧不经过它。
    """
    reported = {
        (record.locator.stable_field_key, record.locator.row_key)
        for record in conflicts
        if record.kind is ConflictKind.protected
    }
    missing = [
        finding
        for finding in findings
        if (finding.stable_field_key, finding.row_key or "") not in reported
    ]
    if missing:
        first = missing[0]
        raise FormulaRegionDriftError(
            f"{len(missing)} 处受保护格篡改没有对应的 protected 冲突，首个 "
            f"{first.stable_field_key!r}（{first.kind.value} @ {first.oo_location}）—— "
            "公式/auto-source 被改动必须进冲突预览交人工裁决（AC 6.6 / Property 24），"
            "不得静默丢弃"
        )


def assert_formula_regions_intact(
    findings: Sequence[ProtectedCellFinding], *, declared_protected_keys: Sequence[str]
) -> FormulaRegionReport:
    report = verify_formula_regions(
        findings, declared_protected_keys=declared_protected_keys
    )
    if not report.intact:
        raise FormulaRegionDriftError(
            f"受保护公式 / auto-source 区域被改动：{report.first_difference} —— "
            "公式结果不得被覆盖（AC 6.6）；rematerialize 后的产物必须与服务端值一致"
        )
    return report


# ═══════════════════════════════════════════════════════════════════════════
# 10. commit 前置门（AC 8.11：未过不得交 ContentMutationService）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ExcelVerificationBundle:
    """三个 verifier 的合并结论 + 反读出的 outcome。"""

    roundtrip: RoundtripReport
    formulas: FormulaRegionReport
    unmanaged: UnmanagedRegionReport
    extracted: ExcelExtractOutcome

    @property
    def passed(self) -> bool:
        return self.roundtrip.equivalent and self.formulas.intact and self.unmanaged.equivalent

    @property
    def failed_verifiers(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, ok in (
                ("roundtrip", self.roundtrip.equivalent),
                ("formula_regions", self.formulas.intact),
                ("unmanaged_regions", self.unmanaged.equivalent),
            )
            if not ok
        )

    def assert_publishable(self) -> None:
        """未全过即 fail closed。

        三条判据各自抛**自己**的异常类型（而不是统一抛一个 `VerificationNotPassedError`）：
        统一类型会让「反读不等值」「公式被改」「未管理区域异动」在守卫里不可分辨，删掉
        任一条的判定都不会打红。只有「一条都没跑」这种装配错误才归
        :class:`VerificationNotPassedError`。
        """
        if not self.roundtrip.compared_keys and not self.extracted.projection.values:
            raise VerificationNotPassedError(
                "反读出的受管 projection 是空集 —— 「零次比对全部通过」不是通过。"
                "契约声明了受管字段却一个都没读到，说明 identity 定位静默落空或写入根本"
                "没落盘；此时必须 fail closed（AC 6.11 要求的是反读比对，不是跳过比对）"
            )
        if not self.roundtrip.equivalent:
            raise RoundtripEquivalenceError(
                "反读受管 projection 与 merged projection 不等值："
                f"{self.roundtrip.first_difference}"
            )
        if not self.formulas.intact:
            raise FormulaRegionDriftError(
                f"受保护公式 / auto-source 区域被改动：{self.formulas.first_difference}"
            )
        self.unmanaged.assert_equivalent()

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failed_verifiers": list(self.failed_verifiers),
            "roundtrip": {
                "equivalent": self.roundtrip.equivalent,
                "compared_key_count": len(self.roundtrip.compared_keys),
                "first_difference": self.roundtrip.first_difference,
            },
            "formula_regions": {
                "intact": self.formulas.intact,
                "inspected_key_count": len(self.formulas.inspected_keys),
                "first_difference": self.formulas.first_difference,
            },
            "unmanaged_regions": {
                "equivalent": self.unmanaged.equivalent,
                "inspected_aspects": list(self.unmanaged.inspected_aspects),
                "first_difference": self.unmanaged.first_difference,
            },
            "extract": self.extracted.as_dict(),
        }


def verify_before_commit(
    *,
    expected: Projection,
    staged_result: Path,
    substrate: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    substrate_role: SubstrateRole | str = SubstrateRole.incoming,
    substrate_kind: ArtifactKind | str = ArtifactKind.incoming,
    substrate_state: ArtifactState | str = ArtifactState.durable,
    baseline: Projection | None = None,
    baseline_formulas: Mapping[str, str] | None = None,
    limits: SyncLimits | None = None,
) -> ExcelVerificationBundle:
    """Task 38 保存 staged result 之后调用的**唯一**反读门。

    做三件事，一件都不能省：

    1. 用**同一个 adapter**（本模块）重新 extract staged result，与 `expected`（merged
       projection）逐字段类型化比对（Property 29 / AC 6.11）；
    2. 比对受保护公式 / auto-source 区域是否被改动（AC 6.6 / Property 24）；
    3. 比对未管理区域与 substrate 是否按 policy 不变（AC 8.11 / Requirement 6.17）。

    `staged_result` 是**新产出的 staged 文件**，因此按 `kind=canonical,state=staged` 准入；
    substrate 的 kind/state 由调用方给（OO→HTML 必须是 `incoming/durable`）。
    """
    lim = limits or load_limits()
    # substrate 的准入**先判**：quarantined incoming 不得被任何 engine 读，连「只是拿来
    # 做未管理区域比对」也不行（AC 8.10）。放到反读之后会让隔离样本先被解析一遍。
    assert_substrate_usable(
        role=substrate_role, artifact_kind=substrate_kind, artifact_state=substrate_state
    )
    extracted = extract_projection(
        artifact=staged_result,
        definitions=definitions,
        binding=binding,
        substrate_role=SubstrateRole.staged_result,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.staged,
        baseline=baseline if baseline is not None else expected,
        baseline_formulas=baseline_formulas,
        limits=lim,
    )
    roundtrip = verify_roundtrip_equivalence(
        expected=expected, extracted=extracted.projection, contract=definitions.contract
    )
    formulas = verify_formula_regions(
        extracted.protected_findings,
        declared_protected_keys=definitions.contract.protected_field_keys(),
    )
    unmanaged = verify_unmanaged_regions(
        before=substrate,
        after=staged_result,
        contract=definitions.contract,
        region=extracted.region,
        binding=binding,
        scan=extracted.scan,
        limits=lim,
    )
    return ExcelVerificationBundle(
        roundtrip=roundtrip,
        formulas=formulas,
        unmanaged=unmanaged,
        extracted=extracted,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 11. 「extractor 不得反向依赖 materializer」的可执行判据
# ═══════════════════════════════════════════════════════════════════════════

#: Task 38 将要落地的 materializer 模块名（本模块**不得**出现在其 import 图里）。
FORBIDDEN_DOWNSTREAM_MODULES: Final[tuple[str, ...]] = (
    "app.services.workpaper_sync.excel_materialize",
    "app.services.workpaper_sync.excel_rematerialize",
    "app.services.workpaper_sync.adapters.excel",
)


def _imported_module_names(source: Path) -> frozenset[str]:
    """一份源码文件的 import 节点名集合（**AST**，不是字符串匹配）。

    AST 与 grep 的差别正是「改个别名就绕过」那条：`import x as y` / `from x import z`
    的模块名都在节点里，而字符串匹配只看得见字面量。
    """
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return frozenset()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return frozenset(names)


def _is_downstream_consumer(name: str) -> bool:
    """`name` 是否是**合法下游**（它 import 我们，方向 38 → 37）。

    加这一层的理由（Task 38 落地时实测）：只看 `sys.modules` 会把「同一进程里合法加载了
    Task 38 的 materializer」误判成反向依赖 —— 整个 `workpaper_sync` 测试套件必然同时
    加载两侧，于是判据变成恒红的假红。真正要禁的是**方向反了**，所以：

    * 我们的源码 import 了下游 ⇒ 反向依赖，禁（见 :func:`assert_no_materializer_dependency`
      的第一段判据，走 AST）；
    * 下游 import 了我们 ⇒ 方向正确，放行；
    * 既不 import 我们、又没有源码文件（如手工塞进 `sys.modules` 的桩）⇒ 无法证明方向，
      按 fail closed 判违规。
    """
    module = sys.modules.get(name)
    source = getattr(module, "__file__", None)
    if not source:
        return False
    return __name__ in _imported_module_names(Path(source))


def assert_no_materializer_dependency() -> tuple[str, ...]:
    """实测本模块与 Task 38 materializer 之间的依赖**方向**。

    判据是**真实 import 图**（本模块源码的 AST import 节点 + `sys.modules` 的实际内容），
    不是 grep 源码里有没有出现某个字符串 —— 后者改个别名就能绕过（假绿第②源）。

    两段判据各自可达、各自可被 falsify：

    1. 本模块源码若 import 了 :data:`FORBIDDEN_DOWNSTREAM_MODULES` 任一项 ⇒ 反向依赖，抛；
    2. 已加载的下游模块里，凡是**不能证明它 import 了我们**的（没有源码文件、或源码里
       没有本模块）⇒ 方向不明，抛。

    返回违规模块名，正常情况下是空 tuple。
    """
    own = _imported_module_names(Path(__file__))
    reverse = tuple(name for name in FORBIDDEN_DOWNSTREAM_MODULES if name in own)
    if reverse:
        raise ExcelExtractError(
            f"extractor 的源码直接 import 了 materializer 实现 {list(reverse)} —— "
            "Task 37 先于 Task 38，extract 侧不得依赖写入侧（否则两者的判据互为循环，"
            "「materialize 写错了」会被「extract 读错了」抵消掉）"
        )
    loaded = tuple(name for name in FORBIDDEN_DOWNSTREAM_MODULES if name in sys.modules)
    offenders = tuple(name for name in loaded if not _is_downstream_consumer(name))
    if offenders:
        raise ExcelExtractError(
            f"extractor 反向依赖了 materializer 实现 {list(offenders)} —— Task 37 先于 "
            "Task 38，extract 侧不得依赖写入侧（否则两者的判据互为循环，"
            "「materialize 写错了」会被「extract 读错了」抵消掉）"
        )
    return offenders
