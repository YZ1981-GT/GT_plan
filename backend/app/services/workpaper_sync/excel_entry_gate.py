# -*- coding: utf-8 -*-
"""Excel per-entry contract/bundle **loader** 与 candidate **finalize gate**（Task 36）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 36
Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.10, 6.13, 6.14, 6.15, 6.16, 6.17, 6.18, 6.20
Properties: P20 / P21 / P22 / P23 / P28 / P66 / P67

═══ 一、本模块在链条里的位置 ═══

Task 17 只产 **non-current candidate**（`target_contract_definition_id` 与
`target_definition_bundle_id` 刻意留空）。Task 12 的
`assert_candidate_finalizable` 已经能判「缺 approved contract/bundle 就不许
finalize」，Task 15 的 `RepresentationService.finalize_candidate` 能在单事务里把
candidate 变成 published representation，Task 25 的
`MaterializeCoordinator.finalize_definition_upgrade` 是 definitions-only 升级的
**唯一**出口。

缺的那一段就是本模块：**逐 entry** 把「人工审核并发布的 per-entry contract +
approved authority model + approved non-null bundle」装进来，按 frozen bundle
FK/digest 校验 immutable children、structure/identity inventory 与 adapter build，
全过之后才允许调 Task 25 的唯一出口。

Tasks 40~57 的每个标准 Excel entry 在启用前必须各自走一遍本 gate；本模块**不**为
任何 entry 预置 contract/bundle/candidate，也**不**提供「复用另一个 entry 的
contract/evidence」的入口 —— :class:`ExcelEntryFinalizeGate` 的每个判据都以
「本 candidate 自己登记的 FK/digest」为准，换一份别人的 contract 会在
:class:`PerEntryContractUnapprovedError` 或
:class:`FrozenBundleDigestMismatchError` 处 fail closed。

═══ 二、为什么六类失败各有自己的异常类型 ═══

Requirement 6.2 / 6.10 把下面六件事列成**六条独立禁令**：

======  ==============================================  =============================
编号    形态                                             异常
======  ==============================================  =============================
FS-1    slot 整个键缺失（slot omission）                 :class:`FrozenSlotOmittedError`
FS-2    slot 字段为 SQL NULL / JSON null                 :class:`FrozenSlotNullError`
FS-3    slot 字段为空串或纯空白                          :class:`FrozenSlotBlankError`
FS-4    digest 为 64 个 0（伪身份）                       :class:`FrozenSlotAllZeroDigestError`
FS-5    slot type 既非 definition 也非登记 marker         :class:`FrozenSlotIllegalMarkerError`
FS-6    contract child 缺失 / 未 approved / marker 冒充   :class:`PerEntryContractUnapprovedError`
======  ==============================================  =============================

它们**必须**是六个类型。Task 12/13/14 已经连续三次实测到同一个坑：两条判据共用一个
异常类型时，靠前那条被短路之后靠后那条会抛同一类型把它遮蔽 ⇒ 只断言类型的守卫判
GREEN，于是「slot omission 必须 fail closed」这条承诺实际上没有任何单点可锁。

本模块也因此**不**把这六条委派给 `models.validate_bundle_slot`：那里刻意把
NULL/空串合成一句 `BundleIntegrityError`（它是 DB CHECK 的对侧镜像，粒度按 CHECK
走）。本模块的判据是**分类 + 首个 offender 定位**，删掉它不是「行为不变」而是
「error_code 从六个退化成一个」—— 守卫按 `error_code` 断言，删即打红。
形态判据本身仍然委派 `models.validate_bundle_slot`（在分类之后跑），不复制。

═══ 三、可达性说明（别声称守住了不可达分支）═══

V151 把 `working_paper_sync_definition_bundle` 的九个 slot 列全部声明成 `NOT NULL`
并挂了 `wpsync_is_digest()` CHECK，所以 FS-2/FS-3/FS-4 **无法**由一条已落库的行触发。
本模块因此把分类做成**纯函数** :func:`assert_frozen_slot_shape` /
:func:`assert_frozen_slots_shape`，输入是「任意来源的 raw slot map」：

* 已落库的 ORM row（:func:`raw_slot_map_of`，生产路径）；
* **尚未 flush** 的内存 ORM 对象（属性可以是 `None`）；
* 人写的 bundle JSON（`null` / `""` / 全零 hash 都写得出来）。

这不是「为测试留的开关」，而是判据本来的作用域：DB CHECK 是第二道锁，不是第一道。

═══ 四、禁止执行中解析当前 alias ═══

本模块**没有**任何 alias 入口：既不 import `DefinitionAliasRegistry`，也不按
`entry_id` 反查「现在该用哪个 bundle」。要加载什么，全部来自调用方给出的
**frozen** `(bundle_id, bundle_sha256)`；两者与 DB row 不符即
:class:`FrozenBundleDigestMismatchError`。守卫用「把
`DefinitionAliasRegistry.resolve_for_publish` 换成恒抛」的方式实测这一点 ——
判据是**真实执行**，不是「源码里没出现 alias 这个词」。
"""

from __future__ import annotations

import hashlib
import json
import re
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
from app.services.excel_metadata_sheet_policy import (
    PLATFORM_METADATA_SHEETS,
    exclude_metadata_sheets,
    is_platform_metadata_sheet,
)
from app.services.workpaper_sync.adapters.registry import (
    assert_authority_model_contract_pairing,
    assert_bundle_usable,
    assert_contract_identity_frozen,
)
from app.services.workpaper_sync.artifacts import StagedCandidate
from app.services.workpaper_sync.contracts import (
    DYNAMIC_COLUMN_IDENTITY_TEMPLATE,
    SyncContract,
    assert_no_structure_drift,
    load_contract,
)
from app.services.workpaper_sync.definitions import (
    TYPED_NULL_MARKERS,
    canonical_digest,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionKind,
    DefinitionState,
    SyncDomainError,
    is_digest,
    validate_bundle_slot,
)
from app.services.workpaper_sync.representations import RepresentationFinalizeOutcome
from app.services.workpaper_sync.resolution import (
    CanonicalResolutionService,
    DefinitionBundleSnapshot,
)

__all__ = [
    # 异常
    "ExcelEntryGateError",
    "FrozenSlotOmittedError",
    "FrozenSlotNullError",
    "FrozenSlotBlankError",
    "FrozenSlotAllZeroDigestError",
    "FrozenSlotIllegalMarkerError",
    "PerEntryContractUnapprovedError",
    "FrozenBundleDigestMismatchError",
    "IdentityInventoryError",
    "AdapterBuildError",
    "MetadataSheetLeakError",
    "DynamicColumnIdentityError",
    "CandidateEvidenceError",
    "EntryFinalizeGateError",
    # 常量
    "ALL_ZERO_DIGEST",
    "SLOT_COLUMNS",
    "FROZEN_SLOT_FAILURE_CAUSES",
    "REQUIRED_EQUIVALENCE_KEYS",
    # `_GT_SYNC` 业务枚举排除
    "assert_metadata_sheet_excluded",
    "assert_contract_declares_no_metadata_sheet",
    "business_sheet_names",
    # 动态列 identity
    "dynamic_column_stable_keys",
    "assert_dynamic_columns_label_independent",
    # 六类分类
    "raw_slot_map_of",
    "assert_frozen_slot_shape",
    "assert_frozen_slots_shape",
    # identity inventory / adapter build
    "EntryIdentityInventory",
    "parse_identity_inventory",
    "assert_identity_inventory_usable",
    "AdapterBuild",
    "assert_adapter_build_usable",
    # candidate 证据
    "CandidateEvidence",
    "parse_candidate_evidence",
    # loader / gate
    "FrozenEntryDefinitions",
    "ExcelEntryDefinitionLoader",
    "ExcelEntryFinalizeOutcome",
    "ExcelEntryFinalizeGate",
]


