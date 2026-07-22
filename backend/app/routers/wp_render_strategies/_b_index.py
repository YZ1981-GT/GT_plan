"""B-Index 底稿目录自动生成策略

当 B-Index sheet 无持久化 html_data 时，从项目元数据 + 同底稿 sheets 自动生成。
返回结构与 GtBIndex.vue 的 BIndexHtmlData 接口一致。
"""

from __future__ import annotations

import logging
import re

from ._context import RenderContext

logger = logging.getLogger(__name__)

# sheet 级索引号嵌在 sheet_name 末尾（如「审定表D1-1」→ D1-1，
# 「应收票据审计程序表D1A」→ D1A）；wp_code 仅父级（D1），不能用作 index_ref。
_SHEET_INDEX_PATTERN = re.compile(r"([A-Z]\d+[A-Z]?(?:-\d+)*)\s*$")


async def render(ctx: RenderContext) -> dict | None:
    """返回 sheet_html_data，None 表示不变（使用已有）。

    仅当 B-Index sheet 尚无持久化数据时才自动生成：
    - preparation_info：编制信息（实体名/期末/编制人等）
    - navigation_rows：当前底稿内各 sheet 索引导航
    - cycle_workpapers：同审计循环全部底稿跨底稿跳转目录
    """
    # 持久化数据校验：仅当已是有效 b-index 格式（含非空 navigation_rows）才直接复用。
    # 历史脏数据（如 override 压平时期按 d-form-table 保存的 {rows, context, conclusion}）
    # 缺 navigation_rows，必须重新生成架构导航，否则前端架构树空白。
    _existing = ctx.sheet_html_data if isinstance(ctx.sheet_html_data, dict) else None
    # 已有 architecture 导航时仍刷新 cycle_workpapers：
    # G4/G6 等专属组件目录页 class_code=B- 走路由 b-index，历史持久化常缺跨底稿目录。
    if _existing and _existing.get("navigation_rows"):
        from app.services.wp_cycle_directory import build_cycle_workpapers

        cycle_workpapers = await build_cycle_workpapers(
            db=ctx.db,
            project_id=ctx.project_id,
            audit_cycle=ctx.audit_cycle,
            current_wp_id=ctx.wp_id,
        )
        return {**_existing, "cycle_workpapers": cycle_workpapers}

    from app.services.wp_classification_service import derive_component_type

    # ─── 编制信息（lazy prep_info） ───────────────────────────────────────
    if ctx.prep_info is None:
        from app.services.wp_preparation_info_service import build_preparation_info

        ctx.prep_info = await build_preparation_info(ctx.db, ctx.project_id, ctx.wp_id)

    preparation_info = ctx.prep_info

    # ─── 索引导航行（同底稿其他 sheet → 行） ─────────────────────────────
    # 多 sheet 底稿：按 class_code 独立派生 component_type（跳过 wp_code override 压平），
    # 否则所有 sheet 的 component_type 都会变成同一个值，导致架构树阶段分类/图标错误。
    _real = [c for c in ctx.classifications
             if not (c.sheet_name and "GT_Custom" in c.sheet_name)]
    _multi = len(_real) > 1
    navigation_rows: list[dict] = []
    seq = 1
    for cls in ctx.classifications:
        # 跳过 B-Index 自身
        try:
            ct = derive_component_type(cls, ignore_wp_code_override=_multi)
        except Exception:
            ct = "skip"
        if ct == "b-index":
            continue
        if cls.sheet_name and "GT_Custom" in cls.sheet_name:
            continue

        # 从 sheet_name 末尾提取该 sheet 的真实索引号；提取不到则回退父 wp_code
        sheet_index = ""
        m = _SHEET_INDEX_PATTERN.search(cls.sheet_name or "")
        if m:
            sheet_index = m.group(1)
        else:
            sheet_index = getattr(cls, "wp_code", "") or ""

        navigation_rows.append({
            "seq": seq,
            "content": cls.sheet_name,
            "index_ref": sheet_index,
            "component_type": ct,
            "no_print": False,
        })
        seq += 1

    # ─── 外部关联 sheet（如 D0 函证项列入 D1 底稿目录） ─────────────────
    # 源模板中各循环底稿目录会包含跨底稿的函证等 sheet，
    # 从 account_package_registry 读取 source_wp_code != primary_wp_code 的条目追加。
    try:
        from app.services.account_package_registry_service import AccountPackageRegistryService
        registry = AccountPackageRegistryService()
        wp_code = ctx.wp_code or ""
        for pkg in registry.get_packages():
            if pkg.get("primary_wp_code") != wp_code:
                continue
            # 找到当前底稿对应的 package，追加外部 sheet
            for sheet_def in pkg.get("sheets", []):
                src = sheet_def.get("source_wp_code", "")
                if src and src != wp_code:
                    sheet_name = sheet_def.get("sheet_name", "")
                    if not sheet_name:
                        continue
                    # 提取索引号
                    ext_index = ""
                    m = _SHEET_INDEX_PATTERN.search(sheet_name)
                    if m:
                        ext_index = m.group(1)
                    else:
                        ext_index = src
                    navigation_rows.append({
                        "seq": seq,
                        "content": sheet_name,
                        "index_ref": ext_index,
                        "component_type": "external",
                        "no_print": False,
                        "is_external": True,
                        "source_wp_code": src,
                    })
                    seq += 1
            break  # 只匹配第一个 package
    except Exception as e:  # noqa: BLE001
        logger.debug("b-index: 外部关联 sheet 加载失败: %s", e)

    # ─── 循环底稿目录（跨底稿，同 audit_cycle 全部底稿） ──────────────────
    from app.services.wp_cycle_directory import build_cycle_workpapers

    cycle_workpapers = await build_cycle_workpapers(
        db=ctx.db,
        project_id=ctx.project_id,
        audit_cycle=ctx.audit_cycle,
        current_wp_id=ctx.wp_id,
    )

    result = {
        "preparation_info": preparation_info,
        "navigation_rows": navigation_rows,
        "cycle_workpapers": cycle_workpapers,
    }
    # 保留历史持久化数据中用户可能编辑过的字段（如 conclusion / context），
    # 避免重新生成架构导航时丢失已填写内容。
    if _existing:
        for k, v in _existing.items():
            if k not in result and v:
                result[k] = v
    return result
