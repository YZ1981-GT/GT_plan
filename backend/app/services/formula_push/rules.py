"""公式推送规则清单加载与校验（``backend/data/formula_push_rules.json``）。

spec: chain-closure-phase2-formula-push-engine · design §三 · 需求 1.1~1.3

清单是「目标地址 + 来源公式 + 写入策略 + 触发事件」的声明式登记，公式管理面板只读展示，
引擎按它逐条求值。**加载即校验**，任一条不合法整份拒收（``PushRuleError`` 列出全部问题），
不做「跳过坏规则继续跑」—— 那会让某条推送静默消失。

校验项：

* 结构：``rule_id`` 唯一且以 ``{wp_code}.`` 开头；``page_key = workpaper:{wp_code}``；
  ``stage`` / ``policy`` / ``source.kind`` / ``triggers`` 在枚举内，``stage`` 与 ``policy`` 搭配合法；
  每条规则都含 ``manual``（面板「立即推送」覆盖全部规则）。
* 目标：底稿域要 ``sheet_code`` / ``item_id`` 且都以 ``wp_code`` 开头；附注域要
  ``section_by_template``（键 ⊆ listed/soe）与 ``table``；**两条规则不得写同一目标**
  （一个单元格只有一个写入方）。
* 公式：``validate_formula`` 无错、以空上下文试算无 ``errors`` / ``blocked``（抓未注册列名、
  解析失败、非白名单函数）；**禁用列名 ``审定数`` / ``未审数``**（内核别名把它们与
  ``期末余额`` 折叠为同一键：写 ``未审数`` 实际取到的是审定数，字面与取值不符。推送上下文
  ``tb=trial_balance_audited`` 里 ``期末余额`` 即试算表审定数，见 ADR-PUSH-002 修订）；
  ``TB()`` 必须显式写列名；``context`` 取值在登记表内。
* 派生 / 四表来源：``formula_text`` 必填（面板显示算式）；传入 ``known_derivations`` 时
  派生名必须已实现。
* 所有说明文字必须含中文（UI 全中文）。
"""
from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.formula_push_models import PUSH_DOMAINS
from app.services.formula_push.policy import POLICIES

RULES_PATH = Path(__file__).resolve().parents[3] / "data" / "formula_push_rules.json"

STAGES: tuple[str, ...] = ("source", "derived", "note")
SOURCE_KINDS: tuple[str, ...] = ("formula", "four_table_leaves", "derivation")
TRIGGERS: tuple[str, ...] = ("TRIAL_BALANCE_UPDATED", "WORKPAPER_SAVED", "manual")
TEMPLATE_TYPES: tuple[str, ...] = ("listed", "soe")
#: 公式求值上下文登记表：维度 → 允许的取数口径
FORMULA_CONTEXTS: Mapping[str, tuple[str, ...]] = {
    # tb_data 取自 trial_balance 持久化列，与报表引擎**审定模式**同口径（report_engine._COLUMN_MAP）：
    #   TB(code,'期末余额') = audited_amount（试算表审定数，报表同源；recalc 与审定表发布门都写它）
    #   TB(code,'年初余额') = opening_balance
    # 不用「未审数 + AJE调整 + RJE调整」现算：试算表 AJE 列按 V124 排除底稿来源分录（它们只经
    # 审定表发布门写进 audited_amount），现算会让 E1-5 的调整永远显示为差异（ADR-PUSH-002）。
    "tb": ("trial_balance_audited", "trial_balance_audited_occurrence"),
    # adj_data 只含大厅已批准、且 origin≠workpaper 的分录（ADR-PUSH-001）
    "adj": ("hall_approved_excluding_workpaper",),
}
#: 内核里语义不唯一的列名（与「期末余额」折叠为同一键）
BANNED_COLUMNS: tuple[str, ...] = ("审定数", "未审数")
#: 四表叶子槽（文档用途；校验改用各 binding 的 four_table_slots，见 BindingSpec）
FOUR_TABLE_SLOTS: tuple[str, ...] = ("cash", "bank", "other", "finance_co", "digital")
#: 各 stage 允许的 policy
STAGE_POLICIES: Mapping[str, frozenset[str]] = {
    "source": frozenset({"system", "editable"}),
    "derived": frozenset({"derived"}),
    "note": frozenset({"editable"}),
}


