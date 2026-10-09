"""wp_formula 稳定键推导（P0-项1 · spec d4-dual-mode-formula-governance）。

背景与目标
==========
``wp_formula`` 既有业务 identity = ``(wp_id, sheet_name, target_cell)``。其中：
  - ``sheet_name`` 是**展示名**（如 "五、1 审定表D2-1"），带排序前缀、可被重命名 →
    展示名一变，identity 变，公式与单元格失联（孤儿）。
  - ``target_cell`` 是 A1 地址（如 "B5"），本身稳定，但与 preset 版本的布局耦合。

本模块提供**单一真源**的稳定键推导，供 service 写入、迁移回填、PBT 三处共用（不各写一份）：
  - ``stable_sheet_key``：对 sheet 展示名做规范化（去排序前缀 + 折叠空白 + 去常见 sheet 级后缀
    差异），使**纯展示重命名不改键**。
  - ``row_key`` / ``field_key``：把 A1 地址 ``target_cell`` 拆为 行号 + 列字母
    （"B5" → field_key="B", row_key="5"）。无法解析为 A1 的（命名单元/自定义 token）显式
    标记 ``needs_review``，**不静默丢**。

``preset_version`` **不进** identity（本模块从不消费它）；``definition_version`` 是公式**定义**
版本（每次保存定义递增），与 identity 正交，两者职责不同不可混用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A1 地址：列字母（1+）+ 行号（1+），大小写不敏感（列统一大写）。
_A1_RE = re.compile(r"^([A-Za-z]+)(\d+)$")

# sheet 展示名的排序/编号前缀（如 "五、1 "、"1. "、"（一）"、"3、"），规范化时剥离。
#
# 🔴 2026-09-22 修复（PBT test_property_key_stable_across_sheet_rename 抽到反例
#    base='0'：'0' vs '一、0'）：原式为
#      [一二三四五六七八九十]+[、.．]?\d*[、.．]?
#    其中 `\d*` 本意是吃掉 "五、1 " 这类**子序号**，但它会贪心吃掉**正文** ——
#    当正文以数字开头时（"一、0" 里的 "0" 就是正文），整串被剥成空串，于是
#    stable_sheet_key='' 且 needs_review=True，而未加前缀的 "0" 得到 '0' ⇒
#    「加展示前缀不得改键」这条 identity 不变量被破坏（公式与单元格失联的根源）。
#
#    区分「子序号」与「正文」的判据就是**分隔符**：`_ORDER_PREFIXES` 里的 "五、1 "
#    带尾随空格，而 "五、审定表D2-1" 的正文紧跟标点。因此子序号 `\d+` 只在其后紧跟
#    空白或 `、.．` 时才并入前缀；否则这串数字属于正文，必须保留。
#    同时要求中文序号后**必须**有 `、.．`（原式的 `[、.．]?` 会把 "五1 " 也当前缀，
#    剥得过宽），收窄后更不易误吞正文。
_ORDER_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"[一二三四五六七八九十]+[、.．](?:\s*\d+(?=[\s、.．])[、.．]?)?"
    r"|\d+[、.．]"
    r"|[（(][一二三四五六七八九十\d]+[)）]"
    r")\s*"
)


@dataclass(frozen=True)
class StableKey:
    """wp_formula 稳定键三元组 + 可转换标记。"""
    stable_sheet_key: str
    row_key: str | None
    field_key: str
    needs_review: bool  # target_cell 无法安全解析为 A1（命名单元等）→ 显式标记，人工复核


def normalize_sheet_key(sheet_name: str | None) -> str:
    """把 sheet 展示名规范化为稳定 sheet 键（纯展示重命名不改键）。

    规则（幂等、确定性）：
      1. 剥离前导排序/编号前缀（"五、1 " / "1." / "（一）"）。
      2. 折叠内部连续空白（含全角空格）为单个半角空格，首尾 trim。
      3. 大小写不变（sheet 名可能含大小写敏感的 wp_code 如 "D2-1"）。

    空/None → 空串（调用方据此可判 needs_review）。
    """
    if not sheet_name:
        return ""
    s = str(sheet_name)
    s = _ORDER_PREFIX_RE.sub("", s)
    s = re.sub(r"[\s\u3000]+", " ", s).strip()
    return s


def parse_cell(target_cell: str | None) -> tuple[str | None, str, bool]:
    """把 A1 地址拆为 (row_key, field_key, needs_review)。

    - "B5"  → ("5", "B", False)
    - "aa12"→ ("12", "AA", False)   （列统一大写）
    - 非 A1（如命名单元 "净额" / 空）→ (None, <原值 或 空>, True)  显式标记 needs_review。
    """
    if not target_cell or not str(target_cell).strip():
        return None, "", True
    raw = str(target_cell).strip()
    m = _A1_RE.match(raw)
    if not m:
        # 无法解析为 A1：保留原值作 field_key，标 needs_review（不丢弃）
        return None, raw, True
    col, row = m.group(1).upper(), m.group(2)
    return row, col, False


def derive_stable_key(sheet_name: str | None, target_cell: str | None) -> StableKey:
    """由 (sheet_name, target_cell) 推导稳定键（单一真源）。

    needs_review = True 当 sheet 键为空 或 target_cell 无法解析为 A1。这类行在迁移时
    显式打标（stable_sheet_key/row_key/field_key 仍尽力填），供人工复核，绝不静默丢。
    """
    sheet_key = normalize_sheet_key(sheet_name)
    row_key, field_key, cell_review = parse_cell(target_cell)
    needs_review = cell_review or not sheet_key
    return StableKey(
        stable_sheet_key=sheet_key,
        row_key=row_key,
        field_key=field_key,
        needs_review=needs_review,
    )
