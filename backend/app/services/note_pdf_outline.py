"""PDF 书签目录 → 章节标题（第 23 组，AC-1.6）。

LibreOffice / Word 导出的附注 PDF 标题常与正文同字号、不加粗（国企单体模板转 PDF 实测：12 号不加粗，
按字号判标题只得 3 章），但书签目录完整（422 条、5 级）。书签就是作者给的章节树，有就按它切。

两处要处理：
- 模板表格表头段落误设了大纲级别，书签里混进「账 龄」「期末数」「项目名称」等（国企单体 39 条）——
  与带编号的同级书签并列、自身无编号 ⇒ 不是标题；
- 书签深度是相对上级算的：噪声条目下面的真标题深度被算浅（第 179 页「（2）应付关联方款项」深 2、真实 3）
  ⇒ 去掉噪声后按编号对齐层级。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

__all__ = ["OutlineHeading", "locate_heading_lines", "outline_headings"]

_WS = re.compile(r"\s+")
#: 一个标题最多折成几行（PDF 按版面断行）
_MAX_TITLE_LINES = 4


@dataclass(frozen=True)
class OutlineHeading:
    order: int  # 在书签目录里的原始序号（报告被剔除的条目时按它排序）
    title: str
    page: int  # 1 起；-1 = 不指向本文档页面
    level: int
    rank: int | None  # 标题编号排位，无编号为 None


def _parents(entries: list[OutlineHeading]) -> list[int | None]:
    """书签按层级成树（与 ``build_source_tree`` 同一口径：上级 = 前面最近的更浅层级条目）。"""
    parents: list[int | None] = []
    stack: list[int] = []
    for index, entry in enumerate(entries):
        while stack and entries[stack[-1]].level >= entry.level:
            stack.pop()
        parents.append(stack[-1] if stack else None)
        stack.append(index)
    return parents


def _realigned_level(index: int, entries: list[OutlineHeading], parents: list[int | None],
                     noise: set[int], shift: dict[int, int]) -> int:
    """噪声条目的直接下级的新层级：对齐到前面最近的同编号条目；无编号 / 找不到则挂到最近的非噪声祖先下。"""
    rank = entries[index].rank
    if rank is not None:
        for k in range(index - 1, -1, -1):
            if k not in noise and entries[k].rank == rank:
                return entries[k].level + shift.get(k, 0)
    ancestor = parents[index]
    while ancestor is not None and ancestor in noise:
        ancestor = parents[ancestor]
    return entries[ancestor].level + shift.get(ancestor, 0) + 1 if ancestor is not None else 1


def _drop_noise(entries: list[OutlineHeading]) -> tuple[list[OutlineHeading], list[OutlineHeading]]:
    """逐轮剔除「同级已有带编号书签时的无编号书签」，到不变为止（重排层级后可能又露出新的并列）。"""
    dropped: list[OutlineHeading] = []
    while True:
        parents = _parents(entries)
        numbered_groups = {parents[i] for i, entry in enumerate(entries) if entry.rank is not None}
        noise = {i for i, entry in enumerate(entries) if entry.rank is None and parents[i] in numbered_groups}
        if not noise:
            return entries, sorted(dropped, key=lambda entry: entry.order)
        shift: dict[int, int] = {}
        for index, entry in enumerate(entries):
            parent = parents[index]
            if index in noise or parent is None:
                continue
            if parent in shift:  # 已重排节点的子树整体平移
                shift[index] = shift[parent]
            elif parent in noise:
                shift[index] = _realigned_level(index, entries, parents, noise, shift) - entry.level
        dropped.extend(entries[i] for i in noise)
        entries = [replace(entry, level=entry.level + shift.get(i, 0))
                   for i, entry in enumerate(entries) if i not in noise]


def outline_headings(toc: list[list], rank: Callable[[str], int | None]
                     ) -> tuple[list[OutlineHeading], list[OutlineHeading]]:
    """``Document.get_toc()`` 的 ``[层级, 标题, 页码]`` → （标题书签, 被剔除的噪声书签）。"""
    entries = [OutlineHeading(order, title, int(item[2]), int(item[0]), rank(title))
               for order, item in enumerate(toc) if (title := str(item[1] or "").strip())]
    return _drop_noise(entries)


def _find_title_lines(keys: list[str], key: str, start: int, stop: int) -> tuple[int, int] | None:
    for first in range(start, stop):
        joined = ""
        for last in range(first, min(first + _MAX_TITLE_LINES, len(keys))):
            joined += keys[last]
            if joined == key:
                return first, last
            if not key.startswith(joined):
                break
    return None


def locate_heading_lines(lines: list[str], page_starts: list[int], headings: list[OutlineHeading]
                         ) -> tuple[list[tuple[OutlineHeading, int, int]], list[str]]:
    """书签逐条在所指页（及下一页）上找标题行（去空白后整行相等，可折成几行），按文档顺序推进。

    ``page_starts[p]`` = 第 p 页（0 起）首行在 ``lines`` 里的下标，末尾多一个哨兵 = ``len(lines)``。
    找不到的报出来、不猜：其正文留在上一节。
    """
    keys = [_WS.sub("", line) for line in lines]
    pages = len(page_starts) - 1
    hits: list[tuple[OutlineHeading, int, int]] = []
    warnings: list[str] = []
    cursor = 0
    for heading in headings:
        if not 1 <= heading.page <= pages:
            warnings.append(f"书签「{heading.title}」没有指向本文档的页面，未作为标题")
            continue
        start = max(cursor, page_starts[heading.page - 1])
        found = _find_title_lines(keys, _WS.sub("", heading.title), start, page_starts[min(heading.page + 1, pages)])
        if found is None:
            warnings.append(f"书签「{heading.title}」在第 {heading.page} 页找不到对应的标题行，未作为标题")
            continue
        hits.append((heading, *found))
        cursor = found[1] + 1
    return hits, warnings
