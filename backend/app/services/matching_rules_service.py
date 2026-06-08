"""企业子类型推荐服务（对照表规则集成）。

读取 ``backend/data/audit_report_templates/matching_rules.json``，根据项目属性
推荐 ``company_subtype``（type_a/type_b/type_c/type_d）。

规则评估（requirements §7）：
  - 7.2：项目属性唯一匹配某规则 → 返回该 subtype（高 confidence）
  - 7.5：存在歧义（多个候选 subtype）→ 返回全部候选供用户手动选择
  - 7.7：规则推荐优先于需求 1.4 的 listed/non_listed fallback
  - 1.4：无匹配兜底 — listed → type_a，non_listed → type_d

Validates: Requirements 1.4, 7.1, 7.2, 7.5, 7.7
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# matching_rules.json 路径（与 manifest 资产同目录）
_RULES_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "audit_report_templates"
    / "matching_rules.json"
)

# 合法子类型集合
_VALID_SUBTYPES = {"type_a", "type_b", "type_c", "type_d"}

# 需求 1.4 fallback 默认值（matching_rules.json 缺失时兜底）
_DEFAULT_FALLBACK = {"listed": "type_a", "non_listed": "type_d"}


@dataclass
class BackfillResult:
    """存量项目企业子类型回填结果（需求 1.7/1.8）。

    回填顺序（needs_confirmation 控制「待确认企业子类型」横幅）：
      ① 项目已有 ``company_subtype``（用户手动设置）→ 直接采用，``confirmed=True``，不显示横幅
      ② ``matching_rules.json`` 按项目属性推荐 → 作为**建议值**返回，``confirmed=False``，显示横幅
      ③ ``company_type`` fallback（listed→type_a / non_listed→type_d）→ 建议值，``confirmed=False``，显示横幅

    关键约束（需求 1.7 ③ / 1.8）：
      - 当 subtype 来自推断（rule/fallback/default）时 **不视为用户确认**，
        ``needs_confirmation=True``，前端展示非阻断横幅引导用户确认；
        调用方**不得**把未确认推断当作用户选择静默落库。
      - 用户已手动设置时 ``confirmed=True`` 且 ``needs_confirmation=False``，优先于自动推断。
    """

    subtype: str | None
    confirmed: bool
    needs_confirmation: bool
    source: str  # user | rule | fallback | default
    confidence: str = "none"
    candidates: list[str] = field(default_factory=list)
    matched_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "subtype": self.subtype,
            "confirmed": self.confirmed,
            "needs_confirmation": self.needs_confirmation,
            "source": self.source,
            "confidence": self.confidence,
            "candidates": self.candidates,
            "matched_rules": self.matched_rules,
        }


@dataclass
class RecommendResult:
    """推荐结果。

    - subtype: 最终推荐的企业子类型（唯一匹配/最高优先级候选/fallback）
    - confidence: ``high`` 唯一匹配 | ``low`` 歧义或 fallback | ``none`` 无任何信号
    - candidates: 所有候选 subtype（歧义时 >1；唯一时 1；fallback 时含兜底值）
    - matched_rules: 命中的规则 id（便于前端展示「系统建议来源」）
    - source: ``rule`` 规则命中 | ``fallback`` 兜底 | ``default`` 无信息默认
    """

    subtype: str | None
    confidence: str
    candidates: list[str] = field(default_factory=list)
    matched_rules: list[str] = field(default_factory=list)
    source: str = "rule"

    def to_dict(self) -> dict:
        return {
            "subtype": self.subtype,
            "confidence": self.confidence,
            "candidates": self.candidates,
            "matched_rules": self.matched_rules,
            "source": self.source,
        }


@lru_cache(maxsize=1)
def _load_rules() -> dict:
    """加载并缓存 matching_rules.json（缺失时返回空规则集 + 默认 fallback）。"""
    if not _RULES_PATH.exists():
        return {"rules": [], "fallback": dict(_DEFAULT_FALLBACK)}
    try:
        data = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"rules": [], "fallback": dict(_DEFAULT_FALLBACK)}
    if "fallback" not in data:
        data["fallback"] = dict(_DEFAULT_FALLBACK)
    if "rules" not in data:
        data["rules"] = []
    return data


def reload_rules() -> None:
    """清除规则缓存（xlsx 重新导入后调用，requirements §7.4）。"""
    _load_rules.cache_clear()


def _normalize_attrs(project_attrs: dict) -> dict:
    """从原始项目属性中抽取归一化的匹配输入。

    支持的来源键：
      - entity_type / scenario / template_type / industry / company_name
      - company_type（listed/non_listed，用于 fallback）
      - applicable_standard_v2.entity_type（若直接传入嵌套结构）
    """
    attrs = dict(project_attrs or {})

    # 从 applicable_standard_v2 中补 entity_type / scope
    std = attrs.get("applicable_standard_v2")
    if isinstance(std, dict):
        attrs.setdefault("entity_type", std.get("entity_type"))
        attrs.setdefault("scope", std.get("scope"))

    def _s(v) -> str:
        return str(v).strip().lower() if v is not None else ""

    return {
        "entity_type": _s(attrs.get("entity_type")),
        "scenario": _s(attrs.get("scenario")),
        "template_type": _s(attrs.get("template_type")),
        # 关键词检索文本（行业 + 公司名 + 客户名，原文不转小写以保留中文）
        "text": " ".join(
            str(attrs.get(k) or "")
            for k in ("industry", "company_name", "client_name", "name", "company_full_name")
        ),
        "company_type": _s(attrs.get("company_type")),
    }


def _rule_matches(rule: dict, norm: dict) -> bool:
    """判断单条规则是否命中归一化后的项目属性。

    命中条件（任一类别 hit 即视为该规则命中）：
      - entity_type / scenario / template_type 精确包含
      - keywords 在 text 中出现
    """
    match = rule.get("match") or {}

    for key in ("entity_type", "scenario", "template_type"):
        candidates = [str(x).strip().lower() for x in (match.get(key) or [])]
        val = norm.get(key) or ""
        if val and val in candidates:
            return True

    text = norm.get("text") or ""
    for kw in match.get("keywords") or []:
        if kw and kw in text:
            return True

    return False


def recommend_company_subtype(project_attrs: dict) -> RecommendResult:
    """根据项目属性推荐企业子类型。

    Validates: Requirements 1.4, 7.2, 7.5, 7.7
    """
    data = _load_rules()
    norm = _normalize_attrs(project_attrs)

    # 1. 评估所有规则，收集命中项
    matched: list[dict] = [r for r in data.get("rules", []) if _rule_matches(r, norm)]
    # 仅保留合法 subtype
    matched = [r for r in matched if r.get("subtype") in _VALID_SUBTYPES]

    if matched:
        # 按命中规则去重 subtype，保留优先级排序
        matched_sorted = sorted(
            matched, key=lambda r: r.get("priority", 0), reverse=True
        )
        # 候选 subtype（去重保序）
        candidates: list[str] = []
        for r in matched_sorted:
            st = r["subtype"]
            if st not in candidates:
                candidates.append(st)

        matched_rule_ids = [r.get("id", r["subtype"]) for r in matched_sorted]

        if len(candidates) == 1:
            # 7.2 唯一匹配
            return RecommendResult(
                subtype=candidates[0],
                confidence="high",
                candidates=candidates,
                matched_rules=matched_rule_ids,
                source="rule",
            )
        # 7.5 歧义：返回全部候选，subtype 取最高优先级，confidence=low
        return RecommendResult(
            subtype=candidates[0],
            confidence="low",
            candidates=candidates,
            matched_rules=matched_rule_ids,
            source="rule",
        )

    # 2. 无规则命中 → 需求 1.4 fallback（7.7：规则优先于 fallback，此处规则已无命中）
    fallback = data.get("fallback") or dict(_DEFAULT_FALLBACK)
    company_type = norm.get("company_type") or ""
    if company_type in fallback:
        sub = fallback[company_type]
        return RecommendResult(
            subtype=sub,
            confidence="low",
            candidates=[sub],
            matched_rules=[],
            source="fallback",
        )

    # entity_type=listed 也按 listed fallback 处理
    if norm.get("entity_type") == "listed":
        return RecommendResult(
            subtype=fallback.get("listed", "type_a"),
            confidence="low",
            candidates=[fallback.get("listed", "type_a")],
            matched_rules=[],
            source="fallback",
        )
    if norm.get("entity_type") in ("private", "soe"):
        # 私营/国企单体无规则命中时，按 non_listed 兜底（国企集团应由关键词命中 type_c）
        sub = fallback.get("non_listed", "type_d")
        return RecommendResult(
            subtype=sub,
            confidence="low",
            candidates=[sub],
            matched_rules=[],
            source="fallback",
        )

    # 3. 完全无信息 → 默认 type_d（最保守，非公众利益实体）
    return RecommendResult(
        subtype="type_d",
        confidence="none",
        candidates=["type_d"],
        matched_rules=[],
        source="default",
    )


def backfill_company_subtype(
    project_attrs: dict,
    *,
    existing_subtype: str | None = None,
) -> BackfillResult:
    """存量项目企业子类型回填（需求 1.7/1.8）。

    回填顺序：
      ① ``existing_subtype`` 非空（用户手动设置）→ 采用，confirmed=True，不显示横幅（需求 1.8）
      ② ``matching_rules.json`` 推荐（``recommend_company_subtype``，规则优先于 fallback）
         → 作为建议值返回，needs_confirmation=True（需求 1.7 ①③）
      ③ fallback（listed→type_a / non_listed→type_d）已包含在 ``recommend_company_subtype`` 内（需求 1.7 ②）

    返回的推断值（rule/fallback/default）``needs_confirmation=True``，
    前端据此展示「待确认企业子类型」非阻断横幅，**不得**静默落库当作用户选择。

    Validates: Requirements 1.4, 1.7, 1.8, 7.2, 7.5, 7.7
    """
    # ① 用户已手动设置（需求 1.8：用户修改优先于自动推断）
    normalized_existing = (existing_subtype or "").strip().lower()
    if normalized_existing in _VALID_SUBTYPES:
        return BackfillResult(
            subtype=normalized_existing,
            confirmed=True,
            needs_confirmation=False,
            source="user",
            confidence="high",
            candidates=[normalized_existing],
            matched_rules=[],
        )

    # ②③ 规则推荐 → fallback（recommend_company_subtype 已封装两级 + default 兜底）
    rec = recommend_company_subtype(project_attrs)
    return BackfillResult(
        subtype=rec.subtype,
        confirmed=False,
        needs_confirmation=rec.subtype is not None,
        source=rec.source,
        confidence=rec.confidence,
        candidates=rec.candidates,
        matched_rules=rec.matched_rules,
    )
