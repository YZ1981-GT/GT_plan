"""附注会计政策条款解析服务

从会计政策长文本解析标题层级，生成 _policy_clauses sidecar 数组。
支持中文编号标题识别、clause_id 稳定生成、三栏对比、批量确认。

clause_id 生成规则：
1. 若模板源显式提供 clause_id，直接使用。
2. 若无显式 ID，则使用 semantic_section_id + heading_path_hash。
3. 若同一 heading path 重复，追加稳定序号。
4. 标题改名但 heading path 位置不变时，保留原 clause_id 并标记 title_changed。

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


# ---------------------------------------------------------------------------
# 中文编号标题正则
# ---------------------------------------------------------------------------

# Level 1: 一、二、三、…… 或 （一）（二）（三）
_L1_FULL_WIDTH = re.compile(r"^[一二三四五六七八九十百]+、")
_L1_PAREN = re.compile(r"^（[一二三四五六七八九十百]+）")

# Level 2: 1. 2. 3. 或 (1) (2) (3) 或 1、2、3、
_L2_DOT = re.compile(r"^(\d+)\.\s*")
_L2_PAREN = re.compile(r"^\((\d+)\)\s*")
_L2_CHINESE_COMMA = re.compile(r"^(\d+)、")

# Level 3: ① ② ③ 或 (a) (b) 或 a. b.
_L3_CIRCLE = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]")
_L3_ALPHA_PAREN = re.compile(r"^\([a-z]\)\s*")
_L3_ALPHA_DOT = re.compile(r"^[a-z]\.\s*")


def _detect_heading_level(line: str) -> int | None:
    """检测一行文本是否为标题，返回层级 (1/2/3) 或 None。"""
    stripped = line.strip()
    if not stripped:
        return None

    if _L1_FULL_WIDTH.match(stripped) or _L1_PAREN.match(stripped):
        return 1
    if _L2_DOT.match(stripped) or _L2_PAREN.match(stripped) or _L2_CHINESE_COMMA.match(stripped):
        return 2
    if _L3_CIRCLE.match(stripped) or _L3_ALPHA_PAREN.match(stripped) or _L3_ALPHA_DOT.match(stripped):
        return 3
    return None


def _extract_title(line: str) -> str:
    """从标题行中提取纯标题文本（去除编号前缀）。"""
    stripped = line.strip()

    # 尝试各种前缀去除
    for pattern in [_L1_FULL_WIDTH, _L1_PAREN, _L2_DOT, _L2_PAREN,
                    _L2_CHINESE_COMMA, _L3_CIRCLE, _L3_ALPHA_PAREN, _L3_ALPHA_DOT]:
        m = pattern.match(stripped)
        if m:
            return stripped[m.end():].strip()

    return stripped


# ---------------------------------------------------------------------------
# clause_id 生成
# ---------------------------------------------------------------------------


def _heading_path_hash(heading_path: list[str]) -> str:
    """对 heading_path 列表生成短 hash（前 8 位 hex）。"""
    raw = "/".join(heading_path)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]


def generate_clause_id(
    semantic_section_id: str,
    heading_path: list[str],
    existing_ids: set[str],
    explicit_id: str | None = None,
) -> str:
    """生成稳定 clause_id。

    规则：
    1. 显式 ID 优先
    2. semantic_section_id + heading_path_hash
    3. 重复时追加序号

    Args:
        semantic_section_id: 语义章节 ID
        heading_path: 从顶层到当前的标题路径列表
        existing_ids: 已分配的 ID 集合（用于去重）
        explicit_id: 模板显式提供的 clause_id

    Returns:
        唯一 clause_id
    """
    if explicit_id and explicit_id.strip():
        cid = explicit_id.strip()
        if cid not in existing_ids:
            existing_ids.add(cid)
            return cid
        # 显式 ID 冲突时追加序号
        idx = 2
        while f"{cid}_{idx}" in existing_ids:
            idx += 1
        unique = f"{cid}_{idx}"
        existing_ids.add(unique)
        return unique

    # 规则 2: semantic_section_id + heading_path_hash
    path_hash = _heading_path_hash(heading_path)
    base_id = f"{semantic_section_id}_{path_hash}" if semantic_section_id else path_hash

    # 规则 3: 重复时追加序号
    if base_id not in existing_ids:
        existing_ids.add(base_id)
        return base_id

    idx = 2
    while f"{base_id}_{idx}" in existing_ids:
        idx += 1
    unique = f"{base_id}_{idx}"
    existing_ids.add(unique)
    return unique


# ---------------------------------------------------------------------------
# 变量检测
# ---------------------------------------------------------------------------

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _detect_variables(text: str) -> list[str]:
    """检测文本中的模板变量 {{var_name}}。"""
    return _VARIABLE_PATTERN.findall(text)


# ---------------------------------------------------------------------------
# 主解析函数
# ---------------------------------------------------------------------------


def parse_policy_text_to_clauses(
    text_content: str,
    semantic_section_id: str = "",
    existing_clauses: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """从会计政策长文本解析标题层级，生成 _policy_clauses 数组。

    Args:
        text_content: 政策章节文本内容
        semantic_section_id: 用于 clause_id 生成
        existing_clauses: 已有条款列表（用于保留 clause_id）

    Returns:
        _policy_clauses 数组
    """
    if not text_content or not text_content.strip():
        return []

    # 构建已有条款的 heading_path → clause_id 映射（用于 title_changed 检测）
    existing_id_map: dict[str, str] = {}
    existing_title_map: dict[str, str] = {}
    if existing_clauses:
        for clause in existing_clauses:
            cid = clause.get("clause_id", "")
            title = clause.get("title", "")
            if cid:
                existing_id_map[cid] = title
                existing_title_map[cid] = title

    lines = text_content.split("\n")
    clauses: list[dict[str, Any]] = []
    existing_ids: set[str] = set()

    # 收集已有条款的 ID
    if existing_clauses:
        for clause in existing_clauses:
            cid = clause.get("clause_id", "")
            if cid:
                existing_ids.add(cid)

    # 状态：当前标题栈和内容缓冲
    heading_stack: list[str] = []  # 当前路径中各级标题
    level_stack: list[int] = []  # 对应层级

    current_title: str | None = None
    current_level: int = 0
    current_lines: list[str] = []
    current_heading_path: list[str] = []

    def _flush_clause() -> None:
        """将当前缓冲的条款内容写入 clauses。"""
        nonlocal current_title, current_lines, current_heading_path
        if current_title is None:
            return

        content = "\n".join(current_lines).strip()
        variables = _detect_variables(content)

        # 尝试匹配已有条款 clause_id（基于 heading path 位置）
        clause_id = generate_clause_id(
            semantic_section_id,
            current_heading_path,
            existing_ids,
        )

        clause: dict[str, Any] = {
            "clause_id": clause_id,
            "title": current_title,
            "level": current_level,
            "current_text": content if content else None,
            "template_text": None,
            "prior_year_text": None,
            "variables": variables,
            "diff_status": "unknown",
            "confirm_status": "pending",
        }
        clauses.append(clause)

        current_title = None
        current_lines = []

    for line in lines:
        level = _detect_heading_level(line)
        if level is not None:
            # 新标题行出现 → flush 之前的
            _flush_clause()

            title = _extract_title(line)
            current_title = title
            current_level = level

            # 维护标题栈
            while level_stack and level_stack[-1] >= level:
                level_stack.pop()
                heading_stack.pop()

            heading_stack.append(title)
            level_stack.append(level)

            current_heading_path = list(heading_stack)
            current_lines = []
        else:
            # 内容行
            if current_title is not None:
                current_lines.append(line)

    # flush 最后一个条款
    _flush_clause()

    return clauses


# ---------------------------------------------------------------------------
# 三栏对比
# ---------------------------------------------------------------------------


def compare_clauses(
    current: list[dict[str, Any]],
    prior: list[dict[str, Any]],
    template: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """对比本年/上年/模板条款，生成 diff_status。

    对比逻辑基于 clause_id 对齐（不按标题文本匹配）。

    Args:
        current: 本年条款列表
        prior: 上年条款列表
        template: 模板条款列表

    Returns:
        增强后的条款列表（含 diff_status/prior_year_text/template_text）
    """
    prior_map: dict[str, dict[str, Any]] = {
        c["clause_id"]: c for c in prior if c.get("clause_id")
    }
    template_map: dict[str, dict[str, Any]] = {
        c["clause_id"]: c for c in template if c.get("clause_id")
    }

    result: list[dict[str, Any]] = []
    seen_clause_ids: set[str] = set()

    for clause in current:
        cid = clause.get("clause_id", "")
        enriched = dict(clause)
        seen_clause_ids.add(cid)

        # 填充上年文本
        prior_clause = prior_map.get(cid)
        if prior_clause:
            enriched["prior_year_text"] = prior_clause.get("current_text")
        else:
            enriched["prior_year_text"] = None

        # 填充模板文本
        template_clause = template_map.get(cid)
        if template_clause:
            enriched["template_text"] = template_clause.get("current_text") or template_clause.get("template_text")
        else:
            enriched["template_text"] = None

        # 判断 diff_status
        current_text = (enriched.get("current_text") or "").strip()
        prior_text = (enriched.get("prior_year_text") or "").strip()
        template_text = (enriched.get("template_text") or "").strip()

        if not prior_clause and not template_clause:
            enriched["diff_status"] = "added"
        elif current_text == prior_text and current_text == template_text:
            enriched["diff_status"] = "unchanged"
        elif current_text == prior_text:
            # 与上年相同但与模板不同
            enriched["diff_status"] = "unchanged"
        elif current_text != prior_text:
            enriched["diff_status"] = "changed"
        else:
            enriched["diff_status"] = "unchanged"

        result.append(enriched)

    # 检测已删除的条款（在上年/模板中有但本年没有）
    for cid, prior_clause in prior_map.items():
        if cid not in seen_clause_ids:
            removed = dict(prior_clause)
            removed["diff_status"] = "removed"
            removed["current_text"] = None
            removed["confirm_status"] = "pending"
            result.append(removed)

    return result


# ---------------------------------------------------------------------------
# 标题改名但路径不变时保留 clause_id
# ---------------------------------------------------------------------------


def reconcile_clause_ids_on_rename(
    new_clauses: list[dict[str, Any]],
    old_clauses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """标题改名但路径位置不变时，保留原 clause_id 并标记 title_changed。

    对比策略：按位置索引 (level + 在同级中的序号) 匹配。
    若新旧条款在相同位置、相同层级，但标题不同，则保留旧 clause_id 并标记。

    Args:
        new_clauses: 新解析出的条款列表
        old_clauses: 已有的条款列表

    Returns:
        reconciled 条款列表
    """
    if not old_clauses:
        return new_clauses

    # 按位置索引映射旧条款
    old_by_position: dict[int, dict[str, Any]] = {}
    for idx, clause in enumerate(old_clauses):
        old_by_position[idx] = clause

    result: list[dict[str, Any]] = []
    for idx, clause in enumerate(new_clauses):
        enriched = dict(clause)
        old_clause = old_by_position.get(idx)

        if old_clause and old_clause.get("level") == clause.get("level"):
            old_title = old_clause.get("title", "")
            new_title = clause.get("title", "")
            old_cid = old_clause.get("clause_id", "")

            if old_title != new_title and old_cid:
                # 标题改名但位置不变 → 保留旧 clause_id
                enriched["clause_id"] = old_cid
                enriched["title_changed"] = True
                enriched["previous_title"] = old_title

        result.append(enriched)

    return result


# ---------------------------------------------------------------------------
# 批量确认
# ---------------------------------------------------------------------------


def batch_confirm_unchanged(clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """批量确认 unchanged 状态的条款。

    仅将 diff_status == 'unchanged' 且 confirm_status == 'pending' 的条款
    标记为 confirmed。

    Args:
        clauses: 条款列表

    Returns:
        更新后的条款列表（新副本）
    """
    result: list[dict[str, Any]] = []
    for clause in clauses:
        updated = dict(clause)
        if (
            updated.get("diff_status") == "unchanged"
            and updated.get("confirm_status") == "pending"
        ):
            updated["confirm_status"] = "confirmed"
        result.append(updated)
    return result
