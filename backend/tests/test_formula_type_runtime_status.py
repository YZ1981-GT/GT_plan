"""Wave 4 守卫：三类型运行态定性 + logic_check 落库 + 空结果可见化。

spec: formula-management-runtime-closure Task 12
  (Requirements 6.1–6.6, 8.4, 8.5, 8.6 / Property 13, 14, 15, 16, 18)

判据设计四条：

1. **执行链可达性用替身数据验证，不因真实库为空而跳过**（R6.5）——
   `wp_formula` 全库 0 行，若断言依赖真实数据就会静默 skip = 假绿。
2. **「零调用方」打红，但要区分「空转」与「死代码」**（Property 14）——
   `auto_calc`/`reasonability` 的批量入口**有**调用方（`execute_batch`），
   只是上游无数据；真正该打红的是「函数在但一个非测试调用方都没有」。
3. **源码级断言必先 `stripComments()`**（R8.6）—— 本 spec 的注释里会写出
   被禁的旧写法（`return CrossCheckResult(...)` 不落库等），不剥注释会数成真实代码。
4. **`db.add(<ORM 实例>)` 才算落库**（requirements 缺陷 5）—— `CrossCheckResult`
   是同名双实体（dataclass 聚合结果 vs ORM 模型），按符号名 grep 会混为一谈。
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.formula_runtime.coordinator import NO_FORMULAS_KIND
from app.services.formula_runtime_table_status import (
    ALLOWED_DISPOSITIONS,
    FORMULA_RUNTIME_TABLE_STATUS,
    registered_tables,
    status_of as table_status_of,
)
from app.services.formula_type_runtime_status import (
    FORMULA_TYPE_RUNTIME_STATUS,
    FORMULA_TYPES,
    registered_types,
    status_of as type_status_of,
)

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"

ENGINE_PY = APP / "services/formula_management/engine.py"
LOGIC_CHECK_PY = APP / "services/formula_management/logic_check.py"
COORDINATOR_PY = APP / "services/formula_runtime/coordinator.py"
ORCHESTRATOR_PY = APP / "services/formula_management/draft_refresh_orchestrator.py"
WP_FORMULA_PY = APP / "routers/wp_formula.py"


# ---------------------------------------------------------------------------
# 工具：剥注释（带字符串状态机）
# ---------------------------------------------------------------------------
def strip_py_comments(src: str) -> str:
    """剥掉 Python 的 ``#`` 注释与三引号 docstring（保留普通字符串）。

    做法：先按行剥 ``#``（跳过引号内），再用正则剥三引号块。
    """
    out_lines: list[str] = []
    for line in src.splitlines():
        buf = ""
        quote: str | None = None
        i = 0
        while i < len(line):
            c = line[i]
            if quote:
                buf += c
                if c == "\\":
                    if i + 1 < len(line):
                        buf += line[i + 1]
                        i += 2
                        continue
                elif c == quote:
                    quote = None
                i += 1
                continue
            if c in ("'", '"'):
                quote = c
                buf += c
                i += 1
                continue
            if c == "#":
                break
            buf += c
            i += 1
        out_lines.append(buf)
    joined = "\n".join(out_lines)
    joined = re.sub(r'"""[\s\S]*?"""', '""', joined)
    joined = re.sub(r"'''[\s\S]*?'''", "''", joined)
    return joined


def func_body(src: str, name: str) -> str:
    """截取 ``def name`` 的**签名 + 函数体**。

    两个必须一起处理的坑：

    1. 🔴 ``re.M`` 下 ``\\s`` 含换行 → ``^(\\s*)def`` 会从前面的空行开始匹配，
       ``indent`` 被算成一串换行的长度、函数体截成空串（memory 已记）。
       故缩进用 ``[ \\t]*``。
    2. 🔴 **多行签名的闭合行 ``) -> X:`` 与 ``def`` 同缩进** ⇒ 纯按缩进截断会
       在参数列表结束处就停下，"函数体"只有签名（本守卫的
       ``test_func_body_extractor_works`` 自检正是抓这个）。
       故先用**圆括号配对**跳过整个参数列表再开始按缩进截断。
    """
    m = re.search(rf"^([ \t]*)(?:async )?def {re.escape(name)}\b", src, re.M)
    if not m:
        return ""
    indent = len(m.group(1))
    start = m.start()

    # ① 圆括号配对跳过参数列表（字符串内的括号在签名里不出现，无需状态机）
    i = src.index("(", start)
    depth = 0
    while i < len(src):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    # ② 签名结束的冒号所在行
    colon = src.find(":", i)
    line_end = src.find("\n", colon)
    if line_end < 0:
        return src[start:]

    signature = src[start:line_end]
    body_lines: list[str] = []
    for line in src[line_end + 1 :].splitlines():
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body_lines.append(line)
    return signature + "\n" + "\n".join(body_lines)


def production_py_files() -> list[Path]:
    """`backend/app/**` 全部 py（生产代码，排除 __pycache__）。"""
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def callers_of(symbol: str) -> list[str]:
    """`backend/app/**` 里调用 ``symbol(`` 的文件（剥注释后统计，排除定义处自身行）。"""
    hits: list[str] = []
    pattern = re.compile(rf"(?<![\w.]){re.escape(symbol)}\s*\(")
    define = re.compile(rf"^[ \t]*(?:async )?def {re.escape(symbol)}\b", re.M)
    for p in production_py_files():
        src = strip_py_comments(p.read_text(encoding="utf-8", errors="ignore"))
        # 去掉定义行，避免把 `def foo(` 数成调用
        src_wo_def = define.sub("", src)
        if pattern.search(src_wo_def):
            hits.append(str(p.relative_to(BACKEND)))
    return sorted(hits)


# ---------------------------------------------------------------------------
# 提取器自检（判据失效必打红）
# ---------------------------------------------------------------------------
class TestExtractorSelfCheck:
    def test_source_files_exist_and_nonempty(self) -> None:
        for p in (
            ENGINE_PY,
            LOGIC_CHECK_PY,
            COORDINATOR_PY,
            ORCHESTRATOR_PY,
            WP_FORMULA_PY,
        ):
            assert p.exists(), f"路径错会让整份守卫零断言执行: {p}"
            assert len(p.read_text(encoding="utf-8")) > 1000

    def test_strip_comments_actually_strips(self) -> None:
        fixture = (
            '"""旧实现只 return CrossCheckResult(...) 不落库。"""\n'
            "# 反例：account_data.get(col, account_data.get('期末余额'))\n"
            "x = 1  # 尾注释 FORBIDDEN_TOKEN\n"
            "s = 'http://a#b'\n"
        )
        stripped = strip_py_comments(fixture)
        assert "FORBIDDEN_TOKEN" not in stripped
        assert "旧实现只" not in stripped
        # 字符串里的 # 不能被当注释切掉
        assert "http://a#b" in stripped

    def test_func_body_extractor_works(self) -> None:
        body = func_body(
            LOGIC_CHECK_PY.read_text(encoding="utf-8"),
            "persist_cross_check_results",
        )
        assert body, "函数体提取失败会让下方断言全部空转"
        # 🔴 这三条覆盖「多行签名闭合行与 def 同缩进」这个坑：
        # 纯按缩进截断时 body 只有签名，下面三个 token 全部落空。
        assert "CrossCheckResultRow" in body
        assert "db.add(" in body
        assert "return written" in body

    def test_func_body_stops_at_next_sibling_def(self) -> None:
        """反向自检：不得把下一个同级函数吞进来（否则断言会误命中邻居的代码）。"""
        body = func_body(
            LOGIC_CHECK_PY.read_text(encoding="utf-8"),
            "persist_cross_check_results",
        )
        assert "def execute_report_cross_checks" not in body

    def test_func_body_handles_multiline_signature_fixture(self) -> None:
        """替身自检：多行签名 + 同缩进闭合行，仍要拿到真实函数体。"""
        fixture = (
            "def foo(\n"
            "    a: int,\n"
            "    b: int,\n"
            ") -> int:\n"
            '    """doc"""\n'
            "    MARKER = a + b\n"
            "    return MARKER\n"
            "\n"
            "def bar() -> None:\n"
            "    NEIGHBOR = 1\n"
        )
        body = func_body(fixture, "foo")
        assert "MARKER" in body
        assert "NEIGHBOR" not in body

    def test_callers_of_finds_known_symbol(self) -> None:
        # 反向自检：一个确定有调用方的符号必须命中；不存在的符号必须为空
        assert callers_of("execute_batch"), "调用方扫描失效"
        assert callers_of("__definitely_not_a_symbol__") == []


# ---------------------------------------------------------------------------
# Property 18: 三张 0 行表定性完整
# ---------------------------------------------------------------------------
class TestRuntimeTableStatus:
    def test_three_tables_registered_exactly(self) -> None:
        assert set(registered_tables()) == {
            "cross_check_results",
            "draft_marker",
            "formula_runtime_outbox",
        }
        assert len(FORMULA_RUNTIME_TABLE_STATUS) == 3

    def test_disposition_domain_excludes_deprecated(self) -> None:
        # 三表都有生产读写方 ⇒ 取值域刻意不含 '弃用'（删表会打断已实现链路）
        assert ALLOWED_DISPOSITIONS == frozenset({"接线", "保留待接线"})
        for e in FORMULA_RUNTIME_TABLE_STATUS:
            assert e.disposition in ALLOWED_DISPOSITIONS, e.table
            assert e.disposition != "弃用"

    def test_each_entry_has_basis_readers_writers_and_dated_measurement(self) -> None:
        for e in FORMULA_RUNTIME_TABLE_STATUS:
            assert len(e.basis) >= 20, f"{e.table} 判据过短（占位）"
            assert e.readers, f"{e.table} 未登记读方"
            assert e.writers, f"{e.table} 未登记写方"
            assert "2026-" in e.measured, f"{e.table} 实测状态缺日期"

    def test_cross_check_results_marked_wired(self) -> None:
        entry = table_status_of("cross_check_results")
        assert entry is not None
        assert entry.disposition == "接线"
        # 写方必须包含本 spec Task 10 新增的落库函数
        assert any("persist_cross_check_results" in w for w in entry.writers)

    def test_status_of_unknown_returns_none(self) -> None:
        assert table_status_of("no_such_table") is None


# ---------------------------------------------------------------------------
# Property 14: 三类型执行入口各有生产调用方
# ---------------------------------------------------------------------------
class TestFormulaTypeRuntimeStatus:
    def test_three_types_registered_exactly(self) -> None:
        assert set(registered_types()) == set(FORMULA_TYPES)
        assert len(FORMULA_TYPE_RUNTIME_STATUS) == 3

    def test_each_type_has_dated_measurement_and_sink(self) -> None:
        for e in FORMULA_TYPE_RUNTIME_STATUS:
            assert "2026-" in e.measured, f"{e.formula_type} 实测状态缺日期"
            assert len(e.output_sink) >= 8, f"{e.formula_type} 未登记产出去向"

    def test_registered_callers_are_nonempty(self) -> None:
        """零调用方即打红（Property 14）——登记表本身不许空。"""
        for e in FORMULA_TYPE_RUNTIME_STATUS:
            assert e.production_callers, f"{e.formula_type} 零调用方"

    @pytest.mark.parametrize("ftype", FORMULA_TYPES)
    def test_exec_entries_really_have_production_callers(self, ftype: str) -> None:
        """交叉锁死：登记的执行入口在 `backend/app/**` 真有非测试调用方。"""
        entry = type_status_of(ftype)
        assert entry is not None
        for path_and_symbol in (entry.exec_entry, entry.batch_entry):
            symbol = path_and_symbol.split("::")[-1]
            assert callers_of(symbol), f"{symbol} 在生产代码里零调用方（真死代码）"

    def test_engine_docstrings_record_runtime_state(self) -> None:
        """三类型 docstring 必须写明运行态（含实测日期），防「空转」被当已完成。"""
        src = ENGINE_PY.read_text(encoding="utf-8")
        for name in (
            "_exec_auto_calc",
            "_exec_logic_check",
            "_exec_reasonability",
            "_batch_exec_auto_calc",
            "_batch_exec_logic_check",
            "_batch_exec_reasonability",
        ):
            body = func_body(src, name)
            assert body, f"{name} 函数体提取失败"
            assert "2026-08-0" in body, f"{name} docstring 未写实测日期"
            assert "wp_formula" in body, f"{name} docstring 未说明依赖 wp_formula"


# ---------------------------------------------------------------------------
# Property 15: cross_check_results 有 INSERT 生产代码
# ---------------------------------------------------------------------------
class TestCrossCheckPersistence:
    def test_logic_check_adds_orm_row(self) -> None:
        """判据 = `db.add(<ORM 实例>)`，不是「出现了 CrossCheckResult 这个符号」。

        🔴 `CrossCheckResult` 是同名双实体（本模块的 dataclass 聚合结果 vs
        `wp_optimization_models` 的 ORM 模型），按符号名 grep 会把两者混为一谈。
        故断言 import 已改名 + `db.add(CrossCheckResultRow(` 形态。
        """
        src = strip_py_comments(LOGIC_CHECK_PY.read_text(encoding="utf-8"))
        assert "CrossCheckResult as CrossCheckResultRow" in src, (
            "ORM 模型必须改名导入，否则与 dataclass 同名混淆"
        )
        body = func_body(src, "persist_cross_check_results")
        assert re.search(r"db\.add\(\s*\n?\s*CrossCheckResultRow\(", body), (
            "落库判据 = db.add(<ORM 实例>)"
        )

    def test_execute_report_cross_checks_calls_persist(self) -> None:
        src = strip_py_comments(LOGIC_CHECK_PY.read_text(encoding="utf-8"))
        body = func_body(src, "execute_report_cross_checks")
        assert body
        assert "persist_cross_check_results" in body, "落库未接进唯一外部入口"
        # persist 必须由条件门控（persist=False 供纯计算场景）
        assert re.search(r"if\s+persist\s*:", body), "缺 persist 门控"

    def test_persist_is_fail_open(self) -> None:
        """落库失败不得阻断只读勾稽结果返回（fail-open + WARNING）。"""
        src = LOGIC_CHECK_PY.read_text(encoding="utf-8")
        body = func_body(src, "persist_cross_check_results")
        assert "except Exception" in body
        assert "logger.warning" in body
        assert "return 0" in body

    def test_upsert_deletes_same_key_first(self) -> None:
        """表无唯一约束 ⇒ 只能「先删同键再插」；断言该形态存在（幂等前提）。"""
        src = strip_py_comments(LOGIC_CHECK_PY.read_text(encoding="utf-8"))
        body = func_body(src, "persist_cross_check_results")
        assert "sa.delete(CrossCheckResultRow)" in body
        assert "rule_id.in_(" in body

    def test_status_domain_constants_exist(self) -> None:
        from app.services.formula_management.logic_check import (
            CROSS_CHECK_STATUS_FAILED,
            CROSS_CHECK_STATUS_PASSED,
        )

        assert CROSS_CHECK_STATUS_PASSED == "passed"
        assert CROSS_CHECK_STATUS_FAILED == "failed"
        # 列宽 String(20)
        assert len(CROSS_CHECK_STATUS_PASSED) <= 20
        assert len(CROSS_CHECK_STATUS_FAILED) <= 20

    def test_rule_id_fits_column_width(self) -> None:
        """`rule_id` 列宽 String(30)：7 条种子的 formula_id 必须都放得下。"""
        from app.services.formula_management.logic_check import (
            build_cross_check_formulas,
        )

        formulas = build_cross_check_formulas()
        assert len(formulas) == 7
        for f in formulas:
            assert len(f.id) <= 30, f"rule_id 超列宽: {f.id}"


# ---------------------------------------------------------------------------
# Property 15（续）：落库真实产出 —— 替身验证（不依赖真实库）
# ---------------------------------------------------------------------------
class _FakeSession:
    """最小替身：记录 add/delete/flush，验证「执行链可达」而非真实写库（R6.5）。"""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.executed: list[object] = []
        self.flushed = 0

    async def execute(self, stmt: object) -> object:  # noqa: D102
        self.executed.append(stmt)
        return None

    def add(self, obj: object) -> None:  # noqa: D102
        self.added.append(obj)

    async def flush(self) -> None:  # noqa: D102
        self.flushed += 1


@pytest.mark.asyncio
async def test_persist_writes_one_row_per_outcome_with_substitute_data() -> None:
    """用替身数据验证落库链可达（R6.5：不因真实库 0 行而跳过断言）。"""
    from app.models.wp_optimization_models import CrossCheckResult as Row
    from app.services.formula_management.engine import IssueItem
    from app.services.formula_management.logic_check import (
        CrossCheckOutcome,
        CrossCheckResult,
        persist_cross_check_results,
    )

    result = CrossCheckResult(
        issues=[
            IssueItem(
                formula_id="report-cross-check-1",
                addr_id=None,
                description="资产 ≠ 负债+权益",
                left_value=Decimal("100.00"),
                right_value=Decimal("90.00"),
            )
        ],
        outcomes=[
            CrossCheckOutcome(
                formula_id="report-cross-check-1",
                description="资产 ≠ 负债+权益",
                expression="ROW('BS-A') == ROW('BS-B')",
                passed=False,
            ),
            CrossCheckOutcome(
                formula_id="report-cross-check-7",
                description="货币资金 ≥ 0",
                expression="ROW('BS-001') >= 0",
                passed=True,
            ),
        ],
    )
    db = _FakeSession()
    written = await persist_cross_check_results(
        db,  # type: ignore[arg-type]
        project_id="11111111-1111-1111-1111-111111111111",
        year=2025,
        result=result,
    )
    assert written == 2
    assert db.flushed == 1
    assert len(db.executed) == 1, "应先 delete 同键旧行"
    assert all(isinstance(r, Row) for r in db.added)

    by_rule = {r.rule_id: r for r in db.added}  # type: ignore[attr-defined]
    failed = by_rule["report-cross-check-1"]
    assert failed.status == "failed"
    assert failed.left_amount == Decimal("100.00")
    assert failed.right_amount == Decimal("90.00")
    assert failed.difference == Decimal("10.00")

    passed = by_rule["report-cross-check-7"]
    assert passed.status == "passed"
    # passed 无 issue ⇒ 三个金额都不得凭空造值
    assert passed.left_amount is None
    assert passed.right_amount is None
    assert passed.difference is None


@pytest.mark.asyncio
async def test_persist_returns_zero_on_empty_outcomes() -> None:
    from app.services.formula_management.logic_check import (
        CrossCheckResult,
        persist_cross_check_results,
    )

    db = _FakeSession()
    written = await persist_cross_check_results(
        db,  # type: ignore[arg-type]
        project_id="11111111-1111-1111-1111-111111111111",
        year=2025,
        result=CrossCheckResult(issues=[], outcomes=[]),
    )
    assert written == 0
    assert db.added == []


# ---------------------------------------------------------------------------
# Property 13: _load_formulas 空结果可见
# ---------------------------------------------------------------------------
class TestNoFormulasVisibility:
    def test_kind_constant_is_single_source(self) -> None:
        assert NO_FORMULAS_KIND == "no_formulas"

    def test_generate_mutation_plan_appends_scope_failure_on_empty(self) -> None:
        src = strip_py_comments(COORDINATOR_PY.read_text(encoding="utf-8"))
        body = func_body(src, "generate_mutation_plan")
        assert body
        # 判据 = 条件形态 + 在该分支内追加 scope_failures（非「文件里出现过该字样」）
        assert re.search(r"if\s+not\s+formulas\s*:", body), "空公式分支消失"
        head = body[: body.find("return plan") + len("return plan")]
        assert "scope_failures.append" in head, "空公式分支未产出 scope_failures"
        assert "NO_FORMULAS_KIND" in head, "kind 未走单一真源常量"

    def test_load_formulas_has_no_formula_source_filter(self) -> None:
        """Property 10 复核：用户公式（formula_source='custom'）必须进入视野。"""
        src = strip_py_comments(COORDINATOR_PY.read_text(encoding="utf-8"))
        body = func_body(src, "_load_formulas")
        assert body
        assert "formula_source" not in body, (
            "_load_formulas 加 formula_source 过滤会让用户公式重新不可见"
        )

    def test_orchestrator_surfaces_no_formulas_to_warnings(self) -> None:
        """告警必须透到响应体 warnings，不能只 logger.warning。"""
        src = strip_py_comments(ORCHESTRATOR_PY.read_text(encoding="utf-8"))
        body = func_body(src, "_dispatch_via_coordinator")
        assert body
        assert "NO_FORMULAS_KIND" in body
        assert "_coordinator_warnings" in body
        gen = func_body(src, "generate")
        assert "_coordinator_warnings" in gen, "generate 未把告警并入 result"
        assert re.search(r'getattr\(result,\s*["\']warnings["\']', gen), (
            "并入 warnings 的形态缺失"
        )


# ---------------------------------------------------------------------------
# Property 16: lifecycle_state 进响应
# ---------------------------------------------------------------------------
class TestLifecycleStateExposed:
    def test_formula_to_dict_contains_lifecycle_and_version(self) -> None:
        src = WP_FORMULA_PY.read_text(encoding="utf-8")
        body = func_body(src, "_formula_to_dict")
        assert body
        for key in ("lifecycle_state", "definition_version", "formula_source"):
            assert f'"{key}"' in body, f"_formula_to_dict 未下发 {key}"

    def test_frontend_has_lifecycle_label_map(self) -> None:
        """交叉锁死：前端标签真源的键集 SHALL ⊇ 后端实际写入的取值。

        🔴 **本断言曾是「假红发生器」（2026-08-07 修）**：首版硬编码期望
        `draft / active / archived / 草稿 / 生效 / 已归档`，那是立项时按
        通用生命周期语义**推测**的取值域；同 spec 的浏览器实测随后证明
        后端这三个值**一个都不写**，真实取值只有 `saved`（迁移 V104 列默认值
        + `wp_formula_service.save()` 两条分支显式赋值）与 `succeeded`。
        真源与前端守卫都已按实证改对，唯独这条后端断言没跟上 ⇒ 恒红且零信号。

        ⇒ 判据改为**从后端源码抽实际写入值**做交叉锁死（与前端
        `formulaStatusPanelDisplay.spec.ts` 同口径），不再写死推测清单：
        取值域将来变了，两侧一起变红，而不是需要有人记得改测试。
        """
        inv = (
            BACKEND.parent
            / "audit-platform/frontend/src/components/workpaper/composables"
            / "formulaEngineInventory.ts"
        )
        assert inv.exists()
        ts = inv.read_text(encoding="utf-8")
        # 🔴 判据必须带**标识符边界**：裸 `in` 会被 `FORMULA_LIFECYCLE_LABEL_REMOVED`
        # 这类改名骗过（变异检验 M9 实测逃逸），与 memory 记的
        # 「`toContain('<Foo')` 被 `<FooREMOVED` 骗过」同族。
        assert re.search(r"export const FORMULA_LIFECYCLE_LABEL(?![\w])", ts), (
            "生命周期标签真源必须是具名导出（改名/降级为局部常量即打红）"
        )
        assert re.search(r"export function formulaLifecycleLabel(?![\w])", ts), (
            "标签解析函数必须具名导出"
        )

        # ① 后端实际写入的取值（`lifecycle_state = "xxx"` 赋值字面量）
        service_py = BACKEND / "app" / "services" / "wp_formula_service.py"
        assert service_py.exists(), service_py
        written = set(
            re.findall(
                r"""lifecycle_state\s*=\s*["']([\w-]+)["']""",
                service_py.read_text(encoding="utf-8"),
            )
        )
        # 抽取器自检：后端确实写了该字段（正则失效时打红而非静默通过）
        assert written, "未从 wp_formula_service.py 抽到任何 lifecycle_state 赋值"

        # ② 迁移的列默认值（未经 save 的行走这个值）
        migration = BACKEND / "migrations" / "V104__formula_runtime_outbox.sql"
        if migration.exists():
            m = re.search(
                r"lifecycle_state\s+VARCHAR\(\d+\)\s+DEFAULT\s+'([\w-]+)'",
                migration.read_text(encoding="utf-8"),
                re.I,
            )
            if m:
                written.add(m.group(1))

        # ③ 前端标签真源必须覆盖上述全部取值，否则面板走 `?? state` 兜底
        #    显示裸英文 —— 正是 R2.2 要消除的形态（只是换了个字段）
        labeled = set(
            re.findall(r"^\s*([\w-]+)\s*:\s*'[^']+'", ts, re.M)
        ) | set(re.findall(r"^\s*'([\w-]+)'\s*:\s*'[^']+'", ts, re.M))
        missing = sorted(written - labeled)
        assert not missing, (
            f"后端会写入 {sorted(written)}，但前端标签真源缺 {missing}"
            "（缺失值会经 `?? state` 兜底显示裸英文）"
        )

        # ④ 至少要有中文标签（防把 label 写成英文占位）
        assert re.search(r"[\u4e00-\u9fff]", ts), "标签真源无中文，UI 会显示英文"

    def test_panel_consumes_lifecycle_label(self) -> None:
        """交叉锁死：真源有标签 ≠ 面板在用它（避免又一个 dead output）。

        🔴 判据必须落在 **`<template>` 段内的调用形态**：
        `formulaLifecycleLabel` 在 import 行也出现 ⇒ 只断言「文件里有该标识符」
        时，把 `{{ it.lifecycle_state }}`（裸英文值）也放行
        —— 变异检验 M12 实测逃逸，本轮第三次同族缺陷。
        """
        panel = (
            BACKEND.parent
            / "audit-platform/frontend/src/components/workpaper"
            / "FormulaStatusPanel.vue"
        )
        vue = panel.read_text(encoding="utf-8")
        i = vue.index("<template>")
        j = vue.rindex("</template>")
        tmpl = re.sub(r"<!--[\s\S]*?-->", " ", vue[i:j])
        assert re.search(
            r"formulaLifecycleLabel\(\s*it\.lifecycle_state\s*\)", tmpl
        ), "面板未在模板里经中文标签函数渲染 lifecycle_state"
        assert not re.search(r"\{\{\s*it\.lifecycle_state\s*\}\}", tmpl), (
            "不得渲染裸英文生命周期值"
        )
        # 🔴 还要钉住**门控条件形态** —— 上一条只保证「插值走了标签函数」，
        # 把外层 `v-if` 改成 `v-if="false"` 时整个 tag 不渲染而断言仍通过
        # （变异检验 M13 实测逃逸，本轮第四次同族缺陷）。
        assert re.search(
            r'v-if="isAbnormalLifecycle\(\s*it\.lifecycle_state\s*\)"', tmpl
        ), "生命周期 tag 的 v-if 必须绑在 isAbnormalLifecycle 上（禁恒假门控）"
