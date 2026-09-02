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

#: `--check` 的三种结算（封闭词表；自由文本会让守卫只能比字符串）。
CHECK_STAGE_STATES: tuple[str, ...] = ("reused", "would_create")

#: `--check` / `--apply` 共用的目标选取排序（确定性：重跑必选同一条底稿）。
TARGET_ORDER_SQL: str = "wi.wp_code, wp.created_at, wp.id"


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
            "resolved": self.resolved,
            "unresolved_reason": self.unresolved_reason,
        }


async def resolve_targets(
    session: Any,
    *,
    entry_filter: str | None = None,
    project_filter: uuid.UUID | None = None,
) -> list[ProvisionTarget]:
    """按交付登记表 × 真实底稿现算 provisioning 目标（缺目标时给显式原因）。"""
    from app.services.workpaper_sync.adapters import registry as registry_module
    from app.services.workpaper_sync.projection_provisioning import load_projection_supply

    targets: list[ProvisionTarget] = []
    for row in registry_module.DELIVERED_PER_ENTRY_CONTRACTS:
        entry_id = str(row.get("entry_id") or "").strip()
        if entry_filter and entry_id != entry_filter:
            continue
        supply = load_projection_supply(entry_id)
        wp_codes = tuple(sorted(getattr(supply.provider, "PILOT_WP_CODES", ()) or ()))
        target = ProvisionTarget(
            entry_id=entry_id,
            contract_id=supply.contract_id,
            provider_module=supply.provider_module,
            wp_codes=wp_codes,
        )
        if not wp_codes:
            target.unresolved_reason = (
                f"provider {supply.provider_module} 没有 `PILOT_WP_CODES` —— "
                "无法确定该 entry 对应哪些底稿编码"
            )
            targets.append(target)
            continue
        clauses: list[Any] = [sa.text("wp.is_deleted = false")]
        params: dict[str, Any] = {"codes": list(wp_codes)}
        if project_filter is not None:
            clauses.append(sa.text("wp.project_id = :pid"))
            params["pid"] = str(project_filter)
        sql = sa.text(
            "SELECT wp.id AS wp_id, wp.project_id AS project_id, wi.wp_code AS wp_code "
            "FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id "
            "WHERE wi.wp_code = ANY(:codes) AND wp.is_deleted = false "
            + ("AND wp.project_id = :pid " if project_filter is not None else "")
            + f"ORDER BY {TARGET_ORDER_SQL} LIMIT 1"
        )
        hit = (await session.execute(sql, params)).mappings().first()
        if hit is None:
            target.unresolved_reason = (
                f"库里没有 wp_code ∈ {list(wp_codes)} 的未删除底稿"
                + (f"（且限定 project={project_filter}）" if project_filter else "")
                + " —— 该 entry 在本库没有可 provision 的目标底稿；这不是 provisioner 的"
                "缺陷，而是**没有承载它的业务底稿实例**"
            )
            targets.append(target)
            continue
        target.project_id = uuid.UUID(str(hit["project_id"]))
        target.wp_id = uuid.UUID(str(hit["wp_id"]))
        target.wp_code = str(hit["wp_code"])
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
    """只读预判 representation 阶段结算（与 provisioner 的分支同序）。"""
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
    if bundle_id is not None and current_bundle is not None and current_bundle == bundle_id:
        settlement = "reused_current"
    elif int(pending or 0) > 0:
        settlement = "attached_candidate"
    else:
        settlement = "blocked"
    return {
        "settlement": settlement,
        "current_representation_id": None if pointer is None else str(pointer),
        "current_definition_bundle_id": None if current_bundle is None else str(current_bundle),
        "candidates_awaiting_contract": int(pending or 0),
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
