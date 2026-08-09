"""附注「可扩位行」标记的单一真源（纯函数、无 IO、stdlib-only）。

源模板在某些位置留了「可继续加行」的意图（`……` / `可无限量添加行`）。这些位置
既不是数据行也不是合计行 ⇒ 用 additive 的第 6 个 ``row_type`` 取值 ``expandable``
表达：**零可见内容**（不渲染成数据行、不参与任何合计），但保留「此处可增行」的位置
信息供前端将来做增行入口。

为什么判据放在 service 层而不是脚本里
------------------------------------
``row_type`` 有**多个写者**：本 spec 的 ``fix_note_expandable_rows.py``、
共享行构造器 ``scripts/fix/_note_structure_kit.data_row()``、以及若干 per-cycle
幂等脚本（如 ``fix_note_h_policy_chapter_structure.py`` 用
``tables[0] != want`` **深比较整表**后整表重写）。判据分散在脚本里 ⇒ 双写者互相
翻转：实测 soe ``四、生物资产`` 的 4 行 ``……`` 被翻回 ``data``（2026-08-08）。
把判据收在此处后，所有写者共用同一函数，谁也翻不动谁。

🔴 两套词表**有意不同，不得统一**
--------------------------------
* :data:`MARKERS`（6 词）—— **源侧**判据，扫源 xlsx 单元格文本，允许「包含」匹配；
* :data:`LABEL_MARKERS`（5 词，排除 ``可改名``）—— **行标签**判据，且是
  **恰等于**（归一候选之一）。

``可改名`` 在源模板里只出现在 ``项目1（可改名）`` 这类**示例行名**上
（证据：``wp_templates/G/G4 债权投资.xlsx!附注披露信息（上市公司）!A9``），
语义是「这一行的名字可以改」而**不是**「这里可以加行」——
标成零可见内容会把一条合法数据行藏起来。

spec: note-template-columns-and-legacy-snapshot-closure R11.1 / R11.2 / Property 33~34
"""

from __future__ import annotations

import re
from typing import Any

#: additive 新增的第 6 个 ``row_type`` 取值。既有五个
#: （``data``/``total``/``subtotal``/``header_label``/``unowned``）语义逐字不变。
EXPANDABLE_ROW_TYPE = "expandable"

#: 源侧词表（顺序 = 匹配优先级：长串先于短串，否则 `……` 会被 `…` 抢走、
#: `......` 会被 `...` 抢走）。每词在 ``backend/wp_templates/**`` 的披露 sheet
#: 命中 ≥1 次由 ``note_expandable_markers.json`` 的 ``source_hits`` 冻结（Property 34）。
MARKERS: tuple[str, ...] = (
    "可无限量添加行",
    "......",
    "……",
    "可改名",
    "预留",
    "…",
)

#: 可作**行标签**判定的子集（排除 ``可改名``，理由见 :data:`LABEL_MARKER_EXCLUDED`）。
LABEL_MARKERS: tuple[str, ...] = (
    "可无限量添加行",
    "......",
    "……",
    "预留",
    "…",
)

LABEL_MARKER_EXCLUDED: dict[str, str] = {
    "可改名": (
        "源模板里只作示例行名后缀出现（如 `项目1（可改名）`，"
        "wp_templates/G/G4 债权投资.xlsx!附注披露信息（上市公司）!A9），"
        "语义是「行名可改」而非「此处可增行」；标 expandable 会隐藏合法数据行。"
    ),
}

#: label 前缀序号（`1、……` / `2.……`）与尾部标点（`…….`）。
_LABEL_SEQ_PREFIX_RE = re.compile(r"^\d+[、.．]")
_LABEL_TAIL_PUNCT = "。.、，,；;"

_WS_RE = re.compile(r"\s+")


def match_marker(text: Any) -> str | None:
    """返回该文本命中的**源侧**标记词（按 :data:`MARKERS` 顺序，长串优先）。

    用于扫源 xlsx 单元格（允许「包含」匹配）。无命中返 ``None``。
    """
    s = str(text or "")
    if not s:
        return None
    for m in MARKERS:
        if m in s:
            return m
    return None


def label_candidates(label: Any) -> list[str]:
    """行标签的归一候选，按「剥得越少越优先」排列。

    🔴 **必须逐级候选、不能一次剥到底**：``......`` 整串都是尾部标点，
    一次 ``rstrip("。.、，,；;")`` 会把它吃成空串 ⇒ 4 行可扩位静默漏标
    （2026-08-08 实测踩到）。故先拿原样比，再剥序号前缀，最后才剥**一个**尾标点，
    且任一步产出空串即丢弃该候选。
    """
    base = _WS_RE.sub("", str(label or ""))
    stripped = _LABEL_SEQ_PREFIX_RE.sub("", base)
    tail_trimmed = stripped[:-1] if base and base[-1] in _LABEL_TAIL_PUNCT else ""
    out: list[str] = []
    for cand in (base, stripped, tail_trimmed):
        if cand and cand not in out:
            out.append(cand)
    return out


def normalize_label(label: Any) -> str:
    """行标签归一（取最深一级候选，供报告展示；判定请用 :func:`match_label_marker`）。"""
    cands = label_candidates(label)
    return cands[-1] if cands else ""


def match_label_marker(label: Any) -> str | None:
    """返回该**行标签**代表的可扩位标记词；不是可扩位返 ``None``。

    与 :func:`match_marker` 的区别（有意不同，不得统一）：
    * 这里是**恰等于**（归一候选之一），不是「包含」—— 否则 ``项目1（可改名）``
      这类示例行名、以及任何提到「预留」的业务行都会被误标成零可见内容；
    * 词表用 :data:`LABEL_MARKERS`。
    """
    cands = label_candidates(label)
    if not cands:
        return None
    normed = {_WS_RE.sub("", m): m for m in LABEL_MARKERS}
    for cand in cands:
        if cand in normed:
            return normed[cand]
    return None


def row_type_for_label(label: Any, *, default: str = "data") -> str:
    """行构造器用：可扩位标签返回 ``expandable``，否则返回 ``default``。

    供 ``scripts/fix/_note_structure_kit.data_row()`` 与各 per-cycle 幂等脚本
    构造 rows 时复用 —— 这样它们与 ``fix_note_expandable_rows.py`` 不会互相翻转。
    """
    return EXPANDABLE_ROW_TYPE if match_label_marker(label) else default


def is_zero_visible_row(row: Any) -> bool:
    """该行是否「零可见内容」—— 不渲染成数据行、不参与合计。

    单一真源：投影器（``note_sub_table_projector``）与 Word 导出
    （``note_word_exporter``）共用本谓词，禁止各写一份判据。
    """
    return (
        isinstance(row, dict)
        and str(row.get("row_type") or "") == EXPANDABLE_ROW_TYPE
    )
