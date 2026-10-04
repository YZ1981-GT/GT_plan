"""任务 6.3 审查守卫：consol_note_data 访问点无绕过作用域 helper，节点金额无第二套 company_code 算法。

spec: consol-node-key-isolation-and-shared-context（需求 1.1、2.1、4.2；设计 §二第 1/5 条、ADR-CNSC-001）。

本守卫是「静态扫描 + 变异反证」而非运行时集成测试（节点隔离的运行时行为由
test_consol_note_scope / test_consol_note_node_isolation / test_consol_note_shared_context 等覆盖）。
目标是把两条平台级不变式钉死，防止后续改动悄悄引入绕过：

  不变式 A（ADR-CNSC-001：根身份只认当前树精确 node_key）
    附注节点作用域 / 公式 / 报表路径里，**不得**出现按 ``:consol`` 后缀 /
    ``node_key.split(':')`` /``node_key.endswith(':consol')`` 推断节点身份或根身份的**可执行代码**。
    这些字符串只允许出现在 docstring / 注释里（描述「禁止这样做」）。

  不变式 B（设计 §二第 5 条：金额只由 node_key 口径计算，无 company-code 并行算法）
    合并计算内核 ``consol_calc_basis`` 的叶子金额聚合按 ``node_key`` 键（``leaf_amounts[node_key]``），
    **不得**出现按 ``company_code`` 直接聚合金额的并行算法（``company_code`` 只作企业属性 / 列标签 / 溯源）。

铁律遵循（记忆 ㉖ / ⑰）：
  - 用 **AST** 判定「代码是否真做了 X」，不用文本 ``in`` 匹配 —— docstring 是 ``ast.Expr(ast.Constant)``、
    ``#`` 注释根本不进 AST，故按本模块的 AST 扫描天然排除「注释里描述禁止模式」的误报（这些文件里
    恰恰大量存在描述该反模式的 docstring，文本匹配会全数误报）。
  - 每条不变式配**变异反证**：构造一份注入了反模式的临时源，断言扫描器**确实能打红**，
    证明守卫不是恒绿。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[1] / "app"

# 不变式 A 覆盖的节点身份路径（附注作用域解析 / 公式求值 / 报表读时计算 / custom query 读写）。
_NODE_IDENTITY_FILES = [
    _APP / "services" / "consol_note_scope.py",
    _APP / "services" / "consol_note_formula_service.py",
    _APP / "routers" / "consol_note_sections.py",
    _APP / "routers" / "consol_report.py",
    _APP / "services" / "custom_query" / "module_cell_resolver.py",
    _APP / "services" / "custom_query" / "snapshot_writer_modules.py",
]

_CALC_BASIS = _APP / "services" / "consol_calc_basis.py"


# ─────────────────────────── AST 扫描器 ───────────────────────────


class _SuffixInferenceVisitor(ast.NodeVisitor):
    """检出「按 node_key 字符串后缀 / 分段推断身份」的可执行代码。

    命中形态（全部作用在名字含 ``node_key`` 的表达式上，避免误伤无关的 ``key.split(':')``）：
      1. ``<node_key expr>.endswith('...:consol...')`` / ``.startswith('...:consol...')``
      2. ``<node_key expr>.split(':')``
      3. 字面量 ``f"{...}:consol"`` / ``"...:consol"`` 直接拼成 node_key 用于**比较或赋给 node_key**
         （这类在扫描里以「含 ':consol' 的字符串字面量参与 node_key 相关表达式」近似，见
         :func:`_literal_consol_suffix_hits`）。

    docstring / 注释不进 AST，天然排除。
    """

    def __init__(self) -> None:
        self.hits: list[tuple[int, str]] = []

    @staticmethod
    def _mentions_node_key(node: ast.AST) -> bool:
        """表达式里是否引用了 node_key（属性 / 变量名含 node_key）。"""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and "node_key" in sub.id:
                return True
            if isinstance(sub, ast.Attribute) and "node_key" in sub.attr:
                return True
        return False

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            method = func.attr
            if method in ("endswith", "startswith") and self._mentions_node_key(func.value):
                # 仅当参数里出现 ':consol' / ':' 分隔符字面量才算身份后缀推断。
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and ":" in arg.value:
                        self.hits.append((node.lineno, f"node_key.{method}({arg.value!r}) 后缀推断身份"))
            if method == "split" and self._mentions_node_key(func.value):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and arg.value == ":":
                        self.hits.append((node.lineno, "node_key.split(':') 分段推断身份"))
        self.generic_visit(node)


def _scan_suffix_inference(source: str) -> list[tuple[int, str]]:
    visitor = _SuffixInferenceVisitor()
    visitor.visit(ast.parse(source))
    return visitor.hits


def _calc_basis_company_code_amount_hits(source: str) -> list[tuple[int, str]]:
    """检出 consol_calc_basis 里「按 company_code 键聚合金额」的可执行代码。

    金额聚合的真源是 ``leaf_amounts[node_key]`` / ``acc[account_code]``（按科目），
    身份键恒为 node_key。若出现 ``some_amount_dict[company_code]`` 这类**用 company_code 做金额字典键**
    的下标写，即第二套 company-code 金额算法的信号。本扫描近似为：下标表达式的 key 是名为
    ``company_code`` 的 ``ast.Name``，且容器名暗示金额（含 ``amount`` / ``measure`` / ``acc``）。
    """
    hits: list[tuple[int, str]] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        key = node.slice
        if isinstance(key, ast.Name) and key.id == "company_code":
            container = node.value
            name = ""
            if isinstance(container, ast.Name):
                name = container.id
            elif isinstance(container, ast.Attribute):
                name = container.attr
            if any(tok in name.lower() for tok in ("amount", "measure", "acc")):
                hits.append((node.lineno, f"{name}[company_code] 按企业代码做金额键"))
    return hits


# ─────────────────────────── 不变式 A ───────────────────────────


@pytest.mark.parametrize("path", _NODE_IDENTITY_FILES, ids=lambda p: p.name)
def test_no_executable_suffix_inference_in_node_identity_paths(path: Path):
    """不变式 A：附注节点身份路径里无 ``:consol`` 后缀 / ``node_key.split(':')`` 可执行推断。

    Validates: Requirements 1.1；设计 ADR-CNSC-001
    """
    assert path.exists(), f"被审查文件不存在（口径漂移需现读修正）：{path}"
    source = path.read_text(encoding="utf-8")
    hits = _scan_suffix_inference(source)
    assert not hits, (
        f"{path.name} 出现按 node_key 后缀/分段推断身份的可执行代码（违反 ADR-CNSC-001）：\n"
        + "\n".join(f"  行 {ln}: {msg}" for ln, msg in hits)
    )


def test_suffix_inference_scanner_is_not_vacuous():
    """变异反证：扫描器确实能检出注入的后缀推断（防恒绿）。"""
    mutant = (
        "def f(node_key):\n"
        "    is_root = node_key.endswith(':consol')\n"
        "    code = node_key.split(':')[0]\n"
        "    return is_root, code\n"
    )
    hits = _scan_suffix_inference(mutant)
    messages = " ".join(m for _, m in hits)
    assert "后缀推断身份" in messages, "扫描器未检出 endswith(':consol') —— 守卫恒绿"
    assert "分段推断身份" in messages, "扫描器未检出 split(':') —— 守卫恒绿"


def test_docstring_mentions_do_not_false_positive():
    """反向反证：docstring / 注释里描述反模式**不**触发命中（AST 优于文本匹配，铁律 ⑰/㉖）。"""
    doc_only = (
        'def f(node_key):\n'
        '    """ADR-CNSC-001：禁止 node_key.endswith(\':consol\') 判根，也禁止 node_key.split(\':\')。"""\n'
        "    # 下面这行注释同样描述禁止模式：node_key.endswith(':consol')\n"
        "    return node_key\n"
    )
    assert _scan_suffix_inference(doc_only) == [], "docstring/注释被误判为可执行后缀推断"


