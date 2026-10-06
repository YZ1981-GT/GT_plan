"""Tier A 锚点族 binding（单公式审定表核对行）。

18 个底稿编码 / 21 条锚点，全部是 ``TB(...)`` 单值公式、``policy=system``、无派生、无四表叶子。
通过 ``binding_for(code)`` 工厂按科目实例化，注册表写法形如::

    "D1": "app.services.formula_push.bindings.tier_a:binding_for('D1')"

附注推送：``note_rows()`` 从试算表取审定数构建附注行，支持单科目（一行）和多科目（多行 + 合计行）。
损益类科目自动用 ``本期发生额`` 取数。

D1 特殊处理：``note_rows()`` 从 entries 中读 ``D1-cat-rows``（分类明细）和 ``D1-bd-notetype-rows``
（坏账按票据种类）快照，按 slug 聚合后返回六字段行（余额/坏账准备/账面价值 × 期末期初），
与前端 ``buildD1SyncPayload`` 行结构逐标签对拍。

spec: formula-push-all-subjects-rollout · design §九 · 需求 7.2, 7.3
spec: formula-push-note-rollout-batch-c · Task 2
spec: formula-push-note-rollout-batch-e · Task 2 · 需求 E2
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from app.services.formula_push.bindings import TargetSkip, WorkpaperTarget
from app.services.formula_push.js_compat import js_number_to_string
from app.services.formula_push.rules import PushRule, workpaper_addr_id
from app.services.formula_push.sources import FormulaSources, load_tb_audited

_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_PRESETS_PATH = _DATA_DIR / "d_cycle_extraction" / "d_cycle_extraction_presets.json"
_WP_MAPPING_PATH = _DATA_DIR / "wp_account_mapping.json"

#: TB() 第二参数（列名）提取正则
_TB_ARG_RE = re.compile(r"TB\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")

#: 损益类科目前缀（6 开头）：附注取「本期发生额 / 上期发生额」而非「期末余额 / 年初余额」
_PL_PREFIX = "6"

#: D1 分类快照 item_id（与前端 useD1DetailCategory.ts STORAGE_KEY 一致）
_D1_CAT_ROWS_KEY = "D1-cat-rows"
#: D1 坏账按票据种类快照 item_id（与前端 d1AdjudicationModel.ts D1_BD_NOTETYPE_KEY 一致）
_D1_BD_NOTETYPE_KEY = "D1-bd-notetype-rows"

#: 固定行 rowId → 稳定 slug（与前端 d1CategorySlug 同构）
_D1_FIXED_SLUGS: dict[str, str] = {
    "fixed-bank": "bank",
    "fixed-commercial": "commercial",
}
#: slug → 附注中文行标签（用作 note_label 匹配附注模板行）
_D1_SLUG_LABELS: dict[str, str] = {
    "bank": "银行承兑汇票",
    "commercial": "商业承兑汇票",
}


@dataclass
class TierASources:
    """Tier A binding 的取数结果（只有试算表审定口径）。"""
    formula: FormulaSources
    template_type: str | None = None
    warnings: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _load_presets() -> dict[str, list[dict]]:
    """读取预设库（进程内缓存，按文件内容；不含以 ``_`` 开头的元数据键）。"""
    raw = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if isinstance(v, list) and not k.startswith("_")}


@lru_cache(maxsize=1)
def _load_wp_mapping() -> dict[str, str]:
    """按 wp_code 加载科目名映射（``account_name``），进程内缓存。"""
    raw = json.loads(_WP_MAPPING_PATH.read_text(encoding="utf-8"))
    return {
        item["wp_code"]: item.get("account_name", "")
        for item in raw.get("mappings", [])
        if item.get("wp_code")
    }


def _extract_account_codes(expression: str) -> tuple[str, ...]:
    """从 ``TB('code','col')`` 表达式提取所有科目码（去重、排序）。"""
    codes = sorted({m.group(1) for m in _TB_ARG_RE.finditer(expression)})
    if not codes:
        raise ValueError(f"表达式 {expression!r} 中未找到 TB() 调用")
    return tuple(codes)


def _presets_for(wp_code: str) -> list[dict]:
    """取指定底稿编码的预设列表；不存在则抛 KeyError。"""
    presets = _load_presets()
    if wp_code not in presets:
        raise KeyError(f"底稿 {wp_code} 在 Tier A 预设库中不存在")
    return presets[wp_code]


def _all_account_codes(wp_code: str) -> tuple[str, ...]:
    """汇总该底稿全部锚点公式里引用的科目码（去重排序）。"""
    codes: set[str] = set()
    for preset in _presets_for(wp_code):
        for m in _TB_ARG_RE.finditer(preset["expression"]):
            codes.add(m.group(1))
    return tuple(sorted(codes))


def _is_pl_code(code: str) -> bool:
    """损益类科目：标准码以 6 开头。"""
    return code.startswith(_PL_PREFIX)


def _safe_json_array(raw: Any) -> list[dict]:
    """安全解析 JSON 数组字符串；非字符串 / 空 / 非数组一律返空列表。"""
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _safe_float(val: Any) -> float:
    """安全取数值；非数值型返回 0.0。"""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _d1_category_slug(row_id: str, category: str = "") -> str:
    """D1 行 slug 计算，与前端 ``d1CategorySlug`` 同构。

    ``fixed-bank`` → ``bank``、``fixed-commercial`` → ``commercial``、
    ``dynamic-{uuid}`` → ``c-{uuid}``、无 rowId 时按名称关键字兜底。
    """
    rid = (row_id or "").strip()
    if rid in _D1_FIXED_SLUGS:
        return _D1_FIXED_SLUGS[rid]
    if not rid:
        if "银行" in category:
            return "bank"
        if "商业" in category:
            return "commercial"
        return ""
    stripped = re.sub(r"^(dynamic|fixed)-", "", rid)
    safe = re.sub(r"[^A-Za-z0-9_-]", "", stripped)
    return f"c-{safe}" if safe else ""


def _d1_note_rows_from_entries(entries: Mapping[str, Any]) -> list[dict]:
    """从 D1 entries 快照构建六字段附注行。

    读 ``D1-cat-rows``（分类明细 → 余额/balance）和 ``D1-bd-notetype-rows``
    （坏账按票据种类 → 坏账准备/provision），按 slug 聚合后计算六字段。

    分类快照公式（与前端 ``recalcRow`` + ``readD1CategoryAmounts`` 同口径）：
    - ``priorAudited = priorUnadjusted + priorAje + priorRje``
    - ``currentUnadjusted = priorAudited + currentIncrease - currentDecrease``
    - ``currentAudited = currentUnadjusted + currentAje + currentRje``
    → ``end_balance = currentAudited``，``prior_balance = priorAudited``

    坏账按票据种类公式（``readD1BadDebtByNoteType`` 同口径）：
    - ``priorAudited = priorUnadjusted + priorAje + priorRje``
    - ``currentAudited = currentUnadjusted + currentAje + currentRje``
    → ``end_provision = currentAudited``，``prior_provision = priorAudited``

    账面价值 = 余额 - 坏账准备（有任一侧缺失则不计算，标 unresolved）。
    """
    cat_raw = entries.get(_D1_CAT_ROWS_KEY)
    bd_raw = entries.get(_D1_BD_NOTETYPE_KEY)

    cat_rows = _safe_json_array(cat_raw)
    bd_rows = _safe_json_array(bd_raw)

    has_cat = len(cat_rows) > 0
    has_bd = len(bd_rows) > 0

    if not has_cat and not has_bd:
        return []

    # ── 聚合分类数据（余额） ──────────────────────────────────────────
    # slug → {end_balance, prior_balance}
    cat_by_slug: dict[str, dict[str, float]] = {}
    slug_labels: dict[str, str] = {}  # slug → 中文标签（取第一次出现的 category 名）
    slug_order: list[str] = []  # 保持插入顺序

    for row in cat_rows:
        row_id = str(row.get("rowId", ""))
        category = str(row.get("category", ""))
        slug = _d1_category_slug(row_id, category)
        if not slug:
            continue

        prior_unadj = _safe_float(row.get("priorUnadjusted"))
        prior_aje = _safe_float(row.get("priorAje"))
        prior_rje = _safe_float(row.get("priorRje"))
        prior_audited = prior_unadj + prior_aje + prior_rje

        cur_increase = _safe_float(row.get("currentIncrease"))
        cur_decrease = _safe_float(row.get("currentDecrease"))
        cur_unadj = prior_audited + cur_increase - cur_decrease
        cur_aje = _safe_float(row.get("currentAje"))
        cur_rje = _safe_float(row.get("currentRje"))
        cur_audited = cur_unadj + cur_aje + cur_rje

        if slug in cat_by_slug:
            cat_by_slug[slug]["end_balance"] += cur_audited
            cat_by_slug[slug]["prior_balance"] += prior_audited
        else:
            cat_by_slug[slug] = {"end_balance": cur_audited, "prior_balance": prior_audited}
            slug_order.append(slug)

        if slug not in slug_labels:
            slug_labels[slug] = category or _D1_SLUG_LABELS.get(slug, slug)

    # ── 聚合坏账数据（坏账准备） ──────────────────────────────────────
    # slug → {end_provision, prior_provision}
    bd_by_slug: dict[str, dict[str, float]] = {}

    for row in bd_rows:
        row_id = str(row.get("rowId", ""))
        note_type = str(row.get("noteType", row.get("category", "")))
        slug = _d1_category_slug(row_id, note_type)
        if not slug:
            continue

        prior_unadj = _safe_float(row.get("priorUnadjusted"))
        prior_aje = _safe_float(row.get("priorAje"))
        prior_rje = _safe_float(row.get("priorRje"))
        prior_audited = prior_unadj + prior_aje + prior_rje

        cur_unadj = _safe_float(row.get("currentUnadjusted"))
        cur_aje = _safe_float(row.get("currentAje"))
        cur_rje = _safe_float(row.get("currentRje"))
        cur_audited = cur_unadj + cur_aje + cur_rje

        if slug in bd_by_slug:
            bd_by_slug[slug]["end_provision"] += cur_audited
            bd_by_slug[slug]["prior_provision"] += prior_audited
        else:
            bd_by_slug[slug] = {"end_provision": cur_audited, "prior_provision": prior_audited}

        # 坏账行可能有分类没有的 slug（虽罕见），补进顺序
        if slug not in slug_labels:
            slug_labels[slug] = note_type or _D1_SLUG_LABELS.get(slug, slug)
        if slug not in slug_order:
            slug_order.append(slug)

    # ── 组装六字段行 ──────────────────────────────────────────────────
    result: list[dict] = []
    for slug in slug_order:
        cat = cat_by_slug.get(slug)
        bd = bd_by_slug.get(slug)
        label = slug_labels.get(slug, slug)

        end_balance = cat["end_balance"] if cat else None
        prior_balance = cat["prior_balance"] if cat else None
        end_provision = bd["end_provision"] if bd else None
        prior_provision = bd["prior_provision"] if bd else None

        # 账面价值 = 余额 - 坏账准备；任一侧 None 则 book_value 也 None
        if end_balance is not None and end_provision is not None:
            end_book_value = end_balance - end_provision
        else:
            end_book_value = None
        if prior_balance is not None and prior_provision is not None:
            prior_book_value = prior_balance - prior_provision
        else:
            prior_book_value = None

        result.append({
            "key": f"D1-note-{slug}",
            "note_label": label,
            "label": slug,
            "is_total": False,
            "is_memo": False,
            "end_balance": end_balance,
            "end_balance_resolved": end_balance is not None,
            "end_provision": end_provision,
            "end_provision_resolved": end_provision is not None,
            "end_book_value": end_book_value,
            "end_book_value_resolved": end_book_value is not None,
            "prior_balance": prior_balance,
            "prior_balance_resolved": prior_balance is not None,
            "prior_provision": prior_provision,
            "prior_provision_resolved": prior_provision is not None,
            "prior_book_value": prior_book_value,
            "prior_book_value_resolved": prior_book_value is not None,
        })

    return result


def _tb_value(
    tb_data: Mapping[str, Mapping[str, Decimal]], code: str, column: str,
) -> tuple[float, bool]:
    """从 TB 快照取值；返回 ``(value, resolved)``。

    ``resolved=False`` 表示 TB 无该科目行（科目不存在），值为 0。
    """
    bucket = tb_data.get(code)
    if bucket is None:
        return 0.0, False
    raw = bucket.get(column, Decimal("0"))
    return float(raw), True


class TierAAnchorBinding:
    """Tier A 单公式锚点族 binding：只有 ``source/formula`` 单值目标，无派生、无四表叶子。

    附注推送通过 ``note_rows()`` 从试算表取审定数构建附注行。
    """

    def __init__(self, wp_code: str, account_prefixes: tuple[str, ...], *, derivations: frozenset[str] | None = None) -> None:
        self.wp_code = wp_code
        self.account_prefixes = account_prefixes
        self.derivations: frozenset[str] = derivations or frozenset()
        self.four_table_slots: frozenset[str] = frozenset()
        self.tb_columns: frozenset[str] = frozenset({"期末余额", "年初余额", "本期发生额"})
        self.paper_codes: tuple[str, ...] = (wp_code,)
        # 附注推送用：load_sources 时缓存 TB 数据，note_rows 读取
        self._last_tb_data: Mapping[str, Mapping[str, Decimal]] | None = None
        # 科目名（从 wp_account_mapping 加载，用作附注行 label）
        self._account_name: str = _load_wp_mapping().get(wp_code, wp_code)

    async def load_sources(self, db: Any, project_id: UUID, year: int, wp_id: UUID | None) -> TierASources:
        """取齐推送所需的全部源数据（只有试算表审定口径）。"""
        warnings: list[str] = []
        tb = await load_tb_audited(db, project_id, year, self.account_prefixes)
        if len(tb.company_codes) > 1:
            warnings.append(f"试算表含多个公司编码 {list(tb.company_codes)}，按全部合计")
        # 缓存 TB 数据供 note_rows 使用（engine 的 note_rows 签名不传 sources）
        self._last_tb_data = tb.tb_data if tb.available else None
        # 加载附注模板类型
        template_type = await _load_template_type(db, project_id)
        return TierASources(formula=FormulaSources(tb=tb), template_type=template_type, warnings=warnings)

    def workpaper_targets(
        self, rule: PushRule, entries: Mapping[str, Any], sources: TierASources,
        *, paper_code: str | None = None,
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        target = rule.target
        if target.domain != "workpaper":
            raise ValueError(f"{rule.rule_id} 不是底稿目标")
        kind = rule.source.kind
        if kind != "formula":
            raise ValueError(f"{rule.rule_id}: Tier A 只支持 formula 来源，收到 {kind!r}")

        addr = workpaper_addr_id(self.wp_code, target.sheet_code, target.item_id)
        reason = sources.formula.unavailable_reason(rule.source.context_map)
        if reason:
            return [], [TargetSkip(rule.rule_id, addr, reason)]

        from app.services.formula_engine import execute
        result = execute(rule.source.expression, sources.formula.context_for(rule.source.context_map))
        if result.errors or result.blocked:
            return [], [TargetSkip(rule.rule_id, addr, "公式求值失败：" + "；".join(result.errors))]
        value: Any = float(result.value)
        return [WorkpaperTarget(
            rule_id=rule.rule_id, policy=rule.policy, addr_id=addr, item_id=target.item_id,
            formula_value=value, current_value=entries.get(target.item_id),
        )], []

    def apply(self, entries: dict[str, Any], target: WorkpaperTarget, value: Any) -> bool:
        """单值键写入；返回存储值是否改变。"""
        old = entries.get(target.item_id)
        new = "" if value is None else js_number_to_string(float(value))
        entries[target.item_id] = new
        return old != new

    def note_rows(self, entries: Mapping[str, Any], template_type: str, rule: PushRule) -> list[dict]:
        """从试算表 / entries 取审定数构建附注行。

        **D1 特殊路径**（rule_id == "D1.note.main"）：
        从 entries 读 ``D1-cat-rows`` + ``D1-bd-notetype-rows`` 快照，按 slug 聚合后返回
        六字段行（end_balance / end_provision / end_book_value / prior_* 各三），
        与前端 ``buildD1SyncPayload`` 行结构逐标签对拍。

        **其他 Tier A 科目**：
        单科目：一行（label=科目名），ending/opening 取自 TB。
        多科目：每个科目一行 + 合计行。
        损益类（科目码 6 开头）：ending 取「本期发生额」，opening 取「上期发生额」。

        返回格式与 E1 的 ``note_rows`` 一致（D1 扩展为六字段 + 对应 ``*_resolved``）。

        spec: formula-push-note-rollout-batch-e · Task 2 · 需求 E2
        """
        # D1 六字段路径：从 entries 读分类 + 坏账快照
        if self.wp_code == "D1" and rule.rule_id == "D1.note.main":
            return _d1_note_rows_from_entries(entries)

        # 其他 Tier A 科目：从 TB 取数（原逻辑）
        tb_data = self._last_tb_data
        if tb_data is None:
            # TB 不可用（未导入四表），返回空让引擎跳过
            return []

        codes = self.account_prefixes
        # 确定取数列名
        # 对于损益类科目（6 开头），用「本期发生额」代替「期末余额」；
        # opening 统一用「年初余额」（对于损益类，这在 TB 口径下就是上期发生额）
        rows: list[dict] = []
        for code in codes:
            is_pl = _is_pl_code(code)
            ending_col = "本期发生额" if is_pl else "期末余额"
            opening_col = "年初余额"
            ending, ending_resolved = _tb_value(tb_data, code, ending_col)
            opening, opening_resolved = _tb_value(tb_data, code, opening_col)
            label = self._account_name if len(codes) == 1 else f"{self._account_name}_{code}"
            rows.append({
                "key": f"{self.wp_code}-note-{code}",
                "label": label,
                "note_label": label,
                "is_total": False,
                "is_memo": False,
                "ending": ending,
                "opening": opening,
                "ending_resolved": ending_resolved,
                "opening_resolved": opening_resolved,
            })

        # 多科目时追加合计行
        if len(codes) > 1:
            total_ending = sum(r["ending"] for r in rows)
            total_opening = sum(r["opening"] for r in rows)
            rows.append({
                "key": f"{self.wp_code}-note-total",
                "label": self._account_name,
                "note_label": self._account_name,
                "is_total": True,
                "is_memo": False,
                "ending": total_ending,
                "opening": total_opening,
                "ending_resolved": True,
                "opening_resolved": True,
            })

        return rows

    def entry_warnings(self, entries: Mapping[str, Any]) -> list[str]:
        return []


async def _load_template_type(db: Any, project_id: UUID) -> str | None:
    """附注模块渲染用的同一权威（与 E1 binding 同源，ADR-PUSH-003）。"""
    from app.services.disclosure_engine import DisclosureEngine

    value = await DisclosureEngine(db)._get_active_template_type(project_id)
    return value if isinstance(value, str) and value else None


#: 有附注推送规则的 Tier A 科目及其派生名
_NOTE_DERIVATIONS: dict[str, frozenset[str]] = {
    "D1": frozenset({"d1_note_main"}),
    "D2": frozenset({"d2_note_main"}),
    "D3": frozenset({"d3_note_main"}),
    "D4": frozenset({"d4_note_main"}),
    "D6": frozenset({"d6_note_main"}),
    "D7": frozenset({"d7_note_main"}),
    "I3": frozenset({"i3_note_main"}),
}


def binding_for(wp_code: str) -> TierAAnchorBinding:
    """族 binding 工厂：按预设库为指定底稿编码创建 TierAAnchorBinding 实例。"""
    codes = _all_account_codes(wp_code)
    derivations = _NOTE_DERIVATIONS.get(wp_code)
    return TierAAnchorBinding(wp_code=wp_code, account_prefixes=codes, derivations=derivations)
