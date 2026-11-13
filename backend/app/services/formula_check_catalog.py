"""全平台校对规则目录（spec formula-governance-coverage-closure R3，design §5）。

平台里的校对 / 勾稽 / 质控规则分散在十几处（代码种子、规则文件、全局设置），各自执行、各自展示。
这里用一张登记表 ``SOURCES`` 把它们收齐成**只读**目录：每个来源写明分类、在哪里执行、能否在平台里编辑
（去哪编辑）。不新增存储、不收编执行器（ADR-FGC-004）——先让用户看得见全部规则。

* 规则文件型来源按文件修改时间缓存；全局设置型来源（表间审核全局层、报表审核公式）每次现查数据库。
* ``EXCLUDED``：文件名带 rule / check 但不是校对规则的数据文件（附理由）。守卫要求 ``backend/data`` 下每个
  这样的 JSON 不在 ``SOURCES`` 就在 ``EXCLUDED``，且两张表都没有失效条目（见 ``registration_problems``）。
"""
from __future__ import annotations

import ast
import importlib
import json
import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
APP_DIR = Path(__file__).resolve().parents[1]
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
    # 严重级可能是 (str, Enum)（如 GateSeverity）：str() 会得到「GateSeverity.blocking」、标签查不到 ⇒ 取 .value
    sev = severity.value if isinstance(severity, Enum) else severity
    sev = "" if sev is None else f"{sev}"
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
    #: 执行器入口「模块.符号」（函数或类）。None = 本类没有执行器（见 ``unexecutable_reason``）。
    executor_entry: str | None = None
    #: 没有执行器、且定义本身不可执行（自然语言 / 伪表达式 / 依赖不存在）时写明原因；空 = 只展示
    unexecutable_reason: str = ""
    #: 执行状态的一句话说明（目录页展示）
    reason: str = ""
    #: 执行结果落库的表（``cross_check_results`` / ``wp_qc_results`` / ``gate_decisions``）；None = 本类结果不落库
    result_table: str | None = None
    #: ``cross_check_results`` 按 rule_id 过滤的 LIKE 模式（同一张表被多类来源共用）
    result_match: str = ""


