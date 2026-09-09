#!/usr/bin/env python
"""从真实 working-paper/render-config 重算编制说明全局 coverage。

默认只读数据库与权威文件，不维护第二份业务清册。可选 ``--output`` 仅保存带
facts digest 的 evidence snapshot；下一次可用 ``--prior`` 检测 source facts 漂移。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.models.workpaper_models import WorkingPaper, WpIndex  # noqa: E402
from app.services.guidance_coverage_service import (  # noqa: E402
    GuidanceCoverageContext,
    build_global_guidance_coverage,
)
from app.services.guidance_inventory import (  # noqa: E402
    build_static_guidance_inventory,
    load_runtime_exemptions,
    load_template_source_facts,
)
from app.services.guidance_source_refs import (  # noqa: E402
    build_template_authority_snapshot,
)


def _prior_digests(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError("prior evidence 缺少 entries 数组")
    result: dict[str, str] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        entry_id = str(item.get("global_entry_id") or "").strip()
        digest = str(item.get("entry_digest") or "").strip()
        if entry_id and digest:
            result[entry_id] = digest
    return result


async def _fallback_user_id(db) -> object:
    result = await db.execute(sa.text("SELECT id FROM users ORDER BY created_at, id LIMIT 1"))
    user_id = result.scalar()
    if user_id is None:
        raise RuntimeError("数据库没有可用于只读 render context 的用户")
    return user_id


async def _load_contexts(
    db,
    *,
    project_id: UUID | None,
    wp_code: str | None,
    limit: int | None,
) -> tuple[list[GuidanceCoverageContext], list[dict[str, str]]]:
    from app.models.core import Project
    from app.routers import wp_render_config, wp_render_config_helpers
    from app.routers.wp_guidance_chat import _load_runtime_custom_guidance_entries

    stmt = (
        sa.select(
            WorkingPaper.id.label("wp_id"),
            WorkingPaper.project_id.label("project_id"),
            WorkingPaper.file_path.label("file_path"),
            WorkingPaper.source_type.label("source_type"),
            WorkingPaper.created_by.label("created_by"),
            WorkingPaper.updated_by.label("updated_by"),
            WorkingPaper.assigned_to.label("assigned_to"),
            WorkingPaper.reviewer.label("reviewer"),
            WpIndex.wp_code.label("wp_code"),
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .join(Project, WorkingPaper.project_id == Project.id)
        .where(
            WorkingPaper.is_deleted == sa.false(),
            WpIndex.is_deleted == sa.false(),
            Project.is_deleted == sa.false(),
        )
        .order_by(WorkingPaper.project_id, WpIndex.wp_code, WorkingPaper.id)
    )
    if project_id is not None:
        stmt = stmt.where(WorkingPaper.project_id == project_id)
    if wp_code:
        stmt = stmt.where(WpIndex.wp_code == wp_code)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).mappings().all()

    shared_user_id: object | None = None
    contexts: list[GuidanceCoverageContext] = []
    failures: list[dict[str, str]] = []
    for row in rows:
        wp_id = row["wp_id"]
        project = row["project_id"]
        code = str(row["wp_code"] or "").strip()
        context_id = f"{project}/{wp_id}/{code}"
        raw_template_path = wp_render_config_helpers._resolve_template_path(
            SimpleNamespace(file_path=row["file_path"]), code
        )
        template_path = Path(raw_template_path) if raw_template_path else None
        source_origin = str(row["source_type"] or "") or None
        user_id = (
            row["created_by"]
            or row["updated_by"]
            or row["assigned_to"]
            or row["reviewer"]
        )
        if user_id is None:
            if shared_user_id is None:
                shared_user_id = await _fallback_user_id(db)
            user_id = shared_user_id

        try:
            render_response = await wp_render_config._get_render_config_impl(
                wp_id,
                None,
                db,
                SimpleNamespace(id=user_id),
            )
            render_sheets = (
                render_response.get("sheets", [])
                if isinstance(render_response, dict)
                else []
            )
            template_version = (
                str(render_response.get("template_version") or "") or None
                if isinstance(render_response, dict)
                else None
            )
            authority_snapshot = await asyncio.to_thread(
                build_template_authority_snapshot,
                parent_wp_code=code,
                render_sheets=render_sheets,
                active_template_path=template_path,
                template_version=template_version,
                template_origin=source_origin,
            )
            template_facts = await asyncio.to_thread(
                load_template_source_facts,
                code,
                template_path=template_path,
                template_version=template_version,
                template_origin=source_origin,
            )
            exemptions = await asyncio.to_thread(load_runtime_exemptions, code)
            custom_entries = await _load_runtime_custom_guidance_entries(
                db=db,
                project_id=project,
                wp_id=wp_id,
                wp_code=code,
            )
            contexts.append(
                GuidanceCoverageContext(
                    context_id=context_id,
                    wp_id=str(wp_id),
                    project_id=str(project),
                    parent_wp_code=code,
                    render_sheets=tuple(dict(item) for item in render_sheets),
                    template_facts=template_facts,
                    custom_entries=custom_entries,
                    exemptions=exemptions,
                    template_authority_snapshot=authority_snapshot,
                )
            )
        except Exception as exc:  # noqa: BLE001 — 报告全部无法枚举的真实 context
            failures.append(
                {
                    "context_id": context_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
    return contexts, failures


def _print_summary(payload: dict, failures: list[dict[str, str]]) -> None:
    counters = payload["counters"]
    print(
        "guidance coverage "
        f"contexts={counters.get('contexts', 0)} "
        f"entries={counters.get('entries', 0)} "
        f"required={counters.get('required', 0)} "
        f"required_exact={counters.get('required_exact', 0)} "
        f"required_non_exact={counters.get('required_non_exact', 0)} "
        f"closed={payload['closed']} failures={len(failures)}"
    )
    print(
        f"facts_digest={payload['facts_digest']} "
        f"contexts_digest={payload['contexts_digest']} run_id={payload['run_id']}"
    )
    for failure in failures[:20]:
        print(
            f"ERROR {failure['context_id']}: "
            f"{failure['error_type']}: {failure['error']}"
        )
    if len(failures) > 20:
        print(f"ERROR ... 其余 {len(failures) - 20} 项省略")


async def main_async(args: argparse.Namespace) -> int:
    from app.core.database import async_session

    project_id = UUID(args.project_id) if args.project_id else None
    prior = _prior_digests(args.prior)
    static_entries = await asyncio.to_thread(build_static_guidance_inventory)
    async with async_session() as db:
        contexts, failures = await _load_contexts(
            db,
            project_id=project_id,
            wp_code=args.wp_code,
            limit=args.limit,
        )
    report = await asyncio.to_thread(
        build_global_guidance_coverage,
        contexts,
        static_entries=static_entries,
        prior_entry_digests=prior,
    )
    payload = report.to_dict()
    payload["failures"] = failures
    _print_summary(payload, failures)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if failures:
        return 2
    if args.require_closed and not report.closed:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id")
    parser.add_argument("--wp-code")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-closed", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit 必须大于 0")
    try:
        return asyncio.run(main_async(args))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
