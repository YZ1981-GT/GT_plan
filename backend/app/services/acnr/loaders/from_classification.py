"""Loader: workpaper_sheet_classification → SheetCatalogEntry 骨架。

读取 classification DB（通过 SQLAlchemy async session），产出 100% 覆盖的
SheetCatalogEntry 骨架列表。每条记录映射为一个 skeleton entry。

Requirements: 1.1
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_STANDARD_WP_CODE_RE = re.compile(r"^[A-S]\d")

# render_type → editor_engine 映射（源自 workpaper_render_registry.json 的 render_types）
_RENDER_TYPE_TO_ENGINE: dict[str, str] = {
    "html_procedure": "html",
    "html_review": "html",
    "auto_report": "html",
    "univer": "univer",
    "word_template": "onlyoffice",
    "readonly_reference": "html",
    "signing": "html",
}


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class SheetCatalogEntry:
    """L1 SheetCatalogEntry 骨架（design.md §Data Models）。"""

    addr_id: str
    domain: str = "wp"
    origin: str = "standard"
    cycle: str = ""
    parent_wp_code: str = ""
    sheet_code: str = ""
    sheet_name: str = ""
    class_code: str = ""
    functional_type: str = ""
    editor_engine: str = "html"
    display_label: str = ""
    jump_route_template: str = ""
    registry_version: str = ""
    template_version_id: str = ""
    source_of_truth: str = "classification_db"
    # 以下字段由其他 loader 合并填充
    sheet_name_aliases: list[str] = field(default_factory=list)
    component_type: str = ""
    import_export: dict[str, Any] | None = None
    skip_reason: str | None = None


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _extract_cycle(wp_code: str) -> str:
    """从 wp_code 提取循环码（首字母）。"""
    if wp_code:
        return wp_code[0]
    return ""


def _extract_parent_wp_code(wp_code: str) -> str:
    """从 sheet 级 wp_code 提取 parent（如 D2-2 → D2）。

    规则：
    - 含 '-' 且非 A/B/C/S 类聚合：取 '-' 前（如 D2-2 → D2）
    - 不含 '-'：自身即 parent（如 D2 → D2）
    - 特殊后缀如 D4-34-rental：逐级上溯到 D4
    """
    if not wp_code:
        return ""
    # 基础模式：X + digits + 可选后缀
    m = re.match(r"^([A-S]\d+)", wp_code)
    if m:
        return m.group(1)
    return wp_code


def _build_display_label(parent: str, sheet_name: str) -> str:
    """构建展示路径。"""
    return f"底稿 > {parent} > {sheet_name}"


def _build_jump_route_template(sheet_code: str) -> str:
    """构建跳转模板（wp_id 由 ProjectBinding 填充）。"""
    return f"/workpapers/{{wp_id}}?sheet={sheet_code}"


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def load_sheet_skeletons_from_classification(
    records: Sequence[Any],
    *,
    registry_version: str = "",
    render_type_map: dict[str, str] | None = None,
) -> list[SheetCatalogEntry]:
    """将 classification 记录转换为 SheetCatalogEntry 骨架列表。

    classification 表以 (wp_code, sheet_name) 为主键，同一 wp_code 可有多条记录
    （对应底稿内的不同 Tab）。ACNR catalog 以 wp_code 为 sheet 粒度（一个 wp_code
    一个 SheetCatalogEntry），因此需按 wp_code 聚合/去重。

    去重策略：
    - 优先选取非占位（class_code != 'I-占位'）、非 GT_Custom 的记录作为代表
    - 相同 wp_code 的多条记录中 class_code/sheet_name 最具业务含义的胜出
    - functional_type 取第一个非空值

    Parameters
    ----------
    records
        WorkpaperSheetClassification ORM 对象列表（或等价 dict）。
        需有字段：wp_code, sheet_name, class_code, functional_type, template_version_id.
    registry_version
        catalog 版本号。
    render_type_map
        可选 {wp_code → render_type} 映射（来自 render_registry），
        用于推断 editor_engine。

    Returns
    -------
    list[SheetCatalogEntry]
        每个 wp_code 一条 SheetCatalogEntry，100% 覆盖 classification 中所有 distinct wp_code。
    """
    _rtm = render_type_map or {}

    # --- Step 1: 按 wp_code 聚合所有记录 ---
    grouped: dict[str, list[dict[str, str]]] = {}
    for rec in records:
        if isinstance(rec, dict):
            wp_code = rec.get("wp_code", "")
            sheet_name = rec.get("sheet_name", "")
            class_code = rec.get("class_code", "") or ""
            functional_type = rec.get("functional_type", "") or ""
            template_version_id = str(rec.get("template_version_id", "") or "")
        else:
            wp_code = getattr(rec, "wp_code", "")
            sheet_name = getattr(rec, "sheet_name", "")
            class_code = getattr(rec, "class_code", "") or ""
            functional_type = getattr(rec, "functional_type", "") or ""
            template_version_id = str(getattr(rec, "template_version_id", "") or "")

        if not wp_code:
            continue

        if wp_code not in grouped:
            grouped[wp_code] = []
        grouped[wp_code].append({
            "wp_code": wp_code,
            "sheet_name": sheet_name,
            "class_code": class_code,
            "functional_type": functional_type,
            "template_version_id": template_version_id,
        })

    # --- Step 2: 选取代表记录并构建 SheetCatalogEntry ---
    results: list[SheetCatalogEntry] = []

    for wp_code, recs in grouped.items():
        # 选代表记录：优先级 — 非占位非GT_Custom > 非占位 > 任意
        representative = _pick_representative(recs)

        sheet_name = representative["sheet_name"]
        class_code = representative["class_code"]
        template_version_id = representative["template_version_id"]

        # functional_type: 取所有记录中第一个非空值
        functional_type = ""
        for r in recs:
            if r["functional_type"]:
                functional_type = r["functional_type"]
                break

        parent = _extract_parent_wp_code(wp_code)
        cycle = _extract_cycle(wp_code)

        sheet_code = wp_code
        addr_id = f"{parent}/{sheet_code}"

        # editor_engine 推断
        render_type = _rtm.get(wp_code, "")
        editor_engine = _RENDER_TYPE_TO_ENGINE.get(render_type, "html")

        entry = SheetCatalogEntry(
            addr_id=addr_id,
            cycle=cycle,
            parent_wp_code=parent,
            sheet_code=sheet_code,
            sheet_name=sheet_name,
            class_code=class_code,
            functional_type=functional_type,
            editor_engine=editor_engine,
            display_label=_build_display_label(parent, sheet_name),
            jump_route_template=_build_jump_route_template(sheet_code),
            registry_version=registry_version,
            template_version_id=template_version_id,
        )
        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# 代表记录选取
# ---------------------------------------------------------------------------

# class_code 优先级（数字越小越优先）
_CLASS_PRIORITY: dict[str, int] = {
    "A-一般程序表": 1,
    "A-实质性程序": 1,
    "F-审定表": 2,
    "F-明细表": 3,
    "F-检查表": 4,
    "F-分析表": 5,
    "F-数据表": 6,
    "C-附注披露": 7,
    "B-底稿目录": 8,
    "H-辅助说明": 9,
    "I-占位": 99,
}


def _pick_representative(recs: list[dict[str, str]]) -> dict[str, str]:
    """从同 wp_code 的多条记录中选出最具业务含义的代表。

    优先级：class_code 优先级表 > 非 GT_Custom > 第一条
    """
    # 过滤掉 GT_Custom 和 占位（如果有其他选择）
    meaningful = [
        r for r in recs
        if r["sheet_name"] != "GT_Custom" and r["class_code"] != "I-占位"
    ]

    candidates = meaningful if meaningful else recs

    # 按 class_code 优先级排序
    candidates.sort(key=lambda r: _CLASS_PRIORITY.get(r["class_code"], 50))

    return candidates[0]
