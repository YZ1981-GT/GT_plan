"""合并附注章节 API — 从种子数据或 JSON 文件加载附注模板章节和表格结构

GET /api/consol-note-sections/{standard}              — 获取所有章节（树形）
GET /api/consol-note-sections/{standard}/{section_id} — 获取单个章节详情（含表格）
PUT /api/consol-note-sections/{project_id}/{year}/{section_id} — 保存用户编辑的附注数据
GET /api/consol-note-sections/{project_id}/{year}/{section_id}/data — 加载用户已保存的附注数据
"""

import json
from dataclasses import replace as _replace
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, require_project_access
from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import User
from app.services.consol_node_scope import (
    NodeScope,
    NodeScopeError,
    load_scoped_note_record,
    load_scoped_note_records,
    resolve_node_scope,
    resolve_requested_node_key,
    save_scoped_note_record,
)

router = APIRouter(prefix="/api/consol-note-sections", tags=["consol-note-sections"])

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# 内存缓存 (mtime, data)
_cache: dict[str, tuple[float, list[dict]]] = {}


def _load_sections(standard: str) -> list[dict]:
    """从 JSON 文件加载章节数据（带内存缓存，文件变更时自动刷新）。

    自动将 multi_header 转换为 _column_groups（使前端渲染路径统一）。
    """
    json_path = DATA_DIR / f"consol_note_sections_{standard}.json"
    if not json_path.exists():
        return []

    mtime = json_path.stat().st_mtime
    cached = _cache.get(standard)
    if cached and cached[0] == mtime:
        return cached[1]

    data = json.loads(json_path.read_text(encoding="utf-8"))

    # 补齐 _column_groups + columns + _row_types
    from app.services.consol_note_formula_service import (
        multi_header_to_column_groups,
        _ensure_columns,
        _ensure_row_types,
    )

    for section in data:
        if not isinstance(section, dict):
            continue
        if not section.get("_column_groups"):
            mh = section.get("multi_header")
            if mh:
                groups = multi_header_to_column_groups(mh)
                if groups:
                    section["_column_groups"] = groups
        _ensure_columns(section)
        _ensure_row_types(section)

    _cache[standard] = (mtime, data)
    return data


# ─── 附注差额与「按公式填入」（spec consol-elimination-single-source-push 任务 7）──────────────
# 固定前缀路径（breakdown / fill-by-formula）声明在 ``/{standard}/{section_id}`` 之前，免得被当成模板名。


def _note_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc))


def _requested_note_template(body: dict) -> str | None:
    """读取标准/模板请求，并拒绝两个字段指向不同模板。"""
    from app.services.consol_note_formula_service import note_template_type

    standard = body.get("standard")
    template_type = body.get("template_type")
    if standard and template_type and note_template_type(standard) != note_template_type(template_type):
        raise _note_error(
            ValueError(
                f"standard={standard} 与 template_type={template_type} 指向不同附注模板"
            )
        )
    return template_type or standard


async def _resolve_requested_template(
    db: AsyncSession,
    project_id: UUID,
    body: dict,
) -> str:
    """按项目真实标准解析模板；显式标准/模板只用于一致性校验。"""
    from app.services.consol_note_formula_service import NoteFormulaError, resolve_note_template_type

    requested = _requested_note_template(body)
    try:
        return await resolve_note_template_type(db, project_id, requested)
    except NoteFormulaError as exc:
        raise _note_error(exc) from exc


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

    try:
        result = await note_breakdown(db, project_id, year, section_id, node_key=node_key, standard=standard)
    except NoteFormulaError as e:
        await db.rollback()
        raise _note_error(e) from e
    await db.commit()  # 只可能写了按需种子（模板级派生配置），不写项目数据
    return result


