"""删除端点强制 CAS（需求 13.4、13.5，ADR-FHIC-11）。

三个 DELETE 端点均要求 ``expected_version``：
- ``DELETE /api/workpapers/{wp_id}/formulas/{formula_id}?expected_version=``
- ``DELETE /api/formula-templates/{template_id}?expected_version=``
- ``DELETE /api/projects/{pid}/formula-settings/{domain}/overrides?slot_key=&expected_version=``

## 本文件的判据层级（2026-10-29 重写，勘误见下）

🔴 **重写原因**：本文件原第 1~3 节共 8 条用例是空壳 —— 在测试里自己
``raise HTTPException(...)`` 再断言自己抛的那个异常，或把 ``restore_global`` 的
CAS 循环整段抄进测试体内跑。**零条触达生产端点**，故「缺 428 / 不符 409 /
个数不等 422」三项长期零覆盖。暴露途径：候选给 ``delete_formula`` 加上强制 CAS
后，HEAD 既有的真发请求用例
``test_task_5_4_batch_cas_audit.py::TestAuditChain::test_single_delete_writes_audit``
（不带版本号、期望 200）变红 —— 真覆盖的那条咬出了语义变化，而本该守它的新用例
全是空壳（memory 铁律㉓①「写了 service 却从未调用其主函数」、「端到端测试在测试
里重写循环」）。

重写后的判据分两层，**行为层只覆盖 wp_formula**：

| 端点 | 行为判据（真发请求） | 源码判据（本文件） |
|------|---------------------|-------------------|
| ``wp_formula.delete_formula`` | ✅ `test_task_5_4_batch_cas_audit.py` 的 `TestCASPreconditionRequired`：缺版本 428、版本不符 409，两种情况都对账公式行未删、审计未写 | ✅ |
| ``formula_templates.delete_template`` | ❌ 无（夹具缺模板表世界，登记在交接 spec） | ✅ |
| ``formula_settings.restore_global`` | ❌ 无（同上，需项目适配世界） | ✅ |

源码判据用 **AST** 而非文本匹配：docstring 是 ``Expr(Constant)``、``#`` 注释不进
AST，故「注释里写了 428」骗不过它（memory 铁律㉖）。判据对「删掉某个 raise 分支」
敏感 —— 这是它相对空壳的实质进步，但它**不验证运行时真的走到那条分支**，所以上表
的 ❌ 是如实标注，不是已覆盖。
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _status_of(node: ast.AST) -> str | None:
    """从 status_code 实参取状态码：字面量 428 或 status.HTTP_428_... 都认。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return str(node.value)
    if isinstance(node, ast.Attribute):
        m = re.search(r"HTTP_(\d{3})", node.attr)
        return m.group(1) if m else None
    return None


def _error_codes(node: ast.AST) -> list[str]:
    """取 detail={"error_code": "..."} 里的错误码字面量。"""
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Dict):
            for k, v in zip(sub.keys, sub.values):
                if (isinstance(k, ast.Constant) and k.value == "error_code"
                        and isinstance(v, ast.Constant)):
                    out.append(str(v.value))
    return out


def _raises_in(module_rel: str, func_name: str) -> set[tuple[str, str]]:
    """返回函数体内 raise 出的 (状态码, 错误码) 对。

    `HTTPException` 取 status_code 与 detail.error_code；自定义异常类（如
    `VersionRequired`）取 ("exc", 类名)。函数必须存在且恰一处定义，否则直接失败——
    改名/挪走会让判据打红，而不是静默变成空集合（防「扫描器读出空仍全绿」，
    memory 铁律⑰）。
    """
    path = BACKEND_ROOT / module_rel
    assert path.exists(), f"模块不存在：{module_rel}"
    tree = ast.parse(path.read_text("utf-8"))
    defs = [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name]
    assert len(defs) == 1, f"{module_rel}::{func_name} 定义数应为 1，实为 {len(defs)}"
    found: set[tuple[str, str]] = set()
    for sub in ast.walk(defs[0]):
        if not isinstance(sub, ast.Raise) or sub.exc is None:
            continue
        exc = sub.exc
        if isinstance(exc, ast.Call):
            fn = exc.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name == "HTTPException":
                status = next((_status_of(kw.value) for kw in exc.keywords
                               if kw.arg == "status_code"), None)
                for code in _error_codes(exc) or ["-"]:
                    found.add((status or "?", code))
            else:
                found.add(("exc", name))
        elif isinstance(exc, ast.Name):
            found.add(("exc", exc.id))
    assert found, f"{module_rel}::{func_name} 未解析出任何 raise —— 判据不得为空转"
    return found


