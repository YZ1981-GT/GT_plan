"""ACNR L0 Grammar — 语法常量与工具函数

加载 grammar_v1.json 并导出核心常量，供全平台消费。

单一真源：backend/data/acnr/grammar_v1.json (R12.1)
消费者通过本模块 import，禁止在其他文件中重复定义 (R12.2, R12.3)。

Requirements: 9, 10, 11, 12
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

# ─── Load grammar_v1.json ────────────────────────────────────────────────────

# grammar.py 位于 backend/app/services/acnr/grammar.py
# parents[0] = backend/app/services/acnr/
# parents[1] = backend/app/services/
# parents[2] = backend/app/
# parents[3] = backend/
# 目标: backend/data/acnr/grammar_v1.json
_GRAMMAR_FILE = (
    Path(__file__).resolve().parents[3] / "data" / "acnr" / "grammar_v1.json"
)

_grammar: dict = {}
if _GRAMMAR_FILE.exists():
    with open(_GRAMMAR_FILE, encoding="utf-8") as f:
        _grammar = json.load(f)


# ─── Grammar Validation (Req-2) ─────────────────────────────────────────────

def _validate_grammar(data: dict) -> list[str]:
    """校验 grammar_v1.json 内容完整性，返回缺失项清单。

    校验项 (Req-2.3):
    - 至少 5 个域定义 (uri_profiles)
    - 至少 11 个命名空间映射 (index_namespaces)
    - STANDARD_WP_CODE_RE 常量存在
    - registry_version (即顶层 version) 非空
    """
    missing: list[str] = []

    # 1. registry_version 非空
    version = data.get("version")
    if not version:
        missing.append("registry_version (顶层 'version' 字段缺失或为空)")

    # 2. 至少 5 个域定义
    uri_profiles = data.get("uri_profiles", {})
    if len(uri_profiles) < 5:
        missing.append(
            f"uri_profiles 域定义不足: 需要 ≥5, 实际 {len(uri_profiles)}"
        )

    # 3. 至少 11 个命名空间映射
    index_ns = data.get("index_namespaces", {})
    if len(index_ns) < 11:
        missing.append(
            f"index_namespaces 命名空间不足: 需要 ≥11, 实际 {len(index_ns)}"
        )

    # 4. STANDARD_WP_CODE_RE 常量存在
    constants = data.get("constants", {})
    if not constants.get("STANDARD_WP_CODE_RE"):
        missing.append("constants.STANDARD_WP_CODE_RE 缺失或为空")

    return missing


def validate_grammar_on_startup() -> None:
    """启动时校验 grammar_v1.json 完整性。

    由 lifespan 调用。文件不存在/JSON 解析失败/校验项缺失 → sys.exit(1)。
    (Req-2.1, Req-2.2, Req-2.4)
    """
    if not _GRAMMAR_FILE.exists():
        print(
            f"[FATAL] grammar_v1.json 不存在: {_GRAMMAR_FILE}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        with open(_GRAMMAR_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"[FATAL] grammar_v1.json 加载失败: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    missing = _validate_grammar(data)
    if missing:
        print(
            "[FATAL] grammar_v1.json 校验失败，缺失项:",
            file=sys.stderr,
        )
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        sys.exit(1)


# ─── Constants (R12.1, R12.2) ────────────────────────────────────────────────

# 标准底稿码判定正则 — 单一常量，所有消费者必须从此处 import
# 值来自 grammar_v1.json constants.STANDARD_WP_CODE_RE = "^[A-S]\d"
STANDARD_WP_CODE_RE: re.Pattern[str] = re.compile(
    _grammar.get("constants", {}).get("STANDARD_WP_CODE_RE", r"^[A-S]\d"),
    re.IGNORECASE,
)

# 字符串形式（供需要组合更复杂正则的场景使用）
STANDARD_WP_CODE_RE_STR: str = _grammar.get("constants", {}).get(
    "STANDARD_WP_CODE_RE", r"^[A-S]\d"
)


def is_standard_wp_code(wp_code: str) -> bool:
    """判断 wp_code 是否为标准底稿编码（[A-S] 开头 + 数字）。

    R12.4: J1/S3 判为标准底稿。
    R12.5: 消除旧 [A-I]\\d 误判（I 之后的 J~S 循环也是标准）。
    """
    return bool(STANDARD_WP_CODE_RE.search((wp_code or "").strip()))


# ─── formula_ref ↔ URI 互转 (R10.3, 无损往返) ────────────────────────────────
#
# 这是 ACNR grammar 层的互转入口，WP/PREV 委托 parse_wp_formula() 结构化解析。
# 非 WP/PREV 域（TB/ROW/NOTE/AUX/REPORT）委托 address_registry 原有逻辑。
#
# URI Profiles (grammar_v1.json):
#   standard:    wp://{parent}/{sheet_name}#{cell}
#   custom_flat: wp://{wp_code}/{cell}
# ─────────────────────────────────────────────────────────────────────────────


def formula_ref_to_uri(formula_ref: str) -> Optional[str]:
    """将 formula_ref 转为 URI，保留第三参（R10.3 无损往返铁律）。

    WP/PREV 域使用 parse_wp_formula() 结构化解析：
      - 3 参 standard: WP('D2','明细表D2-2','E100') → wp://D2/明细表D2-2#E100
      - 2 参 custom_flat: WP('CUST-01','B7') → wp://CUST-01/B7
      - 2 参 standard sheet-level: WP('D2','明细表D2-2') → wp://D2/明细表D2-2
      - PREV 3 参: PREV('D2','审定表D2-1','审定数') → wp://D2/审定表D2-1#审定数
      - PREV 2 参 (TB 语义): PREV('1002','期末余额') → tb://1002#期末余额

    非 WP/PREV 域委托 address_registry.formula_ref_to_uri()。

    Requirements: 10.3
    """
    if not formula_ref or not formula_ref.strip():
        return None

    stripped = formula_ref.strip()
    upper = stripped.upper()

    # WP/PREV 域：委托 parse_wp_formula 精确解析
    if upper.startswith("WP(") or upper.startswith("PREV("):
        from app.services.formula_grammar import (
            FormulaParseError,
            FormulaProfile,
            parse_wp_formula,
        )

        try:
            parsed = parse_wp_formula(stripped)
        except FormulaParseError:
            return None

        if parsed.arity == 3:
            # 3 参 standard: wp://parent/sheet_name#cell_or_semantic
            parent, sheet_name, cell_or_semantic = parsed.args
            return f"wp://{parent}/{sheet_name}#{cell_or_semantic}"
        elif parsed.arity == 2:
            if parsed.profile == FormulaProfile.CUSTOM_FLAT.value:
                # 2 参 custom_flat: wp://wp_code/cell
                wp_code, cell = parsed.args
                return f"wp://{wp_code}/{cell}"
            else:
                # 2 参 standard sheet-level: wp://parent/sheet_name
                # OR PREV 2-arg TB semantics
                if parsed.func_name == "PREV":
                    # PREV 2 参 → TB 语义 (prior year balance)
                    code, col = parsed.args
                    return f"tb://{code}#{col}"
                else:
                    # WP 2 参 standard sheet-level
                    parent, sheet_name = parsed.args
                    return f"wp://{parent}/{sheet_name}"
        return None

    # 非 WP/PREV 域：委托 address_registry 原有逻辑
    from app.services.address_registry import (
        formula_ref_to_uri as _legacy_formula_ref_to_uri,
    )

    return _legacy_formula_ref_to_uri(stripped)


def uri_to_formula_ref(uri: str) -> Optional[str]:
    """将 URI 转回 formula_ref（R10.3 无损往返铁律）。

    WP 域 URI 解析规则：
      - wp://parent/sheet_name#cell → WP('parent','sheet_name','cell') (3 参 standard)
      - wp://parent/sheet_name      → WP('parent','sheet_name')       (2 参 standard)
      - wp://wp_code/cell           → WP('wp_code','cell')            (2 参 custom_flat)

    对 wp 域：path+cell 都存在 → 3 参；仅 path → 2 参。
    非 wp 域委托 address_registry.uri_to_formula_ref()。

    Requirements: 10.3
    """
    if not uri or not uri.strip():
        return None

    stripped = uri.strip()

    # WP 域：自行解析以保证无损往返
    if stripped.startswith("wp://"):
        rest = stripped[5:]  # 去掉 "wp://"

        # 解析 source/path#cell 结构
        cell = ""
        if "#" in rest:
            before_hash, cell = rest.rsplit("#", 1)
        else:
            before_hash = rest

        # 解析 source/path
        if "/" in before_hash:
            source, path = before_hash.split("/", 1)
        else:
            source = before_hash
            path = ""

        # xref 特殊处理（不转公式）
        if path == "xref" and cell:
            return None

        if cell and path:
            # 3 参 standard: WP('source','path','cell')
            return f"WP('{source}','{path}','{cell}')"
        elif path:
            # 2 参: WP('source','path')
            return f"WP('{source}','{path}')"
        elif cell:
            # 兼容 legacy wp://source#cell → WP('source','cell')
            return f"WP('{source}','{cell}')"
        else:
            # 仅 source，无法构造合法 WP 公式
            return None

    # 非 wp 域：委托 address_registry 原有逻辑
    from app.services.address_registry import (
        uri_to_formula_ref as _legacy_uri_to_formula_ref,
    )

    return _legacy_uri_to_formula_ref(stripped)
