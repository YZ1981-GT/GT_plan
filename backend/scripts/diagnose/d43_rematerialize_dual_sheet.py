# -*- coding: utf-8 -*-
"""D4 multi-sheet rematerialize：把已发布 representation 升级到 d42+d43+d45 契约 bundle。

前置：Task76 已创建新 contract/instrumentation/bundle（本脚本不 provision）。
路径：rehash 同款 plan → multi-instrument substrate → 读多 store →
``publish_first_generation``（推进 content revision）。

用法::

    $env:PYTHONIOENCODING='utf-8'; $env:DB_DISABLE_SSL='True'
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/d43_rematerialize_dual_sheet.py --check
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/d43_rematerialize_dual_sheet.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

ENTRY_ID = "xlsx/gt-d4-operating-revenue"


def _engine():
    from app.core.config import settings

    return create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)


def _load_rehash_module() -> Any:
    path = _BACKEND / "scripts" / "fix" / "fix_projection_representation_rehash.py"
    name = "fix_projection_representation_rehash"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


async def _desired_bundle(session: Any, *, contract_id: str) -> dict[str, Any]:
    from app.services.workpaper_sync.projection_first_publication import (
        _approved_projection_bundle_id,
    )

    bundle_id = await _approved_projection_bundle_id(session, contract_id=contract_id)
    row = (
        await session.execute(
            sa.text(
                "SELECT id::text AS id, canonical_payload_sha256 AS sha256 "
                "FROM working_paper_sync_definition_bundle WHERE id = :id"
            ),
            {"id": str(bundle_id)},
        )
    ).mappings().one()
    return {"id": row["id"], "sha256": row["sha256"]}


async def _current_bundle_sha(session: Any, *, representation_id: Any) -> str:
    row = (
        await session.execute(
            sa.text(
                "SELECT definition_bundle_sha256 "
                "FROM working_paper_content_representation WHERE id = :id"
            ),
            {"id": str(representation_id)},
        )
    ).scalar_one()
    return str(row)


async def _read_store_map(
    session: Any, *, wp_id: str, item_ids: tuple[str, ...]
) -> dict[str, str]:
    from app.services.workpaper_sync import phase5_d4_revenue_detail as D4

    fixed_ids = set(getattr(D4, "STORE_ITEM_IDS_D45_FIXED", ()) or ())
    out: dict[str, str] = {}
    for item_id in item_ids:
        raw = (
            await session.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
                ),
                {"wp": str(wp_id), "item": item_id},
            )
        ).scalar_one_or_none()
        if raw is None or not str(raw).strip():
            out[item_id] = "" if item_id in fixed_ids else D4.EMPTY_STORE_PAYLOAD
        else:
            out[item_id] = str(raw)
    return out


async def run(*, apply: bool, force: bool = False) -> dict[str, Any]:
    from app.services.workpaper_sync import phase5_d4_revenue_detail as D4
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync import projection_first_publication as F
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    RH = _load_rehash_module()
    engine = _engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)
    report: dict[str, Any] = {
        "entry_id": ENTRY_ID,
        "mode": "apply" if apply else "check",
        "force": bool(force),
    }
    try:
        async with Session() as session:
            current = await RH._current_representation(session, entry_id=ENTRY_ID)
            if current is None:
                report["status"] = "blocked"
                report["reason"] = "no current published representation"
                return report
            current_sha = await _current_bundle_sha(
                session, representation_id=current["representation_id"]
            )
            report["current"] = {
                "representation_id": str(current["representation_id"]),
                "wp_id": str(current["wp_id"]),
                "project_id": str(current["project_id"]),
                "bundle_sha256": current_sha,
                "generation": current["generation"],
            }
            desired = await _desired_bundle(session, contract_id=D4.ADAPTER_ID)
            report["desired_bundle"] = desired
            if current_sha == desired["sha256"] and not force:
                report["status"] = "already_on_desired_bundle"
                return report

            store_item_ids = tuple(D4.STORE_ITEM_IDS) + tuple(
                getattr(D4, "STORE_ITEM_IDS_D45_FIXED", ()) or ()
            )
            store_map = await _read_store_map(
                session, wp_id=str(current["wp_id"]), item_ids=store_item_ids
            )
            report["store_bytes"] = {
                item: len(payload.encode("utf-8")) for item, payload in store_map.items()
            }
            if not apply:
                report["status"] = "would_rematerialize"
                return report

            resolution = CanonicalResolutionService(
                session, CanonicalArtifactRepository(_BACKEND)
            )
            artifacts = CanonicalArtifactRepository(_BACKEND)
            repository = WorkpaperSyncRepository(session)
            plan = await RH.resolve_rehash_plan(
                session=session,
                resolution=resolution,
                project_id=uuid.UUID(str(current["project_id"])),
                wp_id=uuid.UUID(str(current["wp_id"])),
                entry_id=ENTRY_ID,
                actor_id=None,
            )
            with tempfile.TemporaryDirectory(prefix="d43-remat-") as tmp:
                staged = F.stage_instrumented_substrate(
                    entry_id=ENTRY_ID,
                    staging_dir=Path(tmp),
                    contract=plan.contract,
                )
                receipt = await F.publish_first_generation(
                    session=session,
                    resolution=resolution,
                    artifacts=artifacts,
                    repository=repository,
                    plan=plan,
                    staged=staged,
                    store_payload=store_map,
                )
                await session.commit()
            report["status"] = "rematerialized"
            report["new_representation_id"] = str(receipt.representation_id)
            report["new_generation"] = int(receipt.representation_generation)
            report["new_revision"] = int(receipt.revision)
            return report
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="即使已在 desired bundle 上也重新 publish（修 identity 冻结漂移等）",
    )
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()
    report = asyncio.run(run(apply=bool(args.apply), force=bool(args.force)))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.json_path:
        Path(args.json_path).write_text(text, encoding="utf-8")
    ok = report.get("status") in {
        "would_rematerialize",
        "rematerialized",
        "already_on_desired_bundle",
    }
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
