# -*- coding: utf-8 -*-
"""按底稿把 entry 的在线编辑版本从权威模板重新发布一代（业务内容不变）。

spec: d2-skeleton-slot-reuse-and-writeback-speed · R3 / design §5

═══ 为什么需要 ═══

骨架槽位复用只在「新行」上生效，且永不把新行排到已有业务数据上方 ⇒ 已经发布过的底稿
（业务数据排在模板骨架之后，如重药安徽 D2-2：骨架 13~24、数据 25~524）不会被就地改形。
本工具从权威模板重新 instrument，再用当前 store 走首版发布同一条链
（``resolve_rehash_plan`` → ``stage_instrumented_substrate`` → ``publish_first_generation``），
产出新 revision / 新代际：store 行先填模板骨架行、剩余插在其后 ⇒ 业务数据从模板首行开始。

与 ``scripts/diagnose/d2_rematerialize_sibling_sheets.py`` 的区别：那个按 entry 取「第一家」
底稿的 representation；本工具必须指定 ``--wp-id``，只动这一份底稿。

用法::

    $env:PYTHONIOENCODING='utf-8'
    .\\.venv\\Scripts\\python.exe backend/scripts/fix/republish_entry_from_template.py --wp-id <id> --check
    .\\.venv\\Scripts\\python.exe backend/scripts/fix/republish_entry_from_template.py --wp-id <id> --apply

``--check`` 只读：当前代际、受管表第一条业务行行号、store 字节数、是否有人正在在线编辑。
``--apply`` 有人正在在线编辑（未过期房间里有未过期的活跃参与者）时拒绝执行。
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import io
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

DEFAULT_ENTRY_ID = "xlsx/gt-d2-accounts-receivable"


def _engine() -> Any:
    from app.core.config import settings

    return create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)


def _load_rehash_module() -> Any:
    path = _BACKEND / "scripts" / "fix" / "fix_projection_representation_rehash.py"
    name = "fix_projection_representation_rehash"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _provider(entry_id: str) -> Any:
    from app.services.workpaper_sync import projection_first_publication as F

    row = F._delivered_row(entry_id)
    return importlib.import_module(str(row["provider_module"]))


def _primary_spec(provider: Any) -> Any:
    specs = getattr(provider, "instrumentation_specs", None)
    if callable(specs):
        return tuple(specs())[0]
    return provider.instrumentation_spec()


def first_business_row(data: bytes, *, spec: Any) -> dict[str, Any]:
    """受管表里第一条非骨架身份的行号，以及它上方的骨架行数（只读 UUID 列）。"""
    import openpyxl

    from app.services.workpaper_sync.contracts import is_template_skeleton_identity

    from openpyxl.utils import column_index_from_string

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb[spec.managed_sheet]
        column = column_index_from_string(spec.uuid_col)
        skeleton_above = 0
        cells = ws.iter_rows(
            min_row=spec.first_data_row, min_col=column, max_col=column, values_only=True
        )
        for row, (value,) in enumerate(cells, start=spec.first_data_row):
            identity = str(value or "").strip()
            if not identity:
                continue
            if is_template_skeleton_identity(identity):
                skeleton_above += 1
                continue
            return {"first_business_row": row, "skeleton_rows_above": skeleton_above}
        return {"first_business_row": None, "skeleton_rows_above": skeleton_above}
    finally:
        wb.close()


async def _current(session: Any, *, wp_id: str, entry_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.text(
                "SELECT s.current_representation_id::text AS representation_id, "
                "       s.representation_generation AS generation, "
                "       w.project_id::text AS project_id, a.relative_path AS relative_path, "
                "       v.revision AS revision "
                "FROM working_paper_sync_entry_state s "
                "JOIN working_paper w ON w.id = s.wp_id "
                "JOIN working_paper_content_representation r ON r.id = s.current_representation_id "
                "JOIN working_paper_artifact a ON a.id = r.artifact_id "
                "JOIN working_paper_content_version v ON v.id = r.content_version_id "
                "WHERE s.wp_id = :wp AND s.entry_id = :entry"
            ),
            {"wp": wp_id, "entry": entry_id},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def _live_editors(session: Any, *, wp_id: str, entry_id: str) -> int:
    """未过期房间里未过期的活跃参与者数（有人正在在线编辑）。"""
    return int(
        (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM working_paper_oo_participant p "
                    "JOIN working_paper_oo_room r ON r.id = p.room_id "
                    "WHERE r.wp_id = :wp AND r.entry_id = :entry "
                    "AND r.state NOT IN ('closed', 'superseded') AND r.expires_at > now() "
                    "AND p.state = 'active' AND p.expires_at > now()"
                ),
                {"wp": wp_id, "entry": entry_id},
            )
        ).scalar_one()
    )


async def _store_map(session: Any, *, wp_id: str, provider: Any) -> dict[str, str]:
    item_ids_fn = getattr(provider, "all_store_item_ids", None)
    item_ids = tuple(item_ids_fn()) if callable(item_ids_fn) else (provider.STORE_ITEM_ID,)
    out: dict[str, str] = {}
    for item_id in item_ids:
        raw = (
            await session.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
                ),
                {"wp": wp_id, "item": item_id},
            )
        ).scalar_one_or_none()
        if raw is not None and str(raw).strip():
            out[item_id] = str(raw)
    return out


async def run(*, wp_id: str, entry_id: str, apply: bool) -> dict[str, Any]:
    from app.services.workpaper_sync import projection_first_publication as F
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    RH = _load_rehash_module()
    provider = _provider(entry_id)
    spec = _primary_spec(provider)
    report: dict[str, Any] = {
        "entry_id": entry_id,
        "wp_id": wp_id,
        "mode": "apply" if apply else "check",
    }
    engine = _engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            current = await _current(session, wp_id=wp_id, entry_id=entry_id)
            if current is None:
                report["status"] = "blocked"
                report["reason"] = "该底稿还没有已发布的在线编辑版本（首版走首次打开自动发布）"
                return report
            artifact = RH._artifact_path(str(current["relative_path"]))
            report["current"] = {
                **{k: current[k] for k in ("representation_id", "generation", "revision")},
                **first_business_row(artifact.read_bytes(), spec=spec),
            }
            store_map = await _store_map(session, wp_id=wp_id, provider=provider)
            report["store_bytes"] = {k: len(v.encode("utf-8")) for k, v in store_map.items()}
            editors = await _live_editors(session, wp_id=wp_id, entry_id=entry_id)
            report["live_editors"] = editors
            if not apply:
                report["status"] = "would_republish"
                return report
            if editors:
                report["status"] = "blocked"
                report["reason"] = f"有 {editors} 位用户正在在线编辑该底稿，请先关闭在线编辑再执行"
                return report

            artifacts = CanonicalArtifactRepository(_BACKEND)
            resolution = CanonicalResolutionService(session, artifacts)
            plan = await RH.resolve_rehash_plan(
                session=session,
                resolution=resolution,
                project_id=uuid.UUID(str(current["project_id"])),
                wp_id=uuid.UUID(wp_id),
                entry_id=entry_id,
                actor_id=None,
            )
            with tempfile.TemporaryDirectory(prefix="republish-") as tmp:
                staged = F.stage_instrumented_substrate(
                    entry_id=entry_id, staging_dir=Path(tmp), contract=plan.contract
                )
                receipt = await F.publish_first_generation(
                    session=session,
                    resolution=resolution,
                    artifacts=artifacts,
                    repository=WorkpaperSyncRepository(session),
                    plan=plan,
                    staged=staged,
                    store_payload=store_map,
                )
                await session.commit()
        async with Session() as session:
            after = await _current(session, wp_id=wp_id, entry_id=entry_id)
        assert after is not None
        report["status"] = "republished"
        report["receipt"] = {
            "representation_id": str(receipt.representation_id),
            "generation": int(receipt.representation_generation),
            "revision": int(receipt.revision),
        }
        report["after"] = {
            **{k: after[k] for k in ("representation_id", "generation", "revision")},
            **first_business_row(
                RH._artifact_path(str(after["relative_path"])).read_bytes(), spec=spec
            ),
        }
        return report
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wp-id", required=True)
    parser.add_argument("--entry-id", default=DEFAULT_ENTRY_ID)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()
    report = asyncio.run(
        run(wp_id=str(uuid.UUID(args.wp_id)), entry_id=args.entry_id, apply=bool(args.apply))
    )
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.json_path:
        Path(args.json_path).write_text(text, encoding="utf-8")
    return 0 if report.get("status") in {"would_republish", "republished"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
