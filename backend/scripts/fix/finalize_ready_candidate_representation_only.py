"""对一个 `state=ready` 的 upgrade candidate 执行 representation-only finalize。

**Spec: workpaper-html-onlyoffice-bidirectional-writeback-closure（G1-2 apply / G1-3 前置）**

═══ 做什么 ══════════════════════════════════════════════════════════════════

G1-2 裁决：纯口径 stale（artifact 字节未变、`_GT_SYNC` 坐标一致、只是冻结
`structure_hash` 是旧整份摘要口径）走 representation-only：在**既有 content version**
上经 `ExcelEntryFinalizeGate.finalize_candidate` → `MaterializeCoordinator.
finalize_definition_upgrade` → `RepresentationService.finalize_candidate` 产出新
representation generation，`content_revision` **不变**，旧 generation 保留且不 current。

本脚本是这条链的真实执行宿主，只针对**已就绪**（`state=ready`、contract+bundle 已
attach）的 candidate。它**不自造** candidate、**不重投影业务内容**、**不推进 revision**。
finalize 所需的四项实测入参（observed_structure / business_sheets / dynamic_columns /
identity_inventory）由 candidate 的 staged instrumented 字节现读得到，用的正是请求时刻
观测器（`published_identity_observer`）那批同一原语 —— 不抄第二份。

═══ 安全 ════════════════════════════════════════════════════════════════════

* 写业务库，但**可逆**：新增一个 representation generation + 切 entry pointer；旧
  generation 保留（`trg_wpcr_immutable` 禁止改旧行），`content_revision` 不变。
* 事务由 `RepresentationService` 内部单次 commit 持有；本脚本失败即 rollback。
* `--check` 只读预演（不 finalize）；`--apply` 真写。判成败一律查数据。

═══ 用法 ════════════════════════════════════════════════════════════════════

    $env:PYTHONIOENCODING='utf-8'
    python backend/scripts/fix/finalize_ready_candidate_representation_only.py --check --entry xlsx/gt-h1-fixed-assets
    python backend/scripts/fix/finalize_ready_candidate_representation_only.py --apply --entry xlsx/gt-h1-fixed-assets
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import uuid
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


class FinalizeHostError(RuntimeError):
    """宿主前置不成立。"""


async def _ready_candidate(session: Any, *, entry_id: str) -> Any:
    row = (
        await session.execute(
            sa.text(
                "SELECT c.id, c.wp_id, c.entry_id, c.content_version_id, "
                "       c.staged_artifact_id, c.staged_artifact_sha256, "
                "       c.target_definition_bundle_id, c.state, "
                "       c.visible_equivalence_report_sha256, "
                "       a.relative_path AS staged_rel, wp.project_id "
                "FROM working_paper_representation_upgrade_candidate c "
                "JOIN working_paper_artifact a ON a.id = c.staged_artifact_id "
                "JOIN working_paper wp ON wp.id = c.wp_id "
                "WHERE c.entry_id = :entry AND c.state = 'ready' "
                "  AND c.finalized_representation_id IS NULL "
                "ORDER BY c.created_at DESC, c.id DESC LIMIT 1"
            ),
            {"entry": entry_id},
        )
    ).mappings().first()
    if row is None:
        raise FinalizeHostError(
            f"entry {entry_id!r} 没有 state=ready 且未 finalize 的 candidate —— "
            "本脚本只处理已就绪 candidate，不自造"
        )
    return row


async def _adapter_id_for(session: Any, *, wp_id: str, cv_id: str) -> str:
    aid = (
        await session.execute(
            sa.text(
                "SELECT adapter_id FROM working_paper_content_representation "
                "WHERE wp_id = :wp AND content_version_id = :cv "
                "ORDER BY generation DESC LIMIT 1"
            ),
            {"wp": str(wp_id), "cv": str(cv_id)},
        )
    ).scalar_one()
    return str(aid)


def _equivalence_relative(staged_rel: str) -> str:
    """equivalence 报告与 candidate artifact 同目录，文件名前缀 `equivalence-`。

    `stage_upgrade_candidate` 落盘时把 `equivalence-<digest>.json` 放在 candidate
    artifact 同目录。gate 的 `_read_equivalence_report` 用 `Path(staged.path).parent /
    Path(equivalence_relative_path).name` 定位，故此处返回**equivalence 文件本身**的相对
    路径（其 `.name` 才是那个 json 文件名）。文件名从磁盘现读，不猜 digest。
    """
    parent_abs = _BACKEND_ROOT / Path(staged_rel).parent
    matches = sorted(parent_abs.glob("equivalence-*.json"))
    if not matches:
        raise FinalizeHostError(
            f"candidate 目录里没有 equivalence-*.json: {parent_abs}"
        )
    rel = matches[0].relative_to(_BACKEND_ROOT)
    return str(rel).replace("\\", "/")


async def _frozen_bundle_sha_and_instrumentation(
    session: Any, resolution: Any, *, bundle_id: uuid.UUID
) -> tuple[str, dict[str, Any]]:
    """从 frozen bundle 取 canonical digest 与 instrumentation payload（复用观测器读法）。"""
    from app.services.workpaper_sync.definitions import BundleSlot
    from app.services.workpaper_sync.published_identity_observer import PublishedIdentityObserver

    bundle = await resolution.load_bundle_snapshot(bundle_id)
    observer = PublishedIdentityObserver(session=session, resolution=resolution)
    child = await observer._load_child_row(
        slot=BundleSlot.instrumentation, bundle=bundle, context={"bundle_id": str(bundle_id)}
    )
    payload = await observer._read_definition_payload(
        child=child, context={"bundle_id": str(bundle_id)}
    )
    return str(bundle.bundle_sha256), dict(payload)


def _observe_candidate_bytes(*, data: bytes, contract: Any, instrumentation: dict[str, Any]):
    """用请求时刻观测器的同一批原语，从 candidate 字节现读四项 finalize 入参。"""
    from app.services.workpaper_sync.published_identity_observer import (
        _frozen_anchors,
        observe_dynamic_column_bindings,
        observe_structure_inventory,
    )
    from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory
    from app.services.excel_structure_fingerprint import (
        identity_inventory,
        structure_fingerprint,
    )

    anchors = _frozen_anchors(instrumentation)
    if anchors is None:
        raise FinalizeHostError("frozen instrumentation 缺 anchors —— 不得按展示名猜")
    fingerprint = structure_fingerprint(data)
    if fingerprint.errors:
        raise FinalizeHostError(f"candidate 结构采集有非致命错误: {fingerprint.errors[:3]}")
    inventory_raw = identity_inventory(
        data,
        expected_table=anchors["table_name"],
        uuid_column_letter=anchors["uuid_column_letter"],
        metadata_sheet=anchors["metadata_sheet"],
    )
    table = inventory_raw.get("excel_table") or {}
    physical_sheet = table.get("table_sheet")
    if not table.get("present") or not physical_sheet:
        raise FinalizeHostError("candidate 里找不到冻结 Excel Table 锚点")
    physical_sheet_by_key = {anchors["sheet_key"]: str(physical_sheet)}
    inventory = parse_identity_inventory(inventory_raw)
    row_uuid_rows = sorted(int(r) for r in inventory.row_uuids if str(r).isdigit())
    structure = observe_structure_inventory(
        contract=contract,
        fingerprint=fingerprint,
        physical_sheet_by_key=physical_sheet_by_key,
        row_uuid_rows=row_uuid_rows,
    )
    dynamic_bindings = observe_dynamic_column_bindings(
        contract=contract, fingerprint=fingerprint, physical_sheet_by_key=physical_sheet_by_key
    )
    dynamic_columns = {
        table_key: [(key, col) for key, col in cols.items()]
        for table_key, cols in dynamic_bindings.items()
    }
    return {
        "identity_inventory": inventory,
        "business_sheets": tuple(fingerprint.business_sheet_names()),
        "structure": structure,
        "dynamic_columns": dynamic_columns,
    }


async def _process(session: Any, *, entry_id: str, apply: bool) -> dict[str, Any]:
    from app.services.workpaper_sync.artifacts import (
        CanonicalArtifactRepository,
        StagedCandidate,
    )
    from app.services.workpaper_sync.contracts import load_contract
    from app.services.workpaper_sync.excel_entry_gate import (
        AdapterBuild,
        ExcelEntryDefinitionLoader,
        ExcelEntryFinalizeGate,
    )
    from app.services.workpaper_sync.materialize_coordinator import (
        build_materialize_coordinator,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    cand = await _ready_candidate(session, entry_id=entry_id)
    wp_id = uuid.UUID(str(cand["wp_id"]))
    project_id = uuid.UUID(str(cand["project_id"]))
    cv_id = str(cand["content_version_id"])
    bundle_id = uuid.UUID(str(cand["target_definition_bundle_id"]))

    revision_before = (
        await session.execute(
            sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
            {"wp": str(wp_id)},
        )
    ).scalar_one()
    gen_before = (
        await session.execute(
            sa.text(
                "SELECT max(generation) FROM working_paper_content_representation "
                "WHERE wp_id = :wp AND entry_id = :entry"
            ),
            {"wp": str(wp_id), "entry": entry_id},
        )
    ).scalar_one()

    adapter_id = await _adapter_id_for(session, wp_id=str(wp_id), cv_id=cv_id)
    contract = load_contract(adapter_id)

    resolution = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND_ROOT))
    frozen_bundle_sha256, instrumentation = await _frozen_bundle_sha_and_instrumentation(
        session, resolution, bundle_id=bundle_id
    )

    staged_path = _BACKEND_ROOT / str(cand["staged_rel"])
    data = staged_path.read_bytes()
    observed_sha = hashlib.sha256(data).hexdigest()
    if observed_sha != str(cand["staged_artifact_sha256"]):
        raise FinalizeHostError(
            f"staged candidate 字节 digest {observed_sha} 与登记 "
            f"{cand['staged_artifact_sha256']} 不一致"
        )

    observed = _observe_candidate_bytes(
        data=data, contract=contract, instrumentation=instrumentation
    )

    report: dict[str, Any] = {
        "entry_id": entry_id,
        "wp_id": str(wp_id),
        "candidate_id": str(cand["id"]),
        "content_version_id": cv_id,
        "revision_before": int(revision_before),
        "generation_before": int(gen_before or 0),
        "adapter_id": adapter_id,
        "observed_structure_size": len(observed["structure"]),
        "mode": "apply" if apply else "check",
    }
    if not apply:
        report["state"] = "ready_would_finalize"
        return report

    staged_candidate = StagedCandidate(
        candidate_id=uuid.UUID(str(cand["id"])),
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        path=staged_path,
        relative_path=str(cand["staged_rel"]),
        sha256=str(cand["staged_artifact_sha256"]),
        size_bytes=len(data),
        document_type="xlsx",
        equivalence_relative_path=_equivalence_relative(str(cand["staged_rel"])),
        equivalence_sha256=str(cand["visible_equivalence_report_sha256"] or ""),
        verified_before_move=True,
        verified_after_move=True,
    )
    coordinator = build_materialize_coordinator(session)
    loader = ExcelEntryDefinitionLoader(session=session, resolution=resolution)
    gate = ExcelEntryFinalizeGate(loader=loader, resolution=resolution, coordinator=coordinator)

    adapter_build = AdapterBuild(
        adapter_id=adapter_id,
        adapter_build_digest=await _adapter_build_digest(session, wp_id=str(wp_id), cv_id=cv_id),
        document_type="xlsx",
        contract_version=str(getattr(contract, "semantic_version", "") or "1.0.0"),
    )
    outcome = await gate.finalize_candidate(
        project_id=project_id,
        entry_id=entry_id,
        candidate_id=uuid.UUID(str(cand["id"])),
        staged_candidate=staged_candidate,
        frozen_bundle_sha256=frozen_bundle_sha256,
        adapter_build=adapter_build,
        observed_structure=observed["structure"],
        observed_business_sheets=observed["business_sheets"],
        observed_dynamic_columns=observed["dynamic_columns"],
    )

    revision_after = (
        await session.execute(
            sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
            {"wp": str(wp_id)},
        )
    ).scalar_one()
    if int(revision_after) != int(revision_before):
        raise FinalizeHostError(
            f"finalize 推进了 content_revision {revision_before} → {revision_after}"
        )
    report["state"] = "finalized"
    report["revision_after"] = int(revision_after)
    report["new_representation_id"] = str(outcome.finalize.representation_id)
    report["new_generation"] = int(outcome.finalize.representation_generation)
    report["revision_unchanged"] = bool(outcome.revision_unchanged)
    return report


async def _adapter_build_digest(session: Any, *, wp_id: str, cv_id: str) -> str:
    d = (
        await session.execute(
            sa.text(
                "SELECT adapter_build_digest FROM working_paper_content_representation "
                "WHERE wp_id = :wp AND content_version_id = :cv "
                "ORDER BY generation DESC LIMIT 1"
            ),
            {"wp": str(wp_id), "cv": str(cv_id)},
        )
    ).scalar_one()
    return str(d)


async def run(*, entry_id: str, apply: bool) -> dict[str, Any]:
    from app.core.config import settings

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise FinalizeHostError("必须真实 PostgreSQL")
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            try:
                report = await _process(session, entry_id=entry_id, apply=apply)
                if not apply:
                    await session.rollback()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    parser.add_argument("--entry", required=True)
    args = parser.parse_args(argv)

    report = asyncio.run(run(entry_id=args.entry, apply=bool(args.apply)))
    for key, value in report.items():
        print(f"  {key} = {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
