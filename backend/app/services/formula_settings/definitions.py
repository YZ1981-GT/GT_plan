"""公式位定义：各域的字段口径、规范化、哈希与相等判定（design §3）。

* 执行字段参与哈希与冲突判定；说明字段随定义保存，但不判冲突（R2.4）。
* ``{"disabled": true}`` 表示本项目停用该公式位（有效定义为空，R1.1）。
* ``None`` 表示「该层没有定义」，与 ``{"disabled": true}`` 不同。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

DISABLED_KEY = "disabled"


@dataclass(frozen=True)
class DomainSpec:
    key: str
    label: str
    exec_fields: tuple[str, ...]
    desc_fields: tuple[str, ...]
    #: 全局层作用范围：standard（适用准则）/ template_type（附注模板类型）/ any（通用 ``*``）
    scope_kind: str
    #: 停用 = 公式字段全空（报表域：项目行公式置空即停用，没有单独的停用标记列）
    disabled_as_empty: bool = False
    #: 判「公式字段全空」看哪些字段（默认 = 执行字段；报表域不看公式类别）
    formula_fields: tuple[str, ...] = ()


DOMAINS: dict[str, DomainSpec] = {
    "report": DomainSpec(
        "report", "报表公式",
        ("formula", "aje_formula", "rje_formula", "formula_category"),
        ("formula_description", "formula_source"),
        "standard",
        disabled_as_empty=True,
        formula_fields=("formula", "aje_formula", "rje_formula"),
    ),
    "tb_detail": DomainSpec(
        "tb_detail", "试算表科目明细公式",
        ("formula", "formula_category"),
        ("formula_description", "row_name"),
        "any",
    ),
    "cross_check": DomainSpec(
        "cross_check", "表间审核规则",
        ("left_ref", "operator", "right_ref", "tolerance"),
        ("label", "description"),
        "standard",
    ),
    "wp": DomainSpec(
        "wp", "底稿公式",
        ("expression", "formula_type"),
        ("description", "category"),
        "any",
    ),
    "note": DomainSpec(
        "note", "附注公式",
        ("formula", "category"),
        ("description", "source"),
        "template_type",
    ),
    "consol_note": DomainSpec(
        "consol_note", "合并附注公式",
        ("formula",),
        ("description",),
        "template_type",
    ),
    # 公式位 = 推送规则 rule_id；系统预设 = formula_push_rules.json（spec formula-governance-coverage-closure R2）
    "push": DomainSpec(
        "push", "公式推送规则",
        ("expression",),
        ("description",),
        "any",
    ),
}

#: 通用作用范围（全局层对所有准则 / 模板类型生效）。
ANY_SCOPE = "*"


class UnknownDomain(ValueError):
    """域不存在。"""


def get_spec(domain: str) -> DomainSpec:
    spec = DOMAINS.get(domain)
    if spec is None:
        raise UnknownDomain(f"公式域不存在：{domain}")
    return spec


def _norm_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, Decimal)):
        try:
            text = format(Decimal(str(value)).normalize(), "f")
        except (InvalidOperation, ValueError):
            return str(value)
        return text
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def is_disabled(definition: Mapping[str, Any] | None) -> bool:
    return bool(definition) and bool(definition.get(DISABLED_KEY))


#: 字段级规范化：底稿公式 ``=TB(...)`` 与 ``TB(...)`` 视为同一公式（单元格公式惯例带等号）；
#: 各域写入方缺省的类别 / 运算符按其缺省值比较（缺省与显式缺省值不算差异）。
_FIELD_CANON = {
    ("wp", "expression"): lambda v: v.lstrip("=").strip(),
    ("push", "expression"): lambda v: v.lstrip("=").strip(),
    ("wp", "formula_type"): lambda v: v or "auto_calc",
    ("note", "category"): lambda v: v or "auto_calc",
    ("tb_detail", "formula_category"): lambda v: v or "auto_calc",
    ("cross_check", "operator"): lambda v: v or "=",
}


def normalize(domain: str, definition: Mapping[str, Any] | None) -> dict[str, str] | None:
    """只保留域内已登记字段，值统一为去首尾空白的字符串；``None`` 原样返回。"""
    if definition is None:
        return None
    if is_disabled(definition):
        return {DISABLED_KEY: "true"}
    spec = get_spec(domain)
    out = {}
    for f in spec.exec_fields + spec.desc_fields:
        value = _norm_value(definition.get(f))
        canon = _FIELD_CANON.get((domain, f))
        out[f] = canon(value) if canon else value
    return out


def exec_view(domain: str, definition: Mapping[str, Any] | None) -> dict[str, str] | None:
    """参与冲突判定的执行字段视图。"""
    norm = normalize(domain, definition)
    if norm is None:
        return None
    spec = get_spec(domain)
    if DISABLED_KEY in norm:
        if spec.disabled_as_empty:
            return {f: "" for f in spec.exec_fields}
        return {DISABLED_KEY: "true"}
    return {f: norm[f] for f in spec.exec_fields}


def is_effectively_disabled(domain: str, definition: Mapping[str, Any] | None) -> bool:
    """有定义但不生效（停用标记，或报表域执行字段全空）。"""
    if definition is None:
        return False
    if is_disabled(definition):
        return True
    spec = get_spec(domain)
    if not spec.disabled_as_empty:
        return False
    norm = normalize(domain, definition) or {}
    return not any(norm.get(f) for f in (spec.formula_fields or spec.exec_fields))


def exec_hash(domain: str, definition: Mapping[str, Any] | None) -> str | None:
    view = exec_view(domain, definition)
    if view is None:
        return None
    raw = json.dumps(view, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def same_exec(domain: str, a: Mapping[str, Any] | None, b: Mapping[str, Any] | None) -> bool:
    """执行字段是否相同（两边都没有定义也算相同）。"""
    return exec_view(domain, a) == exec_view(domain, b)


def display_formula(domain: str, definition: Mapping[str, Any] | None) -> str:
    """给审计日志 / 弹窗展示用的单行公式文本。"""
    if definition is None:
        return ""
    if is_disabled(definition):
        return "（本项目停用）"
    if domain == "cross_check":
        d = normalize(domain, definition) or {}
        text = f"{d.get('left_ref', '')} {d.get('operator', '') or '='} {d.get('right_ref', '')}".strip()
        tol = d.get("tolerance", "")
        return f"{text}（容差 {tol}）" if tol else text
    field = "expression" if domain in ("wp", "push") else "formula"
    return _norm_value(definition.get(field))


def merge_keep_local_desc(domain: str, upstream: Mapping[str, Any] | None,
                          local: Mapping[str, Any] | None,
                          base: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """采用上游定义，但本项目改过（≠ 基线）的说明字段保留本项目的值（R2.4）。"""
    if upstream is None:
        return None
    merged = dict(upstream)
    if not local or is_disabled(local) or is_disabled(upstream):
        return merged
    for f in get_spec(domain).desc_fields:
        local_v = _norm_value(local.get(f))
        base_v = _norm_value((base or {}).get(f))
        if local_v != base_v:
            merged[f] = local.get(f)
    return merged
