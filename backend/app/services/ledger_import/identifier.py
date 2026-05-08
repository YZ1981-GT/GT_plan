"""识别层 — 3 级识别策略 + 置信度评分（v2.1 并行联合打分）。

职责（见 design.md §4 / §28 / Sprint 5 Task 74b-d）：

- **Level 1**：Sheet 名正则识别（``SHEET_NAME_PATTERNS``，置信度 75/90）。
- **Level 2**：表头特征识别（``HEADER_ALIASES`` 别名映射 + ``KEY_COLUMNS``
  / ``RECOMMENDED_COLUMNS`` 作为单一真源，关键列 AND + 推荐列加分；置信度
  50-95，关键列驱动）。
- **Level 3**：内容样本识别（前 10 行金额列数 / 方向列 / 日期规则，0-100）。
- **聚合**  ：L1/L2/L3 **始终并行执行**，按权重（0.2/0.5/0.3）加权聚合。
- **决策树**：每级命中 / 未命中写入 ``SheetDetection.detection_evidence``。

v2.1 改进（design §28）：
- L1/L2/L3 始终并行执行，不再串行降级
- 权重可配置（从 JSON 规则文件读取）
- 列内容验证器集成（header_conf × 0.7 + content_conf × 0.3）
- 识别规则从 JSON 文件加载，支持 hot-reload

公开入口：``identify(sheet: SheetDetection) -> SheetDetection``
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from .content_validators import validate_column_content
from .detection_types import (
    KEY_COLUMNS,
    RECOMMENDED_COLUMNS,
    ColumnMatch,
    ConfidenceLevel,
    SheetDetection,
    TableType,
    classify_column_tier,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON 规则加载（Task 74d）
# ---------------------------------------------------------------------------

_RULES_FILE = Path(__file__).resolve().parents[4] / "data" / "ledger_recognition_rules.json"

_RULES: dict = {}
MATCHING_CONFIG: dict = {}
SHEET_NAME_PATTERNS: dict[TableType, list[str]] = {}


def reload_rules(rules_path: Optional[Path] = None) -> None:
    """加载/重新加载识别规则 JSON。

    支持 hot-reload：修改 JSON 后调用此函数即可生效。
    """
    global _RULES, MATCHING_CONFIG, SHEET_NAME_PATTERNS  # noqa: PLW0603

    path = rules_path or _RULES_FILE
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                _RULES = json.load(f)
            logger.info("Loaded recognition rules from %s (version=%s)", path, _RULES.get("version"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load rules from %s: %s, using defaults", path, exc)
            _RULES = {}
    else:
        logger.debug("Rules file not found at %s, using defaults", path)
        _RULES = {}

    # 解析 matching_config
    MATCHING_CONFIG.clear()
    MATCHING_CONFIG.update(_RULES.get("matching_config", {
        "exact_match_confidence": 95,
        "fuzzy_match_confidence": 70,
        "min_fuzzy_length": 3,
        "levenshtein_max_distance": 2,
        "min_levenshtein_length": 4,
        "weights": {"sheet_name": 0.2, "header": 0.5, "content": 0.3},
        "thresholds": {"high_confidence": 80, "medium_confidence": 60, "low_confidence": 30},
    }))

    # 解析 sheet_name_patterns
    SHEET_NAME_PATTERNS.clear()
    table_sigs = _RULES.get("table_signatures", {})
    for tt, sig in table_sigs.items():
        patterns = sig.get("sheet_name_patterns", [])
        if patterns:
            SHEET_NAME_PATTERNS[tt] = patterns  # type: ignore[index]

    # 如果 JSON 没有 sheet_name_patterns，使用内置默认
    if not SHEET_NAME_PATTERNS:
        SHEET_NAME_PATTERNS.update(_DEFAULT_SHEET_NAME_PATTERNS)


# 内置默认 sheet 名模式（JSON 缺失时的兜底）
_DEFAULT_SHEET_NAME_PATTERNS: dict[TableType, list[str]] = {
    "balance": [
        r"(?i)(科目余额|余额表|试算平衡|总账|general\s*ledger)",
        r"^TB\s*[0-9]{4}",
    ],
    "ledger": [
        r"(?i)(凭证|序时|日记账|明细账|detail\s*ledger|journal)",
        r"^(1|2|3|4|5|6|7|8|9|10|11|12)月(凭证)?$",
    ],
    "aux_balance": [
        r"(?i)(辅助余额|核算项目余额|辅助核算.*余额)",
    ],
    "aux_ledger": [
        r"(?i)(辅助明细|核算项目.*明细|多维.*明细)",
    ],
    "account_chart": [
        r"(?i)(科目表|账户表|chart\s*of\s*accounts)",
    ],
}

# 月拆分 sheet 的置信度略低
_FUZZY_L1_PATTERNS: frozenset[str] = frozenset(
    {r"^(1|2|3|4|5|6|7|8|9|10|11|12)月(凭证)?$"}
)


# ---------------------------------------------------------------------------
# Level 2 — 表头别名映射
# ---------------------------------------------------------------------------

# 原始别名表：standard_field → 中文 / 英文别名列表（未归一化）。
_RAW_HEADER_ALIASES: dict[str, list[str]] = {
    # 科目
    "account_code": ["科目编码", "科目代码", "账户编码", "科目编号", "Account Code"],
    "account_name": ["科目名称", "科目全名", "账户名称", "Account Name"],
    # 期初
    "opening_balance": ["年初余额", "期初余额"],
    "opening_debit": ["年初借方", "期初借方", "期初借方余额"],
    "opening_credit": ["年初贷方", "期初贷方", "期初贷方余额"],
    # 本期发生额
    "debit_amount": [
        "借方金额", "本期借方", "借方发生额", "借方本期",
        "借方本期发生额", "本期借方发生额", "借方", "Debit", "DR",
    ],
    "credit_amount": [
        "贷方金额", "本期贷方", "贷方发生额", "贷方本期",
        "贷方本期发生额", "本期贷方发生额", "贷方", "Credit", "CR",
    ],
    # 期末
    "closing_balance": ["期末余额"],
    "closing_debit": ["期末借方", "期末借方余额"],
    "closing_credit": ["期末贷方", "期末贷方余额"],
    # 凭证定位
    "voucher_date": ["日期", "记账日期", "凭证日期", "制单日期", "业务日期"],
    "voucher_no": ["凭证号", "凭证字号", "凭证编号"],
    "voucher_type": ["凭证类型", "凭证字", "字"],
    # 描述
    "summary": ["摘要", "凭证摘要", "摘要说明", "Description"],
    "preparer": ["制单人", "制单", "经办人"],
    # 辅助
    "currency_code": ["币种", "币别", "Currency"],
    "entry_seq": ["分录号", "序号", "Line", "Line No", "Line Number"],
    "level": ["级次", "科目级别", "Level"],
    # 辅助核算（混合维度列 = 单列含多维度字符串）
    "aux_dimensions": ["核算维度", "辅助核算", "核算项目", "辅助维度", "多维度"],
    # 辅助核算（独立列：类型/编码/名称分开三列）
    "aux_type": ["辅助类型", "辅助核算类型"],
    "aux_code": ["辅助编码", "核算项目编码", "辅助项目编码"],
    "aux_name": ["辅助名称", "核算项目名称", "辅助项目名称"],
    # 科目表
    "category": ["类别", "科目类别"],
    "direction": ["方向", "余额方向", "科目方向"],
    # 其他
    "company_code": ["公司代码", "公司编码", "组织编码", "核算组织", "Company Code"],
    "accounting_period": ["会计期间", "期间", "Period"],
}


# 归一化正则：剥离空白与常见符号
_NORMALIZE_RE = re.compile(
    r"[\s\-_./:：()（）【】\[\]{}|,，、。；;~!@#$%^&*+=<>?\"'`]+"
)


def _normalize(s: object) -> str:
    """归一化列名 / 别名：strip → lowercase → 剥离空白 / 标点。"""
    if s is None:
        return ""
    text = str(s).strip().lower()
    return _NORMALIZE_RE.sub("", text)


def _build_header_alias_table() -> tuple[dict[str, set[str]], dict[str, str]]:
    """构造归一化后的别名表 + 反查表。

    优先从 JSON 规则的 column_aliases 构建；缺失时用内置 _RAW_HEADER_ALIASES。
    """
    # 优先使用 JSON 规则中的 column_aliases
    source = _RULES.get("column_aliases", _RAW_HEADER_ALIASES)

    aliases_by_field: dict[str, set[str]] = {}
    reverse: dict[str, str] = {}
    for field, raw_aliases in source.items():
        normalized = {_normalize(a) for a in raw_aliases if a}
        normalized.discard("")
        aliases_by_field[field] = normalized
        for na in normalized:
            reverse.setdefault(na, field)
    return aliases_by_field, reverse


def _rebuild_aliases() -> None:
    """重建别名表（规则加载后调用）。"""
    global HEADER_ALIASES, _REVERSE_ALIAS_LOOKUP  # noqa: PLW0603
    HEADER_ALIASES, _REVERSE_ALIAS_LOOKUP = _build_header_alias_table()


HEADER_ALIASES: dict[str, set[str]] = {}
_REVERSE_ALIAS_LOOKUP: dict[str, str] = {}


def default_aliases() -> dict[str, list[str]]:
    """返回通用列别名映射的深拷贝。"""
    source = _RULES.get("column_aliases", _RAW_HEADER_ALIASES)
    return {field: list(aliases) for field, aliases in source.items()}


# ---------------------------------------------------------------------------
# Levenshtein（早退版）
# ---------------------------------------------------------------------------


def _levenshtein_leq(a: str, b: str, max_d: int = 2) -> bool:
    """判断 ``levenshtein(a, b) <= max_d``。"""
    if a == b:
        return True
    if abs(len(a) - len(b)) > max_d:
        return False
    m, n = len(a), len(b)
    if m == 0:
        return n <= max_d
    if n == 0:
        return m <= max_d
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i] + [0] * n
        row_min = curr[0]
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
            if curr[j] < row_min:
                row_min = curr[j]
        if row_min > max_d:
            return False
        prev = curr
    return prev[n] <= max_d


# ---------------------------------------------------------------------------
# Level 1
# ---------------------------------------------------------------------------


def _detect_by_sheet_name(sheet_name: str) -> tuple[TableType, int, dict]:
    """Level 1：按 sheet 名正则识别。返回 (table_type, score_0_100, evidence)。"""
    patterns_tried: dict[TableType, list[str]] = {
        tt: list(patterns) for tt, patterns in SHEET_NAME_PATTERNS.items()
    }

    name = (sheet_name or "").strip()
    for tt, patterns in SHEET_NAME_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, name):
                conf = 75 if pat in _FUZZY_L1_PATTERNS else 90
                return (
                    tt,  # type: ignore[return-value]
                    conf,
                    {
                        "patterns_tried": patterns_tried,
                        "matched_pattern": pat,
                        "matched_table": tt,
                        "confidence": conf,
                    },
                )

    return (
        "unknown",
        0,
        {
            "patterns_tried": patterns_tried,
            "matched_pattern": None,
            "matched_table": "unknown",
            "confidence": 0,
        },
    )


# ---------------------------------------------------------------------------
# Level 2
# ---------------------------------------------------------------------------

# 负向信号
_NEGATIVE_SIGNALS: dict[TableType, set[str]] = {
    "balance": {"voucher_date", "voucher_no"},
    "ledger": {"opening_balance", "closing_balance"},
    "aux_balance": {"voucher_date", "voucher_no"},
    "aux_ledger": {"opening_balance", "closing_balance"},
}

_MIN_SUBSTR_ALIAS_LEN = 3
_MIN_LEVENSHTEIN_LEN = 4

# ---------------------------------------------------------------------------
# 合并表头语义映射（P0 修复）
# ---------------------------------------------------------------------------
# 合并表头 "期末余额.借方金额" 的正确语义是 closing_debit，不是 debit_amount。
# 映射规则：group_name → {sub_name → standard_field}
# _default 用于 group 单独出现时的映射。

_MERGED_HEADER_MAPPING: dict[str, dict[str, str]] = {
    "年初余额": {
        "借方金额": "opening_debit", "贷方金额": "opening_credit",
        "借方": "opening_debit", "贷方": "opening_credit",
        "_default": "opening_balance",
    },
    "期初余额": {
        "借方金额": "opening_debit", "贷方金额": "opening_credit",
        "借方": "opening_debit", "贷方": "opening_credit",
        "_default": "opening_balance",
    },
    "期末余额": {
        "借方金额": "closing_debit", "贷方金额": "closing_credit",
        "借方": "closing_debit", "贷方": "closing_credit",
        "_default": "closing_balance",
    },
    "本期发生额": {
        "借方金额": "debit_amount", "贷方金额": "credit_amount",
        "借方": "debit_amount", "贷方": "credit_amount",
        "_default": "debit_amount",
    },
    "本年累计": {
        "借方金额": "debit_amount", "贷方金额": "credit_amount",
        "借方": "debit_amount", "贷方": "credit_amount",
        "_default": "debit_amount",
    },
    "累计发生额": {
        "借方金额": "debit_amount", "贷方金额": "credit_amount",
        "借方": "debit_amount", "贷方": "credit_amount",
        "_default": "debit_amount",
    },
}


def _match_merged_header(header: str) -> tuple[Optional[str], int, str]:
    """尝试按合并表头语义映射。

    对含 '.' 的列名（如 "期末余额.借方金额"），拆分为 group + sub，
    用 _MERGED_HEADER_MAPPING 查找精确映射。

    返回 (standard_field, confidence, source) 或 (None, 0, "") 表示未命中。
    """
    if "." not in header:
        return None, 0, ""

    dot_idx = header.index(".")
    group = header[:dot_idx].strip()
    sub = header[dot_idx + 1:].strip()

    if not group or not sub:
        return None, 0, ""

    # 在映射表中查找 group
    mapping = _MERGED_HEADER_MAPPING.get(group)
    if mapping is None:
        # 尝试归一化后查找
        for key, val in _MERGED_HEADER_MAPPING.items():
            if _normalize(key) == _normalize(group):
                mapping = val
                break

    if mapping is None:
        return None, 0, ""

    # 在 sub 映射中查找
    field = mapping.get(sub)
    if field is None:
        # 尝试归一化后查找
        norm_sub = _normalize(sub)
        for k, v in mapping.items():
            if k != "_default" and _normalize(k) == norm_sub:
                field = v
                break

    if field is None:
        # 兜底：用 _default
        field = mapping.get("_default")

    if field:
        exact_conf = MATCHING_CONFIG.get("exact_match_confidence", 95)
        return field, exact_conf, "header_exact"

    return None, 0, ""


def _match_header(header: str) -> tuple[Optional[str], int, str]:
    """把单个列名映射到 standard_field。

    返回 ``(standard_field | None, confidence, source)``。

    匹配优先级：
    1. 合并表头语义映射（dot-notation，如 "期末余额.借方金额" → closing_debit）
    2. 精确匹配（归一化后完全相等）
    3. 子串包含（最长匹配优先，避免短别名抢先命中）
    4. Levenshtein 距离
    """
    # P0: 合并表头优先处理（含 '.' 的列名）
    if "." in header:
        merged_field, merged_conf, merged_source = _match_merged_header(header)
        if merged_field:
            return merged_field, merged_conf, merged_source

    normalized = _normalize(header)
    if not normalized:
        return None, 0, "header_fuzzy"

    # 从 matching_config 读取置信度
    exact_conf = MATCHING_CONFIG.get("exact_match_confidence", 95)
    fuzzy_conf = MATCHING_CONFIG.get("fuzzy_match_confidence", 70)
    min_fuzzy = MATCHING_CONFIG.get("min_fuzzy_length", 3)
    min_lev = MATCHING_CONFIG.get("min_levenshtein_length", 4)

    # Exact
    field = _REVERSE_ALIAS_LOOKUP.get(normalized)
    if field is not None:
        return field, exact_conf, "header_exact"

    # P2: Fuzzy 子串包含 — 最长匹配优先
    best_match: tuple[Optional[str], int] = (None, 0)
    for std_field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if len(alias) < min_fuzzy:
                continue
            if alias in normalized or normalized in alias:
                # 选择最长的匹配别名（避免短别名 "借方" 抢先于 "期末借方"）
                if len(alias) > best_match[1]:
                    best_match = (std_field, len(alias))
    if best_match[0] is not None:
        return best_match[0], fuzzy_conf, "header_fuzzy"

    # Fuzzy: Levenshtein
    max_d = MATCHING_CONFIG.get("levenshtein_max_distance", 2)
    for std_field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if len(alias) < min_lev or len(normalized) < min_lev:
                continue
            if _levenshtein_leq(normalized, alias, max_d=max_d):
                return std_field, fuzzy_conf, "header_fuzzy"

    return None, 0, "header_fuzzy"


def _score_table_type(
    table_type: TableType,
    matched_std_fields: set[str],
) -> tuple[float, float, int, int, int]:
    """计算某表类型的得分。

    对 key_columns 数量少的表类型（如 account_chart 只有 2 个），
    当其他表类型也有较高匹配时，给予适当惩罚避免误判。

    支持 alternatives：如 opening_balance 可由 opening_debit + opening_credit 替代。
    """
    keys = KEY_COLUMNS.get(table_type, set())
    recs = RECOMMENDED_COLUMNS.get(table_type, set())
    if not keys:
        return 0.0, 0.0, 0, 0, 0

    # 扩展 matched_std_fields：处理 alternatives
    effective_matched = set(matched_std_fields)
    for key_col in keys:
        if key_col in effective_matched:
            continue
        # 检查 alternatives（从 JSON 规则读取）
        alts = _get_alternatives(table_type, key_col)
        for alt_group in alts:
            # alt_group 格式如 "opening_debit+opening_credit"
            alt_fields = set(alt_group.split("+"))
            if alt_fields <= matched_std_fields:
                # 所有替代字段都已匹配 → 视为该 key_col 已满足
                effective_matched.add(key_col)
                break

    matched_keys = effective_matched & keys
    key_score = len(matched_keys) / len(keys)

    matched_recs = matched_std_fields & recs
    if recs:
        rec_bonus = min(15.0, len(matched_recs) / len(recs) * 15.0)
    else:
        rec_bonus = 0.0

    # 负向信号打折
    neg = _NEGATIVE_SIGNALS.get(table_type, set())
    if matched_std_fields & neg:
        key_score *= 0.5

    # 对 key_columns 数量少的表类型（≤ 2），如果匹配的总字段数远超其 key 数量，
    # 说明数据更可能属于字段更多的表类型，给予惩罚
    if len(keys) <= 2 and len(matched_std_fields) > len(keys) + 2:
        # 匹配了很多字段但该表类型只需要 2 个 → 可能是误判
        key_score *= 0.6

    return key_score, rec_bonus, len(matched_keys), len(keys), len(matched_recs)


# 内置 alternatives 映射（JSON 规则中也有，这里作为兜底）
_BUILTIN_ALTERNATIVES: dict[str, list[str]] = {
    "opening_balance": ["opening_debit+opening_credit"],
    "closing_balance": ["closing_debit+closing_credit"],
}


def _get_alternatives(table_type: TableType, key_col: str) -> list[str]:
    """获取某关键列的替代字段组合。

    优先从 JSON 规则的 table_signatures.{type}.key_columns.{col}.alternatives 读取，
    兜底用内置 _BUILTIN_ALTERNATIVES。
    """
    # 从 JSON 规则读取
    table_sigs = _RULES.get("table_signatures", {})
    sig = table_sigs.get(table_type, {})
    key_col_defs = sig.get("key_columns", {})
    col_def = key_col_defs.get(key_col, {})
    alts = col_def.get("alternatives", [])
    if alts:
        return alts

    # 兜底
    return _BUILTIN_ALTERNATIVES.get(key_col, [])


def _detect_by_headers(
    header_cells: list[str],
    data_rows: list[list[str]] | None = None,
) -> tuple[TableType, int, list[ColumnMatch], dict]:
    """Level 2：按列名 + KEY_COLUMNS 识别表类型，集成内容验证器。

    返回 ``(table_type, confidence_0_100, column_matches, evidence)``。
    """
    # Step 1: 映射每列
    header_mappings: list[tuple[str, Optional[str], int, str]] = []
    for header in header_cells or []:
        std, conf, source = _match_header(header)
        header_mappings.append((header, std, conf, source))

    matched_std_fields: set[str] = {
        std for _h, std, _c, _s in header_mappings if std is not None
    }

    # Step 2: 评估每种表类型
    candidate_types: list[TableType] = [
        "balance", "ledger", "aux_balance", "aux_ledger", "account_chart",
    ]
    scores: dict[TableType, tuple[float, float, int, int, int]] = {}
    for tt in candidate_types:
        scores[tt] = _score_table_type(tt, matched_std_fields)

    # Step 3: 挑出最高分表类型
    def _sort_key(tt: TableType) -> float:
        sc, bn, *_ = scores[tt]
        return sc + bn / 100.0

    best_tt = max(candidate_types, key=_sort_key) if candidate_types else "unknown"
    best_score, best_bonus, mk, tk, mr = scores.get(best_tt, (0.0, 0.0, 0, 0, 0))

    if best_score < 0.5:
        winning_type: TableType = "unknown"
        winning_conf = int(80 * best_score + best_bonus)
    else:
        winning_type = best_tt
        raw = int(round(80 * best_score + best_bonus))
        winning_conf = min(raw, 95)

    # Step 4: 内容验证器集成（Task 74c）
    # 获取该表类型的 content_validator 定义
    table_sigs = _RULES.get("table_signatures", {})
    sig = table_sigs.get(winning_type, {})
    key_col_defs = sig.get("key_columns", {})
    rec_col_defs = sig.get("recommended_columns", {})
    all_col_defs = {**key_col_defs, **rec_col_defs}

    # Step 5: 组装 ColumnMatch（按最终 winning_type 判 tier）
    # 构建 alternatives 反查表：哪些字段是 key 字段的替代组成部分
    _alt_to_key: set[str] = set()
    for key_col in KEY_COLUMNS.get(winning_type, set()):
        for alt_group in _get_alternatives(winning_type, key_col):
            for alt_field in alt_group.split("+"):
                _alt_to_key.add(alt_field)

    column_matches: list[ColumnMatch] = []
    for idx, (header, std, conf, source) in enumerate(header_mappings):
        tier = classify_column_tier(std, winning_type)

        # 如果字段是 key 列的 alternative 组成部分，提升 tier 为 "key"
        if tier != "key" and std in _alt_to_key:
            tier = "key"

        # 内容验证器：如果有 data_rows 且该字段定义了 content_validator
        final_conf = conf
        if std and data_rows and std in all_col_defs:
            validator_type = all_col_defs[std].get("content_validator")
            if validator_type:
                # 提取该列的数据值
                col_values = []
                for row in data_rows[:10]:
                    if idx < len(row):
                        col_values.append(str(row[idx]) if row[idx] else "")
                    else:
                        col_values.append("")

                content_score = validate_column_content(col_values, validator_type)
                # 混合置信度：header × 0.7 + content × 0.3
                final_conf = int(conf * 0.7 + content_score * 100 * 0.3)

        column_matches.append(
            ColumnMatch(
                column_index=idx,
                column_header=str(header),
                standard_field=std,
                column_tier=tier,
                confidence=final_conf,
                source=source,  # type: ignore[arg-type]
                sample_values=[],
            )
        )

    evidence = {
        "table_type": winning_type,
        "confidence": winning_conf,
        "standard_fields_matched": sorted(matched_std_fields),
        "key_columns_hit": mk,
        "key_columns_total": tk,
        "recommended_hits": mr,
        "per_type_scores": {
            tt: {
                "key_score": round(sc, 3),
                "recommended_bonus": round(bn, 3),
                "matched_keys": m,
                "total_keys": t,
                "matched_recommended": r,
            }
            for tt, (sc, bn, m, t, r) in scores.items()
        },
    }

    return winning_type, winning_conf, column_matches, evidence


# ---------------------------------------------------------------------------
# Level 3
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(r"(20\d{2})[-/年]\d{1,2}")
_DIRECTION_VALUES: frozenset[str] = frozenset({"借", "贷", "1", "-1", "d", "c"})


def _is_numeric(value: object) -> bool:
    """判定单元格是否可解析为金额。"""
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    candidate = text.replace(",", "")
    try:
        float(candidate)
        return True
    except (TypeError, ValueError):
        return False


def _detect_by_content(
    rows: list[list[str]],
    data_start_row: int,
) -> tuple[TableType, int, dict]:
    """Level 3：扫描前几行数据样本，按特征给 balance / ledger 加权。

    返回 (table_type, score_0_100, evidence)。
    """
    data_rows: list[list[str]] = []
    if rows:
        start = max(0, int(data_start_row))
        data_rows = rows[start: start + 10]

    signals: dict[str, bool | int] = {
        "has_date_column": False,
        "has_direction_column": False,
        "numeric_column_count": 0,
    }

    if not data_rows:
        evidence = {
            "table_type": "unknown",
            "confidence": 0,
            "signals": signals,
            "data_rows_scanned": 0,
        }
        return "unknown", 0, evidence

    width = max(len(r) for r in data_rows)

    has_date_col = False
    has_direction_col = False
    numeric_col_count = 0

    for c in range(width):
        column_values: list[str] = []
        for row in data_rows:
            if c < len(row):
                column_values.append(str(row[c]) if row[c] is not None else "")
            else:
                column_values.append("")

        if not has_date_col:
            for v in column_values:
                if v and _DATE_PATTERN.search(v):
                    has_date_col = True
                    break

        if not has_direction_col:
            direction_hits = sum(
                1 for v in column_values if v.strip().lower() in _DIRECTION_VALUES
            )
            non_empty = sum(1 for v in column_values if v.strip())
            if direction_hits > 0 and non_empty > 0:
                has_direction_col = True

        numeric_hits = sum(1 for v in column_values if _is_numeric(v))
        if numeric_hits > 0:
            numeric_col_count += 1

    signals["has_date_column"] = has_date_col
    signals["has_direction_column"] = has_direction_col
    signals["numeric_column_count"] = numeric_col_count

    ledger_weight = 0.0
    balance_weight = 0.0
    if has_date_col:
        ledger_weight += 0.3
    if has_direction_col:
        ledger_weight += 0.3
    if numeric_col_count >= 4:
        balance_weight += 0.3

    if ledger_weight == 0 and balance_weight == 0:
        evidence = {
            "table_type": "unknown",
            "confidence": 0,
            "signals": signals,
            "data_rows_scanned": len(data_rows),
        }
        return "unknown", 0, evidence

    if ledger_weight >= balance_weight:
        weight = ledger_weight
        best: TableType = "ledger"
    else:
        weight = balance_weight
        best = "balance"

    # 映射到 0-100 分数
    # 0.3 → 30, 0.6 → 50, 0.9 → 59 (cap)
    confidence = min(59, int(30 + (weight - 0.3) / 0.3 * 15))
    confidence = max(confidence, 30)

    evidence = {
        "table_type": best,
        "confidence": confidence,
        "signals": signals,
        "data_rows_scanned": len(data_rows),
        "ledger_weight": round(ledger_weight, 2),
        "balance_weight": round(balance_weight, 2),
    }
    return best, confidence, evidence


# ---------------------------------------------------------------------------
# 主入口 — 并行聚合三级 + confidence_level 判定（v2.1）
# ---------------------------------------------------------------------------


def _classify_confidence_level(conf: int) -> ConfidenceLevel:
    thresholds = MATCHING_CONFIG.get("thresholds", {})
    high = thresholds.get("high_confidence", 80)
    medium = thresholds.get("medium_confidence", 60)
    low = thresholds.get("low_confidence", 30)
    if conf >= high:
        return "high"
    if conf >= medium:
        return "medium"
    if conf >= low:
        return "low"
    return "manual_required"


def _resolve_header_cells(sheet: SheetDetection) -> list[str]:
    """从 SheetDetection 中取 header_cells。"""
    evidence_cells = sheet.detection_evidence.get("header_cells")
    if evidence_cells:
        return [str(c) if c is not None else "" for c in evidence_cells]

    if sheet.preview_rows and 0 <= sheet.header_row_index < len(sheet.preview_rows):
        row = sheet.preview_rows[sheet.header_row_index]
        return [str(c) if c is not None else "" for c in row]

    return []


def identify(sheet: SheetDetection) -> SheetDetection:
    """对 detector 返回的 SheetDetection 应用 3 级并行识别。

    v2.1 改进：L1/L2/L3 始终并行执行，按权重加权聚合最终置信度。
    """
    # 获取权重配置
    weights = MATCHING_CONFIG.get("weights", {"sheet_name": 0.2, "header": 0.5, "content": 0.3})

    # ---- Level 1: Sheet 名 + 文件名（P1 修复：文件名也含强信号）
    l1_type, l1_score, l1_evidence = _detect_by_sheet_name(sheet.sheet_name)

    # P1: 如果 sheet 名无信号，尝试从文件名获取 L1 信号
    if l1_type == "unknown" and sheet.file_name:
        # 提取文件名主体（去掉路径和扩展名，去掉 "archive.zip!" 前缀）
        fname = sheet.file_name
        if "!" in fname:
            fname = fname.split("!")[-1]
        fname_stem = os.path.splitext(os.path.basename(fname))[0]
        fn_type, fn_score, fn_evidence = _detect_by_sheet_name(fname_stem)
        if fn_type != "unknown":
            l1_type = fn_type
            # 文件名信号略弱于 sheet 名（-10）
            l1_score = max(fn_score - 10, 65)
            l1_evidence = {**fn_evidence, "source": "file_name", "file_name": fname_stem}

    # ---- Level 2: 表头特征 + 内容验证器
    header_cells = _resolve_header_cells(sheet)
    data_rows = sheet.preview_rows[sheet.data_start_row:] if sheet.preview_rows else []
    l2_type, l2_score, column_matches, l2_evidence = _detect_by_headers(header_cells, data_rows)

    # ---- Level 3: 内容特征（始终执行，不再条件触发）
    l3_type, l3_score, l3_evidence = _detect_by_content(
        sheet.preview_rows, sheet.data_start_row
    )

    # ---- 加权聚合（v2.1 并行联合打分）
    # 收集每个 table_type 的加权投票
    votes: dict[TableType, float] = {}
    vote_details: list[dict] = []

    for tt, score, weight_key, level_name in [
        (l1_type, l1_score, "sheet_name", "L1"),
        (l2_type, l2_score, "header", "L2"),
        (l3_type, l3_score, "content", "L3"),
    ]:
        w = weights.get(weight_key, 0.3)
        if tt != "unknown" and score > 0:
            weighted = score * w / 100.0
            votes[tt] = votes.get(tt, 0.0) + weighted
            vote_details.append({"level": level_name, "type": tt, "score": score, "weight": w, "weighted": round(weighted, 4)})
        else:
            vote_details.append({"level": level_name, "type": tt, "score": score, "weight": w, "weighted": 0})

    # 选出最终 table_type
    total_weight = sum(weights.values())
    conflict = False

    # S6-9: L1 强信号锁定机制——sheet 名命中且置信度 ≥ l1_lock_threshold 时，
    # 锁定 table_type 为 L1 的判断，不让 L2/L3 否决（典型场景：和平物流的
    # "余额表" sheet 被非标准列结构让 L2 误投 ledger）
    l1_lock_threshold = MATCHING_CONFIG.get("l1_lock_threshold", 85)
    l1_locked = (
        l1_type != "unknown"
        and l1_score >= l1_lock_threshold
    )

    if votes:
        if l1_locked:
            final_type = l1_type  # type: ignore[assignment]
        else:
            final_type: TableType = max(votes, key=lambda k: votes[k])
        # 计算最终置信度：
        # 使用实际贡献权重归一化，确保单级别强信号也能给出合理分数
        contributing_weight = 0.0
        for tt, score, weight_key, _ in [
            (l1_type, l1_score, "sheet_name", "L1"),
            (l2_type, l2_score, "header", "L2"),
            (l3_type, l3_score, "content", "L3"),
        ]:
            if tt != "unknown" and score > 0:
                contributing_weight += weights.get(weight_key, 0.3)

        # 归一化方式：按贡献权重归一化，但不超过 95
        # 这样 L1 alone (90 * 0.2 / 0.2) = 90, L2 alone (95 * 0.5 / 0.5) = 95
        if l1_locked:
            # L1 锁定：置信度直接用 L1 score（封顶 95）
            final_conf = int(min(l1_score, 95))
        elif contributing_weight > 0:
            final_conf = int(min(votes[final_type] * 100 / contributing_weight, 95))
        else:
            final_conf = 0

        # 但如果只有弱信号（L3 alone），cap 在 59
        if contributing_weight <= weights.get("content", 0.3) and l1_type == "unknown" and l2_type == "unknown":
            final_conf = min(final_conf, 59)

        final_conf = max(final_conf, 20)

        # 检测冲突：L1 和 L2 都有结果但不同
        if l1_type != "unknown" and l2_type != "unknown" and l1_type != l2_type:
            conflict = True
    else:
        final_type = "unknown"
        final_conf = 0

    # ---- 如果 final_type 与 L2 给的不同，需重算 column_tier
    if final_type != l2_type:
        column_matches = [
            cm.model_copy(
                update={
                    "column_tier": classify_column_tier(cm.standard_field, final_type),
                }
            )
            for cm in column_matches
        ]

    confidence_level = _classify_confidence_level(final_conf)

    detection_evidence: dict = {
        "header_cells": header_cells,
        "merged_header": bool(sheet.detection_evidence.get("merged_header", False)),
        "level1": {
            "table_type": l1_type,
            "confidence": l1_score,
            **{k: v for k, v in l1_evidence.items() if k != "confidence"},
        },
        "level2": {
            "table_type": l2_type,
            "confidence": l2_score,
            **{k: v for k, v in l2_evidence.items() if k != "confidence"},
        },
        "level3": {
            "table_type": l3_type,
            "confidence": l3_score,
            **{k: v for k, v in l3_evidence.items() if k != "confidence"},
        },
        "final_choice": {
            "source": "l1_locked" if l1_locked else "weighted_aggregation",
            "table_type": final_type,
            "confidence": final_conf,
            "conflict": conflict,
            "l1_locked": l1_locked,
            "l1_lock_threshold": l1_lock_threshold,
            "votes": {str(k): round(v, 4) for k, v in votes.items()},
            "vote_details": vote_details,
            "weights": weights,
        },
    }

    # 保留原有 evidence 中其他不冲突的字段
    for k, v in sheet.detection_evidence.items():
        if k not in detection_evidence:
            detection_evidence[k] = v

    return sheet.model_copy(
        update={
            "table_type": final_type,
            "table_type_confidence": final_conf,
            "confidence_level": confidence_level,
            "column_mappings": column_matches,
            "detection_evidence": detection_evidence,
        }
    )


# ---------------------------------------------------------------------------
# 模块初始化：加载规则 + 构建别名表
# ---------------------------------------------------------------------------

reload_rules()
_rebuild_aliases()


__all__ = [
    "identify",
    "SHEET_NAME_PATTERNS",
    "HEADER_ALIASES",
    "MATCHING_CONFIG",
    "default_aliases",
    "reload_rules",
]
