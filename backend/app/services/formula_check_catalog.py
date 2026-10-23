"""全平台校对规则目录（spec formula-governance-coverage-closure R3，design §5）。

平台里的校对 / 勾稽 / 质控规则分散在十几处（代码种子、规则文件、全局设置），各自执行、各自展示。
这里用一张登记表 ``SOURCES`` 把它们收齐成**只读**目录：每个来源写明分类、在哪里执行、能否在平台里编辑
（去哪编辑）。不新增存储、不收编执行器（ADR-FGC-004）——先让用户看得见全部规则。

* 规则文件型来源按文件修改时间缓存；全局设置型来源（表间审核全局层、报表审核公式）每次现查数据库。
* ``EXCLUDED``：文件名带 rule / check 但不是校对规则的数据文件（附理由）。守卫要求 ``backend/data`` 下每个
  这样的 JSON 不在 ``SOURCES`` 就在 ``EXCLUDED``，且两张表都没有失效条目（见 ``registration_problems``）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_CYCLE_GLOB = "*_cycle_validation_rules.json"
_STD_LABEL = {"soe": "国企", "listed": "上市"}
_SEVERITY_LABEL = {
    "blocking": "阻断", "error": "错误", "warning": "警告", "info": "提示",
    "logic_check": "勾稽", "reasonability": "提醒",
}
_STANDARD_LABEL = {
    "soe_standalone": "国企单体", "soe_consolidated": "国企合并", "listed_standalone": "上市单体",
    "listed_consolidated": "上市合并", "enterprise": "企业会计准则", "*": "通用",
}

Rule = dict[str, Any]


def _rule(rid: Any, label: Any, expression: Any, *, severity: Any = "", scope: Any = "",
          fields: dict[str, Any] | None = None) -> Rule:
    sev = str(severity or "")
    out: Rule = {"id": str(rid or ""), "label": str(label or "").strip(), "expression": str(expression or "").strip(),
                 "severity": sev, "severity_label": _SEVERITY_LABEL.get(sev, sev), "scope": str(scope or "").strip()}
    if fields is not None:
        out["fields"] = fields
    return out


def _json(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _relation(left: Any, operator: Any, right: Any, tolerance: Any = None) -> str:
    text = f"{left or ''} {operator or '='} {right or ''}".strip()
    return f"{text}（容差 {tolerance}）" if tolerance not in (None, "") else text


# ── 各来源加载器（静态来源同步、全局设置来源异步读库） ──────────────────────────────


def _report_builtin() -> list[Rule]:
    from app.services.formula_management.logic_check import _CROSS_CHECK_SEEDS

    return [_rule(s["id"], s["description"], s["expression"], severity="logic_check", scope="报表")
            for s in _CROSS_CHECK_SEEDS]


def _cross_check_preset() -> list[Rule]:
    out = []
    for i, r in enumerate(_json("cross_check_preset_rules.json")["rules"], start=1):
        fields = {k: r.get(k) for k in ("label", "left_ref", "operator", "right_ref", "tolerance", "description")}
        out.append(_rule(f"preset-{i}", r.get("label"), _relation(r.get("left_ref"), r.get("operator"),
                                                               r.get("right_ref"), r.get("tolerance")),
                         severity="logic_check", scope=r.get("category") or "", fields=fields))
    return out


def _consol_note_checks() -> list[Rule]:
    from app.services.note_check_rules import load_all_check_rules, rollforward_for

    def cols(indexes) -> str:
        return "、".join(str(i) for i in indexes) or "无"

    out = []
    for std in ("soe", "listed"):
        for section, rules in sorted(load_all_check_rules(std).items()):
            for r in rules:
                if r.mode == "column_balance":  # 列由标题行库按表头认（与执行同一份）
                    flow = rollforward_for(std, section)
                    expr = ("标题行库认不出期初 / 期末 / 增减列" if flow is None else
                            f"期初（列{flow.opening}）+ 增加（列{cols(flow.increase)}）− 减少（列{cols(flow.decrease)}）"
                            f"= 期末（列{flow.closing}）")
                else:
                    expr = (f"{r.self_row_label}（列{r.self_col_index}）= {r.peer_section_id} "
                            f"{r.peer_row_label}（列{r.peer_col_index}）")
                out.append(_rule(f"{std}:{r.check_id}", r.description, f"{expr}（容差 {r.tolerance}）",
                                 severity="logic_check", scope=f"{_STD_LABEL[std]} {section}"))
    return out


def _note_preset_checks() -> list[Rule]:
    data = _json("note_check_preset_formulas.json")
    out = []
    for std in ("soe", "listed"):
        for r in data.get(std) or []:
            if not isinstance(r, dict) or r.get("category") not in ("logic_check", "reasonability"):
                continue
            scope = f"{_STD_LABEL[std]} {r.get('note_section') or ''}{r.get('section_title') or ''}"
            out.append(_rule(f"{std}:{r.get('id')}", r.get("description"), r.get("formula"),
                             severity=r.get("category"), scope=scope))
    return out


def _note_disclosure_balance() -> list[Rule]:
    return [_rule(r.get("rule_id"), r.get("description"), _relation(r.get("left"), "=", r.get("right"),
                                                                    r.get("tolerance")),
                  severity=r.get("severity"), scope=r.get("section_id"))
            for r in _json("note_disclosure_balance_rules.json")["rules"]]


def _wp_cross_account() -> list[Rule]:
    out = []
    for r in _json("cross_account_rules.json")["rules"]:
        cycles = "、".join(r.get("applicable_cycles") or [])
        tol = r.get("tolerance")
        out.append(_rule(r.get("rule_id"), r.get("description"),
                         f"{r.get('formula') or ''}" + (f"（容差 {tol}）" if tol not in (None, "") else ""),
                         severity=r.get("severity"), scope=f"{cycles} 循环" if cycles else ""))
    return out


def cycle_rule_files() -> tuple[str, ...]:
    return tuple(sorted(p.name for p in DATA_DIR.glob(_CYCLE_GLOB)))


def _cycle_validation() -> list[Rule]:
    out = []
    for name in cycle_rule_files():
        for r in _json(name)["rules"]:
            out.append(_rule(r.get("rule_id"), r.get("description") or r.get("rule_name"), r.get("formula"),
                             severity=r.get("severity"), scope=r.get("wp_code")))
    return out


def _a17() -> list[Rule]:
    out = []
    for r in _json("a17_consistency_rules.json"):
        parts = [f"{r.get('source_chapter') or '—'}：{r.get('source_pattern') or '（空）'}"]
        if r.get("target_chapter"):
            parts.append(f"{r['target_chapter']}：{r.get('target_pattern') or '（空）'}")
        out.append(_rule(r.get("rule_id"), r.get("description"), f"{r.get('condition') or ''}（{'；'.join(parts)}）",
                         severity=r.get("severity"), scope="A17 审计报告"))
    return out


def _qc_rules() -> list[Rule]:
    out = []
    for name in ("qc_rule_definitions_seed.json", "audit_log_rules_seed.json"):
        for r in _json(name):
            out.append(_rule(r.get("rule_code"), f"{r.get('title') or ''}：{r.get('description') or ''}".strip("："),
                             f"{r.get('expression_type') or ''}：{r.get('expression') or ''}",
                             severity=r.get("severity"), scope=f"{r.get('scope') or ''} {r.get('category') or ''}"))
    return out


def _cross_wp_references() -> list[Rule]:
    out = []
    for r in _json("cross_wp_references.json").get("references") or []:
        targets = "、".join(
            f"{t.get('wp_code') or ''} {t.get('sheet') or ''}!{t.get('cell') or ''}".strip()
            for t in (r.get("targets") or []) if isinstance(t, dict))
        source = f"{r.get('source_wp') or ''} {r.get('source_sheet') or ''}!{r.get('source_cell') or ''}".strip()
        out.append(_rule(r.get("ref_id"), r.get("description"), f"{source} → {targets or '（无目标）'}",
                         scope=r.get("source_wp")))
    return out


async def _cross_check_global(db: AsyncSession) -> list[Rule]:
    from app.models.formula_setting_models import FormulaSetting

    rows = (await db.execute(sa.select(FormulaSetting).where(
        FormulaSetting.domain == "cross_check", FormulaSetting.layer == "global",
        FormulaSetting.is_deleted == sa.false()).order_by(FormulaSetting.scope, FormulaSetting.slot_key))).scalars()
    out = []
    for row in rows:
        d = row.definition or {}
        if d.get("disabled"):
            continue
        out.append(_rule(row.slot_key, d.get("label") or row.slot_label,
                         _relation(d.get("left_ref"), d.get("operator"), d.get("right_ref"), d.get("tolerance")),
                         severity="logic_check", scope=_STANDARD_LABEL.get(row.scope, row.scope)))
    return out


async def _report_audit(db: AsyncSession) -> list[Rule]:
    from app.models.report_models import ReportConfig

    rows = (await db.execute(sa.select(ReportConfig).where(
        ReportConfig.formula_category.in_(("logic_check", "reasonability")),
        ReportConfig.is_deleted == sa.false(),
        ~ReportConfig.applicable_standard.like("project:%"),
    ).order_by(ReportConfig.applicable_standard, ReportConfig.report_type, ReportConfig.row_number))).scalars()
    out = []
    for row in rows:
        if not (row.formula or "").strip():
            continue
        rt = row.report_type.value if hasattr(row.report_type, "value") else str(row.report_type)
        label = row.row_name + (f"：{row.formula_description}" if row.formula_description else "")
        out.append(_rule(f"{rt}:{row.row_code}", label, row.formula, severity=row.formula_category,
                         scope=_STANDARD_LABEL.get(row.applicable_standard, row.applicable_standard)))
    return out


# ── 登记表 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CheckSource:
    key: str
    label: str
    category: str  # 报表 / 附注 / 底稿 / 质控 / 关系
    runs_in: str  # 执行位置（现查代码得出）
    edit_where: str  # 空 = 平台里不可编辑；否则写去哪编辑
    loader: Callable[..., Any]
    files: tuple[str, ...] = ()  # backend/data 下的规则文件（登记守卫用）
    from_db: bool = False  # 全局设置层（读库）
    allow_empty: bool = False  # 全局层可以一条都没有


SOURCES: tuple[CheckSource, ...] = (
    CheckSource("report_builtin", "报表勾稽（内置）", "报表", "公式管理中心表间审核「执行校验」，结果落库",
                "", _report_builtin),
    CheckSource("cross_check_global", "表间审核规则（全局层）", "报表",
                "表间审核「执行校验」：本项目生效 = 全局 + 本项目适配", "公式管理中心「表间审核」/ 全局公式设置",
                _cross_check_global, from_db=True, allow_empty=True),
    CheckSource("cross_check_preset", "表间审核预置", "报表", "新增表间审核规则时「从预置选用」",
                "选用后可改", _cross_check_preset, files=("cross_check_preset_rules.json",)),
    CheckSource("report_audit", "报表审核公式", "报表", "报表页「审核」（与表间审核同一严格求值）",
                "公式管理中心报表公式（类别选逻辑审核 / 提示合理性）", _report_audit, from_db=True, allow_empty=True),
    CheckSource("consol_note_checks", "合并附注勾稽", "附注", "合并附注页勾稽校验", "", _consol_note_checks,
                files=("consol_note_sections_soe.json", "consol_note_sections_listed.json")),
    CheckSource("note_preset_checks", "附注预置勾稽 / 提醒", "附注", "公式管理中心附注预设（导入为附注公式后执行）",
                "导入后在附注公式里改", _note_preset_checks, files=("note_check_preset_formulas.json",)),
    CheckSource("note_disclosure_balance", "附注披露平衡", "附注", "暂未接入执行（NoteDisclosureBalanceService 无调用方）",
                "", _note_disclosure_balance, files=("note_disclosure_balance_rules.json",)),
    CheckSource("wp_cross_account", "底稿跨科目校验", "底稿", "底稿跨科目校验", "项目可另加自定义规则",
                _wp_cross_account, files=("cross_account_rules.json",)),
    CheckSource("cycle_validation", "循环校验规则", "底稿",
                "签字前一致性门禁（同编号规则由代码实现）/ 底稿校验规则展示", "", _cycle_validation,
                files=cycle_rule_files()),
    CheckSource("a17_consistency", "A17 跨章节一致性", "底稿", "A17 审计报告汇总 / 导出", "", _a17,
                files=("a17_consistency_rules.json",)),
    CheckSource("qc_rules", "质控规则", "质控", "质控引擎（启停以 qc_rule_definitions 表为准）", "质控规则管理",
                _qc_rules, files=("qc_rule_definitions_seed.json", "audit_log_rules_seed.json")),
    CheckSource("cross_wp_references", "跨底稿引用（取数关系，非校对）", "关系", "底稿关系图 / 依赖图 / 过期传播",
                "", _cross_wp_references, files=("cross_wp_references.json",)),
)

#: 文件名带 rule / check 但不是校对规则（目录前缀以「/」结尾）
EXCLUDED: dict[str, str] = {
    "formula_push_rules.json": "公式推送取数规则，已纳入公式治理内核 push 域",
    "ledger_recognition_rules.json": "账套导入的表格识别规则",
    "audit_report_templates/matching_rules.json": "审计报告模板匹配规则",
    "note_columns_rules.json": "附注表格列结构生成规则",
    "note_guidance_rules.json": "附注编制指引生成规则",
    "note_wp_mapping_rules.json": "附注与底稿的章节映射",
    "review_checklist_templates.json": "复核清单模板（人工勾选，不是公式校对）",
    "sheet_mapping_rules.json": "底稿 sheet 名称映射",
    "workpaper_sync_alert_rules.json": "底稿同步运维告警规则",
    "workpaper_sync_contracts/": "底稿同步契约（文件名里的 check 是底稿名称）",
    "wp_parse_rules.json": "底稿解析规则",
    "wp_parse_rules_extended.json": "底稿解析规则（扩展）",
}

_cache: dict[str, tuple[tuple[int, ...], list[Rule]]] = {}


def _mtimes(source: CheckSource) -> tuple[int, ...]:
    return tuple((DATA_DIR / f).stat().st_mtime_ns for f in source.files)


async def load_source(db: AsyncSession | None, source: CheckSource) -> list[Rule]:
    if source.from_db:
        if db is None:
            return []
        async with db.begin_nested():  # 只读；失败不污染调用方事务
            return await source.loader(db)
    key = _mtimes(source) if source.files else ()
    hit = _cache.get(source.key)
    if hit is not None and hit[0] == key:
        return hit[1]
    rules = source.loader()
    _cache[source.key] = (key, rules)
    return rules


def _summary(source: CheckSource, rules: list[Rule] | None, error: str | None) -> dict[str, Any]:
    return {
        "key": source.key, "label": source.label, "category": source.category, "runs_in": source.runs_in,
        "editable": bool(source.edit_where), "edit_where": source.edit_where, "files": list(source.files),
        "from_db": source.from_db, "rule_count": len(rules) if rules is not None else 0, "error": error,
    }


async def build_check_catalog(db: AsyncSession | None, *, source: str | None = None, keyword: str = "",
                              limit: int = 500) -> dict[str, Any]:
    """来源清单 + 规则。``source`` 给定只返回该来源的规则；``keyword`` 跨来源检索（编号 / 名称 / 公式 / 范围）。

    单个来源加载失败只标在该来源上（``error``），不拖垮整个目录。
    """
    kw = keyword.strip().lower()
    out, total = [], 0
    for s in SOURCES:
        if source and s.key != source:
            continue
        try:
            rules = await load_source(db, s)
            error = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("[check-catalog] 来源 %s 加载失败：%s", s.key, exc)
            rules, error = None, f"加载失败：{exc}"
        item = _summary(s, rules, error)
        total += item["rule_count"]
        if rules is not None and (source or kw):
            picked = [r for r in rules if not kw or any(kw in str(r[k]).lower()
                                                        for k in ("id", "label", "expression", "scope"))]
            item["matched"] = len(picked)
            item["rules"] = picked[:limit]
        out.append(item)
    if source and not out:
        raise KeyError(source)
    return {"sources": out, "total": total}


# ── 登记守卫 ──────────────────────────────────────────────────────────────────


def rule_like_files(data_dir: Path = DATA_DIR) -> list[str]:
    """``data_dir`` 下文件名带 rule / check 的 JSON（相对路径，正斜杠）。"""
    return sorted(p.relative_to(data_dir).as_posix() for p in data_dir.rglob("*.json")
                  if "rule" in p.name.lower() or "check" in p.name.lower())


def registration_problems(data_dir: Path = DATA_DIR, sources: tuple[CheckSource, ...] = SOURCES,
                          excluded: dict[str, str] | None = None) -> list[str]:
    """未登记的规则文件 / 失效的登记条目 / 无理由排除（空 = 登记完整）。"""
    excluded = EXCLUDED if excluded is None else excluded
    registered = {f for s in sources for f in s.files}
    problems = []
    for rel in rule_like_files(data_dir):
        if rel in registered or rel in excluded or any(rel.startswith(k) for k in excluded if k.endswith("/")):
            continue
        problems.append(f"未登记：{rel}（是校对规则就登记进 SOURCES，不是就写进 EXCLUDED 并写明理由）")
    for rel in sorted(registered):
        if not (data_dir / rel).is_file():
            problems.append(f"SOURCES 登记的文件不存在：{rel}")
    for rel, why in sorted(excluded.items()):
        if not why.strip():
            problems.append(f"EXCLUDED 缺理由：{rel}")
        path = data_dir / rel.rstrip("/")
        if not (path.is_dir() if rel.endswith("/") else path.is_file()):
            problems.append(f"EXCLUDED 条目已失效：{rel}")
    return problems
