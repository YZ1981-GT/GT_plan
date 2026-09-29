# -*- coding: utf-8 -*-
"""D1 重新发布 representation：用当前磁盘契约 provision 新 bundle + 发新 generation。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 25~29 的门解除

═══ 为什么需要重新发布 ═══

`_INCLUDE_D104_NOTETYPE_STATIC` 撤回（T7 裁决 A）使契约从 19 table 回到 18 table，
但已 published representation 的 `structure_hash` 冻结于更早的值（先于 T7 甚至先于
本 spec 的任何改动就已过期，真因见 `test_d1_full_book_gate_blocker_pg.py::
test_blocker_predates_this_spec_static_table`）。
整册门 `verify_d1_full_book_real_stack.py` 因 `ObservedIdentityDriftError` fail-closed。

解除路径 = provision 新 bundle（用当前磁盘契约）+ 用新 bundle 发新 representation（新
generation、新 structure_hash）。D2 先例 `d2_rematerialize_sibling_sheets.py`。

═══ 🔴 这是写共享 dev 库的操作 ═══

* 会创建新 definition artifacts + 新 definition bundle + 新 content representation
* 推进 content revision（新 generation）
* **不可逆**（发布后旧 representation 仍可查但不再是 current）

用法::

    .venv\\Scripts\\python.exe backend/scripts/fix/fix_d1_republish_representation.py --check
    .venv\\Scripts\\python.exe backend/scripts/fix/fix_d1_republish_representation.py --apply
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

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

ENTRY_ID = "xlsx/gt-d1-notes-receivable"
ADAPTER_ID = "d1.notes_receivable_detail"


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


async def run(*, apply: bool, force: bool = False) -> dict[str, Any]:
    from app.services.workpaper_sync import phase5_d1_notes_receivable as D1
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
    }
    try:
        async with Session() as session:
            # ── ① 当前 representation ──
            current = await RH._current_representation(session, entry_id=ENTRY_ID)
            if current is None:
                report["status"] = "blocked"
                report["reason"] = "no current published representation"
                return report
            report["current"] = {
                "representation_id": str(current["representation_id"]),
                "wp_id": str(current["wp_id"]),
                "project_id": str(current["project_id"]),
                "generation": current["generation"],
            }

            # ── ② provision 新 bundle（用当前磁盘契约，幂等去重）──
            # 🔴 **必须用 `ReusingDefinitionPublisher`**（不是内层 `DefinitionPublisher`）：
            #    它先查已存在的 approved definition 再决定 insert 还是 reuse，
            #    避免 unique constraint 冲突（authority_model sha 不变时直接复用）。
            from app.services.workpaper_sync.projection_provisioning import (
                ReusingDefinitionPublisher,
            )

            publisher = ReusingDefinitionPublisher(
                session=session,
                artifacts=CanonicalArtifactRepository(_BACKEND),
                repository=WorkpaperSyncRepository(session),
                project_id=uuid.UUID(str(current["project_id"])),
                wp_id=uuid.UUID(str(current["wp_id"])),
                source_commit="fix_d1_republish",
            )
            defs = await D1.publish_definitions(publisher)
            report["bundle_id"] = str(defs.bundle_id)
            report["bundle_sha256"] = defs.bundle_sha256
            report["contract_sha256"] = defs.contract_definition_sha256
            report["reused_stages"] = list(publisher.reused_stages)
            report["created_stages"] = list(publisher.created_stages)
            print(f"[②] bundle={defs.bundle_id} "
                  f"reused={publisher.reused_stages} created={publisher.created_stages}")

            if not apply:
                await session.rollback()
                report["status"] = "would_republish"
                return report

            await session.commit()
            print("[②] committed")

        # ── ③ 用新 bundle 发新 representation ──
        async with Session() as session:
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

            # 读 D1 的 store 载荷
            store_item_ids = tuple(D1.all_store_item_ids())
            store_map: dict[str, str] = {}
            for item_id in store_item_ids:
                raw = (
                    await session.execute(
                        sa.text(
                            "SELECT remark FROM checklist_responses "
                            "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
                        ),
                        {"wp": str(current["wp_id"]), "item": item_id},
                    )
                ).scalar_one_or_none()
                if raw is not None and str(raw).strip():
                    store_map[item_id] = str(raw)
            report["store_items"] = len(store_map)
            print(f"[③] store 载荷 {len(store_map)}/{len(store_item_ids)} 有数据")

            with tempfile.TemporaryDirectory(prefix="d1-republish-") as tmp:
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
            report["status"] = "republished"
            report["new_representation_id"] = str(receipt.representation_id)
            report["new_generation"] = int(receipt.representation_generation)
            report["new_revision"] = int(receipt.revision)
            print(f"[③] 已发布新 representation generation={receipt.representation_generation}")
            return report
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()
    report = asyncio.run(run(apply=bool(args.apply)))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.json_path:
        Path(args.json_path).write_text(text, encoding="utf-8")
    ok = report.get("status") in {"would_republish", "republished"}
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
