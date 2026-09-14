# -*- coding: utf-8 -*-
"""发布 custom / user-upload（OOXML 本体权威）lane 的 approved authority model + bundle。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 65
Requirements: 2.11, 3.9, 5.5, 6.19, 12.6, 12.10
Properties: **P50 / P64 / P69**

═══ 这个脚本是 `OpaqueAuthorityProvisioner.provision()` 的**唯一消费宿主** ═══

改造前 `OpaqueAuthorityProvisioner` 只有一个 `ensure()`，它在**业务内容写入的那一次**
顺手 `publish_bundle(..., approved=True)`。AC 6.19 要求的是「先发布 approved
authority-model definition 与 non-null approved definition bundle」，写路径自己给自己
发证等于让这条承诺没有任何可 falsify 的判据。

Task 65 把它拆成两个方法：

* `resolve(lane_id=...)` —— 只查，`commit_bytes` 只调这个；缺供给时抛
  `OpaqueBundleNotProvisionedError` 并指向本脚本；
* `provision(project_id, wp_id, authority_model=...)` —— 查+发布，**只有本脚本调**。

与 Task 76 的 `fix_task76_provision_projection_definitions.py` 同款：服务层不开事务、
不 commit，事务边界与 CLI 语义都在本脚本里。

═══ 为什么 provision 的粒度是 authority model 而不是 lane ═══

opaque bundle 的 canonical payload 只由四项组成：authority-model definition 的 digest
加三个 registry typed null marker 的 digest（`definitions.build_bundle_canonical_payload`
的 marker 分支）。于是**同一个 authority model 下所有 lane 的 bundle canonical bytes
逐字节相同**；而 `working_paper_sync_definition_bundle.canonical_payload_sha256` 有
`UNIQUE` 约束（V151），所以「一 lane 一 bundle」在物理上不可能 —— 第二条 lane 插入时
必然撞 UNIQUE。

因此 Task 65 正文「每类 custom/opaque entry 必须先发布 approved …definition 与 non-null
approved definition bundle」在 opaque 通道的正确落地是：

* **每个 authority model 一份 approved bundle**（本脚本发布，当前 2 个）；
* **每条 lane 经 `OpaqueEntryGate` 解析到它**，并在 gate 里逐条校验 lane 登记的
  authority model 与 bundle 的 authority child 双向锁死；
* lane 之间的独立性体现在 `entry_id` / representation generation / evidence 上，
  **不在 bundle 上** —— 那是内容寻址的必然结果，不是偷懒。

对照：`projection_contract` 的 bundle 三个 slot 都是 per-entry definition child，
canonical bytes 逐 entry 不同，所以那条通道才是「一 entry 一 bundle」。

═══ artifact 归属列说明（不是身份）═══

`DefinitionPublisher.publish_definition` 会往 `working_paper_artifact` 写一行，它的
`project_id` / `wp_id` 是 NOT NULL FK。而 definition store 的路径是**内容寻址**的
（`definition_store/{kind}/{sha256}.json`，见 `definitions.definition_store_relative_path`），
authority-model definition 的 canonical payload 只有 `schema_version` 与
`authority_model` 两个键 —— 两者都不含 project/wp。

也就是说：这两列只是 artifact 行的归属标签，既不进 definition digest、也不进 bundle
digest、更不进 `application_key`。本脚本取「最早创建的未删除底稿」作为归属（确定性、
可复现），并把它记进报告，而不是随机挑一个然后不留痕。

用法（Windows PowerShell，仓库根）::

    .\\.venv\\Scripts\\python.exe backend/scripts/fix/fix_task65_provision_opaque_authority_bundles.py --check
    .\\.venv\\Scripts\\python.exe backend/scripts/fix/fix_task65_provision_opaque_authority_bundles.py --apply
    .\\.venv\\Scripts\\python.exe backend/scripts/fix/fix_task65_provision_opaque_authority_bundles.py --check --json tmp_task65_check.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import sqlalchemy as sa  # noqa: E402


class ProvisionScriptError(RuntimeError):
    """脚本级失败。**不**降级为成功退出码（禁 fail-open）。"""


# ═══════════════════════════════════════════════════════════════════════════
# 1. 目标解析
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProvisionTarget:
    """一个待发布的 authority model + 它服务的 lane 清单。"""

    authority_model: str
    lane_ids: tuple[str, ...]
    project_id: uuid.UUID | None
    wp_id: uuid.UUID | None
    unresolved_reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.project_id is not None and self.wp_id is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority_model": self.authority_model,
            "lane_ids": list(self.lane_ids),
            "artifact_owner_project_id": None if self.project_id is None else str(self.project_id),
            "artifact_owner_wp_id": None if self.wp_id is None else str(self.wp_id),
            "unresolved_reason": self.unresolved_reason,
        }


async def _artifact_owner(session: Any) -> tuple[uuid.UUID, uuid.UUID] | None:
    """取 artifact 归属列用的 `(project_id, wp_id)`：最早创建的未删除底稿。

    确定性排序（`created_at, id`）而不是 `LIMIT 1` 随缘：报告里要能复现「这次归属给了
    谁」，否则同一份 definition 在两次运行里挂到不同 wp 上，事后追不回来。
    """
    row = (
        await session.execute(
            sa.text(
                "SELECT project_id, id FROM working_paper "
                "WHERE is_deleted = false AND project_id IS NOT NULL "
                "ORDER BY created_at, id LIMIT 1"
            )
        )
    ).first()
    if row is None:
        return None
    return uuid.UUID(str(row[0])), uuid.UUID(str(row[1]))


async def resolve_targets(
    session: Any, *, authority_filter: str | None = None
) -> list[ProvisionTarget]:
    """由 lane 登记表**现算**待发布的 authority model 集合。

    分母来自 `opaque_entry_gate.OPAQUE_AUTHORITY_LANES`，不在本脚本抄第二份清单 ——
    抄一份就意味着「新登记一条 lane」不会自动进 provision 目标，于是 gate 侧会永远
    fail closed 而运维不知道该发布什么。
    """
    from app.services.workpaper_sync.opaque_entry_gate import (
        OPAQUE_AUTHORITY_LANES,
        assert_commit_bytes_lane_arguments_match_registry,
        assert_lane_registry_covers_source,
        assert_lane_writers_exist,
    )

    # 发布之前先让登记表与源码对上：给一个「登记表已经与源码脱钩」的库发布 bundle，
    # 发出来的东西没有消费方（或消费方拿不到）。三条判据各自独立 fail closed。
    assert_lane_registry_covers_source()
    assert_lane_writers_exist()
    assert_commit_bytes_lane_arguments_match_registry()

    by_model: dict[str, list[str]] = {}
    for lane in OPAQUE_AUTHORITY_LANES:
        by_model.setdefault(lane.authority_model.value, []).append(lane.lane_id)

    owner = await _artifact_owner(session)
    targets: list[ProvisionTarget] = []
    for model, lanes in sorted(by_model.items()):
        if authority_filter and model != authority_filter:
            continue
        targets.append(
            ProvisionTarget(
                authority_model=model,
                lane_ids=tuple(sorted(lanes)),
                project_id=None if owner is None else owner[0],
                wp_id=None if owner is None else owner[1],
                unresolved_reason=(
                    None
                    if owner is not None
                    else "库里没有未删除且带 project_id 的底稿 —— `working_paper_artifact` "
                    "的 project_id/wp_id 是 NOT NULL FK，无法登记 definition blob"
                ),
            )
        )
    if authority_filter and not targets:
        raise ProvisionScriptError(
            f"--authority {authority_filter!r} 不在 lane 登记表声明的 authority model 集合 "
            f"{sorted(by_model)} 内"
        )
    return targets


# ═══════════════════════════════════════════════════════════════════════════
# 2. 现状快照
# ═══════════════════════════════════════════════════════════════════════════


async def snapshot_opaque_supply(session: Any) -> dict[str, Any]:
    """opaque 通道的供给现状（按 authority model 分桶）。

    只读，且**不**调用 gate 的 resolve —— 快照要能在「一个都没发布」时也返回结构完整的
    结果，而 gate 在那种情况下（正确地）抛异常。
    """
    rows = (
        await session.execute(
            sa.text(
                "SELECT a.authority_model_type AS model, a.state AS auth_state, "
                "       b.id AS bundle_id, b.state AS bundle_state, "
                "       b.canonical_payload_sha256 AS bundle_sha, "
                "       b.template_slot_type, b.instrumentation_slot_type, b.contract_slot_type "
                "  FROM working_paper_sync_definition_artifact a "
                "  LEFT JOIN working_paper_sync_definition_bundle b "
                "         ON b.authority_model_definition_id = a.id "
                " WHERE a.kind = 'authority_model' "
                "   AND a.authority_model_type IN "
                "       ('custom_authoritative_ooxml', 'opaque_single_onlyoffice') "
                " ORDER BY a.authority_model_type, b.created_at NULLS FIRST, b.id"
            )
        )
    ).mappings().all()
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_model.setdefault(str(row["model"]), []).append(
            {
                "authority_state": row["auth_state"],
                "bundle_id": None if row["bundle_id"] is None else str(row["bundle_id"]),
                "bundle_state": row["bundle_state"],
                "bundle_sha256": row["bundle_sha"],
                "slot_types": [
                    row["template_slot_type"],
                    row["instrumentation_slot_type"],
                    row["contract_slot_type"],
                ],
            }
        )
    totals = (
        await session.execute(
            sa.text(
                "SELECT "
                " (SELECT count(*) FROM working_paper_sync_definition_artifact "
                "   WHERE kind = 'authority_model') AS authority_definitions, "
                " (SELECT count(*) FROM working_paper_sync_definition_bundle) AS bundles, "
                " (SELECT count(*) FROM working_paper_sync_definition_null_marker "
                "   WHERE state = 'active') AS active_markers"
            )
        )
    ).mappings().one()
    return {"by_authority_model": by_model, "totals": dict(totals)}


async def probe_gate(session: Any) -> dict[str, Any]:
    """逐 lane 跑一次 gate 的只读解析，如实记录每条 lane 现在能不能消费。

    这是本脚本 `--check` 的核心判据：它跑的是**生产消费路径那一份** gate
    （`OpaqueEntryGate.resolve_approved_bundle`），不是脚本自己抄的一段查询。抄一段的
    后果是「脚本说 OK 但业务请求仍然 500」。
    """
    from app.services.workpaper_sync.opaque_entry_gate import OpaqueEntryGate, lane_ids

    gate = OpaqueEntryGate(session=session)
    out: dict[str, Any] = {}
    for lane_id in lane_ids():
        try:
            resolved = await gate.resolve_approved_bundle(lane_id=lane_id)
        except Exception as exc:  # noqa: BLE001 - 如实记录，收尾按 errors 决定退出码
            out[lane_id] = {
                "consumable": False,
                "error_code": getattr(exc, "error_code", type(exc).__name__),
                "error": str(exc).splitlines()[0],
            }
            continue
        out[lane_id] = {"consumable": True, **resolved.as_dict()}
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 3. check / apply
# ═══════════════════════════════════════════════════════════════════════════


async def run_check(session: Any, targets: list[ProvisionTarget]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "mode": "check",
        "targets": [t.as_dict() for t in targets],
        "supply": await snapshot_opaque_supply(session),
        "gate": await probe_gate(session),
        "errors": [],
    }
    report["consumable_lane_count"] = sum(
        1 for item in report["gate"].values() if item.get("consumable")
    )
    report["blocked_lane_count"] = len(report["gate"]) - report["consumable_lane_count"]
    # `--check` 只报告，不因为「还没 provision」判失败 —— 那正是它要回答的问题。
    unresolved = [t.as_dict() for t in targets if not t.resolved]
    if unresolved:
        report["errors"].append(
            {"kind": "artifact_owner_unresolved", "targets": unresolved}
        )
    return report


async def run_apply(session_factory: Any, targets: list[ProvisionTarget]) -> dict[str, Any]:
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.writer_migration import OpaqueAuthorityProvisioner

    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
    report: dict[str, Any] = {"mode": "apply", "published": [], "errors": []}
    async with session_factory() as probe:
        report["supply_before"] = await snapshot_opaque_supply(probe)
    for target in targets:
        item: dict[str, Any] = {"target": target.as_dict()}
        if not target.resolved:
            item["status"] = "unresolved"
            report["published"].append(item)
            report["errors"].append(
                {
                    "authority_model": target.authority_model,
                    "error": target.unresolved_reason or "artifact 归属未解析",
                }
            )
            continue
        # 一个 authority model 一个事务：失败只回滚它自己。
        async with session_factory() as session:
            provisioner = OpaqueAuthorityProvisioner(
                session=session,
                repository=WorkpaperSyncRepository(session),
                artifacts=artifacts,
                resolution=CanonicalResolutionService(session, artifacts),
            )
            try:
                snapshot = await provisioner.provision(
                    project_id=target.project_id,  # type: ignore[arg-type]
                    wp_id=target.wp_id,  # type: ignore[arg-type]
                    authority_model=target.authority_model,
                )
                await session.commit()
            except Exception as exc:  # noqa: BLE001 - 记 ERROR 态并在收尾抛出（禁 fail-open）
                await session.rollback()
                item["status"] = "error"
                item["error"] = f"{type(exc).__name__}: {exc}"
                report["published"].append(item)
                report["errors"].append(
                    {"authority_model": target.authority_model, "error": item["error"]}
                )
                continue
        item["status"] = "ok"
        item["definition_bundle_id"] = str(snapshot.bundle_id)
        item["definition_bundle_sha256"] = snapshot.bundle_sha256
        item["authority_model_definition_id"] = str(snapshot.authority_model_definition_id)
        item["authority_model_definition_sha256"] = snapshot.authority_model_definition_sha256
        item["typed_slot_inventory"] = [list(x) for x in snapshot.typed_slot_inventory]
        report["published"].append(item)
    async with session_factory() as probe:
        report["supply_after"] = await snapshot_opaque_supply(probe)
        # 发布之后逐 lane 再跑一次生产 gate：这是「发出来的东西真的能被消费」的判据。
        # 只看 `provision()` 的返回值不够 —— 它返回的是 provisioner 自己的视角，而
        # 消费侧还要过 lane 登记 ↔ bundle authority child 双向锁死与三 slot marker 判据。
        report["gate_after"] = await probe_gate(probe)
    blocked = sorted(
        lane_id
        for lane_id, item in report["gate_after"].items()
        if not item.get("consumable")
    )
    report["blocked_lane_ids_after_apply"] = blocked
    if blocked:
        report["errors"].append(
            {
                "kind": "lane_still_blocked_after_apply",
                "lane_ids": blocked,
                "detail": {k: report["gate_after"][k] for k in blocked},
            }
        )
    return report


# ═══════════════════════════════════════════════════════════════════════════
# 4. CLI
# ═══════════════════════════════════════════════════════════════════════════


async def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 65 opaque authority bundle provisioner")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只读预演（默认）")
    mode.add_argument("--apply", action="store_true", help="真发布 approved authority + bundle")
    parser.add_argument(
        "--authority", default=None, help="只处理这一个 authority model 枚举值"
    )
    parser.add_argument("--json", dest="json_path", default=None, help="报告落盘路径")
    args = parser.parse_args(argv)

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise ProvisionScriptError(
            "本脚本写 V151 的真实表（含 CHECK/trigger），必须真实 PostgreSQL；"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}"
        )
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            targets = await resolve_targets(session, authority_filter=args.authority)
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
            f"{len(report['errors'])} 项失败（详见报告 errors）—— 不降级为成功"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
