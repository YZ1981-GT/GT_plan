# -*- coding: utf-8 -*-
"""Excel `WorkpaperSyncAdapter` 实现 —— 把 Task 37/38 的 engine 接到既有 commit 链上。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 38
Requirements: 3.4, 3.5, 6.4, 6.5, 6.6, 6.11, 6.17, 8.10, 8.11, 8.12
Properties: **P9** / **P22** / **P23** / **P24** / **P29** / **P65** / **P66**

═══ 为什么这一层必须存在 ═══

`ContentMutationService._stage_and_verify` 调的是
``adapter.materialize(substrate, projection, output, contract)`` →
``adapter.extract(artifact, contract)`` → ``adapter.verify_unmanaged_regions(before, after,
contract)``；`oo_to_html.extract_three_way` 与 `conflict_resolution` 的 rollback 也只经
``adapter.extract``。没有这一层，Task 37/38 两个模块在生产链上**一个消费方都没有** ——
那正是本 spec 反复强调的「additive 注入即死代码」（假绿第①源）。

═══ 无状态 vs 冻结身份：protocol 签名逼出来的做法 ═══

protocol 只给 `materialize`/`extract` 传 `contract`，而 identity-aware engine 还需要
`FrozenEntryDefinitions`（bundle/authority/identity inventory）与 `ExcelIdentityBinding`
（Table 名 / UUID 列 / tombstone 清册 / 动态列实测绑定）。因此 adapter **按 operation 构造**
并把这些冻结值作为不可变字段带着走 —— 不是「在实例上缓存 room/base/bundle」，而是
「这一个 operation 的身份就是构造参数」。

为了让「拿 A entry 的 adapter 去处理 B entry」不可能发生，:meth:`_assert_same_contract`
在每次 `materialize`/`extract`/`verify_unmanaged_regions` 入口比对传入 contract 的
canonical digest 与冻结 contract 的 digest：不一致立刻抛。protocol 的窄签名本来会让这种
串台完全不可见。

═══ 本层不做的事 ═══

* 不 commit、不递增 revision、不切 pointer、不发 outbox —— `assert_no_mutation_surface`
  在构造时逐字段实测本 adapter 没有这些能力面；
* 不做三方 merge（Task 14 / Task 26 的活）；
* 不自己判 identity 语义（全部委派 Task 37）。
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.services.workpaper_sync.adapters.base import (
    AdapterProtocolError,
    MaterializeResult,
    Projection,
    ProjectionMutation,
    SubstrateRole,
    SyncContext,
    UnmanagedRegionReport,
    assert_no_mutation_surface,
)
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.excel_entry_gate import FrozenEntryDefinitions
from app.services.workpaper_sync.excel_extract import (
    ExcelIdentityBinding,
    assert_engine_entry_definitions,
    extract_projection,
    resolve_managed_region,
    verify_unmanaged_regions,
)
from app.services.workpaper_sync.excel_materialize import (
    ExcelWriteCapability,
    materialize_projection,
)
from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState

__all__ = [
    "ExcelAdapterIdentityError",
    "ExcelSyncAdapter",
    "STAGING_NAMESPACE",
    "build_excel_adapter",
]

#: Task 11 `ArtifactStorageLayout.staging_dir` 的固定命名空间目录名。
STAGING_NAMESPACE: str = ".staging"


class ExcelAdapterIdentityError(AdapterProtocolError):
    """传进来的 contract 与 adapter 冻结的 contract 不是同一份（跨 entry 串台）。"""

    error_code = "excel_adapter_contract_identity_mismatch"


@dataclass(frozen=True)
class ExcelSyncAdapter:
    """一个 operation 的 Excel adapter。**冻结身份 + 无写入面**。

    `substrate_kind` / `substrate_state` 描述 `materialize` 的 substrate 形态：
    HTML→OO 是 `canonical/published`，OO→HTML 的 rematerialize 是 `incoming/durable`。
    由调用方按方向给，Task 13 的 `assert_substrate_usable` 在 engine 入口逐条判。
    """

    definitions: FrozenEntryDefinitions
    binding: ExcelIdentityBinding
    substrate_role: SubstrateRole = SubstrateRole.published_representation
    substrate_kind: ArtifactKind = ArtifactKind.canonical
    substrate_state: ArtifactState = ArtifactState.published
    capability: ExcelWriteCapability | None = None
    limits: SyncLimits | None = None
    #: OO→HTML 的 baseline 来源（application 冻结的 base representation）。给了才做受保护格
    #: 篡改分类；`extract` 对**这份**文件本身不套 baseline（它就是 baseline）。
    baseline_representation: Path | None = None
    #: 同 workbook 其它受管 sheet 的 binding（首版 / 重投影写全表时用；日常单 sheet 切页为空）。
    sibling_bindings: tuple[ExcelIdentityBinding, ...] = ()
    _baseline: dict[str, Any] = dataclass_field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="ExcelSyncAdapter")
        assert_engine_entry_definitions(self.definitions)
        if self.definitions.contract.document_type != "xlsx":
            raise ExcelAdapterIdentityError(
                f"ExcelSyncAdapter 只接 xlsx，实得 "
                f"{self.definitions.contract.document_type!r}"
            )

    # ── protocol 属性 ────────────────────────────────────────────────
    @property
    def adapter_id(self) -> str:
        return self.definitions.adapter_build.adapter_id

    @property
    def document_type(self) -> str:
        return self.definitions.contract.document_type

    @property
    def contract_version(self) -> str:
        return self.definitions.contract.semantic_version

    # ── 内部 ────────────────────────────────────────────────────────
    @property
    def _limits(self) -> SyncLimits:
        return self.limits or load_limits()

    def _assert_same_contract(self, contract: SyncContract, *, where: str) -> None:
        """传入 contract 必须与冻结 contract 逐 digest 相同（Property 28 的 adapter 侧）。

        protocol 只传 contract 不传 bundle，所以「adapter 是按哪个 bundle 造的」在签名上
        看不见。少了这一条，把 A entry 的 adapter 复用到 B entry 会静默按 A 的 identity
        binding 去写 B 的文件 —— 受管格全部错位而没有任何报错。
        """
        frozen = self.definitions.contract
        if contract.canonical_sha256 != frozen.canonical_sha256:
            raise ExcelAdapterIdentityError(
                f"{where}: 传入 contract {contract.contract_id!r} 的 canonical digest "
                f"{contract.canonical_sha256[:12]}… 与 adapter 冻结的 "
                f"{frozen.contract_id!r}/{frozen.canonical_sha256[:12]}… 不一致 —— "
                "adapter 按 operation 冻结身份构造，不得跨 entry 复用"
            )

    def _all_bindings(self) -> tuple[ExcelIdentityBinding, ...]:
        if not self.sibling_bindings:
            return (self.binding,)
        seen = {self.binding.table_key}
        out: list[ExcelIdentityBinding] = [self.binding]
        for binding in self.sibling_bindings:
            if binding.table_key in seen:
                continue
            seen.add(binding.table_key)
            out.append(binding)
        return tuple(out)

    def _merge_projections(self, parts: Sequence[Projection]) -> Projection:
        if len(parts) == 1:
            return parts[0]
        values: dict[str, Any] = {}
        row_keys: dict[str, tuple[str, ...]] = {}
        for part in parts:
            values.update(part.values)
            for table_key, keys in part.row_keys.items():
                merged = list(row_keys.get(table_key, ()))
                for key in keys:
                    if key not in merged:
                        merged.append(key)
                row_keys[table_key] = tuple(merged)
        head = parts[0]
        return Projection(
            contract_id=head.contract_id,
            semantic_version=head.semantic_version,
            document_type=head.document_type,
            values=values,
            row_keys=row_keys,
        )

    def _baseline_pair(self) -> tuple[Projection | None, Mapping[str, str] | None]:
        """从冻结的 base representation 现算 `(baseline projection, baseline formulas)`。

        缓存键是**冻结路径本身**（构造参数），因此「同一 operation retry 得到同一结果」
        成立；它不是可变状态，也不跨 operation 共享（adapter 按 operation 构造）。
        """
        if self.baseline_representation is None:
            return (None, None)
        cached = self._baseline.get("pair")
        if cached is None:
            from app.services.workpaper_sync.excel_rematerialize import (
                derive_baseline_from_representation,
            )

            cached = derive_baseline_from_representation(
                representation=self.baseline_representation,
                definitions=self.definitions,
                binding=self.binding,
                limits=self._limits,
            )
            self._baseline["pair"] = cached
        return cached

    # ── protocol 方法 ───────────────────────────────────────────────
    async def read_current_projection(self, ctx: SyncContext) -> Projection:
        """读 `ctx.substrate_path` 的受管 projection（HTML→OO 的现状快照）。"""
        ctx.assert_frozen_identity_consistent()
        if ctx.contract is not None:
            self._assert_same_contract(ctx.contract, where="read_current_projection")
        _, kind, state = self._substrate_shape_of(ctx.substrate_path)
        return extract_projection(
            artifact=ctx.substrate_path,
            definitions=self.definitions,
            binding=self.binding,
            substrate_role=ctx.substrate_role,
            artifact_kind=kind,
            artifact_state=state,
            limits=self._limits,
        ).projection

    async def stage_projection_mutation(
        self, ctx: SyncContext, merged: Projection, *, expected_revision: int
    ) -> ProjectionMutation:
        """把 merged projection 包成**未提交**的 mutation。落库由 Task 15 唯一控制。"""
        ctx.assert_frozen_identity_consistent()
        if ctx.contract is not None:
            self._assert_same_contract(ctx.contract, where="stage_projection_mutation")
        merged.assert_matches_contract(self.definitions.contract)
        return ProjectionMutation(
            entry_id=self.definitions.entry_id,
            contract_id=self.definitions.contract.contract_id,
            expected_revision=expected_revision,
            projection=merged,
            staged_payload={
                "contract_id": merged.contract_id,
                "semantic_version": merged.semantic_version,
                "document_type": merged.document_type,
                "stable_keys": list(merged.stable_keys()),
            },
            changed_stable_keys=merged.stable_keys(),
        )

    def materialize(
        self,
        *,
        substrate: Path,
        projection: Projection,
        output: Path,
        contract: SyncContract,
    ) -> MaterializeResult:
        """写 staged 产物。反读门由 `ContentMutationService` 紧随其后的 `extract` 完成。

        OO→HTML：OnlyOffice 可能保留 `_GT_SYNC` 清册项却掏空 sheetData。此时从冻结的
        base representation 重注 runtime binding 到**临时** xlsx 再写；durable incoming
        本体一字不动（AC 8.10）。
        """
        self._assert_same_contract(contract, where="materialize")
        repaired: Path | None = None
        substrate_for_write = substrate
        g7_sanitized: Path | None = None
        try:
            # OO→HTML：OnlyOffice 可能保留 `_GT_SYNC` 清册却掏空 sheetData。从冻结的
            # base representation 重注到临时 xlsx；durable incoming 本体一字不动（AC 8.10）。
            # 路径命名空间也认 `.incoming/`：registry 上常见 `html_to_oo` 复用实例，
            # 此时 `substrate_kind` 仍是 canonical，不能只靠 kind 门。
            incoming_ns = (
                self.substrate_kind is ArtifactKind.incoming
                or ".incoming" in substrate.resolve().parts
            )
            if self.baseline_representation is not None and incoming_ns:
                from app.services.workpaper_sync.excel_extract import (
                    reinject_runtime_binding_from_base_if_needed,
                )

                repaired = reinject_runtime_binding_from_base_if_needed(
                    incoming=substrate,
                    base=self.baseline_representation,
                    metadata_sheet=self.binding.metadata_sheet,
                )
                if repaired is not None:
                    substrate_for_write = repaired
            # G7：OnlyOffice 对部分 IF() 在加载期 tocBool 崩溃（error -82）。在 substrate
            # 副本上中性化后再 materialize，使 before/after 公式集一致、哈希自洽。
            if self.adapter_id == "g7.soe_subsidiary_disclosure":
                import shutil

                from app.services.workpaper_sync.pilot_g7_two_level_dynamic import (
                    neutralize_oo_crash_if_formulas,
                )

                g7_sanitized = substrate_for_write.with_name(
                    substrate_for_write.name + ".g7-noif.xlsx"
                )
                shutil.copy2(substrate_for_write, g7_sanitized)
                neutralize_oo_crash_if_formulas(g7_sanitized)
                substrate_for_write = g7_sanitized

            bindings = self._all_bindings()
            role = (
                SubstrateRole.incoming if incoming_ns else self.substrate_role
            )
            kind = ArtifactKind.incoming if incoming_ns else self.substrate_kind
            state = ArtifactState.durable if incoming_ns else self.substrate_state
            if len(bindings) == 1:
                result = materialize_projection(
                    substrate=substrate_for_write,
                    projection=projection,
                    output=output,
                    definitions=self.definitions,
                    binding=bindings[0],
                    substrate_role=role,
                    substrate_kind=kind,
                    substrate_state=state,
                    capability=self.capability,
                    limits=self._limits,
                ).result
                from app.services.workpaper_sync.phase5_d4_29_customer_detail import materialize_file, is_enabled
                if is_enabled(contract):
                    # D4-29 转置写盘后只刷新 artifact 字节摘要；structure_hash 由
                    # ContentMutationService._projection_structure_hash（与观测器同构）覆盖，
                    # 不得用 normalized_structure_hash（整簿指纹）覆盖 —— 那会立刻漂移。
                    import dataclasses
                    import hashlib
                    materialize_file(output, projection, contract)
                    result = dataclasses.replace(
                        result,
                        artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                    )
                return result

            # 多受管 sheet：按 binding 顺序叠写同一份 workbook（首版 / 重投影）。
            # 🔴 row_shift / total_formula_rows / identity 清册保留**主 binding**那一趟的声明：
            #    末趟（sibling）常无插行 ⇒ row_shift=None，若用末趟结果喂 verify，主 sheet 的
            #    插行会被判成 unmanaged drift（D4 rematerialize 实测 169→253）。
            #
            # 🔴 但 workbook_row_change 例外：它必须是**全部趟**的位移声明并集，不能只留主 binding。
            #    多 sheet 各趟对 xl/workbook.xml own-sheet definedName（GT_FOOTER_ANCHOR_D42x /
            #    _xlnm.Print_Area）的合法位移各自声明在自己那趟的 workbook_row_change 里；只留主
            #    binding（如 D4-29 转置表无这些位移）会让 sibling（D4-22/D4-23）的合法 workbook.xml
            #    位移在 verify 时无声明可归一化 ⇒ 逐字节判 adapter_unmanaged_region_drift。
            #    收集每趟 step.workbook_row_change，返回前合并成一份 MaterializeWorkbookChangeSet。
            #    （spec multi-sheet-materialize-defined-name-shift-normalization）
            import dataclasses
            import tempfile

            from app.services.workpaper_sync.excel_workbook_row_change import (
                merge_workbook_row_change_propagations,
            )

            current = substrate_for_write
            primary_result: MaterializeResult | None = None
            last_result: MaterializeResult | None = None
            field_count = 0
            trip_changes: list[Any] = []
            # 每张**发生插行**的 sheet 各自那趟的位移声明,供 verify 按 sheet 分派归一化。
            # 主 binding 不一定是插行的那张（真实场景 D4-2 未插、D4-22/D4-23 插）——只留主
            # binding 的 row_shift 会让 sibling 的 managed_sheet_* 桶漏归一化判 drift（§4b）。
            per_table_shift: dict[str, tuple[Any, Any]] = {}
            tmp_paths: list[Path] = []
            try:
                for index, binding in enumerate(bindings):
                    is_last = index == len(bindings) - 1
                    if is_last:
                        target = output
                    else:
                        handle = tempfile.NamedTemporaryFile(
                            suffix=f".sheet{index}.xlsx", delete=False
                        )
                        handle.close()
                        target = Path(handle.name)
                        tmp_paths.append(target)
                    step = materialize_projection(
                        substrate=current,
                        projection=projection,
                        output=target,
                        definitions=self.definitions,
                        binding=binding,
                        substrate_role=role,
                        substrate_kind=kind,
                        substrate_state=state,
                        capability=self.capability,
                        limits=self._limits,
                        retain_identity_inventory=(
                            binding.table_key == self.binding.table_key
                        ),
                    ).result
                    field_count += int(step.managed_field_count)
                    if step.workbook_row_change is not None:
                        trip_changes.append(step.workbook_row_change)
                    if step.row_shift is not None:
                        per_table_shift[binding.table_key] = (
                            step.row_shift,
                            step.total_formula_rows,
                        )
                    if binding.table_key == self.binding.table_key:
                        primary_result = step
                    last_result = step
                    current = target
            finally:
                for path in tmp_paths:
                    path.unlink(missing_ok=True)
            assert last_result is not None
            assert primary_result is not None
            from app.services.workpaper_sync.phase5_d4_29_customer_detail import materialize_file, is_enabled
            if is_enabled(contract):
                # D4-29 转置写盘后只刷新 artifact 字节摘要；structure_hash 由
                # ContentMutationService._projection_structure_hash（与观测器同构）覆盖。
                import hashlib
                materialize_file(output, projection, contract)
                last_result = dataclasses.replace(
                    last_result,
                    artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                )
            # workbook_row_change = 全部趟的位移声明并集（含主 binding + sibling 的
            # workbook.xml own-sheet definedName 位移 + 引用侧 sheet 传播）。
            merged_change = merge_workbook_row_change_propagations(trip_changes)
            return dataclasses.replace(
                primary_result,
                managed_field_count=field_count,
                output_path=output,
                # 产物字节摘要以末趟为准（含全部 sibling 写入）。
                artifact_sha256=last_result.artifact_sha256,
                # structure_hash 是 workbook 级，末趟与主趟同值；identity 清册必须用主
                # binding：observer/_frozen_anchors 只锚主表，末趟 sibling 的 digest
                # 会写成 D43 清册并与观测器重算的 D42 清册漂移（D4 rematerialize 实测）。
                structure_hash=last_result.structure_hash,
                identity_inventory_sha256=primary_result.identity_inventory_sha256,
                workbook_row_change=merged_change,
                per_table_shift=(per_table_shift or None),
            )
        finally:
            if repaired is not None:
                repaired.unlink(missing_ok=True)
            if g7_sanitized is not None:
                g7_sanitized.unlink(missing_ok=True)

    def extract(self, *, artifact: Path, contract: SyncContract) -> Projection:
        """反读受管 projection。

        `artifact` 的 substrate 形态按**它是谁**判：

        * 它就是冻结的 base representation ⇒ `canonical/published`，且不套 baseline
          （它自己就是 baseline）；
        * 它是 `materialize` 刚写出的 staged 产物 ⇒ `canonical/staged`；
        * 其余（incoming）⇒ 按 adapter 构造时给的 kind/state，并套 base baseline 做受保护格
          篡改分类（Property 24 的生产可见性）。

        三支各自有真实调用点：`oo_to_html` 依次读 base / current / incoming，
        `ContentMutationService` 读自己刚写的 staged 产物。
        """
        self._assert_same_contract(contract, where="extract")
        baseline, baseline_formulas = self._baseline_pair()
        role, kind, state = self._substrate_shape_of(artifact)
        if role is SubstrateRole.published_representation:
            baseline, baseline_formulas = (None, None)
        parts: list[Projection] = []
        for binding in self._all_bindings():
            parts.append(
                extract_projection(
                    artifact=artifact,
                    definitions=self.definitions,
                    binding=binding,
                    substrate_role=role,
                    artifact_kind=kind,
                    artifact_state=state,
                    baseline=baseline,
                    baseline_formulas=baseline_formulas,
                    limits=self._limits,
                    # 冻结 inventory 只锁主 sheet；sibling 表列跨度不同，不得拿主表期望比对。
                    retain_identity_inventory=binding.table_key == self.binding.table_key,
                ).projection
            )
        from app.services.workpaper_sync.phase5_d4_29_customer_detail import is_enabled, extract_file
        if is_enabled(contract):
            parts.append(extract_file(artifact, contract))
        return self._merge_projections(parts)

    def _substrate_shape_of(
        self, artifact: Path
    ) -> tuple[SubstrateRole, ArtifactKind, ArtifactState]:
        """按**路径身份**判 substrate 形态，四支各有真实调用点。

        判据不用「这是第几次调用」：按调用序号推断在 retry / 乱序下必然错，而 base
        representation 的路径是 application 冻结的值、staging 目录名是 Task 11 的固定
        命名空间。

        * base representation（`oo_to_html` 先读它）⇒ `canonical/published`
        * `.staging/` 下的产物（`ContentMutationService` 反读自己刚写的）⇒ `canonical/staged`
        * OO→HTML 方向的其余文件 ⇒ 本次 incoming，按构造时给的 kind/state
        * 其余（HTML→OO 的 substrate、`oo_to_html` 读的 current representation）⇒
          `canonical/published`
        """
        published = (
            SubstrateRole.published_representation,
            ArtifactKind.canonical,
            ArtifactState.published,
        )
        resolved = artifact.resolve()
        if (
            self.baseline_representation is not None
            and resolved == self.baseline_representation.resolve()
        ):
            return published
        if STAGING_NAMESPACE in resolved.parts:
            return (
                SubstrateRole.staged_result,
                ArtifactKind.canonical,
                ArtifactState.staged,
            )
        if self.substrate_kind is ArtifactKind.incoming:
            return (SubstrateRole.incoming, self.substrate_kind, self.substrate_state)
        return published

    def verify_unmanaged_regions(
        self,
        *,
        before: Path,
        after: Path,
        contract: SyncContract,
        row_shift: Any = None,
        total_formula_rows: Any = (),
        propagation: Any = None,
        per_table_shift: Any = None,
    ) -> UnmanagedRegionReport:
        """未管理区域比对。判据实现全部在 Task 37，本层只解析受管区域后转手。

        三个归一化入参都是本次 materialize **写盘之前冻结**的声明，由
        :class:`~app.services.workpaper_sync.adapters.base.MaterializeResult` 随产物带出：

        * `row_shift`（`excel_row_shift.RowShiftPlan | None`）—— 结构性插行声明。给了它，
          verifier 就用同一份声明把 after 侧**受管 sheet** 的行号反向归一化后再比对；
        * `total_formula_rows` —— 契约声明携带合计公式的行（位移前口径），合计区间的
          合法扩张按它求值；
        * `propagation`（`excel_workbook_row_change.WorkbookRowChangePlan | None`）——
          工作簿级传播声明。给了它，verifier 才知道**引用侧 sheet** 上那些跨 sheet 公式的
          行号改写是本次声明过的（`'明细表D2-2'!$AI$25` → `$AI$754`），否则整桶
          `other_sheet_parts` 判漂移。

        三者都是**声明值而非观测值** ⇒ 与声明一致判等价、声明之外的任何改动仍判漂移。
        事后从 diff 推断等于让被检查对象自己声明自己合法（design.md 拒绝方案第 3 条）。

        🔴 默认值让它保持**纯增量**：都不传时行为与加参数之前逐字相同，既有调用方
        （含 `adapters/base` 协议里只声明三个参数的实现）不受影响。
        类型标 `Any` 而不是 import 那两个 plan 类型：本层只做转手，不碰它们的任何成员，
        标死类型反而给本模块加两条不必要的 import 边。
        """
        self._assert_same_contract(contract, where="verify_unmanaged_regions")
        # G7：materialize 在 substrate 副本上中性化 IF()；before 必须用同一口径，
        # 否则 verifier 会把「清 IF」误判成 unmanaged 公式漂移，commit 永远进不去，
        # OO 继续吃带 IF 的 published 表示 → error -82。
        before_for_compare = before
        g7_before_sanitized: Path | None = None
        d429_before: Path | None = None
        try:
            from app.services.workpaper_sync.phase5_d4_29_customer_detail import (
                is_enabled, materialize_transposed_workbook, extract_transposed_workbook,
            )
            if is_enabled(contract):
                import tempfile
                handle = tempfile.NamedTemporaryFile(suffix=".d429-before.xlsx", delete=False)
                handle.close()
                d429_before = Path(handle.name)
                d429_before.write_bytes(materialize_transposed_workbook(
                    before.read_bytes(), extract_transposed_workbook(after.read_bytes())
                ))
                before_for_compare = d429_before
            if self.adapter_id == "g7.soe_subsidiary_disclosure":
                import shutil

                from app.services.workpaper_sync.pilot_g7_two_level_dynamic import (
                    neutralize_oo_crash_if_formulas,
                )

                g7_before_sanitized = before.with_name(
                    before.name + ".g7-noif-before.xlsx"
                )
                shutil.copy2(before, g7_before_sanitized)
                neutralize_oo_crash_if_formulas(g7_before_sanitized)
                before_for_compare = g7_before_sanitized
            with zipfile.ZipFile(after) as zf:
                regions_by_binding: list[tuple[ExcelIdentityBinding, Any]] = []
                for binding in self._all_bindings():
                    regions_by_binding.append(
                        (
                            binding,
                            resolve_managed_region(
                                zf,
                                contract=self.definitions.contract,
                                binding=binding,
                            ),
                        )
                    )
            all_managed_parts = frozenset(
                region.sheet_part for _binding, region in regions_by_binding
            )
            last_report: UnmanagedRegionReport | None = None
            for binding, region in regions_by_binding:
                extra = all_managed_parts - {region.sheet_part}
                # 🔴 每张 sheet 的 shift-aware 归一化必须用**它自己那趟**的 row_shift /
                #    total_formula_rows。多 sheet 场景里主 binding 不一定是插行的 sheet
                #    （真实：D4-2 未插、D4-22/D4-23 插）——只按 "是否主 binding" 分派会把
                #    sibling 的合法插行判 managed_sheet_* drift（§4b）。
                #    per_table_shift 给了就按 region.table_key 取本表声明；没给（Word/单 sheet
                #    /旧调用方）则回退旧口径（主 binding 标量 + sibling None），纯增量。
                if per_table_shift is not None:
                    this_shift, this_total = per_table_shift.get(
                        region.table_key, (None, ())
                    )
                else:
                    is_primary = binding.table_key == self.binding.table_key
                    this_shift = row_shift if is_primary else None
                    this_total = total_formula_rows if is_primary else ()
                # 插行 / 工作簿传播声明来自主 sheet 那一趟；sibling 校验仍要带上，
                # 否则 workbook.xml definedName 位移会被判成 workbook_and_styles 漂移。
                last_report = verify_unmanaged_regions(
                    before=before_for_compare,
                    after=after,
                    contract=self.definitions.contract,
                    region=region,
                    binding=binding,
                    limits=self._limits,
                    row_shift=this_shift,
                    total_formula_rows=this_total,
                    propagation=propagation,
                    extra_managed_sheet_parts=extra,
                )
                last_report.assert_equivalent()
            assert last_report is not None
            return last_report
        finally:
            if d429_before is not None:
                d429_before.unlink(missing_ok=True)
            if g7_before_sanitized is not None:
                g7_before_sanitized.unlink(missing_ok=True)


def build_excel_adapter(
    *,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    direction: str,
    baseline_representation: Path | None = None,
    capability: ExcelWriteCapability | None = None,
    limits: SyncLimits | None = None,
    sibling_bindings: tuple[ExcelIdentityBinding, ...] = (),
) -> ExcelSyncAdapter:
    """按方向构造 adapter。`direction` 是封闭词表，不接受自由文本。

    两条方向的 substrate 形态是 design §Materialize 第 1 条的直译，写在这里唯一一处：

    * ``html_to_oo`` → `published_representation / canonical / published`
    * ``oo_to_html`` → `incoming / incoming / durable`
    """
    shapes: Mapping[str, tuple[SubstrateRole, ArtifactKind, ArtifactState]] = {
        "html_to_oo": (
            SubstrateRole.published_representation,
            ArtifactKind.canonical,
            ArtifactState.published,
        ),
        "oo_to_html": (SubstrateRole.incoming, ArtifactKind.incoming, ArtifactState.durable),
    }
    if direction not in shapes:
        raise ExcelAdapterIdentityError(
            f"direction={direction!r} 不在封闭词表 {sorted(shapes)} 内 —— substrate 形态"
            "不得由自由文本决定（AC 8.10）"
        )
    role, kind, state = shapes[direction]
    if direction == "oo_to_html" and baseline_representation is None:
        raise ExcelAdapterIdentityError(
            "oo_to_html 方向必须给 application 冻结的 base representation —— 它是受保护格"
            "篡改分类（Property 24）的 baseline 来源，缺它等于关掉那条判据"
        )
    return ExcelSyncAdapter(
        definitions=definitions,
        binding=binding,
        substrate_role=role,
        substrate_kind=kind,
        substrate_state=state,
        capability=capability,
        limits=limits,
        baseline_representation=baseline_representation,
        sibling_bindings=sibling_bindings,
    )
