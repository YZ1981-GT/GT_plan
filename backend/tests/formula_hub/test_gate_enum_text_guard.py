"""守卫：门禁 / 就绪相关枚举不得用 ``str()`` / ``f"{x}"`` / ``format()`` 取文本后去比字面量或对外输出（第 2 轮 S1）。

``GateSeverity`` / ``GateDecisionResult`` / ``GateType`` / ``CheckStatus`` 都是 ``(str, Enum)``：``str(x)`` 是
``'GateSeverity.blocking'`` 而不是 ``'blocking'``。就绪页三处（readiness_facade / partner_service / qc_dashboard_service）
曾因此 ready 恒不变 false、分组停在「通过」、标签显示原文，已改为 ``readiness_facade.enum_text``（取 ``.value``）。

扫描（AST，纯静态）：``backend/app`` 里提到门禁枚举或门禁结果（``hit_rules`` / ``GateRuleHit`` / ``gate_engine`` /
``gate_result``）的模块中，对名字含 severity / decision / gate_type / status / verdict / phase 的表达式取文本、且结果
被拿去与字符串字面量比较、作为 dict 字面量的值、作为下标 / ``.get()`` 的键、或赋给变量的地方。现存只有登记表里的条目
（逐条写明为什么不是缺陷）；新增即红。日志 / 报错文案里的 f-string 不在上述语境里，不计。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
FILE_HINT = re.compile(r"GateSeverity|GateDecisionResult|GateType|CheckStatus|GateCheckStatus|GateVerdict|GatePhase|"
                       r"hit_rules|GateRuleHit|gate_engine|gate_result")
NAME_HINT = re.compile(r"severity|decision|gate_type|status|verdict|phase", re.I)
FLAGGED_CONTEXTS = {"compare_literal", "dict_value", "mapping_key", "assign"}

#: （相对 backend/app 的文件, 函数, 取文本的源码）→ 为什么不是缺陷
ALLOWED: dict[tuple[str, str, str], str] = {
    ("services/readiness_facade.py", "_worst_status", 'f.get("severity", "info")'):
        "finding 是 dict：门禁命中的 severity 已由 _hit_to_finding 经 enum_text 取值，补充类目本就是普通字符串",
}


def _context(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    parent = parents.get(node)
    if isinstance(parent, ast.FormattedValue):
        node, parent = parent, parents.get(parent)
        if isinstance(parent, ast.JoinedStr):
            node, parent = parent, parents.get(parent)
    if isinstance(parent, ast.Compare):
        others = [o for o in (parent.left, *parent.comparators) if o is not node]
        literal = any(isinstance(o, ast.Constant) and isinstance(o.value, str) for o in others)
        return "compare_literal" if literal or any(isinstance(o, (ast.Set, ast.Tuple, ast.List)) for o in others) \
            else "compare_other"
    if isinstance(parent, ast.Dict):
        return "dict_value"
    if isinstance(parent, ast.Subscript) and parent.slice is node:
        return "mapping_key"
    if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute) and parent.func.attr == "get" \
            and parent.args and parent.args[0] is node:
        return "mapping_key"
    if isinstance(parent, ast.Assign):
        return "assign"
    return "other"


def scan_source(text: str, rel: str) -> set[tuple[str, str, str]]:
    tree = ast.parse(text)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def func_of(node: ast.AST) -> str:
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur.name
        return "<module>"

    found: set[tuple[str, str, str]] = set()
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("str", "format") \
                and node.args:
            target = node.args[0]
        elif isinstance(node, ast.FormattedValue) and node.format_spec is None and node.conversion in (-1, 115):
            target = node.value
        if target is None:
            continue
        src = ast.get_source_segment(text, target) or ""
        if NAME_HINT.search(src) and _context(node, parents) in FLAGGED_CONTEXTS:
            found.add((rel, func_of(node), src))
    return found


def scan_app() -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if FILE_HINT.search(text):
            found |= scan_source(text, path.relative_to(APP).as_posix())
    return found


def test_no_new_enum_text_comparisons_on_gate_paths():
    found = scan_app()
    assert found - set(ALLOWED) == set(), sorted(found - set(ALLOWED))
    assert set(ALLOWED) - found == set(), ("登记表有已不存在的条目（只许删）", sorted(set(ALLOWED) - found))


def test_scanner_flags_the_original_defect_shapes():
    """判据不空转：修复前就绪页的三种写法都会被扫到，日志 f-string 不会。"""
    sample = '''
def check(gate_result, h, hit):
    gate_decision = str(gate_result.decision)
    blocking = str(getattr(h, "severity", "")) == "blocking"
    finding = {"severity": str(getattr(hit, "severity", "info"))}
    logger.info(f"gate_type={hit.gate_type}")
'''
    found = {src for _rel, _func, src in scan_source("gate_result = None\n" + sample, "sample.py")}
    assert found == {"gate_result.decision", 'getattr(h, "severity", "")', 'getattr(hit, "severity", "info")'}, found
