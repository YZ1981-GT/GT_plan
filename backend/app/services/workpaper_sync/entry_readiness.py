# -*- coding: utf-8 -*-
"""Entry 级同步 readiness：静态裁决、运行时供给、验收证据三层投影。

只读。不得创建 room、operation、artifact、candidate、evidence 或 content revision。
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperContentRepresentation,
    WorkpaperSyncTestRun,
)
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    RegistryError,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.entry_profile import (
    Capability,
    extract_entry_profile,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.entry_scoped_registration import prepare_entry_only
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.parse_cache import BoundedLruCache
from app.services.workpaper_sync.target_bound_registration import (
    bind_registration_to_target,
    target_representation_id,
)

_ALLOWED_MODES: Mapping[str | None, tuple[str, ...]] = {
    "bidirectional": ("html", "oo"),
    "single_html": ("html",),
    "single_onlyoffice": ("oo",),
    "unreachable": (),
    None: (),
}


@dataclass(frozen=True)
class ReadinessReason:
    code: str
    message: str
    next_action: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
        }


@dataclass(frozen=True)
class RuntimeReadiness:
    ready: bool
    adapter_id: str | None = None
    authority_model: str | None = None
    definition_bundle_id: str | None = None
    definition_bundle_sha256: str | None = None
    typed_slots_complete: bool = False
    typed_slots: tuple[tuple[str, str, str], ...] = ()
    representation_id: str | None = None
    representation_generation: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "adapter_id": self.adapter_id,
            "authority_model": self.authority_model,
            "definition_bundle_id": self.definition_bundle_id,
            "definition_bundle_sha256": self.definition_bundle_sha256,
            "typed_slots_complete": self.typed_slots_complete,
            "typed_slots": [
                {"slot": slot, "type": slot_type, "sha256": digest}
                for slot, slot_type, digest in self.typed_slots
            ],
            "representation_id": self.representation_id,
            "representation_generation": self.representation_generation,
        }


@dataclass(frozen=True)
class AcceptanceReadiness:
    state: str
    stale: bool
    run_id: str | None = None
    required_scenario_set_digest: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "stale": self.stale,
            "run_id": self.run_id,
            "required_scenario_set_digest": self.required_scenario_set_digest,
        }


@dataclass(frozen=True)
class EntrySyncReadiness:
    entry_id: str
    effective_entry_id: str
    capability: str | None
    adjudication_state: str
    allowed_modes: tuple[str, ...]
    can_claim_bidirectional: bool
    runtime: RuntimeReadiness
    acceptance: AcceptanceReadiness
    reason: ReadinessReason | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "effective_entry_id": self.effective_entry_id,
            "capability": self.capability,
            "adjudication_state": self.adjudication_state,
            "allowed_modes": list(self.allowed_modes),
            "can_claim_bidirectional": self.can_claim_bidirectional,
            "runtime": self.runtime.as_dict(),
            "acceptance": self.acceptance.as_dict(),
            "reason": None if self.reason is None else self.reason.as_dict(),
        }


@dataclass(frozen=True)
class RepresentationFacts:
    representation_id: uuid.UUID
    generation: int
    definition_bundle_id: uuid.UUID
    definition_bundle_sha256: str


@dataclass(frozen=True)
class AcceptanceFacts:
    run_id: uuid.UUID
    aggregate_result: str
    manifest_source_digest: str
    scenario_profile_digest: str
    definition_bundle_sha256: str
    required_scenario_set_digest: str


ReadRepresentation = Callable[..., Awaitable[RepresentationFacts | None]]
ReadAcceptance = Callable[..., Awaitable[AcceptanceFacts | None]]
BindRegistration = Callable[..., Awaitable[AdapterRegistration]]
PrepareRegistration = Callable[..., Awaitable[bool]]

_READINESS_CACHE: "BoundedLruCache[tuple[str, ...], EntrySyncReadiness]" = (
    BoundedLruCache(maxsize=512)
)
_READINESS_LOCKS: dict[tuple[str, ...], asyncio.Lock] = {}


def clear_entry_readiness_cache() -> None:
    _READINESS_CACHE.clear()
    _READINESS_LOCKS.clear()


def _reason(code: str, detail: str | None = None) -> ReadinessReason:
    messages: Mapping[str, tuple[str, str]] = {
        "ENTRY_UNADJUDICATED": (
            "该底稿尚未完成双向能力裁决。",
            "先完成 HTML 对端、契约、发布版本和验收证据核对。",
        ),
        "ENTRY_UNREACHABLE": (
            "该入口已判定为不可达旧桩。",
            "请使用已登记的替代入口；旧桩将按删除计划移除。",
        ),
        "REPRESENTATION_MISSING": (
            "当前底稿尚未发布在线编辑版本。",
            "首次进入在线编辑时会自动发布首版。",
        ),
        "ADAPTER_NOT_READY": (
            "当前底稿的双向 adapter 尚未就绪。",
            "请按提示补齐契约、definition bundle 或目标版本绑定。",
        ),
        "CONTRACT_DRIFT": (
            "同步契约声明的结构与已发布版本不一致。",
            "按「模板 → 插桩 → 契约 → bundle → representation」重新发布新 definitions，"
            "不要按旧坐标继续写格。",
        ),
        "PUBLISHED_IDENTITY_DRIFT": (
            "该版本冻结的受管结构与当前实测不一致。",
            "先对该底稿重新投影产出新版本，再进入在线编辑。",
        ),
        "FROZEN_INSTRUMENTATION_UNUSABLE": (
            "该版本冻结的插桩信息缺少反读所需的锚点。",
            "该底稿需重新插桩并发布新版本；请勿按 sheet 展示名猜锚点。",
        ),
        "ENTRY_SOURCE_FACT_UNAVAILABLE": (
            "该入口缺少可观测的挂载点事实，无法推导同步档案。",
            "先确认该入口在前端有真实挂载，再重新检查。",
        ),
        "ENTRY_SELECTION_INVALID": (
            "该入口的底稿编码匹配域与已冻结声明不一致。",
            "请修正该 entry 的 wp_code 匹配域，使其覆盖全部底稿编码。",
        ),
        "DEFINITION_BUNDLE_MISMATCH": (
            "目标版本与 adapter 冻结的 definition bundle 不是同一份。",
            "请把该底稿绑定到与 adapter 一致的 bundle，或重新发布版本。",
        ),
        "DEFINITION_SLOT_INVALID": (
            "definition bundle 的 typed slots 不完整。",
            "补齐 template / instrumentation / contract 三个 slot 后重新发布 bundle。",
        ),
        "RUNTIME_REGISTRATION_FAILED": (
            "同步定义校验失败，当前不能进入在线编辑。",
            "请修复契约或发布版本漂移后重试。",
        ),
        "EVIDENCE_MISSING": (
            "双向链路已接入，但真实验收证据尚未生成。",
            "请执行该 entry 的真实 OnlyOffice required scenarios。",
        ),
        "EVIDENCE_STALE": (
            "双向验收证据已过期。",
            "请按当前源码、bundle 和场景配置重新执行验收。",
        ),
        "EVIDENCE_FAILED": (
            "最近一次双向验收未通过。",
            "请查看该次 test run 的失败场景并修复后重跑。",
        ),
        "EVIDENCE_UNVERIFIABLE": (
            "最近一次双向验收尚不可验证。",
            "请补齐真实 OnlyOffice、浏览器或测试数据环境后重跑。",
        ),
    }
    message, next_action = messages[code]
    if detail:
        next_action = f"{next_action}（{detail}）"
    return ReadinessReason(code=code, message=message, next_action=next_action)


class EntryReadinessNotFound(SyncDomainError):
    error_code = "entry_readiness_not_found"


class DefinitionBundleMismatch(SyncDomainError):
    """目标 representation 与 adapter 冻结的 bundle 不是同一份。

    🔴 与 :class:`EntryReadinessNotFound` 分开：后者是「指针悬空 / 跨 scope」（对外 404），
    前者是「两边都在、但不是同一份 bundle」（对外 200 + 可操作原因）。原先两种情形共用
    同一个 error_code，前端只能显示同一句笼统文案（AC 1.5 要求可操作原因）。
    """

    error_code = "definition_bundle_mismatch"


#: registry / domain 的 **typed** 失败 → readiness reason code 的**显式**映射。
#:
#: 🔴 为什么必须显式：原实现只按 `not_registered` / `not_ready` 子串二分，其余全部压成
#:    `RUNTIME_REGISTRATION_FAILED`。而真库实测的失败是五类不同成因（契约结构漂移 /
#:    已发布身份漂移 / 冻结插桩不可用 / 无挂载点事实 / wp_code 匹配域不一致），压成一句
#:    「同步定义校验失败」后，用户拿不到下一步动作 —— 这正是 Task 2.4 点名禁止的
#:    「不得合并成泛化未注册」。
#:
#: 维护约束由 `test_readiness_typed_failure_alignment.py` 钉住：registry 侧已知 typed
#: error_code 全集必须被本表覆盖，新增一类而忘了映射即打红。
_RUNTIME_FAILURE_REASONS: Mapping[str, str] = {
    "sync_contract_structure_drift": "CONTRACT_DRIFT",
    "published_identity_observed_drift": "PUBLISHED_IDENTITY_DRIFT",
    "published_identity_frozen_child_unusable": "FROZEN_INSTRUMENTATION_UNUSABLE",
    "entry_source_fact_unavailable": "ENTRY_SOURCE_FACT_UNAVAILABLE",
    "sync_phase5_e1_selection_invalid": "ENTRY_SELECTION_INVALID",
    "definition_bundle_mismatch": "DEFINITION_BUNDLE_MISMATCH",
    "entry_readiness_not_found": "DEFINITION_BUNDLE_MISMATCH",
}


def runtime_failure_reason_code(error_code: str) -> str:
    """typed error_code → reason code。先查显式表，再按族前缀，最后才兜底。

    兜底保留但**不是**主路径：兜底被命中说明出现了没登记的新失败类型，守卫会打红。
    """
    mapped = _RUNTIME_FAILURE_REASONS.get(error_code)
    if mapped is not None:
        return mapped
    if "not_registered" in error_code or "not_ready" in error_code:
        return "ADAPTER_NOT_READY"
    return "RUNTIME_REGISTRATION_FAILED"


async def _read_representation(
    session: Any, *, wp_id: Any, entry_id: str
) -> RepresentationFacts | None:
    representation_id = await target_representation_id(
        session, wp_id=wp_id, entry_id=entry_id
    )
    if representation_id is None:
        return None
    row = (
        await session.execute(
            sa.select(
                WorkpaperContentRepresentation.id,
                WorkpaperContentRepresentation.generation,
                WorkpaperContentRepresentation.definition_bundle_id,
                WorkpaperContentRepresentation.definition_bundle_sha256,
            ).where(
                WorkpaperContentRepresentation.id == representation_id,
                WorkpaperContentRepresentation.wp_id == wp_id,
                WorkpaperContentRepresentation.entry_id == entry_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise EntryReadinessNotFound(
            f"entry {entry_id}: current pointer 指向不存在或跨 scope 的 representation"
        )
    return RepresentationFacts(
        representation_id=row[0],
        generation=int(row[1]),
        definition_bundle_id=row[2],
        definition_bundle_sha256=str(row[3]),
    )


async def _read_acceptance(session: Any, *, entry_id: str) -> AcceptanceFacts | None:
    row = (
        await session.execute(
            sa.select(
                WorkpaperSyncTestRun.id,
                WorkpaperSyncTestRun.aggregate_result,
                WorkpaperSyncTestRun.manifest_source_digest,
                WorkpaperSyncTestRun.scenario_profile_digest,
                WorkpaperSyncTestRun.definition_bundle_sha256,
                WorkpaperSyncTestRun.required_scenario_set_digest,
            )
            .where(WorkpaperSyncTestRun.entry_id == entry_id)
            .order_by(WorkpaperSyncTestRun.started_at.desc(), WorkpaperSyncTestRun.id.desc())
            .limit(1)
        )
    ).one_or_none()
    if row is None:
        return None
    return AcceptanceFacts(
        run_id=row[0],
        aggregate_result=str(row[1]),
        manifest_source_digest=str(row[2]),
        scenario_profile_digest=str(row[3]),
        definition_bundle_sha256=str(row[4]),
        required_scenario_set_digest=str(row[5]),
    )


def _acceptance(
    facts: AcceptanceFacts | None,
    *,
    manifest_source_digest: str,
    scenario_profile_digest: str,
    bundle_sha256: str,
) -> AcceptanceReadiness:
    if facts is None:
        return AcceptanceReadiness(state="missing", stale=False)
    stale = (
        facts.manifest_source_digest != manifest_source_digest
        or facts.scenario_profile_digest != scenario_profile_digest
        or facts.definition_bundle_sha256 != bundle_sha256
    )
    if stale:
        state = "stale"
    elif facts.aggregate_result == "passed":
        state = "verified"
    elif facts.aggregate_result == "failed":
        state = "failed"
    else:
        state = "unverifiable"
    return AcceptanceReadiness(
        state=state,
        stale=stale,
        run_id=str(facts.run_id),
        required_scenario_set_digest=facts.required_scenario_set_digest,
    )


def _acceptance_reason(value: AcceptanceReadiness) -> ReadinessReason | None:
    return {
        "missing": _reason("EVIDENCE_MISSING"),
        "stale": _reason("EVIDENCE_STALE"),
        "failed": _reason("EVIDENCE_FAILED"),
        "unverifiable": _reason("EVIDENCE_UNVERIFIABLE"),
    }.get(value.state)


def _static_readiness(entry: Mapping[str, Any]) -> EntrySyncReadiness | None:
    entry_id = str(entry["entry_id"])
    effective_entry_id = str(entry.get("effective_entry_id") or entry_id)
    capability = entry.get("capability")
    adjudication_state = str(entry.get("adjudication_state") or "pending")
    if capability is None:
        counterpart = entry.get("html_counterpart_verdict")
        allowed = ("html", "oo") if counterpart == "exists" else ("oo",)
        blockers = ", ".join(entry.get("capability_target_blocked_by") or [])
        return EntrySyncReadiness(
            entry_id=entry_id,
            effective_entry_id=effective_entry_id,
            capability=None,
            adjudication_state=adjudication_state,
            allowed_modes=allowed,
            can_claim_bidirectional=False,
            runtime=RuntimeReadiness(ready=False),
            acceptance=AcceptanceReadiness(state="not_applicable", stale=False),
            reason=_reason("ENTRY_UNADJUDICATED", blockers or None),
        )
    if capability == Capability.unreachable.value:
        return EntrySyncReadiness(
            entry_id=entry_id,
            effective_entry_id=effective_entry_id,
            capability=capability,
            adjudication_state=adjudication_state,
            allowed_modes=(),
            can_claim_bidirectional=False,
            runtime=RuntimeReadiness(ready=False),
            acceptance=AcceptanceReadiness(state="not_applicable", stale=False),
            reason=_reason("ENTRY_UNREACHABLE"),
        )
    if capability in {Capability.single_html.value, Capability.single_onlyoffice.value}:
        return EntrySyncReadiness(
            entry_id=entry_id,
            effective_entry_id=effective_entry_id,
            capability=capability,
            adjudication_state=adjudication_state,
            allowed_modes=_ALLOWED_MODES[capability],
            can_claim_bidirectional=False,
            runtime=RuntimeReadiness(ready=True),
            acceptance=AcceptanceReadiness(state="not_applicable", stale=False),
            reason=None,
        )
    return None


async def evaluate_entry_readiness(
    *,
    session: Any,
    registry: WorkpaperSyncAdapterRegistry,
    project_id: Any,
    wp_id: Any,
    entry_id: str,
    manifest: Mapping[str, Any] | None = None,
    read_representation: ReadRepresentation = _read_representation,
    read_acceptance: ReadAcceptance = _read_acceptance,
    bind_registration: BindRegistration = bind_registration_to_target,
    prepare_registration: PrepareRegistration = prepare_entry_only,
) -> EntrySyncReadiness:
    """现算一条 entry 的 readiness；所有数据库操作均只读。"""
    manifest_doc = dict(manifest or load_entry_manifest())
    by_id = manifest_entries_by_id(manifest_doc)
    entry = by_id.get(str(entry_id))
    if entry is None:
        raise EntryReadinessNotFound(f"entry {entry_id!r} 不在 current manifest")
    static = _static_readiness(entry)
    if static is not None:
        return static

    effective_entry_id = str(entry.get("effective_entry_id") or entry_id)
    effective = by_id.get(effective_entry_id)
    if effective is None:
        raise EntryReadinessNotFound(
            f"entry {entry_id!r} 的 effective entry {effective_entry_id!r} 不存在"
        )
    representation = await read_representation(
        session, wp_id=wp_id, entry_id=effective_entry_id
    )
    if representation is None:
        # 尚无首版 ≠ 不能在线编辑：首版只在「首次进入在线编辑」时由
        # `ensure_first_publication` 按需发布（spec d2-online-edit-platform-closure R7）。
        # 这里若只放行 html，入口被藏、桥也拒绝，首版永远发不出来（死锁）。
        # ⇒ runtime.ready 如实保持 False，但按 capability 放行 oo；首版准入（lane / bundle /
        #   契约复核等）仍由首版端点自己判，不满足时返回 422 中文原因。
        capability = entry.get("capability")
        return EntrySyncReadiness(
            entry_id=str(entry_id),
            effective_entry_id=effective_entry_id,
            capability=str(capability),
            adjudication_state=str(entry.get("adjudication_state")),
            allowed_modes=_ALLOWED_MODES.get(capability, ("html",)),
            can_claim_bidirectional=False,
            runtime=RuntimeReadiness(ready=False),
            acceptance=AcceptanceReadiness(state="missing", stale=False),
            reason=_reason("REPRESENTATION_MISSING"),
        )

    acceptance_facts = await read_acceptance(session, entry_id=effective_entry_id)
    profile_digest = extract_entry_profile(effective).scenario_profile.digest
    cache_key = (
        str(project_id), str(wp_id), effective_entry_id,
        str(representation.representation_id),
        str(representation.definition_bundle_id),
        str(manifest_doc.get("manifest_digest") or ""),
        "none" if acceptance_facts is None else str(acceptance_facts.run_id),
    )
    cached = _READINESS_CACHE.get(cache_key)
    if cached is not None:
        return EntrySyncReadiness(
            **{**cached.__dict__, "entry_id": str(entry_id)}
        )

    lock = _READINESS_LOCKS.setdefault(cache_key, asyncio.Lock())
    try:
        async with lock:
            cached = _READINESS_CACHE.get(cache_key)
            if cached is not None:
                return EntrySyncReadiness(
                    **{**cached.__dict__, "entry_id": str(entry_id)}
                )
            result = await _evaluate_runtime(
                session=session,
                registry=registry,
                project_id=project_id,
                wp_id=wp_id,
                requested_entry_id=str(entry_id),
                effective_entry=effective,
                representation=representation,
                acceptance_facts=acceptance_facts,
                manifest_source_digest=str(manifest_doc.get("source_digest") or ""),
                profile_digest=profile_digest,
                bind_registration=bind_registration,
                prepare_registration=prepare_registration,
            )
            _READINESS_CACHE.put(cache_key, result)
            return result
    finally:
        if not lock.locked():
            _READINESS_LOCKS.pop(cache_key, None)


async def _evaluate_runtime(
    *,
    session: Any,
    registry: WorkpaperSyncAdapterRegistry,
    project_id: Any,
    wp_id: Any,
    requested_entry_id: str,
    effective_entry: Mapping[str, Any],
    representation: RepresentationFacts,
    acceptance_facts: AcceptanceFacts | None,
    manifest_source_digest: str,
    profile_digest: str,
    bind_registration: BindRegistration,
    prepare_registration: PrepareRegistration,
) -> EntrySyncReadiness:
    effective_entry_id = str(effective_entry["entry_id"])
    acceptance = _acceptance(
        acceptance_facts,
        manifest_source_digest=manifest_source_digest,
        scenario_profile_digest=profile_digest,
        bundle_sha256=representation.definition_bundle_sha256,
    )
    try:
        await prepare_registration(
            session=session,
            registry=registry,
            entry_id=effective_entry_id,
            wp_id=wp_id,
        )
        registration = await bind_registration(
            session=session,
            registry=registry,
            entry_id=effective_entry_id,
            wp_id=wp_id,
        )
        bundle = registration.bundle
        if str(bundle.bundle_id) != str(representation.definition_bundle_id):
            raise DefinitionBundleMismatch(
                "目标 representation 与 adapter 冻结的 definition bundle 不一致"
            )
        if bundle.bundle_sha256 != representation.definition_bundle_sha256:
            raise DefinitionBundleMismatch(
                "目标 representation 与 adapter 的 definition bundle digest 不一致"
            )
    except (RegistryError, SyncDomainError) as exc:
        error_code = str(getattr(exc, "error_code", "adapter_not_ready"))
        reason_code = runtime_failure_reason_code(error_code)
        return EntrySyncReadiness(
            entry_id=requested_entry_id,
            effective_entry_id=effective_entry_id,
            capability=Capability.bidirectional.value,
            adjudication_state=str(effective_entry.get("adjudication_state")),
            allowed_modes=("html",),
            can_claim_bidirectional=False,
            runtime=RuntimeReadiness(
                ready=False,
                representation_id=str(representation.representation_id),
                representation_generation=representation.generation,
                definition_bundle_id=str(representation.definition_bundle_id),
                definition_bundle_sha256=representation.definition_bundle_sha256,
            ),
            acceptance=acceptance,
            reason=_reason(reason_code, error_code),
        )

    inventory = tuple(bundle.typed_slot_inventory)
    typed_slots_complete = (
        len(inventory) == 3
        and len({slot for slot, _slot_type, _digest in inventory}) == 3
        and all(slot_type and slot_digest for _slot, slot_type, slot_digest in inventory)
    )
    runtime = RuntimeReadiness(
        ready=typed_slots_complete,
        adapter_id=registration.adapter_id,
        authority_model=bundle.authority_model.value,
        definition_bundle_id=str(bundle.bundle_id),
        definition_bundle_sha256=bundle.bundle_sha256,
        typed_slots_complete=typed_slots_complete,
        typed_slots=inventory,
        representation_id=str(representation.representation_id),
        representation_generation=representation.generation,
    )
    if not typed_slots_complete:
        return EntrySyncReadiness(
            entry_id=requested_entry_id,
            effective_entry_id=effective_entry_id,
            capability=Capability.bidirectional.value,
            adjudication_state=str(effective_entry.get("adjudication_state")),
            allowed_modes=("html",),
            can_claim_bidirectional=False,
            runtime=runtime,
            acceptance=acceptance,
            reason=_reason("DEFINITION_SLOT_INVALID", "definition_slot_invalid"),
        )
    return EntrySyncReadiness(
        entry_id=requested_entry_id,
        effective_entry_id=effective_entry_id,
        capability=Capability.bidirectional.value,
        adjudication_state=str(effective_entry.get("adjudication_state")),
        allowed_modes=("html", "oo"),
        can_claim_bidirectional=True,
        runtime=runtime,
        acceptance=acceptance,
        reason=_acceptance_reason(acceptance),
    )


__all__ = [
    "AcceptanceFacts",
    "AcceptanceReadiness",
    "DefinitionBundleMismatch",
    "EntryReadinessNotFound",
    "runtime_failure_reason_code",
    "EntrySyncReadiness",
    "ReadinessReason",
    "RepresentationFacts",
    "RuntimeReadiness",
    "clear_entry_readiness_cache",
    "evaluate_entry_readiness",
]
