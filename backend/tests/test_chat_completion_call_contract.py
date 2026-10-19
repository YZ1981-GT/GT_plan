"""``chat_completion`` 调用契约：第一个参数 / ``messages=`` 必须是消息列表。

2026-10-19（spec llm-ocr-local-first-routing）现场：3 处把提示词字符串当 messages 传入、1 处传了
不存在的 ``system=`` / ``user=``，每次调用都在构造请求时抛错 —— 功能恒走兜底文案，旧实现还把
这类调用方错误计入全局熔断，60 秒内拖垮全部 AI 功能。三个同名入口（``llm_client`` /
``AIService`` / ``UnifiedAIService``）签名都是 ``messages`` 在前，按同一契约扫描。
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
_FORBIDDEN_KEYWORDS = frozenset({"system", "user", "prompt", "system_prompt", "user_prompt"})


def _is_text(node: ast.AST | None) -> bool:
    """字符串常量、f-string、字符串拼接 / 格式化 —— 都不是消息列表。"""
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.BinOp):
        return _is_text(node.left) or _is_text(node.right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "format" and _is_text(node.func.value)
    return False


def _assigned_values(statements) -> dict[str, list[ast.AST]]:
    """作用域内对简单名字的赋值（含 ``+=`` 与带注解赋值）。"""
    names: dict[str, list[ast.AST]] = {}
    for statement in statements:
        for node in ast.walk(statement):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.setdefault(target.id, []).append(node.value)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
                if node.value is not None:
                    names.setdefault(node.target.id, []).append(node.value)
    return names


class _Scanner(ast.NodeVisitor):
    """按函数作用域扫描：``chat_completion(prompt)`` 里的 ``prompt`` 若在本作用域被赋成字符串也算违规
    （2026-10-19 现场三处都是这种写法 —— 只认字面量的扫描器一处都抓不到）。"""

    def __init__(self, rel: str, module: ast.Module):
        self.rel, self.calls, self.bad = rel, 0, []
        self.scopes = [_assigned_values(module.body)]

    def _scope(self, node) -> None:
        self.scopes.append(_assigned_values(node.body))
        self.generic_visit(node)
        self.scopes.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _scope

    def _is_text_value(self, node: ast.AST | None) -> bool:
        if _is_text(node):
            return True
        return isinstance(node, ast.Name) and any(_is_text(v) for v in self.scopes[-1].get(node.id, []))

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name == "chat_completion":
            self.calls += 1
            first = node.args[0] if node.args else next(
                (kw.value for kw in node.keywords if kw.arg == "messages"), None
            )
            if self._is_text_value(first):
                self.bad.append(f"{self.rel}:{node.lineno} messages 传的是字符串")
            for kw in node.keywords:
                if kw.arg in _FORBIDDEN_KEYWORDS:
                    self.bad.append(f"{self.rel}:{node.lineno} 传了不存在的参数 {kw.arg}=")
        self.generic_visit(node)


def _violations(source: str, rel: str) -> tuple[int, list[str]]:
    module = ast.parse(source)
    scanner = _Scanner(rel, module)
    scanner.visit(module)
    return scanner.calls, scanner.bad


def test_every_chat_completion_call_passes_a_message_list():
    total, problems = 0, []
    for path in sorted(APP.rglob("*.py")):
        # utf-8-sig：仓内有带 BOM 的源文件（Python 能执行，ast.parse 直接读字符串会报 U+FEFF）
        source = path.read_text(encoding="utf-8-sig")
        calls, bad = _violations(source, path.relative_to(APP.parent).as_posix())
        total += calls
        problems.extend(bad)
    # 防空转：扫描器确实看到了调用点（现算 ≥ 20 处；目录或形态变了会在这里先红）
    assert total >= 20, f"只扫到 {total} 处 chat_completion 调用"
    assert not problems, "\n".join(problems)


def test_scanner_catches_each_bad_shape():
    """双向变异：每种错误形态都要命中，正确写法一个都不能误报。"""
    bad_shapes = [
        "await chat_completion('提示词')",
        "await chat_completion(f'提示词 {x}')",
        "await chat_completion('前缀' + x)",
        "await chat_completion('模板 {}'.format(x))",
        "await chat_completion(messages=f'提示词 {x}')",
        "await llm.chat_completion(system='你是审计师', user=x)",
        "await self.ai.chat_completion(prompt=x)",
        # 现场写法：提示词先赋给局部变量再整串传入
        "prompt = f'请分析 {x}'\n    await chat_completion(prompt, temperature=0.3)",
        "prompt = '前缀'\n    prompt += x\n    await chat_completion(prompt)",
    ]
    for shape in bad_shapes:
        _, found = _violations(f"async def f():\n    {shape}\n", "synthetic.py")
        assert found, f"漏报：{shape}"
    good_shapes = [
        "await chat_completion([{'role': 'user', 'content': '提示词'}])",
        "await chat_completion(messages=[{'role': 'user', 'content': x}], max_tokens=300)",
        "await chat_completion(history)",
        "await self.ai.chat_completion(messages, model=name)",
        "prompt = f'请分析 {x}'\n    await chat_completion([{'role': 'user', 'content': prompt}])",
        "messages = [{'role': 'user', 'content': x}]\n    await chat_completion(messages)",
    ]
    for shape in good_shapes:
        calls, found = _violations(f"async def f():\n    {shape}\n", "synthetic.py")
        assert calls == 1 and not found, f"误报：{shape} → {found}"
    # 作用域隔离：别的函数里同名变量是字符串，不影响这里
    other_scope = (
        "def g():\n    prompt = '字符串'\n\n"
        "async def f(prompt):\n    await chat_completion(prompt)\n"
    )
    assert _violations(other_scope, "synthetic.py") == (1, [])
