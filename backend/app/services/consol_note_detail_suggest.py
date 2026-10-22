"""合并附注明细模板：来源行名 → 模板目标行的建议算法（纯函数，无 DB）。

从 ``consol_note_detail_source_service`` 拆出（该文件超 800 行门禁）；原导入路径仍可用
（source service 重新导出 ``suggest_template_rows``）。

spec: consol-note-detail-template-and-mapping（consol-note-pull-from-standalone 收口）
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

_LABEL_WS = str.maketrans("", "", " \t\r\n\u3000")


def _label_key(label: Any) -> str:
    """行名比较键：去掉全部空白（模板「合  计」与来源「合计」是同一行）。"""
    return str(label or "").translate(_LABEL_WS)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 模板建议算法（R1.1 / D§六）
# ═══════════════════════════════════════════════════════════════════════════════


def suggest_template_rows(
    source_groups: list[dict[str, Any]],
    *,
    existing_template_rows: list[dict[str, Any]] | None = None,
    history_mappings: list[dict[str, Any]] | None = None,
    rule_template_suggestions: list[dict[str, Any]] | None = None,
    previous_year_suggestions: list[dict[str, Any]] | None = None,
    fuzzy_threshold: float = 0.75,
) -> list[dict[str, Any]]:
    """生成模板建议行列表。

    每条来源标签经七级匹配：
    1. 精确匹配目标 canonical_name
    2. 别名匹配 aliases
    3. 规则模板库匹配（rule_template_suggestions，confidence=0.92）
    4. 上年同集团项目匹配（previous_year_suggestions，confidence=0.88）
    5. 模糊匹配（SequenceMatcher ≥ threshold）
    6. 历史规则复用
    7. 未匹配 → 建议新增

    返回 ``[{source_label, suggested_target, confidence, match_type, candidates}]``
    """
    template_rows = existing_template_rows or []
    history = history_mappings or []

    # 构建规则模板建议索引（source_label → suggestion）
    rule_tmpl_index: dict[str, dict[str, Any]] = {}
    for s in (rule_template_suggestions or []):
        sl = str(s.get("source_label", "")).strip()
        if sl and s.get("suggested_target"):
            rule_tmpl_index[sl] = s

    # 构建上年项目建议索引
    prev_year_index: dict[str, dict[str, Any]] = {}
    for s in (previous_year_suggestions or []):
        sl = str(s.get("source_label", "")).strip()
        if sl and s.get("suggested_target"):
            prev_year_index[sl] = s

    # 收集所有来源标签（去重保序）
    all_labels: list[str] = []
    seen: set[str] = set()
    for group in source_groups:
        for sr in group.get("source_rows", []):
            label = sr["label"]
            if label and label not in seen:
                all_labels.append(label)
                seen.add(label)

    # 构建目标索引（按去空白的行名比较：模板「合  计」与来源「合计」是同一行）
    name_to_target: dict[str, dict[str, Any]] = {}
    alias_to_target: dict[str, dict[str, Any]] = {}
    for tr in template_rows:
        cn = _label_key(tr.get("canonical_name", ""))
        if cn:
            name_to_target[cn] = tr
        for alias in tr.get("aliases", []):
            a = _label_key(alias)
            if a:
                alias_to_target[a] = tr

    # 历史映射索引
    history_index: dict[str, str] = {}
    for hm in history:
        sl = str(hm.get("source_label", "")).strip()
        trid = str(hm.get("target_row_id", "")).strip()
        if sl and trid:
            history_index[sl] = trid

    suggestions: list[dict[str, Any]] = []
    for label in all_labels:
        key = _label_key(label)
        # 1. 精确匹配 canonical_name
        if key in name_to_target:
            suggestions.append(_suggestion(
                label, name_to_target[key], "exact", 1.0,
            ))
            continue

        # 2. 别名匹配
        if key in alias_to_target:
            suggestions.append(_suggestion(
                label, alias_to_target[key], "alias", 0.95,
            ))
            continue

        # 3. 规则模板库匹配（confidence=0.92）
        if label in rule_tmpl_index:
            s = rule_tmpl_index[label]
            suggestions.append({
                "source_label": label,
                "suggested_target": s["suggested_target"],
                "confidence": s.get("confidence", 0.92),
                "match_type": "rule_template",
                "candidates": s.get("candidates", []),
                **({"template_id": s["template_id"]} if "template_id" in s else {}),
            })
            continue

        # 4. 上年同集团项目匹配（confidence=0.88）
        if label in prev_year_index:
            s = prev_year_index[label]
            suggestions.append({
                "source_label": label,
                "suggested_target": s["suggested_target"],
                "confidence": s.get("confidence", 0.88),
                "match_type": "previous_year",
                "candidates": s.get("candidates", []),
            })
            continue

        # 5. 模糊匹配
        best_ratio = 0.0
        best_target: dict[str, Any] | None = None
        candidates: list[dict[str, Any]] = []
        for tr in template_rows:
            cn = str(tr.get("canonical_name", ""))
            ratio = SequenceMatcher(None, label, cn).ratio()
            if ratio >= fuzzy_threshold:
                candidates.append({"target": tr, "ratio": round(ratio, 3)})
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_target = tr
            for alias in tr.get("aliases", []):
                r2 = SequenceMatcher(None, label, str(alias)).ratio()
                if r2 >= fuzzy_threshold and r2 > best_ratio:
                    best_ratio = r2
                    best_target = tr
                    candidates.append({"target": tr, "ratio": round(r2, 3)})

        if best_target is not None:
            suggestions.append(_suggestion(
                label, best_target, "fuzzy", round(best_ratio, 3), candidates,
            ))
            continue

        # 6. 历史规则复用
        if label in history_index:
            target_row_id = history_index[label]
            # 在模板中找到对应行
            for tr in template_rows:
                if str(tr.get("target_row_id", "")) == target_row_id:
                    suggestions.append(_suggestion(
                        label, tr, "history", 0.85,
                    ))
                    break
            else:
                suggestions.append({
                    "source_label": label,
                    "suggested_target": None,
                    "confidence": 0.0,
                    "match_type": "manual",
                    "candidates": [],
                })
            continue

        # 7. 未匹配
        suggestions.append({
            "source_label": label,
            "suggested_target": None,
            "confidence": 0.0,
            "match_type": "manual",
            "candidates": [],
        })

    return suggestions


def _suggestion(
    label: str,
    target: dict[str, Any],
    match_type: str,
    confidence: float,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "source_label": label,
        "suggested_target": {
            "target_row_id": target.get("target_row_id"),
            "canonical_name": target.get("canonical_name"),
        },
        "confidence": confidence,
        "match_type": match_type,
        "candidates": candidates or [],
    }
