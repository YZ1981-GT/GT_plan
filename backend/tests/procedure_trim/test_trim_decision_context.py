# -*- coding: utf-8 -*-
"""Task 9 守卫：裁剪三维判据上下文装配（`app.services.trim_decision_context`）。

Feature: procedure-trimming-and-delegation-intelligence
Validates: Requirements 4.1~4.6, 5.5, 5.6 / Property 34

═══ 本文件的判据分层（判红时先分清是哪一层）═══

- **类 A 独立口径**：不依赖被测实现的事实（源码级只读断言、`_degradation` 契约、
  判据函数自身的替身反向自检）。这些**现在就应该全绿** —— 绿了才证明判据基础设施
  有效而非空转。
- **类 B 被测实现**：装配结果与类 A 口径一致。

═══ 替身 session 必须按 SQL 文本分流（不分流 = 静默错值）═══

`build_trim_decision_context` 一次调用真实走**五条**查询：

1. `trial_balance`（SA Core select）      → 科目金额
2. `materiality`（SA Core select）        → 重要性
3. `wp_index` JOIN（`sa.text`）           → 定位 B50 wp_id（被 risk 与 cscope 各调一次）
4. `checklist_responses LIKE 'B50-T3-%'`  → B50 风险矩阵
5. `checklist_responses LIKE 'B50-T3-cscope-%'` → 完整性清单项目覆盖

🔴 第 4 与第 5 条**都含 `checklist_responses`**，必须再按 `cscope` 子串二次分流 ——
只按表名分流会让 cscope 查询拿到整份矩阵行（反之亦然）而**不报错**（表现为空 dict =
与"没覆盖"不可区分）。范式来自同目录 `test_b50_reader_extension.py` 的 `_FakeSession`，
本文件在其上多分流 `trial_balance` 与 `materiality` 两路。

`get_active_filter` 是真实 async 函数（会查 `ledger_datasets`），故 monkeypatch 成返回
**真实 `sa.true()`**（不是 `MagicMock()` —— 后者一旦被 `sa.and_` 消费会抛异常并被
fail-open 吞成空结果 = 假绿，见 memory「MagicMock 当 get_active_filter 返回值 = 潜在假绿」）。
"""
from __future__ import annotations

import ast
import asyncio
import io
import re
import tokenize
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_SVC_PATH = _BACKEND / "app" / "services" / "trim_decision_context.py"
_ROUTER_PATH = _BACKEND / "app" / "routers" / "procedures.py"

_SEVEN_KEYS = {
    "accounts",
    "materiality",
    "risk",
    "risk_dimension_available",
    "completeness_override",
    "workpaper_entry",
    "degradations",
}


def _svc():
    """测试内 import；失败 fail 而非 skip（skip 会让缺陷静默）。"""
    try:
        from app.services import trim_decision_context as mod
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import app.services.trim_decision_context: {e!r}")
    return mod


# ═══════════════════════════════════════════════════════════════════════════
# 替身
# ═══════════════════════════════════════════════════════════════════════════
class _FakeResult:
    def __init__(self, *, rows=None, one=None, scalar=None):
        self._rows = rows if rows is not None else []
        self._one = one
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    """按 SQL 文本分流七路；任一路可注入异常。

    `raise_on` 取值域 =
    {'trial_balance','materiality','wp_index','responses','cscope','probe_target','probe'}。

    🔴 未预期 SQL 一律 `AssertionError` —— 这是**有意的 tripwire**：新增取数若不在此登记
    就会被服务层的 fail-soft 吞成 degradation，从而「接线错误」伪装成「本项目没数据」。
    Task 10 接线时按此扩了 probe_target / probe 两路，而不是让新查询落进兜底。

    🔴 两路 probe 按 **SQL 首行标记**分流而非表名：探测 SQL 同时含
    `wp_index` / `working_paper` / `checklist_responses` 三张表名，靠表名会被上面的
    `wp_index` 路先抢走（那条返回 scalar，探测侧 `.fetchall()` 会静默得空 → 假绿）。
    """

    def __init__(
        self,
        *,
        tb_rows=None,
        mat_row=None,
        wp_id: str | None = "wp-b50",
        b50_rows=None,
        cscope_rows=None,
        pi_rows=None,
        probe_rows=None,
        raise_on: set[str] | None = None,
    ):
        self.tb_rows = tb_rows if tb_rows is not None else []
        self.mat_row = mat_row
        self.wp_id = wp_id
        self.b50_rows = b50_rows if b50_rows is not None else []
        self.cscope_rows = cscope_rows if cscope_rows is not None else []
        self.pi_rows = pi_rows if pi_rows is not None else []
        self.probe_rows = probe_rows if probe_rows is not None else []
        self.raise_on = raise_on or set()
        self.seen: list[str] = []
        self.probe_params: list[dict] = []

    async def execute(self, stmt, params=None):  # noqa: ANN001
        sql = str(stmt)
        # 标记优先（必须早于表名分流，见类 docstring）
        if "-- probe_target_wp_codes" in sql:
            route = "probe_target"
        elif "-- workpaper_entry_probe" in sql:
            route = "probe"
        elif "trial_balance" in sql:
            route = "trial_balance"
        elif "materiality" in sql:
            route = "materiality"
        elif "wp_index" in sql:
            route = "wp_index"
        elif "checklist_responses" in sql:
            # 🔴 二次分流：cscope 查询与矩阵查询共用同一张表
            route = "cscope" if "cscope" in sql else "responses"
        else:
            raise AssertionError(f"替身收到未预期的 SQL: {sql[:160]}")
        self.seen.append(route)
        if route == "probe":
            self.probe_params.append(dict(params or {}))
        if route in self.raise_on:
            raise RuntimeError(f"injected failure on {route}")
        if route == "trial_balance":
            return _FakeResult(rows=self.tb_rows)
        if route == "materiality":
            return _FakeResult(one=self.mat_row)
        if route == "wp_index":
            return _FakeResult(scalar=self.wp_id)
        if route == "cscope":
            return _FakeResult(rows=self.cscope_rows)
        if route == "probe_target":
            return _FakeResult(rows=self.pi_rows)
        if route == "probe":
            return _FakeResult(rows=self.probe_rows)
        return _FakeResult(rows=self.b50_rows)


