"""报表过期状态读者清单冻结 + 各读者接入行为（spec formula-hub-integrity-closure 任务 14；需求 5.1 读取部分；ADR-FHIC-04；F38）。

静态（AST 扫描 ``backend/app``，带违规样本自检）：
- 「原始读」= 绕过 ``services/report_freshness`` 直接读 ``financial_report.is_stale``：ORM 属性读取（根名字绑定到
  ``FinancialReport`` —— import / 别名 / 由含 ``FinancialReport`` 的表达式赋值，如 ``_FR = FinancialReport.__table__``）、
  或非 docstring 的 SQL 字符串（含 f-string 与 ``+`` 拼接）同时出现 ``financial_report`` 与 ``is_stale``；
  ``UPDATE financial_report SET …`` 开头的写入语句与属性赋值不算读。扫描不到的写法：对查询结果行（类型未知的变量）
  读 ``.is_stale``、``getattr(…, "is_stale")`` —— 新读者一律经本模块即可避开。
- 「经新鲜度模块」= 函数里引用了从 ``app.services.report_freshness`` 导入的名字；写入接口 :data:`WRITE_API`（定义写入出口
  同事务标过期，任务 15；生成路径写入的计算版本号，任务 16）不是读、不计入。
两类都按 ``文件::限定名`` 与下方写死的清单逐项相等：新增读者必须登记（原始读还须写明不接入的理由）。高级查询报表源
（advanced-query-linkage-closure，design §8.3）已在主树入库而不在本 worktree 基底：合并后其 ``custom_query/source_registry.py``
的原始读会让本守卫红，届时改为 ``stale_clause(_FR)`` 并登记到 :data:`FRESHNESS_READERS`。

行为（SQLite，夹具与期望见 ``_freshness_world``）：F38 四个读者 + AI 上下文读者对同一组行给出同一组过期 / 计算失败 / 留空计数。
"""
from __future__ import annotations

import ast
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models.report_models import FinancialReport
from app.services.ai_chat.contracts import HostType
from app.services.ai_chat.host_context import AuthorizedHostContext
from app.services.deliverable_readiness_service import DeliverableReadinessService
from app.services.doc_ai_context_builder import ContextBuilder
from app.services.formula_health_service import _stale_stats
from app.services.report_export_checks import _check_freshness
from app.services.stale_summary_aggregate import get_full_summary
from tests.formula_hub._freshness_world import BLANK, CALC_ERROR, SHAPES, SUMMARY_STALE, YEAR, sqlite_world

BACKEND = Path(__file__).resolve().parents[2]
FRESHNESS_MODULE = "app.services.report_freshness"
#: report_freshness 的写入接口：三个定义写入出口同事务标过期（任务 15），以及生成路径成功写库时写入的计算版本号
#: ``CALC_VERSION``（任务 16 ``report_row_compute.write_row``；判过期一律经 stale_clause / is_flag_stale 等函数）。引用它们的函数不算读者
WRITE_API = frozenset({"mark_changed", "mark_statement", "slot_row_codes", "CALC_VERSION"})

#: 经 report_freshness 判过期的读者（文件::限定名 → 用途）
FRESHNESS_READERS: dict[str, str] = {
    "app/routers/reports.py::get_report": "报表视图：逐行 row_status（含生成时公式与生效公式比较）",
    "app/routers/reports.py::export_report_excel": "单表 Excel 导出：「说明」列 status_note(row_status)",
    "app/services/deliverable_readiness_service.py::DeliverableReadinessService._check_reports": "F38 交付就绪",
    "app/services/report_export_checks.py::_check_freshness": "F38 导出前检查（过期 / 计算失败 / 留空三条提示）",
    "app/services/stale_summary_aggregate.py::get_full_summary": "F38 过期汇总（签发清单 / 合伙人 / EQCR 复用）",
    "app/services/formula_health_service.py::_stale_stats": "F38 公式健康度",
    "app/services/doc_ai_context_builder.py::ContextBuilder._get_report_content": "AI 上下文报表正文（汇总口径一条提示）",
    "app/services/report_engine.py::ReportEngine.recalculate_stale_rows":
        "stale 重算选行：只选已标过期（is_marked_stale；不因 D13-A 自动重算存量行，ADR-FHIC-05 / X3）",
    "app/services/report_row_compute.py::build_row_cache":
        "报表依赖缓存：库中行只有未标过期且计算版本为当前版本才作输入（is_flag_stale，ADR-FHIC-05）",
    "app/services/formula_management/refresh_idempotency_store.py::report_basis":
        "Draft Refresh 幂等计划指纹的报表四项：本项目年度 stale_clause() 过期行数（另取生效报表定义与 CALC_VERSION）",
}

