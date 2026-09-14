# -*- coding: utf-8 -*-
"""evidence freshness guard：把 AC 14.16 的**全部**失效轴闭合。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 39
Requirements: 12.10, 12.13, 14.14, 14.16
Properties: **P71**（并为 P49 提供「今天为什么必须是 UNVERIFIABLE」的机器判据）

═══ 为什么需要这个模块，而不是直接用 Task 29 的 `_stale_reasons` ═══

Task 29 的 :meth:`~app.services.workpaper_sync.evidence.EvidenceRecomputer._stale_reasons`
逐字段比对了十条轴：manifest source digest、editability、room_model、scenario profile、
required scenario set、source commit、runner、OO build、browser build、environment digest。

但 :class:`~app.services.workpaper_sync.evidence.StaleReason` 里还有两个成员
**从未被任何代码 emit**：

* `authority_model_changed`
* `definition_bundle_changed`

原因是结构性的：recomputer 只拿到 `entry_id` / `run_id` / `environment`，**没有 bundle
输入**，因此它只能把 run 行的 bundle digest 与 scenario 行的 bundle digest 互相比
（同一批写入的两个副本，必然相等），而无法与「今天 approved 的那个 bundle」比。于是
「换了 bundle 但没重跑」这条 AC 14.16 明文列出的失效轴在生产上不可达 —— 声明存在、
判据为空，正是本 spec 反复点名的第①类假绿（additive 注入即死代码）。

本模块补上第三条轴 **typed child**：AC 14.16 的原文是「immutable definition bundle id/
digest **及其 template/instrumentation/contract typed child identities**」。child 换了而
bundle digest 没跟着变，是**篡改**（bundle canonical payload 含 child digests，正常升级
一定会带动 bundle digest）；两者一起变，是正常升级。共用一个码就分不出这两件事，因此
:attr:`~app.services.workpaper_sync.evidence.StaleReason.definition_bundle_child_changed`
是独立成员。

═══ 与 Property 51 / AC 12.13 的边界 ═══

「structural pre-reconcile 可以如实报告 stale，且不得把 fresh=0 当作其前置条件」——
因此本模块只**报告**，不做任何删除资格判断。:class:`FreshnessVerdict` 明确区分
`stale_reasons`（新鲜度）与 `defects`（重算缺陷）：前者可以在 pre-reconcile 报告里如实
出现，后者才是"未验收"。真正的 pre-delete eligibility 归 Task 67/71。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
    WorkpaperSyncTestRun,
)
from app.services.workpaper_sync.definitions import bundle_canonical_digest
from app.services.workpaper_sync.evidence import (
    EvidenceDefect,
    EvidenceEnvironment,
    EvidenceError,
    EvidenceRecomputer,
    EvidenceResult,
    EvidenceVerdict,
    StaleReason,
)
from app.services.workpaper_sync.models import AuthorityModel, BundleSlot, DefinitionState
from app.services.workpaper_sync.pilot_harness import BundleIdentity

#: 本模块负责的三条轴。挂成常量是为了让守卫能与 emit 点**双向**锁死 —— 「某条 stale
#: 码是否真被某处 emit」是这个 spec 里最容易空转的判据。
BUNDLE_AXES: tuple[StaleReason, ...] = (
    StaleReason.authority_model_changed,
    StaleReason.definition_bundle_changed,
    StaleReason.definition_bundle_child_changed,
)


class BundleTamperError(EvidenceError):
    """bundle 行的 typed child 与它自己声明的 canonical digest 不自洽。

    这不是 staleness 而是**损坏**：bundle canonical payload 由 authority digest + 三个
    slot digest 唯一决定（见 :func:`definitions.build_bundle_canonical_payload`），
    因此 child 被就地改过而 `canonical_payload_sha256` 没变，只能是有人绕过发布器直接
    UPDATE。fail closed 抛出，而不是记一条 stale —— 记 stale 意味着"重跑一次就好了"。
    """

    error_code = "sync_bundle_child_inventory_tampered"


@dataclass(frozen=True)
class FreshnessVerdict:
    """一次 freshness 评估。`fresh` 由集合推导，不接受写入值。"""

    entry_id: str
    run_id: uuid.UUID | None
    recomputed: EvidenceVerdict
    bundle_stale_reasons: tuple[StaleReason, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def stale_reasons(self) -> tuple[StaleReason, ...]:
        """recomputer 的十条轴 + 本模块的三条轴，去重保序。"""
        out: list[StaleReason] = []
        for reason in tuple(self.recomputed.stale_reasons) + self.bundle_stale_reasons:
            if reason not in out:
                out.append(reason)
        return tuple(out)

    @property
    def defects(self) -> tuple[EvidenceDefect, ...]:
        return tuple(self.recomputed.defects)

    @property
    def result(self) -> EvidenceResult:
        """🔴 缺陷优先于 stale，stale 优先于 verified。

        顺序不可交换：把 stale 放在 defects 之前会让一个"既过期又有缺陷"的 run 显示成
        `stale`，读者会以为"重跑一次就好了"，而它其实结构上不成立。
        """
        if self.defects:
            return EvidenceResult.unverified
        if self.stale_reasons:
            return EvidenceResult.stale
        if self.run_id is None:
            return EvidenceResult.unverified
        return EvidenceResult.verified

    @property
    def fresh(self) -> bool:
        return not self.stale_reasons

    @property
    def verified(self) -> bool:
        return self.result is EvidenceResult.verified

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "run_id": None if self.run_id is None else str(self.run_id),
            "result": self.result.value,
            "fresh": self.fresh,
            "stale_reasons": [r.value for r in self.stale_reasons],
            "recomputed_stale_reasons": [r.value for r in self.recomputed.stale_reasons],
            "bundle_stale_reasons": [r.value for r in self.bundle_stale_reasons],
            "defects": [d.value for d in self.defects],
            "notes": list(self.recomputed.notes) + list(self.notes),
        }


def recompute_bundle_canonical_digest(identity: BundleIdentity) -> str:
    """从 typed child 现算 bundle canonical digest。

    刻意**复用**发布器的 :func:`definitions.bundle_canonical_digest` 而不是在这里拼
    payload：两份 canonicalization 就意味着"篡改检测"可以与"发布"各算各的，
    于是任一侧改了规则都不会打红。
    """
    return bundle_canonical_digest(
        authority_model=identity.authority_model,
        authority_model_definition_sha256=identity.authority_model_definition_sha256,
        slots={
            BundleSlot.template: {
                "type": identity.template_slot[0],
                "ref": identity.template_slot[1],
                "digest": identity.template_slot[2],
            },
            BundleSlot.instrumentation: {
                "type": identity.instrumentation_slot[0],
                "ref": identity.instrumentation_slot[1],
                "digest": identity.instrumentation_slot[2],
            },
            BundleSlot.contract: {
                "type": identity.contract_slot[0],
                "ref": identity.contract_slot[1],
                "digest": identity.contract_slot[2],
            },
        },
    )


def assert_bundle_child_inventory_intact(identity: BundleIdentity) -> None:
    """bundle 行声明的 digest 必须与其 typed child 现算值一致。"""
    recomputed = recompute_bundle_canonical_digest(identity)
    if recomputed != identity.bundle_sha256:
        raise BundleTamperError(
            f"bundle {identity.bundle_id} 的 canonical digest 与 typed child 现算值不符："
            f"行上 {identity.bundle_sha256}，按 authority+template/instrumentation/contract "
            f"重算 {recomputed} —— child 被就地改过而 digest 未变（绕过发布器的 UPDATE）"
        )


def bundle_stale_reasons(
    *, run: WorkpaperSyncTestRun, current: BundleIdentity, frozen_child_digest: str | None
) -> tuple[tuple[StaleReason, ...], tuple[str, ...]]:
    """AC 14.16 的 bundle / authority / typed-child 三条轴。

    :param frozen_child_digest: 该 run 当时冻结的 typed child digest。V151 的 test run 表
        只存 bundle digest 与 authority digest 两列（没有 child digest 列），因此 child
        轴的历史值由 run manifest artifact 提供；拿不到时**不静默跳过**，而是回退成
        「用当前 bundle 的 child digest 与 run 的 bundle digest 交叉验证」：只要 bundle
        digest 相等而 child digest 与之不自洽，仍然会被
        :func:`assert_bundle_child_inventory_intact` 抓住。
    """
    reasons: list[StaleReason] = []
    notes: list[str] = []
    if str(run.authority_model_definition_sha256) != current.authority_model_definition_sha256:
        reasons.append(StaleReason.authority_model_changed)
        notes.append(
            f"authority model definition digest 变了："
            f"run {run.authority_model_definition_sha256} → 现行 "
            f"{current.authority_model_definition_sha256}"
        )
    if str(run.definition_bundle_sha256) != current.bundle_sha256:
        reasons.append(StaleReason.definition_bundle_changed)
        notes.append(
            f"definition bundle digest 变了：run {run.definition_bundle_sha256} → 现行 "
            f"{current.bundle_sha256}"
        )
    if frozen_child_digest is not None and frozen_child_digest != current.typed_child_digest:
        reasons.append(StaleReason.definition_bundle_child_changed)
        notes.append(
            f"bundle typed child identities 变了：run {frozen_child_digest} → 现行 "
            f"{current.typed_child_digest}"
        )
    return tuple(reasons), tuple(notes)


class EvidenceFreshnessGuard:
    """组合 Task 29 的重算与本模块的 bundle 三轴。

    **只读**。`aggregate_result` 的写入归
    :meth:`~app.services.workpaper_sync.pilot_harness.SyncTestRunHarness.finalize_run`。
    """

    def __init__(
        self, session: AsyncSession, *, manifest: Mapping[str, Any] | None = None
    ) -> None:
        self._session = session
        self._recomputer = EvidenceRecomputer(session, manifest=manifest)

    async def load_bundle_identity(self, bundle_id: uuid.UUID) -> BundleIdentity:
        """读 bundle + authority definition 行（approved 才算数）。

        与 :meth:`SyncTestRunHarness.resolve_bundle_identity` 的区别：那边是**写入前**的
        准入（抛 :class:`HarnessRejected`），这边是**读侧**评估（抛 :class:`EvidenceError`）。
        两处都必须存在 —— 只在写入侧校验，会让一个当年 approved、如今 retired 的 bundle
        永远显示 fresh。
        """
        bundle = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionBundle).where(
                    WorkpaperSyncDefinitionBundle.id == bundle_id
                )
            )
        ).scalar_one_or_none()
        if bundle is None:
            raise EvidenceError(f"definition bundle {bundle_id} 不存在")
        if str(bundle.state) != DefinitionState.approved.value:
            raise EvidenceError(
                f"definition bundle {bundle_id} 现状 {bundle.state!r} 已非 approved —— "
                "evidence 不得继续引用它（AC 12.1）"
            )
        authority = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id == bundle.authority_model_definition_id
                )
            )
        ).scalar_one_or_none()
        if authority is None:
            raise EvidenceError(f"bundle {bundle_id} 的 authority model definition 不存在")
        try:
            model = AuthorityModel(authority.authority_model_type)
        except (ValueError, TypeError) as exc:
            raise EvidenceError(
                f"authority_model_type={authority.authority_model_type!r} 不在封闭枚举内"
            ) from exc
        return BundleIdentity(
            bundle_id=bundle.id,
            bundle_sha256=str(bundle.canonical_payload_sha256),
            authority_model=model,
            authority_model_definition_sha256=str(bundle.authority_model_definition_sha256),
            template_slot=(
                str(bundle.template_slot_type),
                str(bundle.template_slot_ref),
                str(bundle.template_slot_digest),
            ),
            instrumentation_slot=(
                str(bundle.instrumentation_slot_type),
                str(bundle.instrumentation_slot_ref),
                str(bundle.instrumentation_slot_digest),
            ),
            contract_slot=(
                str(bundle.contract_slot_type),
                str(bundle.contract_slot_ref),
                str(bundle.contract_slot_digest),
            ),
        )

    async def assess(
        self,
        *,
        entry_id: str,
        bundle_id: uuid.UUID,
        environment: EvidenceEnvironment,
        run_id: uuid.UUID | None = None,
        frozen_child_digest: str | None = None,
    ) -> FreshnessVerdict:
        """评估一个 entry 的最新（或指定）run 的新鲜度与重算结论。"""
        current = await self.load_bundle_identity(bundle_id)
        assert_bundle_child_inventory_intact(current)
        recomputed = await self._recomputer.recompute(
            entry_id=entry_id,
            authority_model=current.authority_model,
            environment=environment,
            run_id=run_id,
        )
        if recomputed.run_id is None:
            return FreshnessVerdict(
                entry_id=entry_id, run_id=None, recomputed=recomputed
            )
        run = (
            await self._session.execute(
                sa.select(WorkpaperSyncTestRun).where(
                    WorkpaperSyncTestRun.id == recomputed.run_id
                )
            )
        ).scalar_one_or_none()
        if run is None:  # pragma: no cover - recomputer 刚读到它
            raise EvidenceError(f"test run {recomputed.run_id} 在重算后消失")
        reasons, notes = bundle_stale_reasons(
            run=run, current=current, frozen_child_digest=frozen_child_digest
        )
        return FreshnessVerdict(
            entry_id=entry_id,
            run_id=run.id,
            recomputed=recomputed,
            bundle_stale_reasons=reasons,
            notes=notes,
        )


def summarize_freshness(verdicts: Sequence[FreshnessVerdict]) -> dict[str, Any]:
    """manifest evidence summary 的新鲜度部分（AC 12.13 的五类计数之一）。

    只报告计数，**不**给删除资格结论 —— 那是 Task 67（结构报告）与 Task 71
    （pre-delete eligibility）的事。
    """
    stale = [v.entry_id for v in verdicts if v.result is EvidenceResult.stale]
    unverified = [v.entry_id for v in verdicts if v.result is EvidenceResult.unverified]
    verified = [v.entry_id for v in verdicts if v.verified]
    by_reason: dict[str, list[str]] = {}
    for verdict in verdicts:
        for reason in verdict.stale_reasons:
            by_reason.setdefault(reason.value, []).append(verdict.entry_id)
    return {
        "assessed": len(verdicts),
        "verified": sorted(verified),
        "stale": sorted(stale),
        "unverified": sorted(unverified),
        "stale_by_reason": {k: sorted(v) for k, v in sorted(by_reason.items())},
    }


__all__ = [
    "BUNDLE_AXES",
    "BundleTamperError",
    "EvidenceFreshnessGuard",
    "FreshnessVerdict",
    "assert_bundle_child_inventory_intact",
    "bundle_stale_reasons",
    "recompute_bundle_canonical_digest",
    "summarize_freshness",
]
