"""判据上下文的报表行金额维度接线守卫（additive 第八键 + 既有七键零回归）。

Feature: procedure-trim-report-line-account-resolution — Task 7
Requirements: 4.5, 5.5
Validates: Property 13（部分：单项失败不阻断其余维度）,
           Property 15（部分：上下文既有七键逐字节不变）

═══ 这条守卫在防什么 ═══

`procedure-trimming-and-delegation-intelligence` 已收口，上下文的七个键有三个现存
消费方（档 4 数据存在性 / 复核视图金额未知统计 / `resolveAccountName`）。本 spec 只
**加**一个维度，前七键必须逐字不动 —— 改它们的结构会三处同时波及，而三处的守卫各自
只看自己那一侧。

另一条：目标 wp_code 清单必须与底稿录入探测**同源**（`_collect_probe_wp_codes`）。
两套目标集会让「某程序有录入探测结果但没有金额」这种半开状态出现，而两侧各自的守卫
都查不出（各自只看自己那套）。

🔴 禁在模块顶层 import 生产模块（顶层失败 = collection error = 零断言执行）。
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import io
import tokenize
from pathlib import Path

import pytest
import sqlalchemy as sa

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
_CTX_PATH = _BACKEND / "app" / "services" / "trim_decision_context.py"

#: 改造前的七键（2026-08-15 冻结）—— 顺序即返回 dict 的字面顺序
FROZEN_SEVEN_KEYS: tuple[str, ...] = (
    "accounts",
    "materiality",
    "risk",
    "risk_dimension_available",
    "completeness_override",
    "workpaper_entry",
    "degradations",
)

#: 改造前的五个维度装配函数 —— 本 spec 一律不改
FROZEN_LOADERS: tuple[str, ...] = (
    "_load_accounts",
    "_load_materiality",
    "_load_risk",
    "_load_completeness_override",
    "_load_workpaper_entry",
)


def _ctx_mod():
    try:
        from app.services import trim_decision_context as mod
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import app.services.trim_decision_context: {e!r}")
    return mod


# ═══════════════════════════════════════════════════════════════════════════
# 剥注释 helper + 反向自检
# ═══════════════════════════════════════════════════════════════════════════
def _strip_py_comments(src: str) -> str:
    spans: list[tuple[int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((tok.start[0], tok.start[1]))
    except tokenize.TokenError:  # pragma: no cover
        return src
    lines = src.splitlines()
    for row, col in spans:
        if 1 <= row <= len(lines):
            lines[row - 1] = lines[row - 1][:col]
    return "\n".join(lines)


def _code_only(src: str) -> str:
    """剥 ``#`` 注释与全部 docstring，保留普通字符串字面量（SQL 在三引号里）。"""
    no_comment = _strip_py_comments(src)
    try:
        tree = ast.parse(no_comment)
    except SyntaxError:  # pragma: no cover
        return no_comment
    lines = no_comment.splitlines()
    blank: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                blank.add(ln)
    return "\n".join("" if (i + 1) in blank else ln for i, ln in enumerate(lines))


def test_code_only_self_check():
    """🔴 剥注释 helper 双向自检。"""
    sample = '''
"""docstring 提到 procedure_instances 与第二套目标集作为反例。"""
SQL = """
SELECT DISTINCT wp_code FROM procedure_instances
"""
'''
    code = _code_only(sample)
    assert "第二套目标集" not in code, "docstring 未剥 —— 反例说明会被数成真实实现"
    assert "SELECT DISTINCT wp_code" in code, "普通字符串字面量被误剥 —— SQL 判据全失效"