@router.post("/fill-by-formula/{project_id}/{year}/{section_id}")
async def fill_note_by_formula(
    project_id: UUID, year: int, section_id: str,
    node_key: str | None = Query(None, description="企业树节点；根节点允许读取历史兼容行但写入节点专属行"),
    standard: str | None = Query(None, description="附注标准（soe / listed）；不传按项目口径"),
    template_type: str | None = Query(None, description="合并附注模板（soe / listed）；不传按项目口径"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """把合并数写入该章节已保存数据；按项目标准解析模板并清除待更新标记。"""
    from app.services.consol_note_formula_service import NoteFormulaError, fill_by_formula

    try:
        result = await fill_by_formula(
            db,
            project_id,
            year,
            section_id,
            node_key=node_key,
            standard=standard,
            template_type=template_type,
        )
    except NoteFormulaError as e:
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
            "continuation_of": sec.get("continuation_of"),
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
            result = {
                "section_id": sec["section_id"],
                "title": sec["title"],
                "parent_section": sec.get("parent_section", ""),
                "headers": sec.get("headers", []),
                "rows": sec.get("rows", []),
                "multi_header": sec.get("multi_header"),
            }
            if sec.get("_column_groups"):
                result["_column_groups"] = sec["_column_groups"]
            if sec.get("columns"):
                result["columns"] = sec["columns"]
            if sec.get("_row_types"):
                result["_row_types"] = sec["_row_types"]
            return result
    return {"error": "章节不存在", "section_id": section_id}


# ─── 用户数据存储（按项目+年度+章节+节点） ───────────────────────────────────


def _requested_node_key(query_node_key: str | None, body: dict | None = None) -> str | None:
    """兼容旧 body 调用，并把 query/body 冲突转换成当前路由的 4xx。"""
    try:
        return resolve_requested_node_key(query_node_key, body)
    except NodeScopeError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


async def _resolve_note_scope(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    node_key: str | None,
    section_id: str | None = None,
) -> NodeScope:
    """把共享作用域错误转换成当前路由的 HTTP 错误。"""
    try:
        return await resolve_node_scope(db, project_id, year, node_key, section_id)
    except NodeScopeError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


async def _load_saved_note_data(
    db: AsyncSession,
    scope: NodeScope,
) -> dict[str, dict]:
    """读取已验证作用域的附注数据；根节点才允许逐章节回退 legacy。"""
    records = await load_scoped_note_records(db, scope)
    return {
        record.section_id: record.data if isinstance(record.data, dict) else {}
        for record in records
    }


async def _load_note_record(
    db: AsyncSession,
    scope: NodeScope,
    *,
    allow_root_legacy_fallback: bool = True,
) -> ConsolNoteData | None:
    """按已验证作用域读取附注行。"""
    return await load_scoped_note_record(
        db, scope, allow_root_legacy_fallback=allow_root_legacy_fallback,
    )


async def _save_note_record(
    db: AsyncSession,
    scope: NodeScope,
    data: dict,
    *,
    now=None,
) -> ConsolNoteData:
    """按已验证作用域写入附注行，统一处理 legacy 复制与并发。"""
    try:
        return await save_scoped_note_record(db, scope, data, now=now)
    except NodeScopeError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


async def _load_tb_map(
    db: AsyncSession,
    scope: NodeScope,
) -> dict[str, dict[str, float]]:
    """从共享合并上下文构建节点科目金额，不按 company_code 自行汇总。

    ``audited`` 是所选节点的合并数；``opening`` 使用上一审计年度同一 node_key
    的共享合并数，避免把项目级根公司余额误当作子节点/汇总节点金额。
    """
    from app.services.consol_calc_basis import MEASURE_CONSOLIDATED, node_measures
    from app.services.consol_report_view_service import (
        ViewError,
        find_node,
        load_view_context,
    )

    ctx = await load_view_context(db, scope.project_id, scope.year)
    if ctx is None:
        raise ValueError("无法加载当前年度合并计算上下文")
    try:
        node = find_node(ctx.basis.tree, scope.node_key)
    except ViewError as exc:
        raise ValueError(str(exc)) from exc

    node_values = node_measures(ctx.basis)
    current = node_values.get(node.node_key)
    if current is None:
        raise ValueError(f"节点 {node.node_key} 缺少当前年度金额")
    audited_by_code = current.get(MEASURE_CONSOLIDATED, {})

    # 附注模板的“期初/年初”沿用同一共享节点口径，以上一有效审计年度审定数表示。
    # 若上一年度或节点不存在，opening 保持 0（与旧映射的空期初兼容）。
    opening_by_code: dict[str, object] = {}
    prior_ctx = await load_view_context(db, scope.project_id, scope.year - 1)
    if prior_ctx is not None:
        try:
            prior_node = find_node(prior_ctx.basis.tree, node.node_key)
        except ViewError:
            prior_node = None
        if prior_node is not None:
            prior_values = node_measures(prior_ctx.basis).get(prior_node.node_key, {})
            opening_by_code = prior_values.get(MEASURE_CONSOLIDATED, {})

    names = dict(ctx.basis.names)
    if prior_ctx is not None:
        for code, name in prior_ctx.basis.names.items():
            names.setdefault(code, name)

    tb_map: dict[str, dict[str, float]] = {}
    for code in set(audited_by_code) | set(opening_by_code):
        name = names.get(code)
        if not name:
            continue
        tb_map[name] = {
            "audited": float(audited_by_code.get(code, 0)),
            "opening": float(opening_by_code.get(code, 0)),
        }
    return tb_map


@router.get("/data/{project_id}/{year}/{section_id}")
async def get_note_data(
    project_id: UUID, year: int, section_id: str,
    node_key: str | None = Query(None, description="企业树节点；不传读取项目级兼容行"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """加载用户已保存的附注数据。根节点无专属行时兼容读取历史项目级行。"""
    try:
        scope = await _resolve_note_scope(db, project_id, year, node_key, section_id)
        record = await _load_note_record(db, scope)
    except HTTPException:
        raise
    if record is None:
        return {"content": {}, "updated_at": None, "node_key": node_key}
    return {
        "content": record.data if isinstance(record.data, dict) else {},
        "updated_at": str(record.updated_at) if record.updated_at else None,
        "node_key": record.node_key if record.node_key is not None else node_key,
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

    resolved_node_key = _requested_node_key(node_key, body)
    scope = await _resolve_note_scope(db, project_id, year, resolved_node_key, section_id)
    payload = body.get("data", {})
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="附注数据格式无效")

    # 自动回填合计行（对用户保存的数据，合计行空值自动求和）
    from app.services.consol_note_formula_service import backfill_total_rows
    save_rows = payload.get("rows")
    if isinstance(save_rows, list) and save_rows:
        backfill_total_rows(save_rows)

    now = datetime.now(timezone.utc)
    try:
        await _save_note_record(db, scope, payload, now=now)
        await db.commit()
        return {"ok": True, "updated_at": str(now), "node_key": scope.node_key}
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        return {"ok": False, "error": str(e), "node_key": scope.node_key}


# ─── 列定位辅助（spec consol-note-refresh-multi-header-fix） ─────────────────

# 期末/本期 关键词
_ENDING_KEYWORDS = ("期末", "本期")
# 期初/年初/上年 关键词
_OPENING_KEYWORDS = ("期初", "年初", "上期", "上年")
# 变动类排除词（含这些词的列是变动列，不应被当作期末/期初写入目标）
_CHANGE_EXCLUDE = ("增加", "减少", "计提", "转回", "转销", "核销", "摊销", "偿还", "发行", "转入", "变动")


def _header_root(h: str) -> str:
    """取斜杠路径表头的首段；无斜杠时原样返回。"""
    return h.split("/", 1)[0] if "/" in h else h


def _is_ending_label(label: str) -> bool:
    """判断 label 是否表示"期末/本期"类（排除变动列如"本期增加""本期减少"）。"""
    if not any(k in label for k in _ENDING_KEYWORDS):
        return False
    # 含变动类关键词的列排除（"本期增加"不是期末值列）
    if any(k in label for k in _CHANGE_EXCLUDE):
        return False
    return True


def _is_opening_label(label: str) -> bool:
    """判断 label 是否表示"期初/年初/上年"类。"""
    return any(k in label for k in _OPENING_KEYWORDS)


def _classify_header(h: str) -> str | None:
    """单列表头分类：返回 ``'audited'`` / ``'opening'`` / ``None``。

    用于审计校验等需要**逐列判断**的场景（不同于 _resolve_value_columns 只取第一列）。
    对斜杠路径只看首段，排除变动列。
    """
    h_clean = h.replace(" ", "").replace("\u3000", "")
    if not h_clean:
        return None
    root = _header_root(h_clean)
    if _is_ending_label(root):
        return "audited"
    if _is_opening_label(root):
        return "opening"
    return None


def _resolve_value_columns(
    template: dict,
) -> dict[str, list[int]]:
    """从模板解析数值列映射：``{'audited': [col_indices], 'opening': [col_indices]}``。

    策略分三层（逐层降级）：

    1. ``_column_groups``（P2 产出）存在时，按组名定位到组内第一列。
    2. ``multi_header`` 非 null 时，按 multi_header 第一行的顶级分组名匹配，
       对每个分组只取**起始列**（即叶子列第一个）。
    3. 扁平表头：用首段关键词匹配，多列命中**只取第一个**（保守策略）。

    对"本期增加""本期减少"等变动列不写入（刷新只推合计值到期末/期初列）。
    """
    headers = template.get("headers", [])
    column_groups = template.get("_column_groups")

    # ── 策略 1：_column_groups（P2 就绪后走此路径） ──
    if column_groups:
        audited_cols: list[int] = []
        opening_cols: list[int] = []
        for g in column_groups:
            group_name = str(g.get("group", ""))
            start = int(g.get("start", 0))
            if _is_ending_label(group_name):
                audited_cols.append(start)
            elif _is_opening_label(group_name):
                opening_cols.append(start)
        return {"audited": audited_cols[:1], "opening": opening_cols[:1]}

    # ── 策略 2：multi_header 非 null ──
    multi_header = template.get("multi_header")
    if multi_header and len(multi_header) >= 2:
        # multi_header[0] 是顶级分组行，如 ["账龄", "期末数", "期初数", "", ""]
        top_row = multi_header[0]
        audited_cols = []
        opening_cols = []
        # 从顶级行识别"期末"/"期初"分组的起始列
        for ci, cell in enumerate(top_row):
            if ci == 0:
                continue
            cell_clean = str(cell).replace(" ", "").replace("\u3000", "")
            if not cell_clean:
                continue  # 空白 = 前一个分组的延续列
            if _is_ending_label(cell_clean):
                audited_cols.append(ci)
            elif _is_opening_label(cell_clean):
                opening_cols.append(ci)
        return {"audited": audited_cols[:1], "opening": opening_cols[:1]}

    # ── 策略 3：扁平表头降级 ──
    audited_cols = []
    opening_cols = []
    for ci, h in enumerate(headers):
        if ci == 0:
            continue
        h_clean = str(h).replace(" ", "").replace("\u3000", "")
        if not h_clean:
            continue
        # 取首段做匹配，避免斜杠路径里"账面余额"误命中
        root = _header_root(h_clean)
        if _is_ending_label(root):
            audited_cols.append(ci)
        elif _is_opening_label(root):
            opening_cols.append(ci)
    # 多列命中只取第一个（保守：变动表"本期增加/本期减少/期末余额"只取期末余额不现实，
    # 故只取第一个命中列——通常就是期末余额列）
    return {"audited": audited_cols[:1], "opening": opening_cols[:1]}


# ─── 公式刷新：根据项目数据重新计算附注表格 ──────────────────────────────────

@router.post("/refresh/{project_id}/{year}/{section_id}")
async def refresh_note_by_formula(
    project_id: UUID, year: int, section_id: str,
    body: dict,
    node_key: str | None = Query(None, description="企业树节点；根节点按 node_key 读取对应企业试算表"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """刷新并持久化当前节点章节，保留旧 rows/message 字段兼容客户端。"""
    from app.services.consol_note_formula_service import NoteFormulaError, fill_by_formula

    resolved_node_key = _requested_node_key(node_key, body)
    # 节点作用域完整校验（项目/年度/企业树/节点定位）
    scope = await _resolve_note_scope(db, project_id, year, resolved_node_key, section_id)
    template_type = await _resolve_requested_template(db, project_id, body)

    try:
        result = await fill_by_formula(
            db,
            project_id,
            year,
            section_id,
            node_key=resolved_node_key,
            template_type=template_type,
        )
        await db.commit()
    except NoteFormulaError as exc:
        await db.rollback()
        raise _note_error(exc) from exc
    except Exception:
        await db.rollback()
        raise

    return {
        **result,
        "rows": result["data"].get("rows", []),
        "message": f"附注章节已持久化刷新（保留人工单元格 {result['kept_manual_count']} 个）",
    }


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
    2. 与试算表数据交叉校验（使用 ORM 真实列 audited_amount / opening_balance）
    """
    try:
        resolved_node_key = _requested_node_key(node_key, body)
        template_type = await _resolve_requested_template(db, project_id, body)
    except HTTPException:
        await db.rollback()
        raise

    scope = await _resolve_note_scope(db, project_id, year, resolved_node_key)

    sections = _load_sections(template_type)
    results: list[dict] = []

    # 加载用户已保存的数据；带节点键时严格隔离，根合并节点允许兼容读取 legacy 行
    saved_data: dict[str, dict] = {}
    saved_data_error: str | None = None
    try:
        saved_data = await _load_saved_note_data(db, scope)
    except Exception as e:
        saved_data_error = f"加载已保存数据失败: {e}"

    # 加载试算表数据用于交叉校验（ORM 真实列）
    tb_map: dict[str, dict[str, float]] = {}
    tb_error: str | None = None
    try:
        tb_map = await _load_tb_map(db, scope)
    except Exception as e:
        tb_error = f"加载试算表失败: {e}"

    audited_sections = 0

    for sec in sections:
        sec_id = sec["section_id"]
        title = sec.get("title", "")
        headers = sec.get("headers", [])

        # 获取用户数据或模板数据
        user_data = saved_data.get(sec_id, {})
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
                        "message": "合计行与明细行之和不一致",
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
                    col_type = _classify_header(h)
                    if col_type == "audited":
                        expected = tb_entry["audited"]
                    elif col_type == "opening":
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

    response: dict = {
        "total_sections": audited_sections,
        "results": results,
    }
    # 暴露数据加载层错误，不吞异常
    errors: list[str] = []
    if saved_data_error:
        errors.append(saved_data_error)
    if tb_error:
        errors.append(tb_error)
    if errors:
        response["load_errors"] = errors
    return response


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
    try:
        resolved_node_key = _requested_node_key(node_key, body)
        template_type = await _resolve_requested_template(db, project_id, body)
    except HTTPException:
        await db.rollback()
        raise
    scope = await _resolve_note_scope(db, project_id, year, resolved_node_key, section_id)
    headers = body.get("headers", [])
    data_rows = body.get("rows", [])

    # 加载模板获取标题
    sections = _load_sections(template_type)
    title = section_id
    for sec in sections:
        if sec["section_id"] == section_id:
            title = sec.get("title", section_id)
            if not headers:
                headers = sec.get("headers", [])
            if not data_rows:
                data_rows = sec.get("rows", [])
            break

    results: list[dict] = []

    if not headers or not data_rows:
        return {"results": [], "message": "无数据可审核"}

    # 规则1：合计行校验
    for ri, row in enumerate(data_rows):
        if not row or not row[0]:
            continue
        cell0 = str(row[0]).replace(" ", "").replace("　", "")
        if "合计" not in cell0 and "小计" not in cell0:
            continue

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
    col_map: dict = {}
    for ci, h in enumerate(headers):
        h_clean = h.replace(" ", "").replace("\u3000", "")
        root = _header_root(h_clean)
        col_type = _classify_header(h)
        if col_type == "audited":
            col_map["closing"] = ci
        elif col_type == "opening":
            col_map["opening"] = ci
        elif "增加" in root or "计提" in root:
            col_map.setdefault("increase", []).append(ci) if isinstance(col_map.get("increase"), list) else col_map.update({"increase": [ci]})
        elif "减少" in root or "转回" in root or "转销" in root:
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
                    "message": "期末 ≠ 期初 + 增加 - 减少",
                })

    # 规则3：与试算表交叉校验（ORM 真实列）
    tb_map: dict[str, dict[str, float]] = {}
    tb_error: str | None = None
    try:
        tb_map = await _load_tb_map(db, scope)
    except Exception as e:
        tb_error = f"加载试算表失败: {e}"

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
                col_type = _classify_header(h)
                if col_type == "audited":
                    expected = tb_entry["audited"]
                elif col_type == "opening":
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
                            "message": "与试算表数据不一致",
                        })

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

    response: dict = {"results": results}
    if tb_error:
        response["load_errors"] = [tb_error]
    return response


# ─── 一键取数计算：对所有附注表格执行公式取数 ─────────────────────────────────

@router.post("/apply-formulas/{project_id}/{year}")
async def apply_all_formulas(
    project_id: UUID, year: int,
    body: dict,
    node_key: str | None = Query(None, description="企业树节点；不传写入项目级兼容行"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """逐章节按共享公式内核刷新所有附注，并隔离单章节失败。"""
    from app.services.consol_note_aggregation_service import validate_lineage_dag
    from app.services.consol_note_formula_service import (
        NoteFormulaError,
        consol_note_tables,
        fill_note_sections,
        resolve_note_template_type,
    )

    resolved_node_key = _requested_node_key(node_key, body)
    # 节点作用域完整校验（项目/年度/企业树/节点定位）
    await _resolve_note_scope(db, project_id, year, resolved_node_key)
    # DAG 校验（合并层级链不能有循环引用）
    if not await validate_lineage_dag(project_id, db):
        raise HTTPException(status_code=400, detail="合并层级链存在循环引用，无法批量刷新")

    try:
        requested_template = body.get("template_type") or body.get("standard")
        template_type = await resolve_note_template_type(db, project_id, requested_template)
        section_ids = [str(sec.get("section_id")) for sec in consol_note_tables(template_type) if sec.get("section_id")]
        result = await fill_note_sections(
            db,
            project_id,
            year,
            section_ids,
            node_key=resolved_node_key,
            template_type=template_type,
        )
        await db.commit()
    except NoteFormulaError as exc:
        await db.rollback()
        raise _note_error(exc) from exc
    except Exception:
        await db.rollback()
        raise

    return {
        **result,
        "updated_sections": result["sections_updated"],
        "message": f"已持久化刷新 {result['sections_updated']} 个附注表格",
    }


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

    mode=direct: 汇总当前节点的直接下级企业（从企业树获取）
    mode=custom: 汇总用户选择的企业列表
    """
    from app.services.consol_node_scope import scope_for_tree_node

    section_id = body.get("section_id", "")
    row_idx = body.get("row_idx", 0)
    col_idx = body.get("col_idx", 1)
    mode = body.get("mode", "direct")
    company_codes = body.get("company_codes", [])
    resolved_node_key = _requested_node_key(node_key, body)
    template_type = await _resolve_requested_template(db, project_id, body)
    scope = await _resolve_note_scope(db, project_id, year, resolved_node_key, section_id)

    # 获取目标子节点列表
    child_scopes: list[NodeScope] = []
    if mode == "direct":
        # 从已验证的企业树获取直接下级节点
        if scope.node is not None and scope.node.children:
            for child in scope.node.children:
                if child.node_key:
                    child_scopes.append(scope_for_tree_node(scope, child, section_id))
    else:
        # 用户指定企业列表 — 用 company_codes 在树中定位节点
        if scope.tree is not None:
            from app.services.consol_tree_service import find_node_by_key as _fnbk

            for code in company_codes:
                for suffix in (":consol", ":parent", ":hq"):
                    child_node = _fnbk(scope.tree, f"{code}{suffix}")
                    if child_node is not None:
                        child_scopes.append(scope_for_tree_node(scope, child_node, section_id))
                        break

    if not child_scopes:
        return {"value": None, "count": 0, "message": "无下级企业"}

    # 从各子节点的已保存数据中提取同位置的值并汇总
    total = 0.0
    count = 0
    child_errors: list[dict] = []
    for child_scope in child_scopes:
        try:
            record = await _load_note_record(db, child_scope)
            if record is not None:
                data = record.data if isinstance(record.data, dict) else {}
                rows = data.get("rows", [])
                if row_idx < len(rows) and col_idx < len(rows[row_idx]):
                    val = rows[row_idx][col_idx]
                    try:
                        num = float(str(val).replace(",", "").replace("，", ""))
                        total += num
                        count += 1
                    except (ValueError, TypeError):
                        pass
        except Exception as e:
            child_errors.append({"node_key": child_scope.node_key, "error": str(e)})

    # 如果没有从附注数据中找到，尝试从试算表提取
    if count == 0:
        sections = _load_sections(template_type)
        template = next((sec for sec in sections if sec["section_id"] == section_id), None)

        if template:
            item_name = ""
            if template.get("rows") and row_idx < len(template["rows"]):
                item_name = template["rows"][row_idx][0] if template["rows"][row_idx] else ""

            if item_name:
                for child_scope in child_scopes:
                    try:
                        child_tb = await _load_tb_map(db, child_scope)
                        entry = child_tb.get(item_name.strip())
                        if entry:
                            headers = template.get("headers", [])
                            col_header = headers[col_idx] if col_idx < len(headers) else ""
                            h_clean = col_header.replace(" ", "")
                            val = 0.0
                            col_type = _classify_header(col_header)
                            if col_type == "audited":
                                val = entry["audited"]
                            elif col_type == "opening":
                                val = entry["opening"]
                            if val:
                                total += val
                                count += 1
                    except Exception as e:
                        child_errors.append({"node_key": child_scope.node_key, "error": f"试算表加载失败: {e}"})

    response: dict = {
        "value": round(total, 2) if count > 0 else None,
        "count": count,
        "message": f"已汇总 {count} 家企业",
    }
    if child_errors:
        response["child_errors"] = child_errors
    return response



# ─── 跨表勾稽校验 ──────────────────────────────────────────────────────────────
# spec: note-sub-table-formula-and-cross-check Phase 0


@router.get("/check-rules/{project_id}/{year}/{section_id}")
async def get_check_rules(
    project_id: UUID,
    year: int,
    section_id: str,
    template_type: str = Query("soe", description="soe 或 listed"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
):
    """返回指定章节的 check_rules 声明 + 执行结果。"""
    from app.services.note_check_rules import _load_check_rules, check_note_cross_rules

    rules = _load_check_rules(template_type, section_id)
    if not rules:
        return {"section_id": section_id, "template_type": template_type, "rules": [], "results": []}

    results = await check_note_cross_rules(db, project_id, year, section_id, template_type)
    return {
        "section_id": section_id,
        "template_type": template_type,
        "rules": [
            {
                "check_id": r.check_id,
                "peer_section_id": r.peer_section_id,
                "relation": r.relation,
                "description": r.description,
            }
            for r in rules
        ],
        "results": [r.to_dict() for r in results],
    }
