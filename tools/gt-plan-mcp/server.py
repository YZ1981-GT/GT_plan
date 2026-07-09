#!/usr/bin/env python3
"""GT_plan 领域 MCP — wp_code / spec / migration 查询（只读）。"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(
    os.environ.get("GT_PLAN_ROOT", Path(__file__).resolve().parents[2])
).resolve()

mcp = FastMCP("gt-plan")

OVERRIDES_PATH = PROJECT_ROOT / "backend" / "app" / "data" / "wp_code_overrides.json"
SPECS_INDEX = PROJECT_ROOT / ".kiro" / "specs" / "INDEX.md"
SPECS_DIR = PROJECT_ROOT / ".kiro" / "specs"
MIGRATIONS_DIR = PROJECT_ROOT / "backend" / "migrations"
GUIDANCE_DIR = PROJECT_ROOT / "backend" / "data" / "wp_guidance"
RENDER_SCHEMA_DIR = PROJECT_ROOT / "backend" / "data" / "wp_render_schema"


def _load_overrides() -> dict[str, str]:
    data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("wp_code_overrides.json must be a flat object")
    return data


def _parse_tasks(tasks_path: Path) -> dict[str, int]:
    if not tasks_path.exists():
        return {"total": 0, "done": 0, "pending": 0, "optional": 0}
    text = tasks_path.read_text(encoding="utf-8")
    done = len(re.findall(r"^- \[x\]", text, re.MULTILINE))
    optional = len(re.findall(r"^- \[ \]\*", text, re.MULTILINE))
    pending = len(re.findall(r"^- \[ \][^*]", text, re.MULTILINE))
    return {
        "total": done + pending + optional,
        "done": done,
        "pending": pending,
        "optional": optional,
    }


def _cycle_from_wp_code(wp_code: str) -> str:
    m = re.match(r"^([A-S])\d", wp_code.upper())
    return m.group(1) if m else "?"


@mcp.tool()
def wp_lookup(wp_code: str) -> str:
    """按 wp_code 查 componentType、循环字母、guidance/render schema 路径。"""
    overrides = _load_overrides()
    key = wp_code.strip()
    component_type = overrides.get(key)
    if component_type is None:
        # 大小写/全角容错
        for k, v in overrides.items():
            if k.upper() == key.upper():
                key, component_type = k, v
                break
    if component_type is None:
        return json.dumps(
            {"found": False, "wp_code": wp_code, "hint": "未在 wp_code_overrides.json 中找到"},
            ensure_ascii=False,
            indent=2,
        )

    guidance = GUIDANCE_DIR / f"{key}.json"
    render_candidates = list(RENDER_SCHEMA_DIR.glob(f"**/{key}*.yaml"))[:5]

    return json.dumps(
        {
            "found": True,
            "wp_code": key,
            "component_type": component_type,
            "cycle": _cycle_from_wp_code(key),
            "guidance_path": str(guidance.relative_to(PROJECT_ROOT)) if guidance.exists() else None,
            "render_schema_paths": [
                str(p.relative_to(PROJECT_ROOT)) for p in render_candidates
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def spec_list_active() -> str:
    """列出 active spec 目录（不含 _archive）。"""
    if not SPECS_DIR.exists():
        return json.dumps({"active_specs": [], "count": 0})
    active = sorted(
        d.name
        for d in SPECS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    )
    return json.dumps({"count": len(active), "active_specs": active}, ensure_ascii=False, indent=2)


@mcp.tool()
def spec_status(spec_name: str) -> str:
    """查 spec 三件套存在性与 tasks.md 完成度。"""
    name = spec_name.strip().strip("/")
    spec_dir = SPECS_DIR / name
    if not spec_dir.exists():
        archive_matches = list(SPECS_DIR.glob(f"_archive/**/{name}"))
        if archive_matches:
            spec_dir = archive_matches[0]
        else:
            return json.dumps(
                {"found": False, "spec_name": spec_name},
                ensure_ascii=False,
                indent=2,
            )

    req = spec_dir / "requirements.md"
    design = spec_dir / "design.md"
    tasks = spec_dir / "tasks.md"
    progress = _parse_tasks(tasks)

    return json.dumps(
        {
            "found": True,
            "spec_name": name,
            "path": str(spec_dir.relative_to(PROJECT_ROOT)),
            "has_requirements": req.exists(),
            "has_design": design.exists(),
            "has_tasks": tasks.exists(),
            "tasks": progress,
            "completion_pct": round(
                100 * progress["done"] / progress["total"], 1
            )
            if progress["total"]
            else None,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def migration_status() -> str:
    """扫描 backend/migrations 下 V*.sql，返回最高版本与文件数。"""
    if not MIGRATIONS_DIR.exists():
        return json.dumps({"error": "migrations dir not found"})
    versions: list[int] = []
    for p in MIGRATIONS_DIR.glob("V*.sql"):
        m = re.match(r"V(\d+)", p.name)
        if m:
            versions.append(int(m.group(1)))
    versions.sort()
    return json.dumps(
        {
            "migration_dir": str(MIGRATIONS_DIR.relative_to(PROJECT_ROOT)),
            "count": len(versions),
            "highest": f"V{versions[-1]:03d}" if versions else None,
            "latest_files": [
                f"V{v:03d}.sql" for v in versions[-5:]
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def index_summary() -> str:
    """读取 .kiro/specs/INDEX.md 前 15 行摘要。"""
    if not SPECS_INDEX.exists():
        return json.dumps({"error": "INDEX.md not found"})
    lines = SPECS_INDEX.read_text(encoding="utf-8").splitlines()[:15]
    return json.dumps({"summary_lines": lines}, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
