"""附注子表 ``guidance``（TAB 页签编制提示）的**读时**回填。

为什么需要
----------
``guidance`` 原先只在 **seed 路径**生效（``disclosure_engine._carry_seed_table_guidance``
把模板显式声明的 guidance 写进生成时的 ``table_data``）。而 ``_source=workpaper``
的记录读取时走 ``note_sub_table_projector.project_sub_tables`` 投影 —— 投影只认
推送来的 ``sub_table_data`` + ``_sub_table_columns``，**模板的 guidance 不参与**
（同步载荷里也没有 guidance 这一项，它是模板侧的编制指引而非业务数据）。

结果：项目一旦点过「同步到附注」，附注 TAB 的编制提示就永久变空。
实测证据（2026-07-30，项目 2aa00f57 §八、31 / §五、30）：投影出的 5/4 张表
``guidance`` 全为空串，而模板里这些表的 guidance 都已写好。

本模块在**读端**按 ``(source_template, note_section, 表名)`` 把模板 guidance 贴回
投影结果。**不写库**、表名对不上就跳过、模板缺 guidance 就保持原值 —— 因此对
既有行为零回归（此前是空，现在最坏还是空）。

单一真源仍是 ``note_template_{listed,soe}.json`` 的 ``tables[].guidance``；
本模块只做搬运，不产生第二份文案。

spec: `.kiro/specs/n1-deferred-tax-disclosure-template-alignment/` R4.6 / R7.1
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

_TEMPLATE_FILES = {
    "listed": "note_template_listed.json",
    "soe": "note_template_soe.json",
}


def _template_path(template_type: str) -> Path | None:
    name = _TEMPLATE_FILES.get(str(template_type or "").strip().lower())
    return _DATA_DIR / name if name else None


@lru_cache(maxsize=8)
def _load_guidance_index(template_type: str, mtime: float) -> dict[str, dict[str, str]]:
    """``{section_number: {table_name: guidance}}``。

    ``mtime`` 只作为缓存键参与失效（模板 JSON 被幂等脚本改写后自动重载），
    函数体不使用它。
    """
    path = _template_path(template_type)
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover - 模板损坏时降级为"无 guidance"
        logger.warning("note_table_guidance: 模板解析失败 %s", path, exc_info=True)
        return {}

    index: dict[str, dict[str, str]] = {}
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        number = str(section.get("section_number") or "").strip()
        if not number:
            continue
        by_name: dict[str, str] = {}
        for table in section.get("tables") or []:
            if not isinstance(table, dict):
                continue
            name = str(table.get("name") or "").strip()
            guidance = str(table.get("guidance") or "").strip()
            if name and guidance:
                by_name[name] = guidance
        if by_name:
            # 同一章节出现重名表时保留首个（重名表本身是模板脏数据，另有守卫）
            index.setdefault(number, {}).update(
                {k: v for k, v in by_name.items() if k not in index.get(number, {})}
            )
    return index


def load_section_guidance(template_type: str, section_number: str) -> dict[str, str]:
    """取某章节的 ``{表名: guidance}``；模板不存在 / 无声明时返回空 dict。"""
    path = _template_path(template_type)
    if path is None or not path.exists():
        return {}
    try:
        mtime = path.stat().st_mtime
    except OSError:  # pragma: no cover
        return {}
    return _load_guidance_index(str(template_type).strip().lower(), mtime).get(
        str(section_number or "").strip(), {}
    )


def resolve_template_type(template_type: str | None, section_number: str | None) -> str | None:
    """把可能**记错**的 ``source_template`` 纠正为真正含该章节号的模板。

    🔴 为什么需要（2026-07-30 实证）：``disclosure_notes.source_template`` 记的是
    **项目模板**而非该章节所属变体 —— 项目 ``2aa00f57`` 用国企版模板生成，于是连
    ``五、30``（**上市版**章节号）都被标成 ``soe``。凡「按 source_template 查模板」
    的读时逻辑在这类章节上必然查不到（N1 实测：国企侧 guidance 能填、上市侧填不上）。

    纠正规则（保守，只在**确定记错**时才换）：
    1. 记录的模板里存在该章节号 → 原样返回（绝大多数情况，零行为变化）
    2. 记录的模板里**没有**该章节号，而**另一个**模板里**恰好有** → 返回另一个
    3. 两个都有 / 两个都没有 → 返回原值（有歧义就不猜）

    章节号在两份模板里几乎不重号（`五、` 系列只在 listed、`八、` 系列只在 soe），
    规则 3 的「两个都有」实际是兜底防御。
    """
    number = str(section_number or "").strip()
    if not number:
        return template_type
    declared = str(template_type or "").strip().lower()
    hit = [t for t in _TEMPLATE_FILES if load_section_guidance(t, number)]
    if declared in hit:
        return template_type
    if len(hit) == 1:
        return hit[0]
    return template_type


def carry_template_guidance(
    tables: list[dict[str, Any]] | None,
    template_type: str | None,
    section_number: str | None,
) -> int:
    """把模板 guidance 按表名就地贴到投影出的 ``tables``。

    规则（宁缺勿造）：
    - 表已带非空 ``guidance`` → 不覆盖（推送侧若将来自带提示，以推送为准）
    - 表名在模板里找不到 → 跳过（不猜、不按位置对齐）
    - 模板该表无 guidance → 跳过

    :returns: 实际贴上的表数（供日志/测试断言）
    """
    if not tables or not template_type or not section_number:
        return 0
    # `source_template` 记的是**项目模板**，上市章节号可能被标成 soe → 先纠正
    mapping = load_section_guidance(
        resolve_template_type(template_type, section_number) or template_type,
        section_number,
    )
    if not mapping:
        return 0
    filled = 0
    for table in tables:
        if not isinstance(table, dict):
            continue
        if str(table.get("guidance") or "").strip():
            continue
        guidance = mapping.get(str(table.get("name") or "").strip())
        if guidance:
            table["guidance"] = guidance
            filled += 1
    return filled


__all__ = ["carry_template_guidance", "load_section_guidance"]
