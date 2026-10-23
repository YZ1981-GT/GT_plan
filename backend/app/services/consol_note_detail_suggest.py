"""合并附注明细模板：来源行名 → 模板目标行的建议算法（纯函数，无 DB）。

从 ``consol_note_detail_source_service`` 拆出（该文件超 800 行门禁）；原导入路径仍可用
（source service 重新导出 ``suggest_template_rows``）。

spec: consol-note-detail-template-and-mapping（consol-note-pull-from-standalone 收口）
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

_LABEL_WS = str.maketrans("", "", " \t\r\n\u3000")


def _label_key(label: Any) -> str:
    """行名比较键：去全部空白 + 去尾冒号（模板「合  计」与来源「合计」、「小计：」与「小计」是同一行）。"""
    s = str(label or "").translate(_LABEL_WS)
    return s.rstrip(":").rstrip("：")


# ── 全局行名别名库 ──

_ALIASES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_row_label_aliases.json"


@lru_cache(maxsize=1)
def _load_global_aliases() -> dict[str, str]:
    """加载全局别名库，返回 {变体归一键 → 标准名归一键}。"""
    if not _ALIASES_PATH.exists():
        return {}
    raw = json.loads(_ALIASES_PATH.read_bytes())
    index: dict[str, str] = {}
    for entry in raw.get("aliases", []):
        canonical = _label_key(entry.get("canonical", ""))
        if not canonical:
            continue
        for v in entry.get("variants", []):
            vk = _label_key(v)
            if vk and vk != canonical:
                index[vk] = canonical
    return index


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
    # V204: 同时收集来源行的 _pushed_row_id（集团下推的行）
    label_to_pushed_rid: dict[str, str] = {}
    for group in source_groups:
        for sr in group.get("source_rows", []):
            label = sr["label"]
            if label and label not in seen:
                all_labels.append(label)
                seen.add(label)
                # 来源行带 _pushed_row_id = 集团下推的行
                rid = sr.get("_pushed_row_id") or ""
                if rid:
                    label_to_pushed_rid[label] = rid

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

    # 构建目标行 row_id 索引（V204: 第 0 级 row_id 精确匹配）
    target_by_rid: dict[str, dict[str, Any]] = {}
    for tr in template_rows:
        trid = str(tr.get("target_row_id", "")).strip()
        if trid:
            target_by_rid[trid] = tr

    suggestions: list[dict[str, Any]] = []
    for label in all_labels:
        key = _label_key(label)

        # 0. row_id 精确匹配（集团下推的行带 _pushed_row_id）
        pushed_rid = label_to_pushed_rid.get(label, "")
        if pushed_rid and pushed_rid in target_by_rid:
            suggestions.append(_suggestion(
                label, target_by_rid[pushed_rid], "exact_id", 1.0,
            ))
            continue

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

        # 2.5. 全局别名库匹配（行名变体归一后找到等价的标准名）
        global_aliases = _load_global_aliases()
        canonical_key = global_aliases.get(key)
        if canonical_key and canonical_key in name_to_target:
            suggestions.append(_suggestion(
                label, name_to_target[canonical_key], "global_alias", 0.93,
            ))
            continue
        # 反向：来源用标准名、模板行用变体名
        if key in {v for v in global_aliases.values()}:
            for vk, ck in global_aliases.items():
                if ck == key and vk in name_to_target:
                    suggestions.append(_suggestion(
                        label, name_to_target[vk], "global_alias", 0.93,
                    ))
                    break
            else:
                pass  # 没找到，继续下一级
            if suggestions and suggestions[-1].get("match_type") == "global_alias":
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
