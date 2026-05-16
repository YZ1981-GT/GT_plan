"""底稿模板下载路由

提供底稿模板文件的下载端点：
- GET  /api/projects/{pid}/wp-templates/{wp_code}/download  — 下载单个科目模板
- GET  /api/projects/{pid}/wp-templates/download-all         — 批量下载全部模板（ZIP）
- GET  /api/projects/{pid}/wp-templates/list                 — 列出全部模板（含元数据合并 + 项目状态）

template-library-coordination Sprint 1 Task 1.3: /list 增强 5 字段
（component_type/has_formula/source_file_count/sheet_count/generated）
N+1 防退化：4 次 IO（2 SQL + 2 文件读），内存 dict 按 primary_code 查找。
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.wp_template_init_service import (
    find_template_file_any,
    find_all_template_files,
    TEMPLATES_DIR,
    _load_index,
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/wp-templates",
    tags=["workpaper-template-download"],
)


@router.get("/{wp_code}/download")
async def download_template_by_code(
    project_id: str,
    wp_code: str,
    current_user: User = Depends(require_project_access("readonly")),
):
    """下载单个科目的模板文件（从 wp_templates/ 目录）

    如果该科目有多个模板文件（如 D2 有审定表+分析程序+检查程序），
    打包为 ZIP 返回；单文件直接返回 xlsx。
    """
    all_files = find_all_template_files(wp_code)
    if not all_files:
        # 尝试单文件
        single = find_template_file_any(wp_code)
        if single:
            all_files = [single]

    if not all_files:
        raise HTTPException(status_code=404, detail=f"模板不存在: {wp_code}")

    # 单文件直接返回
    if len(all_files) == 1:
        f = all_files[0]
        from urllib.parse import quote
        filename = f.name
        ascii_name = filename.encode("ascii", "ignore").decode() or "template.xlsx"
        utf8_name = quote(filename, safe="")
        return FileResponse(
            str(f),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}',
            },
        )

    # 多文件打包为 ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in all_files:
            zf.write(f, f.name)
    buf.seek(0)

    from urllib.parse import quote
    zip_name = f"{wp_code}_模板.zip"
    utf8_name = quote(zip_name, safe="")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{wp_code}_templates.zip"; filename*=UTF-8\'\'{utf8_name}',
        },
    )


@router.get("/list")
async def list_all_templates(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """列出所有可用底稿模板（供树形展示）

    返回按主编码（去除子表）去重后的模板列表，含 5 个增强字段：
      - component_type / audit_stage / linked_accounts / procedure_steps（来自 wp_template_metadata）
      - has_formula（来自 prefill_formula_mapping.json）
      - source_file_count（运行时按 primary_code 前缀从 _index.json["files"] 统计）
      - sheet_count（≈ source_file_count，spec 层近似展示）
      - generated（当前项目是否已生成对应底稿）
      - sort_order（来自 gt_wp_coding 编码体系）

    N+1 防退化：单次批量预加载（4 次 IO）：
      1. SELECT wp_template_metadata 全表
      2. SELECT wp_index 当前项目全部 wp_code
      3. 读 prefill_formula_mapping.json（含缓存）
      4. 读 _index.json（含缓存）

    性能要求：响应时间 ≤ 500ms，DB 查询数 ≤ 4。
    """
    # ------------------------------------------------------------------
    # 1. 加载文件索引（cached），按 primary_code 前缀分组统计 source_file_count
    # ------------------------------------------------------------------
    index = _load_index()  # list[dict]，由 wp_template_init_service 缓存
    if not index:
        return {"items": [], "total": 0}

    # 按 primary_code 分组：count(file where wp_code == primary OR wp_code starts with primary + "-")
    files_by_primary: dict[str, list[dict]] = {}
    for entry in index:
        wp_code = entry.get("wp_code") or ""
        if not wp_code or wp_code.startswith("_"):
            continue
        primary = wp_code.split("-")[0]
        files_by_primary.setdefault(primary, []).append(entry)

    # ------------------------------------------------------------------
    # 2. 加载 prefill_formula_mapping → has_formula 集合
    # ------------------------------------------------------------------
    prefill_path = DATA_DIR / "prefill_formula_mapping.json"
    prefill_wp_codes: set[str] = set()
    if prefill_path.exists():
        try:
            with open(prefill_path, "r", encoding="utf-8") as f:
                pdata = json.load(f)
            prefill_wp_codes = {
                m.get("wp_code") for m in (pdata.get("mappings") or [])
                if m.get("wp_code")
            }
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("failed to load prefill_formula_mapping.json: %s", exc)

    # ------------------------------------------------------------------
    # 3. 单次批量预加载 wp_template_metadata 全表（按 wp_code 主编码维度）
    # ------------------------------------------------------------------
    meta_rows = (
        await db.execute(
            text(
                "SELECT wp_code, component_type, audit_stage, cycle, "
                "       linked_accounts, procedure_steps, file_format "
                "FROM wp_template_metadata"
            )
        )
    ).mappings().all()
    metadata_by_primary: dict[str, dict] = {}
    for r in meta_rows:
        wp_code = r["wp_code"]
        if not wp_code:
            continue
        # 按主编码归并，子表（D2-1/D2-2）归到主编码 D2 下
        primary = wp_code.split("-")[0]
        # 如果 primary 已存在则只保留主编码本身（不被子表覆盖）
        # 使用"主编码命中优先"策略：wp_code == primary 时直接覆盖
        existing = metadata_by_primary.get(primary)
        if existing is None or wp_code == primary:
            metadata_by_primary[primary] = dict(r)

    # ------------------------------------------------------------------
    # 4. 单次批量预加载 working_paper（通过 wp_index JOIN）当前项目的 wp_code 集合
    # ------------------------------------------------------------------
    generated_wp_codes: set[str] = set()
    try:
        gen_rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT wi.wp_code "
                    "FROM working_paper wp "
                    "JOIN wp_index wi ON wp.wp_index_id = wi.id "
                    "WHERE wp.project_id = :pid AND wp.is_deleted = false"
                ),
                {"pid": project_id},
            )
        ).mappings().all()
        # 主编码维度：D2-1 也算 D2 已生成（与树节点维度对齐）
        for r in gen_rows:
            wpc = r["wp_code"] or ""
            if wpc:
                generated_wp_codes.add(wpc)
                generated_wp_codes.add(wpc.split("-")[0])
    except Exception as exc:
        logger.warning("query working_paper failed: %s", exc)

    # ------------------------------------------------------------------
    # 5. （可选）查 gt_wp_coding 取 sort_order — 第 4 个 SQL（DB 查询数 ≤ 4 上限）
    # ------------------------------------------------------------------
    sort_by_prefix: dict[str, int] = {}
    try:
        sort_rows = (
            await db.execute(
                text(
                    "SELECT code_prefix, code_range, sort_order "
                    "FROM gt_wp_coding WHERE is_active = true ORDER BY sort_order"
                )
            )
        ).mappings().all()
        for r in sort_rows:
            cp = r["code_prefix"]
            so = r["sort_order"]
            if cp and so is not None:
                # 取该循环字母的最小 sort_order（首次出现即代表整个循环顺序）
                sort_by_prefix.setdefault(cp, int(so))
    except Exception as exc:
        logger.warning("query gt_wp_coding failed: %s", exc)

    # ------------------------------------------------------------------
    # 6. 按 primary_code 维度去重组装结果
    # ------------------------------------------------------------------
    CYCLE_NAMES = {
        'A': 'A 完成阶段', 'B': 'B 风险评估', 'C': 'C 控制测试',
        'D': 'D 销售循环', 'E': 'E 货币资金', 'F': 'F 存货',
        'G': 'G 投资', 'H': 'H 固定资产', 'I': 'I 无形资产',
        'J': 'J 薪酬', 'K': 'K 费用', 'L': 'L 负债',
        'M': 'M 权益', 'N': 'N 税项', 'S': 'S 特定项目',
    }

    items: list[dict] = []
    seen_primaries: set[str] = set()
    # 排序：按 primary_code 升序（同主编码下先取主表本身）
    for entry in sorted(index, key=lambda x: (x.get("wp_code") or "", len(x.get("filename") or ""))):
        wp_code = entry.get("wp_code") or ""
        if not wp_code or wp_code.startswith("_"):
            continue
        primary = wp_code.split("-")[0]
        if primary in seen_primaries:
            continue
        seen_primaries.add(primary)

        cycle = primary[0] if primary else '?'
        # 从文件名提取底稿名称（去掉编码前缀）
        fname = entry.get("filename") or ""
        name_part = fname.rsplit('.', 1)[0] if fname else primary
        if ' ' in name_part:
            name_part = name_part.split(' ', 1)[1]

        # 从 metadata 合并字段
        meta = metadata_by_primary.get(primary, {})
        # source_file_count：按主编码前缀匹配的物理文件数
        source_files = files_by_primary.get(primary, [])
        source_file_count = len(source_files)
        sheet_count = max(1, source_file_count)

        items.append({
            "wp_code": primary,
            "wp_name": name_part,
            "cycle": cycle,
            "cycle_name": CYCLE_NAMES.get(cycle, f'{cycle} 循环'),
            "filename": fname,
            "format": entry.get("format", "xlsx"),
            # 5 个新增字段（Sprint 1 Task 1.3）
            "component_type": meta.get("component_type"),
            "audit_stage": meta.get("audit_stage"),
            "linked_accounts": meta.get("linked_accounts") or [],
            "procedure_steps": meta.get("procedure_steps") or [],
            "has_formula": primary in prefill_wp_codes,
            "source_file_count": source_file_count,
            "sheet_count": sheet_count,
            "generated": primary in generated_wp_codes,
            "sort_order": sort_by_prefix.get(cycle),
        })

    # 按 cycle sort_order 排序，然后按 wp_code 升序
    def _sort_key(it: dict):
        cyc = it.get("cycle") or "Z"
        so = sort_by_prefix.get(cyc)
        # sort_order 为 None 时排到最后（用 999999 兜底，保留 cycle 字母作 tie-break）
        return (so if so is not None else 999999, cyc, it.get("wp_code") or "")

    items.sort(key=_sort_key)
    return {"items": items, "total": len(items)}


@router.get("/download-all")
async def download_all_templates(
    project_id: str,
    current_user: User = Depends(require_project_access("readonly")),
):
    """批量下载全部底稿模板（ZIP，按循环分目录）

    目录结构: {循环字母}/{wp_code} {名称}.xlsx
    """
    index = _load_index()
    if not index:
        raise HTTPException(status_code=404, detail="模板索引为空")

    buf = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        seen = set()
        for entry in index:
            rel_path = entry.get("relative_path", "")
            if not rel_path or rel_path in seen:
                continue
            full_path = TEMPLATES_DIR / rel_path
            if not full_path.exists():
                continue
            seen.add(rel_path)
            # 保持原始目录结构
            zf.write(full_path, rel_path)
            file_count += 1

    buf.seek(0)
    logger.info("download_all_templates: %d files, %d bytes", file_count, buf.getbuffer().nbytes)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="workpaper_templates_all.zip"; filename*=UTF-8\'\'%E5%BA%95%E7%A8%BF%E6%A8%A1%E6%9D%BF%E5%85%A8%E9%87%8F.zip',
        },
    )