#: 仍直接读原始 is_stale 列的位置（文件::限定名 → 不接入的理由）；任务 16 后本 spec 自己的读者为空（stale 重算选行改经 is_marked_stale）
#: 🔴 2026-10-30 整合到分支 HEAD 时登记：高级查询数据源注册表是并发 spec `advanced-query-linkage-closure`（B5/B6）先落地的代码，
#:    本 spec 后落地只登记、不改其实现（design §8.2 同口径）。后果：高级查询里「已过期」只认 is_stale 列，
#:    calc_version 为空（D13-A 判过期）的行会显示为未过期 —— 接入 report_freshness 交 S3 formula-writer-ownership-and-stale
RAW_READERS: dict[str, str] = {
    "app/services/custom_query/source_registry.py::<module>":
        "高级查询报表源的 is_stale 输出列（advanced-query-linkage-closure 先落地，后落地方只登记；接入交 S3）",
    "app/services/custom_query/source_registry.py::_report_warn":
        "高级查询报表源的过期行数提示（同上；接入 stale_clause 交 S3）",
}

#: 需求 5.1 / F38 + 报表视图 / 导出：必须经 report_freshness
REQUIRED = (
    "app/services/deliverable_readiness_service.py::DeliverableReadinessService._check_reports",
    "app/services/report_export_checks.py::_check_freshness",
    "app/services/stale_summary_aggregate.py::get_full_summary",
    "app/services/formula_health_service.py::_stale_stats",
    "app/routers/reports.py::get_report",
    "app/routers/reports.py::export_report_excel",
)

_TABLE = re.compile(r"\bfinancial_report\b(?!_)", re.I)
_COLUMN = re.compile(r"\bis_stale\b", re.I)
_WRITE = re.compile(r"^\s*update\s+financial_report\s+set\s", re.I)


