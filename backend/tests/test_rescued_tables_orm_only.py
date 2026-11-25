"""
Spec: 平台技术债清偿（2026-11-25）——三张 rescued 表的 ORM-only 守卫

背景：`linkage_audit_log` / `seed_load_history` / `wp_review_records` 此前是
「裸 SQL 在用、无迁移、无 ORM」的幽灵表（写入/查询被 try/except 吞掉，功能
静默失效）。V275/V276 补迁移、`rescued_runtime_tables.py` 补 ORM、生产调用方
已全部改走 ORM（stale_propagation_engine / linkage_bus / template_library_mgmt /
quality_rating_service 共 6 处）。

本守卫钉住**不回退**：
1. 生产代码（backend/app/）不得再出现对三张表的裸 SQL 字符串引用
   （FROM/JOIN/INSERT INTO/UPDATE/DELETE FROM + 表名，剥离注释与 docstring 后判定，
   防 memory 铁律㉖「注释/docstring 骗过扫描器」——但**允许**字符串出现在本守卫
   自身与模型文件的注释/表名字段里）；
2. 三张表的 ORM 模型必须真实注册在 Base.metadata（防模型文件被删后守卫空转）；
3. 双向：模型文件里 `__tablename__` 必须逐值等于三张表名（模型改名=表失联）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND / "app"

TABLES = ("linkage_audit_log", "seed_load_history", "wp_review_records")
MODEL_FILE = APP_DIR / "models" / "rescued_runtime_tables.py"

# 允许出现表名字面量的文件（模型定义本体；表名字段是 ORM 声明不是裸 SQL）
_ALLOWED_FILES = {
    str(MODEL_FILE),
    # 迁移文件不在 backend/app/ 下，天然不在扫描范围
}

# 裸 SQL 形态：SQL 关键字后紧跟表名（与 test_raw_sql_schema_contract 同口径）
_SQL_REF = re.compile(
    r"(?:\bFROM\b|\bJOIN\b|\bINSERT\s+INTO\b|\bUPDATE\b|\bDELETE\s+FROM\b|\bTRUNCATE\b)\s+"
    r"(?:public\.)?(?P<name>[a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)


def _strip_comments_and_docstrings(src: str) -> str:
    """剥离 `#` 注释与模块/函数/类 docstring——判据只认**代码**里的字面量。"""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    drop: set[int] = set()
    for node in ast.walk(tree):
        # docstring = 函数/类/模块体的第一条 Expr(Constant(str))
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                for ln in range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1):
                    drop.add(ln)
    kept = [line for i, line in enumerate(lines, start=1) if i not in drop]
    out = []
    for line in kept:
        # 行内 # 注释（粗剥：字符串里的 # 不常见于 SQL 调用行，误剥无害——判据是「不得出现」）
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


def _iter_production_python():
    for py in APP_DIR.rglob("*.py"):
        rel = str(py)
        if rel in _ALLOWED_FILES:
            continue
        yield py


class TestNoRawSqlForRescuedTables:
    @pytest.mark.parametrize("table", TABLES)
    def test_no_raw_sql_reference_in_production(self, table: str) -> None:
        offenders: list[str] = []
        for py in _iter_production_python():
            src = py.read_text(encoding="utf-8", errors="replace")
            code = _strip_comments_and_docstrings(src)
            for m in _SQL_REF.finditer(code):
                if m.group("name").lower() == table:
                    rel = py.relative_to(BACKEND)
                    offenders.append(f"{rel}:{src[:m.start()].count(chr(10)) + 1}")
        assert not offenders, (
            f"表 {table} 的读写必须走 ORM（app.models.rescued_runtime_tables），"
            f"生产代码出现裸 SQL 引用：\n" + "\n".join(f"  {o}" for o in offenders)
        )


class TestModelsStillRegistered:
    def test_orm_models_registered_in_metadata(self) -> None:
        """模型文件被删/改名会让裸 SQL 回潮且无守卫可拦 —— 钉住注册状态。"""
        import importlib
        import pkgutil

        import app.models as models_pkg

        for mi in pkgutil.iter_modules(models_pkg.__path__):
            if mi.name.startswith("_"):
                continue
            try:
                importlib.import_module(f"app.models.{mi.name}")
            except Exception:
                pass
        from app.models.base import Base

        for table in TABLES:
            assert table in Base.metadata.tables, (
                f"rescued 表 {table} 的 ORM 模型未注册到 Base.metadata"
                "（models/rescued_runtime_tables.py 被删或改名？）"
            )

    @pytest.mark.parametrize("table", TABLES)
    def test_model_tablename_exact_match(self, table: str) -> None:
        """`__tablename__` 必须与迁移建表名逐值一致（模型改名=与表失联）。"""
        src = MODEL_FILE.read_text(encoding="utf-8")
        assert f'__tablename__ = "{table}"' in src, (
            f"模型文件缺少 __tablename__ = \"{table}\""
        )

    def test_denominator_real(self) -> None:
        """分母非空：模型文件必须真实存在且含三个类（防空转）。"""
        assert MODEL_FILE.is_file(), "models/rescued_runtime_tables.py 不存在"
        src = MODEL_FILE.read_text(encoding="utf-8")
        for cls in ("LinkageAuditLog", "SeedLoadHistory", "WpReviewRecord"):
            assert f"class {cls}(Base)" in src, f"缺少模型类 {cls}"
