"""底稿程序步骤→Sheet映射 API（P0-P3 功能集合）

包含：
- GET /{wp_id}/step-mapping：程序步骤→Sheet映射
- GET /mapping-rules：映射规则配置
- POST /mapping-rules/custom：用户自定义映射规则
- GET /{wp_id}/references：跨模块引用关系
- GET /{wp_id}/validation-rules：校验规则
- GET /{wp_id}/stale-chain：stale传播链
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import json
from pathlib import Path

from app.deps import get_db, get_current_user

router = APIRouter(prefix="/api/workpapers", tags=["workpaper-step-mapping"])

# Load mapping data at module level (hot-reload friendly)
_MAPPING_DATA = None
_RULES_DATA = None


def _load_mapping():
    global _MAPPING_DATA, _RULES_DATA
    base = Path(__file__).parent.parent.parent / "data"
    _MAPPING_DATA = json.loads((base / "step_sheet_mapping.json").read_bytes())
    _RULES_DATA = json.loads((base / "sheet_mapping_rules.json").read_bytes())
    return _MAPPING_DATA, _RULES_DATA


def _get_mapping():
    global _MAPPING_DATA
    if _MAPPING_DATA is None:
        _load_mapping()
    return _MAPPING_DATA


def _get_rules():
    global _RULES_DATA
    if _RULES_DATA is None:
        _load_mapping()
    return _RULES_DATA


# ═══════════════════════════════════════════════════════════════════════════════
# P0: step-mapping
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/step-mapping")
async def get_step_mapping(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取底稿的程序步骤→Sheet映射"""
    from sqlalchemy import text

    # Get wp_code from wp_index
    result = await db.execute(
        text("SELECT wp_code FROM wp_index WHERE id = :id"), {"id": wp_id}
    )
    row = result.fetchone()
    if not row:
        return {"steps": [], "wp_code": None, "message": "底稿未找到"}

    wp_code = row[0]
    # Get primary code (D2-1 -> D2)
    primary_code = wp_code.split("-")[0] if "-" in wp_code else wp_code

    mapping = _get_mapping()
    wp_mapping = mapping.get("mappings", {}).get(primary_code)

    if not wp_mapping:
        return {
            "steps": [],
            "wp_code": wp_code,
            "primary_code": primary_code,
            "message": "无映射数据",
        }

    return {
        "wp_code": wp_code,
        "primary_code": primary_code,
        "wp_name": wp_mapping.get("wp_name", ""),
        "has_template": wp_mapping.get("has_template", False),
        "available_sheets": wp_mapping.get("available_sheets", []),
        "steps": wp_mapping.get("steps", []),
    }


@router.get("/mapping-rules")
async def get_mapping_rules(user=Depends(get_current_user)):
    """获取映射规则配置（供前端展示规则说明）"""
    rules = _get_rules()
    return {
        "new_workpaper_defaults": rules.get("new_workpaper_defaults", {}),
        "pattern_count": len(rules.get("naming_patterns", {}).get("patterns", [])),
        "exact_rule_codes": list(rules.get("exact_rules", {}).keys()),
        "custom_rule_codes": [
            k for k in rules.get("custom_rules", {}).keys() if not k.startswith("_")
        ],
    }


