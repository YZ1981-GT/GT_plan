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
    release_scoped_workbooks,
    resolve_managed_region,
    verify_unmanaged_regions,
    workbook_read_scope,
)
from app.services.workpaper_sync.excel_materialize import (
    ExcelWriteCapability,
    materialize_projection,
)
from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState

import logging

logger = logging.getLogger(__name__)

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


def _resolve_oo_crash_neutralization_fn(adapter_id: str):
    """按注册表声明取该 adapter 的 OO 崩溃中性化函数（取代硬编码 adapter_id 字面量分支）。

    spec: d1-sync-row-table-engine-and-d1-coverage · Task 13 · Requirements 3.1 / 7.1

    未注册、或注册了但未声明 `oo_crash_neutralization_fn`、或声明的 provider 模块未真正
    导出该函数名，一律返回 `None`（保持原字面量分支等价的软跳过语义——这不是新增校验，
    原代码本就只对唯一一家 adapter 生效，其余家从不进这段逻辑）。
    """
    import importlib

    from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

    plan = STORE_MERGE_REGISTRY.get(adapter_id)
    if plan is None or not plan.oo_crash_neutralization_fn:
        return None
    module = importlib.import_module(f"app.services.workpaper_sync.{plan.provider_module}")
    return getattr(module, plan.oo_crash_neutralization_fn, None)


