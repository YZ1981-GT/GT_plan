"""Sprint A.4.2 / A.4.4 — 附注段落 Jinja 渲染入口.

提供一个无 DB / 无副作用的 helper，把 section 的 text_template 渲染成最终
``text_content``。Word 导出器（A.4.4）可直接消费 ``text_content`` 字段，
无需重新走 Jinja —— 由 A.4.2 在落库前确保 ``text_content`` 已渲染即可。

主要 API:
- ``render_section_text(section, vars, rendered_numbers) -> str``
   - 优先用 ``section['text_template']``（Jinja 模板）
   - 缺则降级到 ``section['text_content']``（旧 schema 字符串）
   - 缺则降级到 ``section['text_sections']`` 拼接（旧 schema 多段）
   - 全缺 → 返回空字符串

- ``async def render_section_text_async(db, section, project_id, year,
   rendered_numbers=None) -> str``
   - 同上，但 vars 由 ``collect_paragraph_vars`` 自动收集
"""

from __future__ import annotations

import logging
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.note_text_paragraph_vars import collect_paragraph_vars
from app.services.note_text_template_engine import render_text_paragraph

logger = logging.getLogger(__name__)


def _section_get(section: Any, key: str, default: Any = None) -> Any:
    """ORM 实例 / dict 通用 getter."""
    if isinstance(section, Mapping):
        return section.get(key, default)
    return getattr(section, key, default)


def _coerce_legacy_text(section: Any) -> str:
    """回退到旧 schema：``text_content`` / ``text_sections`` 拼接."""
    legacy = _section_get(section, "text_content")
    if legacy:
        return str(legacy)
    sections_list = _section_get(section, "text_sections")
    if isinstance(sections_list, list):
        parts: list[str] = []
        for item in sections_list:
            if isinstance(item, str) and item.strip():
                parts.append(item.rstrip())
            elif isinstance(item, Mapping):
                # 常见形态 {"content": "..."} 或 {"text": "..."}
                content = item.get("content") or item.get("text") or ""
                if content:
                    parts.append(str(content).rstrip())
        return "\n\n".join(parts)
    return ""


def render_section_text(
    section: Any,
    vars: dict[str, Any] | None = None,
    rendered_numbers: dict[str, str] | None = None,
    *,
    strict: bool = True,
) -> str:
    """渲染 section 文字段落.

    优先级：
    1. ``text_template`` 字段存在且非空 → Jinja 渲染
    2. 降级 ``text_content``（旧 schema 字符串）
    3. 降级 ``text_sections``（旧 schema 列表）
    4. 全无 → ``""``

    Args:
        section: ORM 实例 / dict / Mapping
        vars: 模板变量字典
        rendered_numbers: 章节序号字典（``ref()`` 用）
        strict: True=未声明变量抛错（CI-11）

    Returns:
        渲染后的字符串。
    """
    template_str = _section_get(section, "text_template")
    if template_str and isinstance(template_str, str) and template_str.strip():
        return render_text_paragraph(
            template_str,
            vars or {},
            rendered_numbers=rendered_numbers,
            strict=strict,
        )
    return _coerce_legacy_text(section)


async def render_section_text_async(
    db: AsyncSession,
    section: Any,
    project_id: UUID,
    year: int,
    *,
    rendered_numbers: dict[str, str] | None = None,
    section_id: str | None = None,
    extra_vars: dict[str, Any] | None = None,
    prior_notes_cache: dict[str, str] | None = None,
    strict: bool = True,
) -> str:
    """渲染 section 文字段落（自动收集变量）.

    与 ``render_section_text`` 一致，但 vars 自动由
    ``collect_paragraph_vars`` 从 DB / wizard_state / consol scope 装配。

    Args:
        section: ORM 实例 / dict
        project_id: 项目 ID
        year: 年度
        rendered_numbers: 章节序号字典
        section_id: 当前章节 section_id（覆盖 section 自带）
        extra_vars: 额外变量（最高优先级）
        prior_notes_cache: 上年附注缓存（可选）
        strict: 严格模式
    """
    sid = section_id or _section_get(section, "section_id")
    section_template_vars = _section_get(section, "text_template_vars")
    if not isinstance(section_template_vars, dict):
        section_template_vars = None

    vars_dict = await collect_paragraph_vars(
        db,
        project_id,
        year,
        section_id=sid,
        section_text_template_vars=section_template_vars,
        prior_notes_cache=prior_notes_cache,
    )
    if extra_vars:
        vars_dict.update(extra_vars)

    return render_section_text(
        section,
        vars=vars_dict,
        rendered_numbers=rendered_numbers,
        strict=strict,
    )
