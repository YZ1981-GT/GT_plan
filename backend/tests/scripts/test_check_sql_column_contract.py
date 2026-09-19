"""Tests for check_sql_column_contract.py — SQL 列契约检查脚本。

验收标准：脚本可在无 DB 连接时部分运行（allowlist + regex 提取测试）。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_allowlist_is_valid_json():
    """白名单文件是合法 JSON 且包含 allowed_references 列表。"""
    allowlist_path = Path(__file__).resolve().parents[2] / "scripts" / "check" / "sql_column_contract_allowlist.json"
    assert allowlist_path.exists(), f"allowlist not found: {allowlist_path}"

    data = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert "allowed_references" in data
    assert isinstance(data["allowed_references"], list)
    assert len(data["allowed_references"]) > 0


def test_extract_column_refs_qualified():
    """_extract_column_refs 提取 table.column 格式引用。"""
    from scripts.check.check_sql_column_contract import _extract_column_refs

    sql = "SELECT t.name, t.amount FROM trial_balance t WHERE t.project_id = :pid"
    refs = _extract_column_refs(sql)

    # Should extract t.name, t.amount, t.project_id
    assert ("t", "name") in refs
    assert ("t", "amount") in refs
    assert ("t", "project_id") in refs


def test_extract_column_refs_skips_python_patterns():
    """_extract_column_refs 跳过 Python 对象引用（self.xxx, os.path 等）。"""
    from scripts.check.check_sql_column_contract import _extract_column_refs

    sql = "self.value os.path json.dumps datetime.now"
    refs = _extract_column_refs(sql)

    assert len(refs) == 0, f"Should skip Python patterns, got: {refs}"


def test_extract_column_refs_skips_sql_functions():
    """_extract_column_refs 跳过 SQL 函数调用。"""
    from scripts.check.check_sql_column_contract import _extract_column_refs

    sql = "func.count func.sum func.now"
    refs = _extract_column_refs(sql)

    assert len(refs) == 0, f"Should skip SQL functions, got: {refs}"


def test_extract_column_refs_skips_fstring_interpolation():
    """_extract_column_refs 跳过 f-string 插值部分。"""
    from scripts.check.check_sql_column_contract import _extract_column_refs

    sql = "SELECT t.name FROM {table_name} t WHERE t.id = {some_var.value}"
    refs = _extract_column_refs(sql)

    # Should extract t.name and t.id, but NOT some_var.value (inside {})
    assert ("t", "name") in refs
    assert ("t", "id") in refs
    assert ("some_var", "value") not in refs


def test_extract_orm_attr_refs_basic():
    """_extract_orm_attr_refs 提取 Model.column 模式。"""
    from scripts.check.check_sql_column_contract import _extract_orm_attr_refs

    source = """\
from app.models.core import Project
import sqlalchemy as sa

stmt = sa.select(WorkingPaper.id, WorkingPaper.file_path)
query = stmt.where(TrialBalance.project_id == project_id)
"""
    refs = _extract_orm_attr_refs(source)

    # Should find WorkingPaper.id, WorkingPaper.file_path, TrialBalance.project_id
    class_attrs = [(cls, attr) for cls, attr, _ in refs]
    assert ("WorkingPaper", "id") in class_attrs
    assert ("WorkingPaper", "file_path") in class_attrs
    assert ("TrialBalance", "project_id") in class_attrs


def test_extract_orm_attr_refs_skips_non_orm():
    """_extract_orm_attr_refs 跳过非 ORM 类引用。"""
    from scripts.check.check_sql_column_contract import _extract_orm_attr_refs

    source = """\
from pathlib import Path
from uuid import UUID

x = Path.exists
y = UUID.hex
z = HTTPException.status_code
w = BaseModel.model_validate
"""
    refs = _extract_orm_attr_refs(source)

    class_attrs = [(cls, attr) for cls, attr, _ in refs]
    assert ("Path", "exists") not in class_attrs
    assert ("UUID", "hex") not in class_attrs
    assert ("HTTPException", "status_code") not in class_attrs


def test_extract_orm_attr_refs_skips_method_calls():
    """_extract_orm_attr_refs 跳过方法调用（后面紧跟括号）。"""
    from scripts.check.check_sql_column_contract import _extract_orm_attr_refs

    source = """\
