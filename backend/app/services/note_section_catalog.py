"""附注章节目录 — JSON / Word / DB 的唯一对齐入口.

铁律（禁止三套体系并行）：
- **section_code** = ``note_template_{soe|listed}.json`` 的 ``section_number``
- **variant_key** = ``{template_type}_{report_scope}`` → 致同 Word 路径
- **DB** ``disclosure_notes.note_section`` = section_code（经 legacy 归一化后写入）
- **bindings** 查表键 = section_code；历史 ``五、N``（国企）经 ``normalize_section_code`` 映射到 ``八、N``

Word 模板中的 Heading 文本（如「货币资金」）不作主键，仅通过 ``section_code_index.json`` 映射到 section_code。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
WORD_TEMPLATE_DIR = DATA_DIR / "audit_report_templates" / "disclosure_notes"

VARIANT_KEYS = (
    "soe_standalone",
    "soe_consolidated",
    "listed_standalone",
    "listed_consolidated",
)

# 国企历史底稿/公式/映射常用「五、N」，种子 JSON 为「八、N」（财务报表主要项目注释章）
_SOE_LEGACY_PREFIX = "五、"
_SOE_CANONICAL_PREFIX = "八、"


def normalize_report_scope(report_scope: str | None) -> str:
    s = (report_scope or "standalone").strip().lower()
    return s if s in ("standalone", "consolidated") else "standalone"


def normalize_template_type(template_type: str | None) -> str:
    t = (template_type or "soe").strip().lower()
    return t if t in ("soe", "listed") else "soe"


def build_variant_key(template_type: str | None, report_scope: str | None) -> str:
    return f"{normalize_template_type(template_type)}_{normalize_report_scope(report_scope)}"


def section_applies_to_scope(section: dict[str, Any], report_scope: str | None) -> bool:
    """判断 JSON 模板节是否适用于当前报表口径."""
    scope = (section.get("scope") or "both").strip()
    rs = normalize_report_scope(report_scope)

    if scope == "both":
        return True
    if scope == "consolidated_only":
        return rs == "consolidated"
    if scope == "standalone_only":
        return rs == "standalone"
    if scope in ("standalone", "consolidated"):
        return scope == rs or scope == "both"
    return True


def filter_template_sections(
    sections: list[dict[str, Any]],
    report_scope: str | None,
) -> list[dict[str, Any]]:
    return [s for s in sections if section_applies_to_scope(s, report_scope)]


def template_json_path(template_type: str | None) -> Path:
    t = normalize_template_type(template_type)
    return DATA_DIR / f"note_template_{t}.json"


def word_template_path(variant_key: str) -> Path:
    if variant_key not in VARIANT_KEYS:
        raise ValueError(f"Unknown variant_key: {variant_key}")
    return WORD_TEMPLATE_DIR / f"{variant_key}.docx"


def word_template_relpath(variant_key: str) -> str:
    return f"disclosure_notes/{variant_key}.docx"


@lru_cache(maxsize=2)
def load_section_scope_map(template_type: str | None) -> dict[str, str]:
    """section_number → scope（来自 JSON 种子，供口径过滤）."""
    path = template_json_path(template_type)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        s.get("section_number", ""): s.get("scope", "both")
        for s in data.get("sections", [])
        if s.get("section_number")
    }


def section_scope_for_code(
    section_code: str,
    scope_map: dict[str, str],
    *,
    template_type: str | None = "soe",
) -> str:
    """查章节 scope；支持 legacy 归一后查表."""
    code = (section_code or "").strip()
    if not code:
        return "both"
    if code in scope_map:
        return scope_map[code]
    canonical = normalize_section_code(code, template_type=template_type)
    return scope_map.get(canonical, "both")


def note_applies_to_report_scope(
    note_section: str | None,
    template_type: str | None,
    report_scope: str | None,
) -> bool:
    """单章是否应出现在当前口径的导出/编号结果中."""
    rs = (report_scope or "both").strip().lower()
    if rs == "both":
        return True
    scope_map = load_section_scope_map(template_type)
    scope = section_scope_for_code(note_section or "", scope_map, template_type=template_type)
    return section_applies_to_scope({"scope": scope}, rs)


def filter_tree_by_report_scope(
    tree: list[dict[str, Any]],
    template_type: str | None,
    report_scope: str | None,
) -> list[dict[str, Any]]:
    """过滤附注目录树（get_section_numbers / 预览编号）."""
    rs = (report_scope or "both").strip().lower()
    if rs == "both":
        return list(tree)
    scope_map = load_section_scope_map(template_type)
    return [
        item
        for item in tree
        if section_applies_to_scope(
            {"scope": section_scope_for_code(item.get("note_section", ""), scope_map, template_type=template_type)},
            rs,
        )
    ]


@lru_cache(maxsize=2)
def _load_soe_section_numbers() -> frozenset[str]:
    path = template_json_path("soe")
    if not path.exists():
        return frozenset()
    data = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(
        s.get("section_number", "")
        for s in data.get("sections", [])
        if s.get("section_number")
    )


def normalize_section_code(
    note_section: str,
    *,
    template_type: str | None = "soe",
) -> str:
    """将 DB/公式中的历史编号归一为当前模板种子的 section_code."""
    code = (note_section or "").strip()
    if not code or normalize_template_type(template_type) != "soe":
        return code
    if not code.startswith(_SOE_LEGACY_PREFIX):
        return code
    suffix = code[len(_SOE_LEGACY_PREFIX) :]
    candidate = f"{_SOE_CANONICAL_PREFIX}{suffix}"
    if candidate in _load_soe_section_numbers():
        return candidate
    return code


def resolve_binding_key(
    note_section: str,
    *,
    template_type: str | None = "soe",
) -> str:
    return normalize_section_code(note_section, template_type=template_type)


def detect_heading_level(section_code: str) -> int:
    """由 section_code 推断 Word 导出标题层级（与 NoteWordExporter 一致）."""
    if not section_code:
        return 3
    code = section_code.strip()
    if re.fullmatch(r"[一二三四五六七八九十百]+", code):
        return 1
    if re.match(r"^[一二三四五六七八九十百]+、", code):
        return 2
    parts = code.split(".")
    if len(parts) == 1:
        return 1
    if len(parts) == 2:
        return 2
    return 3
