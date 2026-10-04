"""合并附注章节 API — 从种子数据或 JSON 文件加载附注模板章节和表格结构

GET /api/consol-note-sections/{standard}              — 获取所有章节（树形）
GET /api/consol-note-sections/{standard}/{section_id} — 获取单个章节详情（含表格）
PUT /api/consol-note-sections/{project_id}/{year}/{section_id} — 保存用户编辑的附注数据
GET /api/consol-note-sections/{project_id}/{year}/{section_id}/data — 加载用户已保存的附注数据
"""

import json
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, require_project_access
from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import User

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


# ─── 附注差额与「按公式填入」（spec consol-elimination-single-source-push 任务 7）──────────────
# 固定前缀路径（breakdown / fill-by-formula）声明在 ``/{standard}/{section_id}`` 之前，免得被当成模板名。


def _note_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc))


@router.get("/breakdown/{project_id}/{year}/{section_id}")
async def get_note_breakdown(
    project_id: UUID, year: int, section_id: str,
    node_key: str | None = Query(None, description="汇总节点；默认根合并节点"),
    standard: str | None = Query(None, description="附注模板（soe / listed）；不传按项目口径"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """有公式的单元格：个别数汇总 / 调整 / 抵销 / 合并数，及所选汇总节点各直接子节点贡献（需求 6.3）。"""
    from app.services.consol_note_formula_service import NoteFormulaError, note_breakdown
    from app.services.consol_note_scope import (
        NoteScopeError,
        load_note_request_context,
    )

    try:
        ctx = await load_note_request_context(db, project_id, year, node_key=node_key)
        result = await note_breakdown(
            db, project_id, year, section_id, node_key=node_key, standard=standard, request_ctx=ctx,
        )
    except (NoteFormulaError, NoteScopeError) as e:
        await db.rollback()
        raise _note_error(e) from e
    await db.commit()  # 只可能写了按需种子（模板级派生配置），不写项目数据
    return result


@router.post("/fill-by-formula/{project_id}/{year}/{section_id}")
async def fill_note_by_formula(
    project_id: UUID, year: int, section_id: str,
    node_key: str | None = Query(None, description="企业树节点；根节点允许读取历史兼容行但写入节点专属行"),
    standard: str | None = Query(None, description="附注模板（soe / listed）；不传按项目口径"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """把合并数写入该章节已保存数据；手工单元格（``data.manual_cells``）保留并列出；清除待更新标记（需求 6.4）。"""
    from app.services.consol_note_formula_service import NoteFormulaError, fill_by_formula
    from app.services.consol_note_scope import (
        NoteScopeError,
        load_note_request_context,
    )

    try:
        ctx = await load_note_request_context(db, project_id, year, node_key=node_key)
        result = await fill_by_formula(
            db, project_id, year, section_id, node_key=node_key, standard=standard, request_ctx=ctx,
        )
    except (NoteFormulaError, NoteScopeError) as e:
        await db.rollback()
        raise _note_error(e) from e
    await db.commit()
    return result


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


# ─── 用户数据存储（按项目+年度+章节+节点） ───────────────────────────────────


def _node_filter(node_key: str | None) -> sa.ColumnElement[bool]:
    """旧请求读写项目级 NULL 行；带节点键时严格匹配节点行。"""
    return ConsolNoteData.node_key.is_(None) if node_key is None else ConsolNoteData.node_key == node_key


def _requested_node_key(query_node_key: str | None, body: dict | None = None) -> str | None:
    """统一兼容旧 body 调用和新 query 参数调用。显式 query 参数优先。

    单一真源：委托 ``consol_note_scope.requested_node_key``（空字符串按无效输入保留，由作用域解析拒绝）。
    """
    from app.services.consol_note_scope import requested_node_key

    return requested_node_key(query_node_key, body)


async def _note_request_context(
    db: AsyncSession, project_id: UUID, year: int | None, node_key: str | None,
):
    """为 refresh / audit / audit-all / apply-formulas / aggregate 装载一次共享请求上下文（§四）。

    - 显式 node_key：经企业树精确校验并装载合并视图上下文；非法键 / 无效年度 / 非合并项目
      以 ``NoteScopeError`` 抛出（路由转 400 / 404，§四「请求级上下文失败用明确 HTTP 错误」）。
    - 省略 node_key（旧项目级兼容调用）：合并上下文装载不成立时返回 ``None``，端点维持旧 NULL 兼容行为，
      不把旧调用强行升级成合并节点请求（ADR-CNSC-002）。

    返回的 ``NoteRequestContext`` 内 scope / view / node_measures 供同一请求各处复用，不再重复建树取数。
    """
    from app.services.consol_note_scope import (
        NoteScopeError,
        load_note_request_context,
    )

    try:
        return await load_note_request_context(db, project_id, year, node_key=node_key)
    except NoteScopeError:
        if node_key:
            raise  # 显式节点键无效 ⇒ 明确报错，不降级
        return None  # 旧项目级兼容调用：没有合并上下文也放行既有逻辑


async def _is_root_consol_node(
    db: AsyncSession, project_id: UUID, node_key: str | None,
) -> bool:
    """经**企业树**判定 node_key 是否为树根合并节点（ADR-CNSC-001：禁 ``:consol`` 后缀兜底）。"""
    if not node_key:
        return False
    from app.services.consol_note_formula_service import _is_tree_root_consol

    return await _is_tree_root_consol(db, project_id, node_key)


async def _load_saved_note_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    node_key: str | None,
) -> dict[str, dict]:
    """批量读取指定节点的附注数据；根节点逐章节优先专属行、再回退 legacy 行。"""
    # str(UUID)：text() 裸 SQL 在 SQLite 上无法绑定 UUID 对象；PG 对参数化比较会把 text 转 uuid。
    params: dict[str, object] = {"pid": str(project_id), "y": year}
    if node_key is None:
        node_clause = "node_key IS NULL"
    else:
        params["nk"] = node_key
        node_clause = "node_key = :nk"
        if await _is_root_consol_node(db, project_id, node_key):
            node_clause = "(node_key = :nk OR node_key IS NULL)"

    result = await db.execute(text(
        "SELECT section_id, data, node_key "
        "FROM consol_note_data "
        "WHERE project_id = :pid AND year = :y AND " + node_clause
    ), params)
    saved: dict[str, dict] = {}
    for row in result.fetchall():
        section_id, data, row_node_key = row
        if row_node_key == node_key or section_id not in saved:
            saved[section_id] = data if isinstance(data, dict) else {}
    return saved


async def _load_note_data_for_company(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
    company_code: str,
    *,
    node_key: str | None = None,
) -> dict | None:
    """读取企业附注数据，优先使用共享 section_id + node_key，兼容旧后缀键。"""
    params: dict[str, object] = {
        "pid": str(project_id),
        "y": year,
        "sid": section_id,
        "legacy_sid": f"{section_id}_{company_code}",
        "source_nk": node_key or f"{company_code}:consol",
    }
    result = await db.execute(text(
        "SELECT section_id, data, node_key "
        "FROM consol_note_data "
        "WHERE project_id = :pid AND year = :y "
        "AND ((section_id = :sid AND node_key = :source_nk) "
        "OR (section_id = :legacy_sid AND node_key IS NULL))"
    ), params)
    rows = result.fetchall()
    for row in rows:
        if row[0] == section_id and row[2] == params["source_nk"]:
            return row[1] if isinstance(row[1], dict) else {}
    for row in rows:
        if row[0] == params["legacy_sid"] and row[2] is None:
            return row[1] if isinstance(row[1], dict) else {}
    return None


# ─── 试算表取数（唯一真源：只读真实 ORM/schema 列，不吞异常）────────────────────────
#
# `trial_balance` 真实列见 ``app.models.audit_platform_models.TrialBalance``：
#   standard_account_code / account_name / unadjusted_amount / audited_amount /
#   opening_balance / aje_adjustment / rje_adjustment / wp_adjustment / is_deleted。
# 既不存在 ``account_code`` / ``closing_balance`` / ``debit_amount`` / ``credit_amount``。
# 列语义口径与 ``amount_resolver._COLUMN_MAP`` / ``report_engine`` 一致：
#   期末/本期/账面余额 → audited_amount（审定数）；期初/年初 → opening_balance；
#   本期发生额 → audited_amount - opening_balance。
# 附注表无「借方发生额/贷方发生额」真实来源，故不再伪造 debit/credit 列。


async def _load_tb_account_map(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    company_code: str,
) -> dict[str, dict[str, float]]:
    """按科目名返回试算表审定口径金额映射；只引用真实列并过滤软删行。

    返回 ``{account_name: {"closing": 审定数, "opening": 期初, "period": 本期发生额}}``。
    DB 层异常**不吞**：由调用端点转为明确 HTTP 错误（§四、需求 2.3）。
    """
    # 走 ORM select：标准列映射 + 跨方言 UUID 绑定（text() 裸 SQL 在 SQLite 上无法绑定 UUID）。
    from app.models.audit_platform_models import TrialBalance

    stmt = sa.select(
        TrialBalance.account_name,
        TrialBalance.audited_amount,
        TrialBalance.opening_balance,
    ).where(
        TrialBalance.project_id == project_id,
        TrialBalance.year == year,
        sa.or_(TrialBalance.is_deleted.is_(False), TrialBalance.is_deleted.is_(None)),
    )
    if company_code:
        stmt = stmt.where(TrialBalance.company_code == company_code)
    result = await db.execute(stmt)
    tb_map: dict[str, dict[str, float]] = {}
    for name, audited, opening in result.all():
        if name is None:
            continue
        closing = float(audited or 0)
        opening_val = float(opening or 0)
        tb_map[name] = {
            "closing": closing,
            "opening": opening_val,
            "period": closing - opening_val,
        }
    return tb_map


async def _load_note_record(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
    node_key: str | None,
) -> ConsolNoteData | None:
    """加载附注数据；**经企业树验证的**根合并节点允许从 NULL legacy 行读取，但不改变其写入归属。

    单一真源：委托 ``consol_note_formula_service._note_data_record``（根判定经树验证，ADR-CNSC-001）。
    """
    from app.services.consol_note_formula_service import _note_data_record

    return await _note_data_record(
        db, project_id, year, section_id, node_key=node_key,
    )


async def _save_note_record(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
    node_key: str | None,
    data: dict,
    now,
) -> ConsolNoteData:
    """按节点 upsert；不使用旧项目级 ON CONFLICT，兼容 V177 两个部分唯一索引。"""
    target = await _load_note_record(db, project_id, year, section_id, node_key)
    # 根节点回退到 legacy 只用于展示；带 node_key 的保存必须创建专属行。
    if target is not None and node_key is not None and target.node_key != node_key:
        target = None
    if target is None:
        target = ConsolNoteData(
            project_id=project_id,
            year=year,
            section_id=section_id,
            node_key=node_key,
            data=data,
            updated_at=now,
        )
        db.add(target)
    else:
        target.data = data
        target.updated_at = now
    return target


@router.get("/data/{project_id}/{year}/{section_id}")
async def get_note_data(
    project_id: UUID, year: int, section_id: str,
    node_key: str | None = Query(None, description="企业树节点；不传读取项目级兼容行"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """加载用户已保存的附注数据。根节点无专属行时兼容读取历史项目级行。"""
    record = await _load_note_record(db, project_id, year, section_id, node_key)
    if record is None:
        return {"content": {}, "updated_at": None, "node_key": node_key}
    return {
        "content": record.data if isinstance(record.data, dict) else {},
        "updated_at": str(record.updated_at) if record.updated_at else None,
        "node_key": record.node_key or node_key,
    }


@router.put("/data/{project_id}/{year}/{section_id}")
async def save_note_data(
    project_id: UUID, year: int, section_id: str,
    body: dict,
    node_key: str | None = Query(None, description="企业树节点；不传保存项目级兼容行"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """保存用户编辑的附注数据，带节点键时只写节点专属行。"""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    try:
        await _save_note_record(db, project_id, year, section_id, node_key, body.get("data", {}), now)
        await db.commit()
        return {"ok": True, "updated_at": str(now), "node_key": node_key}
    except Exception as e:
        await db.rollback()
        return {"ok": False, "error": str(e), "node_key": node_key}


# ─── 公式刷新：根据项目数据重新计算附注表格 ──────────────────────────────────

@router.post("/refresh/{project_id}/{year}/{section_id}")
async def refresh_note_by_formula(
    project_id: UUID, year: int, section_id: str,
    body: dict,
    node_key: str | None = Query(None, description="企业树节点；根节点按 node_key 读取对应企业试算表"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """根据公式从项目试算表/报表数据重新计算附注表格内容
    
    逻辑：
    1. 加载该章节的模板结构（headers + 模板行）
    2. 查找该章节关联的公式规则
    3. 从项目试算表/报表中提取对应科目数据
    4. 按公式计算填充每行每列
    """
    from app.services.consol_note_scope import NoteScopeError

    standard = body.get("standard", "soe")
    company_code = body.get("company_code", "")
    node_key = _requested_node_key(node_key, body)
    # 节点身份经共享请求上下文（企业树）校验，并复用其视图上下文（§四）；company_code 从验证过的树节点取，
    # 不再用 node_key.split(':') 裸推导。请求级上下文失败按明确错误返回（§四，不吞异常）。
    try:
        request_ctx = await _note_request_context(db, project_id, year, node_key)
    except NoteScopeError as e:
        raise _note_error(e) from e
    if request_ctx is not None and node_key and not company_code:
        company_code = request_ctx.find_node().company_code

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

    # 从试算表提取数据：只读真实列，取数失败明确报错（需求 2.3，不吞异常回传模板值）
    try:
        tb_map = await _load_tb_account_map(db, project_id, year, company_code)
    except Exception as e:  # noqa: BLE001  — 转为明确 HTTP 错误，不静默回传模板
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"试算表取数失败: {e}") from e

    if not tb_map:
        return {"rows": template_rows, "message": "试算表无数据"}

    # 按模板行匹配科目名称填充数据
    filled_rows = []
    matched_count = 0
    for row in template_rows:
        if not row:
            filled_rows.append(row)
            continue
        item_name = row[0] if row else ""
        clean_name = item_name.strip().lstrip("△▲*#").strip()

        matched = tb_map.get(clean_name) or tb_map.get(item_name.strip())

        # 精确匹配失败 → 查科目-附注映射表（该查询失败亦明确报错，不吞）
        if not matched:
            map_result = await db.execute(
                text(
                    "SELECT account_name, mapping_type FROM account_note_mapping "
                    "WHERE project_id = :pid AND section_id = :sid AND row_name = :rn LIMIT 1"
                ),
                {"pid": str(project_id), "sid": section_id, "rn": clean_name},
            )
            map_row = map_result.fetchone()
            if map_row:
                matched = tb_map.get(map_row[0])

        # 映射表也没有 → 模糊匹配（包含关系）
        if not matched and len(clean_name) >= 2:
            for acc_name, acc_data in tb_map.items():
                if clean_name in acc_name or acc_name in clean_name:
                    matched = acc_data
                    break

        if matched:
            new_row = list(row)
            for ci, h in enumerate(headers):
                if ci == 0:
                    continue  # 项目名列不填
                h_lower = h.replace(" ", "").replace("　", "")
                if "期末" in h_lower or "本期" in h_lower or "账面余额" in h_lower:
                    new_row[ci] = str(matched["closing"]) if matched["closing"] else ""
                elif "期初" in h_lower or "年初" in h_lower:
                    new_row[ci] = str(matched["opening"]) if matched["opening"] else ""
                elif "本期发生" in h_lower or "发生额" in h_lower:
                    new_row[ci] = str(matched["period"]) if matched["period"] else ""
            filled_rows.append(new_row)
            matched_count += 1
        else:
            filled_rows.append(row)

    return {"rows": filled_rows, "message": f"已从试算表匹配 {matched_count} 行"}


# ─── 全审：对所有附注表格执行公式审核 ─────────────────────────────────────────

@router.post("/audit-all/{project_id}/{year}")
async def audit_all_notes(
    project_id: UUID, year: int,
    body: dict,
    node_key: str | None = Query(None, description="企业树节点；不传读取项目级兼容行"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """对所有附注表格执行公式审核
    
    审核规则：
    1. 合计行校验：合计行 = 明细行之和
    2. 期末 = 期初 + 增加 - 减少（如适用）
    3. 借贷平衡校验
    4. 与试算表数据交叉校验
    """
    from app.services.consol_note_scope import NoteScopeError

    standard = body.get("standard", "soe")
    company_code = body.get("company_code", "")
    node_key = _requested_node_key(node_key, body)
    # 节点身份经共享请求上下文（企业树）校验并复用（§四）；company_code 取自验证过的树节点。
    try:
        request_ctx = await _note_request_context(db, project_id, year, node_key)
    except NoteScopeError as e:
        raise _note_error(e) from e
    if request_ctx is not None and node_key and not company_code:
        company_code = request_ctx.find_node().company_code
    
    sections = _load_sections(standard)
    results = []

    # 加载用户已保存的数据；带节点键时严格隔离，根合并节点允许兼容读取 legacy 行。
    # 读取失败明确报错（需求 2.3），不吞异常后对空数据伪造「全部通过」。
    try:
        saved_data = await _load_saved_note_data(db, project_id, year, node_key)
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"附注数据读取失败: {e}") from e

    # 加载试算表数据用于交叉校验（只读真实列，取数失败明确报错）
    try:
        tb_map = await _load_tb_account_map(db, project_id, year, company_code)
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"试算表取数失败: {e}") from e

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
    project_id: UUID, year: int, section_id: str,
    body: dict,
    node_key: str | None = Query(None, description="企业树节点；不传读取项目级兼容行"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """对指定附注表格执行公式审核（前端传入当前编辑的数据）"""
    from app.services.consol_note_scope import NoteScopeError

    standard = body.get("standard", "soe")
    company_code = body.get("company_code", "")
    node_key = _requested_node_key(node_key, body)
    # 节点身份经共享请求上下文（企业树）校验并复用（§四）；company_code 取自验证过的树节点。
    try:
        request_ctx = await _note_request_context(db, project_id, year, node_key)
    except NoteScopeError as e:
        raise _note_error(e) from e
    if request_ctx is not None and node_key and not company_code:
        company_code = request_ctx.find_node().company_code
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

    # 规则3：与试算表交叉校验（只读真实列，取数失败明确报错，不吞异常）
    try:
        tb_map = await _load_tb_account_map(db, project_id, year, company_code)
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"试算表取数失败: {e}") from e

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
    project_id: UUID, year: int,
    body: dict,
    node_key: str | None = Query(None, description="企业树节点；不传写入项目级兼容行"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """对所有附注表格执行公式取数计算，从试算表提取数据填充"""
    from app.services.consol_note_scope import NoteScopeError

    standard = body.get("standard", "soe")
    company_code = body.get("company_code", "")
    node_key = _requested_node_key(node_key, body)
    # 节点身份经共享请求上下文（企业树）校验并复用（§四）；company_code 取自验证过的树节点。
    try:
        request_ctx = await _note_request_context(db, project_id, year, node_key)
    except NoteScopeError as e:
        raise _note_error(e) from e
    if request_ctx is not None and node_key and not company_code:
        company_code = request_ctx.find_node().company_code

    sections = _load_sections(standard)

    # 加载试算表数据：只读真实列，取数失败明确报错（需求 2.3，不吞异常伪造 0/成功）
    try:
        tb_map = await _load_tb_account_map(db, project_id, year, company_code)
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"试算表取数失败: {e}") from e

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
            now = _dt.utcnow()
            data = {"headers": headers, "rows": new_rows}
            try:
                await _save_note_record(
                    db, project_id, year, sec["section_id"], node_key, data, now,
                )
                updated += 1
            except Exception:
                await db.rollback()

    if updated:
        await db.commit()

    return {"updated_sections": updated, "message": f"已更新 {updated} 个附注表格"}


# ─── 数据汇总：按单位汇总附注/报表数据 ───────────────────────────────────────

@router.post("/aggregate/{project_id}/{year}")
async def aggregate_data(
    project_id: UUID, year: int,
    body: dict,
    node_key: str | None = Query(None, description="当前汇总节点；不传保持旧 company_code 语义"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
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
    node_key = _requested_node_key(node_key, body)
    # 节点身份经共享请求上下文（企业树）校验并复用（§四）；company_code 取自验证过的树节点。
    from app.services.consol_note_scope import NoteScopeError

    try:
        request_ctx = await _note_request_context(db, project_id, year, node_key)
    except NoteScopeError as e:
        raise _note_error(e) from e
    if request_ctx is not None and node_key and not company_code:
        company_code = request_ctx.find_node().company_code

    # 获取目标企业列表
    target_codes = []
    if mode == "direct":
        # 从基本信息表获取直接下级；读取失败明确报错（需求 2.3，不吞异常伪造「无下级」）
        try:
            result = await db.execute(
                text("SELECT data FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = 'info'"),
                {"pid": str(project_id), "y": year},
            )
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"基本信息表读取失败: {e}") from e
        row = result.fetchone()
        if row and isinstance(row[0], dict):
            info_rows = row[0].get("rows", [])
            for r in info_rows:
                if r.get("company_code") and r.get("company_name"):
                    # 直接下级 = parent_code 等于当前节点
                    if not company_code or r.get("parent_code") == company_code:
                        target_codes.append(r["company_code"])
    else:
        target_codes = company_codes

    if not target_codes:
        return {"value": None, "count": 0, "message": "无下级企业"}

    # 从各企业的已保存数据中提取同位置的值并汇总
    total = 0
    count = 0
    for code in target_codes:
        try:
            # 查询该企业的附注数据：新数据使用共享 section_id + node_key，旧数据兼容后缀 section_id
            data = await _load_note_data_for_company(
                db, project_id, year, section_id, code,
                node_key=f"{code}:consol" if node_key is None else f"{code}:consol",
            )
            if isinstance(data, dict):
                rows = data.get("rows", [])
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
                headers = template.get("headers", [])
                col_header = headers[col_idx] if col_idx < len(headers) else ""
                h_clean = col_header.replace(" ", "")
                # 只读真实列：期末/本期 → 审定数（audited_amount）；期初/年初 → opening_balance。
                # 取数失败明确报错（需求 2.3），不吞异常伪造 0。
                from app.models.audit_platform_models import TrialBalance

                try:
                    for code in target_codes:
                        stmt = sa.select(
                            TrialBalance.audited_amount,
                            TrialBalance.opening_balance,
                        ).where(
                            TrialBalance.project_id == project_id,
                            TrialBalance.year == year,
                            TrialBalance.company_code == code,
                            TrialBalance.account_name == item_name.strip(),
                            sa.or_(
                                TrialBalance.is_deleted.is_(False),
                                TrialBalance.is_deleted.is_(None),
                            ),
                        )
                        row = (await db.execute(stmt)).first()
                        if not row:
                            continue
                        val = 0.0
                        if "期末" in h_clean or "本期" in h_clean:
                            val = float(row[0] or 0)
                        elif "期初" in h_clean or "年初" in h_clean:
                            val = float(row[1] or 0)
                        if val:
                            total += val
                            count += 1
                except Exception as e:  # noqa: BLE001
                    await db.rollback()
                    raise HTTPException(
                        status_code=500, detail=f"试算表取数失败: {e}"
                    ) from e

    return {
        "value": round(total, 2) if count > 0 else None,
        "count": count,
        "message": f"已汇总 {count} 家企业",
    }