result = Model.query()
data = Model.filter(x)
items = Model.all()
"""
    refs = _extract_orm_attr_refs(source)

    # query/filter/all are followed by ( so should be skipped
    class_attrs = [(cls, attr) for cls, attr, _ in refs]
    assert ("Model", "query") not in class_attrs
    assert ("Model", "filter") not in class_attrs
    assert ("Model", "all") not in class_attrs


def test_extract_orm_attr_refs_skips_imports():
    """_extract_orm_attr_refs 跳过 import 行。"""
    from scripts.check.check_sql_column_contract import _extract_orm_attr_refs

    source = """\
from app.models.core import Project
import app.models.WorkingPaper as WP
"""
    refs = _extract_orm_attr_refs(source)

    # Import lines should be skipped entirely
    assert len(refs) == 0


def test_extract_orm_attr_refs_skips_sqlalchemy_internals():
    """_extract_orm_attr_refs 跳过 SQLAlchemy 内部方法（.where, .order_by 等）。"""
    from scripts.check.check_sql_column_contract import _extract_orm_attr_refs

    source = """\
stmt = SomeModel.query
items = SomeModel.where
order = SomeModel.order_by
"""
    refs = _extract_orm_attr_refs(source)

    class_attrs = [(cls, attr) for cls, attr, _ in refs]
    # These are in _SKIP_ORM_ATTRS
    assert ("SomeModel", "query") not in class_attrs
    assert ("SomeModel", "where") not in class_attrs
    assert ("SomeModel", "order_by") not in class_attrs


def test_extract_sql_strings_finds_text_calls():
    """_extract_sql_strings 提取 text() 中的 SQL。"""
    from scripts.check.check_sql_column_contract import _extract_sql_strings

    source = '''
result = await db.execute(text("""
    SELECT t.name, t.amount
    FROM trial_balance t
    WHERE t.project_id = :pid
"""))
'''
    results = _extract_sql_strings(source)

    assert len(results) == 1
    sql, line_no = results[0]
    assert "SELECT" in sql
    assert "trial_balance" in sql


def test_build_alias_map():
    """_build_alias_map 从 FROM/JOIN 构建别名映射。"""
    from scripts.check.check_sql_column_contract import _build_alias_map

    sql = "SELECT t.name FROM trial_balance t JOIN projects p ON t.project_id = p.id"
    alias_map = _build_alias_map(sql)

    assert alias_map["t"] == "trial_balance"
    assert alias_map["p"] == "projects"


def test_build_alias_map_with_as():
    """_build_alias_map 处理 AS 关键字。"""
    from scripts.check.check_sql_column_contract import _build_alias_map

    sql = "SELECT t.name FROM trial_balance AS t"
    alias_map = _build_alias_map(sql)

    assert alias_map["t"] == "trial_balance"


def test_extract_orm_attr_refs_skips_docstrings():
    """_extract_orm_attr_refs 跳过 docstring 中的引用。"""
    from scripts.check.check_sql_column_contract import _extract_orm_attr_refs

    source = '''\
def my_func():
    """获取数据供 TrialBalance.vue 使用"""
    stmt = select(WorkingPaper.id)
'''
    refs = _extract_orm_attr_refs(source)

    class_attrs = [(cls, attr) for cls, attr, _ in refs]
    # WorkingPaper.id should be found (not in docstring)
    assert ("WorkingPaper", "id") in class_attrs
    # TrialBalance.vue should NOT be found (in docstring + .vue is file extension)
    assert ("TrialBalance", "vue") not in class_attrs


def test_extract_orm_attr_refs_skips_file_extensions():
    """_extract_orm_attr_refs 跳过文件扩展名引用。"""
    from scripts.check.check_sql_column_contract import _extract_orm_attr_refs

    source = """\
# Some comment
x = SomeModel.py
y = Component.vue
z = Config.json
real = WorkingPaper.file_path
"""
    refs = _extract_orm_attr_refs(source)

    class_attrs = [(cls, attr) for cls, attr, _ in refs]
    assert ("SomeModel", "py") not in class_attrs
    assert ("Component", "vue") not in class_attrs
    assert ("Config", "json") not in class_attrs
    assert ("WorkingPaper", "file_path") in class_attrs
