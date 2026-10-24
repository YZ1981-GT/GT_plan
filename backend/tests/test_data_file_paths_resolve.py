"""生产代码按 ``Path(__file__)`` 拼出来的数据文件路径必须真的存在。

起因（spec formula-fetch-followup-defect-closure R1.6）：调整到达通知按 ``parent.parent / "data"`` 读映射表，落在
``backend/app/data/``（文件在 ``backend/data/``），读不到就被 ``except`` 吞掉 —— 功能从上线起就没生效过，界面与日志都看不出来。
这一类缺陷只有「把路径真算出来看文件在不在」才抓得到。

判据：``backend/app`` 里所有 ``<路径表达式> / "<文件名>.<json|yaml|yml|txt|csv|xlsx|md>"`` 形态（含模块级常量），
只要路径能静态求值（``Path(__file__)`` / ``.resolve()`` / ``.parent`` / ``.parents[N]`` / 模块级变量 / ``/`` 拼接），
算出来的文件就必须存在；故意可缺的逐条登记理由（只许减少，登记了却已存在即打红）。函数体里由参数拼出的路径不在此列。
"""
from __future__ import annotations

import ast
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "app"
_SUFFIXES = ("json", "yaml", "yml", "txt", "csv", "xlsx", "md")

#: 故意可缺的路径（相对 backend/app 的模块, 相对仓库根的目标）→ 理由
KNOWN_MISSING: dict[tuple[str, str], str] = {
    ("core/build_version.py", "backend/app/_build_version.json"):
        "打包时生成的版本文件；开发环境不存在，代码有兜底值",
    ("services/workpaper_sync/capacity_profile.py",
     ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/requirements.md"):
        "先找在用路径、找不到再找归档目录（_requirements_path）；spec 已归档",
    ("services/ledger_import/identifier.py", "data/ledger_recognition_rules.json"):
        "🔴 已登记未修（design §10.3）：parents[4] 多上了一层，账套识别规则 JSON 从未加载、一直用内置默认；"
        "且该 JSON 已比内置旧（缺 aux_dimensions 别名），直接改路径会让辅助核算列识别退化 —— 需先同步 JSON 或删掉 JSON 改内置为唯一来源",
}


class _Unresolved(Exception):
    pass


def _evaluate(node: ast.AST, env: dict[str, ast.AST], here: Path, depth: int = 0):
    if depth > 20:
        raise _Unresolved("too deep")
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        if node.id == "__file__":
            return here
        if node.id in env:
            return _evaluate(env[node.id], env, here, depth + 1)
        raise _Unresolved(node.id)
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name) and f.id in ("Path", "_Path", "PurePath") and len(node.args) == 1:
            return Path(_evaluate(node.args[0], env, here, depth + 1))
        if isinstance(f, ast.Attribute) and f.attr in ("resolve", "absolute") and not node.args:
            return _evaluate(f.value, env, here, depth + 1)
        raise _Unresolved(ast.unparse(node)[:60])
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        return _evaluate(node.value, env, here, depth + 1).parent
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents" \
            and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
        return _evaluate(node.value.value, env, here, depth + 1).parents[node.slice.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _evaluate(node.left, env, here, depth + 1)
        if not isinstance(left, Path):
            raise _Unresolved("left operand is not a path")
        return left / _evaluate(node.right, env, here, depth + 1)
    raise _Unresolved(type(node).__name__)


def resolved_data_paths(source: str, module_path: Path) -> list[tuple[int, Path]]:
    """模块里能静态求值的数据文件路径：[(行号, 绝对路径)]。"""
    tree = ast.parse(source)
    env: dict[str, ast.AST] = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            env[n.targets[0].id] = n.value
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
            env[n.target.id] = n.value
    out: list[tuple[int, Path]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant)):
            continue
        name = node.right.value
        if not (isinstance(name, str) and "." in name and name.rsplit(".", 1)[-1] in _SUFFIXES):
            continue
        try:
            target = _evaluate(node, env, module_path)
        except (_Unresolved, IndexError):
            continue
        out.append((node.lineno, Path(target)))
    return out


def _repo_root() -> Path:
    return _APP.parents[1]


def _scan() -> tuple[list[str], set[tuple[str, str]], int]:
    missing: list[str] = []
    seen_known: set[tuple[str, str]] = set()
    checked = 0
    root = _repo_root()
    for module in sorted(_APP.rglob("*.py")):
        source = module.read_text(encoding="utf-8-sig")
        if "__file__" not in source:
            continue
        rel_module = module.relative_to(_APP).as_posix()
        for line, target in resolved_data_paths(source, module):
            checked += 1
            if target.exists():
                continue
            try:
                rel_target = target.resolve().relative_to(root).as_posix()
            except ValueError:
                rel_target = str(target)
            key = (rel_module, rel_target)
            if key in KNOWN_MISSING:
                seen_known.add(key)
                continue
            missing.append(f"app/{rel_module}:{line} → {rel_target}")
    return missing, seen_known, checked


def test_every_resolvable_data_path_exists():
    missing, _seen, checked = _scan()
    assert checked > 100, f"只求值到 {checked} 处路径，扫描口径可能失效"
    assert missing == [], "这些路径指向不存在的文件（读不到多半被 except 吞掉）：\n" + "\n".join(missing)


def test_known_missing_entries_are_live():
    _missing, seen, _checked = _scan()
    stale = sorted(set(KNOWN_MISSING) - seen)
    assert stale == [], f"登记项已失效（文件已存在或代码已改）：删掉 {stale}"
    assert all(reason.strip() for reason in KNOWN_MISSING.values())


def test_evaluator_catches_a_wrong_parent_count():
    """自检：同一判据对「少 / 多一层 parent」都能算出不存在的路径（原调整到达通知的写法）。"""
    module = _APP / "routers" / "adjustments.py"
    wrong = 'from pathlib import Path\np = Path(__file__).resolve().parent.parent / "data" / "wp_account_mapping.json"\n'
    right = 'from pathlib import Path\np = Path(__file__).resolve().parents[2] / "data" / "wp_account_mapping.json"\n'
    (_line, wrong_path), = resolved_data_paths(wrong, module)
    (_line, right_path), = resolved_data_paths(right, module)
    assert not wrong_path.exists() and right_path.exists()