# ═══════════════════════════════════════════════════════════════════════════
# 既有七键零回归（R5.5 / Property 15）
# ═══════════════════════════════════════════════════════════════════════════
def _return_dict_keys(src: str) -> list[str]:
    """抽 ``build_trim_decision_context`` 返回 dict 的键（有序）。

    🔴 用 AST 而非正则：正则会把 docstring 里的示例 dict 也数进来。
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if node.name != "build_trim_decision_context":
            continue
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict):
                return [
                    k.value
                    for k in stmt.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                ]
    return []


def test_result_keys_are_seven_plus_one():
    """``_RESULT_KEYS`` = 既有七键 + 报表行一键，且七键顺序不变。"""
    mod = _ctx_mod()
    keys = tuple(mod._RESULT_KEYS)
    assert "report_line_amounts" in keys, "_RESULT_KEYS 未登记 report_line_amounts"
    without_new = tuple(k for k in keys if k != "report_line_amounts")
    assert without_new == FROZEN_SEVEN_KEYS, (
        f"既有七键被改动（顺序或内容）：{without_new} vs {FROZEN_SEVEN_KEYS}"
    )
    assert len(keys) == 8, f"_RESULT_KEYS 应为八键，实得 {len(keys)}：{keys}"


def test_return_dict_keys_match_result_keys():
    """返回 dict 的键与 ``_RESULT_KEYS`` 逐字一致（防「登记了但没下发」）。

    🔴 这正是本平台「additive 注入即死代码」的形态：常量里加了键、装配函数写好了、
    但返回语句忘了带 ⇒ 前端永远读到 undefined，而后端所有单测都绿。
    """
    keys = _return_dict_keys(_code_only(_CTX_PATH.read_text(encoding="utf-8")))
    assert keys, "未能抽到 build_trim_decision_context 的返回 dict —— 锚点漂移"
    mod = _ctx_mod()
    assert tuple(keys) == tuple(mod._RESULT_KEYS), (
        f"返回 dict 的键与 _RESULT_KEYS 不一致：\n  返回={keys}\n  登记={list(mod._RESULT_KEYS)}"
    )


def test_frozen_loaders_signatures_unchanged():
    """五个既有维度装配函数的签名逐字不变（R5.5）。"""
    mod = _ctx_mod()
    expected = {
        "_load_accounts": ["db", "project_id", "year", "cycles"],
        "_load_materiality": ["db", "project_id", "year"],
        "_load_risk": ["db", "project_id"],
        "_load_completeness_override": ["db", "project_id"],
        "_load_workpaper_entry": ["db", "project_id", "cycles"],
    }
    for name in FROZEN_LOADERS:
        fn = getattr(mod, name, None)
        assert fn is not None, f"既有装配函数 {name} 消失了"
        params = list(inspect.signature(fn).parameters)
        assert params == expected[name], f"{name} 签名被改：{params}"


def test_forbidden_keys_still_enforced():
    """``overall_materiality`` 仍在禁用键里（改造未削弱既有结构性保证）。"""
    mod = _ctx_mod()
    assert "overall_materiality" in mod.FORBIDDEN_RESULT_KEYS
    assert "overall_materiality" not in mod._RESULT_KEYS


# ═══════════════════════════════════════════════════════════════════════════
# 新维度的登记与取值域（R5.5）
# ═══════════════════════════════════════════════════════════════════════════
def test_degradation_dimension_registered():
    """``report_line`` 已登记进 ``DEGRADATION_DIMENSIONS``，且既有五维仍在。"""
    mod = _ctx_mod()
    assert mod.DIM_REPORT_LINE == "report_line"
    assert mod.DIM_REPORT_LINE in mod.DEGRADATION_DIMENSIONS
    for legacy in (
        mod.DIM_ACCOUNTS, mod.DIM_MATERIALITY, mod.DIM_RISK,
        mod.DIM_COMPLETENESS_OVERRIDE, mod.DIM_WORKPAPER_ENTRY,
    ):
        assert legacy in mod.DEGRADATION_DIMENSIONS, f"既有维度 {legacy} 被移除"
    assert len(mod.DEGRADATION_DIMENSIONS) == 6, (
        f"维度取值域应为 6 个，实得 {sorted(mod.DEGRADATION_DIMENSIONS)}"
    )


def test_report_line_degradation_rejects_cause():
    """``cause`` 仍是 accounts 维度专属 —— 新维度传 cause 必须报错。"""
    mod = _ctx_mod()
    with pytest.raises(ValueError):
        mod._degradation(mod.DIM_REPORT_LINE, "x", mod.CAUSE_QUERY_FAILED)
    # 不带 cause 时正常
    entry = mod._degradation(mod.DIM_REPORT_LINE, "报表行取数不可用")
    assert entry == {"dimension": "report_line", "reason": "报表行取数不可用"}


def test_loader_exists_with_expected_signature():
    """``_load_report_line_amounts`` 存在且签名与其余维度同款。"""
    mod = _ctx_mod()
    fn = getattr(mod, "_load_report_line_amounts", None)
    assert fn is not None, "未新增 _load_report_line_amounts"
    assert inspect.iscoroutinefunction(fn), "_load_report_line_amounts 必须是 async"
    assert list(inspect.signature(fn).parameters) == [
        "db", "project_id", "year", "cycles",
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 目标集同源（不新建第二套）
# ═══════════════════════════════════════════════════════════════════════════
def _fn_source(src: str, name: str) -> str:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.unparse(node)
    return ""


def test_target_set_reuses_probe_collector():
    """目标 wp_code 清单复用 ``_collect_probe_wp_codes``，不另发查询。"""
    code = _code_only(_CTX_PATH.read_text(encoding="utf-8"))
    body = _fn_source(code, "_load_report_line_amounts")
    assert body, "未能抽到 _load_report_line_amounts 源码"
    assert "_collect_probe_wp_codes" in body, (
        "未复用 _collect_probe_wp_codes —— 第二套目标集会产生「有录入探测但无金额」的半开状态"
    )
    assert "procedure_instances" not in body, (
        "函数体内直接写了 procedure_instances 查询 —— 这就是第二套目标集"
    )
    assert "SELECT" not in body.upper() or "sa.text" not in body, (
        "函数体内自己发了 SQL —— 目标集与 report_config 读取都应委托既有件"
    )


def test_probe_target_sql_appears_exactly_once():
    """``procedure_instances`` 的目标集 SQL 在整个模块里只有一处。

    🔴 判据落在 SQL 标记常量上（``PROBE_TARGET_SQL_MARKER``），而不是数
    ``procedure_instances`` 出现次数 —— 后者会被 docstring 里的说明文字骗。
    """
    mod = _ctx_mod()
    code = _code_only(_CTX_PATH.read_text(encoding="utf-8"))
    marker = mod.PROBE_TARGET_SQL_MARKER
    assert code.count(marker) == 1, (
        f"目标集 SQL 标记 {marker!r} 出现 {code.count(marker)} 次 —— 应恰好一处"
    )
    assert code.count("FROM procedure_instances") == 1, (
        f"procedure_instances 查询出现 {code.count('FROM procedure_instances')} 次 —— 应恰好一处"
    )


def test_report_line_loader_delegates_to_amount_module():
    """金额解析全权委托 ``trim_report_line_amounts``，上下文层不重写取数。"""
    code = _code_only(_CTX_PATH.read_text(encoding="utf-8"))
    body = _fn_source(code, "_load_report_line_amounts")
    assert "resolve_trim_report_line_amounts" in body, "未调用金额解析模块"
    for banned in ("ReportFormulaParser", "report_config", "trial_balance"):
        assert banned not in body, f"上下文层引用了 {banned} —— 取数逻辑应全在金额模块里"


def test_dataclass_to_dict_keeps_null_amount_key():
    """``_report_line_amount_as_dict`` 对 ``amount=None`` **保留键并置 null**。

    省略该键会让前端「hasOwnProperty 判空」与「后端没下发这个维度」不可区分。
    """
    mod = _ctx_mod()
    try:
        from app.services.trim_report_line_amounts import (
            AMOUNT_NO_REPORT_LINE,
            ReportLineAmount,
        )
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import trim_report_line_amounts: {e!r}")

    payload = mod._report_line_amount_as_dict(
        ReportLineAmount(wp_code="L2", status=AMOUNT_NO_REPORT_LINE, reason="无落点")
    )
    assert "amount" in payload, "amount 键被省略了"
    assert payload["amount"] is None, f"amount 竟为 {payload['amount']!r}"
    assert payload["standard_codes"] == [], "standard_codes 未转成 list（JSON 不能序列化 tuple 语义）"
    for key in (
        "status", "amount", "row_code", "row_name", "formula",
        "standard_codes", "applicable_standard", "source_symbol", "reason",
    ):
        assert key in payload, f"下发载荷缺 {key} —— 前端 TrimReportLineAmount 接口对不上"
    assert len(payload) == 9, f"载荷键数应为 9，实得 {sorted(payload)}"


# ═══════════════════════════════════════════════════════════════════════════
# 连库真跑：八键齐全 + 单维失败不阻断（R4.5）
# ═══════════════════════════════════════════════════════════════════════════
_PICK_PROJECT_SQL = """
SELECT id::text AS pid, audit_year,
       (SELECT count(*) FROM procedure_instances pi WHERE pi.project_id = p.id) AS pi_n