#: 64 个 0 —— 在 `char(64)` 与 hex 正则层面都合法的**伪身份**，必须单独拒绝。
ALL_ZERO_DIGEST: Final[str] = "0" * 64

#: `BundleSlot` → `working_paper_sync_definition_bundle` 的三个列名。
#:
#: 列名与 DB 逐字一致（不是「差不多的名字」）：:func:`raw_slot_map_of` 用它从 ORM row
#: 取值，守卫用它构造反例，两侧共用一份 ⇒ 改列名时只有一处要改。
SLOT_COLUMNS: Final[Mapping[BundleSlot, tuple[str, str, str]]] = {
    BundleSlot.template: (
        "template_slot_type",
        "template_slot_ref",
        "template_slot_digest",
    ),
    BundleSlot.instrumentation: (
        "instrumentation_slot_type",
        "instrumentation_slot_ref",
        "instrumentation_slot_digest",
    ),
    BundleSlot.contract: (
        "contract_slot_type",
        "contract_slot_ref",
        "contract_slot_digest",
    ),
}

#: candidate 的 visible-equivalence 报告里**必须**出现的键（Task 17 写入侧的对侧）。
REQUIRED_EQUIVALENCE_KEYS: Final[tuple[str, ...]] = (
    "schema_version",
    "entry_id",
    "visible_equivalence",
    "identity_inventory",
    "probe_gate",
    "instrumented_sha256",
    "template_definition_sha256",
    "instrumentation_definition_sha256",
)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常 —— 一条禁令一个类型一个 error_code
# ═══════════════════════════════════════════════════════════════════════════


class ExcelEntryGateError(SyncDomainError):
    """Task 36 的域基类。"""

    error_code = "excel_entry_gate_failed"


class FrozenSlotOmittedError(ExcelEntryGateError):
    """FS-1：typed slot 的键整个不存在。

    与 :class:`FrozenSlotNullError` 严格区分：「键没出现」与「键出现但值是 NULL」是
    两条独立禁令（Requirement 6.2 原文并列列出），合并后删掉任一分支都不会打红。
    """

    error_code = "frozen_bundle_slot_omitted"


class FrozenSlotNullError(ExcelEntryGateError):
    """FS-2：typed slot 字段是 SQL NULL / JSON null。"""

    error_code = "frozen_bundle_slot_null"


class FrozenSlotBlankError(ExcelEntryGateError):
    """FS-3：typed slot 字段是空串或纯空白。"""

    error_code = "frozen_bundle_slot_blank"


class FrozenSlotAllZeroDigestError(ExcelEntryGateError):
    """FS-4：slot digest 是 64 个 0（忘了算 hash 就填 0 的伪身份）。"""

    error_code = "frozen_bundle_slot_all_zero_digest"


class FrozenSlotIllegalMarkerError(ExcelEntryGateError):
    """FS-5：slot type 既非 `definition` 也非 registry 登记的版本化 typed null marker。

    marker registry 的单一真源是 `definitions.TYPED_NULL_MARKERS`，本类只负责在
    frozen 加载侧给出专属 error_code 与首个 offender 定位。
    """

    error_code = "frozen_bundle_slot_illegal_marker"


class PerEntryContractUnapprovedError(ExcelEntryGateError):
    """FS-6：per-entry contract 缺失 / 未 approved / 被 typed null marker 冒充。

    `projection_contract` 入口的 contract slot 必须是 **approved definition**；
    marker 只属于 `custom_authoritative_ooxml` / `opaque_single_onlyoffice`。
    """

    error_code = "per_entry_contract_missing_or_unapproved"


class FrozenBundleDigestMismatchError(ExcelEntryGateError):
    """frozen `(bundle_id, bundle_sha256)` 与 DB row 不符 —— 禁止按当前 alias 顶替。"""

    error_code = "frozen_bundle_digest_mismatch"


class IdentityInventoryError(ExcelEntryGateError):
    """identity inventory 缺失 / 空 UUID / 重复 UUID / metadata sheet 未排除。"""

    error_code = "excel_entry_identity_inventory_invalid"


class AdapterBuildError(ExcelEntryGateError):
    """adapter build 身份与 frozen contract/bundle 不符，或 build digest 非法。"""

    error_code = "excel_entry_adapter_build_invalid"


class MetadataSheetLeakError(ExcelEntryGateError):
    """`_GT_SYNC` 之类平台隐藏 metadata sheet 泄漏进业务 sheet 枚举或契约声明。"""

    error_code = "excel_entry_metadata_sheet_leaked"


class DynamicColumnIdentityError(ExcelEntryGateError):
    """动态列 identity 与可改 label 耦合（重命名改键 / 重名撞键 / 缺实测 label）。"""

    error_code = "excel_entry_dynamic_column_identity_invalid"


class CandidateEvidenceError(ExcelEntryGateError):
    """candidate 的 visible-equivalence / roundtrip 证据缺失、digest 不符或未通过。"""

    error_code = "excel_entry_candidate_evidence_invalid"


class EntryFinalizeGateError(ExcelEntryGateError):
    """gate 装配不全或 candidate 与本次 entry scope 不符。"""

    error_code = "excel_entry_finalize_gate_blocked"


