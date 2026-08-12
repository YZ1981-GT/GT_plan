# -*- coding: utf-8 -*-
"""成员负载批量视图守卫（Task 16 / Requirements 10.3, 10.4, 10.5）。

守的是**口径单一性**：`member_workloads()`（批量，供下拉与委派界面展示）与
`_assignee_workload()`（单成员，preview 返回 `membership_load.active_task_count`）
必须逐条同口径 —— 一侧改了过滤条件而另一侧未跟进即打红。

为什么值得守：改造前前端自行按"底稿张数"聚合了第二份负载（口径与后端"非终态
任务数"不同，且仅在打开全项目概览后才有值）。收敛到后端单一真源后，如果两个
后端方法自己再分叉，就又回到双真源 —— 只是这次分叉发生在后端、更难发现。

不连库：判据全部基于**编译后的 SQL 文本**与源码 AST，可直接进 CI。
"""
from __future__ import annotations

import ast
import io
import re
import textwrap
import tokenize
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
SERVICE_PY = BACKEND / "app" / "services" / "procedure_delegation_service.py"
ROUTER_PY = BACKEND / "app" / "routers" / "procedure_delegations.py"


# ---------------------------------------------------------------------------
# 读源码型判据的前置：剥注释与 docstring
#
# 🔴 必须剥，否则守卫会被**自己的说明文字**骗过。实测两例：
#   - 把 `isnot(None)` 删掉并留注释 `# removed isnot(None)` → 裸子串判据仍通过
#   - 把返回键 `"loads"` 改掉，但 docstring 里写着 `{"loads": ...}` → 判据仍通过
# 两者都是「守卫看着全绿而功能已坏」，由变异检验抓出。
#
# 只剥 `#` 注释（tokenize）与 docstring（AST），**不剥普通字符串字面量**
# —— 字典键名、SQL 片段都是真实代码，剥了会产生假红。
# ---------------------------------------------------------------------------


def _code_lines(path: Path) -> list[str]:
    """逐行返回 code-only 文本（注释与 docstring 置空，行号保持不变）。"""
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()

    # 1) 剥 # 注释（按 token 的列区间精确切除，保留行内代码）
    drops: list[tuple[int, int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                drops.append((tok.start[0], tok.start[1], tok.end[1]))
    except tokenize.TokenError:  # pragma: no cover - 容忍不完整尾部
        pass
    for row, c0, c1 in sorted(drops, reverse=True):
        i = row - 1
        if 0 <= i < len(lines):
            lines[i] = lines[i][:c0] + lines[i][c1:]

    # 2) 剥 docstring（module / class / function 的首个字符串表达式）
    tree = ast.parse(src)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for i in range(first.lineno - 1, (first.end_lineno or first.lineno)):
                if 0 <= i < len(lines):
                    lines[i] = ""
    return lines


def _func_code(path: Path, name: str) -> str:
    """取某函数/方法的 **code-only** 源码（已剥注释与 docstring）。"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = _code_lines(path)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            end = node.end_lineno or node.lineno
            return "\n".join(lines[node.lineno - 1 : end])
    raise AssertionError(f"{path.name} 中未找到函数 {name}")


def _raw_func(path: Path, name: str) -> str:
    """取某函数的**原始**源码（含注释，仅用于反向自检）。"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            end = node.end_lineno or node.lineno
            return "\n".join(lines[node.lineno - 1 : end])
    raise AssertionError(f"{path.name} 中未找到函数 {name}")


def _service_cls():
    try:
        from app.services.procedure_delegation_service import ProcedureDelegationService
    except Exception as exc:  # pragma: no cover - 导入失败要打红而非 skip
        pytest.fail(f"无法导入 ProcedureDelegationService：{exc}")
    return ProcedureDelegationService


# ---------------------------------------------------------------------------
# 类 A：独立口径判据（现在就应全绿）
# ---------------------------------------------------------------------------


def test_service_source_exists():
    """守卫的扫描面非空自检（防路径写错导致所有断言空转）。"""
    assert SERVICE_PY.exists(), f"service 源码不存在：{SERVICE_PY}"
    assert ROUTER_PY.exists(), f"router 源码不存在：{ROUTER_PY}"
    src = SERVICE_PY.read_text(encoding="utf-8")
    assert "_assignee_workload" in src, "既有单成员负载方法不见了，判据基准已失效"


def test_terminal_states_constant_is_shared():
    """两个方法必须引用**同一个**终态常量，而不是各写一份字面量集合。"""
    src = SERVICE_PY.read_text(encoding="utf-8")
    assert "TERMINAL_WORKFLOW_STATES" in src
    # 不得出现内联的终态字面量集合（那会让两处独立漂移）
    inline = re.findall(r"\{\s*['\"](?:reviewed|cancelled)['\"]", src)
    assert not inline, (
        "发现内联终态字面量集合 %r —— 终态口径必须只有 TERMINAL_WORKFLOW_STATES "
        "一个真源，否则两个负载方法会各自漂移" % inline
    )


# ---------------------------------------------------------------------------
# 类 B：批量与单成员口径一致（本 Task 的被测实现）
# ---------------------------------------------------------------------------

# 两个方法都必须施加的过滤条件（按 SQL 文本片段判定，不依赖调用顺序）
_SHARED_FILTERS = (
    "project_id",
    "is_deleted",
    "workflow_status",
)


def _func_source(cls, name: str) -> str:
    """按 code-only 口径取方法源码（cls 参数仅用于存在性校验）。"""
    assert getattr(cls, name, None) is not None, f"{cls.__name__}.{name} 不存在"
    return _func_code(SERVICE_PY, name)


def test_strip_comments_self_check():
    """反向自检：剥注释必须真的生效，否则下面所有判据都会被说明文字骗过。"""
    raw = _raw_func(SERVICE_PY, "member_workloads")
    code = _func_code(SERVICE_PY, "member_workloads")
    assert "必须同口径" in raw, "member_workloads 的 docstring 说明文字不见了（判据基准失效）"
    assert "必须同口径" not in code, (
        "剥注释未生效 —— docstring 内容仍在 code-only 文本里，"
        "守卫会被自己的说明文字骗过（实测变异 M6/M8 即因此假绿）"
    )
    assert "sa.select" in code, "剥注释过度，把真实代码也剥掉了"


def test_member_workloads_exists_and_is_async():
    import inspect as _inspect

    cls = _service_cls()
    fn = getattr(cls, "member_workloads", None)
    assert fn is not None, (
        "ProcedureDelegationService.member_workloads 不存在 —— "
        "底稿主编下拉需要全部成员的负载，而 preview 只返回被选中那一个"
    )
    assert _inspect.iscoroutinefunction(fn), "member_workloads 必须是 async"
    sig = _inspect.signature(fn)
    assert list(sig.parameters) == ["self", "project_id"], (
        "member_workloads 签名应为 (self, project_id)，实为 %s" % sig
    )


@pytest.mark.parametrize("token", _SHARED_FILTERS)
def test_batch_applies_same_filters_as_single(token: str):
    """批量版必须施加与单成员版相同的三个过滤条件。"""
    cls = _service_cls()
    single = _func_source(cls, "_assignee_workload")
    batch = _func_source(cls, "member_workloads")
    assert token in single, f"基准方法 _assignee_workload 未含过滤 {token}（判据已失效）"
    assert token in batch, (
        f"member_workloads 缺少过滤条件 {token} —— 与 _assignee_workload 口径分叉，"
        "会让下拉显示的负载与委派 preview 显示的负载不一致"
    )


def test_batch_excludes_null_assignee():
    """批量版按 assignee 分组，必须显式排除未分配任务（单成员版靠等值匹配天然排除）。"""
    cls = _service_cls()
    batch = _func_source(cls, "member_workloads")
    assert "isnot(None)" in batch or "is_not(None)" in batch, (
        "member_workloads 必须显式排除 assignee_staff_id 为 NULL 的任务，"
        "否则 GROUP BY 会产出一个 key 为 None 的伪成员"
    )
    assert "group_by" in batch, "member_workloads 必须按 assignee 分组"


def test_batch_is_single_query():
    """批量版必须一次查完（不得按成员循环发查询）。"""
    cls = _service_cls()
    batch = _func_source(cls, "member_workloads")
    # 🔴 用 textwrap.dedent 而非 inspect.cleandoc —— 后者是为 docstring 设计的，
    # 对方法源码会破坏缩进并抛 IndentationError
    tree = ast.parse(textwrap.dedent(batch))
    loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.AsyncFor, ast.While))]
    for node in loops:
        seg = ast.dump(node)
        assert "execute" not in seg, (
            "member_workloads 在循环里发查询 —— 必须一次 GROUP BY 查完，"
            "否则成员多时会退化成 N+1"
        )


