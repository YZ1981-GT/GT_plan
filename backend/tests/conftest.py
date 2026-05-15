"""Backend test environment configuration. Validates: Requirements 2.8"""
import os
from collections.abc import AsyncGenerator
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")
import fakeredis.aioredis  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401  — Phase 9: must be before collaboration_models
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401  — Phase 13: Word导出
import app.models.phase10_models  # noqa: E402, F401  — Phase 10: 批注/报告溯源（R1 QC 依赖）
import app.models.phase12_models  # noqa: E402, F401  — Phase 12: AI generation 等
import app.models.phase14_enums  # noqa: E402, F401  — Phase 14: Gate 引擎枚举
import app.models.phase14_models  # noqa: E402, F401  — Phase 14: Gate 引擎模型
import app.models.phase15_enums  # noqa: E402, F401  — Phase 15: 任务树枚举
import app.models.phase15_models  # noqa: E402, F401  — Phase 15: 任务树模型
import app.models.phase16_enums  # noqa: E402, F401  — Phase 16: 证据包枚举
import app.models.phase16_models  # noqa: E402, F401  — Phase 16: 证据包模型
import app.models.archive_models  # noqa: E402, F401  — R1 归档作业
import app.models.knowledge_models  # noqa: E402, F401
import app.models.note_trim_models  # noqa: E402, F401
import app.models.procedure_models  # noqa: E402, F401
import app.models.shared_config_models  # noqa: E402, F401
import app.models.template_library_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401  — Round 5
import app.models.related_party_models  # noqa: E402, F401  — Round 5
import app.models.independence_models  # noqa: E402, F401  — Round 5
import app.models.audit_log_models  # noqa: E402, F401
import app.models.handover_models  # noqa: E402, F401
import app.models.rotation_models  # noqa: E402, F401
import app.models.qc_rating_models  # noqa: E402, F401
import app.models.qc_case_library_models  # noqa: E402, F401
import app.models.qc_inspection_models  # noqa: E402, F401
import app.models.qc_rule_models  # noqa: E402, F401  — Round 6
import app.models.workpaper_editing_lock_models  # noqa: E402, F401  — Round 4
import app.models.wp_optimization_models  # noqa: E402, F401  — 底稿深度优化

# Stub for 'workpapers' table referenced by AI models FK
import sqlalchemy as _sa
class _WorkpaperStub(Base):
    __tablename__ = "workpapers"
    __table_args__ = {"extend_existing": True}
    id = _sa.Column(_sa.Uuid, primary_key=True)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


def pytest_collection_modifyitems(config, items):
    """Skip pg_only tests when DATABASE_URL is not PostgreSQL."""
    db_url = os.getenv("DATABASE_URL", "sqlite")
    if "postgresql" not in db_url:
        skip_pg = pytest.mark.skip(reason="requires PostgreSQL")
        for item in items:
            if "pg_only" in item.keywords:
                item.add_marker(skip_pg)


# ---------------------------------------------------------------------------
# Task 4: 模型注册完整性测试
# ---------------------------------------------------------------------------

def test_all_models_registered():
    """反射遍历 backend/app/models/ 下所有 .py，断言每个继承 Base 的模型的
    __tablename__ 已注册到 Base.metadata.tables。

    Validates: Requirements 7 AC5
    """
    import ast
    from pathlib import Path

    models_dir = Path(__file__).resolve().parent.parent / "app" / "models"
    assert models_dir.exists(), f"models dir not found: {models_dir}"

    # 收集所有 .py 文件中继承 Base 的类及其 __tablename__
    expected_tables: dict[str, str] = {}  # tablename -> "file:class"

    for py_file in sorted(models_dir.glob("*.py")):
        if py_file.name.startswith("_") or py_file.name.endswith("_schemas.py"):
            continue
        # 跳过纯枚举文件（无 ORM 模型）
        if py_file.name.endswith("_enums.py"):
            continue

        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # 检查是否继承 Base（直接或间接通过名称匹配）
            inherits_base = any(
                (isinstance(b, ast.Name) and b.id == "Base")
                or (isinstance(b, ast.Attribute) and b.attr == "Base")
                for b in node.bases
            )
            if not inherits_base:
                continue

            # 提取 __tablename__
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == "__tablename__":
                            if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                                expected_tables[item.value.value] = f"{py_file.name}:{node.name}"

    # 确保我们至少找到了一些模型（防止空集误判通过）
    assert len(expected_tables) > 10, (
        f"Only found {len(expected_tables)} models, expected many more. "
        f"Check AST parsing logic."
    )

    # 获取已注册的表名
    registered_tables = set(Base.metadata.tables.keys())

    # 断言每个模型的 __tablename__ 都已注册
    missing = {
        tbl: loc
        for tbl, loc in expected_tables.items()
        if tbl not in registered_tables
    }
    assert not missing, (
        f"以下模型的 __tablename__ 未注册到 Base.metadata.tables:\n"
        + "\n".join(f"  {tbl} (定义于 {loc})" for tbl, loc in sorted(missing.items()))
    )
