"""科目→附注行映射 API — 维护科目名称到附注表格行的映射关系，提高自动取数匹配率

表结构：account_note_mapping
  - project_id + account_name + section_id + row_name 唯一
  - mapping_type: 'exact'（精确匹配）| 'contains'（包含匹配）| 'regex'（正则匹配）
  - 支持项目级自定义 + 全局默认

API:
  GET  /api/account-note-mapping/{project_id}           — 获取项目的所有映射
  PUT  /api/account-note-mapping/{project_id}           — 保存/更新映射（upsert）
  DELETE /api/account-note-mapping/{project_id}/{mapping_id} — 删除映射
  POST /api/account-note-mapping/{project_id}/auto-generate — 自动生成映射（从试算表和附注模板推断）
"""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/api/account-note-mapping", tags=["account-note-mapping"])


class MappingSave(BaseModel):
    account_name: str       # 试算表科目名
    section_id: str         # 附注章节 ID
    row_name: str           # 附注表格行名
    col_index: int = 1      # 目标列索引（默认第2列=期末余额）
    mapping_type: str = 'exact'  # exact | contains | regex


class MappingResponse(BaseModel):
    id: str
    project_id: str
    account_name: str
    section_id: str
    row_name: str
    col_index: int
    mapping_type: str
    created_at: str | None = None


_table_created = False

async def ensure_table(db: AsyncSession):
    global _table_created
    if _table_created:
        return
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS account_note_mapping (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL,
                account_name VARCHAR(200) NOT NULL,
                section_id VARCHAR(50) NOT NULL,
                row_name VARCHAR(200) NOT NULL,
                col_index INT NOT NULL DEFAULT 1,
                mapping_type VARCHAR(20) NOT NULL DEFAULT 'exact',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(project_id, account_name, section_id, row_name)
            )
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_anm_proj ON account_note_mapping(project_id)"
        ))
        await db.commit()
        _table_created = True
    except Exception:
        await db.rollback()
        _table_created = True


@router.get("/{project_id}", response_model=list[MappingResponse])
async def get_mappings(project_id: str, db: AsyncSession = Depends(get_db)):
    await ensure_table(db)
    result = await db.execute(
        text("SELECT id, project_id, account_name, section_id, row_name, col_index, mapping_type, created_at FROM account_note_mapping WHERE project_id = :pid ORDER BY account_name"),
        {"pid": project_id},
    )
    return [MappingResponse(id=str(r[0]), project_id=str(r[1]), account_name=r[2], section_id=r[3], row_name=r[4], col_index=r[5], mapping_type=r[6], created_at=str(r[7]) if r[7] else None) for r in result.fetchall()]


@router.put("/{project_id}", response_model=MappingResponse)
async def save_mapping(project_id: str, body: MappingSave, db: AsyncSession = Depends(get_db)):
    await ensure_table(db)
    now = datetime.utcnow()
    new_id = str(uuid.uuid4())
    try:
        await db.execute(text("""
            INSERT INTO account_note_mapping (id, project_id, account_name, section_id, row_name, col_index, mapping_type, created_at)
            VALUES (:id, :pid, :an, :sid, :rn, :ci, :mt, :now)
            ON CONFLICT (project_id, account_name, section_id, row_name)
            DO UPDATE SET col_index = :ci, mapping_type = :mt
        """), {"id": new_id, "pid": project_id, "an": body.account_name, "sid": body.section_id, "rn": body.row_name, "ci": body.col_index, "mt": body.mapping_type, "now": now})
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    return MappingResponse(id=new_id, project_id=project_id, account_name=body.account_name, section_id=body.section_id, row_name=body.row_name, col_index=body.col_index, mapping_type=body.mapping_type, created_at=str(now))


@router.delete("/{project_id}/{mapping_id}")
async def delete_mapping(project_id: str, mapping_id: str, db: AsyncSession = Depends(get_db)):
    await ensure_table(db)
    await db.execute(text("DELETE FROM account_note_mapping WHERE id = :mid AND project_id = :pid"), {"mid": mapping_id, "pid": project_id})
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/auto-generate")
async def auto_generate_mappings(project_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """自动生成映射：从试算表科目名和附注模板行名进行模糊匹配"""
    await ensure_table(db)
    year = body.get("year", datetime.utcnow().year - 1)
    standard = body.get("standard", "soe")

    # 1. 获取试算表所有科目名
    result = await db.execute(
        text("SELECT DISTINCT account_name FROM trial_balance_entries WHERE project_id = :pid AND year = :y"),
        {"pid": project_id, "y": year},
    )
    account_names = [r[0] for r in result.fetchall() if r[0]]

    # 2. 加载附注模板
    from pathlib import Path
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    json_path = data_dir / f"consol_note_sections_{standard}.json"
    sections = []
    if json_path.exists():
        sections = json.loads(json_path.read_text(encoding="utf-8"))

    # 3. 模糊匹配：科目名包含在附注行名中，或附注行名包含在科目名中
    generated = 0
    for sec in sections:
        headers = sec.get("headers", [])
        rows = sec.get("rows", [])
        for row in rows:
            if not row or not row[0]:
                continue
            row_name = str(row[0]).strip()
            for acc_name in account_names:
                if not acc_name:
                    continue
                # 精确匹配或包含匹配
                matched = False
                if acc_name == row_name:
                    matched = True
                    mtype = 'exact'
                elif acc_name in row_name or row_name in acc_name:
                    # 只匹配长度 >= 2 的，避免单字匹配
                    if len(acc_name) >= 2 and len(row_name) >= 2:
                        matched = True
                        mtype = 'contains'

                if matched:
                    try:
                        await db.execute(text("""
                            INSERT INTO account_note_mapping (id, project_id, account_name, section_id, row_name, col_index, mapping_type, created_at)
                            VALUES (:id, :pid, :an, :sid, :rn, 1, :mt, :now)
                            ON CONFLICT (project_id, account_name, section_id, row_name) DO NOTHING
                        """), {"id": str(uuid.uuid4()), "pid": project_id, "an": acc_name, "sid": sec["section_id"], "rn": row_name, "mt": mtype, "now": datetime.utcnow()})
                        generated += 1
                    except Exception:
                        pass

    await db.commit()
    return {"generated": generated, "account_count": len(account_names), "section_count": len(sections)}
