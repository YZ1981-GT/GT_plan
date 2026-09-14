# -*- coding: utf-8 -*-
"""Excel **rematerializer** —— 三条入口门 + Task 37 反读门（Task 38 的编排侧）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 38
Requirements: 3.4, 3.5, 6.6, 6.9, 6.11, 6.15, 6.16, 6.17, 6.18, 8.10, 8.11, 8.12
Properties: **P9** / **P22** / **P23** / **P24** / **P29** / **P65** / **P66** / **P67**

═══ 一、三条入口，substrate 角色**写死**在入口里 ═══

design §Materialize 第 1 条把 substrate 来源按方向分得很死，本模块因此提供三个入口而不是
一个带 `role` 参数的函数 —— 参数化会让「OO→HTML 用了 published representation 当底」这种
最贵的错误在类型上合法：

===========================  ==========================  ============================
入口                          substrate                   输出
===========================  ==========================  ============================
:func:`materialize_for_editing`   current published representation   staged result（HTML→OO）
:func:`rematerialize_merged_projection`  application 固定的 `kind=incoming,state=durable`   staged result（OO→HTML）
:func:`plan_representation_upgrade`      current published representation   **non-current candidate**
===========================  ==========================  ============================

quarantined incoming 在**engine 入口**就被拒（AC 8.10：只允许 authorization-first
download-only / expire / retention，本协议不提供解除隔离），upgrade candidate 同样 ——
两者由 Task 13 的 `assert_substrate_usable` 各抛自己的类型，本模块不把它们归一。

═══ 二、保存后**必须**过 Task 37 的唯一 commit 前置门 ═══

`ContentMutationService` 只接受过了 :meth:`RematerializeOutcome.assert_ready_for_commit`
的产物。那个方法转手调 Task 37 的
:meth:`~app.services.workpaper_sync.excel_extract.ExcelVerificationBundle.assert_publishable`
—— 三条判据（反读等值 / 公式区域 / 未管理区域）各抛自己的异常类型，本模块**不**在这一侧
再包一层统一异常：包了就等于把「哪条判据在起作用」重新弄成不可分辨。

═══ 三、Property 24 在生产上的可见性缺口，用「派生」而不是「持久化」补 ═══

Task 37 登记的缺口是：`formula_inventory` 若不落地，下一次 extract 拿不到
`baseline_formulas`，于是「把 `=G7-D7` 改写成 `=G7-D7+1`（缓存值不变）」这一类篡改在生产上
完全不可见。

本模块不给它加一列/一张表，而是**从 application 冻结的 base representation 现算**：

* base representation 是审计师**打开时**的那份字节，它的受管格公式就是「本来应该是什么」
  的权威；
* 它不可变（immutable representation generation），所以同一 operation 无论 retry 多少次都得
  到同一份 baseline —— 比落一列再读回来少一个可漂移的中间态；
* 不需要迁移、不需要新 artifact kind、更不需要往 `_GT_SYNC` 里塞一张公式表
  （AC 6.14 枚举的 runtime binding 内容里没有它，塞进去是越界）。

于是 :func:`rematerialize_merged_projection` 把 `base_representation` 做成**必填**参数，
并在入口对 incoming 跑一次带 baseline 的 extract，再用 Task 37 的
`assert_protected_tamper_fully_reported` 要求「发现的每一处受保护格篡改都已在调用方的
conflict set 里」。少了这一条，merge 漏报 protected 冲突时 rematerialize 会照常发布。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.services.workpaper_sync.adapters.base import (
    Projection,
    SubstrateRole,
)
from app.services.workpaper_sync.conflicts import ConflictRecord
from app.services.workpaper_sync.excel_entry_gate import FrozenEntryDefinitions
from app.services.workpaper_sync.excel_extract import (
    ExcelExtractOutcome,
    ExcelIdentityBinding,
    ExcelVerificationBundle,
    ProtectedCellFinding,
    assert_protected_tamper_fully_reported,
    extract_projection,
    protected_conflicts_for_findings,
    verify_before_commit,
)
from app.services.workpaper_sync.excel_materialize import (
    ExcelMaterializeOutcome,
    ExcelWriteCapability,
    materialize_projection,
)
from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState, SyncDomainError

__all__ = [
    "ExcelRematerializeError",
    "RepresentationUpgradeNotCommittableError",
    "BusinessProjectionChangedError",
    "CandidateNamespaceRequiredError",
    "ExcelRematerializeMode",
    "RematerializeOutcome",
    "RepresentationUpgradeOutcome",
    "CANDIDATE_NAMESPACE",
    "derive_baseline_from_representation",
    "protected_conflicts_from_incoming",
    "materialize_for_editing",
    "rematerialize_merged_projection",
    "plan_representation_upgrade",
]


#: candidate 专用命名空间（`ArtifactStorageLayout.candidate_dir` 的目录名）。
CANDIDATE_NAMESPACE: str = ".upgrade-candidates"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常
# ═══════════════════════════════════════════════════════════════════════════


class ExcelRematerializeError(SyncDomainError):
    error_code = "excel_rematerialize_failed"


class RepresentationUpgradeNotCommittableError(ExcelRematerializeError):
    """把 representation upgrade 的产物当业务 commit 交出去（Property 67）。

    纯表示升级不产生业务内容变化 ⇒ 不得递增 content revision，只能走
    `RepresentationService.finalize_candidate`。它与「反读没通过」是两件完全不同的事，
    所以有自己的类型：合并后「误把 candidate 当业务 commit」这条分支不可分辨。
    """

    error_code = "excel_rematerialize_upgrade_not_committable"


class BusinessProjectionChangedError(ExcelRematerializeError):
    """声称是「纯表示升级」，但业务 projection 变了（Property 67 / AC 6.18）。"""

    error_code = "excel_rematerialize_business_projection_changed"


class CandidateNamespaceRequiredError(ExcelRematerializeError):
    """upgrade candidate 的产物没有写进 candidate 命名空间。"""

    error_code = "excel_rematerialize_candidate_namespace_required"


class ExcelRematerializeMode(str, Enum):
    """三条入口各自的模式标签（进 operation error detail 与 evidence）。"""

    html_to_oo = "html_to_oo"
    oo_to_html = "oo_to_html"
    representation_upgrade = "representation_upgrade"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 结果类型
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RematerializeOutcome:
    """一次 materialize/rematerialize 的完整结论。**不含**任何发布面。"""

    mode: ExcelRematerializeMode
    materialize: ExcelMaterializeOutcome
    verification: ExcelVerificationBundle
    #: OO→HTML 才有：带 base baseline 的 incoming 反读（受保护格篡改分类的来源）。
    incoming_view: ExcelExtractOutcome | None = None

    @property
    def staged_path(self) -> Path:
        return self.materialize.output_path

    @property
    def publishable(self) -> bool:
        return self.verification.passed

    @property
    def protected_findings(self) -> tuple[ProtectedCellFinding, ...]:
        return (
            () if self.incoming_view is None else tuple(self.incoming_view.protected_findings)
        )

    def assert_ready_for_commit(self) -> None:
        """交 `ContentMutationService` 之前的唯一门（AC 8.11）。

        直接转手 Task 37 的 `assert_publishable` —— 三条判据各抛自己的类型。本方法**不**
        try/except：包一层统一异常会让「反读不等值 / 公式被改 / 未管理区域异动」在守卫里
        重新变得不可分辨（本 spec 已三次踩到这个形态）。

        `representation_upgrade` 模式在这里就被拒：它不是业务 commit。
        """
        if self.mode is ExcelRematerializeMode.representation_upgrade:
            raise RepresentationUpgradeNotCommittableError(
                "representation upgrade 的产物不得交 ContentMutationService —— 纯表示升级"
                "不改业务 projection，必须经 non-current candidate + approved bundle 由 "
                "`RepresentationService.finalize_candidate` 为**同一** content version "
                "finalize 新 generation，content revision 保持不变（AC 6.18 / Property 67）"
            )
        self.verification.assert_publishable()

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "publishable": self.publishable,
            "staged_path": str(self.staged_path),
            "materialize": self.materialize.as_dict(),
            "verification": self.verification.as_dict(),
            "incoming_protected_findings": [
                {
                    "stable_field_key": f.stable_field_key,
                    "kind": f.kind.value,
                    "oo_location": f.oo_location,
                }
                for f in self.protected_findings
            ],
        }


@dataclass(frozen=True)
class RepresentationUpgradeOutcome:
    """纯表示升级的结论。**没有** revision 面 —— 它按定义不推进 revision。"""

    rematerialize: RematerializeOutcome
    candidate_path: Path
    business_projection_unchanged: bool
    before_projection_digest: str
    after_projection_digest: str

    #: 本模块对 revision 的承诺：恒为 0。写成字段而不是注释，守卫才能直接断言。
    revision_delta: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_path": str(self.candidate_path),
            "business_projection_unchanged": self.business_projection_unchanged,
            "before_projection_digest": self.before_projection_digest,
            "after_projection_digest": self.after_projection_digest,
            "revision_delta": self.revision_delta,
            "rematerialize": self.rematerialize.as_dict(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3. baseline 派生（Property 24 的生产可见性）
# ═══════════════════════════════════════════════════════════════════════════


def derive_baseline_from_representation(
    *,
    representation: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    limits: SyncLimits | None = None,
) -> tuple[Projection, Mapping[str, str]]:
    """从**已 published** representation 现算 `(baseline projection, baseline formulas)`。

    这是 Task 37 登记的 `formula_inventory` 闭环在本任务的落法（见模块 docstring 第三节）：
    baseline 不落库、不写 `_GT_SYNC`，而是从不可变的 representation 字节现算，因此
    「baseline 与它描述的那份字节不一致」在结构上不可能发生。
    """
    outcome = extract_projection(
        artifact=representation,
        definitions=definitions,
        binding=binding,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
        limits=limits or load_limits(),
    )
    return outcome.projection, dict(outcome.formula_inventory)


def protected_conflicts_from_incoming(
    *,
    incoming_view: ExcelExtractOutcome,
    definitions: FrozenEntryDefinitions,
    base: Projection,
    current: Projection,
    incoming: Projection,
    existing: Sequence[ConflictRecord] = (),
) -> tuple[ConflictRecord, ...]:
    """把 incoming 侧的受保护格篡改补成 `protected` 冲突（Property 24）。

    只是 Task 37 `protected_conflicts_for_findings` 的定向包装 —— 不在这里重写补齐规则，
    重写会让两侧口径分叉。
    """
    return protected_conflicts_for_findings(
        findings=incoming_view.protected_findings,
        contract=definitions.contract,
        base=base,
        current=current,
        incoming=incoming,
        existing=existing,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 三条入口
# ═══════════════════════════════════════════════════════════════════════════


def _materialize_and_verify(
    *,
    mode: ExcelRematerializeMode,
    substrate: Path,
    substrate_kind: ArtifactKind,
    substrate_state: ArtifactState,
    substrate_role: SubstrateRole,
    projection: Projection,
    output: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    capability: ExcelWriteCapability | None,
    limits: SyncLimits,
    incoming_view: ExcelExtractOutcome | None = None,
    intended_formulas: Mapping[str, str] | None = None,
) -> RematerializeOutcome:
    """写 staged result，然后**无条件**过 Task 37 的反读门。

    「无条件」是判据的一部分：把 verifier 做成可选参数或 try/except 包起来，就等于允许
    调用方在真实数据上关掉它（本 spec 里 verifier 被整体关掉的形态出现过三次）。
    """
    materialized = materialize_projection(
        substrate=substrate,
        projection=projection,
        output=output,
        definitions=definitions,
        binding=binding,
        substrate_role=substrate_role,
        substrate_kind=substrate_kind,
        substrate_state=substrate_state,
        capability=capability,
        intended_formulas=intended_formulas,
        limits=limits,
    )
    verification = verify_before_commit(
        expected=projection,
        staged_result=materialized.output_path,
        substrate=substrate,
        definitions=definitions,
        binding=binding,
        substrate_role=substrate_role,
        substrate_kind=substrate_kind,
        substrate_state=substrate_state,
        baseline_formulas=materialized.intended_formulas,
        limits=limits,
    )
    return RematerializeOutcome(
        mode=mode,
        materialize=materialized,
        verification=verification,
        incoming_view=incoming_view,
    )


def materialize_for_editing(
    *,
    current_representation: Path,
    projection: Projection,
    output: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    capability: ExcelWriteCapability | None = None,
    limits: SyncLimits | None = None,
) -> RematerializeOutcome:
    """HTML→OO：以**当前 published representation** 为底写 staged result。

    design §Materialize 第 1 条：「HTML→OO 读取当前 published entry representation」。
    substrate 角色/kind/state 三项写死成 `published_representation / canonical / published`
    —— 传 incoming 或 candidate 进来会在 Task 13 的准入门被各自的类型拒掉。
    """
    return _materialize_and_verify(
        mode=ExcelRematerializeMode.html_to_oo,
        substrate=current_representation,
        substrate_kind=ArtifactKind.canonical,
        substrate_state=ArtifactState.published,
        substrate_role=SubstrateRole.published_representation,
        projection=projection,
        output=output,
        definitions=definitions,
        binding=binding,
        capability=capability,
        limits=limits or load_limits(),
    )


def rematerialize_merged_projection(
    *,
    merged: Projection,
    incoming_substrate: Path,
    base_representation: Path,
    output: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    merge_conflicts: Sequence[ConflictRecord] = (),
    incoming_state: ArtifactState = ArtifactState.durable,
    capability: ExcelWriteCapability | None = None,
    limits: SyncLimits | None = None,
) -> RematerializeOutcome:
    """OO→HTML：只以 application 固定的 `kind=incoming,state=durable` artifact 为只读底。

    执行顺序即判据（不可交换）：

    1. **incoming 侧带 baseline 的 extract** —— baseline 从 application 冻结的 base
       representation 现算（模块 docstring 第三节）。`incoming_state` 由调用方给，于是
       quarantined / 未 durable 两种形态各自被 Task 13 的专属类型在 engine 入口拒掉；
    2. **受保护格篡改的跨层闭合**（Property 24）—— 每一处 finding 都必须在调用方交来的
       conflict set 里；漏报即抛，不得静默发布；
    3. 写 staged result 并过 Task 37 反读门（未管理区域与 **incoming** 比对，AC 8.10）。

    1 在 3 之前：篡改漏报时一个字节都不该写。
    """
    lim = limits or load_limits()
    baseline_projection, baseline_formulas = derive_baseline_from_representation(
        representation=base_representation,
        definitions=definitions,
        binding=binding,
        limits=lim,
    )
    incoming_view = extract_projection(
        artifact=incoming_substrate,
        definitions=definitions,
        binding=binding,
        substrate_role=SubstrateRole.incoming,
        artifact_kind=ArtifactKind.incoming,
        artifact_state=incoming_state,
        baseline=baseline_projection,
        baseline_formulas=baseline_formulas,
        limits=lim,
    )
    assert_protected_tamper_fully_reported(
        findings=incoming_view.protected_findings, conflicts=merge_conflicts
    )
    return _materialize_and_verify(
        mode=ExcelRematerializeMode.oo_to_html,
        substrate=incoming_substrate,
        substrate_kind=ArtifactKind.incoming,
        substrate_state=incoming_state,
        substrate_role=SubstrateRole.incoming,
        projection=merged,
        output=output,
        definitions=definitions,
        binding=binding,
        capability=capability,
        limits=lim,
        incoming_view=incoming_view,
        # 🔴 受保护格 `<f>` 的应有文本取 **base representation**，不是 incoming：incoming 上的
        #    公式可能已被 OO 改写（缓存值不变），拿它当 intended 就是「篡改比篡改」⇒
        #    `verify_formula_regions` 恒通过、被改写的公式逐字进 staged result（AC 6.6 失守）。
        #    本任务首轮实测踩到过这个形态，守卫
        #    `test_reported_tamper_proceeds_and_keeps_the_template_formula` 正面钉住它。
        intended_formulas=baseline_formulas,
    )


def plan_representation_upgrade(
    *,
    current_representation: Path,
    candidate_output: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    capability: ExcelWriteCapability | None = None,
    limits: SyncLimits | None = None,
) -> RepresentationUpgradeOutcome:
    """纯表示升级：产出 **non-current candidate**，业务 projection 必须逐字节不变。

    与前两条入口的三点不同，每一点都是 Property 67 的判据：

    1. **要写的 projection 不是调用方给的** —— 它就是当前 representation 反读出来的那一份。
       接受外部 projection 会让「趁升级顺手改业务值」成为可能，而那正是「纯 hidden upgrade
       递增 content revision / 改写旧行」要防的东西；
    2. **输出必须落 candidate 命名空间**（:data:`CANDIDATE_NAMESPACE`）—— candidate 永不
       可被 resolver / room / download / current pointer / evidence 使用（AC 6.18）；
    3. **结论不可交 commit** —— :meth:`RematerializeOutcome.assert_ready_for_commit` 对本
       模式恒抛，发布只能走 `RepresentationService.finalize_candidate`（revision 不变）。
    """
    lim = limits or load_limits()
    if CANDIDATE_NAMESPACE not in candidate_output.resolve().parts:
        raise CandidateNamespaceRequiredError(
            f"representation upgrade 的输出 {candidate_output} 不在 candidate 命名空间 "
            f"{CANDIDATE_NAMESPACE!r} 下 —— candidate 必须与 `.versions` 物理隔离，"
            "否则一个手滑的 relative_path 就能让它被 resolver 当 current 读到"
            "（AC 6.18 / Property 67）"
        )
    before, _ = derive_baseline_from_representation(
        representation=current_representation,
        definitions=definitions,
        binding=binding,
        limits=lim,
    )
    outcome = _materialize_and_verify(
        mode=ExcelRematerializeMode.representation_upgrade,
        substrate=current_representation,
        substrate_kind=ArtifactKind.canonical,
        substrate_state=ArtifactState.published,
        substrate_role=SubstrateRole.published_representation,
        projection=before,
        output=candidate_output,
        definitions=definitions,
        binding=binding,
        capability=capability,
        limits=lim,
    )
    after = outcome.verification.extracted.projection
    before_digest = _projection_digest(before)
    after_digest = _projection_digest(after)
    if before_digest != after_digest:
        raise BusinessProjectionChangedError(
            f"纯表示升级后业务 projection 变了（{before_digest[:12]}… → {after_digest[:12]}…）"
            " —— 只要业务 projection 变化，它就不是表示升级而是业务 commit，"
            "必须走 `ContentMutationService` 并递增 revision（AC 6.18 / Property 67）"
        )
    return RepresentationUpgradeOutcome(
        rematerialize=outcome,
        candidate_path=outcome.staged_path,
        business_projection_unchanged=True,
        before_projection_digest=before_digest,
        after_projection_digest=after_digest,
    )


def _projection_digest(projection: Projection) -> str:
    """业务 projection 的 canonical digest。

    复用 Task 15 的 `projection_canonical_digest` —— 「业务 projection 有没有变」这条判据
    必须与 commit 侧同一口径，各写一套就会出现「升级侧说没变、commit 侧说变了」。
    """
    from app.services.workpaper_sync.content_mutation import projection_canonical_digest

    return projection_canonical_digest(projection)
