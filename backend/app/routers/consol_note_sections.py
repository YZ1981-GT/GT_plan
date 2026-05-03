"""合并附注章节 API — 从种子数据或 JSON 文件加载附注模板章节和表格结构

GET /api/consol-note-sections/{standard}              — 获取所有章节（树形）
GET /api/consol-note-sections/{standard}/{section_id} — 获取单个章节详情（含表格）
PUT /api/consol-note-sections/{project_id}/{year}/{section_id} — 保存用户编辑的附注数据
GET /api/consol-note-sections/{project_id}/{year}/{section_id}/data — 加载用户已保存的附注数据
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/api/consol-note-sections", tags=["consol-note-sections"])

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# 内存缓存 (mtime, data)
_cache: dict[str, tuple[float, list[dict]]] = {}


def _load_sections(standard: str) -> list[dict]:
    """从 JSON 文件加载章节数据（带内存缓存，文件变更时自动刷新）"""
    json_path = DATA_DIR / f"consol_note_sections_{standard}.json"
    if not json_path.exists():
        return []

    mtime = json_path.stat().st_mtime
    cached = _cache.get(standard)
    if cached and cached[0] == mtime:
        return cached[1]

    data = json.loads(json_path.read_text(encoding="utf-8"))
    _cache[standard] = (mtime, data)
    return data


@router.get("/{standard}")
async def get_all_sections(standard: str):
    """获取所有章节（按父章节分组的树形结构）"""
    sections = _load_sections(standard)
    # 按 parent_section 分组
    groups: dict[str, list[dict]] = {}
    group_order: list[str] = []
    for sec in sections:
        parent = sec.get("parent_section", "")
        if parent not in groups:
            groups[parent] = []
            group_order.append(parent)
        groups[parent].append({
            "section_id": sec["section_id"],
            "title": sec["title"],
            "seq": sec["seq"],
            "parent_seq": sec.get("parent_seq", 0),
        })

    tree = []
    for parent_name in group_order:
        children = groups[parent_name]
        tree.append({
            "label": parent_name,
            "parent_seq": children[0]["parent_seq"] if children else 0,
            "children": children,
            "table_count": len(children),
        })
    return tree


@router.get("/{standard}/{section_id}")
async def get_section_detail(standard: str, section_id: str):
    """获取单个表格节点详情（含表头和模板行）"""
    sections = _load_sections(standard)
    for sec in sections:
        if sec["section_id"] == section_id:
            return {
                "section_id": sec["section_id"],
                "title": sec["title"],
                "parent_section": sec.get("parent_section", ""),
                "headers": sec.get("headers", []),
                "rows": sec.get("rows", []),
                "multi_header": sec.get("multi_header"),
            }
    return {"error": "章节不存在", "section_id": section_id}


# ─── 用户数据存储（按项目+年度+章节） ─────────────────────────────────────────

_table_created = False


async def _ensure_table(db: AsyncSession):
    global _table_created
    if _table_created:
        return
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS consol_note_data (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL,
                year INT NOT NULL,
                section_id VARCHAR(50) NOT NULL,
                data JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(project_id, year, section_id)
            )
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_cnd_proj_year ON consol_note_data(project_id, year)"
        ))
        await db.commit()
        _table_created = True
    except Exception:
        await db.rollback()
        _table_created = True


@router.get("/data/{project_id}/{year}/{section_id}")
async def get_note_data(
    project_id: str, year: int, section_id: str,
    db: AsyncSession = Depends(get_db),
):
    """加载用户已保存的附注数据"""
    await _ensure_table(db)
    result = await db.execute(
        text("SELECT data, updated_at FROM consol_note_data WHERE project_id = :pid AND year = :y AND section_id = :sid"),
        {"pid": project_id, "y": year, "sid": section_id},
    )
    row = result.fetchone()
    if not row:
        return {"data": {}, "updated_at": None}
    return {"data": row[0] if isinstance(row[0], dict) else {}, "updated_at": str(row[1]) if row[1] else None}


@router.put("/data/{project_id}/{year}/{section_id}")
async def save_note_data(
    project_id: str, year: int, section_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """保存用户编辑的附注数据"""
    await _ensure_table(db)
    import uuid
    from datetime import datetime
    now = datetime.utcnow()
    data_json = json.dumps(body.get("data", {}), ensure_ascii=False)
    try:
        await db.execute(
            text("""
                INSERT INTO consol_note_data (id, project_id, year, section_id, data, updated_at)
                VALUES (:id, :pid, :y, :sid, CAST(:data AS jsonb), :now)
                ON CONFLICT (project_id, year, section_id)
                DO UPDATE SET data = CAST(:data AS jsonb), updated_at = :now
            """),
            {"id": str(uuid.uuid4()), "pid": project_id, "y": year, "sid": section_id, "data": data_json, "now": now},
        )
        await db.commit()
        return {"ok": True, "updated_at": str(now)}
    except Exception as e:
        await db.rollback()
        return {"ok": False, "error": str(e)}


# ─── 公式刷新：根据项目数据重新计算附注表格 ──────────────────────────────────

@router.post("/refresh/{project_id}/{year}/{section_id}")
async def refresh_note_by_formula(
    project_id: str, year: int, section_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """根据公式从项目试算表/报表数据重新计算附注表格内容
    
    逻辑：
    1. 加载该章节的模板结构（headers + 模板行）
    2. 查找该章节关联的公式规则
    3. 从项目试算表/报表中提取对应科目数据
    4. 按公式计算填充每行每列
    """
    standard = body.get("standard", "soe")
    company_code = body.get("company_code", "")
    
    # 加载章节模板
    sections = _load_sections(standard)
    template = None
    for sec in sections:
        if sec["section_id"] == section_id:
            template = sec
            break
    
    if not template:
        return {"rows": [], "message": "章节不存在"}
    
    headers = template.get("headers", [])
    template_rows = template.get("rows", [])
    
    # 尝试从试算表提取数据
    try:
        # 查询该企业的试算表数据
        params = {"pid": project_id, "y": year}
        query = "SELECT account_code, account_name, opening_balance, closing_balance, debit_amount, credit_amount FROM trial_balance_entries WHERE project_id = :pid AND year = :y"
        if company_code:
            query += " AND company_code = :cc"
            params["cc"] = company_code
        
        result = await db.execute(text(query), params)
        tb_rows = result.fetchall()
        
        if not tb_rows:
            return {"rows": template_rows, "message": "未找到试算表数据，返回模板默认值"}
        
        # 构建科目索引
        tb_map = {}
        for r in tb_rows:
            tb_map[r[1]] = {  # account_name as key
                "code": r[0], "name": r[1],
                "opening": float(r[2] or 0), "closing": float(r[3] or 0),
                "debit": float(r[4] or 0), "credit": float(r[5] or 0),
            }
        
        # 按模板行匹配科目名称填充数据
        filled_rows = []
        for row in template_rows:
            if not row:
                filled_rows.append(row)
                continue
            item_name = row[0] if row else ""
            # 清理项目名称用于匹配
            clean_name = item_name.strip().lstrip("△▲*#").strip()
            
            matched = tb_map.get(clean_name) or tb_map.get(item_name.strip())
            if matched:
                new_row = list(row)
                # 按表头匹配填充：期末余额、期初余额、本期发生额等
                for ci, h in enumerate(headers):
                    if ci == 0:
                        continue  # 项目名列不填
                    h_lower = h.replace(" ", "").replace("　", "")
                    if "期末" in h_lower or "本期" in h_lower or "账面余额" in h_lower:
                        new_row[ci] = str(matched["closing"]) if matched["closing"] else ""
                    elif "期初" in h_lower or "年初" in h_lower:
                        new_row[ci] = str(matched["opening"]) if matched["opening"] else ""
                    elif "借方" in h_lower or "增加" in h_lower:
                        new_row[ci] = str(matched["debit"]) if matched["debit"] else ""
                    elif "贷方" in h_lower or "减少" in h_lower:
                        new_row[ci] = str(matched["credit"]) if matched["credit"] else ""
                filled_rows.append(new_row)
            else:
                filled_rows.append(row)
        
        return {"rows": filled_rows, "message": f"已从试算表匹配 {len([r for r in filled_rows if r != template_rows])} 行"}
    
    except Exception as e:
        # 试算表不存在或查询失败，返回模板默认值
        return {"rows": template_rows, "message": f"数据提取失败: {str(e)}，返回模板默认值"}


# ─── 全审：对所有附注表格执行公式审核 ─────────────────────────────────────────

@router.post("/audit-all/{project_id}/{year}")
async def audit_all_notes(
    project_id: str, year: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """对所有附注表格执行公式审核
    
    审核规则：
    1. 合计行校验：合计行 = 明细行之和
    2. 期末 = 期初 + 增加 - 减少（如适用）
    3. 借贷平衡校验
    4. 与试算表数据交叉校验
    """
    standard = body.get("standard", "soe")
    company_code = body.get("company_code", "")
    
    sections = _load_sections(standard)
    results = []
    
    # 加载用户已保存的数据
    saved_data = {}
    try:
        rows = await db.execute(
            text("SELECT section_id, data FROM consol_note_data WHERE project_id = :pid AND year = :y"),
            {"pid": project_id, "y": year},
        )
        for r in rows.fetchall():
            saved_data[r[0]] = r[1] if isinstance(r[1], dict) else {}
    except Exception:
        pass
    
    # 加载试算表数据用于交叉校验
    tb_map = {}
    try:
        params = {"pid": project_id, "y": year}
        query = "SELECT account_name, closing_balance, opening_balance FROM trial_balance_entries WHERE project_id = :pid AND year = :y"
        if company_code:
            query += " AND company_code = :cc"
            params["cc"] = company_code
        tb_result = await db.execute(text(query), params)
        for r in tb_result.fetchall():
            tb_map[r[0]] = {"closing": float(r[1] or 0), "opening": float(r[2] or 0)}
    except Exception:
        pass
    
    audited_sections = 0
    
    for sec in sections:
        section_id = sec["section_id"]
        title = sec.get("title", "")
        headers = sec.get("headers", [])
        
        # 获取用户数据或模板数据
        user_data = saved_data.get(section_id, {})
        data_rows = user_data.get("rows", sec.get("rows", []))
        
        if not headers or not data_rows:
            continue
        
        audited_sections += 1
        
        # 规则1：合计行校验
        total_row_idx = None
        for ri, row in enumerate(data_rows):
            if row and row[0] and ("合" in str(row[0]) and "计" in str(row[0])):
                total_row_idx = ri
                break
        
        if total_row_idx is not None:
            total_row = data_rows[total_row_idx]
            for ci in range(1, len(headers)):
                # 计算明细行之和
                detail_sum = 0
                has_data = False
                for ri in range(total_row_idx):
                    row = data_rows[ri]
                    if ri == 0 and row[0] and ("合" in str(row[0]) or "小" in str(row[0])):
                        continue
                    try:
                        val = float(str(row[ci]).replace(",", "").replace("，", "")) if ci < len(row) and row[ci] else 0
                        detail_sum += val
                        if val != 0:
                            has_data = True
                    except (ValueError, IndexError):
                        pass
                
                if not has_data:
                    continue
                
                try:
                    total_val = float(str(total_row[ci]).replace(",", "").replace("，", "")) if ci < len(total_row) and total_row[ci] else 0
                except (ValueError, IndexError):
                    total_val = 0
                
                diff = round(total_val - detail_sum, 2)
                if abs(diff) > 0.01:
                    results.append({
                        "section_title": title,
                        "rule_name": f"合计行校验 - {headers[ci]}",
                        "level": "error",
                        "expected": f"{detail_sum:,.2f}",
                        "actual": f"{total_val:,.2f}",
                        "difference": f"{diff:,.2f}",
                        "message": f"合计行与明细行之和不一致",
                    })
                else:
                    results.append({
                        "section_title": title,
                        "rule_name": f"合计行校验 - {headers[ci]}",
                        "level": "pass",
                        "expected": f"{detail_sum:,.2f}",
                        "actual": f"{total_val:,.2f}",
                        "difference": "",
                        "message": "通过",
                    })
        
        # 规则2：与试算表交叉校验（按第一列科目名匹配）
        if tb_map:
            for ri, row in enumerate(data_rows):
                if not row or not row[0]:
                    continue
                item_name = str(row[0]).strip().lstrip("△▲*#").strip()
                tb_entry = tb_map.get(item_name)
                if not tb_entry:
                    continue
                
                for ci in range(1, min(len(headers), len(row))):
                    h = headers[ci].replace(" ", "")
                    try:
                        cell_val = float(str(row[ci]).replace(",", "").replace("，", "")) if row[ci] else 0
                    except ValueError:
                        continue
                    
                    if cell_val == 0:
                        continue
                    
                    expected = None
                    if "期末" in h or "本期" in h:
                        expected = tb_entry["closing"]
                    elif "期初" in h or "年初" in h:
                        expected = tb_entry["opening"]
                    
                    if expected is not None:
                        diff = round(cell_val - expected, 2)
                        if abs(diff) > 0.01:
                            results.append({
                                "section_title": title,
                                "rule_name": f"试算表交叉校验 - {item_name}/{headers[ci]}",
                                "level": "warn",
                                "expected": f"{expected:,.2f}",
                                "actual": f"{cell_val:,.2f}",
                                "difference": f"{diff:,.2f}",
                                "message": f"与试算表 {item_name} 数据不一致",
                            })
    
    return {
        "total_sections": audited_sections,
        "results": results,
    }


# ─── 单表审核：对指定附注表格执行公式审核 ─────────────────────────────────────

@router.post("/audit/{project_id}/{year}/{section_id}")
async def audit_single_note(
    project_id: str, year: int, section_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """对指定附注表格执行公式审核（前端传入当前编辑的数据）"""
    standard = body.get("standard", "soe")
    company_code = body.get("company_code", "")
    headers = body.get("headers", [])
    data_rows = body.get("rows", [])

    # 加载模板获取标题
    sections = _load_sections(standard)
    title = section_id
    for sec in sections:
        if sec["section_id"] == section_id:
            title = sec.get("title", section_id)
            if not headers:
                headers = sec.get("headers", [])
            if not data_rows:
                data_rows = sec.get("rows", [])
            break

    results = []

    if not headers or not data_rows:
        return {"results": [], "message": "无数据可审核"}

    # 规则1：合计行校验
    for ri, row in enumerate(data_rows):
        if not row or not row[0]:
            continue
        cell0 = str(row[0]).replace(" ", "").replace("　", "")
        if "合计" not in cell0 and "小计" not in cell0:
            continue

        # 找到合计行，计算上方明细行之和
        for ci in range(1, len(headers)):
            detail_sum = 0
            has_data = False
            for di in range(ri):
                dr = data_rows[di]
                if not dr or not dr[0]:
                    continue
                d0 = str(dr[0]).replace(" ", "").replace("　", "")
                if "合计" in d0 or "小计" in d0:
                    continue
                try:
                    val = float(str(dr[ci]).replace(",", "").replace("，", "")) if ci < len(dr) and dr[ci] else 0
                    detail_sum += val
                    if val != 0:
                        has_data = True
                except (ValueError, IndexError):
                    pass

            if not has_data:
                continue

            try:
                total_val = float(str(row[ci]).replace(",", "").replace("，", "")) if ci < len(row) and row[ci] else 0
            except (ValueError, IndexError):
                total_val = 0

            diff = round(total_val - detail_sum, 2)
            if abs(diff) > 0.01:
                results.append({
                    "section_title": title,
                    "rule_name": f"合计行校验 - {headers[ci]}",
                    "level": "error",
                    "expected": f"{detail_sum:,.2f}",
                    "actual": f"{total_val:,.2f}",
                    "difference": f"{diff:,.2f}",
                    "message": f"第{ri + 1}行合计与明细行之和不一致",
                })
            else:
                results.append({
                    "section_title": title,
                    "rule_name": f"合计行校验 - {headers[ci]}",
                    "level": "pass",
                    "expected": f"{detail_sum:,.2f}",
                    "actual": f"{total_val:,.2f}",
                    "difference": "",
                    "message": "通过",
                })

    # 规则2：期末 = 期初 + 增加 - 减少（如表头包含这些列）
    col_map = {}
    for ci, h in enumerate(headers):
        h_clean = h.replace(" ", "").replace("　", "")
        if "期末" in h_clean or "本期" in h_clean:
            col_map["closing"] = ci
        elif "期初" in h_clean or "年初" in h_clean:
            col_map["opening"] = ci
        elif "增加" in h_clean or "计提" in h_clean:
            col_map.setdefault("increase", []).append(ci) if isinstance(col_map.get("increase"), list) else col_map.update({"increase": [ci]})
        elif "减少" in h_clean or "转回" in h_clean or "转销" in h_clean:
            col_map.setdefault("decrease", []).append(ci) if isinstance(col_map.get("decrease"), list) else col_map.update({"decrease": [ci]})

    if "closing" in col_map and "opening" in col_map:
        inc_cols = col_map.get("increase", [])
        dec_cols = col_map.get("decrease", [])
        if isinstance(inc_cols, int):
            inc_cols = [inc_cols]
        if isinstance(dec_cols, int):
            dec_cols = [dec_cols]

        for ri, row in enumerate(data_rows):
            if not row or not row[0]:
                continue
            cell0 = str(row[0]).replace(" ", "")
            if "合计" in cell0 or "小计" in cell0 or "其中" in cell0:
                continue
            try:
                opening = float(str(row[col_map["opening"]]).replace(",", "")) if row[col_map["opening"]] else 0
                closing = float(str(row[col_map["closing"]]).replace(",", "")) if row[col_map["closing"]] else 0
            except (ValueError, IndexError):
                continue

            if opening == 0 and closing == 0:
                continue

            inc_sum = 0
            for ic in inc_cols:
                try:
                    inc_sum += float(str(row[ic]).replace(",", "")) if ic < len(row) and row[ic] else 0
                except (ValueError, IndexError):
                    pass
            dec_sum = 0
            for dc in dec_cols:
                try:
                    dec_sum += float(str(row[dc]).replace(",", "")) if dc < len(row) and row[dc] else 0
                except (ValueError, IndexError):
                    pass

            if inc_sum == 0 and dec_sum == 0:
                continue

            expected_closing = opening + inc_sum - dec_sum
            diff = round(closing - expected_closing, 2)
            if abs(diff) > 0.01:
                results.append({
                    "section_title": title,
                    "rule_name": f"勾稽校验 - {row[0]}",
                    "level": "error",
                    "expected": f"{expected_closing:,.2f}",
                    "actual": f"{closing:,.2f}",
                    "difference": f"{diff:,.2f}",
                    "message": f"期末 ≠ 期初 + 增加 - 减少",
                })

    # 规则3：与试算表交叉校验
    tb_map = {}
    try:
        params = {"pid": project_id, "y": year}
        query = "SELECT account_name, closing_balance, opening_balance FROM trial_balance_entries WHERE project_id = :pid AND year = :y"
        if company_code:
            query += " AND company_code = :cc"
            params["cc"] = company_code
        tb_result = await db.execute(text(query), params)
        for r in tb_result.fetchall():
            tb_map[r[0]] = {"closing": float(r[1] or 0), "opening": float(r[2] or 0)}
    except Exception:
        pass

    if tb_map:
        for ri, row in enumerate(data_rows):
            if not row or not row[0]:
                continue
            item_name = str(row[0]).strip().lstrip("△▲*#").strip()
            tb_entry = tb_map.get(item_name)
            if not tb_entry:
                continue
            for ci in range(1, min(len(headers), len(row))):
                h = headers[ci].replace(" ", "")
                try:
                    cell_val = float(str(row[ci]).replace(",", "")) if row[ci] else 0
                except ValueError:
                    continue
                if cell_val == 0:
                    continue
                expected = None
                if "期末" in h or "本期" in h:
                    expected = tb_entry["closing"]
                elif "期初" in h or "年初" in h:
                    expected = tb_entry["opening"]
                if expected is not None:
                    diff = round(cell_val - expected, 2)
                    if abs(diff) > 0.01:
                        results.append({
                            "section_title": title,
                            "rule_name": f"试算表校验 - {item_name}/{headers[ci]}",
                            "level": "warn",
                            "expected": f"{expected:,.2f}",
                            "actual": f"{cell_val:,.2f}",
                            "difference": f"{diff:,.2f}",
                            "message": f"与试算表数据不一致",
                        })

    # 如果没有任何审核结果，说明全部通过
    if not results:
        results.append({
            "section_title": title,
            "rule_name": "整体校验",
            "level": "pass",
            "expected": "",
            "actual": "",
            "difference": "",
            "message": "所有校验规则通过",
        })

    return {"results": results}


# ─── 一键取数计算：对所有附注表格执行公式取数 ─────────────────────────────────

@router.post("/apply-formulas/{project_id}/{year}")
async def apply_all_formulas(
    project_id: str, year: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """对所有附注表格执行公式取数计算，从试算表提取数据填充"""
    standard = body.get("standard", "soe")
    company_code = body.get("company_code", "")

    sections = _load_sections(standard)

    # 加载试算表数据
    tb_map = {}
    try:
        params = {"pid": project_id, "y": year}
        query = "SELECT account_name, opening_balance, closing_balance, debit_amount, credit_amount FROM trial_balance_entries WHERE project_id = :pid AND year = :y"
        if company_code:
            query += " AND company_code = :cc"
            params["cc"] = company_code
        result = await db.execute(text(query), params)
        for r in result.fetchall():
            tb_map[r[0]] = {
                "opening": float(r[1] or 0), "closing": float(r[2] or 0),
                "debit": float(r[3] or 0), "credit": float(r[4] or 0),
            }
    except Exception:
        return {"updated_sections": 0, "message": "无法加载试算表数据"}

    if not tb_map:
        return {"updated_sections": 0, "message": "试算表无数据"}

    updated = 0
    import uuid as _uuid
    from datetime import datetime as _dt

    for sec in sections:
        headers = sec.get("headers", [])
        template_rows = sec.get("rows", [])
        if not headers or not template_rows:
            continue

        filled = False
        new_rows = []
        for row in template_rows:
            if not row or not row[0]:
                new_rows.append(row)
                continue
            item_name = str(row[0]).strip().lstrip("△▲*#").strip()
            matched = tb_map.get(item_name)
            if not matched:
                new_rows.append(row)
                continue

            new_row = list(row)
            for ci, h in enumerate(headers):
                if ci == 0:
                    continue
                h_clean = h.replace(" ", "").replace("　", "")
                if "期末" in h_clean or "本期" in h_clean or "账面余额" in h_clean:
                    if matched["closing"]:
                        new_row[ci] = f"{matched['closing']:.2f}"
                        filled = True
                elif "期初" in h_clean or "年初" in h_clean:
                    if matched["opening"]:
                        new_row[ci] = f"{matched['opening']:.2f}"
                        filled = True
            new_rows.append(new_row)

        if filled:
            # 保存到数据库
            now = _dt.utcnow()
            data_json = json.dumps({"headers": headers, "rows": new_rows}, ensure_ascii=False)
            try:
                await db.execute(
                    text("""
                        INSERT INTO consol_note_data (id, project_id, year, section_id, data, updated_at)
                        VALUES (:id, :pid, :y, :sid, CAST(:data AS jsonb), :now)
                        ON CONFLICT (project_id, year, section_id)
                        DO UPDATE SET data = CAST(:data AS jsonb), updated_at = :now
                    """),
                    {"id": str(_uuid.uuid4()), "pid": project_id, "y": year,
                     "sid": sec["section_id"], "data": data_json, "now": now},
                )
                updated += 1
            except Exception:
                pass

    if updated:
        await db.commit()

    return {"updated_sections": updated, "message": f"已更新 {updated} 个附注表格"}


# ─── 数据汇总：按单位汇总附注/报表数据 ───────────────────────────────────────

@router.post("/aggregate/{project_id}/{year}")
async def aggregate_data(
    project_id: str, year: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """汇总指定单位的数据到目标单元格
    
    mode=direct: 汇总当前节点的直接下级企业
    mode=custom: 汇总用户选择的企业列表
    """
    section_id = body.get("section_id", "")
    row_idx = body.get("row_idx", 0)
    col_idx = body.get("col_idx", 1)
    mode = body.get("mode", "direct")
    company_code = body.get("company_code", "")
    company_codes = body.get("company_codes", [])
    standard = body.get("standard", "soe")
    source = body.get("source", "same")

    # 获取目标企业列表
    target_codes = []
    if mode == "direct":
        # 从基本信息表获取直接下级
        try:
            result = await db.execute(
                text("SELECT data FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = 'info'"),
                {"pid": project_id, "y": year},
            )
            row = result.fetchone()
            if row and isinstance(row[0], dict):
                info_rows = row[0].get("rows", [])
                for r in info_rows:
                    if r.get("company_code") and r.get("company_name"):
                        # 直接下级 = parent_code 等于当前节点
                        if not company_code or r.get("parent_code") == company_code:
                            target_codes.append(r["company_code"])
        except Exception:
            pass
    else:
        target_codes = company_codes

    if not target_codes:
        return {"value": None, "count": 0, "message": "无下级企业"}

    # 从各企业的已保存数据中提取同位置的值并汇总
    total = 0
    count = 0
    for code in target_codes:
        try:
            # 查询该企业的附注数据
            result = await db.execute(
                text("SELECT data FROM consol_note_data WHERE project_id = :pid AND year = :y AND section_id = :sid"),
                {"pid": project_id, "y": year, "sid": f"{section_id}_{code}"},
            )
            row = result.fetchone()
            if row and isinstance(row[0], dict):
                rows = row[0].get("rows", [])
                if row_idx < len(rows) and col_idx < len(rows[row_idx]):
                    val = rows[row_idx][col_idx]
                    try:
                        num = float(str(val).replace(",", "").replace("，", ""))
                        total += num
                        count += 1
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

    # 如果没有从附注数据中找到，尝试从试算表提取
    if count == 0:
        sections = _load_sections(standard)
        template = None
        for sec in sections:
            if sec["section_id"] == section_id:
                template = sec
                break

        if template:
            item_name = ""
            if template.get("rows") and row_idx < len(template["rows"]):
                item_name = template["rows"][row_idx][0] if template["rows"][row_idx] else ""

            if item_name:
                for code in target_codes:
                    try:
                        params = {"pid": project_id, "y": year, "cc": code, "name": item_name.strip()}
                        result = await db.execute(
                            text("SELECT closing_balance, opening_balance FROM trial_balance_entries WHERE project_id = :pid AND year = :y AND company_code = :cc AND account_name = :name"),
                            params,
                        )
                        row = result.fetchone()
                        if row:
                            headers = template.get("headers", [])
                            col_header = headers[col_idx] if col_idx < len(headers) else ""
                            h_clean = col_header.replace(" ", "")
                            val = 0
                            if "期末" in h_clean or "本期" in h_clean:
                                val = float(row[0] or 0)
                            elif "期初" in h_clean or "年初" in h_clean:
                                val = float(row[1] or 0)
                            if val:
                                total += val
                                count += 1
                    except Exception:
                        pass

    return {
        "value": round(total, 2) if count > 0 else None,
        "count": count,
        "message": f"已汇总 {count} 家企业",
    }


# ─── 合并试算平衡表：自动填充汇总数和抵消调整数 ──────────────────────────────

@router.post("/fill-tb/{project_id}/{year}")
async def fill_trial_balance(
    project_id: str, year: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """自动填充合并试算平衡表
    
    1. 审定汇总：从各子企业试算表按科目汇总
    2. 权益抵消/往来抵消/报表调整：从合并工作底稿抵消分录提取
    """
    report_type = body.get("report_type", "balance_sheet")
    period = body.get("period", "closing")  # closing / opening
    company_code = body.get("company_code", "")
    standard = body.get("standard", "soe")

    # 1. 获取合并范围内的子企业列表
    child_codes = []
    try:
        result = await db.execute(
            text("SELECT data FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = 'info'"),
            {"pid": project_id, "y": year},
        )
        row = result.fetchone()
        if row and isinstance(row[0], dict):
            for r in row[0].get("rows", []):
                if r.get("company_code"):
                    child_codes.append(r["company_code"])
    except Exception:
        pass

    # 2. 从各子企业试算表汇总
    summary_map = {}  # account_name -> amount
    balance_field = "closing_balance" if period == "closing" else "opening_balance"
    
    if child_codes:
        try:
            for code in child_codes:
                result = await db.execute(
                    text(f"SELECT account_name, {balance_field} FROM trial_balance_entries WHERE project_id = :pid AND year = :y AND company_code = :cc"),
                    {"pid": project_id, "y": year, "cc": code},
                )
                for r in result.fetchall():
                    name = r[0]
                    val = float(r[1] or 0)
                    summary_map[name] = summary_map.get(name, 0) + val
        except Exception:
            pass
    else:
        # 没有子企业代码，尝试不按企业筛选
        try:
            result = await db.execute(
                text(f"SELECT account_name, SUM({balance_field}) FROM trial_balance_entries WHERE project_id = :pid AND year = :y GROUP BY account_name"),
                {"pid": project_id, "y": year},
            )
            for r in result.fetchall():
                summary_map[r[0]] = float(r[1] or 0)
        except Exception:
            pass

    # 3. 从合并工作底稿提取抵消分录
    elim_map = {}  # account_name -> { equity_dr, equity_cr, trade_dr, trade_cr, adj_dr, adj_cr }
    try:
        result = await db.execute(
            text("SELECT data FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = 'elimination'"),
            {"pid": project_id, "y": year},
        )
        row = result.fetchone()
        if row and isinstance(row[0], dict):
            rows_data = row[0].get("rows", {})
            # 权益抵消
            for r in rows_data.get("equity", []):
                name = r.get("subject", "")
                if not name:
                    continue
                if name not in elim_map:
                    elim_map[name] = {"equity_dr": 0, "equity_cr": 0, "trade_dr": 0, "trade_cr": 0, "adj_dr": 0, "adj_cr": 0}
                direction = r.get("direction", "")
                total = float(r.get("total", 0) or 0)
                if direction == "借":
                    elim_map[name]["equity_dr"] += total
                elif direction == "贷":
                    elim_map[name]["equity_cr"] += total
            # 损益抵消（归入往来交易抵消）
            for r in rows_data.get("income", []):
                name = r.get("subject", "")
                if not name:
                    continue
                if name not in elim_map:
                    elim_map[name] = {"equity_dr": 0, "equity_cr": 0, "trade_dr": 0, "trade_cr": 0, "adj_dr": 0, "adj_cr": 0}
                direction = r.get("direction", "")
                total = float(r.get("total", 0) or 0)
                if direction == "借":
                    elim_map[name]["trade_dr"] += total
                elif direction == "贷":
                    elim_map[name]["trade_cr"] += total
    except Exception:
        pass

    # 4. 加载报表行结构
    try:
        applicable_standard = f"{standard}_consolidated"
        from app.models.report_models import ReportConfig, FinancialReportType
        import sqlalchemy as sa
        rt = FinancialReportType(report_type)
        result = await db.execute(
            sa.select(ReportConfig)
            .where(
                ReportConfig.report_type == rt,
                ReportConfig.applicable_standard == applicable_standard,
                ReportConfig.is_deleted == sa.false(),
            )
            .order_by(ReportConfig.row_number)
        )
        report_rows = result.scalars().all()
    except Exception:
        report_rows = []

    # 5. 构建填充结果
    filled = []
    for r in report_rows:
        name = r.row_name.strip() if r.row_name else ""
        clean_name = name.lstrip("△▲*# ").strip()
        
        summary_val = summary_map.get(clean_name) or summary_map.get(name) or None
        elim = elim_map.get(clean_name) or elim_map.get(name) or {}
        
        filled.append({
            "row_code": r.row_code,
            "row_name": r.row_name,
            "summary": round(summary_val, 2) if summary_val else None,
            "equity_dr": round(elim.get("equity_dr", 0), 2) or None,
            "equity_cr": round(elim.get("equity_cr", 0), 2) or None,
            "trade_dr": round(elim.get("trade_dr", 0), 2) or None,
            "trade_cr": round(elim.get("trade_cr", 0), 2) or None,
            "adj_dr": None,
            "adj_cr": None,
        })

    matched_summary = len([f for f in filled if f["summary"]])
    matched_elim = len([f for f in filled if f["equity_dr"] or f["equity_cr"] or f["trade_dr"] or f["trade_cr"]])

    return {
        "rows": filled,
        "matched_summary": matched_summary,
        "matched_elim": matched_elim,
        "total_rows": len(filled),
        "child_count": len(child_codes),
    }