def _sheet_cumulative_shift(
    per_table_shift: Mapping[str, tuple[Any, Any]],
    *,
    sheet_of_table: Mapping[str, str],
    sheet_part: str,
) -> tuple[Any, tuple[int, ...]]:
    """某张 sheet 上**全部趟**的累积位移声明 + 合并后的合计行集合。

    ═══ 为什么不能按 `region.table_key` 取单趟 ═══

    同 sheet 多受管区（D4-1 主营/其他、D4-9 本期/上期、D4-20 三区、D4-34、D4-36）在
    **逐趟链式** materialize 下会让**同一个 sheet part 被插多次行**（D4-1 实测：主营 7 行 +
    其他 2 行）。verify 的归一化是「把 after 行号反向映射回 before」，而两次插行的复合映射
    **不是**单个 `(insert_at, count)` 能表达的 ⇒ 原先按 `per_table_shift.get(table_key)`
    取单趟，归一化后两侧仍不等 ⇒ 与计划一致的插行被判 `adapter_unmanaged_region_drift`
    （实测 `managed_sheet_unmanaged_cells` 280 → 340）。

    **顺序即正确性**：`per_table_shift` 是 dict，键序 = `_materialize_within_scope` 里
    `for index, binding in enumerate(bindings)` 的**逐趟顺序**（Python 3.7+ 保序）。
    `CompositeRowShift` 依赖这个顺序做链式 unshift（逆序还原），故本函数按 `per_table_shift`
    的原生迭代序收集，**不**排序。

    单趟时返回**原 `RowShiftPlan`**（不包 composite）⇒ 单 sheet / Word / 旧调用方逐字节
    行为不变（纯增量纪律）。
    """
    from app.services.workpaper_sync.excel_row_shift import CompositeRowShift

    plans: list[Any] = []
    totals: list[int] = []
    seen_totals: set[int] = set()
    for table_key, entry in per_table_shift.items():
        if sheet_of_table.get(table_key) != sheet_part:
            continue
        shift, table_totals = entry
        # 🔴 **每趟的 `total_formula_rows` 是「它自己那趟的位移前」口径，不是最初 before**。
        #    第 2 趟看到的 substrate 已经被第 1 趟插过行：D4-1 其他区合计行在最初模板是 18，
        #    但其他区那趟声明的是 **25**（= 18 + 主营插的 7）。而 verify 的
        #    `_is_total_row` 拿的是**完全归一化回最初 before** 的坐标 ⇒ 用 25 去比永远不中
        #    ⇒ 其他区合计公式的扩张不被还原 ⇒ `managed_sheet_unmanaged_cells` 仍判 drift
        #    （项数已对齐、只有内容不等，正是这个形态）。
        #    故把本趟 totals 经**已收集的前序趟** unshift 逆序映射回最初 before 口径。
        prior = tuple(plans)
        for row in table_totals or ():
            normalised = int(row)
            for plan in reversed(prior):
                normalised = plan.unshift(normalised)
            if normalised not in seen_totals:
                seen_totals.add(normalised)
                totals.append(normalised)
        if shift is not None:
            plans.append(shift)
    if not plans:
        return None, ()
    if len(plans) == 1:
        return plans[0], tuple(totals)
    return CompositeRowShift(plans=tuple(plans)), tuple(totals)


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
        # 🔴 多 binding 底稿的写盘路径里也有「同一个文件被解析多遍」：每趟
        # `materialize_projection` 内部要反读**同一个**输入文件的两个视图
        # （data_only True/False）。D4-营业收入实测 39 趟 ⇒ `openpyxl.load_workbook`
        # 90 次、累计 40.3s，占 `adapter.materialize` 42.8s 的绝大部分。
        # 作用域让每趟的两个视图共享一次解析（78 → 39 次真实解析）。
        # 趟与趟之间**不共享**：链式中间产物各是不同文件（缓存键含 mtime/size），
        # 因此不存在「读到上一趟旧字节」的可能。
        # 🔴 下面每一处 `unlink` 之前都必须 `release_scoped_workbooks`，否则缓存里的
        # zip 句柄会让 Windows 删不掉临时文件。
        with workbook_read_scope():
            return self._materialize_within_scope(
                substrate=substrate,
                projection=projection,
                output=output,
                contract=contract,
                repaired=repaired,
                substrate_for_write=substrate_for_write,
                g7_sanitized=g7_sanitized,
            )

    def _materialize_within_scope(
        self,
        *,
        substrate: Path,
        projection: Projection,
        output: Path,
        contract: SyncContract,
        repaired: Path | None,
        substrate_for_write: Path,
        g7_sanitized: Path | None,
    ) -> MaterializeResult:
        """:meth:`materialize` 的本体。拆出来只为让作用域包住整趟，不改任何判据。"""
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
            # OO 加载期公式崩溃中性化（如 G7 的 IF() tocBool 崩溃 error -82）：在 substrate
            # 副本上中性化后再 materialize，使 before/after 公式集一致、哈希自洽。
            # 🔴 Task 13 收敛（需求 3.1/7.1）：原字面量分支 `if self.adapter_id ==
            # "g7.soe_subsidiary_disclosure"` 改走注册表声明 `oo_crash_neutralization_fn`
            # （requirements.md 现状红基线「adapters/excel 2 处」）。哪家需要这个 workaround
            # 由 provider 侧在注册表里显式登记，框架层不再认识具体 adapter_id 字符串。
            _neutralize_fn = _resolve_oo_crash_neutralization_fn(self.adapter_id)
            if _neutralize_fn is not None:
                import shutil

                g7_sanitized = substrate_for_write.with_name(
                    substrate_for_write.name + ".g7-noif.xlsx"
                )
                shutil.copy2(substrate_for_write, g7_sanitized)
                _neutralize_fn(g7_sanitized)
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
                from app.services.workpaper_sync.phase5_transposed_sheet import materialize_file as _transposed_materialize_file
                from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs
                specs = resolve_transposed_specs(contract)
                if specs:
                    # 转置写盘后只刷新 artifact 字节摘要；structure_hash 由
                    # ContentMutationService._projection_structure_hash（与观测器同构）覆盖，
                    # 不得用 normalized_structure_hash（整簿指纹）覆盖 —— 那会立刻漂移。
                    # 多张转置 sheet（D4-29/D4-12…）逐 spec 覆盖各自的列。
                    import dataclasses
                    import hashlib
                    for spec in specs:
                        _transposed_materialize_file(output, projection, spec=spec)
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

            # 🔴 单趟写入优先（spec oo-single-pass-materialize-and-room-leave）：全部 binding
            #    的计划只解析一次 substrate、写入合成一趟。它在「任一 binding 需插行 / 用
            #    openpyxl 全量重写 / 两 binding 写同一格**且 payload 不同**」时**显式 decline**，
            #    回落下面的逐趟链式路径（语义与改动前逐字相同，只是慢）。
            #    ⚠️ 第三条不是「同 sheet」也不是「坐标相交」：同格但 payload 逐字段相同是恒等
            #    覆盖（D4 的 sheet14 C24/E24/C38/E38 四格），按坐标 decline 会把 D4 挡在单趟
            #    之外 —— 而 D4 正是需求 1.5 指名的 entry。判据见
            #    `excel_materialize._cross_binding_payload_conflicts`。
            #    decline 而非静默回落：真库上要能统计回落比例（Requirement 3）。
            #    🔴 下面那条逐趟链式路径**不是死代码**：它是 decline 三条（插行 / openpyxl
            #    全量重写 / payload 冲突）的正式回落路径，被 `single_pass is None` 真实到达。
            single_pass = self._try_single_pass_materialize(
                bindings=bindings,
                substrate_for_write=substrate_for_write,
                projection=projection,
                output=output,
                contract=contract,
                role=role,
                kind=kind,
                state=state,
            )
            if single_pass is not None:
                return single_pass

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
                        # 🔴 ROI-2：非终趟 structure_hash 必被丢弃（下方只取
                        #    last_result.structure_hash）⇒ 跳过整簿指纹重算（每趟省 ~1.4s）。
                        compute_structure_hash=is_last,
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
                    # 先释放作用域内可能持有的 zip 句柄，再删（Windows 上顺序反了就删不掉）。
                    release_scoped_workbooks(path)
                    path.unlink(missing_ok=True)
            assert last_result is not None
            assert primary_result is not None
            from app.services.workpaper_sync.phase5_transposed_sheet import materialize_file as _transposed_materialize_file
            from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs
            specs = resolve_transposed_specs(contract)
            if specs:
                # 转置写盘后只刷新 artifact 字节摘要；structure_hash 由
                # ContentMutationService._projection_structure_hash（与观测器同构）覆盖。
                # 多张转置 sheet 逐 spec 覆盖各自的列。
                import hashlib
                for spec in specs:
                    _transposed_materialize_file(output, projection, spec=spec)
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
                release_scoped_workbooks(repaired)
                repaired.unlink(missing_ok=True)
            if g7_sanitized is not None:
                release_scoped_workbooks(g7_sanitized)
                g7_sanitized.unlink(missing_ok=True)

    def _try_single_pass_materialize(
        self,
        *,
        bindings: tuple[ExcelIdentityBinding, ...],
        substrate_for_write: Path,
        projection: Projection,
        output: Path,
        contract: SyncContract,
        role: SubstrateRole,
        kind: ArtifactKind,
        state: ArtifactState,
    ) -> "MaterializeResult | None":
        """尝试单趟物化；不适用返回 `None`（调用方回落逐趟链式路径）。

        spec: oo-single-pass-materialize-and-room-leave · Requirement 1 / 2

        产出的 `MaterializeResult` 与逐趟路径的返回**逐字段同构**：主 binding 的完整
        result + 全部 binding 的字段数累加 + 全部趟 workbook 位移声明并集。`per_table_shift`
        在单趟路径恒为 `None`（单趟在任一 binding 需插行时就已 decline）。
        """
        import dataclasses
        import hashlib

        from app.services.workpaper_sync.excel_materialize import (
            SinglePassDeclined,
            materialize_projection_single_pass,
        )
        from app.services.workpaper_sync.excel_workbook_row_change import (
            merge_workbook_row_change_propagations,
        )

        try:
            outcome = materialize_projection_single_pass(
                substrate=substrate_for_write,
                projection=projection,
                output=output,
                definitions=self.definitions,
                bindings=bindings,
                primary_table_key=self.binding.table_key,
                substrate_role=role,
                substrate_kind=kind,
                substrate_state=state,
                capability=self.capability,
                limits=self._limits,
            )
        except SinglePassDeclined as exc:
            # 🔴 仍然**不在这里** emit metrics：metrics 是注册制契约（`METRICS_BY_NAME` +
            #    归因维度 + 治理 gate），且 platform 级指标必须带 project_id/wp_id ——
            #    engine 层是纯计算、拿不到 scope，编一个 scope 就是假归因。
            #    Task 10（requirements 3.3「回落原因统计」）的做法是**登记分型**：engine 只说
            #    「发生了哪一类回落」，emit 与归因由持有 scope 的 router 完成。作用域之外
            #    `record_single_pass_decline` 是安全空操作，所以这行不会让任何既有调用路径变化。
            from app.services.workpaper_sync.materialize_reuse_verdict import (
                record_single_pass_decline,
            )

            decline_class = record_single_pass_decline(exc.reason)
            logger.info(
                "[single_pass] 回落逐趟链式（entry=%s，class=%s）：%s",
                self.adapter_id,
                decline_class.value,
                exc.reason,
            )
            return None

        logger.info(
            "[single_pass] 单趟物化命中（entry=%s，binding=%d）",
            self.adapter_id,
            len(bindings),
        )
        result = outcome.primary.result
        from app.services.workpaper_sync.phase5_transposed_sheet import (
            materialize_file as _transposed_materialize_file,
        )
        from app.services.workpaper_sync.transposed_registry import (
            resolve_transposed_specs,
        )

        specs = resolve_transposed_specs(contract)
        if specs:
            # 转置写盘后只刷新 artifact 字节摘要；structure_hash 由
            # ContentMutationService._projection_structure_hash（与观测器同构）覆盖。
            for spec in specs:
                _transposed_materialize_file(output, projection, spec=spec)
            result = dataclasses.replace(
                result,
                artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
            )

        merged_change = merge_workbook_row_change_propagations(
            list(outcome.workbook_row_changes)
        )
        return dataclasses.replace(
            result,
            managed_field_count=int(result.managed_field_count),
            output_path=output,
            workbook_row_change=merged_change,
            # 单趟在任一 binding 需插行时就 decline ⇒ 到这里必然全无插行。
            per_table_shift=None,
        )

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
        # 🔴 多 binding 底稿（D4-营业收入实测 39 个 binding）每个 binding 都要读同一个
        # artifact 的两个视图（data_only True/False）⇒ 78 次全簿 openpyxl 解析、cProfile
        # 累计 60.8s，这是 store-projection 首请求十秒量级的主项。作用域内同一
        # (文件身份, data_only) 只解析一次；退出时 finally 关闭全部句柄（Windows 上
        # staged/repaired 临时文件随后要 unlink，不能有残留句柄）。
        # 只改「解析几次」不改「解析出什么」——作用域外行为与优化前逐字节相同。
        with workbook_read_scope():
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
            from app.services.workpaper_sync.phase5_transposed_sheet import extract_file as _transposed_extract_file
            from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs
            for spec in resolve_transposed_specs(contract):
                parts.append(_transposed_extract_file(artifact, contract, spec=spec))
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
            from app.services.workpaper_sync.phase5_transposed_sheet import (
                materialize_transposed_workbook as _transposed_materialize,
                extract_transposed_workbook as _transposed_extract,
            )
            from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs
            specs = resolve_transposed_specs(contract)
            if specs:
                # 把 after 侧每张转置 sheet 的受管列重投影回 before 副本，使 verify 不把
                # 合法的转置列变化判成 unmanaged drift。多张转置 sheet 链式叠加（逐 spec 各
                # 重投影一遍，前一遍产物喂下一遍）。
                import tempfile
                handle = tempfile.NamedTemporaryFile(suffix=".transposed-before.xlsx", delete=False)
                handle.close()
                d429_before = Path(handle.name)
                projected = before.read_bytes()
                after_bytes = after.read_bytes()
                any_projected = False
                for spec in specs:
                    # `share_parse=True`：after 字节与 `extract` / `structure_hash` 读的是
                    # 同一份产物 ⇒ 全簿解析在 `workbook_read_scope()` 里共用一次（需求 2.1）。
                    # 复用的只是**解析结果**：下面的中性化、逐 binding digest 比对、
                    # `assert_equivalent` 一条都没省（需求 2.3）。
                    after_rows = _transposed_extract(after_bytes, spec=spec, share_parse=True)
                    # 🔴 空转置表跳过中性化（否则假 drift）：`materialize_transposed_workbook`
                    #    经 openpyxl `wb.save()` 重序列化目标 sheet part，即便**零实体**也会
                    #    产出字节不同的 XML。而 materialize 侧对空转置表是 no-op
                    #    （`materialize_file`：`if spec.table_key not in projection.row_keys: return`），
                    #    故 after 该 sheet 与 before 逐字节相同。若这里仍无条件重投影，就把
                    #    before 那张 sheet 无谓 openpyxl 重写成字节不同 ⇒ verify 的
                    #    `other_sheet_parts` 把「after==before 的空转置 sheet」判成 drift
                    #    （D4-12 无行时 sheet17 假漂移的真因）。空则不动 before，保持与 after 对称。
                    if not after_rows:
                        continue
                    projected = _transposed_materialize(projected, after_rows, spec=spec)
                    any_projected = True
                if any_projected:
                    d429_before.write_bytes(projected)
                    before_for_compare = d429_before
            # 同上：注册表声明取代字面量分支（Task 13 收敛）。
            _neutralize_fn_before = _resolve_oo_crash_neutralization_fn(self.adapter_id)
            if _neutralize_fn_before is not None:
                import shutil

                g7_before_sanitized = before.with_name(
                    before.name + ".g7-noif-before.xlsx"
                )
                shutil.copy2(before, g7_before_sanitized)
                _neutralize_fn_before(g7_before_sanitized)
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
            #: `table_key → sheet_part` —— 判定「哪些趟落在同一张 sheet」的唯一依据。
            #  不按 sheet_key 猜（同 sheet 双区共享一个 sheet_key，但那是契约概念；
            #  物理归组必须用 region 解析出的真实 part）。
            sheet_of_table: dict[str, str] = {
                region.table_key: region.sheet_part
                for _binding, region in regions_by_binding
            }
            # 🔴 转置 sheet（D4-29 customer_detail / D4-12 contract_inspection）是**受管
            #    sheet**，但走 carrier-row 身份机制、**没有 ExcelIdentityBinding**（不在
            #    instrumentation_specs 的受管表清单里）。若不显式登记，它们的 sheet part 不在
            #    all_managed_parts ⇒ 落进 `other_sheet_parts` 桶做**原始字节比对**。而转置
            #    materialize 用 openpyxl `wb.save()` 全量重序列化目标 sheet part，其字节依赖整簿
            #    内部状态：materialize 侧在 34-binding 链式改写后的 workbook 上跑、verify 中性化
            #    侧在原始 before 上跑 ⇒ 两侧非受管列字节（dimension/style xf 索引/属性序）不一致
            #    ⇒ 假 `adapter_unmanaged_region_drift`（D4-29 非空真栈复现；D4-12 空表同类，此前
            #    靠 `if not after_rows: continue` 空守卫绕过，非空则复发）。
            #    正解：把转置 sheet part 并入 all_managed_parts，与「有 binding 的 sheet 走各自
            #    managed_sheet_* aspect、不进 other_sheet_parts」同口径。转置 sheet 的受管内容
            #    （列）由 `extract_transposed_workbook` 往返 + fail-closed 校验（公式格拒绝 /
            #    carrier 强校验）守护；保护区（label 列 A/B / footer / static prompt）materialize
            #    不写、只被 openpyxl 重序列化碰字节，排除原始字节比对不损失篡改检测。
            if specs:
                from app.services.workpaper_sync.excel_extract import _sheet_parts

                with zipfile.ZipFile(after) as _zf_after:
                    after_sheet_parts = _sheet_parts(_zf_after)
                transposed_parts = frozenset(
                    part
                    for spec in specs
                    if (part := after_sheet_parts.get(spec.managed_sheet)) is not None
                )
                all_managed_parts = all_managed_parts | transposed_parts
            last_report: UnmanagedRegionReport | None = None
            # 同 sheet 多受管区：每个 binding 的受管坐标先算好，校验时把**同 sheet 兄弟区**
            # 的坐标并进 extra_managed_coords。否则 OO→HTML rematerialize 改写兄弟区格
            # （sharedString→inlineStr / 浮点规整）会被本 binding 当成 unmanaged drift。
            from app.services.workpaper_sync.excel_extract import _managed_coordinates

            coords_by_table: dict[str, frozenset[str]] = {
                binding.table_key: _managed_coordinates(
                    contract=self.definitions.contract,
                    region=region,
                    binding=binding,
                    scan=None,
                )
                for binding, region in regions_by_binding
            }
            for binding, region in regions_by_binding:
                extra = all_managed_parts - {region.sheet_part}
                sibling_coord_sets = [
                    coords_by_table[other.table_key]
                    for other, other_region in regions_by_binding
                    if other_region.sheet_part == region.sheet_part
                    and other.table_key != binding.table_key
                ]
                sibling_coords = (
                    frozenset().union(*sibling_coord_sets)
                    if sibling_coord_sets
                    else frozenset()
                )
                # 🔴 每张 sheet 的 shift-aware 归一化必须用**它自己那趟**的 row_shift /
                #    total_formula_rows。多 sheet 场景里主 binding 不一定是插行的 sheet
                #    （真实：D4-2 未插、D4-22/D4-23 插）——只按 "是否主 binding" 分派会把
                #    sibling 的合法插行判 managed_sheet_* drift（§4b）。
                #    per_table_shift 给了就按 region.table_key 取本表声明；没给（Word/单 sheet
                #    /旧调用方）则回退旧口径（主 binding 标量 + sibling None），纯增量。
                if per_table_shift is not None:
                    # 🔴 **同 sheet 多趟插行必须按累积位移归一化**（D4-1 主营 7 行 + 其他
                    #    2 行落在同一张 sheet）。逐趟链式路径下同一个 sheet part 会被插多次，
                    #    而单趟 `row_shift` 表达不了累积映射 ⇒ 与计划一致的插行仍被判
                    #    `adapter_unmanaged_region_drift`（实测 managed_sheet_unmanaged_cells
                    #    280 → 340）。合成 `CompositeRowShift`（链式 unshift / inserted_rows
                    #    并集 / 合计扩张逐趟精确还原），单趟时**仍传原 plan** ⇒ 单 sheet 与
                    #    Word 路径逐字节行为不变。
                    this_shift, this_total = _sheet_cumulative_shift(
                        per_table_shift,
                        sheet_of_table=sheet_of_table,
                        sheet_part=region.sheet_part,
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
                    extra_managed_coords=sibling_coords,
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
