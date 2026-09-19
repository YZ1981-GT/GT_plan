"""Task 44 门禁准入判据守卫 —— 钉住 2026-09-06 修掉的两条结构性缺陷。

═══ 修的是什么 ═══

`check_task44_oo94_excel_pilot_gate.py` 的 `FinalizeSignals.admitted` 原有两个
**结构上不可满足**的合取项，使任何 pilot 永不可准入（与实现好坏无关）：

1. `adapter_registered = adapter_id in registered`，而 `registered` 取自**不带 session**
   的 `build_production_registry()`。Task 75 起该函数只绑定注册计划、不执行注册
   （真实注册在 `register_from_manifest(session=...)`）⇒ 恒为空集 ⇒ 该信号恒 False。
2. `bool(attach_without_representation)` —— 要求「无 published representation 时
   attach 仍返回 adapter_id」，那正是 RG-18 / AC 1.4 禁止的伪双向。

判据全部落在**真实执行 / 源码形态**，不查「某字符串在不在」。
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GATE_PATH = (
    _REPO_ROOT / "backend" / "scripts" / "check" / "check_task44_oo94_excel_pilot_gate.py"
)


def _load_gate():
    """按路径加载门禁脚本（它不在包里，不能 import 名字）。"""
    if not _GATE_PATH.is_file():
        pytest.skip(f"门禁脚本不存在: {_GATE_PATH}")
    spec = importlib.util.spec_from_file_location("_task44_gate_probe", _GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def _probe_impl():
    """取伴生模块里**真实**的请求路径探针实现（判据真源在那里，不是宿主的薄转发）。"""
    path = _GATE_PATH.parent / "_task44_request_path_probe.py"
    if not path.is_file():
        pytest.fail(
            f"伴生探针模块缺失: {path} —— 宿主的薄转发会 ImportError，"
            "请求路径信号整条失效"
        )
    spec = importlib.util.spec_from_file_location("_task44_probe_impl", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.probe_request_path_registration


def _signals(gate, **over):
    """造一份 FinalizeSignals，默认全部「就绪」，由 over 覆盖单项。"""
    base = dict(
        capability_enabled=True,
        capability_reject="",
        adapter_registered=False,  # registry 快照恒空 —— 默认就是 False
        registered_adapter_ids=(),
        published_identity_observer="available",
        observer_detail="",
        attach_without_representation=(),  # 正确行为：无 representation 就拒绝
        attach_with_representation_without_bundle=(),
        attach_session_reads=1,
        request_path_registered_adapter_ids=("d2.receivable_detail",),
        request_path_detail="",
        adapter_id_probe="d2.receivable_detail",
    )
    base.update(over)
    return gate.FinalizeSignals(**base)


class TestAdmissionNoLongerStructurallyUnsatisfiable:
    def test_admitted_is_true_when_request_path_registers(self, gate) -> None:
        """供给就绪时必须准入 —— 这正是修复前**永不可能**发生的事。"""
        assert _signals(gate).admitted is True

    def test_registry_snapshot_false_does_not_block_admission(self, gate) -> None:
        """`adapter_registered`（无 session 的 registry 快照）恒 False 不得再阻断准入。

        它恒空是 Task 75 的设计（只绑定计划、不注册），拿它当供给判据即结构性假红。
        """
        sig = _signals(gate, adapter_registered=False, registered_adapter_ids=())
        assert sig.admitted is True

    def test_admission_requires_request_path_registration(self, gate) -> None:
        """请求路径没注册上 ⇒ 不准入（判据仍然严格，不是放宽）。"""
        assert _signals(gate, request_path_registered_adapter_ids=()).admitted is False

    def test_unavailable_db_is_none_not_false(self, gate) -> None:
        """拿不到真库 ⇒ `None`（unverifiable），**不是** False（failed）。

        两者混为一谈会把「环境不可得」误报成「实现没做」。
        """
        sig = _signals(gate, request_path_registered_adapter_ids=None)
        assert sig.adapter_registered_on_request_path is None
        assert sig.admitted is False

    def test_other_pilots_adapter_id_does_not_count(self, gate) -> None:
        """请求路径注册了**别的** entry 的 adapter 不算本 entry 已注册。"""
        sig = _signals(
            gate, request_path_registered_adapter_ids=("h1.disposal_check",)
        )
        assert sig.adapter_registered_on_request_path is False
        assert sig.admitted is False


class TestRefusalInvariantDirectionIsCorrect:
    def test_empty_attach_without_representation_is_the_healthy_state(self, gate) -> None:
        """无 representation 时返回空元组 = 健康（拒绝伪双向）。"""
        assert _signals(gate, attach_without_representation=()).refuses_without_representation is True

    def test_registering_without_representation_blocks_admission(self, gate) -> None:
        """无 representation 却注册了 adapter ⇒ 伪双向 ⇒ 必须拒绝准入。

        🔴 这条方向不能反：修复前的判据要求它非空才准入，等于把被禁止的行为
        当成准入条件。
        """
        sig = _signals(gate, attach_without_representation=("d2.receivable_detail",))
        assert sig.refuses_without_representation is False
        assert sig.admitted is False


class TestGateMeasuresRequestPath:
    def test_probe_uses_register_from_manifest_not_bare_registry(self, gate) -> None:
        """请求路径探针必须真调 `register_from_manifest`，而不是只读 registry 快照。"""
        src = inspect.getsource(_probe_impl())
        assert "register_from_manifest" in src, (
            "请求路径信号必须经 `register_from_manifest(session=...)` 取得 —— "
            "只读 `build_production_registry()` 的话该信号恒空，缺陷会原样回归"
        )

    def test_probe_uses_isolated_nullpool_engine(self, gate) -> None:
        """必须用独立 NullPool 引擎并 dispose，否则多次 asyncio.run 会制造假 ERROR 态。"""
        src = inspect.getsource(_probe_impl())
        assert "poolclass=NullPool" in src, (
            "共享连接池会让第二次 asyncio.run 报 'NoneType' has no attribute 'send'，"
            "被误读成「库不可达」"
        )
        assert "dispose()" in src

    def test_host_delegates_to_companion_probe(self, gate) -> None:
        """宿主那层薄转发必须**真的调用**伴生模块，不能只在注释里提到它。

        🔴 判据走 AST：变异把 `return probe_request_path_registration()` 换成
        `return None, '未实现'` 时，docstring 里仍留着模块名，子串检查会照绿
        （2026-09-06 变异 M08 实测 GREEN）。这里断言函数体里确有一次
        对 `probe_request_path_registration` 的 Call。
        """
        import ast

        tree = ast.parse(inspect.getsource(gate._probe_request_path_registration).strip())
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        calls = [
            n.func.id
            for n in ast.walk(func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        ]
        assert "probe_request_path_registration" in calls, (
            "宿主没有真调伴生模块的探针 —— 请求路径信号会退化成常量，"
            f"实测调用为 {calls}"
        )

    def test_probe_reports_none_on_failure_not_false(self, gate) -> None:
        """**每一条**失败返回路径都必须给 `None`（unverifiable），不得给 `()`。

        🔴 判据走 AST 而不是子串：该函数里有多处 `return None, ...`，
        用 `"return None" in tail` 会被**别的**分支顶住 —— 变异把异常分支改成
        `return (), ...` 时守卫照绿（2026-09-06 变异检验实测 GREEN）。
        这里逐条取出 return 语句的第一个元素，断言没有任何一条返回空 tuple 字面量。
        """
        import ast

        tree = ast.parse(inspect.getsource(_probe_impl()).strip())
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)

        offenders: list[str] = []
        for node in ast.walk(func):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            value = node.value
            # 形态是 `return <first>, <detail>`
            first = value.elts[0] if isinstance(value, ast.Tuple) and value.elts else value
            # 内层协程 `_run()` 的 `return tuple(...)` 不在此约束内（它是成功路径）
            if isinstance(first, ast.Tuple) and not first.elts:
                offenders.append(ast.unparse(node))
        assert not offenders, (
            "失败路径返回了空 tuple 而不是 None —— 「环境不可得」会被当成"
            f"「实现没做」制造假红：{offenders}"
        )
        # 正向：至少有一条失败路径确实给 None
        nones = [
            ast.unparse(n)
            for n in ast.walk(func)
            if isinstance(n, ast.Return)
            and isinstance(n.value, ast.Tuple)
            and n.value.elts
            and isinstance(n.value.elts[0], ast.Constant)
            and n.value.elts[0].value is None
        ]
        assert nones, "没有任何失败路径返回 None ⇒ unverifiable 分型不存在"

    def test_signals_feed_probe_result_into_admission(self, gate) -> None:
        """`probe_finalize_signals` 必须把请求路径结果真的填进信号里。

        漏填 = 新字段永远是默认值 ⇒ additive 死代码（假绿第①源）。
        """
        src = inspect.getsource(gate.probe_finalize_signals)
        assert "_probe_request_path_registration()" in src
        assert "request_path_registered_adapter_ids=" in src
        assert "adapter_id_probe=" in src


class TestSelfCheckIsNotAssumingRealStateIsFalse:
    def test_state_sensitivity_uses_two_sided_criterion(self, gate) -> None:
        """自检判据不得是 `real != substituted`。

        🔴 那个写法预设「真实态必然 False」：实现真做好之后 real == substituted，
        自检会把「做好了」误判成「读的是死值」而打红。正确判据是双向的
        （就绪 ⇒ True、饿死 ⇒ False）。
        """
        src = inspect.getsource(gate.gate_probe_admission_is_state_sensitive)
        assert "starved" in src, "必须有「信号饿死」那一侧的实测"
        assert "real.admitted != substituted.admitted" not in src, (
            "该判据预设真实态为 False，实现变好时会反向打红"
        )

    def test_substitute_keeps_refusal_invariant(self, gate) -> None:
        """替身的 `_attach` 必须仍返回空元组（保持拒绝不变量）。

        替身若返回 adapter_id 来模拟「已注册」，就与 `refuses_without_representation`
        矛盾，替身态永不可 admitted ⇒ 自检恒红。
        """
        src = inspect.getsource(gate.gate_probe_admission_is_state_sensitive)
        attach_def = src[src.index("async def _attach") :]
        body = attach_def[: attach_def.index("class _Stand")]
        assert "return ()" in body, "替身必须保持「无 representation 就拒绝」"