def _tb(name, code="1001", audited=None, unadjusted=None):
    return SimpleNamespace(
        account_name=name,
        standard_account_code=code,
        audited_amount=audited,
        unadjusted_amount=unadjusted,
    )


def _mat(pm=None, tt=None):
    return SimpleNamespace(performance_materiality=pm, trivial_threshold=tt)


def _cr(item_id, conclusion=None, remark=None):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _pi(wp_code, audit_cycle="D"):
    """procedure_instances 行（探测目标清单）。"""
    return SimpleNamespace(wp_code=wp_code, audit_cycle=audit_cycle)


def _pe(wp_code, has_entry):
    """底稿已录入探测结果行。"""
    return SimpleNamespace(wp_code=wp_code, has_entry=has_entry)


@pytest.fixture(autouse=True)
def _stub_active_filter(monkeypatch):
    """`get_active_filter` 返回真实 `sa.true()`（禁 MagicMock，见模块 docstring）。"""

    async def _fake(db, table, project_id, year, **kw):  # noqa: ANN001
        return sa.true()

    monkeypatch.setattr(
        "app.services.dataset_query.get_active_filter", _fake, raising=True
    )


def _build(session, *, year=2025, cycles=None):
    mod = _svc()
    return asyncio.run(
        mod.build_trim_decision_context(session, "p-1", year, cycles or [])
    )


