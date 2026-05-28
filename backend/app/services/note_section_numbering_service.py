"""D13 章节序号动态层级 — 格式注册器 + 编号 Service.

Sprint A.0.3 + A.0.4 — 实现致同附注模板 5 级编号体系：

- level=1：``一、`` ``二、``                  （中文数字 + 顿号）
- level=2：``（一）`` ``（二）``               （括号 + 中文数字）
- level=3：``1.`` ``2.``                     （阿拉伯数字 + 句点）
- level=4：``(1)`` ``(2)``                    （小括号 + 阿拉伯数字）
- level=5：``①`` ``②``                       （带圈数字，1~20）

核心思想：
- 章节序号不写死，由 (level, sort_index) 派生（``LEVEL_FORMATS``）。
- ``NoteSectionNumberingService.render_all`` 按 scope 过滤后树形遍历每层独立计数。
- 用户锁定（``lock_number=True``）的章节使用 ``locked_number`` 占位，不参与重排但仍占同层 sort 位。
- 自动编号（``auto_numbering=True``）才参与 counter 自增；``False`` 的章节渲染空字符串。

详见 design.md §一 D13。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote


# ---------------------------------------------------------------------------
# 中文数字工具（cn_number 1~99）
# ---------------------------------------------------------------------------

_CN_DIGITS = "一二三四五六七八九"
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def cn_number(i: int) -> str:
    """阿拉伯整数转中文数字（1~99 支持，超范围回退原数字串）.

    示例:
        cn_number(1)  -> "一"
        cn_number(10) -> "十"
        cn_number(11) -> "十一"
        cn_number(20) -> "二十"
        cn_number(35) -> "三十五"
        cn_number(99) -> "九十九"
        cn_number(100) -> "100"   # 超界回退
    """
    if i < 1:
        return str(i)
    if 1 <= i <= 9:
        return _CN_DIGITS[i - 1]
    if i == 10:
        return "十"
    if 11 <= i <= 19:
        return f"十{_CN_DIGITS[i - 10 - 1]}"
    if 20 <= i <= 99:
        tens = i // 10
        ones = i % 10
        tens_str = _CN_DIGITS[tens - 1] + "十"
        return f"{tens_str}{_CN_DIGITS[ones - 1]}" if ones else tens_str
    return str(i)


def circled_number(i: int) -> str:
    """阿拉伯整数转带圈数字（1~20 支持，超范围回退括号格式 ``(N)``）."""
    if 1 <= i <= 20:
        return _CIRCLED[i - 1]
    return f"({i})"


# ---------------------------------------------------------------------------
# 5 级格式注册器（A.0.4）
# ---------------------------------------------------------------------------

# 单级序号格式：i 是同 (level, parent) 内的 1-based 序号
LEVEL_FORMATS: dict[int, Any] = {
    1: lambda i: f"{cn_number(i)}、",     # 一、 二、 三、
    2: lambda i: f"（{cn_number(i)}）",    # （一）（二）（三）
    3: lambda i: f"{i}.",                  # 1. 2. 3.
    4: lambda i: f"({i})",                 # (1) (2) (3)
    5: circled_number,                     # ① ② ③
}


def render_section_number(level: int, sort_index: int) -> str:
    """渲染单层级序号（A.0.4 入口）.

    Args:
        level: 1~5；超范围抛 ValueError。
        sort_index: 1-based 序号（同层级内的兄弟位置）。

    Returns:
        格式化序号字符串（如 ``"四、"`` ``"（二）"`` ``"3."``）。
    """
    if level not in LEVEL_FORMATS:
        raise ValueError(f"Unsupported level={level}, expected 1..5")
    if sort_index < 1:
        raise ValueError(f"sort_index must be >= 1, got {sort_index}")
    fn = LEVEL_FORMATS[level]
    return fn(sort_index)


# ---------------------------------------------------------------------------
# 章节节点（service 内部用）
# ---------------------------------------------------------------------------


class _SectionNode:
    """轻量级章节节点（DB 记录或 dict 形式 section）的统一封装."""

    __slots__ = (
        "section_id", "level", "parent_section_id", "sort_index",
        "auto_numbering", "lock_number", "locked_number", "scope",
        "is_deleted", "raw",
    )

    def __init__(self, raw: Any):
        self.raw = raw
        self.section_id = _attr(raw, "section_id")
        lvl = _attr(raw, "level")
        self.level = int(lvl) if lvl is not None else 0
        self.parent_section_id = _attr(raw, "parent_section_id")
        si = _attr(raw, "sort_index")
        self.sort_index = int(si) if si is not None else 0
        self.auto_numbering = bool(_attr(raw, "auto_numbering", True))
        self.lock_number = bool(_attr(raw, "lock_number", False))
        self.locked_number = _attr(raw, "locked_number")
        self.scope = _attr(raw, "scope", "both")
        self.is_deleted = bool(_attr(raw, "is_deleted", False))


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """对 ORM 实例 / dict 都能 get 字段."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ---------------------------------------------------------------------------
# Service（A.0.3）
# ---------------------------------------------------------------------------


