# -*- coding: utf-8 -*-
"""生产侧 `projection_contract` definition 链的幂等 provisioning 入口（`--check` / `--apply`）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 4 Task 76
Requirements: 2.1, 2.3, 2.4, 3.3, 3.4, 3.6, 6.2, 6.10, 6.18, 12.1
Properties: **P4 / P5 / P10 / P28 / P67**

═══ 这个脚本是 `ProjectionDefinitionProvisioner` 的**唯一消费宿主** ═══

`app.services.workpaper_sync.projection_provisioning` 是纯服务层：它不开事务、不
commit、不选目标底稿。没有宿主时它就是 additive 死代码（本 spec 反复实测过的假绿第①
源），所以判「Task 76 接上了没有」的判据落在这里：

* `--check`  只读：按真实 `DELIVERED_PER_ENTRY_CONTRACTS` × 真实 `working_paper`
  现算「哪些 entry 有可 provision 的目标」「四段 canonical digest 是否已在库里
  approved」「representation 阶段会怎么结算」，一行都不写；
* `--apply`  逐 entry 各开一个事务调 `provisioner.ensure()` 并 commit；任一 entry 失败
  只回滚它自己那个事务（失败只留下不可见 orphan blob，由 Task 11 的 orphan GC 清理），
  随后整体以非零退出码报 ERROR —— **不**降级成「本项目无此数据」。

═══ 为什么 `--check` 不是「跑一遍再回滚」 ═══

回滚能保证 DB 不留行，但 `publish_definition_blob()` 已经把 blob 写进 definition
store ⇒ 每次 `--check` 都产生一批 orphan 文件。故 `--check` 用
:class:`DryRunPublisher`：**payload 是真的、digest 是真算的、库查是真查的**，只是
不 insert。它同时把 `publish_pilot_definitions()` 里那两条单向引用判据
（template/instrumentation digest 必须与契约声明相等）真跑了一遍。

═══ 目标底稿怎么选（不写第二份清单）═══

`entry → wp_code` 只有一份真源：该 entry 自己的 provider 模块的 `PILOT_WP_CODES`
（`registry._ALLOWED_PROVIDER_MODULES` 白名单内）。脚本按它 JOIN `wp_index` 查
未删除底稿，按 `(wp_code, created_at, id)` 取第一条 —— 确定性排序，重跑选同一条。
查不到目标时给**显式原因**并计入 `unresolved`，不静默跳过。

用法（Windows PowerShell，仓库根）::

    .\\.venv\\Scripts\\python.exe backend/scripts/fix/fix_task76_provision_projection_definitions.py --check
    .\\.venv\\Scripts\\python.exe backend/scripts/fix/fix_task76_provision_projection_definitions.py --apply
    .\\.venv\\Scripts\\python.exe backend/scripts/fix/fix_task76_provision_projection_definitions.py --check --json tmp_task76_check.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import (  # noqa: E402
    projection_target_resolution as _TARGET_RESOLUTION,
)

#: `--check` 的三种结算（封闭词表；自由文本会让守卫只能比字符串）。
CHECK_STAGE_STATES: tuple[str, ...] = ("reused", "would_create")

#: `--check` / `--apply` 共用的目标选取排序 —— 真源在生产模块，本宿主只**转引**。
#:
#: 🔴 BP-24（2026-09-05 实测）：这里原来是 `"wi.wp_code, wp.created_at, wp.id"`，比首版宿主
#:    少了 `has_store_payload DESC` 那一项。两份全序读同一张裁决表却选出不同底稿：D2 的首版
#:    发布落在 `ef7f88e3`（store 866,972 B），本脚本解析到 `1e171c06`（store 空）⇒ `--check`
#:    对**已发布**的 D2 报 `settlement=blocked` / `current_representation_id=null`；B60 同样
#:    分歧。若 `--apply` 照旧执行，candidate/representation 会建在另一条底稿上 ——「四表有
#:    真实行」与「首版已发布」各自成立却指向不同 wp，是假绿。理由与实证见生产模块顶部。
TARGET_ORDER_SQL: str = _TARGET_RESOLUTION.TARGET_ORDER_SQL


class ProvisionScriptError(RuntimeError):
    """脚本自身失败（禁 fail-open：让退出码非零，而不是降级成「无数据」）。"""


# ═══════════════════════════════════════════════════════════════════════════
# 1. 目标解析
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ProvisionTarget:
    entry_id: str
    contract_id: str
    provider_module: str
    wp_codes: tuple[str, ...]
    project_id: uuid.UUID | None = None
    wp_id: uuid.UUID | None = None
    wp_code: str | None = None
    #: 选中底稿的 HTML 侧 store 载荷字节数。它是 :data:`TARGET_ORDER_SQL` 的**第一决定项**，
    #: 报告里带上它，「为什么选这条」才是可复算的而不是要读者自己去猜排序。
    store_bytes: int = 0
    unresolved_reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.wp_id is not None and self.project_id is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "contract_id": self.contract_id,
            "provider_module": self.provider_module,
            "wp_codes": list(self.wp_codes),
            "project_id": None if self.project_id is None else str(self.project_id),
            "wp_id": None if self.wp_id is None else str(self.wp_id),
            "wp_code": self.wp_code,
            "store_bytes": self.store_bytes,
            "resolved": self.resolved,
            "unresolved_reason": self.unresolved_reason,
        }


#: wp_code 裁决表（真源见文件自身的 `why` / `basis_rule`）。
WP_CODE_ADJUDICATION = _TARGET_RESOLUTION.WP_CODE_ADJUDICATION


def load_wp_code_adjudication() -> dict[str, dict[str, Any]]:
    """转引生产侧的裁决表读取（BP-24：本宿主不再自留第二份实现）。"""
    try:
        return _TARGET_RESOLUTION.load_wp_code_adjudication()
    except _TARGET_RESOLUTION.ProjectionTargetResolutionError as exc:
        raise SystemExit(f"[FAIL] {exc}") from exc


async def resolve_targets(
    session: Any,
    *,
    entry_filter: str | None = None,
    project_filter: uuid.UUID | None = None,
) -> list[ProvisionTarget]:
    """按交付登记表 × 真实底稿现算 provisioning 目标（缺目标时给显式原因）。"""
    from app.services.workpaper_sync.adapters import registry as registry_module
    from app.services.workpaper_sync.projection_provisioning import load_projection_supply

    adjudication = load_wp_code_adjudication()

    targets: list[ProvisionTarget] = []
    for row in registry_module.DELIVERED_PER_ENTRY_CONTRACTS:
        entry_id = str(row.get("entry_id") or "").strip()
        if entry_filter and entry_id != entry_filter:
            continue
        supply = load_projection_supply(entry_id)
        # 🔴 宿主解析**不读** `PILOT_WP_CODES`：那是 manifest 从宿主 Vue 文件名 CamelCase 抽出来的
        #    启发式产物，实测产出 `D2A` / `G7L` / `H1F` 三个在 `wp_index` 里 0 命中的幻影码，
        #    于是四份契约全部 unresolved 且 `unresolved_reason` 说的原因（「没有承载它的业务底稿」）
        #    是错的。真源见 `backend/data/workpaper_sync_entry_wp_code_adjudication.json`
        #    （契约里冻结的 `template.relative_path` + 受管 `excel_name`，都进了 contract sha256）。
        verdict = adjudication.get(entry_id)
        wp_codes = tuple(verdict["wp_codes"]) if verdict else ()
        target = ProvisionTarget(
            entry_id=entry_id,
            contract_id=supply.contract_id,
            provider_module=supply.provider_module,
            wp_codes=wp_codes,
        )
        if verdict is None:
            # fail closed：**不回落**到启发式。回落等于把「无人裁决」伪装成「已裁决」。
            target.unresolved_reason = (
                f"entry {entry_id} 在 wp_code 裁决表里没有条目 —— 宿主解析必须走显式裁决，"
                "不得回落到 manifest 的 `wp_code_patterns` 启发式（它会产幻影码）"
            )
            targets.append(target)
            continue
        # 🔴 2026-09-04：判据从 `resolvable_today` 换成 `resolvable_for_provisioning`。
        #
        # 旧字段把两件互不相干的事混在一个布尔里：①能不能为该 entry 定位到宿主底稿
        # （provisioning 要的）②该 wp_code 能不能当 EntryMatcher 的域（RG-3 要的）。
        # G7 的 ② 为假（三个 entry 真码同为 G7 ⇒ MatcherOverlapError），于是 ① 也被一并
        # 关掉，Task 76 对 G7 完全不 provision，G7 的首版发布因此恒落
        # `blocked_missing_approved_bundle`。而裁决文件自己的 `basis.blocked_note` 明写
        # 「本条裁决只供 provisioning 定位宿主，**不得**直接当 EntryMatcher 的域」——
        # 文件既声明两种用途要分开，又用同一个开关把两者一起关掉，是自相矛盾。
        #
        # 缺键即抛（**不** `get(..., True)` 默认放行）：默认 True 会让「裁决表漏填」被
        # 静默当成「已裁决可解析」，那是 fail-open。
        if "resolvable_for_provisioning" not in verdict:
            raise ProvisionScriptError(
                f"entry {entry_id} 的裁决条目缺 `resolvable_for_provisioning` —— "
                "该键是 provisioning 的准入判据，缺键不得默认放行"
                "（旧键 `resolvable_today` 已废弃：它把宿主定位与 matcher 域两件事"
                "混在一个布尔里，见裁决文件的 superseded_verdict_note）"
            )
        if not verdict["resolvable_for_provisioning"]:
            target.unresolved_reason = (
                f"entry {entry_id} 的 wp_code 裁决为 {list(wp_codes)}，但登记为"
                f"不可用于 provisioning 定位宿主："
                f"{verdict.get('not_provisionable_reason') or '（未写明原因）'}"
            )
            targets.append(target)
            continue
        if not wp_codes:
            target.unresolved_reason = (
                f"entry {entry_id} 的裁决条目里 `wp_codes` 为空 —— 裁决表结构错误"
            )
            targets.append(target)
            continue
        # 🔴 BP-24：目标解析走生产侧单一真源（含 `has_store_payload DESC` 那一项）。
        #    `store_item_id` 从 provider 现取 —— 它决定全序的第一项，写死空串会让本脚本
        #    重新退回「选到 store 为空的那条底稿」，也就是 BP-24 本身。
        hit = await _TARGET_RESOLUTION.resolve_projection_target(
            session,
            wp_codes=wp_codes,
            store_item_id=str(getattr(supply.provider, "STORE_ITEM_ID", "") or ""),
            project_id=project_filter,
        )
        if hit is None:
            target.unresolved_reason = (
                f"库里没有 wp_code ∈ {list(wp_codes)} 的未删除底稿"
                + (f"（且限定 project={project_filter}）" if project_filter else "")
                + " —— 该 entry 在本库没有可 provision 的目标底稿；这不是 provisioner 的"
                "缺陷，而是**没有承载它的业务底稿实例**"
            )
            targets.append(target)
            continue
        target.project_id = uuid.UUID(str(hit.project_id))
        target.wp_id = uuid.UUID(str(hit.wp_id))
        target.wp_code = str(hit.wp_code)
        target.store_bytes = int(hit.store_bytes or 0)
        targets.append(target)
    return targets


# ═══════════════════════════════════════════════════════════════════════════
# 2. `--check` 的只读发布器
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _DryDefinition:
    definition_id: uuid.UUID
    sha256: str


@dataclass(frozen=True)
class _DryBundle:
    bundle_id: uuid.UUID
    canonical_sha256: str


@dataclass
class DryRunPublisher:
    """算真 digest、查真库、**不 insert** 的发布器门面（`--check` 专用）。

    与 `ReusingDefinitionPublisher` 的复用判据同尺度（canonical bytes），因此
    `--apply` 之后再跑 `--check` 必须全部落在 `reused` —— 这就是「幂等重跑 0 新增」的
    可观察判据。
    """

    session: Any
    stages: dict[str, str] = field(default_factory=dict)
    digests: dict[str, str] = field(default_factory=dict)
    ids: dict[str, uuid.UUID | None] = field(default_factory=dict)

    async def publish_definition(
        self,
        *,
        kind: Any,
        payload: Any,
        logical_id: str,
        semantic_version: str,
        blob_bytes: bytes | None = None,
        structure_hash: str | None = None,
        approved: bool = True,
    ) -> _DryDefinition:
        from app.models.workpaper_sync_models import WorkpaperSyncDefinitionArtifact
        from app.services.workpaper_sync.definitions import (
            canonical_digest,
            validate_definition_payload,
        )
        from app.services.workpaper_sync.models import DefinitionKind, DefinitionState

        k = kind if isinstance(kind, DefinitionKind) else DefinitionKind(kind)
        # payload 校验照跑：只读模式不等于免检（否则 `--check` 会对非法 payload 报绿）。
        validate_definition_payload(k, dict(payload))
        digest = canonical_digest(dict(payload))
        existing = (
            (
                await self.session.execute(
                    sa.select(WorkpaperSyncDefinitionArtifact)
                    .where(
                        WorkpaperSyncDefinitionArtifact.kind == k.value,
                        WorkpaperSyncDefinitionArtifact.sha256 == digest,
                        WorkpaperSyncDefinitionArtifact.state
                        == DefinitionState.approved.value,
                    )
                    .order_by(
                        WorkpaperSyncDefinitionArtifact.created_at,
                        WorkpaperSyncDefinitionArtifact.id,
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        self.stages[k.value] = "reused" if existing is not None else "would_create"
        self.digests[k.value] = digest
        self.ids[k.value] = None if existing is None else existing.id
        # id 只在「已存在」时是真的；不存在时用 digest 派生的稳定占位 id（只用于把
        # slot ref 组装出来，绝不落库 —— 落库路径在 `--apply`，那里是真 id）。
        return _DryDefinition(
            definition_id=(
                existing.id
                if existing is not None
                else uuid.uuid5(uuid.NAMESPACE_URL, f"task76-dry/{k.value}/{digest}")
            ),
            sha256=digest,
        )

    async def publish_bundle(
        self,
        *,
        authority_model_definition_id: uuid.UUID,
        authority_model: Any,
        authority_model_definition_sha256: str,
        slots: Any,
        approved: bool = True,
    ) -> _DryBundle:
        from app.models.workpaper_sync_models import WorkpaperSyncDefinitionBundle
        from app.services.workpaper_sync.definitions import bundle_canonical_digest
        from app.services.workpaper_sync.models import DefinitionState

        # bundle canonical payload 只含 type + sha256（无 uuid），故 digest 在 child 还
        # 没落库时也可复现 —— 这条是 `--check` 能给出真 bundle digest 的前提。
        digest = bundle_canonical_digest(
            authority_model=authority_model,
            authority_model_definition_sha256=authority_model_definition_sha256,
            slots=slots,
        )
        existing = (
            (
                await self.session.execute(
                    sa.select(WorkpaperSyncDefinitionBundle)
                    .where(
                        WorkpaperSyncDefinitionBundle.canonical_payload_sha256 == digest,
                        WorkpaperSyncDefinitionBundle.state == DefinitionState.approved.value,
                    )
                    .order_by(
                        WorkpaperSyncDefinitionBundle.created_at,
                        WorkpaperSyncDefinitionBundle.id,
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        self.stages["bundle"] = "reused" if existing is not None else "would_create"
        self.digests["bundle"] = digest
        self.ids["bundle"] = None if existing is None else existing.id
        return _DryBundle(
            bundle_id=(
                existing.id
                if existing is not None
                else uuid.uuid5(uuid.NAMESPACE_URL, f"task76-dry/bundle/{digest}")
            ),
            canonical_sha256=digest,
        )

    # `publish_pilot_definitions` 不用这两个，但发布器门面语义要求可用。
    def mark_stage_approved(self, stage: Any) -> None:  # pragma: no cover - 只读模式无 DAG 台账
        return None

    @property
    def would_create(self) -> tuple[str, ...]:
        return tuple(s for s, v in sorted(self.stages.items()) if v == "would_create")

    @property
    def reused(self) -> tuple[str, ...]:
        return tuple(s for s, v in sorted(self.stages.items()) if v == "reused")


async def preview_representation_settlement(
    session: Any, *, wp_id: uuid.UUID, entry_id: str, bundle_id: uuid.UUID | None
) -> dict[str, Any]:
    """只读预判 representation 阶段结算（与 provisioner 的分支**同序且同数量**）。

    🔴 2026-09-05 修：本函数曾**漏掉** `_settle_representation_stage` 的第二条分支
    （`_candidate_bound_to` → `reused_candidate`），于是「已 attach 完、candidate 处于
    `ready` 且已绑本次 bundle」这个状态被预判成 `blocked`，而 `--apply` 实跑会给
    `reused_candidate`。H1 实测复现：attach 成功后 `--check` 仍报
    `settlement=blocked` —— 预演与真跑对同一库状态给出不同结论，正是「预演选 A 真发选
    B 而报告读起来完全正常」那类缺陷。分支必须与生产那份逐条对应。
    """
    from app.models.workpaper_sync_models import (
        WorkpaperContentRepresentation,
        WorkpaperRepresentationUpgradeCandidate,
        WorkpaperSyncEntryState,
    )
    from app.services.workpaper_sync.models import CandidateState

    pointer = (
        (
            await session.execute(
                sa.select(WorkpaperSyncEntryState.current_representation_id).where(
                    WorkpaperSyncEntryState.wp_id == wp_id,
                    WorkpaperSyncEntryState.entry_id == entry_id,
                )
            )
        )
        .scalars()
        .first()
    )
    current_bundle = None
    if pointer is not None:
        current_bundle = (
            (
                await session.execute(
                    sa.select(WorkpaperContentRepresentation.definition_bundle_id).where(
                        WorkpaperContentRepresentation.id == pointer
                    )
                )
            )
            .scalars()
            .first()
        )
    pending = (
        (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(WorkpaperRepresentationUpgradeCandidate)
                .where(
                    WorkpaperRepresentationUpgradeCandidate.wp_id == wp_id,
                    WorkpaperRepresentationUpgradeCandidate.entry_id == entry_id,
                    WorkpaperRepresentationUpgradeCandidate.state
                    == CandidateState.awaiting_contract.value,
                )
            )
        ).scalar_one()
    )
    # 与生产第二条分支同源：已绑本次 bundle 且**未 finalize** 的 candidate。
    # 判据取 `target_definition_bundle_id == bundle_id`（而不是 `state == 'ready'`）——
    # 生产那边就是这么找的，用状态当代理会把「ready 但绑的是别的 bundle」误判成复用。
    bound_candidate: Any = None
    if bundle_id is not None:
        bound_candidate = (
            (
                await session.execute(
                    sa.select(
                        WorkpaperRepresentationUpgradeCandidate.id,
                        WorkpaperRepresentationUpgradeCandidate.state,
                    ).where(
                        WorkpaperRepresentationUpgradeCandidate.wp_id == wp_id,
                        WorkpaperRepresentationUpgradeCandidate.entry_id == entry_id,
                        WorkpaperRepresentationUpgradeCandidate.target_definition_bundle_id
                        == bundle_id,
                        WorkpaperRepresentationUpgradeCandidate.finalized_representation_id
                        .is_(None),
                    )
                )
            )
            .first()
        )
    if bundle_id is not None and current_bundle is not None and current_bundle == bundle_id:
        settlement = "reused_current"
    elif bound_candidate is not None:
        settlement = "reused_candidate"
    elif int(pending or 0) > 0:
        settlement = "attached_candidate"
    else:
        settlement = "blocked"
    return {
        "settlement": settlement,
        "current_representation_id": None if pointer is None else str(pointer),
        "current_definition_bundle_id": None if current_bundle is None else str(current_bundle),
        "candidates_awaiting_contract": int(pending or 0),
        "candidate_bound_to_target_bundle": (
            None if bound_candidate is None else str(bound_candidate[0])
        ),
        "candidate_bound_state": (
            None if bound_candidate is None else str(bound_candidate[1])
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. 两种运行模式
# ═══════════════════════════════════════════════════════════════════════════


async def run_check(session: Any, targets: list[ProvisionTarget]) -> dict[str, Any]:
    from app.services.workpaper_sync.projection_provisioning import (
        count_supply_rows,
        load_projection_supply,
    )

    report: dict[str, Any] = {
        "mode": "check",
        "supply_rows": await count_supply_rows(session),
        "entries": [],
        "errors": [],
    }
    for target in targets:
        item: dict[str, Any] = {"target": target.as_dict()}
        if not target.resolved:
            item["status"] = "unresolved"
            report["entries"].append(item)
            continue
        supply = load_projection_supply(target.entry_id)
        publisher = DryRunPublisher(session=session)
        try:
            definitions = await supply.provider.publish_pilot_definitions(publisher)
        except Exception as exc:  # noqa: BLE001 - 记 ERROR 态并在收尾抛出（禁 fail-open）
            item["status"] = "error"
            item["error"] = f"{type(exc).__name__}: {exc}"
            report["entries"].append(item)
            report["errors"].append({"entry_id": target.entry_id, "error": item["error"]})
            continue
        item["status"] = "ok"
        item["stages"] = dict(sorted(publisher.stages.items()))
        item["digests"] = dict(sorted(publisher.digests.items()))
        item["would_create"] = list(publisher.would_create)
        item["reused"] = list(publisher.reused)
        item["representation"] = await preview_representation_settlement(
            session,
            wp_id=target.wp_id,  # type: ignore[arg-type]
            entry_id=target.entry_id,
            bundle_id=publisher.ids.get("bundle"),
        )
        item["definition_bundle_sha256"] = definitions.bundle_sha256
        report["entries"].append(item)
    report["would_create_total"] = sum(
        len(e.get("would_create") or ()) for e in report["entries"]
    )
    return report


async def run_apply(session_factory: Any, targets: list[ProvisionTarget]) -> dict[str, Any]:
    from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.projection_provisioning import (
        ProjectionDefinitionProvisioner,
        count_supply_rows,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
    report: dict[str, Any] = {"mode": "apply", "entries": [], "errors": []}
    async with session_factory() as probe:
        report["supply_rows_before"] = await count_supply_rows(probe)
    for target in targets:
        item: dict[str, Any] = {"target": target.as_dict()}
        if not target.resolved:
            item["status"] = "unresolved"
            report["entries"].append(item)
            continue
        # 一 entry 一事务：失败只回滚它自己（其余 entry 的已提交结果不受影响）。
        async with session_factory() as session:
            provisioner = ProjectionDefinitionProvisioner(
                session=session,
                repository=WorkpaperSyncRepository(session),
                artifacts=artifacts,
                project_id=target.project_id,  # type: ignore[arg-type]
                wp_id=target.wp_id,  # type: ignore[arg-type]
            )
            try:
                outcome = await provisioner.ensure(entry_id=target.entry_id)
                await session.commit()
            except Exception as exc:  # noqa: BLE001 - 记 ERROR 态并在收尾抛出（禁 fail-open）
                await session.rollback()
                item["status"] = "error"
                item["error"] = f"{type(exc).__name__}: {exc}"
                report["entries"].append(item)
                report["errors"].append({"entry_id": target.entry_id, "error": item["error"]})
                continue
        item["status"] = "ok"
        item["outcome"] = outcome.as_dict()
        report["entries"].append(item)
    async with session_factory() as probe:
        report["supply_rows_after"] = await count_supply_rows(probe)
    report["created_total"] = sum(
        len((e.get("outcome") or {}).get("created_stages") or ())
        for e in report["entries"]
    )
    return report


# ═══════════════════════════════════════════════════════════════════════════
# 4. CLI
# ═══════════════════════════════════════════════════════════════════════════


async def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只读预演（默认）")
    mode.add_argument("--apply", action="store_true", help="真发布 approved definition 链")
    parser.add_argument("--entry", default=None, help="只处理这一个 entry_id")
    parser.add_argument("--project-id", default=None, help="限定 project")
    parser.add_argument("--json", dest="json_path", default=None, help="报告落盘路径")
    args = parser.parse_args(argv)

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise ProvisionScriptError(
            "本脚本写 V151/V153 的真实表（含 CHECK/trigger），必须真实 PostgreSQL；"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}"
        )
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    project_filter = uuid.UUID(args.project_id) if args.project_id else None
    try:
        async with Session() as session:
            targets = await resolve_targets(
                session, entry_filter=args.entry, project_filter=project_filter
            )
        if args.apply:
            report = await run_apply(Session, targets)
        else:
            async with Session() as session:
                report = await run_check(session, targets)
    finally:
        await engine.dispose()

    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.json_path:
        Path(args.json_path).write_text(text, encoding="utf-8")
    print(text)
    if report["errors"]:
        raise ProvisionScriptError(
            f"{len(report['errors'])} 个 entry 失败（详见报告 errors）—— 不降级为成功"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