@router.post("/mapping-rules/custom")
async def add_custom_rule(body: dict, user=Depends(get_current_user)):
    """用户添加自定义映射规则"""
    wp_code = body.get("wp_code")
    step_name = body.get("step_name")
    target_sheets = body.get("target_sheets", [])

    if not wp_code or not step_name or not target_sheets:
        raise HTTPException(400, "wp_code, step_name, target_sheets are required")

    rules = _get_rules()
    custom = rules.get("custom_rules", {})
    if wp_code not in custom:
        custom[wp_code] = {}
    custom[wp_code][step_name] = target_sheets
    rules["custom_rules"] = custom

    # Save back
    base = Path(__file__).parent.parent.parent / "data"
    (base / "sheet_mapping_rules.json").write_bytes(
        json.dumps(rules, ensure_ascii=False, indent=2).encode("utf-8")
    )

    # Invalidate cache
    global _MAPPING_DATA, _RULES_DATA
    _MAPPING_DATA = None
    _RULES_DATA = None

    return {
        "ok": True,
        "message": f"已添加自定义规则: {wp_code}.{step_name} → {target_sheets}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# P1: cross-module references
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/references")
async def get_wp_references(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取底稿的跨模块引用关系（上游依赖+下游影响）"""
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT wp_code FROM wp_index WHERE id = :id"), {"id": wp_id}
    )
    row = result.fetchone()
    if not row:
        return {"incoming": [], "outgoing": [], "module_links": []}

    wp_code = row[0]
    primary_code = wp_code.split("-")[0] if "-" in wp_code else wp_code

    base = Path(__file__).parent.parent.parent / "data"
    cwr = json.loads((base / "cross_wp_references.json").read_bytes())

    incoming = []
    outgoing = []
    module_links = []

    for ref in cwr.get("references", []):
        source = ref.get("source_wp", "")
        targets = ref.get("targets", [])

        # This wp is the source
        if source == primary_code:
            for t in targets:
                if "wp_code" in t:
                    outgoing.append(
                        {
                            "ref_id": ref.get("ref_id", ""),
                            "target_wp": t["wp_code"],
                            "target_sheet": t.get("sheet", ""),
                            "description": ref.get("description", ""),
                            "severity": ref.get("severity", "warning"),
                            "category": ref.get("category", ""),
                        }
                    )
                elif "target_module" in t:
                    module_links.append(
                        {
                            "ref_id": ref.get("ref_id", ""),
                            "target_module": t["target_module"],
                            "link_type": t.get("link_type", ""),
                            "description": ref.get("description", ""),
                        }
                    )

        # This wp is a target
        for t in targets:
            if t.get("wp_code") == primary_code:
                incoming.append(
                    {
                        "ref_id": ref.get("ref_id", ""),
                        "source_wp": source,
                        "source_sheet": ref.get("source_sheet", ""),
                        "description": ref.get("description", ""),
                        "severity": ref.get("severity", "warning"),
                        "formula": t.get("formula"),
                    }
                )

    return {
        "wp_code": wp_code,
        "primary_code": primary_code,
        "incoming": incoming,
        "outgoing": outgoing,
        "module_links": module_links,
        "total_connections": len(incoming) + len(outgoing) + len(module_links),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# P2: validation rules
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/validation-rules")
async def get_wp_validation_rules(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取底稿适用的校验规则"""
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT wp_code FROM wp_index WHERE id = :id"), {"id": wp_id}
    )
    row = result.fetchone()
    if not row:
        return {"rules": [], "wp_code": None}

    wp_code = row[0]
    primary_code = wp_code.split("-")[0] if "-" in wp_code else wp_code

    base = Path(__file__).parent.parent.parent / "data"

    all_rules = []
    for fname in [
        "d_cycle_validation_rules.json",
        "efghijklmn_cycle_validation_rules.json",
        "bcas_cycle_validation_rules.json",
    ]:
        fp = base / fname
        if fp.exists():
            data = json.loads(fp.read_bytes())
            for rule in data.get("rules", []):
                if rule.get("wp_code") == primary_code:
                    all_rules.append(rule)

    return {
        "wp_code": wp_code,
        "primary_code": primary_code,
        "rules": all_rules,
        "total": len(all_rules),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# P3: stale propagation chain
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/stale-chain")
async def get_stale_chain(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取底稿的stale传播链（如果本底稿数据变更，哪些下游会受影响）"""
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT wp_code FROM wp_index WHERE id = :id"), {"id": wp_id}
    )
    row = result.fetchone()
    if not row:
        return {"affected": [], "wp_code": None}

    wp_code = row[0]
    primary_code = wp_code.split("-")[0] if "-" in wp_code else wp_code

    base = Path(__file__).parent.parent.parent / "data"
    cwr = json.loads((base / "cross_wp_references.json").read_bytes())

    # BFS: find all downstream affected workpapers
    affected = []
    visited = set()
    queue = [primary_code]

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        for ref in cwr.get("references", []):
            if ref.get("source_wp") == current:
                for t in ref.get("targets", []):
                    target = t.get("wp_code", t.get("target_module", ""))
                    if target and target not in visited:
                        affected.append(
                            {
                                "wp_code": target,
                                "via": current,
                                "description": ref.get("description", ""),
                                "severity": ref.get("severity", "warning"),
                                "depth": len(visited),
                            }
                        )
                        # Don't traverse into system modules
                        if target not in (
                            "REPORT",
                            "NOTE",
                        ) and not target.startswith(
                            (
                                "disclosure",
                                "audit_",
                                "financial",
                                "trial",
                                "adjustment",
                                "misstatement",
                                "consolidation",
                            )
                        ):
                            queue.append(target)

    return {
        "wp_code": wp_code,
        "primary_code": primary_code,
        "affected": affected,
        "total_affected": len(affected),
    }
