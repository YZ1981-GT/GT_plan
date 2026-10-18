"""右栏「当前页公式」服务端 sheet 归属精确过滤（Task 3.1 / ADR-FMC-01、§5 步骤 3）。

背景与定位
==========
`GET /api/workpapers/{wp_id}/formulas` 旧实现只按 ``wp_id`` 过滤，返回**整册**所有
sheet 的 wp_formula 行；右栏当前页视图的 sheet 归属过滤**只在前端**做
（``FormulaManagerDialog.vue : matchRowToSelectedSheet`` / ``sheetIdentityMatch.ts``，
Task 1.2）。本模块是该前端结构化精确等值的**服务端口径配套**：当请求带 ``sheet_uid``
（当前页 sheet 身份）时，服务端先**精确等值 + fail-closed** 过滤 ``items``，使右栏只含
精确当前 sheet 的行（门禁断言⑤a：右栏按 ``stable_sheet_key`` 精确相等）。

与前端 `matchRowToSelectedSheet` 同口径（单一真源）
=================================================
前端 ``sheetIdentityMatch.ts : matchRowToSelectedSheet`` 的精确归属有两条可命中维度，
本服务端过滤**逐一对应**（避免前后端口径分叉致「前端滤掉、后端放行」或反之）：

  - 维度 1 · ``stable_sheet_key`` 精确等值：行与请求身份都能归一出**非空 sheet 键**时，
    归一后 ``==``。sheet 名归一**一律复用** ``stable_key.normalize_sheet_key``
    （单一真源，ADR-FMC-01 / NIT-1，**禁另写**）。
  - 维度 2 · 结构化 sheet 编码精确等值：行的结构身份常是**展示名**（如 ``审定表E1-1``、
    ``E1-10 银行账户核对表``），而当前页身份 ``sheet_uid`` 常是**结构化 sheet 编码**
    （如 ``E1-1``）——二者归一后并不相等（``审定表E1-1`` ≠ ``E1-1``）。此时按前端同款
    ``extractSheetCodeFromName`` 从行身份与 ``sheet_uid`` 各自提取结构化编码，再**精确
    等值**（归一后 ``==``，禁 ``includes`` 子串）。

两条维度都命中不了（归一后 sheet 键为空且提不出结构化编码）→ **fail-closed 排除**，
**禁退回 ``includes`` 子串匹配**（旧 ``matchSheetCode`` 用 ``a.includes(b)||b.includes(a)``
致 ``E1-1`` 串入 ``E1-10/14/15``、``D2-1`` 串入 ``D2-10/12``，§1 #1 实测）。

结构化编码归一 / 提取
====================
``normalize_sheet_code`` / ``extract_sheet_code_from_name`` 与前端
``sheetIdentityMatch.ts : normalizeSheetCode / extractSheetCodeFromName`` 逐条对齐
（trim + 小写 + 破折号变体统一；整体是编码 / 末尾 token 边界锚定，禁子串启发式串页）。
这是**结构化编码**（sheet_code token）层面的归属判定，与 ``stable_key.py`` 的**sheet 展示名
规范化**职责不同，不是对后者的二次实现——故不违反「禁另写一套 sheet 名规范化」。

``sheet_uid`` 语义
==================
前端右栏当前页身份经 ``sheet_uid`` 传入（location identity · sheet 维度）。它承载当前页
sheet 的展示身份（通常是结构化 ``sheet_code``，也兼容展示名）；服务端按上述两维度与每行
``stable_sheet_key`` / ``sheet_name`` 比对。本模块**不**消费 workbook-instance 的 G-ID
``sheet_uid``（``sheet:order:token``），二者命名相同但语义不同——本过滤的权威维度是右栏
``stable_sheet_key`` 精确等值（门禁⑤a）与其结构化编码回退。
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.services.formula_management.stable_key import normalize_sheet_key

# ── 结构化 sheet 编码归一 / 提取（与前端 sheetIdentityMatch.ts 逐条对齐）──────────
# 破折号变体（全角破折号 —）统一为半角 `-`；下划线统一为 `-`；剥 `wp-`/`sheet-` 前缀。
_FULLWIDTH_DASH_RE = re.compile(r"—")
_UNDERSCORE_RE = re.compile(r"_")
_WP_SHEET_PREFIX_RE = re.compile(r"^(?:wp-|sheet-)")
# 结构化 sheet 编码形态：字母+数字，可带 `-数字`/`-数字字母` 段（如 e1-1 / d2-10 / e1-2a）。
_STRUCTURED_CODE_RE = re.compile(r"^[a-z]+\d+(?:-\d+[a-z]?)*$")
# 末尾结构化编码 token（如「审定表e1-1」末段 e1-1）。
_TRAILING_CODE_RE = re.compile(r"([a-z]+\d+(?:-\d+[a-z]?)*)$")


def normalize_sheet_code(value: str | None) -> str:
    """结构化 sheet 编码归一（trim + 小写 + 破折号/下划线统一为 `-`，剥 wp-/sheet- 前缀）。

    与前端 ``sheetIdentityMatch.ts : normalizeSheetCode`` 同口径。空/None → 空串。
    """
    if not value:
        return ""
    s = str(value).strip().lower()
    s = _FULLWIDTH_DASH_RE.sub("-", s)
    s = _UNDERSCORE_RE.sub("-", s)
    s = _WP_SHEET_PREFIX_RE.sub("", s)
    return s


def extract_sheet_code_from_name(sheet_name: str | None) -> str:
    """从 sheet 展示名提取结构化 sheet 编码（如「货币资金审定表E1-1」→ ``e1-1``）。

    与前端 ``sheetIdentityMatch.ts : extractSheetCodeFromName`` 同口径（fail-closed）：
    仅当展示名**整体**是结构化编码，或其**末尾 token** 是结构化编码（且前有非字母数字边界，
    防 ``e1-10`` 末段误当 ``e1-1``）时才返回；否则空串（宁可不匹配也不子串串页）。
    """
    normalized = normalize_sheet_code(sheet_name)
    if not normalized:
        return ""
    if _STRUCTURED_CODE_RE.match(normalized):
        return normalized
    m = _TRAILING_CODE_RE.search(normalized)
    if m and _STRUCTURED_CODE_RE.match(m.group(1)):
        idx = normalized.rfind(m.group(1))
        prev = normalized[idx - 1] if idx > 0 else ""
        if idx == 0 or not re.match(r"[a-z0-9]", prev):
            return m.group(1)
    return ""


def _row_sheet_key(row: Mapping[str, Any]) -> str:
    """取某公式行投影的归一 sheet 键（单一真源归一）。

    - 优先 ``stable_sheet_key``（V163 列，展示重命名不改键）。
    - 回退 ``sheet_name`` 归一（历史未回填 ``stable_sheet_key`` 的行，由 Task 1.3 回填）。
    - 两者归一后均空 → 返回空串（调用方据此 fail-closed 排除，不静默放行）。
    """
    stable = row.get("stable_sheet_key")
    key = normalize_sheet_key(stable) if stable else ""
    if key:
        return key
    return normalize_sheet_key(row.get("sheet_name"))


def _row_sheet_code(row: Mapping[str, Any]) -> str:
    """取某公式行的结构化 sheet 编码（从 stable_sheet_key 优先、回退 sheet_name 提取）。"""
    code = extract_sheet_code_from_name(row.get("stable_sheet_key"))
    if code:
        return code
    return extract_sheet_code_from_name(row.get("sheet_name"))


def row_matches_sheet_uid(row: Mapping[str, Any], sheet_uid: str | None) -> bool:
    """某公式行是否精确归属 ``sheet_uid`` 当前页（结构化精确等值 + fail-closed）。

    与前端 ``matchRowToSelectedSheet`` 两维度同口径：
      - ``sheet_uid`` 既无归一 sheet 键又提不出结构化编码 → fail-closed False。
      - 维度 1：行与请求都能归一出**非空 sheet 键** → 归一后精确等值。
      - 维度 2：从行身份与 ``sheet_uid`` 各提结构化编码（均非空）→ 精确等值。
      - 都命中不了 → fail-closed False（禁退回 ``includes`` 子串匹配）。
    """
    want_key = normalize_sheet_key(sheet_uid)
    want_code = normalize_sheet_code(sheet_uid)
    want_code_struct = want_code if _STRUCTURED_CODE_RE.match(want_code) else ""
    # 选中 sheet 本身无任何可解析结构身份 → fail-closed。
    if not want_key and not want_code_struct:
        return False

    # 维度 1 · stable_sheet_key 精确等值（展示重命名不改键，库 V163 列同口径）。
    row_key = _row_sheet_key(row)
    if row_key and want_key and row_key == want_key:
        return True

    # 维度 2 · 结构化 sheet 编码精确等值（展示名 ↔ 编码场景，如 审定表E1-1 ↔ E1-1）。
    if want_code_struct:
        row_code = _row_sheet_code(row)
        if row_code and row_code == want_code_struct:
            return True

    return False


def filter_items_by_sheet_uid(
    items: list[Mapping[str, Any]], sheet_uid: str | None
) -> list[Mapping[str, Any]]:
    """按 ``sheet_uid`` 服务端精确过滤公式行列表（右栏当前页口径）。

    - ``sheet_uid`` 为 None / 空白 → 不过滤（整册视图，返回原列表，向后兼容）。
    - 否则只保留精确归属该 sheet 的行（``row_matches_sheet_uid`` 精确等值 + fail-closed）。

    **不** 做子串匹配、**不** 在匹配不到时退回全量（否则精确化形同虚设）。
    """
    if sheet_uid is None or not str(sheet_uid).strip():
        return list(items)
    return [row for row in items if row_matches_sheet_uid(row, sheet_uid)]