def _strings(node: ast.AST) -> str | None:
    """字符串字面量（含 f-string 的常量部分、``+`` 拼接的字面量链）⇒ 文本；否则 None。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _strings(node.left), _strings(node.right)
        return None if left is None or right is None else left + right
    return None


def _root(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


class _Scan(ast.NodeVisitor):
    def __init__(self, rel: str, tree: ast.AST):
        self.rel, self.stack = rel, []
        self.raw: dict[str, set[str]] = {}
        self.fresh: set[str] = set()
        self.model_names: set[str] = set()
        self.fresh_names: set[str] = set()
        self.fresh_modules: set[str] = set()
        self.docstrings = {id(n.value) for n in ast.walk(tree)
                           if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "FinancialReport":
                        self.model_names.add(alias.asname or alias.name)
                    if node.module == FRESHNESS_MODULE and alias.name not in WRITE_API:
                        self.fresh_names.add(alias.asname or alias.name)
                    if f"{node.module}.{alias.name}" == FRESHNESS_MODULE:
                        self.fresh_modules.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == FRESHNESS_MODULE and alias.asname:
                        self.fresh_modules.add(alias.asname)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and "FinancialReport" in ast.unparse(node.value):
                self.model_names.update(t.id for t in node.targets if isinstance(t, ast.Name))

    def _key(self) -> str:
        return f"{self.rel}::{'.'.join(self.stack) or '<module>'}"

    def _scoped(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scoped

    def visit_Attribute(self, node):  # noqa: N802
        if node.attr == "is_stale" and isinstance(node.ctx, ast.Load) and _root(node.value) in self.model_names:
            self.raw.setdefault(self._key(), set()).add(f"orm:{ast.unparse(node)}")
        if isinstance(node.value, ast.Name) and node.value.id in self.fresh_modules and node.attr not in WRITE_API:
            self.fresh.add(self._key())
        self.generic_visit(node)

    def visit_Name(self, node):  # noqa: N802
        if node.id in self.fresh_names and isinstance(node.ctx, ast.Load):
            self.fresh.add(self._key())

    def _text(self, node) -> bool:
        text = _strings(node)
        if text is None:
            return False
        if id(node) not in self.docstrings and _TABLE.search(text) and _COLUMN.search(text) and not _WRITE.search(text):
            self.raw.setdefault(self._key(), set()).add("sql")
        return True

    def visit_Constant(self, node):  # noqa: N802
        self._text(node)

    def visit_JoinedStr(self, node):  # noqa: N802
        self._text(node)
        for value in node.values:  # 插值表达式照常扫（常量部分已按整串判过）
            if isinstance(value, ast.FormattedValue):
                self.visit(value.value)

    def visit_BinOp(self, node):  # noqa: N802
        if not self._text(node):  # 纯字面量 + 链按整串判；否则逐项扫
            self.generic_visit(node)


def scan_source(rel: str, text: str) -> tuple[dict[str, set[str]], set[str]]:
    tree = ast.parse(text)
    scan = _Scan(rel, tree)
    scan.visit(tree)
    return scan.raw, scan.fresh


def scan_app() -> tuple[dict[str, set[str]], set[str], list[str]]:
    raw: dict[str, set[str]] = {}
    fresh: set[str] = set()
    errors: list[str] = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        if rel == "app/services/report_freshness.py":
            continue
        try:
            file_raw, file_fresh = scan_source(rel, path.read_bytes().decode("utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{rel}: {exc}")
            continue
        raw.update(file_raw)
        fresh |= file_fresh
    return raw, fresh, errors


# ── 静态：冻结清单 ─────────────────────────────────────────────────────────────────


def test_scanner_parses_every_app_module():
    """扫描不得静默跳过文件（BOM 文件按 utf-8-sig 读）。"""
    *_, errors = scan_app()
    assert errors == []


def test_raw_readers_frozen():
    raw, *_ = scan_app()
    unexpected = sorted(set(raw) - set(RAW_READERS))
    missing = sorted(set(RAW_READERS) - set(raw))
    assert not unexpected, ("新增了直接读 financial_report.is_stale 的位置：改用 report_freshness.stale_clause / "
                            f"row_status，或在 RAW_READERS 登记不接入的理由：{ {k: sorted(raw[k]) for k in unexpected} }")
    assert not missing, f"RAW_READERS 有已不存在的原始读（接入后删除该条）：{missing}"


def test_freshness_readers_frozen():
    _, fresh, _ = scan_app()
    assert sorted(fresh) == sorted(FRESHNESS_READERS), (
        f"经 report_freshness 的读者与清单不符：新增 {sorted(fresh - set(FRESHNESS_READERS))}，"
        f"缺少 {sorted(set(FRESHNESS_READERS) - fresh)}")


def test_required_readers_use_freshness():
    raw, fresh, _ = scan_app()
    assert set(REQUIRED) <= fresh and not set(REQUIRED) & set(raw), (
        f"F38 + 报表视图 / 导出须经 report_freshness 且不得再读原始列：缺 {sorted(set(REQUIRED) - fresh)}，"
        f"仍读原始列 {sorted(set(REQUIRED) & set(raw))}")
    assert set(REQUIRED) <= set(FRESHNESS_READERS)


_VIOLATIONS = {
    "orm": "from app.models.report_models import FinancialReport\nasync def f():\n    return FinancialReport.is_stale\n",
    "alias": "from app.models.report_models import FinancialReport as FR\ndef f():\n    return FR.is_stale == 1\n",
    "core_table": "from app.models.report_models import FinancialReport\n_FR = FinancialReport.__table__\n"
                  "def f():\n    return _FR.c.is_stale\n",
    "instance": "from app.models.report_models import FinancialReport\ndef f():\n    r = FinancialReport()\n"
                "    return r.is_stale\n",
    "sql": "import sqlalchemy as sa\ndef f():\n    return sa.text('SELECT count(*) FROM financial_report WHERE is_stale')\n",
    "fstring": "def f(t):\n    return f\"SELECT 1 FROM financial_report WHERE {t} AND is_stale = true\"\n",
    "concat": "def f():\n    return 'SELECT 1 FROM financial_report ' + 'WHERE is_stale = true'\n",
}
_CLEAN = {
    "docstring": '"""financial_report.is_stale 说明"""\ndef f():\n    """读 financial_report 的 is_stale"""\n',
    "writer": "def f():\n    return 'UPDATE financial_report SET is_stale = true WHERE project_id = :p'\n",
    "store": "from app.models.report_models import FinancialReport\ndef f():\n    r = FinancialReport()\n"
             "    r.is_stale = False\n",
    "other_table": "def f():\n    return 'SELECT is_stale FROM financial_report_items', 'SELECT is_stale FROM disclosure_notes'\n",
    "other_model": "from app.models.report_models import DisclosureNote\ndef f():\n    return DisclosureNote.is_stale\n",
    "mark_writer": "from app.services.report_freshness import mark_changed, slot_row_codes\nasync def f(db, s):\n"
                   "    await mark_changed(db, {1: slot_row_codes(s)})\n",
    "mark_writer_module": "from app.services import report_freshness as rf\nasync def f(db):\n"
                          "    await rf.mark_changed(db, {})\n",
}


@pytest.mark.parametrize("name", sorted(_VIOLATIONS))
def test_scanner_flags_violation_samples(name):
    raw, fresh = scan_source("x.py", _VIOLATIONS[name])
    assert set(raw) == {"x.py::f"} and not fresh, raw


@pytest.mark.parametrize("name", sorted(_CLEAN))
def test_scanner_ignores_clean_samples(name):
    raw, fresh = scan_source("x.py", _CLEAN[name])
    assert raw == {} and not fresh, raw


@pytest.mark.parametrize("source", [
    "from app.services.report_freshness import stale_clause\ndef f():\n    return stale_clause()\n",
    "from app.services import report_freshness as rf\ndef f():\n    return rf.stale_clause()\n",
    "import app.services.report_freshness as rf\ndef f():\n    return rf.count_summary\n",
])
def test_scanner_detects_freshness_use(source):
    raw, fresh = scan_source("x.py", source)
    assert raw == {} and fresh == {"x.py::f"}


# ── 行为：各读者对同一组行同口径 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliverable_readiness_counts():
    async with sqlite_world(tag="fh_fresh_ready") as world:
        blockers: list = []
        status = await DeliverableReadinessService()._check_reports(world.session, world.project_id, YEAR, blockers)
        assert (status.count, status.stale_count) == (len(SHAPES), len(SUMMARY_STALE))
        [blocker] = blockers
        assert blocker.code == "stale_source" and f"有 {len(SUMMARY_STALE)} 条报表行已过期" in blocker.message
        assert (blocker.evidence["calc_error_count"], blocker.evidence["blank_count"]) == (len(CALC_ERROR), len(BLANK))


@pytest.mark.asyncio
async def test_export_checks_messages():
    async with sqlite_world(tag="fh_fresh_export") as world:
        messages = await _check_freshness(world.session, world.project_id, YEAR)
        assert messages[0].startswith(f"报表有 {len(SUMMARY_STALE)} 行已过期"), messages
        assert messages[1] == f"报表有 {len(CALC_ERROR)} 行计算失败（保留旧值）：FHT14-004 新鲜度4：除数为 0"
        assert messages[2] == f"报表有 {len(BLANK)} 行按口径留空：FHT14-005 新鲜度5：取数超出合并口径"
        assert len(messages) == 3, messages


@pytest.mark.asyncio
async def test_stale_summary_reports_section():
    async with sqlite_world(tag="fh_fresh_summary") as world:
        reports = (await get_full_summary(world.session, world.project_id, YEAR))["reports"]
        assert (reports["total"], reports["stale"], reports["calc_error"], reports["blank"]) == (
            len(SHAPES), len(SUMMARY_STALE), len(CALC_ERROR), len(BLANK))
        assert [i["row_code"] for i in reports["items"]] == SUMMARY_STALE
        failed = next(i for i in reports["items"] if i["row_code"] == "FHT14-004")
        assert (failed["calc_error"], failed["blank_reason"]) == ("除数为 0", None)


@pytest.mark.asyncio
async def test_formula_health_stale_stats():
    async with sqlite_world(tag="fh_fresh_health") as world:
        stats = await _stale_stats(world.session, world.project_id, YEAR)
        assert stats == {"report_total": len(SHAPES), "report_stale": len(SUMMARY_STALE),
                         "report_stale_rate": round(len(SUMMARY_STALE) / len(SHAPES) * 100, 1),
                         "report_calc_error": len(CALC_ERROR), "report_blank": len(BLANK)}


_AI_HINT = "[提示：本报表存在已过期的行次"


@pytest.mark.asyncio
async def test_ai_report_context_flags_legacy_rows():
    """本年度只剩存量行（计算版本为空、未标过期）时 AI 上下文也提示过期；只剩新鲜行时不提示。"""
    async with sqlite_world(tag="fh_fresh_ai") as world:
        host = AuthorizedHostContext(principal_id=uuid.uuid4(), project_id=world.project_id, year=YEAR,
                                     resource_type=HostType.report, resource_id="balance_sheet",
                                     display_label="资产负债表", permission_binding="readonly")
        builder = ContextBuilder(world.session)

        async def _keep_only(code: str) -> str:
            await world.session.execute(sa.update(FinancialReport).where(
                FinancialReport.project_id == world.project_id, FinancialReport.year == YEAR
            ).values(is_deleted=FinancialReport.row_code != code))
            return await builder._get_report_content(host)

        assert _AI_HINT in await _keep_only("FHT14-001")
        assert _AI_HINT not in await _keep_only("FHT14-002")
