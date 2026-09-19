"""契约测试：GET /g7-linkage/{project_id}/{year}/stale 端点无额外逻辑（Task 6.1）。

验证端点函数体仅委托既有 `load_linkage_stale_state`，不含任何映射/计算逻辑。
通过源码断言确保将来的修改不会悄悄向该薄端点添加业务逻辑。
"""
import ast
import inspect
import textwrap

from app.routers.consol_worksheet_data import get_g7_linkage_stale
from app.services.g7_consol_linkage_service import load_linkage_stale_state


def test_stale_endpoint_delegates_only_to_load_linkage_stale_state():
    """端点函数体应仅含一个 await 表达式调用 load_linkage_stale_state。"""
    source = inspect.getsource(get_g7_linkage_stale)
    # 去掉装饰器和缩进
    source = textwrap.dedent(source)
    tree = ast.parse(source)

    # 找到函数定义
    func_def = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_g7_linkage_stale":
            func_def = node
            break
    assert func_def is not None, "未找到 get_g7_linkage_stale 函数定义"

    # 收集函数体中所有非文档字符串/非 pass 的语句
    body_stmts = []
    for stmt in func_def.body:
        # 跳过 docstring
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, (ast.Constant, ast.Str)):
            continue
        body_stmts.append(stmt)

    # 应该只有一条 return 语句
    assert len(body_stmts) == 1, (
        f"stale 端点函数体应仅含 1 条有效语句（return await load_linkage_stale_state），"
        f"实际有 {len(body_stmts)} 条"
    )

    ret_stmt = body_stmts[0]
    assert isinstance(ret_stmt, ast.Return), "唯一语句应为 return"

    # return 的值应为 await 表达式
    await_expr = ret_stmt.value
    assert isinstance(await_expr, ast.Await), "return 值应为 await 表达式"

    # await 的表达式应为函数调用
    call = await_expr.value
    assert isinstance(call, ast.Call), "await 的内容应为函数调用"

    # 被调函数名应为 load_linkage_stale_state
    func_node = call.func
    if isinstance(func_node, ast.Name):
        func_name = func_node.id
    elif isinstance(func_node, ast.Attribute):
        func_name = func_node.attr
    else:
        func_name = ""
    assert func_name == "load_linkage_stale_state", (
        f"stale 端点应委托 load_linkage_stale_state，实际调用 {func_name}"
    )


def test_stale_endpoint_has_readonly_permission():
    """端点权限应为 readonly（从源码参数默认值验证）。"""
    source = inspect.getsource(get_g7_linkage_stale)
    # 检查 require_project_access("readonly") 出现在签名中
    assert 'require_project_access("readonly")' in source or "require_project_access('readonly')" in source, (
        "stale 端点权限应为 readonly"
    )


def test_load_linkage_stale_state_is_importable():
    """确认 load_linkage_stale_state 可正确导入且为可调用异步函数。"""
    assert callable(load_linkage_stale_state)
    assert inspect.iscoroutinefunction(load_linkage_stale_state)