FROM projects p
WHERE is_deleted = false AND audit_year IS NOT NULL
  AND EXISTS (SELECT 1 FROM procedure_instances pi WHERE pi.project_id = p.id)
ORDER BY pi_n DESC LIMIT 1
"""


def _live_context():
    """真跑一次 ``build_trim_decision_context``（专用 NullPool engine + 单 loop）。"""
    mod = _ctx_mod()
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with AsyncSession(engine) as session:
                row = (await session.execute(sa.text(_PICK_PROJECT_SQL))).first()
                if row is None:
                    return None
                pid = row.pid
                year = int(row.audit_year)
                ctx = await mod.build_trim_decision_context(session, pid, year, [])
                return {"pid": pid, "year": year, "ctx": ctx}
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"真实库不可达（本组为连库判据）: {e!r}")


@pytest.fixture(scope="module")
def live_ctx():
    got = _live_context()
    if got is None:
        pytest.skip("无带程序实例与年度的项目")
    return got


def test_live_context_has_exactly_eight_keys(live_ctx):
    """真跑结果恰八键，键集合与 ``_RESULT_KEYS`` 相等。"""
    mod = _ctx_mod()
    ctx = live_ctx["ctx"]
    assert set(ctx) == set(mod._RESULT_KEYS), (
        f"键集合不符：多 {sorted(set(ctx) - set(mod._RESULT_KEYS))}、"
        f"缺 {sorted(set(mod._RESULT_KEYS) - set(ctx))}"
    )


def test_live_context_report_line_payload_shape(live_ctx):
    """新键的载荷形态：dict、每项九键、非 resolved 恒无金额。"""
    try:
        from app.services.trim_report_line_amounts import AMOUNT_RESOLVED
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import AMOUNT_RESOLVED: {e!r}")

    payload = live_ctx["ctx"]["report_line_amounts"]
    assert isinstance(payload, dict), f"report_line_amounts 类型为 {type(payload)}"
    bad: list[str] = []
    for code, item in payload.items():
        if not isinstance(item, dict):
            bad.append(f"{code}: 不是 dict")
            continue
        if len(item) != 9:
            bad.append(f"{code}: 键数 {len(item)} ≠ 9（{sorted(item)}）")
        if item.get("status") != AMOUNT_RESOLVED and item.get("amount") is not None:
            bad.append(f"{code}: {item.get('status')} 却带 amount={item.get('amount')!r}")
    assert not bad, f"载荷形态问题：{bad[:10]}"


def test_live_context_degradations_within_domain(live_ctx):
    """``degradations`` 的 dimension 全在六维取值域内，且 cause 只出现在 accounts。"""
    mod = _ctx_mod()
    degs = live_ctx["ctx"]["degradations"]
    assert isinstance(degs, list)
    for d in degs:
        assert d["dimension"] in mod.DEGRADATION_DIMENSIONS, f"未登记维度：{d}"
        if "cause" in d:
            assert d["dimension"] == mod.DIM_ACCOUNTS, f"非 accounts 维度带了 cause：{d}"


def test_live_empty_payload_always_accompanied_by_degradation(live_ctx):
    """``report_line_amounts`` 为空**必须**伴随一条 report_line degradation。

    否则「后端没做报表行取数」与「本项目确实一个底稿都没落点」不可区分，
    前端摘要区会漏标注，审计师以为判据齐全。
    """
    mod = _ctx_mod()
    ctx = live_ctx["ctx"]
    payload = ctx["report_line_amounts"]
    marks = [d for d in ctx["degradations"] if d["dimension"] == mod.DIM_REPORT_LINE]
    if not payload:
        assert marks, (
            "report_line_amounts 为空却无 report_line degradation —— "
            "前端无从知道该维度本次失效"
        )
    else:
        # 非空时若全部 standard_unset，也应标注（整体不可用）
        statuses = {v.get("status") for v in payload.values()}
        if statuses == {"standard_unset"}:
            assert marks, (
                "全部项都是 standard_unset 却无 degradation —— "
                "审计师会逐条看 N 个相同 reason 而不知道去项目设置里确认准则"
            )


def test_live_report_line_failure_does_not_break_other_dimensions(live_ctx, monkeypatch):
    """R4.5：报表行维度整体失败时，其余五个维度照常产出。"""
    mod = _ctx_mod()
    baseline = live_ctx["ctx"]

    async def _boom(db, project_id, year, wp_codes):  # noqa: ANN001
        raise RuntimeError("注入的整体故障（判据用）")

    monkeypatch.setattr(mod, "resolve_trim_report_line_amounts", _boom)

    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with AsyncSession(engine) as session:
                return await mod.build_trim_decision_context(
                    session, live_ctx["pid"], live_ctx["year"], []
                )
        finally:
            await engine.dispose()

    try:
        degraded = asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"报表行维度失败导致整体抛异常：{e!r}")

    assert degraded["report_line_amounts"] == {}, "整体失败时应返空 dict"
    marks = [d for d in degraded["degradations"] if d["dimension"] == mod.DIM_REPORT_LINE]
    assert marks, "整体失败却未记 degradation"

    # 其余五维与基线逐字相同（零回归的运行时证据）
    for key in ("accounts", "materiality", "risk", "risk_dimension_available",
                "completeness_override", "workpaper_entry"):
        assert degraded[key] == baseline[key], (
            f"报表行维度失败连带改变了 {key} —— 维度之间不该有耦合"
        )