def test_returns_str_keyed_dict():
    """返回值键必须是 str（前端按 staff_id 字符串索引）。"""
    cls = _service_cls()
    batch = _func_source(cls, "member_workloads")
    assert "str(" in batch, "member_workloads 必须把 staff_id 转成 str 作为 dict 键"


# ---------------------------------------------------------------------------
# 端点：只读
# ---------------------------------------------------------------------------


def _endpoint_body() -> str:
    """端点的 code-only 源码（🔴 必须剥 docstring：它里面写着 `{"loads": ...}`，
    不剥会让「返回键名被改掉」这个变异静默逃逸）。"""
    return _func_code(ROUTER_PY, "delegation_member_loads")


def test_endpoint_strip_self_check():
    """反向自检：端点 docstring 确实含 loads 字样，且剥后不含。"""
    raw = _raw_func(ROUTER_PY, "delegation_member_loads")
    code = _endpoint_body()
    assert "只读" in raw, "端点 docstring 不见了（判据基准失效）"
    assert "只读" not in code, "剥 docstring 未生效"
    assert "svc.member_workloads" in code, "剥过度，真实代码被剥掉"


def test_endpoint_registered_as_get():
    src = ROUTER_PY.read_text(encoding="utf-8")
    assert 'router.get("/{pid}/procedure-delegations/member-loads")' in src, (
        "member-loads 端点必须以 GET 注册（只读视图）"
    )


def test_endpoint_is_read_only():
    """端点不得 commit / flush / 写表。"""
    body = _endpoint_body()
    for forbidden in ("commit(", "flush(", "db.add(", "db.delete("):
        assert forbidden not in body, (
            f"member-loads 端点出现写操作 {forbidden} —— 它是纯读视图"
        )


def test_endpoint_keeps_delegator_guard():
    """端点必须保留项目级 Delegator 守卫（与同 router 其余端点一致，fail-closed）。"""
    body = _endpoint_body()
    assert "require_project_delegator_pid" in body, (
        "member-loads 端点缺少 require_project_delegator_pid 守卫 —— "
        "负载数据属项目内部信息，不得对无委派权限者开放"
    )


def test_endpoint_returns_loads_key():
    body = _endpoint_body()
    assert '"loads"' in body, "端点返回体必须含 loads 键（前端按此解析）"