def _deg_by_dim(ctx: dict) -> dict[str, dict]:
    return {d["dimension"]: d for d in ctx["degradations"]}


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-1：源码只读断言（不依赖被测行为）
# ═══════════════════════════════════════════════════════════════════════════
def _strip_py_comments(src: str) -> str:
    """剥 `#` 注释 + 全部 docstring，**保留普通字符串字面量**（可能含真实 SQL）。

    docstring 里会如实写出被禁的反例（"不写库"/"不得 INSERT"），裸子串匹配会把说明
    文字数成真实写库调用。
    """
    # 1) 用 ast 收集 docstring 所在行号
    doc_lines: set[int] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:  # pragma: no cover - 语法错时退化为只剥注释
        tree = None
    if tree is not None:
        nodes = [tree]
        nodes += [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        for n in nodes:
            body = getattr(n, "body", None)
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                    doc_lines.add(ln)
    lines = src.splitlines()
    kept = ["" if (i + 1) in doc_lines else ln for i, ln in enumerate(lines)]
    body_src = "\n".join(kept)
    # 2) 剥 `#` 注释 —— 🔴 必须**按 (row, col) 就地截断**保留原始行结构。
    #    用 token.string 重新 join 会把每个 token 放到独立位置，`db.add(` 被拆成
    #    `db . add (` ⇒ `\.add\s*\(` 不再匹配 = 判据静默失效（本文件的
    #    `test_read_only_criteria_self_check` 就是为此把关的）。
    spans: list[tuple[int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(body_src).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((tok.start[0], tok.start[1]))
    except tokenize.TokenError:  # pragma: no cover
        return body_src
    out_lines = body_src.splitlines()
    for row, col in spans:
        if 1 <= row <= len(out_lines):
            out_lines[row - 1] = out_lines[row - 1][:col]
    return "\n".join(out_lines)


# 写库调用判据。🔴 DELETE 必须带 `FROM` 词边界 —— 裸 "DELETE" 会被列名
# `is_deleted` / `deleted_at` 骗（本文件的反向自检钉死了这一点）。
#
# 🔴 同族第二例（2026-08-09 Task 10 落地时暴露）：裸 `\.add\s*\(` 会被 **Python 集合操作**
#    `seen.add(code)` 骗成「出现 db.add( 写库调用」。故 `.add(` 与 `.delete(` 必须锚定
#    session 类接收者；`.add_all(` / `.commit(` / `.flush(` 无 stdlib 同名碰撞，保持宽判据。
#    反向自检见 `test_add_criteria_is_not_fooled_by_set_add`。
_SESSION_RECEIVER = r"(?:db|session|sess|conn|connection)"
_WRITE_PATTERNS: tuple[tuple[str, str], ...] = (
    (rf"\b{_SESSION_RECEIVER}\s*\.\s*add\s*\(", "db.add("),
    (r"\.add_all\s*\(", "db.add_all("),
    (r"\.commit\s*\(", "commit("),
    (r"\.flush\s*\(", "flush("),
    (rf"\b{_SESSION_RECEIVER}\s*\.\s*delete\s*\(", "db.delete("),
    (r"\bINSERT\s+INTO\b", "INSERT INTO"),
    (r"\bUPDATE\s+\w+\s+SET\b", "UPDATE ... SET"),
    (r"\bDELETE\s+FROM\b", "DELETE FROM"),
    (r"\bsa\.insert\s*\(", "sa.insert("),
    (r"\bsa\.update\s*\(", "sa.update("),
    (r"\bsa\.delete\s*\(", "sa.delete("),
)


def find_write_calls(src: str) -> list[str]:
    """判据函数：返回剥注释后命中的写库调用形态清单（空 = 只读）。"""
    stripped = _strip_py_comments(src)
    hits: list[str] = []
    for pat, label in _WRITE_PATTERNS:
        if re.search(pat, stripped, flags=re.IGNORECASE):
            hits.append(label)
    return hits


def test_service_module_is_read_only_at_source_level():
    """Requirement 5.5/5.6：本模块只读，源码级不得出现任何写库调用。"""
    src = _SVC_PATH.read_text(encoding="utf-8")
    hits = find_write_calls(src)
    assert hits == [], f"trim_decision_context.py 出现写库调用: {hits}"


def test_read_only_criteria_self_check():
    """判据反向自检：三个替身各自必须被 `find_write_calls` 打红，且不误伤只读源码。"""
    assert find_write_calls("async def f(db):\n    db.add(x)\n") == ["db.add("]
    assert find_write_calls(
        'async def f(db):\n    await db.execute(sa.text("DELETE FROM t"))\n'
    ) == ["DELETE FROM"]
    assert find_write_calls(
        'async def f(db):\n    await db.execute(sa.text("UPDATE t SET a=1"))\n'
    ) == ["UPDATE ... SET"]
    # 只读源码不得误报
    assert find_write_calls(
        'async def f(db):\n    await db.execute(sa.select(t).where(t.c.is_deleted == sa.false()))\n'
    ) == []


def test_add_criteria_is_not_fooled_by_set_add():
    """🔴 裸 `\\.add\\s*\\(` 会把 Python 集合操作当成写库（Task 10 落地时实测踩中）。

    反向双证：集合 / 字典 / 列表容器操作不得误报；三种 session 接收者形态必须打红。
    """
    # 假阳性侧：纯 Python 容器操作
    assert find_write_calls("def f():\n    seen = set()\n    seen.add(x)\n") == []
    assert find_write_calls("def f():\n    codes.add(code)\n    names.discard(n)\n") == []
    # 真阳性侧：session 类接收者的三种写法都要抓到
    assert find_write_calls("async def f(db):\n    db.add(obj)\n") == ["db.add("]
    assert find_write_calls("async def f(self):\n    self.db.add(obj)\n") == ["db.add("]
    assert find_write_calls("async def f(session):\n    session.add(obj)\n") == ["db.add("]
    # `.add_all(` 无 stdlib 碰撞，保持宽判据（不锚定接收者也要抓到）
    assert find_write_calls("def f(x):\n    x.add_all([a, b])\n") == ["db.add_all("]
    # `.delete(` 同样锚定接收者：容器/缓存客户端不误报，session 必红
    assert find_write_calls("def f():\n    cache.delete(k)\n") == []
    assert find_write_calls("async def f(db):\n    await db.delete(obj)\n") == ["db.delete("]


def test_delete_criteria_is_not_fooled_by_is_deleted_column():
    """🔴 裸 `"DELETE" in sql` 会被列名 `is_deleted` / `deleted_at` 骗。"""
    only_read = (
        "async def f(db):\n"
        '    await db.execute(sa.text("SELECT id FROM t WHERE is_deleted = false"))\n'
        "    x = t.c.deleted_at\n"
    )
    assert find_write_calls(only_read) == []
    assert "DELETE" in only_read.upper(), "反向自检前提失效：样本里本应含 DELETE 子串"


def test_strip_comments_actually_strips():
    """剥注释器自检 —— 否则上面几条断言会在一份"全是注释"的源码上空转。"""
    src = '"""docstring 里写 db.add( 反例"""\n# 注释里写 INSERT INTO t\nx = 1\n'
    out = _strip_py_comments(src)
    assert "db.add(" not in out
    assert "INSERT INTO" not in out
    assert "x = 1" in out
    assert find_write_calls(src) == []


def test_router_endpoint_path_and_permission():
    """端点路径落在 `procedure-scope` 段（避免被 `/procedures/{cycle}` 捕获）+ readonly 依赖。"""
    src = _ROUTER_PATH.read_text(encoding="utf-8")
    assert '"/{project_id}/procedure-scope/trim-decision-context"' in src, (
        "端点路径必须是 /{project_id}/procedure-scope/trim-decision-context"
    )
    # 截该端点装饰器到函数体首行，断言权限依赖在其中
    i = src.index("procedure-scope/trim-decision-context")
    seg = src[i : i + 900]
    assert 'require_project_access("readonly")' in seg, (
        "新端点必须依赖 require_project_access(\"readonly\")（项目读入口至少验证成员身份）"
    )
    assert "build_trim_decision_context" in seg


def test_router_registers_route_and_is_get_only():
    import app.routers.procedures as r

    paths = {
        x.path: getattr(x, "methods", set())
        for x in r.router.routes
        if "trim-decision-context" in x.path
    }
    assert paths, "trim-decision-context 路由未注册"
    (path, methods), = paths.items()
    assert path == "/api/projects/{project_id}/procedure-scope/trim-decision-context"
    assert methods == {"GET"}, f"只读端点必须只有 GET，实际 {methods}"


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-2：`_degradation` 契约 —— cause 只允许出现在 accounts 维度（裁决 2）
# ═══════════════════════════════════════════════════════════════════════════
def test_degradation_dimension_domain_is_exactly_five():
    mod = _svc()
    assert set(mod.DEGRADATION_DIMENSIONS) == {
        "accounts",
        "materiality",
        "risk",
        "completeness_override",
        "workpaper_entry",
    }


def test_degradation_rejects_unregistered_dimension():
    mod = _svc()
    with pytest.raises(ValueError):
        mod._degradation("delegation", "任意理由")


def test_cause_is_accounts_only_at_constructor_level():
    """🔴 裁决 2：`cause` 只允许挂在 accounts 维度，防其余维度被顺手加第二套成因码。"""
    mod = _svc()
    ok = mod._degradation("accounts", "r", cause=mod.CAUSE_QUERY_FAILED)
    assert ok == {
        "dimension": "accounts",
        "reason": "r",
        "cause": mod.CAUSE_QUERY_FAILED,
    }
    for dim in ("materiality", "risk", "completeness_override", "workpaper_entry"):
        with pytest.raises(ValueError):
            mod._degradation(dim, "r", cause=mod.CAUSE_QUERY_FAILED)


def test_degradation_rejects_unregistered_cause():
    mod = _svc()
    with pytest.raises(ValueError):
        mod._degradation("accounts", "r", cause="tb_empty")


def test_accounts_cause_domain_is_exactly_three():
    mod = _svc()
    assert set(mod.ACCOUNTS_CAUSES) == {
        "query_failed",
        "not_imported",
        "no_material_accounts",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-1：返回结构 —— 恰好七键
# ═══════════════════════════════════════════════════════════════════════════
def _healthy_session(**kw):
    base = dict(
        tb_rows=[_tb("货币资金", "1001", audited=1_000_000.0)],
        mat_row=_mat(pm=500_000.0, tt=25_000.0),
        b50_rows=[
            _cr("B50-T3-cycle-货币资金", conclusion="E"),
            _cr("B50-T3-matrix-货币资金-existence-RMM", conclusion="M"),
        ],
        cscope_rows=[_cr("B50-T3-cscope-L", conclusion="Y")],
    )
    base.update(kw)
    return _FakeSession(**base)


def test_returns_exactly_seven_keys():
    ctx = _build(_healthy_session())
    assert set(ctx) == _SEVEN_KEYS, f"键集不符：{sorted(ctx)}"


def test_healthy_path_has_no_degradation_for_three_dimensions():
    ctx = _build(_healthy_session())
    dims = {d["dimension"] for d in ctx["degradations"]}
    assert "accounts" not in dims
    assert "materiality" not in dims
    assert "risk" not in dims
    assert ctx["accounts"] == {"货币资金": {"amount": 1_000_000.0, "cycle": "E"}}
    assert ctx["materiality"] == {
        "performance_materiality": 500_000.0,
        "trivial_threshold": 25_000.0,
    }
    assert ctx["risk_dimension_available"] is True
    assert ctx["completeness_override"] == {"L": True}


def test_all_five_queries_are_reached_on_healthy_path():
    """扫描面非空自检：五条查询都真被走到，否则下面的降级断言可能在空转。"""
    s = _healthy_session()
    _build(s)
    assert {"trial_balance", "materiality", "wp_index", "responses", "cscope"} <= set(
        s.seen
    ), f"实际走到的查询：{s.seen}"


def test_degradation_entries_have_stable_shape():
    """公共字段恰为 dimension+reason；只有 accounts 可多一个 cause。"""
    ctx = _build(_FakeSession(raise_on={"trial_balance", "materiality"}))
    assert ctx["degradations"], "注入两路失败后 degradations 不应为空"
    for d in ctx["degradations"]:
        assert set(d) in ({"dimension", "reason"}, {"dimension", "reason", "cause"})
        assert d["dimension"] in _svc().DEGRADATION_DIMENSIONS
        assert isinstance(d["reason"], str) and d["reason"].strip()
        if "cause" in d:
            assert d["dimension"] == "accounts", (
                f"cause 出现在非 accounts 维度：{d}"
            )


def test_cause_key_appears_only_on_accounts_dimension_in_result():
    """裁决 2 在**装配结果**上再钉一次（构造器断言之外的第二道）。"""
    for raise_on in ({"trial_balance"}, {"materiality"}, {"responses"}, {"cscope"}, set()):
        ctx = _build(_FakeSession(raise_on=raise_on))
        for d in ctx["degradations"]:
            if d["dimension"] != "accounts":
                assert "cause" not in d, f"{d['dimension']} 维度带了 cause: {d}"


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-2：三维度各自降级路径（值为 None/空 且 degradations 有对应条目）
# ═══════════════════════════════════════════════════════════════════════════
def test_materiality_missing_row_degrades():
    ctx = _build(_healthy_session(mat_row=None))
    assert ctx["materiality"] is None
    assert "materiality" in _deg_by_dim(ctx)


def test_materiality_query_failure_degrades():
    ctx = _build(_healthy_session(raise_on={"materiality"}))
    assert ctx["materiality"] is None
    assert "materiality" in _deg_by_dim(ctx)


def test_risk_no_assessed_account_degrades():
    """B50 有科目行但一个认定都没填 rmm ⇒ 风险维度不可用。"""
    ctx = _build(
        _healthy_session(
            b50_rows=[
                _cr("B50-T3-cycle-货币资金", conclusion="E"),
                _cr("B50-T3-balance-货币资金", remark="1000"),
            ]
        )
    )
    assert ctx["risk_dimension_available"] is False
    assert "risk" in _deg_by_dim(ctx)
    # 科目本身仍如实下发（"未评估"不等于"没有这个科目"）
    assert "货币资金" in ctx["risk"]


def test_risk_query_failure_degrades():
    ctx = _build(_healthy_session(raise_on={"responses"}))
    assert ctx["risk_dimension_available"] is False
    assert "risk" in _deg_by_dim(ctx)


def test_workpaper_entry_empty_target_still_degrades():
    """探测目标为空（本项目无带 wp_code 的程序实例）⇒ 空 dict **且**必须有 degradation。

    🔴 空 `workpaper_entry` 不带标注时，「探测不可用 / 无目标」与「探测过且都没录入」在
    前端不可区分 —— 后者会让底稿已录入保护整体失效而无人察觉。

    （Task 10 前本条名为 `test_workpaper_entry_probe_unavailable_degrades`，语义是
    「探测模块尚未交付」；模块交付后该路径已不存在，故按现行语义诚实改名。模块现为
    **顶层硬依赖**：删掉它会让 `trim_decision_context` 直接 import 失败、本文件整批打红，
    比 importlib 静默降级安全。）
    """
    ctx = _build(_healthy_session())  # pi_rows 缺省为空 ⇒ 目标清单为空
    assert ctx["workpaper_entry"] == {}
    assert "workpaper_entry" in _deg_by_dim(ctx), (
        "workpaper_entry 为空却没有 degradation —— 探测不可用与「都没录入」不可区分"
    )


def test_workpaper_entry_wired_returns_explicit_bool_per_code():
    """接线成功路径：每个探测目标都有显式布尔，且**不**记 degradation。"""
    sess = _healthy_session(
        pi_rows=[_pi("D1"), _pi("D2"), _pi("E1")],
        probe_rows=[_pe("D1", True), _pe("D2", False)],  # E1 未命中 → 应补 False
    )
    ctx = _build(sess)
    assert ctx["workpaper_entry"] == {"D1": True, "D2": False, "E1": False}
    assert "workpaper_entry" not in _deg_by_dim(ctx), (
        "探测成功却记了 degradation —— 摘要会常亮假降级，形成告警疲劳"
    )
    assert "probe_target" in sess.seen and "probe" in sess.seen


def test_workpaper_entry_probe_target_filtered_by_cycles():
    """`cycles` 非空时只探测该循环的程序实例（与 `_load_accounts` 同款大写归一口径）。"""
    sess = _healthy_session(
        pi_rows=[_pi("D1", "D"), _pi("E1", "e"), _pi("H1", "H")],
        probe_rows=[],
    )
    _build(sess, cycles=["E"])
    # 只应把 E1 交给探测（'e' 经大写归一命中）
    assert sess.probe_params, "探测未被调用"
    assert sess.probe_params[-1]["codes"] == ["E1"], sess.probe_params[-1]["codes"]


def test_workpaper_entry_probe_target_query_failure_degrades():
    """目标清单查询失败 ⇒ 空 dict + degradation（不得静默当成"无目标"）。"""
    ctx = _build(_healthy_session(raise_on={"probe_target"}))
    assert ctx["workpaper_entry"] == {}
    assert "workpaper_entry" in _deg_by_dim(ctx)


def test_workpaper_entry_probe_failure_degrades_while_keeping_all_true():
    """🔴 探测查询失败 ⇒ 全 True（保守保留）**且必须**记 degradation。

    「探测失败导致全保留」与「确实全都有录入」若不可区分，智能裁剪会整体静默失效
    （每个程序都因"底稿已有录入"而 keep），而四层验证全绿。
    """
    ctx = _build(
        _healthy_session(pi_rows=[_pi("D1"), _pi("D2")], raise_on={"probe"})
    )
    assert ctx["workpaper_entry"] == {"D1": True, "D2": True}
    assert "workpaper_entry" in _deg_by_dim(ctx), (
        "探测降级为全保留却没有 degradation —— 与「确实全都有录入」不可区分"
    )


def test_fake_session_tripwire_still_catches_unregistered_sql():
    """反向自检：替身对未登记 SQL 仍抛 AssertionError（tripwire 未被 Task 10 削弱）。"""
    sess = _healthy_session()
    with pytest.raises(AssertionError, match="未预期的 SQL"):
        asyncio.run(sess.execute(sa.text("SELECT 1 FROM some_unregistered_table")))


def test_completeness_override_query_failure_degrades():
    ctx = _build(_healthy_session(raise_on={"cscope"}))
    assert ctx["completeness_override"] is None
    assert "completeness_override" in _deg_by_dim(ctx)


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-3：裁决 3 —— 重要性不推算、不半开、不下发整体重要性
# ═══════════════════════════════════════════════════════════════════════════
_OVERALL = 2_000_000.0
_COMMON_RATIOS = (0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.9)


def assert_not_derived_from_overall(materiality, overall: float) -> None:
    """判据函数：`materiality` 不得是由 `overall` 按常见比例推算出来的。

    双判据（任一命中即打红）：
      1. 整体维度为 None（真正的"不推算"）—— 直接通过；
      2. 否则 pm 不得等于 overall × 任一常见比例。
    """
    if materiality is None:
        return
    pm = materiality.get("performance_materiality")
    for ratio in _COMMON_RATIOS:
        assert pm != pytest.approx(overall * ratio), (
            f"performance_materiality={pm} 疑似由 overall_materiality={overall} "
            f"× {ratio} 推算而来（Requirement 4.6 禁止推算）"
        )


def test_materiality_is_none_when_only_overall_present():
    """只有 overall_materiality（pm/tt 皆空）⇒ 整个维度缺失，不推算。"""
    ctx = _build(_healthy_session(mat_row=_mat(pm=None, tt=None)))
    assert ctx["materiality"] is None
    deg = _deg_by_dim(ctx)["materiality"]
    assert "推算" in deg["reason"], "降级理由须写明「不由整体重要性推算」"
    assert_not_derived_from_overall(ctx["materiality"], _OVERALL)


@pytest.mark.parametrize(
    "pm,tt",
    [
        (500_000.0, None),  # 半开：只有 pm
        (None, 25_000.0),   # 半开：只有 tt
    ],
)
def test_materiality_rejects_half_open(pm, tt):
    """裁决 3：要么两键齐全，要么整体 None —— 半开一律按维度缺失处理。"""
    ctx = _build(_healthy_session(mat_row=_mat(pm=pm, tt=tt)))
    assert ctx["materiality"] is None, "半开状态必须整体置 None，不得下发半套阈值"
    assert "materiality" in _deg_by_dim(ctx)


def test_derivation_stub_is_caught_by_criteria():
    """🔴 替身反向自检：按 `overall × 0.75` 推算的替身实现必须被判据打红。

    没有这条，`assert_not_derived_from_overall` 可能只是「materiality 恰好为 None」
    时的空转。
    """
    stub = {
        "performance_materiality": _OVERALL * 0.75,
        "trivial_threshold": _OVERALL * 0.75 * 0.05,
    }
    with pytest.raises(AssertionError, match="疑似由 overall_materiality"):
        assert_not_derived_from_overall(stub, _OVERALL)
    # 正对照：真实阈值（与 overall 无比例关系）不得被误伤
    assert_not_derived_from_overall(
        {"performance_materiality": 333_333.0, "trivial_threshold": 12_345.0}, _OVERALL
    )


def _iter_keys(obj):
    """递归产出结构里所有 dict 键。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield from _iter_keys(v)


def test_result_never_contains_overall_materiality_key():
    """🔴 裁决 3：返回结构**任何层级**都不得出现 overall_materiality。

    下发它等于把「不推算」这条约束从后端漏到前端（前端照样能乘个比例）。
    """
    mod = _svc()
    for kw in (
        {},
        {"mat_row": None},
        {"mat_row": _mat(pm=None, tt=None)},
        {"mat_row": _mat(pm=1.0, tt=None)},
        {"raise_on": {"materiality"}},
        {"raise_on": {"trial_balance", "materiality", "responses", "cscope"}},
    ):
        ctx = _build(_healthy_session(**kw))
        keys = set(_iter_keys(ctx))
        assert not (keys & mod.FORBIDDEN_RESULT_KEYS), (
            f"返回结构出现禁用键 {keys & mod.FORBIDDEN_RESULT_KEYS}（入参 {kw}）"
        )


def test_forbidden_key_scan_self_check():
    """递归扫描器自检 —— 否则上一条可能在"扫不到任何键"上空转。"""
    nested = {"a": {"b": [{"overall_materiality": 1}]}}
    assert "overall_materiality" in set(_iter_keys(nested))
    assert "b" in set(_iter_keys(nested))


def test_materiality_query_does_not_select_overall_materiality():
    """结构性保证：SQL 层就不 select 整体重要性（比"返回值里没有"更硬）。

    判据 = 剥注释后 `overall_materiality` 只许出现在 `FORBIDDEN_RESULT_KEYS` 登记行上。
    这样「加一句 `m.c.overall_materiality` 到 select 列表」会立刻打红。
    """
    src = _strip_py_comments(_SVC_PATH.read_text(encoding="utf-8"))
    lines = [ln for ln in src.splitlines() if "overall_materiality" in ln]
    assert lines, "剥注释后完全找不到 overall_materiality —— 禁用键登记表疑似丢失（判据空转）"
    for ln in lines:
        assert "FORBIDDEN_RESULT_KEYS" in ln, (
            f"overall_materiality 出现在登记表之外的代码行：{ln.strip()!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-4：accounts 三态成因可区分（Property 34 + 裁决 1）
# ═══════════════════════════════════════════════════════════════════════════
def accounts_cause_of(ctx: dict) -> str | None:
    """判据函数：抽出 accounts 维度的成因码（无降级返回 None）。"""
    for d in ctx["degradations"]:
        if d["dimension"] == "accounts":
            return d.get("cause")
    return None


def assert_three_causes_distinguishable(
    ctx_failed: dict, ctx_empty: dict, ctx_all_zero: dict
) -> None:
    """判据函数：三种输入必须产出三个**互不相同**且各自正确的成因码。

    并且三态**全部阻断裁剪**（accounts 为空 ⇒ 前端拿不到金额 ⇒ 不裁）。
    """
    got = (
        accounts_cause_of(ctx_failed),
        accounts_cause_of(ctx_empty),
        accounts_cause_of(ctx_all_zero),
    )
    assert got == ("query_failed", "not_imported", "no_material_accounts"), (
        f"三态成因不可区分：{got}"
    )
    assert len(set(got)) == 3
    for ctx in (ctx_failed, ctx_empty, ctx_all_zero):
        assert ctx["accounts"] == {}, "三态都必须阻断裁剪（accounts 为空）"


def _ctx_query_failed():
    return _build(_healthy_session(raise_on={"trial_balance"}))


def _ctx_not_imported():
    return _build(_healthy_session(tb_rows=[]))


def _ctx_no_material_accounts():
    """有行但过滤后零科目：金额全零。"""
    return _build(
        _healthy_session(
            tb_rows=[
                _tb("货币资金", "1001", audited=0.0),
                _tb("应收账款", "1122", audited=None, unadjusted=0.0),
            ]
        )
    )


def test_accounts_three_causes_are_distinguishable():
    assert_three_causes_distinguishable(
        _ctx_query_failed(), _ctx_not_imported(), _ctx_no_material_accounts()
    )


def test_bad_behaviour_stub_collapsing_causes_is_caught():
    """🔴 复现「把不可用当无数据」坏行为的替身必须被同一判据打红。

    坏行为 = 取数失败时报 `not_imported`（既有两个数据源都这么干：`get_scope_accounts`
    的 except 与「过滤后为空」共用同类文案；`resolve_subject_data_availability` 查询失败
    直接 `return {"tb_empty": True}` 把技术故障伪装成"试算表空"）。
    """
    bad_failed = {
        "accounts": {},
        "degradations": [
            {"dimension": "accounts", "reason": "试算表未导入或查询失败",
             "cause": "not_imported"}
        ],
    }
    with pytest.raises(AssertionError, match="三态成因不可区分"):
        assert_three_causes_distinguishable(
            bad_failed, _ctx_not_imported(), _ctx_no_material_accounts()
        )


def test_bad_behaviour_stub_without_degradation_is_caught():
    """更坏的形态：取数失败后**不记 degradation**（静默返回空 accounts）。"""
    silent = {"accounts": {}, "degradations": []}
    with pytest.raises(AssertionError, match="三态成因不可区分"):
        assert_three_causes_distinguishable(
            silent, _ctx_not_imported(), _ctx_no_material_accounts()
        )


def test_bad_behaviour_stub_returning_accounts_on_failure_is_caught():
    """取数失败却下发非空 accounts（把不可用当可用）同样必须打红。"""
    leaky = {
        "accounts": {"货币资金": {"amount": 0.0, "cycle": "E"}},
        "degradations": [
            {"dimension": "accounts", "reason": "x", "cause": "query_failed"}
        ],
    }
    with pytest.raises(AssertionError, match="三态都必须阻断裁剪"):
        assert_three_causes_distinguishable(
            leaky, _ctx_not_imported(), _ctx_no_material_accounts()
        )


def test_three_causes_have_distinct_reason_wording():
    """文案方向必须可区分（技术故障 / 请先导入 / 已导入但全零）。"""
    reasons = []
    for ctx in (_ctx_query_failed(), _ctx_not_imported(), _ctx_no_material_accounts()):
        reasons.append(
            next(d["reason"] for d in ctx["degradations"] if d["dimension"] == "accounts")
        )
    assert len(set(reasons)) == 3, f"三态文案不可区分：{reasons}"
    assert "失败" in reasons[0]
    assert "导入" in reasons[1]
    assert "零" in reasons[2] or "核实" in reasons[2]


def test_cycle_filter_empty_result_is_no_material_accounts_not_not_imported():
    """试算表有非零科目、但都不在所选循环 ⇒ 仍是"已导入"态，不得报 not_imported。"""
    ctx = _build(
        _healthy_session(tb_rows=[_tb("货币资金", "1001", audited=1000.0)]),
        cycles=["L"],
    )
    assert ctx["accounts"] == {}
    assert accounts_cause_of(ctx) == "no_material_accounts"


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-5：accounts 取数口径（与 get_scope_accounts 同口径）
# ═══════════════════════════════════════════════════════════════════════════
def test_audited_amount_takes_precedence_over_unadjusted():
    ctx = _build(
        _healthy_session(
            tb_rows=[_tb("货币资金", "1001", audited=900.0, unadjusted=100.0)]
        )
    )
    assert ctx["accounts"]["货币资金"]["amount"] == 900.0


def test_falls_back_to_unadjusted_when_audited_is_null():
    ctx = _build(
        _healthy_session(
            tb_rows=[_tb("货币资金", "1001", audited=None, unadjusted=123.45)]
        )
    )
    assert ctx["accounts"]["货币资金"]["amount"] == 123.45


def test_same_account_name_rows_are_aggregated():
    """同名多子科目合并求和（get_scope_accounts 口径）。"""
    ctx = _build(
        _healthy_session(
            tb_rows=[
                _tb("货币资金", "1001", audited=100.0),
                _tb("货币资金", "1002", audited=250.5),
            ]
        )
    )
    assert ctx["accounts"]["货币资金"]["amount"] == 350.5


def test_near_zero_accounts_are_filtered_but_nonzero_kept():
    ctx = _build(
        _healthy_session(
            tb_rows=[
                _tb("货币资金", "1001", audited=1e-9),   # 过滤
                _tb("应收账款", "1122", audited=-500.0),  # 保留（负额也是有数据）
            ]
        )
    )
    assert "货币资金" not in ctx["accounts"]
    assert ctx["accounts"]["应收账款"]["amount"] == -500.0


def test_cycle_is_mapped_by_cycle_for_account():
    """cycle 由 `b50_risk_reader.cycle_for_account` 映射（不自造第二套关键词表）。"""
    from app.services.b50_risk_reader import cycle_for_account

    ctx = _build(
        _healthy_session(
            tb_rows=[
                _tb("货币资金", "1001", audited=1.0),
                _tb("应收账款", "1122", audited=2.0),
                _tb("应交税费", "2221", audited=3.0),
            ]
        )
    )
    for name in ("货币资金", "应收账款", "应交税费"):
        assert ctx["accounts"][name]["cycle"] == cycle_for_account(name, "")


def test_cycle_filter_is_case_insensitive_and_keeps_only_wanted():
    ctx = _build(
        _healthy_session(
            tb_rows=[
                _tb("货币资金", "1001", audited=1.0),   # E
                _tb("应收账款", "1122", audited=2.0),   # D
            ]
        ),
        cycles=["e"],
    )
    assert set(ctx["accounts"]) == {"货币资金"}


def test_blank_account_name_rows_are_skipped():
    ctx = _build(
        _healthy_session(
            tb_rows=[
                _tb("  ", "1001", audited=999.0),
                _tb("货币资金", "1001", audited=1.0),
            ]
        )
    )
    assert set(ctx["accounts"]) == {"货币资金"}


def test_service_docstring_declares_shared_criteria_with_scope_accounts():
    """两处一改必须同改 —— 口径来源必须在 docstring 里写明（防下个会话各改一份）。"""
    src = _SVC_PATH.read_text(encoding="utf-8")
    assert "get_scope_accounts" in src, "docstring 须写明与 get_scope_accounts 同口径"
    assert "同改" in src or "同口径" in src


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-6：risk_dimension_available = 「至少一个认定有 rmm」（不是六认定全填）
# ═══════════════════════════════════════════════════════════════════════════
def test_risk_available_false_when_accounts_exist_but_no_rmm():
    ctx = _build(
        _healthy_session(
            b50_rows=[
                _cr("B50-T3-cycle-货币资金", conclusion="E"),
                _cr("B50-T3-cycle-应收账款", conclusion="D"),
            ]
        )
    )
    assert ctx["risk"], "科目应如实下发"
    assert ctx["risk_dimension_available"] is False


def test_risk_available_true_with_only_one_assertion_filled():
    """🔴 钉死「至少一个」口径：只填 1/6 个认定即视为可用。

    严格口径（`useB50RiskMatrix.incompleteAccounts` 的「六认定全填」）会让「只填了关键
    认定」的项目在裁剪页恒显示"B50 未填"而无法使用风险维度。前端 `b50Completeness.ts`
    的 docstring 明文警告不得把两个口径统一。
    """
    ctx = _build(
        _healthy_session(
            b50_rows=[
                _cr("B50-T3-cycle-货币资金", conclusion="E"),
                _cr("B50-T3-matrix-货币资金-completeness-RMM", conclusion="H"),
            ]
        )
    )
    assert ctx["risk_dimension_available"] is True
    cells = ctx["risk"]["货币资金"]["cells"]
    assert len(cells) == 1, "本样本只填了一个认定 —— 严格口径下会判未完成"
    assert ctx["risk"]["货币资金"]["max_risk"] == "H"


def test_risk_available_ignores_special_risk_without_rmm():
    """只勾了特别风险而没填 rmm ⇒ 风险等级维度仍不可用（判据是 rmm 不是 special）。"""
    ctx = _build(
        _healthy_session(
            b50_rows=[
                _cr("B50-T3-matrix-货币资金-existence-SR", conclusion="Y"),
            ]
        )
    )
    assert ctx["risk"]["货币资金"]["has_special"] is True
    assert ctx["risk_dimension_available"] is False


def test_risk_available_predicate_is_pure_and_directly_testable():
    """直接对纯函数施加判据（不经装配），钉死「至少一个」而非「全填」。"""
    mod = _svc()
    six = ["existence", "completeness", "accuracy", "cutoff", "classification", "presentation"]
    one_filled = {
        "A": {"cells": {a: {"rmm": ("M" if a == "cutoff" else None), "special": False} for a in six}}
    }
    none_filled = {"A": {"cells": {a: {"rmm": None, "special": False} for a in six}}}
    assert mod._risk_dimension_available(one_filled) is True
    assert mod._risk_dimension_available(none_filled) is False
    assert mod._risk_dimension_available({}) is False


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-7：completeness_override 三态（Y/N/键不存在）
# ═══════════════════════════════════════════════════════════════════════════
def test_completeness_override_three_states():
    ctx = _build(
        _healthy_session(
            cscope_rows=[
                _cr("B50-T3-cscope-L", conclusion="Y"),
                _cr("B50-T3-cscope-J", conclusion="N"),
                # D 那一行压根不存在 ⇒ 不进 dict（前端退回平台默认清单）
            ]
        )
    )
    ov = ctx["completeness_override"]
    assert ov == {"L": True, "J": False}, f"三态不可区分：{ov}"
    assert "D" not in ov, "未覆盖的循环不得出现在 dict 里（否则退不回平台默认）"


def test_completeness_override_ignores_dirty_values():
    """空 / 历史脏值视为未覆盖（不进 dict）—— 不得当成 False。"""
    ctx = _build(
        _healthy_session(
            cscope_rows=[
                _cr("B50-T3-cscope-L", conclusion=""),
                _cr("B50-T3-cscope-J", conclusion="on"),
                _cr("B50-T3-cscope-K", conclusion=None),
                _cr("B50-T3-cscope-N", conclusion="y"),  # 大小写不敏感
            ]
        )
    )
    assert ctx["completeness_override"] == {"N": True}


def test_completeness_override_empty_when_no_b50_workpaper():
    """未建 B50 底稿 = 没有任何项目级覆盖，是正常状态（`{}` 而非 `None`），不记降级。"""
    ctx = _build(_healthy_session(wp_id=None))
    assert ctx["completeness_override"] == {}
    assert "completeness_override" not in _deg_by_dim(ctx)


def test_completeness_override_none_is_distinct_from_empty_dict():
    """`None`（读取失败，退回默认并标注）与 `{}`（无覆盖）必须可区分。"""
    failed = _build(_healthy_session(raise_on={"cscope"}))
    none_wp = _build(_healthy_session(wp_id=None))
    assert failed["completeness_override"] is None
    assert none_wp["completeness_override"] == {}
    assert failed["completeness_override"] is not none_wp["completeness_override"]


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-8：全维度同时失败仍不抛异常（fail-soft 但不静默）
# ═══════════════════════════════════════════════════════════════════════════
def test_all_dimensions_failing_still_returns_seven_keys_with_degradations():
    ctx = _build(
        _FakeSession(
            raise_on={"trial_balance", "materiality", "wp_index", "responses", "cscope"}
        )
    )
    assert set(ctx) == _SEVEN_KEYS
    assert ctx["accounts"] == {}
    assert ctx["materiality"] is None
    assert ctx["risk"] == {}
    assert ctx["risk_dimension_available"] is False
    assert ctx["workpaper_entry"] == {}
    dims = {d["dimension"] for d in ctx["degradations"]}
    # wp_index 失败被 `_find_b50_wp_id` fail-open 成 None ⇒ 走「B50 未建」正常态；
    # 其余四个维度必须各有一条标注。
    assert {"accounts", "materiality", "risk", "workpaper_entry"} <= dims, dims


# ═══════════════════════════════════════════════════════════════════════════
# 类 C：前端登记跨前后端交叉锁死
#
# 有意把判据放在**这一份**文件里（不新建前端 spec）—— 同一不变式两处各写一份的话，
# 改一处另一处不红（memory 已多次实证）。
# ═══════════════════════════════════════════════════════════════════════════
_FE = _BACKEND.parent / "audit-platform" / "frontend" / "src" / "services"
_API_PATHS = _FE / "apiPaths" / "workpaper.ts"
_API_BARREL = _FE / "apiPaths" / "index.ts"
_COMMON_API = _FE / "commonApi.ts"


def _fe_src(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"前端文件不存在: {path}")
    return path.read_text(encoding="utf-8")


def test_frontend_apipath_matches_backend_route_verbatim():
    """apiPaths 访问器路径 ↔ 后端 router 注册路径逐字一致。"""
    paths_src = _fe_src(_API_PATHS)
    m = re.search(
        r"trimDecisionContext:\s*\(pid: string\)\s*=>\s*\n?\s*`([^`]+)`", paths_src
    )
    assert m, "apiPaths 未声明 trimDecisionContext 访问器"
    fe_path = m.group(1).replace("${pid}", "{project_id}")

    import app.routers.procedures as r

    be_paths = [x.path for x in r.router.routes if "trim-decision-context" in x.path]
    assert be_paths, "后端未注册 trim-decision-context 路由"
    assert fe_path == be_paths[0], (
        f"前端路径 {fe_path!r} 与后端注册 {be_paths[0]!r} 不一致"
    )


def test_trim_decision_accessor_lives_in_reexported_object():
    """访问器必须挂在**已被 barrel 具名 re-export** 的对象内。

    barrel 用具名 re-export（不是 `export *`）⇒ 新建 const 而不改 index.ts 的清单，
    外部会拿到 `undefined`。挂进既有 `procedures` 对象即零改动 barrel。
    """
    paths_src = _fe_src(_API_PATHS)
    obj_start = paths_src.index("export const procedures = {")
    obj_end = paths_src.index("} as const", obj_start)
    assert "trimDecisionContext" in paths_src[obj_start:obj_end], (
        "trimDecisionContext 必须声明在 procedures 对象内"
    )
    barrel = _fe_src(_API_BARREL)
    assert re.search(r"\bprocedures\b", barrel), (
        "procedures 对象未被 apiPaths/index.ts 具名 re-export ⇒ 外部拿到 undefined"
    )


def test_common_api_fetch_function_uses_apipaths_not_hardcoded_url():
    """取数函数存在、走 apiPaths 访问器、不硬编码 URL。"""
    src = _fe_src(_COMMON_API)
    assert "export async function fetchTrimDecisionContext" in src, (
        "commonApi 缺少 fetchTrimDecisionContext"
    )
    body_start = src.index("export async function fetchTrimDecisionContext")
    body = src[body_start : body_start + 1600]
    assert "trimDecisionContext(" in body, "取数函数未走 apiPaths 访问器"
    assert "procedure-scope" not in body, (
        "取数函数里出现硬编码 URL 片段 —— 必须走 apiPaths 单一真源"
    )


def test_frontend_type_does_not_expose_overall_materiality():
    """🔴 裁决 3 在前端侧再钉一次：类型与取数函数都不得出现 overall_materiality。"""
    src = _fe_src(_COMMON_API)
    i = src.index("export interface TrimDecisionContext")
    j = src.index("export async function getProcedureMaterializeJob")
    seg = src[i:j]
    # 注释里如实写出「不得推算 overall_materiality」是资产不是残留 ⇒ 只扫代码行
    code = "\n".join(
        ln
        for ln in seg.splitlines()
        if not ln.strip().startswith(("*", "//", "/*"))
    )
    assert "overall_materiality" not in code, (
        "前端类型/取数函数出现 overall_materiality —— 下发它等于让 AC 4.6 从后端漏到前端"
    )
    assert "overall_materiality" in seg, (
        "反向自检失效：该段注释本应写明不得推算 overall_materiality"
    )


def test_frontend_keeps_null_distinguishable_from_empty():
    """`materiality` / `completeness_override` 的 null 不得被前端兜底成 `{}`。

    兜底会让「维度缺失」与「查到了但为空」不可区分 —— 前者不许用该判据，后者可以。
    """
    src = _fe_src(_COMMON_API)
    body_start = src.index("export async function fetchTrimDecisionContext")
    body = src[body_start : body_start + 1600]
    assert re.search(r"materiality:\s*p\?\.materiality\s*\?\?\s*null", body), (
        "materiality 必须保留 null（禁 asObj/{}兜底）"
    )
    assert re.search(
        r"completeness_override:\s*p\?\.completeness_override\s*\?\?\s*null", body
    ), "completeness_override 必须保留 null（禁 {} 兜底）"
