# -*- coding: utf-8 -*-
"""Word per-entry **entry gate** 与 candidate **finalize gate**（Task 77）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 4 Task 77
Requirements: 6.10, 6.18, 7.1, 7.2, 7.3, 7.4, 7.5, 7.8, 7.10, 12.5
Properties: **P28**（immutable definition 漂移 fail closed）/ **P30**（Word 只认 tagged
SDT）/ **P31**（Word-only 正文保留）/ **P32**（Word 多实例异值冲突）/ **P34**（SDT 丢失
不降级）/ **P67**（upgrader 先 candidate、approved bundle 后 finalize）

═══ 一、为什么不能沿用 `excel_entry_gate.py` 的判据 ═══

Task 36 的判据形状是 **sheet/cell**：`assert_no_structure_drift` 的
`(sheet_key, table_key, stable_field_key, locator)` 4 元组、`observed_business_sheets`
枚举、`_GT_SYNC` 隐藏 sheet 排除、`{slot}_{seq}` 动态列。Word 文档里这四样**一个都不
存在** —— docx 契约禁声明 `sheets`/`cell`（`contracts._parse_field` 的 CS-19），
`declared_structure_inventory()` 对 docx 产出的 4 元组恒为 `("", "", key, sdt_tag)`。
把 Task 36 的判据搬过来的后果不是「更严」，而是三格恒为空串的**重言式**：改坏任何
东西都不会打红。

本模块因此把判据换成 **tagged-SDT 形状**，四条各自独立、各有专属 error_code：

=====  ===========================================  ==============================
编号   判据                                          异常
=====  ===========================================  ==============================
WG-1   declared tag 集合 ↔ 实测 tag 集合             :class:`WordEntryTagSetDriftError`
WG-2   SDT 层级（container path + block 包裹）        :class:`WordEntryHierarchyDriftError`
WG-3   字段实例计数（含重复实例）                     :class:`WordEntryInstanceCountDriftError`
WG-4   SDT 外 Word-only 区域按 policy 等值            `UnmanagedRegionDriftError`（委派）
=====  ===========================================  ==============================

**只**从 Task 36 复用与文档类型无关的 **bundle typed slot 形态分类**
（:func:`~app.services.workpaper_sync.excel_entry_gate.assert_frozen_slots_shape`
的 FS-1~FS-5 与 `PerEntryContractUnapprovedError` 的 FS-6）—— 那六条讲的是
「bundle 的 slot 是不是伪身份」，与 sheet/cell 无关，抄第二份只会让任一侧被短路都不
改变行为。守卫用 AST 断言本模块**只**从 Task 36 import 白名单里那几个名字，并且
sheet/cell 一族名字**零引用**。

═══ 二、`w:tag` 是唯一锚点，四个降级锚点恒拒 ═══

真源是 `backend/data/onlyoffice_word_sdt_carrier_contract.json` 的 `downstream_gate`
（Task 6 真实 OO 9.4.0-129 探针裁决），本模块**不复制**其中任何清单，一律经
`contracts.load_word_carrier_gate()` 读：

* `anchors_allowed = ["w_tag"]` ⇒ :func:`tag_anchor_name` 要求 allowlist **恰好一个
  元素**并返回它。写成「取唯一元素」而不是写死 `"w_tag"`：有人往 allowlist 里加第二个
  锚点时本函数立刻 fail closed，而写死字面量只会静静地继续用旧锚点。
* `anchors_blocked = ["alias_display_name", "sdt_id", "paragraph_index", "run_index"]`
  ⇒ :func:`assert_only_tag_anchor_is_usable` 把这四个**逐个真喂给**
  `CarrierGate.assert_anchor`，要求每一个都抛。判据是**真实执行**而不是「源码里没出
  现这些字符串」（后者改个别名就绕过，是假绿第②源）。
* `carriers_blocked = ["row_sdt"]` ⇒ :func:`assert_blocked_carriers_have_no_exemption`
  要求 blocked ∩ allowed = ∅、blocked 非空、且每个 blocked 载体真喂进去都抛。
  **没有** per-entry 豁免参数 —— 「某 entry 只差 row 就能过」在签名上无处可写。

段落绝对索引与中文正则 fallback 由两条**结构判据**封死（守卫在本模块 AST 上断言）：
:data:`FORBIDDEN_LOCATOR_ATTRS` 与 :data:`FORBIDDEN_FALLBACK_SYMBOLS` 直接复用
`word_sdt_engine` 的同名常量（`is` 同一对象），再并上 gate 现读的
`anchors_blocked` —— 三份来源合流成一个分母，且分母非空由守卫自检。

═══ 三、declared 清册的三边锁 ═══

「declared tag 集合与实例形态」不来自本模块的想象，而来自**已冻结的 immutable
instrumentation definition payload**（bundle 的 instrumentation typed child），它的
`sdt_tags` 是 Task 59 `WordInstrumentationSpec.expected_tags()` 的落库形态。调用方把
payload 传进来，本模块**重算 canonical digest 并要求它逐字节等于 bundle 的
instrumentation slot digest**（:class:`WordEntryInstrumentationDigestMismatchError`）
—— 于是「换一份 payload 顶上」不可能，payload 与 bundle 是同一身份。

三边分别是：

1. **instrumentation payload**（frozen，digest 锁到 bundle slot）—— declared tag 集合；
2. **per-entry contract**（frozen，digest 由 Task 13 `assert_contract_identity_frozen`
   锁到 bundle contract slot）—— 每个 stable key 的 `sdt_tag` 与 `instances`；
3. **文档实测**（只经 `w:tag` 读出的 `WordExtractOutcome`）。

任两边不一致都 fail closed，且错误里给出**首个**漂移 tag 与它的 XPath（AC 6.10
「指出首个漂移」的 Word 形态：无 sheet 无 cell，位置就是 tag + XPath）。

═══ 四、Word-only 区域：等值、不降级、不用模板重生成 ═══

* 等值判据**委派** `word_sdt_engine.verify_word_only_regions` /
  `verify_word_before_commit`（单一真源，含 `managed_row_identity` 那格的自算），
  本模块只加一条 Task 59 没有的：**覆盖计数必须非空**
  （:class:`WordEntryWordOnlyCoverageError`）—— 手搓最小 DOCX 上「SDT 外正文」是空集，
  `equivalent=True` 是空转。
* 比对的两侧是 **candidate 字节 → 经 tag 重写出的 roundtrip 字节**，**不是**
  「权威模板 → candidate」：后者天然不等价（注入把 token 文本从 SDT 外搬进 SDT 内），
  拿它当判据会恒红；更重要的是它会诱导「用模板重生成」这条被明令禁止的路径。
  本模块**没有任何模板入口**：既不读 `backend/wp_templates/`，也不接受 template 路径
  参数，`materialize_word_projection` 的 `substrate` 只可能是 candidate 自己。
* 不等值时抛 `UnmanagedRegionDriftError`，**不写任何东西**：本模块对
  representation / pointer / revision 的唯一触点是 Task 25 的
  `finalize_definition_upgrade`，而它在全部判据之后调用（顺序即判据）。因此「差异被
  降级成 warning 后继续发布」在结构上不可达，而不是靠注释承诺。

═══ 五、本模块**不**注册 Word adapter ═══

`registry.PENDING_ENGINE_ADAPTERS` 仍禁止 `adapters/word.py` 与 `adapters/word`，
放行门是 Task 61 的真实 OO 9.4 场景。本模块是 **entry gate**，不是 adapter：
零 `adapters/` 落地、零 registry 写入。传给 Task 15 的 `adapter_id` 取
`contract.contract_id`（与 Excel 侧「adapter_id == 契约文件 stem」同一约定），
`adapter_build_digest` 是 :func:`word_engine_build_digest` 现算的**冻结身份摘要**，
它是一条 identity，不是「已有 adapter 模块」的声明。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping as AbcMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
)
from app.services.workpaper_sync.adapters.base import (
    SubstrateRole,
    UnmanagedRegionDriftError,
    UnmanagedRegionReport,
)
from app.services.workpaper_sync.artifacts import StagedCandidate
from app.services.workpaper_sync.contracts import (
    CarrierGate,
    ContractCarrierGateError,
    FieldSpec,
    SyncContract,
    load_word_carrier_gate,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.excel_entry_gate import (
    # 🔴 只 import 与文档类型**无关**的 bundle typed slot 形态判据（FS-1~FS-6）。
    #    sheet/cell 一族（assert_no_structure_drift / observed_business_sheets /
    #    _GT_SYNC 排除 / 动态列 / AdapterBuild / identity inventory）一个都不 import ——
    #    守卫在 AST 上按封闭白名单断言这件事。
    PerEntryContractUnapprovedError,
    assert_frozen_slots_shape,
    raw_slot_map_of,
)
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    BundleSlot,
    BundleSlotSpec,
    DefinitionKind,
    DefinitionState,
    SyncDomainError,
    is_digest,
)
from app.services.workpaper_sync.representations import RepresentationFinalizeOutcome
from app.services.workpaper_sync.resolution import (
    CanonicalResolutionService,
    DefinitionBundleSnapshot,
)
from app.services.workpaper_sync.word_sdt_engine import (
    FORBIDDEN_FALLBACK_SYMBOLS as ENGINE_FORBIDDEN_FALLBACK_SYMBOLS,
    FORBIDDEN_SDT_LOCATOR_ATTRS as ENGINE_FORBIDDEN_SDT_LOCATOR_ATTRS,
    WORD_DOCUMENT_TYPE,
    WORD_ONLY_ASPECTS,
    WordEngineBinding,
    WordEngineMode,
    WordExtractOutcome,
    WordSdtInstance,
    WordVerificationBundle,
    extract_word_projection,
    materialize_word_projection,
    parse_sdt_tag,
    verify_word_before_commit,
)

__all__ = [
    # 常量
    "WORD_UPGRADE_EVIDENCE_SCHEMA",
    "WORD_ENTRY_STRUCTURE_SCHEMA",
    "WORD_ENGINE_BUILD_SCHEMA",
    "REQUIRED_WORD_EVIDENCE_KEYS",
    "REQUIRED_WORD_READBACK_KEYS",
    "WORD_ONLY_COVERAGE_REQUIRED",
    "WORD_ENTRY_FAILURE_CODES",
    "INSTANCE_DRIFT_CAUSES",
    "TAG_SET_DRIFT_CAUSES",
    "HIERARCHY_DRIFT_CAUSES",
    "FORBIDDEN_LOCATOR_ATTRS",
    "FORBIDDEN_FALLBACK_SYMBOLS",
    # 异常
    "WordEntryGateError",
    "WordEntryFrozenBundleDigestMismatchError",
    "WordEntryInstrumentationDigestMismatchError",
    "WordEntryTagSetDriftError",
    "WordEntryHierarchyDriftError",
    "WordEntryInstanceCountDriftError",
    "WordEntryBlockedCarrierError",
    "WordEntryDegradedAnchorError",
    "WordEntryWordOnlyCoverageError",
    "WordEntryDuplicateConflictError",
    "WordEntryCandidateEvidenceError",
    "WordEntryFinalizeGateBlockedError",
    "PerEntryContractUnapprovedError",
    "UnmanagedRegionDriftError",
    # 载体 / 锚点门
    "blocked_anchor_names",
    "blocked_carrier_names",
    "tag_anchor_name",
    "assert_only_tag_anchor_is_usable",
    "assert_blocked_carriers_have_no_exemption",
    # declared / observed
    "WordTagInventory",
    "declared_tag_inventory",
    "WordEntryObservation",
    "observe_word_entry",
    # 四条判据
    "assert_tag_set_matches",
    "assert_sdt_hierarchy_intact",
    "assert_field_instance_counts",
    "assert_word_only_equivalent",
    # candidate 证据
    "WordCandidateEvidence",
    "parse_word_candidate_evidence",
    # 身份摘要
    "word_engine_build_digest",
    "word_entry_structure_hash",
    # loader / gate
    "FrozenWordEntryDefinitions",
    "WordEntryDefinitionLoader",
    "WordEntryFinalizeOutcome",
    "WordEntryFinalizeGate",
]


# ═══════════════════════════════════════════════════════════════════════════
# 0. 常量
# ═══════════════════════════════════════════════════════════════════════════

#: Task 59 `WordInstrumentationUpgrader.stage_and_register_candidate` 写出的证据
#: schema。本模块是它的**唯一**读侧；两侧的行为级交叉锁在 `_pg.py` 守卫里
#: （真跑一次 upgrader，产出的报告必须被本模块解析通过）。
WORD_UPGRADE_EVIDENCE_SCHEMA: Final[str] = "word-instrumentation-upgrade-evidence:v1"

#: 传给 Task 15 的 `structure_hash` 的 schema（tag 形状，不含 sheet/cell）。
WORD_ENTRY_STRUCTURE_SCHEMA: Final[str] = "word-entry-structure:v1"

#: 传给 Task 15 的 `adapter_build_digest` 的 schema（冻结身份摘要，见模块 docstring 第五节）。
WORD_ENGINE_BUILD_SCHEMA: Final[str] = "word-entry-engine-build:v1"

#: candidate 证据报告里**必须**出现且非空的键（写侧是 Task 59，逐字对齐）。
REQUIRED_WORD_EVIDENCE_KEYS: Final[tuple[str, ...]] = (
    "schema_version",
    "entry_id",
    "document_type",
    "template_definition_sha256",
    "instrumentation_definition_sha256",
    "rollback_source_sha256",
    "instrumented_sha256",
    "visible_equivalence",
    "tag_readback",
    "probe_gate",
)

#: `tag_readback` 里必须出现的键（写侧是 `read_back_word_tags` 的返回字典）。
REQUIRED_WORD_READBACK_KEYS: Final[tuple[str, ...]] = (
    "tags",
    "tag_count",
    "instance_count",
    "hierarchy",
    "row_uuids",
    "untagged_sdt_count",
)

#: Word-only 报告里**必须**非空的覆盖项。
#:
#: 刻意**不**包含 `table_shape` 与 `managed_row_identity`：F2-22/F2-23 两份权威模板
#: 的 `w:tbl` / `w:tr` 计数实测为 0（发布记录 `field_evidence[].negative_claims`
#: `document_has_w_tbl=False`），行域字段 0 个。把它们写进必需项会把「本 entry 没有
#: 表格」误判成缺陷；反过来把它们写进「必须为 0」的基线则是把错值锁死。两者都不做：
#: 覆盖计数**全部**进 outcome 供调用方查看，只有本清单里的三项参与放行判据。
WORD_ONLY_COVERAGE_REQUIRED: Final[tuple[str, ...]] = (
    "outside_sdt_text",
    "sdt_tag_set",
    "sdt_hierarchy",
    "protected_parts",
)

#: WG-1 的两种成因（封闭词表；自由文本会让守卫只能比整句字符串）。
TAG_SET_DRIFT_CAUSES: Final[tuple[str, ...]] = (
    "declared_tag_missing_from_document",
    "document_tag_not_declared",
)

#: WG-2 的成因（**一条**）。
#:
#: 🔴 首版还登记了 `block_container_not_wrapping_field`，实测**不可达**已删：
#: `word_sdt_engine._assert_hierarchy` 在 block tag 存在时已经判「field 是否还在 block
#: 内」（extract 阶段就抛），block tag 不存在时 WG-1 先以「declared tag 缺失」拒掉。
#: 两条路都到不了那个分支 ⇒ 留着就是「登记了一个永久不可达的 kind」这种假绿
#: （`word_sdt_engine.WORD_ENGINE_FAILURE_CODES` 的注释里记着同款教训）。
HIERARCHY_DRIFT_CAUSES: Final[tuple[str, ...]] = ("container_path_drift",)

#: WG-3 的两种成因。
#:
#: 🔴 首版还登记了 `single_declaration_has_duplicate_instances` 与
#: `multi_declaration_lost_instances`，实测后删掉：
#: * 前者不可达 —— `instances='one'` 出现多实例由
#:   `word_sdt_engine._assert_instance_counts` 在 extract 阶段就抛；
#: * 后者与 `per_tag_instance_count_drift` 是**同一事件**（`many` 掉到 1 个 ⇔ 逐 tag
#:   精确计数 2→1），两条判据覆盖同一形态时短路任一条都不改变行为 ⇒ 变异必 GREEN。
#: 保留的两条是**不同事件**：一条是「两份冻结声明互相矛盾」（发布期），一条是
#: 「文档相对冻结声明漂移」（运行期）。
INSTANCE_DRIFT_CAUSES: Final[tuple[str, ...]] = (
    "declared_instances_disagree_with_frozen_count",
    "per_tag_instance_count_drift",
)

#: **禁止**参与定位的伪锚点属性名。前两族直接复用 `word_sdt_engine` 的常量对象
#: （守卫用 `is` 断言同一性），第三族是 gate 现读的 `anchors_blocked` ——
#: 三份来源合流，任一份被改小都会让分母缩水，守卫据此自检。
FORBIDDEN_LOCATOR_ATTRS: Final[frozenset[str]] = ENGINE_FORBIDDEN_SDT_LOCATOR_ATTRS
FORBIDDEN_FALLBACK_SYMBOLS: Final[frozenset[str]] = ENGINE_FORBIDDEN_FALLBACK_SYMBOLS


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常（一条禁令一个类型一个 error_code）
# ═══════════════════════════════════════════════════════════════════════════


class WordEntryGateError(SyncDomainError):
    """Task 77 的域基类。"""

    error_code = "word_entry_gate_failed"


class WordEntryFrozenBundleDigestMismatchError(WordEntryGateError):
    """frozen `(bundle_id, bundle_sha256)` 与 DB row 不符 —— 禁按当前 alias 顶替。"""

    error_code = "word_entry_frozen_bundle_digest_mismatch"


class WordEntryInstrumentationDigestMismatchError(WordEntryGateError):
    """调用方给的 instrumentation payload 与 bundle 的 instrumentation slot digest 不符。

    与 :class:`WordEntryFrozenBundleDigestMismatchError` 分开：前者是「bundle 本身被
    换了」，后者是「bundle 没换但 declared 清册被换了」。合并成一个 code 之后，
    「拿另一个 entry 的 tag 清册来对本 entry 的文档」会被 bundle 那条遮蔽。
    """

    error_code = "word_entry_instrumentation_digest_mismatch"


class WordEntryTagSetDriftError(WordEntryGateError):
    """WG-1：declared tag 集合与文档实测集合不符（缺失 / 多余各是一条成因）。"""

    error_code = "word_entry_tag_set_drift"


class WordEntryHierarchyDriftError(WordEntryGateError):
    """WG-2：SDT 层级漂移（container path 变了，或 block 容器没再包住同 key 的 field）。

    与 `word_sdt_engine.WordTagHierarchyDriftError` 分工不同，两者都要保留：
    engine 那条按**文档内实测到的** block tag 判「field 有没有跑出 block」，因此 block
    容器**整个被删掉**时它的判据为空集 ⇒ 恒真；本条按**契约声明的载体**判，删掉容器
    立刻打红。删掉本条不是「行为不变」，而是那种漂移彻底无人把守。
    """

    error_code = "word_entry_sdt_hierarchy_drift"


class WordEntryInstanceCountDriftError(WordEntryGateError):
    """WG-3：字段实例计数与声明不符（含重复实例）。"""

    error_code = "word_entry_field_instance_count_drift"


class WordEntryBlockedCarrierError(WordEntryGateError):
    """契约用到了 Task 6 证伪的载体，或 blocked/allowed 两张表被改成有交集。"""

    error_code = "word_entry_blocked_carrier_refused"


class WordEntryDegradedAnchorError(WordEntryGateError):
    """降级锚点（alias / sdt_id / paragraph_index / run_index）没有被门真正拒掉。"""

    error_code = "word_entry_degraded_anchor_refused"


class WordEntryWordOnlyCoverageError(WordEntryGateError):
    """Word-only 等值报告的覆盖计数为空 —— `equivalent=True` 是空转，不得当通过。"""

    error_code = "word_entry_word_only_coverage_empty"


class WordEntryDuplicateConflictError(WordEntryGateError):
    """同 stable tag 多实例异值产生了未裁决的 duplicate 冲突（AC 7.4）。"""

    error_code = "word_entry_unresolved_duplicate_conflict"


class WordEntryCandidateEvidenceError(WordEntryGateError):
    """candidate 的 instrumentation 证据缺失、digest 不符或未通过。"""

    error_code = "word_entry_candidate_evidence_invalid"


class WordEntryFinalizeGateBlockedError(WordEntryGateError):
    """gate 装配不全，或 candidate 与本次 entry scope 不符。"""

    error_code = "word_entry_finalize_gate_blocked"


#: 本模块可能抛出的**全部**失败 code（含两条刻意委派出去的）。守卫据它断言
#: 「每类各自真触发一次、基数等于登记数、code 互不相同」—— 比「每类各测一遍」强：
#: 后者在两类被合并成同一 code 时**全部仍绿**。
WORD_ENTRY_FAILURE_CODES: Final[tuple[str, ...]] = (
    WordEntryFrozenBundleDigestMismatchError.error_code,
    WordEntryInstrumentationDigestMismatchError.error_code,
    WordEntryTagSetDriftError.error_code,
    WordEntryHierarchyDriftError.error_code,
    WordEntryInstanceCountDriftError.error_code,
    WordEntryBlockedCarrierError.error_code,
    WordEntryDegradedAnchorError.error_code,
    WordEntryWordOnlyCoverageError.error_code,
    WordEntryDuplicateConflictError.error_code,
    WordEntryCandidateEvidenceError.error_code,
    WordEntryFinalizeGateBlockedError.error_code,
    # 委派项：per-entry contract child 未 approved 的单一真源是 Task 36 的 FS-6，
    # Word-only 区域漂移的单一真源是 Task 13 的 `UnmanagedRegionReport`。
    PerEntryContractUnapprovedError.error_code,
    UnmanagedRegionDriftError.error_code,
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 载体门与锚点门（Task 6 裁决恒拒，无 per-entry 豁免）
# ═══════════════════════════════════════════════════════════════════════════


def blocked_anchor_names(gate: CarrierGate | None = None) -> tuple[str, ...]:
    """Task 6 裁决为**不可用**的锚点名（现读 JSON，不写第二份清单）。"""
    g = gate or load_word_carrier_gate()
    return tuple(sorted(g.blocked_anchors))


def blocked_carrier_names(gate: CarrierGate | None = None) -> tuple[str, ...]:
    """Task 6 裁决为**不可用**的载体名（现读 JSON）。"""
    g = gate or load_word_carrier_gate()
    return tuple(sorted(g.blocked_carriers))


def tag_anchor_name(gate: CarrierGate | None = None) -> str:
    """本 gate 使用的**唯一**锚点名 —— 取 allowlist 的唯一元素。

    刻意不写 `"w_tag"` 字面量：allowlist 里出现第二个锚点时本函数立刻 fail closed，
    而写死字面量的版本会继续用旧锚点、把「新增了一个可用锚点」这件事静静吞掉。
    """
    g = gate or load_word_carrier_gate()
    if len(g.allowed_anchors) != 1:
        raise WordEntryDegradedAnchorError(
            f"{g.source_path.name} 的 `anchors_allowed` 现算 {sorted(g.allowed_anchors)} "
            f"（{len(g.allowed_anchors)} 个）—— Requirement 7.1 只承认唯一正式协议锚点；"
            "多于一个时本 gate 无法判定「用的是哪个」，少于一个时整个 gate 不成立"
        )
    return next(iter(g.allowed_anchors))


def assert_only_tag_anchor_is_usable(
    *, gate: CarrierGate | None = None, entry_id: str
) -> str:
    """`w:tag` 可用、四个降级锚点**逐个真喂进门必须抛**（Requirement 7.1 / 7.8）。

    返回唯一锚点名。判据是**真实执行**：把 blocked 名字喂给
    `CarrierGate.assert_anchor` 看它是否抛，而不是在源码里搜这些字符串。
    """
    g = gate or load_word_carrier_gate()
    if g.document_type != WORD_DOCUMENT_TYPE:
        raise WordEntryBlockedCarrierError(
            f"entry {entry_id}: 载体门是 {g.document_type!r} 域的，不能用于 Word entry gate"
        )
    anchor = tag_anchor_name(g)
    g.assert_anchor(anchor, location=f"entry {entry_id}")
    blocked = blocked_anchor_names(g)
    if not blocked:
        raise WordEntryDegradedAnchorError(
            f"entry {entry_id}: {g.source_path.name} 的 `anchors_blocked` 是空集 —— "
            "分母为空时「降级锚点恒拒」是重言式，必须有真实被证伪的锚点"
        )
    leaked: list[str] = []
    for name in blocked:
        # 🔴 只接**门自己的**窄类型。写 `except Exception` 会把「调用签名写错了」
        #    「门内部 AttributeError」一并读成「它正确拒绝了」—— 那正是本 spec 记的
        #    最贵一类 fail-open（AC 5.12 逐字禁止）。
        try:
            g.assert_anchor(name, location=f"entry {entry_id}")
        except ContractCarrierGateError as exc:
            if not str(exc).strip():
                raise WordEntryDegradedAnchorError(
                    f"entry {entry_id}: 锚点 {name!r} 被拒但没有给出理由 —— "
                    "无理由的拒绝无法区分「真拒」与「空实现」"
                ) from exc
            continue
        leaked.append(name)
    if leaked:
        raise WordEntryDegradedAnchorError(
            f"entry {entry_id}: 降级锚点 {leaked} 未被 {g.source_path.name} 的门拒掉 —— "
            "Task 6 已裁定 alias/sdt_id 不唯一、paragraph_index/run_index failed；"
            "它们一个都不得作为定位键（Requirement 7.1 / Property 30 / 34）"
        )
    return anchor


def assert_blocked_carriers_have_no_exemption(
    *, gate: CarrierGate | None = None, entry_id: str, contract: SyncContract | None = None
) -> tuple[str, ...]:
    """blocked 载体恒拒：blocked 非空、与 allowed 无交集、逐个喂进门必抛、契约不声明。

    **没有** per-entry 豁免参数。`row_sdt` 之所以恒拒不是因为本函数写了它的名字，
    而是因为它在 `downstream_gate.carriers_blocked` 里；某个 entry「只差 row 就能过」
    在本签名上无处表达。
    """
    g = gate or load_word_carrier_gate()
    blocked = blocked_carrier_names(g)
    if not blocked:
        raise WordEntryBlockedCarrierError(
            f"entry {entry_id}: {g.source_path.name} 的 `carriers_blocked` 是空集 —— "
            "分母为空时「被证伪的载体恒拒」是重言式"
        )
    overlap = sorted(set(blocked) & set(g.allowed_carriers))
    if overlap:
        raise WordEntryBlockedCarrierError(
            f"entry {entry_id}: 载体 {overlap} 同时出现在 allowlist 与 blocklist —— "
            "两张表有交集时「恒拒」失效（首个非法载体: "
            f"{overlap[0]}）"
        )
    leaked: list[str] = []
    for name in blocked:
        # 同上：只接窄类型，禁 `except Exception`。
        try:
            g.assert_carrier(name, location=f"entry {entry_id}")
        except ContractCarrierGateError:
            continue
        leaked.append(name)
    if leaked:
        raise WordEntryBlockedCarrierError(
            f"entry {entry_id}: 被 Task 6 证伪的载体 {leaked} 未被门拒掉 —— OO 9.4 在"
            "首次序列化时就把 `w:tbl` 下的 `w:sdt` 拆掉，任何依赖它的 entry 必须先经 "
            "design 换载体，不得单点豁免"
        )
    if contract is not None:
        for carrier in contract.identity_carriers:
            g.assert_carrier(carrier, location=f"entry {entry_id} contract identity_carriers")
    return blocked


# ═══════════════════════════════════════════════════════════════════════════
# 4. declared 清册（三边锁的第一、二边）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordTagInventory:
    """一个 Word entry 的**冻结** tag 清册。

    Attributes:
        tags: 已冻结的 declared tag 集合（有序去重；来自 instrumentation payload）。
        row_uuids: declared 行身份集合（无行域字段时为空元组）。
        block_containers: 内层 field tag → 外层 block 容器 tag（由**契约**的载体声明
            推出：`sdt_tag` 以 `gt:block:` 开头的字段必然有同 key 的内层 field tag，
            这是 Task 59 `expected_tags()` 的落库形态）。
        declared_instances: stable key → 契约声明的 `instances`（`one` / `many`）。
        managed_instance_total: 已冻结的受管 SDT 实例总数（`instance_count` 扣掉
            `untagged_sdt_count`）。
        frozen_hierarchy: 已冻结的 tag → container path 列表（注入时实测）。
    """

    entry_id: str
    contract_id: str
    tags: tuple[str, ...]
    row_uuids: tuple[str, ...]
    block_containers: Mapping[str, str]
    declared_instances: Mapping[str, str]
    managed_instance_total: int
    frozen_hierarchy: Mapping[str, tuple[str, ...]]

    def instance_expectation(self, tag: str) -> int:
        """该 tag 在注入时冻结的**实例个数** —— 层级表里每个实例一条 container path。

        这就是 AC 7.10 的「字段实例计数」：契约的 `instances` 只有 one/many 两档，
        精确值只有这里有。
        """
        return len(self.frozen_hierarchy.get(tag, ()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "contract_id": self.contract_id,
            "tag_count": len(self.tags),
            "tags": list(self.tags),
            "row_uuids": list(self.row_uuids),
            "block_containers": dict(sorted(self.block_containers.items())),
            "declared_instances": dict(sorted(self.declared_instances.items())),
            "managed_instance_total": self.managed_instance_total,
            "frozen_hierarchy": {
                tag: list(paths) for tag, paths in sorted(self.frozen_hierarchy.items())
            },
        }


def _require_mapping(value: Any, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, AbcMapping):
        raise WordEntryCandidateEvidenceError(
            f"{where} 必须是对象，实得 {type(value).__name__}"
        )
    return value


def _block_kind_of(spec: FieldSpec) -> str:
    """契约字段声明的载体 kind（`field` / `block`），只看 `sdt_tag` 的第二段。"""
    ref = parse_sdt_tag(str(spec.sdt_tag or ""))
    if ref is None:
        raise WordEntryTagSetDriftError(
            f"契约字段 {spec.stable_field_key!r} 的 sdt_tag={spec.sdt_tag!r} 不是本方案的 "
            "`gt:{field|block}:{contract}:{key}` 形态 —— 受管字段必须逐条声明 tag，"
            "不得按中文标题或段落位置推断（Requirement 7.1）"
        )
    return ref.kind


def declared_tag_inventory(
    *,
    contract: SyncContract,
    instrumentation_payload: Mapping[str, Any],
    readback: Mapping[str, Any],
    entry_id: str,
) -> WordTagInventory:
    """把三边中的**前两边**合成一份冻结清册；两边不一致即 fail closed。

    第一边 = 已冻结的 instrumentation definition payload（`sdt_tags` / `row_uuids`）；
    第二边 = 已冻结的 per-entry contract（每字段的 `sdt_tag` 与 `instances`）；
    实例总数与层级取自 candidate 证据里的 `tag_readback`（注入时的实测事实，其
    digest 已被 candidate 行锁住）。

    交叉判据（每条都能单独短路，故每条都有自己的变异锚点）：

    1. payload 的 `sdt_tags` 必须非空、有序去重（有序等值 + 无重复双断言）；
    2. 每个 declared tag 的 contract 段必须等于 frozen contract 的 `contract_id`；
    3. 契约每个字段的 `sdt_tag` 必须出现在 declared 集合里（契约 → instrumentation）；
    4. block 载体字段必须同时有内层 field tag（Task 6 的 depth=2 形态）；
    5. 每个 declared 的**非行域** tag 必须能被契约解析回一个字段
       （instrumentation → 契约，防「注入了契约不认的 tag」）。
    """
    raw_tags = instrumentation_payload.get("sdt_tags")
    if not isinstance(raw_tags, (list, tuple)) or not raw_tags:
        raise WordEntryTagSetDriftError(
            f"entry {entry_id}: 冻结的 instrumentation payload 里 `sdt_tags` 为空或非列表 —— "
            "空清册会让「tag 集合等值」变成空集恒真（假绿第⑥源）"
        )
    tags = tuple(str(t).strip() for t in raw_tags)
    if any(not t for t in tags):
        raise WordEntryTagSetDriftError(
            f"entry {entry_id}: 冻结 `sdt_tags` 里有空串项 —— 空 tag 无法定位"
        )
    if len(set(tags)) != len(tags):
        duplicated = sorted({t for t in tags if tags.count(t) > 1})
        raise WordEntryTagSetDriftError(
            f"entry {entry_id}: 冻结 `sdt_tags` 有重复项 {duplicated} —— 清册是集合，"
            "重复项会让「实例计数」判据的期望值含义不明"
        )
    if list(tags) != sorted(tags):
        raise WordEntryTagSetDriftError(
            f"entry {entry_id}: 冻结 `sdt_tags` 未按字典序排列 —— 顺序不稳定时"
            "「首个漂移 tag」不可复现（AC 6.10 要求可复现的首个位置）"
        )

    for tag in tags:
        ref = parse_sdt_tag(tag)
        if ref is None:
            raise WordEntryTagSetDriftError(
                f"entry {entry_id}: 冻结 tag {tag!r} 不是 `gt:` 方案形态"
            )
        if ref.contract_id != contract.contract_id:
            raise WordEntryTagSetDriftError(
                f"entry {entry_id}: 冻结 tag {tag!r} 的 contract 段与 frozen contract "
                f"{contract.contract_id!r} 不符 —— 不得拿另一个 entry 的 tag 清册来校验"
                "本 entry（Property 28 / 禁跨 entry 复用）"
            )

    declared = set(tags)
    block_containers: dict[str, str] = {}
    declared_instances: dict[str, str] = {}
    for spec in contract.all_fields():
        tag = str(spec.sdt_tag or "").strip()
        if not spec.row_scoped:
            # 🔴 行域字段**不**进 `declared_instances`：它的 `stable_field_key` 是含
            #    `{row_uuid}` 占位的模板，而实测键是已实例化的具体 key，两者永不相等 ⇒
            #    放进去只会得到「实测 0 个 ⇒ 跳过」这种恒真项。行域的实例形态由
            #    `row_uuids` 与 engine 的 `WordRowInventory` 负责；本 lane（F2）行域字段
            #    实测 0 个，故 Requirement 7.2 的行计数在本任务**分母为空、不宣称通过**。
            declared_instances[spec.stable_field_key] = str(spec.instances)
        if spec.row_scoped:
            # 行域字段的 tag 是模板（含 `{row_uuid}` 占位），实例化后的具体 tag 由
            # instrumentation 的 `row_uuids` 决定；此处只校验模板形态（已由
            # `contracts._parse_field` 强制含 row_uuid），不参与集合等值。
            continue
        if tag not in declared:
            raise WordEntryTagSetDriftError(
                f"entry {entry_id}: 契约字段 {spec.stable_field_key!r} 声明的 tag {tag!r} "
                f"不在冻结 instrumentation 清册里（cause={TAG_SET_DRIFT_CAUSES[0]}）—— "
                "契约与 instrumentation 必须逐项对齐，否则运行态会去找一个从未注入的 tag"
            )
        if _block_kind_of(spec) == "block":
            from app.services.workpaper_sync.word_sdt_engine import format_sdt_tag

            inner = format_sdt_tag(
                kind="field",
                contract_id=contract.contract_id,
                stable_key=spec.stable_field_key,
            )
            if inner not in declared:
                raise WordEntryTagSetDriftError(
                    f"entry {entry_id}: 字段 {spec.stable_field_key!r} 用 block 载体，"
                    f"但冻结清册里没有内层 field tag {inner!r} —— Task 6 实测 block 形态是"
                    "「外层 block 容器 + 内层同 key field 叶子」（depth=2），缺内层意味着"
                    "值没有写入目标"
                )
            block_containers[inner] = tag

    contract_tags = {
        str(spec.sdt_tag or "").strip()
        for spec in contract.all_fields()
        if not spec.row_scoped
    } | set(block_containers)
    row_scoped_declared: list[str] = []
    for tag in tags:
        ref = parse_sdt_tag(tag)
        assert ref is not None  # 上一轮已逐个校验过
        if ref.row_scoped:
            row_scoped_declared.append(str(ref.row_uuid))
            continue
        if tag not in contract_tags:
            raise WordEntryTagSetDriftError(
                f"entry {entry_id}: 冻结清册里的 tag {tag!r} 在 per-entry contract 里没有"
                f"对应字段（cause={TAG_SET_DRIFT_CAUSES[1]}）—— 受管字段必须逐条声明，"
                "instrumentation 不得注入契约不认的 tag（Requirement 6.20 / 7.1）"
            )

    payload_rows = instrumentation_payload.get("row_uuids") or ()
    row_uuids = tuple(sorted({str(u).strip() for u in payload_rows if str(u).strip()}))
    if sorted(set(row_scoped_declared)) != list(row_uuids):
        raise WordEntryTagSetDriftError(
            f"entry {entry_id}: 冻结清册的行域 tag 携带 row_uuid "
            f"{sorted(set(row_scoped_declared))}，与 payload 声明的 {list(row_uuids)} 不符 —— "
            "行身份必须落在 tag 内且与 instrumentation 声明一致（Requirement 7.2）"
        )

    for key in REQUIRED_WORD_READBACK_KEYS:
        if key not in readback:
            raise WordEntryCandidateEvidenceError(
                f"entry {entry_id}: candidate 证据的 `tag_readback` 缺键 {key!r} —— "
                "冻结的实例总数与层级缺任何一项，对应判据都会退化成空转"
            )
    total = int(readback["instance_count"]) - int(readback["untagged_sdt_count"])
    if total <= 0:
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 冻结的受管 SDT 实例总数现算为 {total} —— 注入时一个受管"
            "实例都没有，后续「实例计数等值」是空集恒真"
        )
    frozen_hierarchy_raw = _require_mapping(
        readback["hierarchy"], where=f"entry {entry_id}.tag_readback.hierarchy"
    )
    frozen_hierarchy = {
        str(tag): tuple(sorted(str(p) for p in (paths or ())))
        for tag, paths in frozen_hierarchy_raw.items()
    }
    if sorted(frozen_hierarchy) != list(tags):
        raise WordEntryTagSetDriftError(
            f"entry {entry_id}: 冻结层级表覆盖的 tag {sorted(frozen_hierarchy)[:3]}… 与冻结 "
            f"`sdt_tags` {list(tags)[:3]}… 不是同一集合 —— 两份冻结事实自相矛盾时"
            "不得按其中任意一份放行"
        )
    # 🔴 两份冻结事实的**内部**自洽：逐 tag 层级表的条目总数（= 每个实例一条
    #    container path）必须等于 `instance_count - untagged_sdt_count`。这不是运行态
    #    判据的重复，而是「证据自己是否可信」—— 不自洽时后面拿 `len(frozen_hierarchy[tag])`
    #    当每 tag 期望实例数就没有依据。
    hierarchy_total = sum(len(paths) for paths in frozen_hierarchy.values())
    if hierarchy_total != total:
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: candidate 证据自相矛盾 —— 层级表现算 {hierarchy_total} 个"
            f"受管实例，而 instance_count - untagged 现算 {total}；两份冻结事实不一致时"
            "不得据其中任意一份放行"
        )
    inventory = WordTagInventory(
        entry_id=entry_id,
        contract_id=contract.contract_id,
        tags=tags,
        row_uuids=row_uuids,
        block_containers=dict(sorted(block_containers.items())),
        declared_instances=dict(sorted(declared_instances.items())),
        managed_instance_total=total,
        frozen_hierarchy=frozen_hierarchy,
    )
    # 🔴 两份冻结声明的**互锁**（发布期判据，与运行期的文档漂移判据是不同事件）：
    #    契约的 `instances` 只有 one/many 两档，冻结层级表里有精确个数 —— 两者必须自洽。
    #    不锁的后果：契约声明 `one` 而 instrumentation 注了 2 个实例时，运行态两条判据
    #    各自都「与自己那份声明一致」，谁都不打红。
    for key, declared in sorted(declared_instances.items()):
        tag = _tag_of_key(inventory, key)
        frozen_count = inventory.instance_expectation(tag)
        expected_bucket = "one" if frozen_count == 1 else "many"
        if declared != expected_bucket:
            raise WordEntryInstanceCountDriftError(
                f"entry {entry_id}: 字段 {key!r} 的契约声明 instances={declared!r} 与冻结 "
                f"instrumentation 的实例个数 {frozen_count} 不自洽（cause="
                f"{INSTANCE_DRIFT_CAUSES[0]}，tag={tag!r}）—— 两份 approved 声明互相矛盾时"
                "不得据其中任意一份放行（Requirement 7.10）"
            )
    return inventory


# ═══════════════════════════════════════════════════════════════════════════
# 5. 文档实测（三边锁的第三边；只经 `w:tag`）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordEntryObservation:
    """一次 extract 的 tag 形状投影。

    `xpath` 只作**报告用位置**（AC 7.4「列出全部 OO 位置」/ AC 6.10「指出首个漂移」），
    绝不参与定位 —— 定位键只有 tag。`container_path`（`body/p`、`body/tbl/tr/tc/p`、
    `body/sdt(...)/p`）不含任何序号，因此**插删段落不改变它**，可以安全地当层级判据；
    真正会随插删漂移的 `xpath` 只出现在错误文案里。
    """

    entry_id: str
    tags: tuple[str, ...]
    instance_counts: Mapping[str, int]
    first_xpath: Mapping[str, str]
    xpaths: Mapping[str, tuple[str, ...]]
    hierarchy: Mapping[str, tuple[str, ...]]
    ancestor_tags: Mapping[str, tuple[tuple[str, ...], ...]]
    managed_instance_total: int
    unmanaged_sdt_count: int
    key_counts: Mapping[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "tag_count": len(self.tags),
            "tags": list(self.tags),
            "instance_counts": dict(sorted(self.instance_counts.items())),
            "managed_instance_total": self.managed_instance_total,
            "unmanaged_sdt_count": self.unmanaged_sdt_count,
            "key_counts": dict(sorted(self.key_counts.items())),
        }


def observe_word_entry(extracted: WordExtractOutcome, *, entry_id: str) -> WordEntryObservation:
    """把 `WordExtractOutcome` 投影成 tag 形状的实测事实（不做任何判定）。"""
    instances: Sequence[WordSdtInstance] = extracted.instances
    counts: dict[str, int] = {}
    key_counts: dict[str, int] = {}
    first: dict[str, str] = {}
    xpaths: dict[str, list[str]] = {}
    hierarchy: dict[str, list[str]] = {}
    ancestors: dict[str, list[tuple[str, ...]]] = {}
    for inst in sorted(instances, key=lambda i: (i.tag.raw, i.xpath)):
        raw = inst.tag.raw
        counts[raw] = counts.get(raw, 0) + 1
        first.setdefault(raw, inst.xpath)
        xpaths.setdefault(raw, []).append(inst.xpath)
        hierarchy.setdefault(raw, []).append(inst.container_path)
        ancestors.setdefault(raw, []).append(tuple(inst.ancestor_tags))
        if not (inst.tag.kind == "block" and inst.has_nested_sdt):
            # block 容器只提供层级、不承载值 —— 与 engine 的 `by_key` 同一口径，
            # 否则同一 stable key 会凭空多出一个「实例」，`instances` 判据全部失真。
            key_counts[inst.tag.stable_key] = key_counts.get(inst.tag.stable_key, 0) + 1
    return WordEntryObservation(
        entry_id=entry_id,
        tags=tuple(sorted(counts)),
        instance_counts=dict(sorted(counts.items())),
        first_xpath=dict(sorted(first.items())),
        xpaths={tag: tuple(v) for tag, v in sorted(xpaths.items())},
        hierarchy={tag: tuple(sorted(v)) for tag, v in sorted(hierarchy.items())},
        ancestor_tags={tag: tuple(v) for tag, v in sorted(ancestors.items())},
        managed_instance_total=len(instances),
        unmanaged_sdt_count=int(extracted.unmanaged_sdt_count),
        key_counts=dict(sorted(key_counts.items())),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 四条 tagged-SDT 判据（各自独立，各指出首个漂移 tag/XPath）
# ═══════════════════════════════════════════════════════════════════════════


def assert_tag_set_matches(
    inventory: WordTagInventory, observation: WordEntryObservation, *, entry_id: str
) -> None:
    """WG-1：declared tag 集合 ↔ 实测集合，缺失与多余各一条成因。

    行域 tag 单独处理：审计师可增删行，因此「declared 行域 tag 少了一个」是行集合变化
    而不是 tag retention 失败；但**非行域** tag 少一个就是 Requirement 7.8 的
    「tag 丢失」，必须 fail closed 且**不得**回退段落索引/正则/placeholder 文本。
    """
    declared_static = tuple(tag for tag in inventory.tags if not _is_row_tag(tag))
    observed = set(observation.tags)
    missing = [tag for tag in declared_static if tag not in observed]
    if missing:
        raise WordEntryTagSetDriftError(
            f"entry {entry_id}: 冻结清册声明的 tag 在文档里找不到（cause="
            f"{TAG_SET_DRIFT_CAUSES[0]}）；首个漂移 tag={missing[0]!r}，"
            f"共缺 {len(missing)} 个（{missing[:5]}）—— extract fail closed。"
            "**不得**回退段落绝对索引、中文正则或已替换 placeholder 文本"
            "（Requirement 7.1 / 7.8 / Property 30 / 34）"
        )
    unregistered = [tag for tag in observation.tags if tag not in set(inventory.tags)]
    if unregistered:
        first = unregistered[0]
        raise WordEntryTagSetDriftError(
            f"entry {entry_id}: 文档里出现冻结清册未登记的受管 tag（cause="
            f"{TAG_SET_DRIFT_CAUSES[1]}）；首个漂移 tag={first!r} @ "
            f"{observation.first_xpath.get(first, '<no-xpath>')}，共 "
            f"{len(unregistered)} 个 —— 模板被二次注入或被别的 entry 的 tag 污染"
        )


def _is_row_tag(tag: str) -> bool:
    """tag 是否行域（行身份在 tag 内部，不看行号）。

    冻结清册里的每个 tag 都已在 :func:`declared_tag_inventory` 里逐个解析过，因此这里
    解析失败只可能是有人绕过了那道校验 —— 此时**抛**而不是当成「非行域」继续。
    """
    ref = parse_sdt_tag(tag)
    if ref is None:
        raise WordEntryTagSetDriftError(
            f"冻结清册里出现无法解析的 tag {tag!r} —— 上游形态校验被绕过，"
            "不得按「当它不是受管字段」继续"
        )
    return ref.row_scoped


def assert_sdt_hierarchy_intact(
    inventory: WordTagInventory, observation: WordEntryObservation, *, entry_id: str
) -> None:
    """WG-2：层级两条独立判据。

    每个 tag 的 container path **集合**必须与注入时冻结的一致。container path 不含序号
    （`body/p`、`body/sdt(field_block:gt:block:…)/p`、`body/tbl/tr/tc/p`），因此插删段落
    **不会**触发本条 —— 会触发它的是「字段被搬进/搬出表格」「block 包裹被拆掉」这类
    真实结构漂移。

    比**集合**而不是多重集是刻意的：实例**个数**变化由 WG-3 独占，两条判据覆盖同一
    形态时短路任一条都不改变行为（变异必 GREEN）。

    engine 侧的 `_assert_hierarchy` 判的是另一件事（block tag 存在时 field 是否还在它
    内部、行域字段是否还在单元格里），它**不看** container path，因此本条不是重复判据。
    """
    for tag in inventory.tags:
        ref = parse_sdt_tag(tag)
        if ref is None or ref.row_scoped:
            continue
        want = frozenset(inventory.frozen_hierarchy.get(tag, ()))
        got = frozenset(observation.hierarchy.get(tag, ()))
        if got and want != got:
            raise WordEntryHierarchyDriftError(
                f"entry {entry_id}: tag {tag!r} 的 SDT 层级漂移（cause="
                f"{HIERARCHY_DRIFT_CAUSES[0]}）：冻结 {sorted(want)} → 实测 {sorted(got)}；"
                f"首个漂移位置 {observation.first_xpath.get(tag, '<no-xpath>')} —— "
                "层级变了之后按 tag 读到的值不再属于原来的结构位置，禁止继续写格"
                "（Requirement 6.10 / 7.5）"
            )


def assert_field_instance_counts(
    inventory: WordTagInventory,
    observation: WordEntryObservation,
    *,
    entry_id: str,
) -> None:
    """WG-3：**逐 tag 精确**实例计数（AC 7.10「字段实例计数」的运行期判据）。

    期望值来自注入时冻结的层级表（每个实例一条 container path），因此它是真的精确
    计数，而不是契约 `one`/`many` 两档的近似。`${entityName}` 从 2 处掉到 1 处时 tag
    集合完全相同、`many` 档也仍然「≥1」，只有本条会打红。

    发布期的另一件事（契约声明与冻结实例数互相矛盾）由 :func:`declared_tag_inventory`
    的 `INSTANCE_DRIFT_CAUSES[0]` 守；`instances='one'` 出现多实例在 extract 阶段就被
    `word_sdt_engine._assert_instance_counts` 拒掉。三者事件不同、互不覆盖。

    行域 tag 排除（审计师可增删行，行集合本身可变）。
    """
    for tag in inventory.tags:
        if _is_row_tag(tag):
            continue
        want = inventory.instance_expectation(tag)
        got = int(observation.instance_counts.get(tag, 0))
        if got and got != want:
            raise WordEntryInstanceCountDriftError(
                f"entry {entry_id}: tag {tag!r} 的实例计数由冻结的 {want} 变为实测 {got}"
                f"（cause={INSTANCE_DRIFT_CAUSES[1]}）；首个位置 "
                f"{observation.first_xpath.get(tag, '<no-xpath>')}，全部位置 "
                f"{list(observation.xpaths.get(tag, ()))} —— 同 tag 少/多一个实例都必须 "
                "fail closed（Requirement 7.10「字段实例计数」）"
            )


def _tag_of_key(inventory: WordTagInventory, stable_key: str) -> str:
    """stable key → 它的**值载体** tag（block 形态取内层 field tag）。"""
    for tag in inventory.tags:
        ref = parse_sdt_tag(tag)
        if ref is None or ref.kind != "field":
            continue
        if ref.stable_key == stable_key:
            return tag
    return stable_key


def assert_word_only_equivalent(
    report: UnmanagedRegionReport,
    *,
    entry_id: str,
    required_coverage: Sequence[str] = WORD_ONLY_COVERAGE_REQUIRED,
) -> Mapping[str, int]:
    """WG-4：SDT 外 Word-only 区域按 policy 等值 + **覆盖计数非空**。

    等值判据本身**委派** Task 13 的 `UnmanagedRegionReport.assert_equivalent()`
    （单一真源，抛 `UnmanagedRegionDriftError`）。本函数只加两件 Task 59 没有的：

    * `inspected_aspects` 必须覆盖 `WORD_ONLY_ASPECTS` 全部六格（少一格就是少一条
      判据，而报告仍会说 `equivalent=True`）；
    * `required_coverage` 里的每一项覆盖计数必须 > 0 —— 手搓最小 DOCX 上「SDT 外
      正文」是空集，此时 `equivalent=True` 是空转（假绿第⑥源）。

    返回完整覆盖计数供调用方登记（含 `table_shape` / `managed_row_identity` 这类
    **entry 相关**的 0 值，见 :data:`WORD_ONLY_COVERAGE_REQUIRED` 的说明）。
    """
    missing_aspects = [a for a in WORD_ONLY_ASPECTS if a not in report.inspected_aspects]
    if missing_aspects:
        raise WordEntryWordOnlyCoverageError(
            f"entry {entry_id}: Word-only 报告没有逐项判定 aspect {missing_aspects} —— "
            "少一格判据时 `equivalent=True` 不代表那一格等值"
        )
    coverage_raw = _require_mapping(
        report.details.get("coverage", {}), where=f"entry {entry_id}.word_only.coverage"
    )
    coverage = {str(k): int(v) for k, v in coverage_raw.items()}
    empty = [name for name in required_coverage if int(coverage.get(name, 0)) <= 0]
    if empty:
        raise WordEntryWordOnlyCoverageError(
            f"entry {entry_id}: Word-only 等值报告的覆盖计数 {empty} 为 0 —— "
            f"实测 coverage={coverage}；空集上的「等值」是重言式，fixture 必须是真实"
            "权威模板派生的 candidate（Property 31）"
        )
    # 🔴 顺序：先覆盖后等值。反过来写时「空集 + equivalent=True」会先返回，
    #    覆盖判据变成不可达分支。
    report.assert_equivalent()
    return coverage


# ═══════════════════════════════════════════════════════════════════════════
# 7. candidate 证据（Task 59 写、本模块读；跨 entry 复用在此处 fail closed）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordCandidateEvidence:
    """candidate 的 instrumentation 证据投影（digest 已与 candidate 行比对通过）。"""

    entry_id: str
    payload: Mapping[str, Any]
    report_sha256: str
    template_definition_sha256: str
    instrumentation_definition_sha256: str
    instrumented_sha256: str
    rollback_source_sha256: str
    readback: Mapping[str, Any]
    visible_equivalence: Mapping[str, Any]
    probe_gate: Mapping[str, Any]


def parse_word_candidate_evidence(
    *, report_bytes: bytes, expected_sha256: str, entry_id: str
) -> WordCandidateEvidence:
    """读 candidate 的 instrumentation 证据并逐条校验它**真的**通过了。

    先比 digest 再解析：报告内容与 candidate 行登记的
    `visible_equivalence_report_sha256` 不符时，后面读到的一切都不属于这个 candidate
    —— 典型形态正是「拿另一个 entry 的 evidence 顶上」（AC 6.18 / 7.10 明禁）。
    """
    if not is_digest(expected_sha256):
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: candidate 登记的 visible_equivalence_report_sha256 非法: "
            f"{expected_sha256!r} —— 没有反读等值证据不得 finalize"
        )
    observed = hashlib.sha256(report_bytes).hexdigest()
    if observed != expected_sha256:
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 证据报告实测 digest {observed} 与 candidate 登记的 "
            f"{expected_sha256} 不一致 —— 禁止用别的 candidate/entry 的 evidence 顶替"
        )
    try:
        payload = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 证据报告不是合法 UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(payload, AbcMapping):
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 证据报告根必须是对象，实得 {type(payload).__name__}"
        )
    missing = [
        key
        for key in REQUIRED_WORD_EVIDENCE_KEYS
        if key not in payload or payload.get(key) in (None, "", {}, [])
    ]
    if missing:
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 证据报告缺键或值为空 {missing} —— 证据不完整不得 finalize"
        )
    if str(payload["schema_version"]) != WORD_UPGRADE_EVIDENCE_SCHEMA:
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 证据 schema_version={payload['schema_version']!r}，"
            f"本 gate 只读 {WORD_UPGRADE_EVIDENCE_SCHEMA!r}（Task 59 的 upgrader 写侧）"
        )
    if str(payload["entry_id"]) != entry_id:
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 证据属于 entry {payload['entry_id']!r} —— 不得跨 entry "
            "复用 candidate evidence（Property 70 / Task 77 正文）"
        )
    if str(payload["document_type"]) != WORD_DOCUMENT_TYPE:
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 证据 document_type={payload['document_type']!r} —— "
            f"Word entry gate 只受理 {WORD_DOCUMENT_TYPE!r}"
        )
    equivalence = _require_mapping(
        payload["visible_equivalence"], where=f"entry {entry_id}.visible_equivalence"
    )
    if equivalence.get("equivalent") is not True:
        bad = sorted(
            aspect
            for aspect, ok in (equivalence.get("preserved_aspects") or {}).items()
            if not ok
        )
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: instrumentation 的可见等价未通过，首批不等价 aspect "
            f"{bad} —— 注入破坏了可见业务正文（Requirement 7.3 / 9.9）"
        )
    coverage = _require_mapping(
        equivalence.get("coverage") or {}, where=f"entry {entry_id}.visible_equivalence.coverage"
    )
    if int(coverage.get("visible_text_chars", 0)) <= 0:
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 可见等价报告的 `visible_text_chars` 为 0 —— 空文档上的"
            "「可见文本流逐字符相同」是重言式，证据必须来自真实权威模板"
        )
    readback = _require_mapping(
        payload["tag_readback"], where=f"entry {entry_id}.tag_readback"
    )
    if int(readback.get("untagged_sdt_count", -1)) != 0:
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 注入时留下了 "
            f"{readback.get('untagged_sdt_count')!r} 个无 tag 的 SDT —— 无 tag 的 SDT 无法"
            "定位，等于制造不可读区域"
        )
    if readback.get("duplicate_row_uuids"):
        raise WordEntryCandidateEvidenceError(
            f"entry {entry_id}: 注入时出现重复 row_uuid "
            f"{list(readback['duplicate_row_uuids'])} —— 行身份必须唯一（Requirement 7.2）"
        )
    probe_gate = _require_mapping(
        payload["probe_gate"], where=f"entry {entry_id}.probe_gate"
    )
    for key in ("carrier_contract_sha256", "onlyoffice_build"):
        if not str(probe_gate.get(key) or "").strip():
            raise WordEntryCandidateEvidenceError(
                f"entry {entry_id}: 证据缺 probe_gate.{key} —— tagged SDT 载体必须先过"
                "真实 OnlyOffice 9.4 黑盒探针（Requirement 6.16 / Task 6）"
            )
    for key in (
        "template_definition_sha256",
        "instrumentation_definition_sha256",
        "instrumented_sha256",
        "rollback_source_sha256",
    ):
        if not is_digest(payload.get(key)):
            raise WordEntryCandidateEvidenceError(
                f"entry {entry_id}: 证据的 {key} 非法: {payload.get(key)!r}"
            )
    return WordCandidateEvidence(
        entry_id=entry_id,
        payload=dict(payload),
        report_sha256=observed,
        template_definition_sha256=str(payload["template_definition_sha256"]).strip(),
        instrumentation_definition_sha256=str(
            payload["instrumentation_definition_sha256"]
        ).strip(),
        instrumented_sha256=str(payload["instrumented_sha256"]).strip(),
        rollback_source_sha256=str(payload["rollback_source_sha256"]).strip(),
        readback=dict(readback),
        visible_equivalence=dict(equivalence),
        probe_gate=dict(probe_gate),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. 冻结身份摘要（传给 Task 15 的两个 digest）
# ═══════════════════════════════════════════════════════════════════════════


def word_entry_structure_hash(
    *, contract: SyncContract, inventory: WordTagInventory
) -> str:
    """tag 形状的 structure hash（**无** sheet/cell/列名，也无任何段落序号）。"""
    return canonical_digest(
        {
            "schema_version": WORD_ENTRY_STRUCTURE_SCHEMA,
            "contract_sha256": contract.canonical_sha256,
            "tags": list(inventory.tags),
            "block_containers": dict(sorted(inventory.block_containers.items())),
            "hierarchy": {
                tag: list(paths)
                for tag, paths in sorted(inventory.frozen_hierarchy.items())
            },
            "row_uuids": list(inventory.row_uuids),
        }
    )


def word_engine_build_digest(
    *, binding: WordEngineBinding, inventory: WordTagInventory, anchor: str
) -> str:
    """冻结身份摘要，作为 representation 的 `adapter_build_digest`。

    它是一条 **identity**，不是「已存在 Word adapter 模块」的声明 ——
    `registry.PENDING_ENGINE_ADAPTERS` 仍禁止 `adapters/word.py`，放行门是 Task 61。
    """
    return canonical_digest(
        {
            "schema_version": WORD_ENGINE_BUILD_SCHEMA,
            "frozen_identity": dict(sorted(binding.frozen_identity.items())),
            "declared_instances": dict(sorted(inventory.declared_instances.items())),
            "managed_instance_total": inventory.managed_instance_total,
            "anchor": anchor,
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9. loader
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FrozenWordEntryDefinitions:
    """一个 Word entry 按 frozen FK/digest 加载出的完整、已校验身份。"""

    entry_id: str
    bundle: DefinitionBundleSnapshot
    contract: SyncContract
    contract_origin: str
    binding: WordEngineBinding
    inventory: WordTagInventory
    anchor: str
    blocked_carriers: tuple[str, ...]

    @property
    def adapter_id(self) -> str:
        """Word 侧 `adapter_id` = 契约 id（与 Excel 侧「adapter_id == 契约文件 stem」同约定）。"""
        return self.contract.contract_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "definition_bundle_id": str(self.bundle.bundle_id),
            "definition_bundle_sha256": self.bundle.bundle_sha256,
            "authority_model": self.bundle.authority_model.value,
            "authority_model_definition_id": str(self.bundle.authority_model_definition_id),
            "contract_id": self.contract.contract_id,
            "contract_origin": self.contract_origin,
            "contract_semantic_version": self.contract.semantic_version,
            "contract_sha256": self.contract.canonical_sha256,
            "adapter_id": self.adapter_id,
            "anchor": self.anchor,
            "blocked_carriers": list(self.blocked_carriers),
            "typed_slot_inventory": [
                list(item) for item in self.bundle.typed_slot_inventory
            ],
            "inventory": self.inventory.as_dict(),
        }


class WordEntryDefinitionLoader:
    """按 **frozen** `(bundle_id, bundle_sha256)` 加载并校验一个 Word entry 的身份。

    只读，不写任何行；**没有任何 alias 入口**（既不 import `DefinitionAliasRegistry`，
    也不按 entry_id 反查「现在该用哪个 bundle」）。加载顺序即判据（不可交换）：

    1. bundle row 按 FK 读（无 alias、无 entry 反查）；
    2. raw slot 形态六类分类 FS-1~FS-5（**委派** Task 36 的纯函数）；
    3. frozen digest 与 row 的 `canonical_payload_sha256` 一致；
    4. contract child 的 kind/state（FS-6，**先于** `load_bundle_snapshot`，否则
       Task 12 的 `BundleIntegrityError` 会把它永久遮蔽成不可达分支）；
    5. Task 12 `load_bundle_snapshot` 的 immutable children 深度校验 + canonical 重算；
    6. authority model 必须是 `projection_contract`（Word 的 tagged-SDT 岛按契约投影）；
    7. `WordEngineBinding(bundle_bound)` —— 一次性委派 Task 13 的三条判据
       （`assert_bundle_usable` / `assert_authority_model_contract_pairing` /
       `assert_contract_identity_frozen`，含磁盘契约 digest ↔ frozen slot digest）
       与 Task 6 的载体门；
    8. 锚点门与 blocked 载体门（真实执行，见第二节）；
    9. instrumentation payload 的 canonical digest ↔ frozen instrumentation slot digest；
    10. declared 清册三边锁。
    """

    def __init__(
        self, *, session: AsyncSession, resolution: CanonicalResolutionService
    ) -> None:
        self._session = session
        self._resolution = resolution

    # ─────────────────────────────────────────────────────────────────

    async def load(
        self,
        *,
        entry_id: str,
        contract: SyncContract,
        contract_origin: str,
        frozen_bundle_id: uuid.UUID,
        frozen_bundle_sha256: str,
        instrumentation_payload: Mapping[str, Any],
        readback: Mapping[str, Any],
        carrier_gate: CarrierGate | None = None,
    ) -> FrozenWordEntryDefinitions:
        """加载并校验；任一判据不过即 fail closed，不返回半成品。"""
        gate = carrier_gate or load_word_carrier_gate()
        row = await self._load_bundle_row(frozen_bundle_id, entry_id=entry_id)
        slots = assert_frozen_slots_shape(raw_slot_map_of(row))

        if not is_digest(frozen_bundle_sha256):
            raise WordEntryFrozenBundleDigestMismatchError(
                f"entry {entry_id}: 调用方给出的 frozen bundle digest 非法: "
                f"{frozen_bundle_sha256!r} —— frozen 身份必须显式且合法，"
                "禁止「留空就按当前 alias 取最新版」"
            )
        row_digest = str(getattr(row, "canonical_payload_sha256", "") or "").strip()
        if row_digest != frozen_bundle_sha256.strip():
            raise WordEntryFrozenBundleDigestMismatchError(
                f"entry {entry_id}: frozen bundle {frozen_bundle_id} 的 canonical digest "
                f"{row_digest!r} 与调用方冻结的 {frozen_bundle_sha256!r} 不一致 —— "
                "bundle approved 后不可修改或重组，历史身份不得按当前 alias 重新解析"
                "（Requirement 7.10 / Property 28）"
            )

        await self._assert_contract_child_approved(
            slots[BundleSlot.contract], entry_id=entry_id
        )

        bundle = await self._resolution.load_bundle_snapshot(frozen_bundle_id)
        # 🔴 这里**不**再写一条「authority model 必须是 projection_contract」：
        #    首版写过，变异检验（M26）实测 GREEN，追因后判定为**不可达**已删 ——
        #    `models.validate_bundle_slots` 对 custom/opaque 形态**要求** typed null
        #    marker，而 marker 会先被上面的 contract-child 判据（FS-6）拒掉；反过来
        #    projection 形态又必须三 child 全是 definition。也就是说「三 child 是
        #    definition 且 authority 非 projection」的 bundle 在发布期与 DB CHECK 两层
        #    都构造不出来。这条禁令的真正所有者是 Task 13 的
        #    `assert_authority_model_contract_pairing`（下面由 binding 委派执行）。
        #
        # 三条 Task 13 判据 + 载体门全部**委派** `WordEngineBinding.__post_init__`。
        #    在此重写任一条的后果不是「更安全」，而是任一侧被短路都不改变行为
        #    ⇒ 变异检验判 GREEN。
        binding = WordEngineBinding(
            contract=contract,
            entry_id=entry_id,
            mode=WordEngineMode.bundle_bound,
            bundle=bundle,
            carrier_gate=gate,
        )
        anchor = assert_only_tag_anchor_is_usable(gate=gate, entry_id=entry_id)
        blocked = assert_blocked_carriers_have_no_exemption(
            gate=gate, entry_id=entry_id, contract=contract
        )

        instrumentation_slot = slots[BundleSlot.instrumentation]
        recomputed = canonical_digest(dict(instrumentation_payload))
        if recomputed != instrumentation_slot.slot_digest.strip():
            raise WordEntryInstrumentationDigestMismatchError(
                f"entry {entry_id}: 传入的 instrumentation payload 现算 digest "
                f"{recomputed} 与 frozen bundle 的 instrumentation slot digest "
                f"{instrumentation_slot.slot_digest!r} 不一致 —— declared tag 清册必须"
                "来自 bundle 里那份 immutable instrumentation definition，"
                "不得换一份顶上（Requirement 7.10 / Property 28）"
            )
        if str(instrumentation_payload.get("document_type") or "") != WORD_DOCUMENT_TYPE:
            raise WordEntryInstrumentationDigestMismatchError(
                f"entry {entry_id}: frozen instrumentation payload 的 document_type="
                f"{instrumentation_payload.get('document_type')!r} —— 非 docx 的"
                "instrumentation 不得用于 Word entry gate"
            )
        inventory = declared_tag_inventory(
            contract=contract,
            instrumentation_payload=instrumentation_payload,
            readback=readback,
            entry_id=entry_id,
        )
        return FrozenWordEntryDefinitions(
            entry_id=entry_id,
            bundle=bundle,
            contract=contract,
            contract_origin=contract_origin,
            binding=binding,
            inventory=inventory,
            anchor=anchor,
            blocked_carriers=blocked,
        )

    # ─────────────────────────────────────────────────────────────────

    async def _load_bundle_row(
        self, bundle_id: uuid.UUID, *, entry_id: str
    ) -> WorkpaperSyncDefinitionBundle:
        """按 **FK** 读 bundle row。没有第二条路径（无 alias、无 entry 反查）。"""
        row = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionBundle).where(
                    WorkpaperSyncDefinitionBundle.id == bundle_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise WordEntryFrozenBundleDigestMismatchError(
                f"entry {entry_id}: frozen definition bundle 不存在: {bundle_id} —— "
                "缺 bundle 时不得回退到「registry 当前指向的那个」"
            )
        return row

    async def _assert_contract_child_approved(
        self, slot: BundleSlotSpec, *, entry_id: str
    ) -> uuid.UUID:
        """FS-6：contract slot 必须是 approved `kind=contract` definition child。

        实现形态刻意是**一条正向查询**（`id + kind + state` 三条件命中即可），
        不是三个顺序 `if` 的复制：命中即通过，不命中才回读一次 row 说明真正原因。
        """
        if not slot.is_definition:
            raise PerEntryContractUnapprovedError(
                f"entry {entry_id}: frozen bundle 的 contract slot 是 typed null marker "
                f"{slot.slot_type!r} —— tagged-SDT Word entry 的 `projection_contract` "
                "bundle 必须有 approved per-entry contract child，marker 不得冒充"
                "（Requirement 7.10）"
            )
        child_id = uuid.UUID(slot.slot_ref.split(":", 1)[1])
        hit = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact.id).where(
                    WorkpaperSyncDefinitionArtifact.id == child_id,
                    WorkpaperSyncDefinitionArtifact.kind == DefinitionKind.contract.value,
                    WorkpaperSyncDefinitionArtifact.state == DefinitionState.approved.value,
                )
            )
        ).scalar_one_or_none()
        if hit is not None:
            return child_id
        diagnostic = (
            await self._session.execute(
                sa.select(
                    WorkpaperSyncDefinitionArtifact.kind,
                    WorkpaperSyncDefinitionArtifact.state,
                ).where(WorkpaperSyncDefinitionArtifact.id == child_id)
            )
        ).first()
        if diagnostic is None:
            raise PerEntryContractUnapprovedError(
                f"entry {entry_id}: frozen bundle 的 contract slot 指向不存在的 definition "
                f"{child_id}"
            )
        raise PerEntryContractUnapprovedError(
            f"entry {entry_id}: contract slot 指向的 definition {child_id} 是 "
            f"kind={diagnostic[0]!r} state={diagnostic[1]!r} —— 必须是 approved 的 "
            "per-entry contract（generator 候选永不放行）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 10. tag-retention / Word-only 往返（只以 candidate 为底，无模板入口）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordCandidateRoundtrip:
    """candidate → 经 tag 重写 → candidate' 的一次真实往返结果。"""

    extracted: WordExtractOutcome
    observation: WordEntryObservation
    verification: WordVerificationBundle
    roundtrip_path: Path
    roundtrip_sha256: str
    word_only_coverage: Mapping[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation": self.observation.as_dict(),
            "roundtrip_sha256": self.roundtrip_sha256,
            "verification": self.verification.as_dict(),
            "word_only_coverage": dict(sorted(self.word_only_coverage.items())),
        }


