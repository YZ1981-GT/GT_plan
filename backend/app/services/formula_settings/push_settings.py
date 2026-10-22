"""公式推送规则纳入公式治理内核（spec formula-governance-coverage-closure R2，design §4）。

push 域：公式位 = 推送规则 ``rule_id``；系统预设层 = ``formula_push_rules.json``（文件不改、不迁移，ADR-FGC-001），
全局 / 本项目 / 模板层存 ``formula_setting``。只开放两件事（ADR-FGC-002）：

* 改写公式来源规则的来源公式（``expression``），校验与规则清单加载**同一套**（``rules._check_source``）；
* 启用 / 停用 —— 系统值 / 派生值规则不许停用：它们的目标是推送独占键，前后端保存都会剔除人工填写，
  停用后既无人推送也无人能填。

目标地址、写入策略、触发事件、四表 / 派生来源不可改（定义只认 expression / description / disabled）。
运行时改写失效（如 binding 变了）⇒ 跳过并报原因，不回退系统预设（ADR-FGC-003：宁缺毋错）。
"""
from __future__ import annotations

import dataclasses
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings.definitions import DISABLED_KEY, is_disabled
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.stores import SettingStore, SlotRecord

DOMAIN = "push"
#: 定义里允许的键；其余一律拒收（推送规则只开放改写公式与启用 / 停用）。``_structure`` 是模板条目随带的
#: 只读结构，接收但不落库（结构只认规则清单）
ALLOWED_KEYS = frozenset({"expression", "description", DISABLED_KEY, "_structure"})
#: 不许停用的写入策略（目标是推送独占键）
LOCKED_POLICIES = frozenset({"system", "derived"})
_POLICY_TEXT = {"system": "系统值", "derived": "派生值", "editable": "可编辑值"}
_KIND_TEXT = {"four_table_leaves": "四表明细", "derivation": "派生计算"}
#: 推送取数上下文只给试算表审定数（TB）与大厅调整（ADJ）；其余可用的只有不取数的纯计算函数
PUSH_DATA_FUNCTIONS = frozenset({"TB", "ADJ"})
PUSH_PURE_FUNCTIONS = frozenset({"ABS", "ROUND", "MAX", "MIN", "IF"})
_STRING_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_CODE_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])(TB|ADJ)\(")
_CODE_ARG_RE = re.compile(r"\s*(['\"])(.*?)\1")

_cache: dict[str, Any] = {"rules": None, "by_id": {}, "presets": {}}


def canon_expression(value: Any) -> str:
    """单元格公式惯例带「=」：``=TB(…)`` 与 ``TB(…)`` 是同一个公式。"""
    return str(value or "").strip().lstrip("=").strip()


def _structure(rule: Any) -> dict[str, Any]:
    t = rule.target
    return {
        "wp_code": rule.wp_code, "stage": rule.stage, "policy": rule.policy, "source_kind": rule.source.kind,
        "triggers": list(rule.triggers), "formula_text": rule.source.formula_text or "",
        "target": {"domain": t.domain, "sheet_code": t.sheet_code, "item_id": t.item_id, "table": t.table,
                   "sections": t.sections},
    }


def _preset(rule: Any) -> SlotRecord:
    definition = ({DISABLED_KEY: True} if rule.status != "active"
                  else {"expression": rule.source.expression or "", "description": rule.description or ""})
    return SlotRecord(slot_key=rule.rule_id, definition=definition, version=rule.version,
                      label=f"{rule.wp_code} {rule.description or ''}".strip()[:300], layer="preset",
                      structure=_structure(rule))


def _loaded() -> dict[str, Any]:
    """规则清单（按清单元组身份缓存：文件或 binding 变了 ``load_push_rules`` 才返回新元组）。"""
    from app.services.formula_push.engine import load_push_rules

    rules = load_push_rules()
    if _cache["rules"] is not rules:
        _cache.update(rules=rules, by_id={r.rule_id: r for r in rules},
                      presets={r.rule_id: _preset(r) for r in rules})
    return _cache


def rule_by_id(rule_id: str) -> Any | None:
    return _loaded()["by_id"].get(rule_id)


def can_disable(rule: Any) -> bool:
    return rule.policy not in LOCKED_POLICIES


def editable_formula(rule: Any) -> bool:
    return rule.source.kind == "formula"


def push_context_errors(wp_code: str, expression: str) -> list[str]:
    """推送取数上下文能否给出该公式的数（中文原因；空 = 能）。

    推送只按底稿 binding 的科目取试算表审定数 / 大厅调整（``load_tb_audited`` 以这些科目为键），
    别的取数函数、别的科目在推送里取不到数，公式引擎按「无数据」得 0 —— 推进审定表就是错数，故拒收。
    """
    from app.services.formula_push.bindings import get_binding, supported_wp_codes

    if wp_code not in supported_wp_codes():
        return [f"底稿 {wp_code} 未接入公式推送"]
    errors: list[str] = []
    names = {m.group(1) for m in _CALL_RE.finditer(_STRING_RE.sub("''", expression))}
    unsupported = sorted(names - PUSH_DATA_FUNCTIONS - PUSH_PURE_FUNCTIONS)
    if unsupported:
        errors.append(f"推送只能取试算表审定数（TB）与大厅调整（ADJ），不支持 {'、'.join(unsupported)}"
                      "（推送里取不到这些数，会恒为 0）")
    loaded = tuple(get_binding(wp_code).account_prefixes)
    stray: set[str] = set()
    for m in _CODE_CALL_RE.finditer(expression):
        arg = _CODE_ARG_RE.match(expression, m.end())
        if arg is None:
            errors.append(f"{m.group(1)}() 的科目编码要写成带引号的文本，如 {m.group(1)}('{(loaded or ('1001',))[0]}', …)")
        elif arg.group(2) not in loaded:
            stray.add(arg.group(2))
    if stray:
        errors.append(f"科目 {'、'.join(sorted(stray))} 不在本底稿推送取数的科目内（{'、'.join(loaded) or '无'}），"
                      "取不到数会恒为 0")
    return errors


def validate_push_definition(slot_key: str, definition: dict | None, label: str = "") -> None:
    """写入任一层（全局 / 本项目 / 模板）前的校验；``None`` = 删除该层定义，不校验内容。"""
    from app.services.formula_push.rules import _binding_specs_from_registry, _check_source

    name = label or slot_key
    rule = rule_by_id(slot_key)
    if rule is None:
        raise FormulaSettingError(f"{name}：推送规则不存在")
    if definition is None:
        return
    extra = sorted(set(definition) - ALLOWED_KEYS)
    if extra:
        raise FormulaSettingError(
            f"{name}：推送规则只能改写来源公式或启用 / 停用，不能改 {'、'.join(extra)}（目标、写入策略、触发事件随规则清单）")
    if is_disabled(definition):
        if not can_disable(rule):
            raise FormulaSettingError(
                f"{name}：{_POLICY_TEXT[rule.policy]}规则不能停用 —— 它写的目标是推送独占键，前端与后端保存都会"
                "剔除人工填写，停用后既没有人推送也没有人能填。这类规则只能改写公式。")
        return
    expression = canon_expression(definition.get("expression"))
    if not editable_formula(rule):
        if expression:
            kind = _KIND_TEXT.get(rule.source.kind, rule.source.kind)
            how = ("只能停用或启用" if can_disable(rule)
                   else f"写入策略是{_POLICY_TEXT[rule.policy]}，只读（由引擎按规则清单计算，不能停用）")
            raise FormulaSettingError(f"{name}：该规则的来源是{kind}，{how}，不能改写公式")
        return
    if not expression:
        raise FormulaSettingError(f"{name}：来源公式不能为空")
    errors: list[str] = []
    spec = _binding_specs_from_registry([rule.wp_code]).get(rule.wp_code)
    _check_source(rule.rule_id, {"kind": "formula", "expression": expression, "context": rule.source.context_map},
                  errors, None, spec)
    messages = [e.split(": ", 1)[-1] for e in errors] + push_context_errors(rule.wp_code, expression)
    if messages:
        raise FormulaSettingError(f"{name}：" + "；".join(messages))


def _without_structure(definition: dict | None) -> dict | None:
    return None if definition is None else {k: v for k, v in definition.items() if k != "_structure"}


def _attach_structure(records: dict[str, SlotRecord]) -> dict[str, SlotRecord]:
    by_id = _loaded()["by_id"]
    for key, rec in records.items():
        rule = by_id.get(key)
        rec.structure = _structure(rule) if rule is not None else {}
    return records


class PushStore(SettingStore):
    """全局 / 本项目层在 ``formula_setting``，系统预设 = 规则清单；写入前逐条校验。结构信息只来自清单，不随定义存。"""

    def __init__(self) -> None:
        super().__init__(DOMAIN)

    async def system_presets(self, db, scope):
        return {k: dataclasses.replace(v, definition=dict(v.definition or {}))
                for k, v in _loaded()["presets"].items()}

    # 结构不随定义落库，读出时按规则清单补上（界面显示目标 / 中文算式用）
    async def list_global(self, db, scope):
        return _attach_structure(await super().list_global(db, scope))

    async def list_global_exact(self, db, scope):
        return _attach_structure(await super().list_global_exact(db, scope))

    async def list_project(self, db, project_id):
        return _attach_structure(await super().list_project(db, project_id))

    async def list_project_many(self, db, project_ids):
        many = await super().list_project_many(db, project_ids)
        return {pid: _attach_structure(recs) for pid, recs in many.items()}

    async def write_global(self, db, scope, slot_key, definition, *, user_id, label="", structure=None):
        definition = _without_structure(definition)
        validate_push_definition(slot_key, definition, label)
        return await super().write_global(db, scope, slot_key, definition, user_id=user_id, label=label)

    async def write_project(self, db, project_id, slot_key, **kwargs):
        kwargs["definition"] = _without_structure(kwargs.get("definition"))
        # 内核把「无定义」写成停用（``SettingStore`` 的口径），校验时同样按停用判
        validate_push_definition(slot_key, kwargs["definition"] or {DISABLED_KEY: True}, kwargs.get("label") or "")
        kwargs["structure"] = None
        await super().write_project(db, project_id, slot_key, **kwargs)


async def effective_push_rules(db: AsyncSession, project_id: uuid.UUID, *,
                               slots: dict[str, Any] | None = None) -> tuple[tuple[Any, ...], list[tuple[str, str]]]:
    """本项目有效推送规则：规则清单逐条叠加本项目有效定义（本项目 ?? 模板物化 ?? 全局 ?? 系统预设）。

    返回 ``(规则, [(rule_id, 原因)])``：停用 ⇒ ``status="disabled"``；改写公式 ⇒ 换来源公式；
    有效定义运行时复验不过 ⇒ ``status="invalid"`` 并记原因（跳过，不回退系统预设）。
    ``slots`` 可传入已算好的 ``effective_slots``（规则列表接口同时要层级，免算两遍）。
    """
    from app.services.formula_settings.effective import LAYER_LABELS, effective_slots

    loaded = _loaded()
    if slots is None:
        slots = await effective_slots(db, DOMAIN, project_id)
    out: list[Any] = []
    issues: list[tuple[str, str]] = []
    for rule in loaded["rules"]:
        slot = slots.get(rule.rule_id)
        if slot is None or slot.layer == "preset":
            out.append(rule)
            continue
        definition = slot.definition or {DISABLED_KEY: True}
        try:
            validate_push_definition(rule.rule_id, definition, rule.rule_id)
        except FormulaSettingError as exc:
            out.append(dataclasses.replace(rule, status="invalid"))
            issues.append((rule.rule_id, f"推送规则「{LAYER_LABELS.get(slot.layer, slot.layer)}」定义已不可用，"
                                         f"本次未推送（不回退系统预设）：{exc.message}"))
            continue
        if is_disabled(definition):
            out.append(dataclasses.replace(rule, status="disabled"))
            continue
        effective = rule if rule.status == "active" else dataclasses.replace(rule, status="active")
        expression = canon_expression(definition.get("expression"))
        if editable_formula(rule) and expression != canon_expression(rule.source.expression):
            effective = dataclasses.replace(effective, source=dataclasses.replace(rule.source, expression=expression))
        out.append(effective)
    return tuple(out), issues


def rule_actions(rule: Any, slot: Any | None) -> dict[str, Any]:
    """规则表每行：层级与可用操作（前端 ``formulaPushView.ruleActions`` 按它出按钮与原因）。"""
    from app.services.formula_settings.effective import LAYER_LABELS

    layer = slot.layer if slot is not None else "preset"
    local = slot.local if slot is not None else None
    definition = (slot.definition if slot is not None else None) or {}
    preset = rule_by_id(rule.rule_id) or rule  # 传入的可能是已叠加本项目改写的有效规则
    return {
        "layer": layer, "layer_label": LAYER_LABELS.get(layer, layer),
        "disabled": is_disabled(definition),  # 有效定义（无覆盖时即系统预设：清单 status≠active 记作停用）
        "pending": bool(slot.pending) if slot is not None else False,
        "editable_formula": editable_formula(rule), "can_disable": can_disable(rule),
        "has_local": local is not None, "local_version": local.version if local is not None else None,
        "preset_formula": preset.source.display_formula,
    }