SOURCES: tuple[CheckSource, ...] = (
    CheckSource("report_builtin", "报表勾稽（内置）", "报表", "公式管理中心表间审核「执行校验」，结果落库",
                "", _report_builtin,
                executor_entry="app.services.formula_management.logic_check.execute_report_cross_checks",
                reason="表间审核「执行校验」运行的内置勾稽，结果落库", result_table="cross_check_results",
                result_match="report-cross-check-%"),
    CheckSource("cross_check_global", "表间审核规则（全局层）", "报表",
                "表间审核「执行校验」：本项目生效 = 全局 + 本项目适配", "公式管理中心「表间审核」/ 全局公式设置",
                _cross_check_global, from_db=True, allow_empty=True,
                executor_entry="app.services.formula_settings.cross_check_rules.run_user_rules",
                reason="表间审核「执行校验」运行的用户规则（全局层 + 本项目），结果落库",
                result_table="cross_check_results", result_match="user:%"),
    CheckSource("cross_check_preset", "表间审核预置", "报表", "新增表间审核规则时「从预置选用」",
                "选用后可改", _cross_check_preset, files=("cross_check_preset_rules.json",),
                reason="只作选用模板；选用后成为表间审核规则，按表间审核执行"),
    CheckSource("report_audit", "报表审核公式", "报表", "报表页「审核」（与表间审核同一严格求值）",
                "公式管理中心报表公式（类别选逻辑审核 / 提示合理性）", _report_audit, from_db=True, allow_empty=True,
                executor_entry="app.services.report_audit_checks.run_report_audit",
                reason="报表「审核」按需计算，结果不落库"),
    CheckSource("consol_note_checks", "合并附注勾稽", "附注", "合并附注页勾稽校验", "", _consol_note_checks,
                files=("consol_note_sections_soe.json", "consol_note_sections_listed.json"),
                executor_entry="app.services.note_check_rules.check_note_cross_rules",
                reason="合并附注「勾稽校验」按所选节点现算，结果不落库"),
    CheckSource("note_preset_checks", "附注预置勾稽 / 提醒", "附注", "公式管理中心附注预设（导入为附注公式后执行）",
                "导入后在附注公式里改", _note_preset_checks, files=("note_check_preset_formulas.json",),
                executor_entry="app.services.note_formula_generator.execute_note_formulas",
                reason="附注「执行公式」时运行校对类公式，结果只进问题清单，不落库"),
    CheckSource("note_disclosure_balance", "附注披露平衡", "附注", "暂未接入执行（NoteDisclosureBalanceService 无调用方）",
                "", _note_disclosure_balance, files=("note_disclosure_balance_rules.json",),
                reason="NoteDisclosureBalanceService 存在但没有生产调用方，规则只展示"),
    CheckSource("wp_cross_account", "底稿跨科目校验", "底稿", "底稿跨科目校验", "项目可另加自定义规则",
                _wp_cross_account, files=("cross_account_rules.json",),
                executor_entry="app.services.wp_cross_check_service.CrossCheckService",
                reason="底稿「跨科目校验」与签字门禁运行，结果落库（XR 编号）",
                result_table="cross_check_results", result_match="XR-%"),
    CheckSource("cycle_validation", "循环校验规则", "底稿",
                "签字前一致性门禁（同编号规则由代码实现）/ 底稿校验规则展示", "", _cycle_validation,
                files=cycle_rule_files(),
                unexecutable_reason="规则表达式是伪表达式，引用的变量（如 audited、aje、actual_hours）没有求值器；"
                                    "签字门禁不读取这些 JSON，JSON 只用于底稿步骤映射展示与覆盖率统计",
                reason="表达式无求值器，JSON 不被执行；签字门禁按代码规则判定，门禁记录按项目、不分规则",
                result_table="gate_decisions"),
    CheckSource("a17_consistency", "A17 跨章节一致性", "底稿", "A17 审计报告汇总 / 导出", "", _a17,
                files=("a17_consistency_rules.json",),
                executor_entry="app.services.a17_consistency_checker.check_consistency",
                reason="A17 汇总接口与导出前自检现算，结果不落库"),
    CheckSource("qc_rules", "质控规则", "质控", "质控引擎（启停以 qc_rule_definitions 表为准）", "质控规则管理",
                _qc_rules, files=("qc_rule_definitions_seed.json", "audit_log_rules_seed.json"),
                executor_entry="app.services.qc_engine.QCEngine",
                reason="底稿自检（QCEngine）运行，结果落库到底稿质控结果表",
                result_table="wp_qc_results"),
    CheckSource("cross_wp_references", "跨底稿引用（取数关系，非校对）", "关系", "底稿关系图 / 依赖图 / 过期传播",
                "", _cross_wp_references, files=("cross_wp_references.json",),
                reason="取数关系，不做校对，只供依赖图展示"),
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
    "voucher_check_verdict_vocab.json": "凭证检查行结论的取值词表（只认这些字段与取值，不是校对规则；前端 voucherVerdict.ts 有同值副本并逐值对拍）",
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


def _execution_status(source: CheckSource) -> str:
    """执行状态：wired（入口可导入且可调用）/ display_only（只展示）/ not_executable（不可执行或入口失效）。

    这里只判登记的入口本身；「生产代码是否真的调用它」由 ``wiring_problems`` 扫源码守卫。
    """
    if not source.executor_entry:
        return "not_executable" if source.unexecutable_reason else "display_only"
    module, _, symbol = source.executor_entry.rpartition(".")
    try:
        target = getattr(importlib.import_module(module), symbol)
    except (ImportError, AttributeError):
        return "not_executable"
    return "wired" if callable(target) else "not_executable"


def _called_from_production(executor_entry: str, app_dir: Path) -> bool:
    """``app_dir`` 下（排除定义所在模块、排除测试）是否有文件从该模块 import 了该符号并调用了它。"""
    module, _, symbol = executor_entry.rpartition(".")
    defining = Path(importlib.import_module(module).__file__).resolve()
    for path in app_dir.rglob("*.py"):
        if path.resolve() == defining:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if symbol not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        imported = any(isinstance(n, ast.ImportFrom) and n.module == module
                       and any(a.name == symbol for a in n.names) for n in ast.walk(tree))
        if not imported:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if (isinstance(f, ast.Name) and f.id == symbol) or (isinstance(f, ast.Attribute) and f.attr == symbol):
                    return True
    return False


def wiring_problems(sources: tuple[CheckSource, ...] = SOURCES, app_dir: Path = APP_DIR) -> list[str]:
    """登记了执行器入口的来源：入口必须可调用，且生产代码真的调用它。空 = 接线完整。"""
    problems = []
    for s in sources:
        if not s.executor_entry:
            continue
        if _execution_status(s) != "wired":
            problems.append(f"{s.key}：执行器入口不存在或不可调用（{s.executor_entry}），不能标为已接入")
        elif not _called_from_production(s.executor_entry, app_dir):
            problems.append(f"{s.key}：执行器 {s.executor_entry} 没有生产代码调用（只在定义处或测试中出现）")
    return problems


# ── 最近一次执行结果（只读；不新增落库） ──────────────────────────────────────────

_NEVER_RUN: dict[str, Any] = {"at": None, "status": "never_run", "counts": {}}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


async def _last_run_cross_check(db: AsyncSession, source: CheckSource, project_id: uuid.UUID,
                                year: int | None = None) -> dict[str, Any]:
    """XR / 表间审核：``cross_check_results`` 里按 rule_id 过滤；指定 year 只取该年度，否则取最近记录年度。"""
    from app.models.wp_optimization_models import CrossCheckResult

    query = sa.select(CrossCheckResult.rule_id, CrossCheckResult.status, CrossCheckResult.year,
                      CrossCheckResult.checked_at).where(
        CrossCheckResult.project_id == project_id,
        CrossCheckResult.status != "rule_definition",
        CrossCheckResult.rule_id.like(source.result_match))
    if year is not None:
        query = query.where(CrossCheckResult.year == year)
    rows = (await db.execute(query.order_by(CrossCheckResult.checked_at.desc()))).all()
    if not rows:
        return {**_NEVER_RUN, **({"year": year} if year is not None else {})}
    result_year = year if year is not None else rows[0].year
    latest: dict[str, str] = {}
    for r in rows:
        if r.year == result_year:
            latest.setdefault(r.rule_id, r.status)
    counts = Counter(latest.values())
    if counts["fail"] + counts["failed"]:
        verdict = "failed"
    elif counts["error"]:
        verdict = "error"
    elif counts.keys() - {"pass", "passed", "fail", "failed", "error", "skip", "not_executed", "not_applicable"}:
        verdict = "unknown"
    elif counts["skip"] + counts["not_executed"]:
        verdict = "not_executed"
    elif counts["pass"] + counts["passed"]:
        verdict = "passed"
    else:
        verdict = "not_applicable"
    return {"at": _iso(rows[0].checked_at), "status": verdict, "counts": dict(counts), "year": result_year}


async def _last_run_qc(db: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    """质控：``wp_qc_results`` 经底稿关联到项目；每张底稿取最近一次自检。"""
    from app.models.workpaper_models import WorkingPaper, WpQcResult

    rows = (await db.execute(
        sa.select(WpQcResult.working_paper_id, WpQcResult.passed, WpQcResult.blocking_count,
                  WpQcResult.check_timestamp)
        .join(WorkingPaper, WorkingPaper.id == WpQcResult.working_paper_id)
        .where(WorkingPaper.project_id == project_id)
        .order_by(WpQcResult.check_timestamp.desc())
    )).all()
    if not rows:
        return dict(_NEVER_RUN)
    latest: dict[Any, Any] = {}
    for r in rows:
        latest.setdefault(r.working_paper_id, r)
    failed = sum(1 for r in latest.values() if not r.passed)
    return {
        "at": _iso(rows[0].check_timestamp), "status": "failed" if failed else "passed",
        "counts": {"working_papers": len(latest), "passed": len(latest) - failed, "failed": failed,
                   "blocking": sum(r.blocking_count or 0 for r in latest.values())},
    }


async def _last_run_gate(db: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    """签字门禁：``gate_decisions`` 最近一次 sign_off 结论（按项目记录，不分规则）。"""
    from app.models.phase14_models import GateDecision

    row = (await db.execute(
        sa.select(GateDecision.decision, GateDecision.hit_rules, GateDecision.created_at)
        .where(GateDecision.project_id == project_id, GateDecision.gate_type == "sign_off")
        .order_by(GateDecision.created_at.desc()).limit(1)
    )).first()
    if row is None:
        return dict(_NEVER_RUN)
    return {"at": _iso(row.created_at), "status": row.decision, "counts": {"hit_rules": len(row.hit_rules or [])}}


async def _last_run(db: AsyncSession, source: CheckSource, project_id: uuid.UUID,
                    year: int | None = None) -> dict[str, Any]:
    """只读结果查询失败返回 unavailable；仅 cross-check 能按明确年度过滤。"""
    try:
        async with db.begin_nested():
            if source.result_table == "cross_check_results":
                return await _last_run_cross_check(db, source, project_id, year)
            if source.result_table == "wp_qc_results":
                return await _last_run_qc(db, project_id)
            return await _last_run_gate(db, project_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[check-catalog] 来源 %s 最近结果读取失败：%s", source.key, exc)
        return {"at": None, "status": "unavailable", "counts": {}}


def _history_note(source: CheckSource, year: int | None) -> str:
    """每个来源的历史说明，告知用户所看到的结果范围。"""
    if source.result_table == "cross_check_results":
        scope = f"仅取 {year} 年度" if year is not None else "未指定年度，取最近记录年度"
        return f"{scope}内逐规则最新结果，可能来自多次运行，并非单次运行快照；不是目录每条规则的执行结论"
    if source.result_table == "wp_qc_results":
        return "项目各底稿最新自检结果汇总，并非单次运行快照；不按年度过滤，不能作为所选年度的执行证据"
    return "项目最近一次签字门禁记录；不按年度过滤，不能作为所选年度的执行证据；门禁记录不代表循环 JSON 规则执行"


async def build_check_catalog(db: AsyncSession | None, *, source: str | None = None, keyword: str = "",
                              limit: int = 500, project_id: uuid.UUID | None = None,
                              year: int | None = None) -> dict[str, Any]:
    """只读目录带入口能力；项目历史仅 cross-check 按 year 过滤，其他来源如实说明范围。"""
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
        execution = _execution_status(s)
        item = _summary(s, rules, error)
        item.update({"execution": execution, "execution_reason": s.reason, "executor": s.executor_entry,
                     "result_table": s.result_table})
        total += item["rule_count"]
        if rules is not None and (source or kw):
            picked = [r for r in rules if not kw or any(kw in str(r[k]).lower()
                                                        for k in ("id", "label", "expression", "scope"))]
            item["matched"] = len(picked)
            item["rules"] = [{**r, "execution": execution} for r in picked[:limit]]
        if s.result_table is None:
            item["last_run"], item["last_run_note"] = None, "本类结果不落库"
        elif project_id is None:
            item["last_run"], item["last_run_note"] = None, "未指定项目，未查询执行结果"
        elif db is None:
            item["last_run"] = {"at": None, "status": "unavailable", "counts": {}}
            item["last_run_note"] = "数据库会话不可用，未能读取项目历史；" + _history_note(s, year)
        else:
            item["last_run"] = await _last_run(db, s, project_id, year)
            note = _history_note(s, year)
            if item["last_run"]["status"] == "unavailable":
                note = "读取失败，未取得可用结论；" + note
            elif item["last_run"]["status"] == "never_run":
                note = "未找到此范围的运行记录，不代表校验通过；" + note
            item["last_run_note"] = note
        out.append(item)
    if source and not out:
        raise KeyError(source)
    wired = [i for i in out if i["execution"] == "wired"]
    return {"sources": out, "total": total, "source_count": len(out), "wired_count": len(wired),
            "wired_rule_count": sum(i["rule_count"] for i in wired)}


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