def _params_of(module_rel: str, func_name: str) -> list[str]:
    path = BACKEND_ROOT / module_rel
    tree = ast.parse(path.read_text("utf-8"))
    defs = [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name]
    assert len(defs) == 1, f"{module_rel}::{func_name} 定义数应为 1，实为 {len(defs)}"
    a = defs[0].args
    return [x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs)]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 三个 DELETE 端点的 CAS 分支（源码级，AST）
# ═══════════════════════════════════════════════════════════════════════════════

_WP = "app/routers/wp_formula.py"
_TPL = "app/routers/formula_templates.py"
_SET = "app/routers/formula_settings.py"
_OPS = "app/services/formula_settings/project_ops.py"


class TestDeleteCasBranchesExist:
    """每个端点都有「缺版本」与「版本不符」两条拒绝分支。

    取值按现读实证（`tmp_fhic/probe_delete_raises.py`），不按文档措辞推断：
    wp_formula 与 templates 是 428/409，overrides 路由是 428/422（个数不等），
    其版本不符由 service 层 `VersionConflict` 承担。
    """

    def test_wp_formula_delete_rejects_missing_and_stale_version(self):
        raises = _raises_in(_WP, "delete_formula")
        assert ("428", "FORMULA_VERSION_REQUIRED") in raises
        assert ("409", "FORMULA_VERSION_CONFLICT") in raises

    def test_template_delete_rejects_missing_and_stale_version(self):
        raises = _raises_in(_TPL, "delete_template")
        assert ("428", "FORMULA_VERSION_REQUIRED") in raises
        assert ("409", "FORMULA_VERSION_CONFLICT") in raises

    def test_overrides_delete_rejects_missing_version_and_count_mismatch(self):
        raises = _raises_in(_SET, "restore_global")
        assert ("428", "FORMULA_VERSION_REQUIRED") in raises
        assert ("422", "FORMULA_SETTING_INVALID") in raises

    def test_restore_global_service_raises_version_errors(self):
        raises = _raises_in(_OPS, "restore_global")
        assert ("exc", "VersionRequired") in raises
        assert ("exc", "VersionConflict") in raises

    def test_helper_is_not_blind(self):
        """反向断言：helper 不是「什么都认」——不存在的错误码必须不在集合里。"""
        raises = _raises_in(_WP, "delete_formula")
        assert ("428", "NO_SUCH_ERROR_CODE") not in raises
        assert ("999", "FORMULA_VERSION_REQUIRED") not in raises

    def test_helper_fails_loudly_on_missing_function(self):
        """反向断言：函数改名/挪走时判据打红，而不是静默读出空集合。"""
        with pytest.raises(AssertionError, match="定义数应为 1"):
            _raises_in(_WP, "delete_formula_that_does_not_exist")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 端点签名守卫：三个 DELETE 端点的 expected_version 参数存在
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeleteEndpointSignatures:
    """`inspect` 级：三个删除端点与 service 都有 expected_version(s) 参数。"""

    def test_wp_formula_delete_has_expected_version_param(self):
        import inspect

        from app.routers.wp_formula import delete_formula
        assert "expected_version" in inspect.signature(delete_formula).parameters

    def test_template_delete_has_expected_version_param(self):
        import inspect

        from app.routers.formula_templates import delete_template
        assert "expected_version" in inspect.signature(delete_template).parameters

    def test_overrides_delete_has_expected_version_param(self):
        import inspect

        from app.routers.formula_settings import restore_global
        assert "expected_version" in inspect.signature(restore_global).parameters

    def test_restore_global_service_has_expected_versions_param(self):
        import inspect

        from app.services.formula_settings.project_ops import restore_global
        assert "expected_versions" in inspect.signature(restore_global).parameters

    def test_signature_source_matches_ast(self):
        """AST 取到的参数名与 inspect 一致（两条通路互相对账）。"""
        import inspect

        from app.routers.wp_formula import delete_formula
        live = set(inspect.signature(delete_formula).parameters)
        assert set(_params_of(_WP, "delete_formula")) == live


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 行为覆盖落点（防「以为这里覆盖了」）
# ═══════════════════════════════════════════════════════════════════════════════


class TestBehaviourCoverageIsDeclaredElsewhere:
    """wp_formula 删除 CAS 的行为判据在另一个文件里，这里钉住它真的存在。"""

    def test_wp_formula_behaviour_tests_exist(self):
        path = (BACKEND_ROOT / "tests/formula_management/"
                "test_task_5_4_batch_cas_audit.py")
        assert path.exists(), "行为判据文件不存在"
        src = path.read_text("utf-8")
        tree = ast.parse(src)
        names = {n.name for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert "test_delete_without_expected_version_returns_428_and_keeps_row" in names
        assert "test_delete_with_wrong_expected_version_returns_409_and_keeps_row" in names
        assert "?expected_version=1" in src, "正向删除用例必须带版本号"
