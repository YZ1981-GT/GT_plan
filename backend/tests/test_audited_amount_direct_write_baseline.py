"""AST 守卫：试算表 audited_amount 直写站点基线 — 只许减少，新增即红。

需求 4.4（chain-closure-phase3-push-rollout Task 9）：
- ``publish_rows`` 是唯一允许写入 ``TrialBalance.audited_amount`` 的发布门。
- 其余可达的直写方改经同一函数；无调用方的直写方冻结为基线（只许减少）。
- 新增直写点即打红。

扫描口径：
  1. ORM 属性赋值：`<expr>.audited_amount = <value>` — AST ``Attribute.attr == "audited_amount"``
     且该 Attribute 是 ``Assign.targets`` 的成员。
  2. 裸 SQL 字面量：字符串常量里包含 ``SET audited_amount``（不区分大小写）。
  3. SQLAlchemy ``.values(audited_amount=...)``：关键字参数名 == ``audited_amount``。

排除：
  - ``tb_audited_writer.py`` — 统一写入器本身，是唯一合法的写入点。
  - 注释和 docstring — AST 天然排除注释；docstring 是 ``Expr(Constant)`` 不产生赋值节点，
    但 SQL 字面量在 docstring 里可能误命中 ⇒ 扫描时跳过函数体第一条语句的 ``Expr(Constant)``。
  - 测试文件（``tests/``）。

基线只许减少。往基线集合里加站点 = 绕开门控 = 本守卫打红；去掉基线站点 = 直写收口 = 本守卫保绿。
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_APP_DIR = _BACKEND / "app"

# ─── 基线：已知的 audited_amount 直写站点 ──────────────────────────────────────
# 每一项 = (相对 backend/app 的路径, 函数名, 写入形态简述)
# 去掉一项 → 守卫更绿（收口进度）；新增一项 → 守卫打红（拒绝扩散）。
_BASELINE: set[tuple[str, str]] = {
    # ── 统一重算（recalc_audited / recalc_unadjusted，Task 10 改口径后仍需写） ──
    ("services/trial_balance_service.py", "recalc_audited"),
    ("services/trial_balance_service.py", "recalc_unadjusted"),
    # ── 冻结的无调用方直写（deprecated，0 callers） ──
    ("services/n1_deferred_tax_assets_service.py", "writeback_tb"),
    ("services/n2_taxes_payable_service.py", "writeback_tb"),
    ("services/n3_deferred_tax_liabilities_service.py", "writeback_tb"),
    ("services/n4_taxes_and_surcharges_service.py", "writeback_tb"),
    # ── 公式运行时（CAS 突变适配器，execute_refresh 当前无调用方） ──
    ("services/formula_runtime/adapters/adjudication.py", "apply_many"),
    ("services/formula_runtime/adapters/adjudication.py", "restore_many"),
    # ── 公式管理审定回写（draft_refresh_orchestrator 不直接驱动 writeback_batch） ──
    ("services/formula_management/adjudication_writeback.py", "_write_audited"),
}

# 统一写入器本身 — 不计入基线（它是合法的唯一写入点）。
_ALLOWED_FILES = {
    "services/tb_audited_writer.py",
}


class _AuditedAmountWriteVisitor(ast.NodeVisitor):
    """扫描单个 Python 文件，收集所有「对 audited_amount 赋值」的站点。"""

    def __init__(self) -> None:
        self.sites: list[tuple[str, int]] = []  # (function_name, line)
        self._func_stack: list[str] = []

    # ── 函数/方法进出栈 ──
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    # ── 形态 1：ORM 属性赋值 row.audited_amount = ... ──
    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr == "audited_amount":
                fn = self._func_stack[-1] if self._func_stack else "<module>"
                self.sites.append((fn, node.lineno))
        self.generic_visit(node)

    # ── 形态 2：裸 SQL 字符串含 SET audited_amount ──
    # ── 形态 3：.values(audited_amount=...) 关键字参数 ──
    def visit_Call(self, node: ast.Call) -> None:
        # 形态 3：keyword argument
        for kw in node.keywords:
            if kw.arg == "audited_amount":
                # 排除 dataclass/dict 构造（只关心 .values() 调用）
                if isinstance(node.func, ast.Attribute) and node.func.attr == "values":
                    fn = self._func_stack[-1] if self._func_stack else "<module>"
                    self.sites.append((fn, node.lineno))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and "set audited_amount" in node.value.lower():
            # 排除 docstring：函数体的第一条语句的 Expr(Constant) 是 docstring
            parent = getattr(node, "_parent", None)
            if isinstance(parent, ast.Expr):
                grandparent = getattr(parent, "_parent", None)
                if isinstance(grandparent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                    body = grandparent.body
                    if body and body[0] is parent:
                        return  # docstring，跳过
            fn = self._func_stack[-1] if self._func_stack else "<module>"
            self.sites.append((fn, node.lineno))


def _set_parents(node: ast.AST) -> None:
    """给 AST 每个节点标注 _parent，用于 docstring 判定。"""
    for child in ast.walk(node):
        for sub in ast.iter_child_nodes(child):
            sub._parent = child  # type: ignore[attr-defined]


def _scan_file(filepath: Path) -> list[tuple[str, int]]:
    """扫描单个文件，返回 [(function_name, line), ...]。"""
    source = filepath.read_bytes().decode("utf-8-sig")
    tree = ast.parse(source, filename=str(filepath))
    _set_parents(tree)
    visitor = _AuditedAmountWriteVisitor()
    visitor.visit(tree)
    return visitor.sites


def _scan_all() -> dict[str, list[tuple[str, int]]]:
    """扫描 backend/app/ 下所有 .py 文件（排除 __pycache__）。"""
    results: dict[str, list[tuple[str, int]]] = {}
    for pyfile in sorted(_APP_DIR.rglob("*.py")):
        if "__pycache__" in pyfile.parts:
            continue
        rel = pyfile.relative_to(_APP_DIR).as_posix()
        if rel in _ALLOWED_FILES:
            continue
        sites = _scan_file(pyfile)
        if sites:
            results[rel] = sites
    return results


class TestAuditedAmountDirectWriteBaseline:
    """基线只许减少，新增即红。"""

    def test_no_new_direct_write_sites(self) -> None:
        """扫描 backend/app/ 下所有「对 audited_amount 赋值」的站点，
        与基线比对；新增站点打红（拒绝扩散）。"""
        found = _scan_all()

        found_set: set[tuple[str, str]] = set()
        for rel_path, sites in found.items():
            for func_name, _line in sites:
                found_set.add((rel_path, func_name))

        new_sites = found_set - _BASELINE
        if new_sites:
            details = "\n".join(
                f"  - {path} :: {func}" for path, func in sorted(new_sites)
            )
            pytest.fail(
                f"发现 {len(new_sites)} 个新增 audited_amount 直写站点（基线外）：\n"
                f"{details}\n\n"
                "如果这是合法的新写入方，请改用 tb_audited_writer.publish_rows()。\n"
                "如果确实需要直写（如 recalc），将其加入 _BASELINE 并说明原因。"
            )

    def test_baseline_not_inflated(self) -> None:
        """基线集合里的每一项都必须能在代码里找到；
        已收口（删除直写）的站点须从基线中移除，防止基线虚高掩盖新增。"""
        found = _scan_all()
        found_set: set[tuple[str, str]] = set()
        for rel_path, sites in found.items():
            for func_name, _line in sites:
                found_set.add((rel_path, func_name))

        stale = _BASELINE - found_set
        if stale:
            details = "\n".join(
                f"  - {path} :: {func}" for path, func in sorted(stale)
            )
            pytest.fail(
                f"基线中 {len(stale)} 项已不存在于代码中（已收口？）：\n"
                f"{details}\n\n"
                "请从 _BASELINE 中移除这些已清理的站点。"
            )

    def test_unified_writer_excluded_from_scan(self) -> None:
        """tb_audited_writer.py 是合法的统一写入器，不应出现在扫描结果中。"""
        writer_path = _APP_DIR / "services" / "tb_audited_writer.py"
        assert writer_path.exists(), "tb_audited_writer.py 不存在"
        sites = _scan_file(writer_path)
        # 统一写入器自身有 audited_amount 赋值（.values(audited_amount=...)），
        # 但扫描排除了它 ⇒ _scan_all() 不含它
        assert "services/tb_audited_writer.py" not in _scan_all()

    def test_mutation_detects_new_direct_write(self, tmp_path: Path) -> None:
        """变异证明：往 scan 范围内新增一处直写，实际基线守卫打红。"""
        fake_module = tmp_path / "services" / "fake_new_writer.py"
        fake_module.parent.mkdir()
        fake_module.write_text(textwrap.dedent("""\
            def sneaky_write(row, amount):
                row.audited_amount = amount
        """), encoding="utf-8")

        # 将真实守卫的扫描根切到变异目录，调用与生产回归相同的测试入口。
        # _BASELINE 为空表示这个目录没有已知直写；fake writer 因而必须进入新增差集。
        global _APP_DIR, _BASELINE
        original_app_dir = _APP_DIR
        original_baseline = _BASELINE
        try:
            _APP_DIR = tmp_path
            _BASELINE = set()
            with pytest.raises(pytest.fail.Exception, match="新增 audited_amount 直写站点"):
                self.test_no_new_direct_write_sites()
        finally:
            _APP_DIR = original_app_dir
            _BASELINE = original_baseline

    def test_bom_source_is_parseable(self, tmp_path: Path) -> None:
        """生产扫描范围内的 UTF-8 BOM 文件也必须能被 AST 守卫解析。"""
        bom_module = tmp_path / "bom_writer.py"
        bom_module.write_bytes(
            b"\xef\xbb\xbf"
            + textwrap.dedent("""\
                def bom_write(row, amount):
                    row.audited_amount = amount
            """).encode("utf-8")
        )

        assert _scan_file(bom_module) == [("bom_write", 2)]

    def test_mutation_detects_raw_sql_direct_write(self, tmp_path: Path) -> None:
        """变异证明：裸 SQL SET audited_amount 也能被检测到。"""
        fake_module = tmp_path / "fake_sql_writer.py"
        fake_module.write_text(textwrap.dedent("""\
            import sqlalchemy as sa

            async def raw_sql_write(db, amount, pid):
                await db.execute(
                    sa.text(
                        "UPDATE trial_balance "
                        "SET audited_amount = :amount "
                        "WHERE project_id = :pid"
                    ),
                    {"amount": amount, "pid": pid},
                )
        """), encoding="utf-8")

        sites = _scan_file(fake_module)
        assert len(sites) >= 1
        assert sites[0][0] == "raw_sql_write"

    def test_docstring_not_false_positive(self, tmp_path: Path) -> None:
        """docstring 里提到 SET audited_amount 不应误报。"""
        fake_module = tmp_path / "fake_docstring.py"
        fake_module.write_text(textwrap.dedent('''\
            async def handler(payload):
                """UPDATE trial_balance SET audited_amount = ? WHERE ...

                This is a docstring, not real code.
                """
                pass
        '''), encoding="utf-8")

        sites = _scan_file(fake_module)
        assert len(sites) == 0, f"docstring 误报: {sites}"