def verify_candidate_tag_roundtrip(
    *,
    candidate_path: Path,
    binding: WordEngineBinding,
    scratch_dir: Path,
    entry_id: str,
) -> WordCandidateRoundtrip:
    """只经 `w:tag` 反读 candidate、再按 tag 写回一份，然后逐 aspect 比 Word-only 等值。

    ═══ 为什么两侧是 candidate 与 candidate'，而不是「模板与 candidate」 ═══

    注入把 token 文本从「SDT 外」搬进了「SDT 内」，所以模板 ↔ candidate 的
    `outside_sdt_text` 一格**天然**要变（那条差异属于 Task 59 的
    `verify_docx_visible_equivalence` 口径，逐块用声明 token 解释）。拿它当本函数的
    判据会恒红；更要紧的是它会诱导「用模板重生成」这条被 Task 77 正文明令禁止的
    路径。本模块因此**没有任何模板入口**：`substrate` 只可能是 candidate 自己，
    审计师在 SDT 外编辑过的正文会被逐块保留（Property 31）。

    ═══ 三个 Requirement 7.5 场景为什么被这一次往返覆盖 ═══

    往返的读侧与写侧**都只按 tag 定位**（`extract_word_projection` /
    `materialize_word_projection` 内零段落序号、零正则），因此：

    * **跨 run token**：注入时 `_split_token_paragraph` 把 3 个 run 拆成 SDT + 前后
      run，读回来靠 `w:t` 按序拼接；往返后值不变即证明 run 边界不参与定位；
    * **同段多 token**：同一段落里两个 SDT 各有自己的 tag，往返后两值互不串
      （串了会让 `verify_word_before_commit` 的 `mismatched_keys` 非空）；
    * **插删段落**：`container_path` 不含序号 ⇒ 段落数变化不影响定位；调用方在
      candidate 上插删段落后再跑本函数，值与层级都不变即证明。
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    extracted = extract_word_projection(
        artifact=candidate_path,
        binding=binding,
        substrate_role=SubstrateRole.staged_result,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.staged,
    )
    observation = observe_word_entry(extracted, entry_id=entry_id)
    if extracted.conflicts:
        locations = sorted(
            loc
            for conflict in extracted.conflicts
            for loc in _conflict_locations(conflict)
        )
        kinds = sorted({conflict.kind.value for conflict in extracted.conflicts})
        raise WordEntryDuplicateConflictError(
            f"entry {entry_id}: candidate 上存在未裁决的多实例异值冲突 {kinds}，"
            f"全部 OO 位置 {locations} —— 同 stable tag 的多个实例值不一致时必须先裁决"
            "（AC 7.4 / Property 32），不得挑一个值发布"
        )
    roundtrip = scratch_dir / f"{_safe_name(entry_id)}.roundtrip.docx"
    materialize_word_projection(
        substrate=candidate_path,
        projection=extracted.projection,
        output=roundtrip,
        binding=binding,
        substrate_role=SubstrateRole.staged_result,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.staged,
    )
    verification = verify_word_before_commit(
        expected=extracted.projection,
        staged_result=roundtrip,
        substrate=candidate_path,
        binding=binding,
    )
    coverage = assert_word_only_equivalent(verification.unmanaged, entry_id=entry_id)
    # 反读的受管 projection 与期望不等值时抛 `WordManagedProjectionMismatchError`
    # （Task 59 的单一真源）；Word-only 不等值时抛 `UnmanagedRegionDriftError`。
    verification.assert_publishable()
    return WordCandidateRoundtrip(
        extracted=extracted,
        observation=observation,
        verification=verification,
        roundtrip_path=roundtrip,
        roundtrip_sha256=hashlib.sha256(roundtrip.read_bytes()).hexdigest(),
        word_only_coverage=coverage,
    )


def _conflict_locations(conflict: Any) -> tuple[str, ...]:
    """一条 duplicate 冲突里登记的**全部** OO 位置（AC 7.4 要求列全）。

    权威清单是 Task 14 的 `ConflictRecord.word_instances`（`reduce_word_instances` 的
    docstring 逐字写着「不挑一个当代表就落库」），本函数只读它 —— 刻意**不**做
    「几个候选属性名依次试」的兜底：那种写法在字段改名后会静静退化成「只列一个位置」，
    而 AC 7.4 要的正是「列全」。字段不存在即抛，不猜。
    """
    refs = getattr(conflict, "word_instances", None)
    if refs is None:
        raise WordEntryDuplicateConflictError(
            f"冲突记录 {type(conflict).__name__} 没有 `word_instances` 清单 —— "
            "AC 7.4 要求列出全部 OO 位置，缺清单时不得只报一个位置"
        )
    out = [str(getattr(ref, "xpath", "")) for ref in refs if getattr(ref, "xpath", "")]
    locator = getattr(conflict, "locator", None)
    if locator is not None and getattr(locator, "oo_location", None):
        out.append(str(locator.oo_location))
    return tuple(dict.fromkeys(out))


def _safe_name(entry_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in entry_id)


# ═══════════════════════════════════════════════════════════════════════════
# 11. finalize gate
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordEntryFinalizeOutcome:
    """一次 `finalizeCandidate(entry)` 的结果：已校验身份 + Task 15 的 finalize 结果。"""

    entry_id: str
    definitions: FrozenWordEntryDefinitions
    evidence: WordCandidateEvidence
    roundtrip: WordCandidateRoundtrip
    finalize: RepresentationFinalizeOutcome

    @property
    def revision_unchanged(self) -> bool:
        return self.finalize.revision_unchanged

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "definitions": self.definitions.as_dict(),
            "candidate_evidence_sha256": self.evidence.report_sha256,
            "roundtrip": self.roundtrip.as_dict(),
            "finalize": self.finalize.as_dict(),
        }


class WordEntryFinalizeGate:
    """`finalizeCandidate(entry)` —— Word entry 的唯一放行门。

    ═══ 为什么出口只能是 Task 25 ═══

    `MaterializeCoordinator.finalize_definition_upgrade` 是 definitions-only 升级的
    **唯一**出口：它委派 Task 15 的 `RepresentationService.finalize_candidate`（其仓储
    被 `RevisionLockedRepository` 包住，拿不到 revision 域写入面）并断言
    `revision_unchanged`。本 gate 因此**不**自己调 `RepresentationService`，也不持有
    repository / outbox / artifacts —— 少了这条约束，「纯定义升级推进了业务 revision」
    就会多出一条绕过路径。

    ═══ 顺序即判据 ═══

    全部前置校验都在**调用出口之前**完成，且 `finalize_definition_upgrade` 是本方法里
    唯一一处会产生写入的调用。于是「任一前置不过 ⇒ 不产生 representation、不切
    pointer、不改 revision、原 Word 文件版本原样保留」不是文档承诺，而是可观察事实：
    守卫用记录调用次数的假 coordinator 断言前置失败时它是 0 次。

    ═══ 不做什么 ═══

    * 不注册 adapter（`PENDING_ENGINE_ADAPTERS` 仍禁 `adapters/word.py`，门是 Task 61）；
    * 不读权威模板、不重生成 docx（审计师的 Word-only 正文只可能被逐块保留）；
    * 不把 candidate 交给 resolver / room / current pointer / evidence —— 本 gate 对
      candidate 的唯一动作是「校验它，然后交给 Task 25 去 finalize」。
    """

    def __init__(
        self,
        *,
        loader: WordEntryDefinitionLoader,
        resolution: CanonicalResolutionService,
        coordinator: Any,
    ) -> None:
        self._loader = loader
        self._resolution = resolution
        # `coordinator` 刻意不做静态类型绑定（避免把 140KB 的 materialize_coordinator
        # 拉进本模块的 import 图），但方法名必须是真的 —— 守卫断言
        # `MaterializeCoordinator.finalize_definition_upgrade` 存在且本模块调的正是它。
        self._coordinator = coordinator

    # ─────────────────────────────────────────────────────────────────

    async def finalize_candidate(
        self,
        *,
        project_id: uuid.UUID,
        entry_id: str,
        candidate_id: uuid.UUID,
        staged_candidate: StagedCandidate,
        contract: SyncContract,
        contract_origin: str,
        instrumentation_payload: Mapping[str, Any],
        frozen_bundle_sha256: str,
        scratch_dir: Path,
        equivalence_report_bytes: bytes | None = None,
        carrier_gate: CarrierGate | None = None,
        approved_stages: Any = None,
        switch_entry_pointer: bool = True,
    ) -> WordEntryFinalizeOutcome:
        """校验全过后为**同一 content version** finalize 新的 published representation。"""
        if self._coordinator is None:
            raise WordEntryFinalizeGateBlockedError(
                f"entry {entry_id}: gate 未装配 MaterializeCoordinator —— definitions-only "
                "升级只能经 Task 25 的唯一出口 `finalize_definition_upgrade`，"
                "本 gate 不自行发布 representation（Property 67）"
            )
        # ① Task 12 的五条前置（approved contract + bundle + compatibility + 等值报告
        #    digest + 合法状态边）。**委派**，不重写：重写会让任一侧被短路都不改变行为。
        candidate = await self._resolution.assert_candidate_finalizable(candidate_id)
        if candidate.entry_id != entry_id:
            raise WordEntryFinalizeGateBlockedError(
                f"candidate {candidate_id} 属于 entry {candidate.entry_id!r}，与本次 "
                f"{entry_id!r} 不符 —— 不得用另一个 entry 的 candidate finalize"
            )
        if str(staged_candidate.entry_id) != entry_id:
            raise WordEntryFinalizeGateBlockedError(
                f"staged candidate 属于 entry {staged_candidate.entry_id!r}，与本次 "
                f"{entry_id!r} 不符 —— 禁跨 entry 复用 candidate 字节"
            )
        if str(staged_candidate.document_type) != WORD_DOCUMENT_TYPE:
            raise WordEntryFinalizeGateBlockedError(
                f"entry {entry_id}: staged candidate 的 document_type="
                f"{staged_candidate.document_type!r}，本 gate 只受理 "
                f"{WORD_DOCUMENT_TYPE!r}"
            )
        frozen_bundle_id = candidate.target_definition_bundle_id
        if frozen_bundle_id is None:
            raise PerEntryContractUnapprovedError(
                f"entry {entry_id}: candidate {candidate_id} 没有 approved definition "
                "bundle —— 只有 per-entry contract / authority model / bundle 三者全部 "
                "approved 后才可 finalize（Requirement 6.18 / Property 67）"
            )

        # ② candidate 自己的 instrumentation 证据（digest 锁到 candidate 行）。
        report_bytes = (
            equivalence_report_bytes
            if equivalence_report_bytes is not None
            else _read_evidence_report(staged_candidate)
        )
        evidence = parse_word_candidate_evidence(
            report_bytes=report_bytes,
            expected_sha256=str(candidate.visible_equivalence_report_sha256 or ""),
            entry_id=entry_id,
        )
        if evidence.instrumented_sha256 != staged_candidate.sha256:
            raise WordEntryCandidateEvidenceError(
                f"entry {entry_id}: 证据记录的 instrumented digest "
                f"{evidence.instrumented_sha256} 与 staged candidate 字节 "
                f"{staged_candidate.sha256} 不一致 —— 往返证据与将要发布的字节不是同一份"
            )
        if evidence.rollback_source_sha256 != str(candidate.rollback_source_sha256 or ""):
            raise WordEntryCandidateEvidenceError(
                f"entry {entry_id}: 证据记录的 rollback source digest "
                f"{evidence.rollback_source_sha256} 与 candidate 行登记的 "
                f"{candidate.rollback_source_sha256!r} 不一致 —— 回滚源必须可追溯，"
                "否则「失败保留原 Word 文件版本」无从执行（Requirement 7.8）"
            )

        # ③ frozen 身份 + 三边锁。
        definitions = await self._loader.load(
            entry_id=entry_id,
            contract=contract,
            contract_origin=contract_origin,
            frozen_bundle_id=frozen_bundle_id,
            frozen_bundle_sha256=frozen_bundle_sha256,
            instrumentation_payload=instrumentation_payload,
            readback=evidence.readback,
            carrier_gate=carrier_gate,
        )
        if (
            definitions.contract.instrumentation_definition_sha256
            != evidence.instrumentation_definition_sha256
        ):
            raise WordEntryInstrumentationDigestMismatchError(
                f"entry {entry_id}: 契约声明的 instrumentation digest "
                f"{definitions.contract.instrumentation_definition_sha256} 与 candidate "
                f"证据里的 {evidence.instrumentation_definition_sha256} 不一致 —— "
                "candidate 是用另一版 instrumentation 注入的"
            )
        # ④ 发布门（离线模式恒抛；bundle_bound 且有 bundle 才通过）。
        definitions.binding.assert_may_publish()

        # ⑤ tag-retention + Word-only 等值（真实往返，只以 candidate 为底）。
        roundtrip = verify_candidate_tag_roundtrip(
            candidate_path=Path(staged_candidate.path),
            binding=definitions.binding,
            scratch_dir=scratch_dir,
            entry_id=entry_id,
        )
        # ⑥ 四条 tagged-SDT 判据（tag 集合 / 层级 / 实例计数 已在上面按序执行 WG-4）。
        assert_tag_set_matches(definitions.inventory, roundtrip.observation, entry_id=entry_id)
        assert_sdt_hierarchy_intact(
            definitions.inventory, roundtrip.observation, entry_id=entry_id
        )
        assert_field_instance_counts(
            definitions.inventory, roundtrip.observation, entry_id=entry_id
        )

        # ⑦ 唯一写入面。
        outcome = await self._coordinator.finalize_definition_upgrade(
            project_id=project_id,
            candidate_id=candidate_id,
            staged_candidate=staged_candidate,
            adapter_id=definitions.adapter_id,
            adapter_build_digest=word_engine_build_digest(
                binding=definitions.binding,
                inventory=definitions.inventory,
                anchor=definitions.anchor,
            ),
            structure_hash=word_entry_structure_hash(
                contract=definitions.contract, inventory=definitions.inventory
            ),
            identity_inventory_sha256=roundtrip.extracted.identity_inventory_sha256,
            document_type=WORD_DOCUMENT_TYPE,
            approved_stages=approved_stages,
            switch_entry_pointer=switch_entry_pointer,
        )
        if outcome.definition_bundle_id != frozen_bundle_id:
            raise WordEntryFrozenBundleDigestMismatchError(
                f"entry {entry_id}: finalize 出的 representation 绑定 bundle "
                f"{outcome.definition_bundle_id}，与本 candidate 冻结的 {frozen_bundle_id} "
                "不一致"
            )
        return WordEntryFinalizeOutcome(
            entry_id=entry_id,
            definitions=definitions,
            evidence=evidence,
            roundtrip=roundtrip,
            finalize=outcome,
        )


def _read_evidence_report(staged_candidate: StagedCandidate) -> bytes:
    """读 candidate 隔离目录里的证据报告字节。

    路径由 `StagedCandidate` 自己携带（`equivalence_relative_path` 的文件名部分与
    artifact 同目录），本模块不重拼 `.upgrade-candidates/` 布局 —— 重拼就是第二真源。
    """
    name = Path(str(staged_candidate.equivalence_relative_path)).name
    if not name:
        raise WordEntryCandidateEvidenceError(
            "staged candidate 未携带证据报告路径 —— 没有反读等值证据不得 finalize"
        )
    path = Path(staged_candidate.path).parent / name
    try:
        return path.read_bytes()
    except OSError as exc:
        raise WordEntryCandidateEvidenceError(
            f"candidate 证据报告读不到: {path} ({exc})"
        ) from exc
