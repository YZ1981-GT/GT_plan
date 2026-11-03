"""直接读 ``business_category`` 的位置只许减少（spec trim-generation-plan-followup-optimizations R4.5）。

分类 / 场景判定的唯一入口是 ``app.services.project_classification``；本棘轮冻结迁移期仍直接读分类列的旧读者
（多为展示、AI 提示词、行业误用等历史兼容），新增读者或某文件读得更多即打红，读者减少须同步下调基线。

判据用 AST（注释 / docstring 不算）：
- 读属性 ``x.business_category``（Load 语境；写入 / 删除不算）；
- 字符串常量里出现的 ``business_category`` 词（裸 SQL 取列、``row["business_category"]``、``getattr(x, "business_category")``）。
豁免：分类解释模块本身、ORM 模型声明、请求 / 响应 schema 声明。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_APP = _BACKEND / "app"
_BASELINE = Path(__file__).with_name("business_category_reader_baseline.json")
_EXEMPT = {
    "app/services/project_classification.py",  # 唯一解释入口
    "app/models/core.py",  # ORM 列声明与 CHECK
    "app/models/audit_platform_schemas.py",  # 向导请求 / 项目响应字段声明
}
_WORD = re.compile(r"\bbusiness_category\b")


def _docstring_nodes(tree: ast.AST) -> list[ast.Constant]:
    """模块 / 类 / 函数的 docstring 常量（返回节点本身，调用方按身份比较；树存活期间节点不会被回收）。"""
    found: list[ast.Constant] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                found.append(body[0].value)
    return found


def count_readers(tree: ast.AST) -> int:
    """唯一计数口径：读属性 + 非 docstring 字符串常量里的词（扫描与自检共用这一个函数）。"""
    docstrings = _docstring_nodes(tree)
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "business_category" and isinstance(node.ctx, ast.Load):
            count += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and not any(node is d for d in docstrings):
            count += len(_WORD.findall(node.value))
    return count


def scan() -> dict[str, int]:
    out: dict[str, int] = {}
    for path in sorted(_APP.rglob("*.py")):
        rel = path.relative_to(_BACKEND).as_posix()
        if rel in _EXEMPT:
            continue
        source = path.read_bytes().decode("utf-8-sig")  # 有的历史文件带 BOM，ast.parse 不认
        if "business_category" not in source:
            continue
        count = count_readers(ast.parse(source))
        if count:
            out[rel] = count
    return out


def _baseline() -> dict[str, int]:
    return json.loads(_BASELINE.read_text(encoding="utf-8"))["readers"]


def test_direct_readers_only_shrink():
    current, baseline = scan(), _baseline()
    grown = {f: (baseline.get(f, 0), n) for f, n in current.items() if n > baseline.get(f, 0)}
    assert not grown, (
        "新增 / 增多了直接读 business_category 的代码（应改用 app.services.project_classification）："
        + "；".join(f"{f} {old}→{new}" for f, (old, new) in sorted(grown.items()))
    )
    shrunk = {f: (n, current.get(f, 0)) for f, n in baseline.items() if current.get(f, 0) < n}
    assert not shrunk, (
        "直接读者减少了，请把基线同步下调（只许减少，不留虚高额度）："
        + "；".join(f"{f} {old}→{new}" for f, (old, new) in sorted(shrunk.items()))
    )


def test_detector_sees_attribute_reads_and_sql_text_but_not_comments_or_writes():
    sample = (
        '"""模块说明里提到 business_category 不算。"""\n'
        "def f(project, row):\n"
        '    """函数说明里的 business_category 也不算。"""\n'
        "    # 注释里的 business_category 不算\n"
        "    a = project.business_category\n"
        "    project.business_category = 'C'\n"
        "    del project.business_category\n"
        "    b = row['business_category']\n"
        "    sql = f'SELECT business_category, scenario FROM projects WHERE id = {a}'\n"
        "    return a, b, sql\n"
    )
    assert count_readers(ast.parse(sample)) == 3, "读属性 1 + 下标字符串 1 + SQL 1；docstring / 注释 / 写入 / 删除不算"


def test_baseline_is_frozen_reality_not_a_loose_quota():
    """基线里的文件必须真实存在、不含豁免文件，且至少有一个读者（否则这道棘轮是空转）。"""
    baseline = _baseline()
    assert baseline, "基线为空：扫描口径失效或读者已清零（清零后应把本棘轮改成禁止任何直接读者）"
    assert not (_EXEMPT & set(baseline)), "豁免文件不应出现在基线里"
    missing = [f for f in baseline if not (_BACKEND / f).exists()]
    assert not missing, f"基线里有已不存在的文件，请删除：{missing}"
    for exempt in _EXEMPT:
        assert (_BACKEND / exempt).exists(), f"豁免文件已不存在，请从豁免名单删除：{exempt}"