class NoteSectionNumberingService:
    """章节编号动态计算服务.

    主要 API:

    - ``render_all(project_id, year, scope)``    — DB 加载所有 sections 计算
    - ``render_sections(sections, scope)``       — 给一组 sections（ORM/dict）计算
    - ``render_for_template(template_sections, scope)`` — 给模板 JSON sections 计算

    返回字典：``{section_id: rendered_full_number}``，``rendered_full_number`` 是
    包含父级路径的完整序号（如 ``"四、（一）2."``，对应 level=3 章节）。
    """

    # ----------------------- DB 入口 -----------------------

    async def render_all(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        scope: str = "both",
    ) -> dict[str, str]:
        """从 DB 加载 ``disclosure_notes`` 计算各章节序号."""
        stmt = (
            select(DisclosureNote)
            .where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == False,  # noqa: E712
            )
        )
        rows = (await db.execute(stmt)).scalars().all()
        return self.render_sections(rows, scope=scope)

    # ----------------------- Pure 计算入口 -----------------------

    def render_sections(
        self,
        sections: Sequence[Any],
        scope: str = "both",
    ) -> dict[str, str]:
        """对一组 sections 计算 rendered_number 字典.

        Args:
            sections: ORM 实例或 dict 列表，必须含 ``section_id`` / ``level`` /
                ``parent_section_id`` / ``sort_index`` / ``auto_numbering`` /
                ``lock_number`` / ``locked_number`` / ``scope`` (可选) 字段。
            scope: 'standalone' | 'consolidated' | 'both' — 过滤章节可见性。

        Returns:
            ``{section_id: full_rendered_number}``
        """
        nodes = [_SectionNode(s) for s in sections if _attr(s, "section_id")]
        # 过滤 scope + is_deleted
        nodes = [
            n for n in nodes
            if not n.is_deleted and (scope == "both" or n.scope in (scope, "both"))
        ]
        if not nodes:
            return {}

        # 索引：parent_id → list[node]
        children_map: dict[str | None, list[_SectionNode]] = {}
        for n in nodes:
            children_map.setdefault(n.parent_section_id, []).append(n)
        # 同层稳定按 sort_index 排序
        for k in children_map:
            children_map[k].sort(key=lambda n: (n.sort_index, n.section_id or ""))

        result: dict[str, str] = {}
        # 顶层 = parent_section_id is None OR parent 不在当前节点集合中（orphan）
        all_ids = {n.section_id for n in nodes if n.section_id}
        roots = children_map.get(None, [])[:]
        # 把 parent 不在集合中的节点也当 root（按各自 parent 分组保持独立编号）
        orphan_groups: list[list[_SectionNode]] = []
        for parent_id, children in children_map.items():
            if parent_id is not None and parent_id not in all_ids:
                orphan_groups.append(children)
        # 合并所有 orphan 到 roots（它们的 parent 不可见，直接作为顶层渲染）
        for group in orphan_groups:
            roots.extend(group)
        roots.sort(key=lambda n: (n.sort_index, n.section_id or ""))

        def _walk(node: _SectionNode, parent_path: str, sibling_counter: dict[int, int]):
            """DFS 渲染：兄弟之间在同 sibling_counter 字典内累计."""
            if node.lock_number and node.locked_number:
                rendered = node.locked_number
            elif not node.auto_numbering:
                rendered = ""
            else:
                lvl = node.level if 1 <= node.level <= 5 else 1
                sibling_counter[lvl] = sibling_counter.get(lvl, 0) + 1
                rendered = render_section_number(lvl, sibling_counter[lvl])
            full = f"{parent_path}{rendered}" if parent_path else rendered
            if node.section_id:
                result[node.section_id] = full

            # 递归子节点（每个父节点持自己的 counter，互相独立）
            child_counter: dict[int, int] = {}
            for child in children_map.get(node.section_id, []):
                _walk(child, full, child_counter)

        root_counter: dict[int, int] = {}
        for r in roots:
            _walk(r, "", root_counter)

        return result

    # ----------------------- 模板 JSON 入口 -----------------------

    def render_for_template(
        self,
        template_sections: list[dict],
        scope: str = "both",
    ) -> dict[str, str]:
        """给模板 JSON sections（dict 列表）计算渲染序号.

        与 ``render_sections`` 区别：直接接受 dict（不是 ORM）。
        """
        return self.render_sections(template_sections, scope=scope)



# ---------------------------------------------------------------------------
# Jinja ref() 全局函数（A.0.6）
# ---------------------------------------------------------------------------


def jinja_ref(section_id: str, rendered_numbers: dict[str, str]) -> str:
    """Jinja 模板内部引用函数 — 渲染章节交叉引用为最新序号.

    用法（在 Jinja 模板中）::

        本期增加情况详见 {{ ref("section_revenue_breakdown") }}

    渲染后::

        本期增加情况详见 五、(三) 2.

    Args:
        section_id: 目标章节的 stable section_id。
        rendered_numbers: 由 ``NoteSectionNumberingService.render_sections``
            返回的 ``{section_id: full_rendered_number}`` 字典。

    Returns:
        渲染后的序号字符串；未找到时返回 ``[未知章节: {section_id}]``。
    """
    return rendered_numbers.get(section_id, f"[未知章节: {section_id}]")


def make_jinja_ref_function(rendered_numbers: dict[str, str]):
    """创建绑定了 rendered_numbers 的 ref() 闭包，用于注册到 Jinja env.

    用法::

        from jinja2 import Environment, BaseLoader
        env = Environment(loader=BaseLoader())
        env.globals['ref'] = make_jinja_ref_function(rendered_numbers)
        tmpl = env.from_string("详见 {{ ref('section_cash') }}")
        result = tmpl.render()
    """
    def _ref(section_id: str) -> str:
        return jinja_ref(section_id, rendered_numbers)
    return _ref
