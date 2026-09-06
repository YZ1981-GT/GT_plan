"""文档无关 adapter protocol 与 projection 类型（Task 13）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 13
Requirements 1.4 / 6.1 / 6.2 / 6.3 / 6.10 / 6.14 / 6.20 / 9.8 / 12.1
Property 3 / 20 / 21 / 28

## 设计约束（design §Adapter protocol 原文）

1. **adapter 不 commit、不递增 revision、不更新 pointer、不发布 outbox。**
   本模块用「构造上不可能」而不是「注释里禁止」来落实：:class:`SyncContext` 只
   携带**冻结身份 + 只读路径 + immutable 快照**，根本不持有 `AsyncSession`、
   repository 或 outbox。:func:`assert_no_mutation_surface` 逐字段实测这一点 ——
   任何暴露 `commit/flush/add/execute/publish/delete` 可调用的字段即 fail closed。
   判据落在**对象实际属性**上，不是 grep 源码字符串（后者是假绿第②源）。

2. **adapter 收到的是 application/representation 固定的 immutable
   `DefinitionBundleSnapshot`**，不得在执行中按 registry alias 取「最新版」。
   :class:`SyncContext` 因此只接受 `resolution.DefinitionBundleSnapshot`，且
   `contract` 必须与 bundle 的 typed slot digests 一致
   （:meth:`SyncContext.assert_frozen_identity_consistent`）。

3. **OO→HTML 的 substrate 只能是 `kind=incoming, state=durable` 的 artifact。**
   quarantined incoming 与 upgrade candidate 在 adapter 入口即 fail closed
   （:func:`assert_substrate_usable`），不进 extract/merge/retry/rematerialize。

4. Projection 是**按 stable key 索引的值集合**，不是位置数组 —— 行/列身份一律走
   contract 声明的 row identity 与 `{slot}_{seq}` 动态列 key。

## 本模块不做的事

不实现任何 Excel/Word 载体逻辑，不 import openpyxl/python-docx，不依赖 Task 5/6
的 probe 结论以外的任何载体假设。engine 由 Tasks 36~38（Excel）与 59~61（Word）
在各自 gate 通过后实现。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, fields as dataclass_fields
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from app.services.workpaper_sync.contracts import (
    FieldMode,
    SyncContract,
    ValueType,
)
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    BundleSlot,
    IncomingNotDurableError,
    QuarantinedIncomingError,
    SyncDomainError,
    is_digest,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot

# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常
# ═══════════════════════════════════════════════════════════════════════════


class AdapterProtocolError(SyncDomainError):
    error_code = "adapter_protocol_violation"


class AdapterSideEffectError(AdapterProtocolError):
    """adapter 上下文暴露了写库/提交/发事件的能力面（design §Adapter protocol 第 1 条）。"""

    error_code = "adapter_side_effect_surface"


class AdapterSubstrateError(AdapterProtocolError):
    """substrate artifact 不是允许的 kind/state 组合。"""

    error_code = "adapter_substrate_invalid"


class AdapterCandidateSubstrateError(AdapterSubstrateError):
    """把 representation upgrade candidate 当 substrate（Requirement 6.18）。

    单独一个类型而不是复用父类：candidate 与 incoming/quarantined 是三条完全不同的
    准入原因，合并后把 candidate 分支删掉会被 state 分支遮蔽 ⇒ 变异检验判 GREEN。
    """

    error_code = "adapter_candidate_substrate_forbidden"


class UnmanagedRegionDriftError(AdapterProtocolError):
    """未管理区域在 roundtrip 后发生变化（Requirement 6.11 / 6.17 的 adapter 侧）。"""

    error_code = "adapter_unmanaged_region_drift"


class ProjectionShapeError(AdapterProtocolError):
    """projection 形态与 contract 不一致（stable key 未登记、行键缺失等）。"""

    error_code = "adapter_projection_shape_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 副作用面守卫
# ═══════════════════════════════════════════════════════════════════════════

#: 一旦 adapter 上下文的某个字段暴露这些**可调用**属性，就说明它握着写库/发事件的
#: 能力面。名单刻意覆盖 SQLAlchemy session（commit/flush/add/execute/rollback）、
#: repository（create_*/set_*）与 outbox（publish/enqueue）三类真实入口。
FORBIDDEN_SIDE_EFFECT_ATTRS: frozenset[str] = frozenset(
    {
        "commit",
        "rollback",
        "flush",
        "add",
        "add_all",
        "execute",
        "delete",
        "merge",
        "publish",
        "enqueue",
        "broadcast_raw",
        "set_entry_pointer",
        "finalize_candidate",
    }
)


def assert_no_mutation_surface(obj: Any, *, label: str) -> None:
    """逐字段实测 `obj` 没有暴露写库/提交/发事件的能力面。

    只检查 dataclass 的**直接字段值**：adapter 拿到的是 `SyncContext`，它能碰到的
    就是这些字段。递归深挖会把 `Path`/`str` 的内部属性也扫进来，反而制造假红。

    🔴 判据是「字段值上是否**存在可调用**的禁用属性」，不是「源码里是否出现
    `session`」。后者只要改个变量名就能绕过 ⇒ 假绿第②源。
    """
    for spec in dataclass_fields(obj):
        value = getattr(obj, spec.name, None)
        if value is None or isinstance(value, (str, bytes, int, float, bool, Path, uuid.UUID)):
            continue
        hits = sorted(
            name
            for name in FORBIDDEN_SIDE_EFFECT_ATTRS
            if callable(getattr(value, name, None))
        )
        if hits:
            raise AdapterSideEffectError(
                f"{label}.{spec.name} 暴露了写库/提交/发事件能力 {hits} —— adapter 不得 commit、"
                "不得递增 revision、不得更新 pointer、不得发布 outbox；一次 business commit "
                "由 `ContentMutationService` 唯一控制（design §Adapter protocol）"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 2. substrate 准入
# ═══════════════════════════════════════════════════════════════════════════


class SubstrateRole(str, Enum):
    """adapter 读到的底稿字节来源。"""

    #: OO→HTML：application 固定的 incoming artifact（只读）。
    incoming = "incoming"
    #: HTML→OO：published/current representation（只读）。
    published_representation = "published_representation"
    #: 反读校验：**自己刚写出的 staged result**（尚未 publish）。
    #:
    #: Task 37 的 `verify_before_commit` 必须重新打开这份字节做反读等值（AC 6.11 /
    #: 8.11）。它既不是 incoming、也不是 published —— 用前两者中任何一个声明都会说谎：
    #: `incoming` 会让「staged 不是 durable」误报成下载没完成，`published_representation`
    #: 会在「state=staged」上打红。缺这一行时唯一的出路是让 verifier 绕过 substrate 门，
    #: 那会把 quarantined/candidate 的准入判据一起绕掉。
    staged_result = "staged_result"


def assert_substrate_usable(
    *,
    role: SubstrateRole | str,
    artifact_kind: ArtifactKind | str,
    artifact_state: ArtifactState | str,
) -> None:
    """substrate 准入：quarantined / candidate / 非 durable incoming 一律 fail closed。

    三条判据的异常类型刻意不同，让「哪一条在起作用」可分辨：

    * quarantined → :class:`QuarantinedIncomingError`（安全隔离，只可 download-only/expire）
    * incoming 但未 durable → :class:`IncomingNotDurableError`（下载/校验还没完成）
    * kind/role 组合不合法 → :class:`AdapterSubstrateError`（调用方用法错）
    """
    r = role if isinstance(role, SubstrateRole) else SubstrateRole(role)
    kind = artifact_kind if isinstance(artifact_kind, ArtifactKind) else ArtifactKind(artifact_kind)
    state = (
        artifact_state if isinstance(artifact_state, ArtifactState) else ArtifactState(artifact_state)
    )

    if state is ArtifactState.quarantined:
        raise QuarantinedIncomingError(
            f"quarantined artifact 不得进入 adapter（role={r.value}）—— 只允许 "
            "authorization-first download-only、expire 与 retention/legal-hold，"
            "禁止 release、转 durable、创建 application 或进入 extract/merge/retry/rematerialize"
        )
    if kind is ArtifactKind.upgrade_candidate or state is ArtifactState.candidate:
        raise AdapterCandidateSubstrateError(
            f"representation upgrade candidate（kind={kind.value} state={state.value}）"
            "不得作为 adapter substrate —— candidate 永不可被 canonical resolver、room、"
            "download、current pointer、application substrate 或 evidence 使用"
            "（Requirement 6.18）"
        )
    if r is SubstrateRole.staged_result:
        # 反读自己刚写出的 staged result：只允许 `canonical/staged`。
        # quarantined 与 candidate 已在上面被拒，所以这一支不会成为它们的旁路。
        if kind is not ArtifactKind.canonical:
            raise AdapterSubstrateError(
                f"staged result 必须是 kind=canonical，实得 {kind.value}"
            )
        if state is not ArtifactState.staged:
            raise AdapterSubstrateError(
                f"staged result 必须是 state=staged，实得 {state.value} —— 已 publish 的产物"
                "请用 published_representation 角色读"
            )
        return
    if r is SubstrateRole.incoming:
        if kind is not ArtifactKind.incoming:
            raise AdapterSubstrateError(
                f"OO→HTML 的 substrate 必须是 kind=incoming，实得 {kind.value}"
            )
        if state is not ArtifactState.durable:
            raise IncomingNotDurableError(
                f"incoming substrate 必须先 sealing 为 durable，实得 state={state.value} —— "
                "durable 前不得计算 application key、不得 extract"
            )
        return
    if kind is ArtifactKind.incoming:
        raise AdapterSubstrateError(
            "incoming artifact 永不成为 published/current representation，"
            "不得作为 HTML→OO 的 substrate"
        )
    if kind is not ArtifactKind.canonical:
        raise AdapterSubstrateError(
            f"HTML→OO 的 substrate 必须是 kind=canonical 的 published representation artifact，"
            f"实得 {kind.value}"
        )
    if state is not ArtifactState.published:
        raise AdapterSubstrateError(
            f"HTML→OO 的 substrate 必须是已 published 的 representation artifact，"
            f"实得 state={state.value}（staged/orphan/deleted 不可被 resolver/room 使用）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Projection
# ═══════════════════════════════════════════════════════════════════════════

JsonValue = Any


@dataclass(frozen=True)
class FieldValue:
    """一个受管字段的类型化值（design §Merge Algorithm 的规范化字段）。"""

    stable_key: str
    value: JsonValue
    value_type: ValueType
    mode: FieldMode
    row_key: str | None = None

    @property
    def is_protected(self) -> bool:
        return self.mode in {FieldMode.formula, FieldMode.auto_source}


@dataclass(frozen=True)
class Projection:
    """按 stable key 索引的值集合。

    **不是位置数组** —— 行身份走 `row_keys`（contract 声明的 row identity 值），
    列身份走 contract 的 `{slot}_{seq}`。字段「不存在」用键缺失表示，不用哨兵值，
    这样 Task 14 的三方 merge 才能把 MISSING 与「存在但为空」区分开。
    """

    contract_id: str
    semantic_version: str
    document_type: str
    values: Mapping[str, FieldValue]
    row_keys: Mapping[str, tuple[str, ...]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.row_keys is None:
            object.__setattr__(self, "row_keys", {})

    def __contains__(self, stable_key: object) -> bool:
        return stable_key in self.values

    def get(self, stable_key: str) -> FieldValue | None:
        return self.values.get(stable_key)

    def stable_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self.values))

    def assert_matches_contract(self, contract: SyncContract) -> None:
        """projection 的每个 key 必须能在 contract 中解析（行域 key 允许行实例化）。

        行域字段的 contract key 含 `{row_uuid}` 模板，projection 里是具体行值，
        因此比对时把模板段替换成通配再匹配 —— 这一步不允许退化成「只比前缀」，
        否则 `equity_changes/{row_uuid}/closing_amount` 会误配到任何同前缀键。
        """
        if contract.contract_id != self.contract_id:
            raise ProjectionShapeError(
                f"projection 的 contract_id {self.contract_id!r} 与 contract "
                f"{contract.contract_id!r} 不符"
            )
        if contract.document_type != self.document_type:
            raise ProjectionShapeError(
                f"projection 的 document_type {self.document_type!r} 与 contract "
                f"{contract.document_type!r} 不符"
            )
        templates = [
            (spec.stable_field_key, spec.row_scoped) for spec in contract.all_fields()
        ]
        for key, value in self.values.items():
            if value.stable_key != key:
                raise ProjectionShapeError(
                    f"projection 键 {key!r} 与 FieldValue.stable_key {value.stable_key!r} 不符"
                )
            if not _matches_any_template(key, templates, has_row_key=value.row_key is not None):
                raise ProjectionShapeError(
                    f"projection 含 contract 未登记的 stable key: {key!r} —— "
                    "受管字段必须逐条在 per-entry contract 中声明（Property 21）"
                )


def _matches_any_template(
    key: str, templates: Sequence[tuple[str, bool]], *, has_row_key: bool
) -> bool:
    for template, row_scoped in templates:
        if row_scoped != has_row_key:
            continue
        if not row_scoped:
            if key == template:
                return True
            continue
        expected = template.split("/")
        actual = key.split("/")
        if len(expected) != len(actual):
            continue
        if all(
            exp == act or exp == "{row_uuid}"
            for exp, act in zip(expected, actual)
        ):
            return True
    return False


@dataclass(frozen=True)
class ProjectionMutation:
    """adapter stage 出来的**未提交** projection 变更。

    只描述「要写什么」，不含任何写入能力：落库由
    `ContentMutationService.commit(...)` 在一次 lock/expected revision 中完成，
    同时发布兼容 representation。adapter 自己既不 commit 也不递增 revision。
    """

    entry_id: str
    contract_id: str
    expected_revision: int
    projection: Projection
    staged_payload: Mapping[str, Any]
    changed_stable_keys: tuple[str, ...]
    pending_mutation_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="ProjectionMutation")
        if self.expected_revision < 0:
            raise ProjectionShapeError(
                f"expected_revision 不得为负: {self.expected_revision}"
            )
        unknown = [key for key in self.changed_stable_keys if key not in self.projection]
        if unknown:
            raise ProjectionShapeError(
                f"changed_stable_keys 含 projection 里不存在的键: {sorted(unknown)}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 4. materialize / roundtrip 结果
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MaterializeResult:
    """一次 materialize 的产物身份（staged，尚未 publish）+ 本次写盘冻结的结构性声明。

    ═══ 为什么结构性声明要挂在这里（BP-23）═══════════════════════════════════

    `verify_unmanaged_regions` 支持三个归一化入参（`row_shift` / `total_formula_rows` /
    `propagation`），它们的语义是「**写盘之前冻结的声明**」—— 与声明一致的结构变化判等价，
    声明之外的任何改动仍判漂移。

    但那三个参数此前**没有任何生产调用方喂它们**：`ContentMutationService._stage_projection`
    与首版发布宿主都只传 `before/after/contract` 三个参数。于是任何需要结构性插行的 entry
    在未管理区域比对上必然打红 —— 参数存在、单测覆盖、生产零消费，正是本仓库反复登记的
    「additive 注入即死代码」形态（假绿第①源）。

    D2 首版发布是第一个真正触发它的 entry（729 行插入）：
    * 不传 `row_shift` ⇒ `managed_sheet_unmanaged_cells` 238 → 632 判漂移；
    * 传了 `row_shift` 但不传 `propagation` ⇒ 引用侧三张 sheet 的跨 sheet 公式
      （`'明细表D2-2'!$AI$13:$AI$25` → `$AI$754`）判漂移。

    ⇒ 声明必须从 materialize **显式流到** verifier。挂在本类而不是靠 adapter 实例状态：
    实例状态会在「对另一对文件调 verify」时静默套用过期声明，而本类是随产物一起返回的值，
    不存在张冠李戴。

    🔴 三个字段类型标 `Any`：本模块是 adapter 协议层，不该为了类型标注引入
    `excel_row_shift` / `excel_workbook_row_change` 两条 import 边（Word adapter 也用本类，
    它们对它恒为默认值）。运行时形态由 `excel_materialize` 侧的断言把守。
    """

    output_path: Path
    document_type: str
    artifact_sha256: str
    structure_hash: str
    identity_inventory_sha256: str
    managed_field_count: int
    #: 本次结构性插行声明（`excel_row_shift.RowShiftPlan | None`）。`None` = 未插行。
    row_shift: Any = None
    #: 契约声明「携带合计公式」的行号（位移**前**口径）。
    total_formula_rows: tuple[int, ...] = ()
    #: 本次工作簿级传播声明（`excel_workbook_row_change.WorkbookRowChangePlan | None`）。
    workbook_row_change: Any = None

    def __post_init__(self) -> None:
        for name in ("artifact_sha256", "structure_hash", "identity_inventory_sha256"):
            if not is_digest(getattr(self, name)):
                raise AdapterProtocolError(
                    f"MaterializeResult.{name} 必须是非空非全零的 64 位小写 hex，"
                    f"实得 {getattr(self, name)!r}"
                )
        if self.managed_field_count < 0:
            raise AdapterProtocolError("managed_field_count 不得为负")


@dataclass(frozen=True)
class UnmanagedRegionReport:
    """未管理区域（公式/样式/merge/drawing/chart/pivot/Word 正文）的等价性报告。

    `equivalent=False` 时必须给出 `first_difference` —— Requirement 6.10 要求指出
    首个漂移位置，只报「不等价」无法定位。
    """

    equivalent: bool
    inspected_aspects: tuple[str, ...]
    first_difference: str | None = None
    details: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.details is None:
            object.__setattr__(self, "details", {})
        if not self.inspected_aspects:
            raise AdapterProtocolError(
                "UnmanagedRegionReport 必须声明检查了哪些 aspect —— 空清单等于没检查"
            )
        if not self.equivalent and not (self.first_difference or "").strip():
            raise AdapterProtocolError(
                "UnmanagedRegionReport.equivalent=False 时必须给出 first_difference"
            )
        if self.equivalent and (self.first_difference or "").strip():
            raise AdapterProtocolError(
                "UnmanagedRegionReport.equivalent=True 时不得同时给出 first_difference"
            )

    def assert_equivalent(self) -> None:
        if self.equivalent:
            return
        raise UnmanagedRegionDriftError(
            f"未管理区域在 roundtrip 后发生变化，首个差异: {self.first_difference} "
            f"（已检查 {list(self.inspected_aspects)}）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. SyncContext
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SyncContext:
    """adapter 执行上下文：冻结身份 + 只读路径 + immutable bundle 快照。

    刻意**不含** session / repository / outbox / room 可变指针 —— 见模块 docstring
    第 1 条。`bundle` 是 application/representation 固定的快照，`contract` 是按
    bundle 的 contract slot digest 解析出的同一份 per-entry contract。
    """

    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    adapter_id: str
    adapter_build_digest: str
    content_version_id: uuid.UUID
    content_revision: int
    representation_id: uuid.UUID
    representation_generation: int
    document_type: str
    bundle: DefinitionBundleSnapshot
    substrate_path: Path
    substrate_role: SubstrateRole
    contract: SyncContract | None = None
    room_id: uuid.UUID | None = None
    room_generation: int | None = None
    application_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="SyncContext")
        if not is_digest(self.adapter_build_digest):
            raise AdapterProtocolError(
                f"adapter_build_digest 必须是 64 位小写 hex，实得 {self.adapter_build_digest!r}"
            )
        if self.content_revision < 0 or self.representation_generation < 1:
            raise AdapterProtocolError(
                f"content_revision({self.content_revision}) 必须 >=0、"
                f"representation_generation({self.representation_generation}) 必须 >=1"
            )

    def assert_frozen_identity_consistent(self) -> None:
        """contract ↔ bundle typed slots ↔ document_type 三向锁死（Property 28）。

        没有 contract（`custom_authoritative_ooxml` / `opaque_single_onlyoffice`）时
        只校验 bundle 的 contract slot 确实是 typed null marker，而不是「悄悄缺失」。
        """
        contract_slot = self.bundle.slots.get(BundleSlot.contract)
        if contract_slot is None:
            raise AdapterProtocolError(
                "frozen bundle 缺 contract typed slot —— slot omission 必须 fail closed"
            )
        if self.contract is None:
            if contract_slot.is_definition:
                raise AdapterProtocolError(
                    f"bundle 的 contract slot 是 approved definition "
                    f"({contract_slot.slot_digest}) 却没有解析出 SyncContract —— "
                    "projection-based entry 不得在无 contract 的情况下执行"
                )
            return
        if not contract_slot.is_definition:
            raise AdapterProtocolError(
                f"存在 SyncContract 却把 bundle 的 contract slot 写成 typed null marker "
                f"{contract_slot.slot_type!r} —— marker 不得冒充 per-entry contract"
            )
        if contract_slot.slot_digest != self.contract.canonical_sha256:
            raise AdapterProtocolError(
                f"contract canonical digest {self.contract.canonical_sha256!r} 与 bundle "
                f"contract slot digest {contract_slot.slot_digest!r} 不一致 —— "
                "历史 operation 只读 frozen bundle，不得按 alias 重组"
            )
        if self.contract.document_type != self.document_type:
            raise AdapterProtocolError(
                f"contract.document_type={self.contract.document_type!r} 与 context "
                f"{self.document_type!r} 不符"
            )
        self.contract.assert_matches_bundle_slots(self.bundle.slots)


# ═══════════════════════════════════════════════════════════════════════════
# 6. protocol
# ═══════════════════════════════════════════════════════════════════════════


@runtime_checkable
class WorkpaperSyncAdapter(Protocol):
    """文档无关 adapter protocol（design §Adapter protocol 原文签名）。

    实现者必须是**无状态**的：所有身份从 `ctx` 取，禁止在实例上缓存 room/base/
    bundle —— 缓存会让「同一 operation retry 得到不同结果」这类最难查的问题出现。
    """

    adapter_id: str
    document_type: str
    contract_version: str

    async def read_current_projection(self, ctx: SyncContext) -> Projection: ...

    async def stage_projection_mutation(
        self,
        ctx: SyncContext,
        merged: Projection,
        *,
        expected_revision: int,
    ) -> ProjectionMutation: ...

    def materialize(
        self,
        *,
        substrate: Path,
        projection: Projection,
        output: Path,
        contract: SyncContract,
    ) -> MaterializeResult: ...

    def extract(self, *, artifact: Path, contract: SyncContract) -> Projection: ...

    def verify_unmanaged_regions(
        self, *, before: Path, after: Path, contract: SyncContract
    ) -> UnmanagedRegionReport: ...


#: protocol 要求的成员。registry 用它做**结构化**准入校验，而不是 `isinstance`
#: —— `runtime_checkable` 的 Protocol 只查属性存在性，不查签名，单独用它会放过
#: 「方法名对但参数全错」的桩。
ADAPTER_REQUIRED_ATTRS: frozenset[str] = frozenset(
    {"adapter_id", "document_type", "contract_version"}
)
ADAPTER_REQUIRED_METHODS: frozenset[str] = frozenset(
    {
        "read_current_projection",
        "stage_projection_mutation",
        "materialize",
        "extract",
        "verify_unmanaged_regions",
    }
)


__all__ = [
    "AdapterProtocolError", "AdapterSideEffectError", "AdapterSubstrateError",
    "AdapterCandidateSubstrateError",
    "UnmanagedRegionDriftError", "ProjectionShapeError",
    "FORBIDDEN_SIDE_EFFECT_ATTRS", "assert_no_mutation_surface",
    "SubstrateRole", "assert_substrate_usable",
    "FieldValue", "Projection", "ProjectionMutation",
    "MaterializeResult", "UnmanagedRegionReport",
    "SyncContext", "WorkpaperSyncAdapter",
    "ADAPTER_REQUIRED_ATTRS", "ADAPTER_REQUIRED_METHODS",
]