@dataclass(frozen=True)
class BindingSpec:
    """校验规则时用的 binding 元信息（从 PushBinding 提取，可 hash）。"""
    four_table_slots: frozenset[str]
    derivations: frozenset[str]
    tb_columns: frozenset[str]


#: 提取 TB / SUM_TB 第二参数（列名）；排除 SUM_TB 中的 TB 子串
_TB_COL_RE = re.compile(
    r"(?<![A-Z_])(?:SUM_)?TB\(\s*['\"][^'\"]*['\"]\s*,\s*(['\"])(.*?)\1\s*\)"
)

_RULE_ID_RE = re.compile(r"^[A-Z]\d*(?:\.[A-Za-z0-9_]+)+$")
_PAGE_KEY_RE = re.compile(r"^workpaper:([A-Z]\d*)$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_BANNED_RE = re.compile(r"""['"](%s)['"]""" % "|".join(BANNED_COLUMNS))
_TB_SINGLE_ARG_RE = re.compile(r"(?<![A-Z_])TB\(\s*'[^']*'\s*\)")


class PushRuleError(ValueError):
    """规则清单不合法（携带全部问题）。"""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("公式推送规则清单校验失败：\n" + "\n".join(f"  - {e}" for e in errors))


@dataclass(frozen=True)
class PushTarget:
    domain: str
    wp_code: str | None = None
    sheet_code: str | None = None
    item_id: str | None = None
    rows: str | None = None
    fields: tuple[str, ...] = ()
    section_by_template: tuple[tuple[str, str], ...] = ()
    table: str | None = None
    table_by_template: tuple[tuple[str, str], ...] = ()

    @property
    def sections(self) -> dict[str, str]:
        return dict(self.section_by_template)

    @property
    def tables_by_template(self) -> dict[str, str]:
        return dict(self.table_by_template)

    def resolve_table(self, template_type: str | None) -> str | None:
        """按准则变体选表名：``table_by_template[template_type]`` 优先，回退 ``table``。"""
        if template_type and self.table_by_template:
            tbl = dict(self.table_by_template).get(template_type)
            if tbl:
                return tbl
        return self.table

    def identity(self) -> tuple:
        """「写同一目标」判重键。"""
        if self.domain == "workpaper":
            return ("workpaper", self.wp_code, self.item_id)
        return ("note", self.table, self.table_by_template, self.section_by_template)


@dataclass(frozen=True)
class PushSource:
    kind: str
    expression: str | None = None
    context: tuple[tuple[str, str], ...] = ()
    slots: tuple[str, ...] = ()
    name: str | None = None
    params: tuple[tuple[str, Any], ...] = ()
    formula_text: str | None = None

    @property
    def context_map(self) -> dict[str, str]:
        return dict(self.context)

    @property
    def params_map(self) -> dict[str, Any]:
        return dict(self.params)

    @property
    def display_formula(self) -> str:
        """面板展示用算式：公式规则显示表达式，其余显示中文算式说明。"""
        return self.expression if self.kind == "formula" else (self.formula_text or "")


@dataclass(frozen=True)
class PushRule:
    rule_id: str
    page_key: str
    stage: str
    policy: str
    target: PushTarget
    source: PushSource
    triggers: tuple[str, ...]
    description: str

    @property
    def wp_code(self) -> str:
        return self.page_key.split(":", 1)[1]

    def fires_on(self, trigger: str) -> bool:
        return trigger in self.triggers


# ── addr_id（沿用 ACNR：底稿域 {wp_code}/{sheet_code}/{coordinate}，非底稿域带前缀）──────


def workpaper_addr_id(
    wp_code: str, sheet_code: str, item_id: str, *, row_id: str | None = None, field_name: str | None = None
) -> str:
    """``E1/E1-1/E1-adj-tb-amount-ending`` 或 ``E1/E1-2/E1-cash-detail-rows[fixed-rmb].opening``。"""
    addr = f"{wp_code}/{sheet_code}/{item_id}"
    if row_id is not None:
        addr += f"[{row_id}]"
    if field_name is not None:
        addr += f".{field_name}"
    return addr


def note_addr_id(section: str, table: str, row_label: str, period: str) -> str:
    """``note://五、1/货币资金/库存现金.end``（period ∈ end / prior）。"""
    if period not in ("end", "prior"):
        raise ValueError(f"附注期间只能是 end / prior，收到 {period!r}")
    return f"note://{section}/{table}/{row_label}.{period}"


# ── 校验 ─────────────────────────────────────────────────────────────────────


def _has_cjk(text: Any) -> bool:
    return isinstance(text, str) and bool(_CJK_RE.search(text))


def _check_formula(
    rid: str,
    expression: Any,
    errors: list[str],
    tb_columns: Collection[str] | None = None,
) -> None:
    from app.services.formula_engine import FormulaContext, execute, validate_formula

    if not isinstance(expression, str) or not expression.strip():
        errors.append(f"{rid}: 公式来源缺 expression")
        return
    for msg in validate_formula(expression):
        errors.append(f"{rid}: 公式语法错误 —— {msg}")
    result = execute(expression, FormulaContext())
    if result.blocked:
        errors.append(f"{rid}: 公式含非白名单内容")
    for msg in result.errors:
        errors.append(f"{rid}: 公式试算失败 —— {msg}")
    banned = sorted(set(_BANNED_RE.findall(expression)))
    if banned:
        errors.append(
            f"{rid}: 公式禁用列名 {banned}（内核把它们与「期末余额」折叠为同一键，写法与实际取值不符；"
            "推送上下文 tb=trial_balance_audited 里「期末余额」即试算表审定数，请直接写 期末余额）"
        )
    if _TB_SINGLE_ARG_RE.search(expression):
        errors.append(f"{rid}: TB() 必须显式写列名")
    if tb_columns is not None:
        allowed_columns = frozenset(tb_columns)
        used_columns = {match.group(2) for match in _TB_COL_RE.finditer(expression)}
        unloaded = sorted(used_columns - allowed_columns)
        if unloaded:
            errors.append(
                f"{rid}: 公式使用了 binding.tb_columns 未装载的试算表列 {unloaded} "
                f"（当前 binding 可用 {sorted(allowed_columns)}）"
            )


def _check_target(rid: str, wp_code: str | None, raw: Any, errors: list[str]) -> PushTarget | None:
    if not isinstance(raw, Mapping):
        errors.append(f"{rid}: target 缺失或不是对象")
        return None
    domain = raw.get("domain")
    if domain not in PUSH_DOMAINS:
        errors.append(f"{rid}: target.domain={domain!r} 不在 {PUSH_DOMAINS}")
        return None
    fields = raw.get("fields") or []
    if not isinstance(fields, list) or not all(isinstance(f, str) and f for f in fields):
        errors.append(f"{rid}: target.fields 必须是非空字符串列表")
        fields = []
    rows = raw.get("rows")
    if rows is not None and (not isinstance(rows, str) or not rows):
        errors.append(f"{rid}: target.rows 必须是非空字符串")
    if (rows is None) != (not fields):
        errors.append(f"{rid}: target.rows 与 target.fields 必须同时出现（行集目标要声明写哪些字段）")

    if domain == "workpaper":
        sheet_code, item_id = raw.get("sheet_code"), raw.get("item_id")
        tw = raw.get("wp_code")
        if tw != wp_code:
            errors.append(f"{rid}: target.wp_code={tw!r} 与 page_key 的 {wp_code!r} 不一致")
        for name, value in (("sheet_code", sheet_code), ("item_id", item_id)):
            if not isinstance(value, str) or not value:
                errors.append(f"{rid}: 底稿目标缺 {name}")
        if isinstance(sheet_code, str) and wp_code and not (
            sheet_code == wp_code or sheet_code.startswith(f"{wp_code}-")
        ):
            errors.append(f"{rid}: sheet_code={sheet_code!r} 不属于底稿 {wp_code}")
        if isinstance(item_id, str) and wp_code and not item_id.startswith(f"{wp_code}-"):
            errors.append(f"{rid}: item_id={item_id!r} 不以 {wp_code}- 开头")
        return PushTarget(domain=domain, wp_code=tw, sheet_code=sheet_code, item_id=item_id,
                          rows=rows, fields=tuple(fields))

    sections = raw.get("section_by_template")
    if not isinstance(sections, Mapping) or not sections:
        errors.append(f"{rid}: 附注目标缺 section_by_template")
        sections = {}
    bad_keys = sorted(set(sections) - set(TEMPLATE_TYPES))
    if bad_keys:
        errors.append(f"{rid}: section_by_template 键 {bad_keys} 不在 {TEMPLATE_TYPES}")
    if not all(isinstance(v, str) and v for v in sections.values()):
        errors.append(f"{rid}: section_by_template 章节号必须是非空字符串")
    table = raw.get("table")
    # table_by_template（可选）：上市/国企主表名不同时按变体声明
    table_by_tmpl = raw.get("table_by_template")
    if table_by_tmpl is not None:
        if not isinstance(table_by_tmpl, Mapping) or not table_by_tmpl:
            errors.append(f"{rid}: table_by_template 必须是非空对象")
            table_by_tmpl = {}
        bad_tkeys = sorted(set(table_by_tmpl) - set(TEMPLATE_TYPES))
        if bad_tkeys:
            errors.append(f"{rid}: table_by_template 键 {bad_tkeys} 不在 {TEMPLATE_TYPES}")
        if not all(isinstance(v, str) and v for v in table_by_tmpl.values()):
            errors.append(f"{rid}: table_by_template 表名必须是非空字符串")
    else:
        table_by_tmpl = {}
    # table 在无 table_by_template 时必填；有 table_by_template 时可选（兼容回退）
    if not table_by_tmpl and (not isinstance(table, str) or not table):
        errors.append(f"{rid}: 附注目标缺 table（无 table_by_template 时 table 必填）")
    from app.services.formula_push import note_writer

    unknown_fields = sorted(set(fields) - set(note_writer.NOTE_FIELDS))
    if unknown_fields:
        errors.append(
            f"{rid}: 附注 target.fields 含未登记字段 {unknown_fields} "
            f"（可选 {sorted(note_writer.NOTE_FIELDS)}）"
        )
    return PushTarget(domain=domain, rows=rows, fields=tuple(fields), table=table,
                      section_by_template=tuple(sorted(sections.items())),
                      table_by_template=tuple(sorted(table_by_tmpl.items())))


def _check_source(
    rid: str, raw: Any, errors: list[str], known_derivations: Collection[str] | None,
    binding_spec: BindingSpec | None = None,
) -> PushSource | None:
    if not isinstance(raw, Mapping):
        errors.append(f"{rid}: source 缺失或不是对象")
        return None
    kind = raw.get("kind")
    if kind not in SOURCE_KINDS:
        errors.append(f"{rid}: source.kind={kind!r} 不在 {SOURCE_KINDS}")
        return None
    if kind == "formula":
        expression = raw.get("expression")
        _check_formula(
            rid,
            expression,
            errors,
            tb_columns=binding_spec.tb_columns if binding_spec is not None else None,
        )
        context = raw.get("context") or {}
        if not isinstance(context, Mapping) or not context:
            errors.append(f"{rid}: 公式来源须声明 context（取数口径）")
            context = {}
        for dim, value in context.items():
            allowed = FORMULA_CONTEXTS.get(dim)
            if allowed is None:
                errors.append(f"{rid}: context 维度 {dim!r} 未登记（可选 {sorted(FORMULA_CONTEXTS)}）")
            elif value not in allowed:
                errors.append(f"{rid}: context.{dim}={value!r} 不在 {allowed}")
        if isinstance(expression, str):
            uses_tb = bool(re.search(r"(?<![A-Z_])(?:SUM_)?TB\(", expression))
            uses_adj = "ADJ(" in expression
            if uses_tb and "tb" not in context:
                errors.append(f"{rid}: 公式用了 TB() 但 context 未声明 tb 口径")
            if uses_adj and "adj" not in context:
                errors.append(f"{rid}: 公式用了 ADJ() 但 context 未声明 adj 口径")
        return PushSource(kind=kind, expression=expression, context=tuple(sorted(context.items())))

    formula_text = raw.get("formula_text")
    if not _has_cjk(formula_text):
        errors.append(f"{rid}: {kind} 来源须有中文 formula_text（面板显示算式）")
    if kind == "four_table_leaves":
        slots = raw.get("slots") or []
        if not isinstance(slots, list) or not slots:
            errors.append(f"{rid}: four_table_leaves 须声明 slots")
            slots = []
        allowed_slots = (
            binding_spec.four_table_slots if binding_spec is not None else frozenset(FOUR_TABLE_SLOTS)
        )
        bad = sorted(set(slots) - set(allowed_slots))
        if bad:
            errors.append(f"{rid}: 四表槽 {bad} 不在当前 binding 可用集合 {sorted(allowed_slots)}")
        return PushSource(kind=kind, slots=tuple(slots), formula_text=formula_text)

    name = raw.get("name")
    params = raw.get("params") or {}
    if not isinstance(name, str) or not name:
        errors.append(f"{rid}: derivation 须声明 name")
    else:
        allowed_derivations = (
            binding_spec.derivations if binding_spec is not None else known_derivations
        )
        if allowed_derivations is not None and name not in allowed_derivations:
            errors.append(f"{rid}: 派生 {name!r} 未实现（已实现 {sorted(allowed_derivations)}）")
    if not isinstance(params, Mapping):
        errors.append(f"{rid}: derivation.params 必须是对象")
        params = {}
    return PushSource(kind=kind, name=name, params=tuple(sorted(params.items())), formula_text=formula_text)


def parse_rules(
    document: Any,
    *,
    binding_specs: Mapping[str, BindingSpec] | None = None,
    known_derivations: Collection[str] | None = None,
    registered_wp_codes: Collection[str] | None = None,
) -> tuple[PushRule, ...]:
    """校验并解析整份清单；有任何问题抛 :class:`PushRuleError`（含全部问题）。

    ``binding_specs`` 是按主编码分组的规则校验元信息。传入后，四表槽、派生名和
    TB 列都只按对应 binding 校验；不传时保留旧的全局 / ``known_derivations`` 兼容路径，
    使这个函数仍可作为纯解析器单独使用。
    """
    if registered_wp_codes is None:
        if binding_specs is not None:
            registered_wp_codes = tuple(binding_specs)
        else:
            from app.services.formula_push.bindings import supported_wp_codes

            registered_wp_codes = supported_wp_codes()
    registered_codes = set(registered_wp_codes)
    errors: list[str] = []
    if not isinstance(document, Mapping) or document.get("version") != 1:
        raise PushRuleError(["清单根须为对象且 version == 1"])
    raw_rules = document.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise PushRuleError(["清单 rules 须为非空列表"])

    rules: list[PushRule] = []
    seen_ids: set[str] = set()
    seen_targets: dict[tuple, str] = {}
    for idx, raw in enumerate(raw_rules):
        if not isinstance(raw, Mapping):
            errors.append(f"第 {idx} 条不是对象")
            continue
        rid = raw.get("rule_id")
        if not isinstance(rid, str) or not _RULE_ID_RE.match(rid):
            errors.append(f"第 {idx} 条 rule_id={rid!r} 格式不合法（形如 E1.tb_amount.ending）")
            rid = f"#{idx}"
        elif rid in seen_ids:
            errors.append(f"{rid}: rule_id 重复")
        seen_ids.add(rid)

        page_key = raw.get("page_key")
        m = _PAGE_KEY_RE.match(page_key) if isinstance(page_key, str) else None
        wp_code = m.group(1) if m else None
        if not m:
            errors.append(f"{rid}: page_key={page_key!r} 须形如 workpaper:E1")
        elif not rid.startswith(f"{wp_code}."):
            errors.append(f"{rid}: rule_id 须以 {wp_code}. 开头")
        if wp_code is not None and wp_code not in registered_codes:
            errors.append(f"{rid}: 底稿 {wp_code} 未注册公式推送 binding")

        binding_spec = None
        if wp_code is not None and binding_specs is not None:
            binding_spec = binding_specs.get(wp_code)
            if binding_spec is None:
                errors.append(f"{rid}: 底稿 {wp_code} 未提供 binding 规则校验元信息")

        stage, policy = raw.get("stage"), raw.get("policy")
        if stage not in STAGES:
            errors.append(f"{rid}: stage={stage!r} 不在 {STAGES}")
        if policy not in POLICIES:
            errors.append(f"{rid}: policy={policy!r} 不在 {POLICIES}")
        if stage in STAGE_POLICIES and policy in POLICIES and policy not in STAGE_POLICIES[stage]:
            errors.append(f"{rid}: stage={stage} 不允许 policy={policy}（可选 {sorted(STAGE_POLICIES[stage])}）")

        triggers = raw.get("triggers") or []
        if not isinstance(triggers, list) or not triggers:
            errors.append(f"{rid}: triggers 须为非空列表")
            triggers = []
        bad_triggers = sorted(set(triggers) - set(TRIGGERS))
        if bad_triggers:
            errors.append(f"{rid}: 触发事件 {bad_triggers} 不在 {TRIGGERS}")
        if "manual" not in triggers:
            errors.append(f"{rid}: triggers 须含 manual（面板「立即推送」覆盖全部规则）")
        if len(set(triggers)) != len(triggers):
            errors.append(f"{rid}: triggers 有重复")

        if not _has_cjk(raw.get("description")):
            errors.append(f"{rid}: description 须为中文说明")

        target = _check_target(rid, wp_code, raw.get("target"), errors)
        source = _check_source(rid, raw.get("source"), errors, known_derivations, binding_spec)
        if target is not None:
            if stage == "note" and target.domain != "note":
                errors.append(f"{rid}: stage=note 的目标必须是附注域")
            if stage in ("source", "derived") and target.domain != "workpaper":
                errors.append(f"{rid}: stage={stage} 的目标必须是底稿域")
            key = target.identity()
            if key in seen_targets:
                errors.append(f"{rid}: 与 {seen_targets[key]} 写同一目标（一个单元格只能有一个写入方）")
            else:
                seen_targets[key] = rid
        if target is not None and source is not None:
            rules.append(PushRule(
                rule_id=rid, page_key=page_key, stage=stage, policy=policy,
                target=target, source=source, triggers=tuple(triggers),
                description=raw.get("description"),
            ))

    # 整份拒收：任一条有问题都不返回部分结果（否则那条推送会静默消失）
    if errors:
        raise PushRuleError(errors)
    return tuple(rules)


@lru_cache(maxsize=8)
def _load_cached(
    path: str,
    mtime_ns: int,
    binding_specs_key: tuple[tuple[str, BindingSpec], ...] | None,
    derivations: tuple[str, ...] | None,
    registered_codes: tuple[str, ...],
) -> tuple[PushRule, ...]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_rules(
        document,
        binding_specs=(dict(binding_specs_key) if binding_specs_key is not None else None),
        known_derivations=derivations,
        registered_wp_codes=registered_codes,
    )


def _binding_specs_from_registry(codes: Collection[str]) -> dict[str, BindingSpec]:
    """从注册表快照提取可哈希的规则校验元信息。"""
    from app.services.formula_push.bindings import get_binding

    specs: dict[str, BindingSpec] = {}
    for code in codes:
        binding = get_binding(code)
        specs[code] = BindingSpec(
            four_table_slots=frozenset(binding.four_table_slots),
            derivations=frozenset(binding.derivations),
            tb_columns=frozenset(binding.tb_columns),
        )
    return specs


def _normalize_binding_specs(
    binding_specs: Mapping[str, BindingSpec],
) -> tuple[tuple[str, BindingSpec], ...]:
    normalized: list[tuple[str, BindingSpec]] = []
    for code, spec in binding_specs.items():
        if not isinstance(code, str) or not isinstance(spec, BindingSpec):
            raise TypeError("binding_specs 必须是 str -> BindingSpec 映射")
        normalized.append((code, spec))
    return tuple(sorted(normalized))


def load_rules(
    path: Path | str = RULES_PATH,
    *,
    binding_specs: Mapping[str, BindingSpec] | None = None,
    known_derivations: Collection[str] | None = None,
) -> tuple[PushRule, ...]:
    """读取并校验规则清单（按文件修改时间和 binding 注册表版本缓存）。"""
    from app.services.formula_push.bindings import supported_wp_codes

    p = Path(path)
    registered_codes = tuple(supported_wp_codes())
    if binding_specs is None and known_derivations is not None:
        # 旧调用方显式提供派生注册表时，保留旧的纯解析语义；生产引擎传 binding_specs。
        specs_key = None
    else:
        if binding_specs is None:
            binding_specs = _binding_specs_from_registry(registered_codes)
        specs_key = _normalize_binding_specs(binding_specs)
    derivations = tuple(sorted(known_derivations)) if known_derivations is not None else None
    return _load_cached(str(p.resolve()), p.stat().st_mtime_ns, specs_key, derivations, registered_codes)


def rules_for(
    rules: tuple[PushRule, ...], *, wp_code: str | None = None, trigger: str | None = None
) -> tuple[PushRule, ...]:
    """按底稿 / 触发事件筛选（保持清单顺序）。"""
    return tuple(
        r for r in rules
        if (wp_code is None or r.wp_code == wp_code) and (trigger is None or r.fires_on(trigger))
    )