#: 六类 frozen slot 失败原因 → 异常类型。守卫按它断言「六条各有自己的 error_code」，
#: 而不是在测试里抄一份名单（抄一份就是第二真源）。
FROZEN_SLOT_FAILURE_CAUSES: Final[Mapping[str, type[ExcelEntryGateError]]] = {
    "slot_omission": FrozenSlotOmittedError,
    "null": FrozenSlotNullError,
    "blank": FrozenSlotBlankError,
    "all_zero_digest": FrozenSlotAllZeroDigestError,
    "illegal_marker": FrozenSlotIllegalMarkerError,
    "missing_or_unapproved_contract": PerEntryContractUnapprovedError,
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. `_GT_SYNC` 业务枚举排除（Requirement 6.13 / 6.17 后半句）
# ═══════════════════════════════════════════════════════════════════════════


def business_sheet_names(names: Sequence[Any]) -> tuple[str, ...]:
    """业务 sheet 枚举：**显式**剔除平台隐藏 metadata sheet，保持原顺序。

    排除名单与判定口径全部委派 `excel_metadata_sheet_policy`（Task 17 的单一真源），
    本函数只做「返回 tuple 便于冻结进证据」这一层。
    """
    return tuple(exclude_metadata_sheets(names))


def assert_metadata_sheet_excluded(names: Sequence[Any], *, where: str) -> None:
    """业务侧拿到的 sheet 枚举里不得出现平台隐藏 metadata sheet，指出**首个** offender。"""
    for index, name in enumerate(names):
        if is_platform_metadata_sheet(name):
            raise MetadataSheetLeakError(
                f"{where}: 业务 sheet 枚举第 {index} 项是平台隐藏 metadata sheet {name!r} —— "
                f"必须被业务导入、报表与 sheet 枚举显式排除（Requirement 6.17）；"
                f"排除名单真源 {sorted(PLATFORM_METADATA_SHEETS)}"
            )


def assert_contract_declares_no_metadata_sheet(contract: SyncContract) -> None:
    """per-entry contract 不得把隐藏 metadata sheet 声明成受管业务 sheet。

    这与 :func:`assert_metadata_sheet_excluded` 是**两条**判据：后者管「运行态枚举有没有
    漏出去」，本条管「契约有没有一开始就把它当业务表写进来」。合成一条之后，一份把
    `_GT_SYNC` 写进 `sheets[]` 的契约会因为运行态枚举已排除而悄悄通过。
    """
    for sheet in contract.sheets:
        for value, field_name in (
            (sheet.excel_name, "excel_name"),
            (sheet.sheet_key, "sheet_key"),
        ):
            if is_platform_metadata_sheet(value):
                raise MetadataSheetLeakError(
                    f"contract {contract.contract_id}: sheet[{sheet.sheet_key!r}] 的 "
                    f"{field_name}={value!r} 是平台隐藏 metadata sheet —— 隐藏元数据表"
                    "永不得作为受管业务 sheet 出现在 per-entry contract 里"
                    "（Requirement 6.13 / 6.17）"
                )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 动态列 identity 与可改 label 解耦（Requirement 6.4 / Property 22）
# ═══════════════════════════════════════════════════════════════════════════


def _dynamic_key_pattern(slot: str) -> re.Pattern[str]:
    """由 `DYNAMIC_COLUMN_IDENTITY_TEMPLATE` **派生**的键形态正则。

    不在本模块写 `rf"^{slot}_\\d+$"` 字面量：模板一旦改成别的形状（比如
    `{slot}#{seq}`），写死的正则会继续放行旧形状 ⇒ 契约校验器与本门出现第二真源。
    做法是把模板里的两个占位分别替换成「转义后的 slot」与「数字组」。
    """
    probe = DYNAMIC_COLUMN_IDENTITY_TEMPLATE.format(slot="\x00SLOT\x00", seq="\x00SEQ\x00")
    escaped = re.escape(probe)
    escaped = escaped.replace(re.escape("\x00SLOT\x00"), re.escape(slot))
    escaped = escaped.replace(re.escape("\x00SEQ\x00"), r"[1-9][0-9]*")
    return re.compile(f"^{escaped}$")


def dynamic_column_stable_keys(*, slot: str, count: int) -> tuple[str, ...]:
    """按 `{slot}_{seq}` 生成 `count` 个稳定列键。

    **label 不是入参** —— 这是 Property 22 的实现方式而不是它的检查方式：函数签名里
    根本拿不到 label，于是「重命名公司 label 改变了 key」在构造上不可能。序号从 1 起，
    与平台 H7 范式一致；`{slot}` 取 frozen contract 的稳定 `table_key`。

    模板取自 `contracts.DYNAMIC_COLUMN_IDENTITY_TEMPLATE`（契约强校验器的单一真源），
    不在本模块写死 `f"{slot}_{seq}"`。
    """
    if not slot or not slot.strip():
        raise DynamicColumnIdentityError("dynamic column slot 不得为空")
    if count < 0:
        raise DynamicColumnIdentityError(f"dynamic column 数量不得为负: {count}")
    return tuple(
        DYNAMIC_COLUMN_IDENTITY_TEMPLATE.format(slot=slot.strip(), seq=seq)
        for seq in range(1, count + 1)
    )


def assert_dynamic_columns_label_independent(
    *, slot: str, observed: Sequence[tuple[str, str]], where: str
) -> tuple[str, ...]:
    """把**实测到的** `(label, key)` 对与 label 无关的派生键逐项比对。

    `observed` 是运行态工作簿里那张动态表实际用的列身份：每项是「这一列的可改 label」
    与「这一列当前挂着的 key」。判据三条，触发条件互不重叠，因此三条都可达、都能被
    变异 falsify：

    1. **形态/ASCII**（首先）：实测 key 必须匹配由 `DYNAMIC_COLUMN_IDENTITY_TEMPLATE`
       派生的正则且是 ASCII —— 直接按 label 建键（`公司甲`）在这里被抓；
    2. **实测键互不相同**（其次）：两家同名公司若共用一个键，在这里被抓 —— 这正是平台
       H7 实测过的「key 不能用 label，会撞键」；
    3. **与 label 无关的派生结果逐项相等**（最后）：`dynamic_column_stable_keys` 只吃
       `(slot, count)`，拿不到 label，于是「改名/重排/漏号」都会在这里露出。

    顺序不可交换：把第 2 条放到第 3 条之后，重复键会先被「与派生结果不等」抓走，
    第 2 条永久不可达 ⇒ 它的变异恒 GREEN。第 1 条同理必须在最前。
    """
    labels = [str(label) for label, _ in observed]
    observed_keys = tuple(str(key) for _, key in observed)
    expected = dynamic_column_stable_keys(slot=slot, count=len(observed_keys))
    pattern = _dynamic_key_pattern(str(slot).strip())
    for index, key in enumerate(observed_keys):
        if not key.isascii():
            raise DynamicColumnIdentityError(
                f"{where}: 第 {index} 列（label={labels[index]!r}）的实测 key {key!r} 含非 "
                "ASCII 字符 —— identity 不得依赖中文 label（Requirement 6.14 / Property 22）"
            )
        if pattern.match(key) is None:
            raise DynamicColumnIdentityError(
                f"{where}: 第 {index} 列（label={labels[index]!r}）的实测 key {key!r} 不符 "
                f"`{DYNAMIC_COLUMN_IDENTITY_TEMPLATE}` 形态 —— 稳定 key 只能由 slot + 序号"
                "组成，不得写死列数或用可改 label（Requirement 6.4）"
            )
    if len(set(observed_keys)) != len(observed_keys):
        duplicated = sorted({key for key in observed_keys if observed_keys.count(key) > 1})
        raise DynamicColumnIdentityError(
            f"{where}: 实测动态列 key 发生冲突 {duplicated}（labels={labels}）—— 重复 label "
            f"不得共用一个 `{DYNAMIC_COLUMN_IDENTITY_TEMPLATE}` 键"
        )
    for index, (key, want) in enumerate(zip(observed_keys, expected)):
        if key != want:
            raise DynamicColumnIdentityError(
                f"{where}: 第 {index} 列（label={labels[index]!r}）的实测 key {key!r} 与 label "
                f"无关的派生键 {want!r} 不一致 —— 动态列身份必须只由稳定 slot + 序号决定"
                "（Property 22）"
            )
    return expected


def _assert_dynamic_columns_declared(
    contract: SyncContract, observed_dynamic_columns: Mapping[str, Sequence[tuple[str, str]]]
) -> dict[str, tuple[str, ...]]:
    """契约声明了 `dynamic_columns` 的每张表都必须给出实测 `(label, key)` 对。

    缺就 fail closed（而不是「没给就跳过」）：跳过会让「动态列键是否真的与 label 解耦」
    在最需要它的 entry 上完全不被检查 —— G7/H1 恰恰是横向动态列最多的两类。
    """
    resolved: dict[str, tuple[str, ...]] = {}
    for sheet in contract.sheets:
        for table in sheet.tables:
            if table.dynamic_columns is None:
                continue
            where = (
                f"contract[{contract.contract_id}].sheets[{sheet.sheet_key}]"
                f".tables[{table.table_key}]"
            )
            # `{slot}` 取 frozen contract 的稳定 `table_key` —— 契约里没有别的稳定 slot
            # 名，而用 sheet 展示名或列 label 会把 identity 绑到可改字符串上。
            if table.table_key not in observed_dynamic_columns:
                raise DynamicColumnIdentityError(
                    f"{where}: 契约声明了 dynamic_columns，但未提供实测 (label, key) 对 —— "
                    "动态列身份必须在 finalize 前实测，不得留给运行时推断"
                )
            resolved[table.table_key] = assert_dynamic_columns_label_independent(
                slot=table.table_key,
                observed=[
                    (str(item[0]), str(item[1]))
                    for item in observed_dynamic_columns[table.table_key]
                ],
                where=where,
            )
    unknown = sorted(set(observed_dynamic_columns) - set(resolved))
    if unknown:
        raise DynamicColumnIdentityError(
            f"contract {contract.contract_id}: 提供了未声明 dynamic_columns 的表的实测列: "
            f"{unknown} —— 实测输入必须与契约声明一一对应"
        )
    return resolved


# ═══════════════════════════════════════════════════════════════════════════
# 3. 六类 frozen slot 分类（纯函数，输入是任意来源的 raw slot map）
# ═══════════════════════════════════════════════════════════════════════════


def raw_slot_map_of(row: Any) -> dict[str, Any]:
    """把 bundle row（ORM 对象 / Mapping）投影成 `{列名: 原始值}`。

    **不做任何归一**：`None` 保持 `None`、空串保持空串 —— 归一发生在这里的话，
    FS-2/FS-3 就永远看不到自己要判的东西了。列名缺失时该键**不出现**，让 FS-1
    与 FS-2 保持可分辨。
    """
    out: dict[str, Any] = {}
    for columns in SLOT_COLUMNS.values():
        for column in columns:
            if isinstance(row, AbcMapping):
                if column in row:
                    out[column] = row[column]
            elif hasattr(row, column):
                out[column] = getattr(row, column)
    return out


def assert_frozen_slot_shape(
    slot: BundleSlot, raw: Mapping[str, Any]
) -> BundleSlotSpec:
    """单个 typed slot 的 FS-1~FS-5 分类，返回归一后的 spec。

    判定顺序固定为 **omission → NULL → blank → all-zero digest → illegal marker**，
    每一步都在下一步之前失败，所以 error_code 总指向真正的第一个原因；同一 slot 内
    按 `type → ref → digest` 顺序找 offender。
    """
    type_col, ref_col, digest_col = SLOT_COLUMNS[slot]

    # FS-1：键整个缺失。
    for column in (type_col, ref_col, digest_col):
        if column not in raw:
            raise FrozenSlotOmittedError(
                f"frozen bundle 缺 typed slot 字段 {column!r}（slot={slot.value}）—— "
                "slot omission 必须 fail closed，不得以缺字段代替版本化 typed null marker"
                "（Requirement 6.2）"
            )
    # FS-2：SQL NULL / JSON null。
    for column in (type_col, ref_col, digest_col):
        if raw[column] is None:
            raise FrozenSlotNullError(
                f"frozen bundle 的 typed slot 字段 {column!r} 为 NULL（slot={slot.value}）"
                " —— SQL NULL 与 JSON null 都不得进入 canonical bytes"
            )
    # FS-3：空串 / 纯空白。
    for column in (type_col, ref_col, digest_col):
        if not str(raw[column]).strip():
            raise FrozenSlotBlankError(
                f"frozen bundle 的 typed slot 字段 {column!r} 为空串/纯空白"
                f"（slot={slot.value}）—— 空串不是「可选 child」的表达方式"
            )
    # FS-4：全零 digest（伪身份）。
    if str(raw[digest_col]).strip() == ALL_ZERO_DIGEST:
        raise FrozenSlotAllZeroDigestError(
            f"frozen bundle 的 {digest_col!r} 是全零 hash（slot={slot.value}）—— "
            "「忘了算 hash 就填 0」在 char(64) 与 hex 正则层面都合法，必须单独拒绝"
        )

    spec = BundleSlotSpec(
        slot,
        str(raw[type_col]).strip(),
        str(raw[ref_col]).strip(),
        str(raw[digest_col]).strip(),
    )
    # FS-5：非 definition 时必须是 registry 登记、且属于本 slot 的 marker。
    if spec.slot_type != "definition":
        marker = TYPED_NULL_MARKERS.get(spec.slot_type)
        if marker is None:
            raise FrozenSlotIllegalMarkerError(
                f"frozen bundle 的 {type_col!r}={spec.slot_type!r}（slot={slot.value}）"
                "既非 'definition' 也非 registry 登记的版本化 typed null marker"
                f"（已登记 {sorted(TYPED_NULL_MARKERS)}）"
            )
        if marker.slot is not slot:
            raise FrozenSlotIllegalMarkerError(
                f"frozen bundle 的 slot={slot.value} 用了 {marker.slot.value} 的 marker "
                f"{spec.slot_type!r}"
            )
        if spec.slot_ref != marker.slot_ref or spec.slot_digest != marker.slot_digest:
            raise FrozenSlotIllegalMarkerError(
                f"frozen bundle 的 slot={slot.value} marker ref/digest 与 registry 不一致："
                f"实得 ({spec.slot_ref!r}, {spec.slot_digest!r})，"
                f"registry ({marker.slot_ref!r}, {marker.slot_digest!r})"
            )
    # 剩下的形态判据（64 位小写 hex、`definition:<uuid>` ref 形态、marker 归属）
    # 一律委派 `models.validate_bundle_slot` 的单一实现，本模块不复制。
    validate_bundle_slot(spec)
    return spec


def assert_frozen_slots_shape(raw: Mapping[str, Any]) -> dict[BundleSlot, BundleSlotSpec]:
    """三个 typed slot 的 FS-1~FS-5 分类。按 `BundleSlot` 声明顺序找**首个** offender。"""
    return {slot: assert_frozen_slot_shape(slot, raw) for slot in BundleSlot}


# ═══════════════════════════════════════════════════════════════════════════
# 4. identity inventory（Requirement 6.15 / 6.16 / Property 66）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class EntryIdentityInventory:
    """Task 17 反读出的 identity 清册在 finalize 门上的**类型化投影**。

    只保留 finalize 需要裁决的那几项；原始 inventory 仍然完整地留在 candidate 的
    equivalence 报告里（本模块不改写它，也不重算它的 digest 之外的东西）。
    """

    hidden_sheet_present: bool
    hidden_sheet_is_hidden: bool
    excluded_from_business_enumeration: bool
    defined_names: tuple[str, ...]
    table_present: bool
    table_ref: str
    resolved_sheet_by: str | None
    uuid_column_hidden: bool
    row_uuids: Mapping[str, str]
    duplicate_row_uuids: tuple[str, ...]
    empty_row_uuids: tuple[str, ...]

    @property
    def inventory_digest_input(self) -> Mapping[str, Any]:
        return {
            "defined_names": sorted(self.defined_names),
            "row_uuids": dict(sorted(self.row_uuids.items())),
            "table_ref": self.table_ref,
        }


def _require_mapping(value: Any, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, AbcMapping):
        raise IdentityInventoryError(
            f"{where} 必须是对象，实得 {type(value).__name__} —— identity inventory 缺项"
            "不得降级成「没有 identity」"
        )
    return value


def parse_identity_inventory(raw: Any) -> EntryIdentityInventory:
    """把 `excel_structure_fingerprint.identity_inventory()` 的输出投影成类型化对象。"""
    payload = _require_mapping(raw, where="identity_inventory")
    hidden = _require_mapping(payload.get("hidden_sheet"), where="identity_inventory.hidden_sheet")
    names = _require_mapping(payload.get("defined_name"), where="identity_inventory.defined_name")
    table = _require_mapping(payload.get("excel_table"), where="identity_inventory.excel_table")
    column = _require_mapping(
        payload.get("hidden_uuid_column"), where="identity_inventory.hidden_uuid_column"
    )
    row_uuids = _require_mapping(
        column.get("row_uuids"), where="identity_inventory.hidden_uuid_column.row_uuids"
    )
    return EntryIdentityInventory(
        hidden_sheet_present=bool(hidden.get("present")),
        hidden_sheet_is_hidden=bool(hidden.get("is_hidden")),
        excluded_from_business_enumeration=bool(
            hidden.get("excluded_from_business_enumeration")
        ),
        defined_names=tuple(str(n) for n in (names.get("names") or ())),
        table_present=bool(table.get("present")),
        table_ref=str(table.get("table_ref") or ""),
        resolved_sheet_by=(
            str(column["resolved_sheet_by"])
            if column.get("resolved_sheet_by") is not None
            else None
        ),
        uuid_column_hidden=bool(column.get("uuid_column_hidden")),
        row_uuids={str(k): str(v) for k, v in row_uuids.items()},
        duplicate_row_uuids=tuple(str(v) for v in (column.get("duplicate_row_uuids") or ())),
        empty_row_uuids=tuple(str(v) for v in (column.get("empty_row_uuids") or ())),
    )


def assert_identity_inventory_usable(
    inventory: EntryIdentityInventory, *, contract: SyncContract, entry_id: str
) -> None:
    """identity inventory 必须够 extract 用，且指出**首个**不合格 identity。

    逐条对应 Requirement 6.15 的四种形态（空 UUID / 重复 UUID / identity 列被删 /
    非法结构编辑）与 6.17 后半句（隐藏元数据表必须被业务枚举排除）。
    """
    where = f"entry {entry_id}"
    if not inventory.hidden_sheet_present or not inventory.hidden_sheet_is_hidden:
        raise IdentityInventoryError(
            f"{where}: 隐藏 metadata sheet 反读失败（present="
            f"{inventory.hidden_sheet_present} is_hidden={inventory.hidden_sheet_is_hidden}）"
        )
    if not inventory.excluded_from_business_enumeration:
        raise IdentityInventoryError(
            f"{where}: 隐藏 metadata sheet 未被业务 sheet 枚举排除（Requirement 6.17）"
        )
    if not inventory.defined_names:
        raise IdentityInventoryError(
            f"{where}: 一个 `GT_` defined name 都没反读到 —— sheet 定位锚点缺失"
        )
    if not inventory.table_present or not inventory.table_ref:
        raise IdentityInventoryError(
            f"{where}: Excel Table 反读不到（table_ref={inventory.table_ref!r}）—— "
            "它是 sheet 改名后唯一可用的区域边界锚点"
        )
    if inventory.resolved_sheet_by != "table_sheet":
        raise IdentityInventoryError(
            f"{where}: UUID 列的 sheet 由 {inventory.resolved_sheet_by!r} 解析 —— "
            "生产反读只能走 excel_table_sheet_association（`sheet_id` / sheet 展示名"
            "在 OO 9.4 上已被证伪）"
        )
    if not inventory.uuid_column_hidden:
        raise IdentityInventoryError(f"{where}: row UUID 列未隐藏")
    if inventory.empty_row_uuids:
        raise IdentityInventoryError(
            f"{where}: 首个空 row UUID 位置 {inventory.empty_row_uuids[0]!r} —— "
            "空 identity 必须按 contract 分类为「分配新 ID / 结构冲突 / 拒绝」，"
            "不得静默按位置猜行身份（Requirement 6.15）"
        )
    if inventory.duplicate_row_uuids:
        raise IdentityInventoryError(
            f"{where}: 首个重复 row UUID {inventory.duplicate_row_uuids[0]!r} —— "
            "复制行产生的重复 UUID 必须分类处置，不得复用已删除 UUID"
        )
    # 「一个 row UUID 都没有」只在**契约声明了动态行**时才是缺陷：静态 checklist entry
    # 本来就没有行身份。故判据挂在契约声明上，并点名首张动态行表 —— 无条件要求
    # row_uuids 会让 Task 40 那类纯静态 entry 恒红，而那不是 Requirement 6.15 的形态。
    dynamic_tables = [
        (sheet.sheet_key, table.table_key)
        for sheet in contract.sheets
        for table in sheet.tables
        if table.has_dynamic_rows
    ]
    if dynamic_tables and not inventory.row_uuids:
        first_sheet, first_table = dynamic_tables[0]
        raise IdentityInventoryError(
            f"{where}: 契约声明动态行的首张表 sheet={first_sheet!r} table={first_table!r} "
            "一个 row identity 都没反读到 —— 对应「用户删除 identity 列」形态，"
            "contract 处置为拒绝，不得静默按位置猜行身份（Requirement 6.15）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. adapter build
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AdapterBuild:
    """将要写进 representation 的 adapter 身份。

    刻意由调用方显式给出而不是「从 registry 现查」：Tasks 40~57 的顺序是
    **先 finalize published representation、再注册 adapter**，从 registry 现查会让
    第一次 finalize 恒失败；更要紧的是「执行中按当前 alias/registry 解析」正是
    Requirement 6.2 明令禁止的形态。
    """

    adapter_id: str
    adapter_build_digest: str
    document_type: str
    contract_version: str


def assert_adapter_build_usable(
    build: AdapterBuild,
    *,
    contract: SyncContract,
    bundle: DefinitionBundleSnapshot,
    entry_id: str,
) -> None:
    """adapter build 与 frozen contract/bundle 三向锁死。"""
    where = f"entry {entry_id}"
    if not is_digest(build.adapter_build_digest):
        raise AdapterBuildError(
            f"{where}: adapter_build_digest 必须是非空非全零的 64 位小写 hex，"
            f"实得 {build.adapter_build_digest!r}"
        )
    if build.adapter_id != contract.contract_id:
        raise AdapterBuildError(
            f"{where}: adapter_id {build.adapter_id!r} 与 per-entry contract_id "
            f"{contract.contract_id!r} 不符 —— 契约身份与 adapter 身份必须双向锁死；"
            "禁止复用另一个 entry 的 contract"
        )
    if build.document_type != contract.document_type:
        raise AdapterBuildError(
            f"{where}: adapter document_type {build.document_type!r} 与契约 "
            f"{contract.document_type!r} 不符"
        )
    if build.document_type != "xlsx":
        raise AdapterBuildError(
            f"{where}: 本 gate 只处理标准 Excel entry，实得 document_type "
            f"{build.document_type!r}（Word 走 Tasks 59~64）"
        )
    if build.contract_version != contract.semantic_version:
        raise AdapterBuildError(
            f"{where}: adapter contract_version {build.contract_version!r} 与契约 "
            f"semantic_version {contract.semantic_version!r} 不符 —— adapter 挂着旧契约版本"
        )
    if bundle.authority_model is not AuthorityModel.projection_contract:
        raise AdapterBuildError(
            f"{where}: 标准 Excel entry 的 authority model 必须是 projection_contract，"
            f"实得 {bundle.authority_model.value} —— custom/opaque 走 Task 65"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 6. candidate 证据（visible-equivalence / roundtrip）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CandidateEvidence:
    """candidate 的 visible-equivalence 报告投影。"""

    entry_id: str
    payload: Mapping[str, Any]
    report_sha256: str
    identity_inventory: EntryIdentityInventory
    probe_gate: Mapping[str, Any]
    template_definition_sha256: str
    instrumentation_definition_sha256: str
    instrumented_sha256: str


def parse_candidate_evidence(
    *, report_bytes: bytes, expected_sha256: str, entry_id: str
) -> CandidateEvidence:
    """读 candidate 的 equivalence 报告并逐条校验它**真的**通过了。

    先比 digest 再解析：报告内容与 candidate 行登记的
    `visible_equivalence_report_sha256` 不符时，后面读到的一切都不属于这个 candidate
    （典型形态就是「拿另一个 entry 的 evidence 顶上」）。
    """
    observed = hashlib.sha256(report_bytes).hexdigest()
    if not is_digest(expected_sha256):
        raise CandidateEvidenceError(
            f"entry {entry_id}: candidate 登记的 visible_equivalence_report_sha256 非法: "
            f"{expected_sha256!r}"
        )
    if observed != expected_sha256:
        raise CandidateEvidenceError(
            f"entry {entry_id}: equivalence 报告实测 digest {observed} 与 candidate 登记的 "
            f"{expected_sha256} 不一致 —— 禁止用别的 candidate/entry 的 evidence 顶替"
        )
    try:
        payload = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateEvidenceError(
            f"entry {entry_id}: equivalence 报告不是合法 UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(payload, AbcMapping):
        raise CandidateEvidenceError(
            f"entry {entry_id}: equivalence 报告根必须是对象，实得 {type(payload).__name__}"
        )
    missing = [key for key in REQUIRED_EQUIVALENCE_KEYS if key not in payload]
    if missing:
        raise CandidateEvidenceError(
            f"entry {entry_id}: equivalence 报告缺键 {missing} —— 证据不完整不得 finalize"
        )
    if str(payload.get("entry_id")) != entry_id:
        raise CandidateEvidenceError(
            f"entry {entry_id}: equivalence 报告属于 entry {payload.get('entry_id')!r} —— "
            "不得复用另一个 entry 的 candidate evidence"
        )
    equivalence = _require_mapping(
        payload.get("visible_equivalence"), where=f"entry {entry_id}.visible_equivalence"
    )
    if equivalence.get("equivalent") is not True:
        bad = sorted(
            aspect
            for aspect, ok in (equivalence.get("aspect_verdicts") or {}).items()
            if not ok
        )
        raise CandidateEvidenceError(
            f"entry {entry_id}: candidate 的可见等价性未通过，首批不等价 aspect {bad} —— "
            "instrumentation 破坏了可见业务结构（Requirement 6.17）"
        )
    if equivalence.get("metadata_sheet_excluded_from_business") is not True:
        raise CandidateEvidenceError(
            f"entry {entry_id}: candidate 报告显示隐藏 metadata sheet 未被业务枚举排除"
        )
    inventory = parse_identity_inventory(payload.get("identity_inventory"))
    probe_gate = _require_mapping(
        payload.get("probe_gate"), where=f"entry {entry_id}.probe_gate"
    )
    for key in ("carrier_contract_sha256", "onlyoffice_build"):
        if not str(probe_gate.get(key) or "").strip():
            raise CandidateEvidenceError(
                f"entry {entry_id}: candidate 证据缺 probe_gate.{key} —— identity 载体必须"
                "先过真实 OnlyOffice 9.4 黑盒探针（Requirement 6.16 / Property 66）"
            )
    for key in (
        "template_definition_sha256",
        "instrumentation_definition_sha256",
        "instrumented_sha256",
    ):
        if not is_digest(payload.get(key)):
            raise CandidateEvidenceError(
                f"entry {entry_id}: candidate 证据的 {key} 非法: {payload.get(key)!r}"
            )
    return CandidateEvidence(
        entry_id=entry_id,
        payload=dict(payload),
        report_sha256=observed,
        identity_inventory=inventory,
        probe_gate=dict(probe_gate),
        template_definition_sha256=str(payload["template_definition_sha256"]).strip(),
        instrumentation_definition_sha256=str(
            payload["instrumentation_definition_sha256"]
        ).strip(),
        instrumented_sha256=str(payload["instrumented_sha256"]).strip(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. loader
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FrozenEntryDefinitions:
    """一个 entry 按 frozen FK/digest 加载出的完整、已校验身份。"""

    entry_id: str
    bundle: DefinitionBundleSnapshot
    contract: SyncContract
    adapter_build: AdapterBuild
    identity_inventory: EntryIdentityInventory
    business_sheets: tuple[str, ...]
    dynamic_column_keys: Mapping[str, tuple[str, ...]]
    structure_inventory_size: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "definition_bundle_id": str(self.bundle.bundle_id),
            "definition_bundle_sha256": self.bundle.bundle_sha256,
            "authority_model": self.bundle.authority_model.value,
            "authority_model_definition_id": str(self.bundle.authority_model_definition_id),
            "contract_id": self.contract.contract_id,
            "contract_semantic_version": self.contract.semantic_version,
            "contract_sha256": self.contract.canonical_sha256,
            "adapter_id": self.adapter_build.adapter_id,
            "adapter_build_digest": self.adapter_build.adapter_build_digest,
            "typed_slot_inventory": [
                list(item) for item in self.bundle.typed_slot_inventory
            ],
            "business_sheets": list(self.business_sheets),
            "dynamic_column_keys": {
                key: list(value) for key, value in sorted(self.dynamic_column_keys.items())
            },
            "identity_inventory_sha256": canonical_digest(
                self.identity_inventory.inventory_digest_input
            ),
            "structure_inventory_size": self.structure_inventory_size,
        }


class ExcelEntryDefinitionLoader:
    """按 **frozen** `(bundle_id, bundle_sha256)` 加载并校验一个 Excel entry 的身份。

    只读，不写任何行；没有任何 alias 入口。加载顺序即判据（不可交换）：

    1. raw slot 形态六类分类（FS-1~FS-5，纯函数）；
    2. frozen digest 与 bundle row 的 `canonical_payload_sha256` 一致；
    3. contract child row 的 kind/state（FS-6 在这里，**先于**深度校验，否则
       `load_bundle_snapshot` 的 `BundleIntegrityError` 会把它永久遮蔽）；
    4. Task 12 `load_bundle_snapshot` 的 immutable children 深度校验 + canonical 重算；
    5. Task 13 `assert_bundle_usable` / `assert_authority_model_contract_pairing` /
       `assert_contract_identity_frozen`（含 `assert_matches_bundle_slots` 漂移）；
    6. `_GT_SYNC` 排除、动态列 label 解耦；
    7. structure inventory 漂移（Task 13 的 `assert_no_structure_drift`）；
    8. identity inventory；
    9. adapter build。
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
        frozen_bundle_id: uuid.UUID,
        frozen_bundle_sha256: str,
        adapter_build: AdapterBuild,
        identity_inventory: EntryIdentityInventory,
        observed_structure: Sequence[tuple[str, str, str, str]],
        observed_business_sheets: Sequence[str],
        observed_dynamic_columns: Mapping[str, Sequence[tuple[str, str]]],
    ) -> FrozenEntryDefinitions:
        """加载并校验；任一判据不过即 fail closed，不返回半成品。"""
        row = await self._load_bundle_row(frozen_bundle_id)
        slots = assert_frozen_slots_shape(raw_slot_map_of(row))

        if not is_digest(frozen_bundle_sha256):
            raise FrozenBundleDigestMismatchError(
                f"entry {entry_id}: 调用方给出的 frozen bundle digest 非法: "
                f"{frozen_bundle_sha256!r} —— frozen 身份必须显式且合法，"
                "禁止「留空就按当前 alias 取最新版」"
            )
        row_digest = str(getattr(row, "canonical_payload_sha256", "") or "").strip()
        if row_digest != frozen_bundle_sha256.strip():
            raise FrozenBundleDigestMismatchError(
                f"entry {entry_id}: frozen bundle {frozen_bundle_id} 的 canonical digest "
                f"{row_digest!r} 与调用方冻结的 {frozen_bundle_sha256!r} 不一致 —— "
                "bundle approved 后不可修改或重组，历史身份不得按当前 alias 重新解析"
                "（Requirement 6.2 / Property 28）"
            )

        # FS-6：contract child 必须存在、kind=contract、state=approved，且不是 marker。
        #
        # 🔴 顺序：本条**必须**在 `load_bundle_snapshot` 之前。反过来写时，
        # 「contract child 未 approved」会先被 Task 12 的 `BundleIntegrityError` 抓到，
        # `PerEntryContractUnapprovedError` 变成永久不可达分支 ⇒ 它的变异恒 GREEN，
        # 而 Requirement 6.2 要求这条禁令有自己的 error_code。
        await self._assert_contract_child_approved(
            slots[BundleSlot.contract], entry_id=entry_id
        )

        bundle = await self._resolution.load_bundle_snapshot(frozen_bundle_id)
        assert_bundle_usable(bundle, entry_id=entry_id)

        # 磁盘契约 ↔ frozen bundle contract slot 的 digest 比对**不在本模块重写**：
        # `assert_contract_identity_frozen`（Task 13 RG-10，含
        # `assert_matches_bundle_slots` 的 template/instrumentation 漂移）已经是单一真源。
        # 复制一份的后果不是「更安全」，而是任一侧被短路都不改变行为 ⇒ 变异判 GREEN。
        contract = load_contract(adapter_build.adapter_id)
        assert_authority_model_contract_pairing(
            authority_model=bundle.authority_model,
            contract=contract,
            bundle=bundle,
            entry_id=entry_id,
        )
        assert_contract_identity_frozen(contract=contract, bundle=bundle, entry_id=entry_id)

        assert_contract_declares_no_metadata_sheet(contract)
        assert_metadata_sheet_excluded(
            observed_business_sheets, where=f"entry {entry_id}"
        )
        dynamic_keys = _assert_dynamic_columns_declared(contract, observed_dynamic_columns)

        assert_no_structure_drift(contract, observed_structure)
        assert_identity_inventory_usable(
            identity_inventory, contract=contract, entry_id=entry_id
        )
        assert_adapter_build_usable(
            adapter_build, contract=contract, bundle=bundle, entry_id=entry_id
        )
        return FrozenEntryDefinitions(
            entry_id=entry_id,
            bundle=bundle,
            contract=contract,
            adapter_build=adapter_build,
            identity_inventory=identity_inventory,
            business_sheets=business_sheet_names(observed_business_sheets),
            dynamic_column_keys=dynamic_keys,
            structure_inventory_size=len(tuple(observed_structure)),
        )

    # ─────────────────────────────────────────────────────────────────

    async def _load_bundle_row(self, bundle_id: uuid.UUID) -> WorkpaperSyncDefinitionBundle:
        """按 **FK** 读 bundle row。没有第二条路径（无 alias、无 entry 反查）。"""
        row = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionBundle).where(
                    WorkpaperSyncDefinitionBundle.id == bundle_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise FrozenBundleDigestMismatchError(
                f"frozen definition bundle 不存在: {bundle_id} —— 缺 bundle 时不得回退到"
                "「registry 当前指向的那个」"
            )
        return row

    async def _assert_contract_child_approved(
        self, slot: BundleSlotSpec, *, entry_id: str
    ) -> uuid.UUID:
        """FS-6：contract slot 必须是 approved `kind=contract` definition child。"""
        if not slot.is_definition:
            raise PerEntryContractUnapprovedError(
                f"entry {entry_id}: frozen bundle 的 contract slot 是 typed null marker "
                f"{slot.slot_type!r} —— 标准 Excel entry 的 `projection_contract` bundle "
                "必须有 approved per-entry contract child，marker 不得冒充"
                "（Requirement 6.2 / 6.19）"
            )
        child_id = uuid.UUID(slot.slot_ref.split(":", 1)[1])
        child = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id == child_id
                )
            )
        ).scalar_one_or_none()
        if child is None:
            raise PerEntryContractUnapprovedError(
                f"entry {entry_id}: frozen bundle 的 contract slot 指向不存在的 definition "
                f"{child_id}"
            )
        if child.kind != DefinitionKind.contract.value:
            raise PerEntryContractUnapprovedError(
                f"entry {entry_id}: frozen bundle 的 contract slot 指向 kind={child.kind!r} "
                f"的 definition {child_id} —— 必须是 per-entry contract"
            )
        if child.state != DefinitionState.approved.value:
            raise PerEntryContractUnapprovedError(
                f"entry {entry_id}: per-entry contract definition {child_id} 的 state="
                f"{child.state!r} —— 只有人工审核后 approved 的契约可用于 finalize"
                "（generator 候选永不放行）"
            )
        # child.sha256 ↔ slot digest 的等值比对不在此重写：
        # `resolution.load_bundle_snapshot` 与 V151 的 `wpsync_assert_bundle_slot`
        # 已经是那条判据的双向真源。
        return child_id


# ═══════════════════════════════════════════════════════════════════════════
# 8. finalize gate
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ExcelEntryFinalizeOutcome:
    """一次 `finalizeCandidate(entry)` 的结果：已校验身份 + Task 15 的 finalize 结果。"""

    entry_id: str
    definitions: FrozenEntryDefinitions
    evidence: CandidateEvidence
    finalize: RepresentationFinalizeOutcome

    @property
    def revision_unchanged(self) -> bool:
        return self.finalize.revision_unchanged

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "definitions": self.definitions.as_dict(),
            "candidate_evidence_sha256": self.evidence.report_sha256,
            "finalize": self.finalize.as_dict(),
        }


class ExcelEntryFinalizeGate:
    """`finalizeCandidate(entry)` —— Tasks 40~57 每个标准 Excel entry 的唯一放行门。

    ═══ 为什么出口只能是 Task 25 ═══

    `MaterializeCoordinator.finalize_definition_upgrade` 是 definitions-only 升级的
    **唯一**出口：它委派 Task 15 的 `RepresentationService.finalize_candidate`（其仓储
    被 `RevisionLockedRepository` 包住，拿不到 revision 域写入面）并断言
    `revision_unchanged`。本 gate 因此**不**自己调 `RepresentationService`，也不持有
    repository / outbox —— 少了这条约束，「纯定义升级推进了业务 revision」就会多出
    一条绕过路径，而 Property 4/67 的守卫测的还是另一条。

    ═══ 顺序即判据 ═══

    全部前置校验都在**调用出口之前**完成，且 `finalize_definition_upgrade` 是本方法里
    唯一一处会产生写入的调用。于是「任一前置不过 ⇒ 不产生 representation、不切
    pointer、不改 revision」不是文档承诺，而是可观察事实：守卫用记录调用次数的假
    coordinator 断言前置失败时它是 0 次。
    """

    def __init__(
        self,
        *,
        loader: ExcelEntryDefinitionLoader,
        resolution: CanonicalResolutionService,
        coordinator: Any,
    ) -> None:
        self._loader = loader
        self._resolution = resolution
        # `coordinator` 刻意不做静态类型绑定（避免把 140KB 的 materialize_coordinator
        # 拉进本模块的 import 图），但方法名必须是真的 —— 守卫断言
        # `MaterializeCoordinator.finalize_definition_upgrade` 存在且本模块调的正是它，
        # 否则「接了 Task 25 唯一出口」会退化成一个永远 AttributeError 的假接线。
        self._coordinator = coordinator

    # ─────────────────────────────────────────────────────────────────

    async def finalize_candidate(
        self,
        *,
        project_id: uuid.UUID,
        entry_id: str,
        candidate_id: uuid.UUID,
        staged_candidate: StagedCandidate,
        frozen_bundle_sha256: str,
        adapter_build: AdapterBuild,
        observed_structure: Sequence[tuple[str, str, str, str]],
        observed_business_sheets: Sequence[str],
        observed_dynamic_columns: Mapping[str, Sequence[tuple[str, str]]],
        equivalence_report_bytes: bytes | None = None,
        approved_stages: Any = None,
        switch_entry_pointer: bool = True,
    ) -> ExcelEntryFinalizeOutcome:
        """校验全过后为**同一 content version** finalize 新的 published representation。"""
        if self._coordinator is None:
            raise EntryFinalizeGateError(
                "gate 未装配 MaterializeCoordinator —— definitions-only 升级只能经 Task 25 "
                "的唯一出口 `finalize_definition_upgrade`，本 gate 不自行发布 representation"
            )
        candidate = await self._resolution.assert_candidate_finalizable(candidate_id)
        if candidate.entry_id != entry_id:
            raise EntryFinalizeGateError(
                f"candidate {candidate_id} 属于 entry {candidate.entry_id!r}，与本次 "
                f"{entry_id!r} 不符 —— 不得用另一个 entry 的 candidate finalize"
            )
        if str(staged_candidate.entry_id) != entry_id:
            raise EntryFinalizeGateError(
                f"staged candidate 属于 entry {staged_candidate.entry_id!r}，与本次 "
                f"{entry_id!r} 不符"
            )
        frozen_bundle_id = candidate.target_definition_bundle_id
        if frozen_bundle_id is None:
            raise PerEntryContractUnapprovedError(
                f"entry {entry_id}: candidate {candidate_id} 没有 approved definition bundle"
            )

        report_bytes = (
            equivalence_report_bytes
            if equivalence_report_bytes is not None
            else self._read_equivalence_report(staged_candidate)
        )
        evidence = parse_candidate_evidence(
            report_bytes=report_bytes,
            expected_sha256=str(candidate.visible_equivalence_report_sha256 or ""),
            entry_id=entry_id,
        )
        if evidence.instrumented_sha256 != staged_candidate.sha256:
            raise CandidateEvidenceError(
                f"entry {entry_id}: candidate 证据记录的 instrumented digest "
                f"{evidence.instrumented_sha256} 与 staged candidate 字节 "
                f"{staged_candidate.sha256} 不一致 —— roundtrip 证据与将要发布的字节不是"
                "同一份"
            )

        definitions = await self._loader.load(
            entry_id=entry_id,
            frozen_bundle_id=frozen_bundle_id,
            frozen_bundle_sha256=frozen_bundle_sha256,
            adapter_build=adapter_build,
            identity_inventory=evidence.identity_inventory,
            observed_structure=observed_structure,
            observed_business_sheets=observed_business_sheets,
            observed_dynamic_columns=observed_dynamic_columns,
        )

        outcome = await self._coordinator.finalize_definition_upgrade(
            project_id=project_id,
            candidate_id=candidate_id,
            staged_candidate=staged_candidate,
            adapter_id=definitions.adapter_build.adapter_id,
            adapter_build_digest=definitions.adapter_build.adapter_build_digest,
            structure_hash=canonical_digest(
                {
                    "schema_version": "excel-entry-structure:v1",
                    "contract_sha256": definitions.contract.canonical_sha256,
                    "structure": [list(item) for item in sorted(observed_structure)],
                }
            ),
            identity_inventory_sha256=canonical_digest(
                evidence.identity_inventory.inventory_digest_input
            ),
            document_type=definitions.adapter_build.document_type,
            approved_stages=approved_stages,
            switch_entry_pointer=switch_entry_pointer,
        )
        if outcome.definition_bundle_id != frozen_bundle_id:
            raise FrozenBundleDigestMismatchError(
                f"entry {entry_id}: finalize 出的 representation 绑定 bundle "
                f"{outcome.definition_bundle_id}，与本 candidate 冻结的 {frozen_bundle_id} "
                "不一致"
            )
        return ExcelEntryFinalizeOutcome(
            entry_id=entry_id,
            definitions=definitions,
            evidence=evidence,
            finalize=outcome,
        )

    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _read_equivalence_report(staged_candidate: StagedCandidate) -> bytes:
        """读 candidate 隔离目录里的 equivalence 报告字节。

        路径由 `StagedCandidate` 自己携带（`equivalence_relative_path` 的文件名部分与
        artifact 同目录），不在本模块重拼 `.upgrade-candidates/` 布局 —— 重拼就是第二真源。
        """
        name = Path(str(staged_candidate.equivalence_relative_path)).name
        if not name:
            raise CandidateEvidenceError(
                "staged candidate 未携带 equivalence 报告路径 —— 没有反读等值证据不得 finalize"
            )
        path = Path(staged_candidate.path).parent / name
        try:
            return path.read_bytes()
        except OSError as exc:
            raise CandidateEvidenceError(
                f"candidate equivalence 报告读不到: {path} ({exc})"
            ) from exc
