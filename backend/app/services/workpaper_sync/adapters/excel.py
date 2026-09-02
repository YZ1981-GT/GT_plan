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
from typing import Any, Mapping

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
        """写 staged 产物。反读门由 `ContentMutationService` 紧随其后的 `extract` 完成。"""
        self._assert_same_contract(contract, where="materialize")
        return materialize_projection(
            substrate=substrate,
            projection=projection,
            output=output,
            definitions=self.definitions,
            binding=self.binding,
            substrate_role=self.substrate_role,
            substrate_kind=self.substrate_kind,
            substrate_state=self.substrate_state,
            capability=self.capability,
            limits=self._limits,
        ).result

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
        return extract_projection(
            artifact=artifact,
            definitions=self.definitions,
            binding=self.binding,
            substrate_role=role,
            artifact_kind=kind,
            artifact_state=state,
            baseline=baseline,
            baseline_formulas=baseline_formulas,
            limits=self._limits,
        ).projection

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
        self, *, before: Path, after: Path, contract: SyncContract
    ) -> UnmanagedRegionReport:
        """未管理区域比对。判据实现全部在 Task 37，本层只解析受管区域后转手。"""
        self._assert_same_contract(contract, where="verify_unmanaged_regions")
        with zipfile.ZipFile(after) as zf:
            region = resolve_managed_region(
                zf, contract=self.definitions.contract, binding=self.binding
            )
        return verify_unmanaged_regions(
            before=before,
            after=after,
            contract=self.definitions.contract,
            region=region,
            binding=self.binding,
            limits=self._limits,
        )


def build_excel_adapter(
    *,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    direction: str,
    baseline_representation: Path | None = None,
    capability: ExcelWriteCapability | None = None,
    limits: SyncLimits | None = None,
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
    )
