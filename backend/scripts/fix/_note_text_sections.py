"""附注章节 ``text_sections`` 的标题化 / 去标题化 / 补段（纯函数，stdlib-only）。

从 ``_note_structure_kit.py`` 拆出的伴生模块（R8.4 批 9b-2，2026-10-25）—— 本会话给 kit 加了三个
共享 helper 后它越过 800 行门禁；该文件在 HEAD 是 761 行（**在限内**），所以不该靠白名单放过，
按门禁提示「优先拆伴生模块」把 `text_sections` 这一个关注点整段搬出来。

kit 仍 ``from _note_text_sections import *`` 式逐名 re-export（见其文件末尾注释），因此
``KIT.titleize_text_sections`` / ``KIT.is_title_paragraph`` 这类既有调用（约 30 个幂等脚本 +
多个守卫）逐字不变。

🔴 为什么判据要和后端分开复刻一份：这些函数要能在 ``--check`` 里**不起 FastAPI / 不连库**地独立跑，
故 ``is_title_paragraph`` 是 ``disclosure_engine._is_table_title_paragraph`` 的 stdlib 复刻；
两者必须逐样本相等，由 ``tests/test_note_text_hygiene.py::test_kit_title_judge_matches_backend_engine``
交叉锁死。
"""
from __future__ import annotations

import re
from typing import Any

__all__ = [
    "ensure_text_sections",
    "find_bare_table_name_paragraphs",
    "is_title_paragraph",
    "missing_text_sections",
    "titleize_text_sections",
    "untitleize_text_sections",
]

# 与后端 `disclosure_engine._NUMBERED_TITLE_RE` 同口径（`（N）xxx` / `N. xxx`）
_NUMBERED_TITLE_RE = re.compile(r"^(?:（(\d+)）|(\d+)[.、])")


def is_title_paragraph(para: str) -> bool:
    """复刻 `disclosure_engine._is_table_title_paragraph`（stdlib-only，供 --check 独立跑）。"""
    s = (para or "").strip()
    if not s:
        return False
    if s.startswith("#"):
        return True
    if len(s) > 20:
        return False
    return bool(_NUMBERED_TITLE_RE.match(s))


def titleize_text_sections(section: dict[str, Any]) -> list[str]:
    """把 `text_sections` 里的**裸表名**加上 `#### ` 前缀，返回变更说明。"""
    paras = section.get("text_sections")
    if not isinstance(paras, list):
        return []
    names = {str(t.get("name", "")).strip() for t in (section.get("tables") or [])}
    changes: list[str] = []
    out: list[str] = []
    for p in paras:
        s = str(p)
        stripped = s.strip()
        if stripped in names and not is_title_paragraph(s):
            out.append(f"#### {stripped}")
            changes.append(f"text_sections：裸表名「{stripped}」→ 加 #### 前缀（不再当正文渲染）")
        else:
            out.append(s)
    if changes:
        section["text_sections"] = out
    return changes


def untitleize_text_sections(section: dict[str, Any], paragraphs: list[str]) -> list[str]:
    """摘掉指定段落的 `#### ` 前缀 —— :func:`titleize_text_sections` 的逆操作。幂等。

    🔴 **必须与表名复位成对调用**（`rule(aliases=...)` / ``restore_table_names``）：提示段被
    误当表名后，有人给它加 `#### ` 让「每张表都有小节标题」过关；表名复位后标题就比表多一个
    ⇒ `disclosure_engine` 段落游标多走一格、后续提示段配到别的表上。机理与逐条取证见 spec
    `consol-note-header-library-and-node-reaggregate` design §17.7。

    只摘 `paragraphs` 逐字命中的段；摘完若该段恰是表名，`titleize` 会加回来（互不打架）。
    """
    paras = section.get("text_sections")
    wanted = {str(p).strip() for p in (paragraphs or []) if str(p).strip()}
    if not isinstance(paras, list) or not wanted:
        return []
    changes: list[str] = []
    out: list[str] = []
    for p in paras:
        s, body = str(p), str(p).strip().lstrip("#").strip()
        hit = s.strip().startswith("#") and body in wanted
        out.append(body if hit else s)
        if hit:
            changes.append(f"text_sections：「{body[:24]}…」去掉 #### 前缀（表名已复位，标题多余）")
    if changes:
        section["text_sections"] = out
    return changes


def missing_text_sections(section: dict[str, Any], required: list[str]) -> list[str]:
    """返回 `required` 里尚不存在于 `text_sections` 的段落（按 strip 后逐字比对）。"""
    paras = section.get("text_sections")
    existing = {str(p).strip() for p in (paras if isinstance(paras, list) else [])}
    return [r for r in (required or []) if str(r).strip() not in existing]


def ensure_text_sections(section: dict[str, Any], required: list[str]) -> list[str]:
    """确保 `required` 段落存在 —— **缺失则按序追加到末尾**，已有的一律不动。幂等。

    与 `run_section(text_sections=...)` 的**整表替换**语义不同：这里是「补齐缺段」，
    用于「源模板有某小节说明、模板 JSON 漏了」的场景（如 K1 上市 ⑧⑨⑩ 三节），
    避免为补 3 段而手抄整份 47 段（手抄错字会被脚本写回模板，风险远大于收益）。

    ⚠️ 正文段**不要**带 `#### ` 前缀 —— `disclosure_engine._is_table_title_paragraph`
    见 `#` 即判为标题，标题本身不进任何输出 → 实质披露正文会被静默丢弃。
    """
    paras = section.get("text_sections")
    paras = list(paras) if isinstance(paras, list) else []
    existing = {str(p).strip() for p in paras}
    changes: list[str] = []
    for r in required or []:
        key = str(r).strip()
        if not key or key in existing:
            continue
        paras.append(r)
        existing.add(key)
        changes.append(f"text_sections：追加「{key[:24]}…」")
    if changes:
        section["text_sections"] = paras
    return changes


def find_bare_table_name_paragraphs(section: dict[str, Any]) -> list[str]:
    """返回仍会被当正文渲染的裸表名段落（供 validate / 测试）。"""
    names = {str(t.get("name", "")).strip() for t in (section.get("tables") or [])}
    return [
        str(p).strip()
        for p in (section.get("text_sections") or [])
        if str(p).strip() in names and not is_title_paragraph(str(p))
    ]
