"""底稿模板元数据路由

提供 wp_template_metadata 的查询和种子数据加载端点。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/wp-template-metadata",
    tags=["wp-template-metadata"],
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@router.get("")
async def list_template_metadata(
    audit_stage: str | None = None,
    component_type: str | None = None,
    cycle: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """查询模板元数据（支持按阶段/组件类型/循环筛选）"""
    q = "SELECT * FROM wp_template_metadata WHERE 1=1"
    params: dict = {}
    if audit_stage:
        q += " AND audit_stage = :stage"
        params["stage"] = audit_stage
    if component_type:
        q += " AND component_type = :ctype"
        params["ctype"] = component_type
    if cycle:
        q += " AND cycle = :cycle"
        params["cycle"] = cycle
    q += " ORDER BY wp_code"

    rows = (await db.execute(text(q), params)).mappings().all()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@router.get("/{wp_code}")
async def get_template_metadata(
    wp_code: str,
    db: AsyncSession = Depends(get_db),
):
    """获取单个底稿的模板元数据"""
    row = (await db.execute(
        text("SELECT * FROM wp_template_metadata WHERE wp_code = :code"),
        {"code": wp_code},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"模板元数据不存在: {wp_code}")
    return dict(row)


@router.post("/seed")
async def seed_template_metadata(
    db: AsyncSession = Depends(get_db),
):
    """加载种子数据到 wp_template_metadata 表（幂等）"""
    seed_files = [
        DATA_DIR / "wp_template_metadata_dn_seed.json",
        DATA_DIR / "wp_template_metadata_b_seed.json",
        DATA_DIR / "wp_template_metadata_cas_seed.json",
    ]

    total_entries = []
    for sf in seed_files:
        if not sf.exists():
            continue
        with open(sf, "r", encoding="utf-8") as f:
            data = json.load(f)
        total_entries.extend(data.get("entries", []))

    inserted, updated, errors = 0, 0, []
    for entry in total_entries:
        wp_code = entry.get("wp_code")
        if not wp_code:
            continue
        try:
            existing = (await db.execute(
                text("SELECT id FROM wp_template_metadata WHERE wp_code = :code"),
                {"code": wp_code},
            )).first()

            row_data = {
                "wp_code": wp_code,
                "component_type": entry.get("component_type", "univer"),
                "audit_stage": entry.get("audit_stage", "substantive"),
                "cycle": entry.get("cycle"),
                "file_format": entry.get("file_format", "xlsx"),
                "procedure_steps": json.dumps(entry.get("procedure_steps") or [], ensure_ascii=False),
                "formula_cells": json.dumps(entry.get("formula_cells") or [], ensure_ascii=False),
                "linked_accounts": json.dumps(entry.get("linked_accounts") or [], ensure_ascii=False),
                "note_section": entry.get("note_section"),
                "conclusion_cell": json.dumps(entry.get("conclusion_cell"), ensure_ascii=False) if entry.get("conclusion_cell") else None,
                "audit_objective": entry.get("audit_objective"),
                "related_assertions": json.dumps(entry.get("related_assertions") or [], ensure_ascii=False),
            }

            if existing:
                set_clause = ", ".join(f"{k} = :{k}" for k in row_data if k != "wp_code")
                await db.execute(text(f"UPDATE wp_template_metadata SET {set_clause} WHERE wp_code = :wp_code"), row_data)
                updated += 1
            else:
                row_data["id"] = str(uuid4())
                cols = ", ".join(row_data.keys())
                vals = ", ".join(f":{k}" for k in row_data.keys())
                await db.execute(text(f"INSERT INTO wp_template_metadata ({cols}) VALUES ({vals})"), row_data)
                inserted += 1
        except Exception as e:
            errors.append({"wp_code": wp_code, "error": str(e)})

    await db.commit()
    return {
        "message": f"种子数据加载完成: inserted={inserted}, updated={updated}",
        "inserted": inserted,
        "updated": updated,
        "total": len(total_entries),
        "errors": errors[:10],
    }