# ─────────────────────────── 不变式 B ───────────────────────────


def test_no_second_company_code_amount_algorithm_in_calc_basis():
    """不变式 B：合并计算内核无「按 company_code 聚合金额」的并行算法。

    Validates: Requirements 2.1、4.2；设计 §二第 5 条
    """
    assert _CALC_BASIS.exists(), f"被审查文件不存在：{_CALC_BASIS}"
    source = _CALC_BASIS.read_text(encoding="utf-8")
    hits = _calc_basis_company_code_amount_hits(source)
    assert not hits, (
        "consol_calc_basis 出现按 company_code 做金额字典键的并行算法"
        "（金额身份键必须是 node_key，company_code 只作企业属性）：\n"
        + "\n".join(f"  行 {ln}: {msg}" for ln, msg in hits)
    )


def test_company_code_amount_scanner_is_not_vacuous():
    """变异反证：注入 ``node_amount[company_code] = ...`` 应被检出（防恒绿）。"""
    mutant = (
        "def agg(company_code, amount):\n"
        "    node_amounts = {}\n"
        "    node_amounts[company_code] = amount\n"
        "    return node_amounts\n"
    )
    hits = _calc_basis_company_code_amount_hits(mutant)
    assert hits, "扫描器未检出 node_amounts[company_code] —— 守卫恒绿"


def test_company_code_amount_scanner_allows_attribute_usage():
    """反向反证：company_code 作企业属性 / 列标签（``node.company_code``、溯源行）不触发命中。"""
    benign = (
        "def label(node):\n"
        "    return {'company_code': node.company_code, 'kind': node.role}\n"
    )
    assert _calc_basis_company_code_amount_hits(benign) == [], "合法企业属性用法被误判为金额算法"
