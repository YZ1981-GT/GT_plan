"""V067 三层一致契约测试：deliverable_section_state DDL ↔ ORM 零漂移。

复用项目现有契约测试框架（test_raw_sql_schema_contract / test_raw_sql_column_contract）
的 drift detector 理念，验证：
1. DDL 声明的列集 == ORM Mapped 列集（双向无漂移）
2. 列类型匹配（UUID / INT / VARCHAR(64) / BOOLEAN / TIMESTAMPTZ）
3. 列可空性匹配
4. UniqueConstraint 名 uq_deliverable_section 存在且列正确
5. R067 回滚文件存在且包含 DROP TABLE IF EXISTS

**Validates: Requirements 4.4**（三层一致验证铁律）
"""

from __future__ import annotations

import re
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V067_PATH = REPO_ROOT / "backend" / "migrations" / "V067__deliverable_section_state.sql"
R067_PATH = REPO_ROOT / "backend" / "migrations" / "R067__rollback.sql"


# ---------------------------------------------------------------------------
# Helper: 从 DDL 解析列定义
# ---------------------------------------------------------------------------

# 匹配 CREATE TABLE 内的列定义行（排除 CONSTRAINT / CREATE INDEX 等）
_COL_DEF_RE = re.compile(
    r"^\s+(?P<name>[a-z_][a-z0-9_]*)\s+(?P<type>[A-Za-z]+(?:\(\d+(?:,\s*\d+)?\))?)"
    r"(?P<rest>.*?)$",
    re.IGNORECASE,
)


def _parse_ddl_columns(ddl_text: str) -> dict[str, dict]:
    """从 V067 DDL 文本解析列结构。

    Returns: {col_name: {"type": str, "nullable": bool, "has_default": bool}}
    """
    # 提取 CREATE TABLE ... (...) 块内容
    match = re.search(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?deliverable_section_state\s*\("
        r"(.*?)\)\s*;",
        ddl_text,
        re.DOTALL | re.IGNORECASE,
    )
    assert match, "无法从 V067 DDL 解析 CREATE TABLE deliverable_section_state 块"
    body = match.group(1)

    columns: dict[str, dict] = {}
    for line in body.split("\n"):
        line_stripped = line.strip()
        # 跳过空行、注释、CONSTRAINT 行
        if not line_stripped or line_stripped.startswith("--"):
            continue
        m = _COL_DEF_RE.match(line)
        if not m:
            continue
        name = m.group("name").lower()
        col_type = m.group("type").upper()
        rest = m.group("rest").upper() if m.group("rest") else ""

        # 判断 nullable（显式 NOT NULL → 非空；PRIMARY KEY → 非空；否则可空）
        nullable = "NOT NULL" not in rest and "PRIMARY KEY" not in rest and "PRIMARY" not in col_type

        # 判断是否有 DEFAULT
        has_default = "DEFAULT" in rest or "PRIMARY KEY" in rest

        columns[name] = {
            "type": col_type,
            "nullable": nullable,
            "has_default": has_default,
        }

    return columns


# ---------------------------------------------------------------------------
# Helper: DDL 类型 → SQLAlchemy 类型名归一化
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "UUID": "UUID",
    "INT": "INTEGER",
    "INTEGER": "INTEGER",
    "BOOLEAN": "BOOLEAN",
    "TIMESTAMPTZ": "TIMESTAMP",  # SA DateTime(timezone=True) 反射为 TIMESTAMP
    "VARCHAR(64)": "VARCHAR(64)",
}


def _normalize_ddl_type(ddl_type: str) -> str:
    """将 DDL 类型归一化为可与 SA 比较的形式。"""
    t = ddl_type.strip().upper()
    # 移除 PRIMARY KEY / NOT NULL 等后缀残留
    t = t.replace("PRIMARY", "").replace("KEY", "").strip()
    return _TYPE_MAP.get(t, t)


def _normalize_sa_type(sa_type: sa.types.TypeEngine) -> str:
    """将 SQLAlchemy 列类型归一化为可比字符串。"""
    if isinstance(sa_type, sa.dialects.postgresql.UUID):
        return "UUID"
    if isinstance(sa_type, sa.Integer):
        return "INTEGER"
    if isinstance(sa_type, sa.Boolean):
        return "BOOLEAN"
    if isinstance(sa_type, (sa.DateTime,)):
        return "TIMESTAMP"
    if isinstance(sa_type, sa.String):
        length = getattr(sa_type, "length", None)
        if length:
            return f"VARCHAR({length})"
        return "VARCHAR"
    return type(sa_type).__name__.upper()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_v067_ddl_file_exists():
    """V067 DDL 迁移文件存在。"""
    assert V067_PATH.exists(), f"V067 DDL 文件不存在: {V067_PATH}"


def test_deliverable_section_state_ddl_orm_column_set():
    """V067 三层一致: DDL 列 == ORM Mapped 列（零漂移）。"""
    from app.models.audit_platform_models import DeliverableSectionState

    table = DeliverableSectionState.__table__

    # ORM 声明的列
    orm_columns = {c.name for c in table.columns}

    # DDL 定义的列
    ddl_text = V067_PATH.read_text(encoding="utf-8")
    ddl_columns = set(_parse_ddl_columns(ddl_text).keys())

    # 双向校验
    orm_extra = orm_columns - ddl_columns
    ddl_extra = ddl_columns - orm_columns

    assert not orm_extra, f"ORM 有但 DDL 无的列（orm_extra 漂移）: {sorted(orm_extra)}"
    assert not ddl_extra, f"DDL 有但 ORM 无的列（ddl_extra 漂移）: {sorted(ddl_extra)}"

    # 预期完整列集
    expected_columns = {
        "id", "word_export_task_id", "version_no", "project_id", "year",
        "section_code", "source_snapshot_hash", "is_stale",
        "last_writeback_baseline_hash", "anchor_name",
        "created_at", "updated_at",
    }
    assert orm_columns == expected_columns, (
        f"列集不匹配预期。\n  多余: {orm_columns - expected_columns}\n  缺失: {expected_columns - orm_columns}"
    )


def test_deliverable_section_state_type_match():
    """V067 三层一致: DDL 类型 ↔ ORM 类型匹配。"""
    from app.models.audit_platform_models import DeliverableSectionState

    table = DeliverableSectionState.__table__
    ddl_text = V067_PATH.read_text(encoding="utf-8")
    ddl_cols = _parse_ddl_columns(ddl_text)

    mismatches: list[str] = []
    for col in table.columns:
        if col.name not in ddl_cols:
            continue
        ddl_norm = _normalize_ddl_type(ddl_cols[col.name]["type"])
        orm_norm = _normalize_sa_type(col.type)
        if ddl_norm != orm_norm:
            mismatches.append(
                f"  {col.name}: DDL={ddl_norm}, ORM={orm_norm}"
            )

    assert not mismatches, (
        "DDL 与 ORM 类型不一致:\n" + "\n".join(mismatches)
    )


def test_deliverable_section_state_nullability_match():
    """V067 三层一致: DDL 可空性 ↔ ORM nullable 匹配。"""
    from app.models.audit_platform_models import DeliverableSectionState

    table = DeliverableSectionState.__table__
    ddl_text = V067_PATH.read_text(encoding="utf-8")
    ddl_cols = _parse_ddl_columns(ddl_text)

    mismatches: list[str] = []
    for col in table.columns:
        if col.name not in ddl_cols:
            continue
        ddl_nullable = ddl_cols[col.name]["nullable"]
        orm_nullable = col.nullable if col.nullable is not None else True
        # primary_key 列在 SA 中 nullable=False
        if col.primary_key:
            orm_nullable = False
        if ddl_nullable != orm_nullable:
            mismatches.append(
                f"  {col.name}: DDL nullable={ddl_nullable}, ORM nullable={orm_nullable}"
            )

    assert not mismatches, (
        "DDL 与 ORM 可空性不一致:\n" + "\n".join(mismatches)
    )


def test_deliverable_section_state_unique_constraint():
    """V067 唯一约束 uq_deliverable_section 存在且列正确。"""
    from app.models.audit_platform_models import DeliverableSectionState

    table = DeliverableSectionState.__table__

    # 搜索所有 UniqueConstraint（包括在 __table_args__ 中声明的）
    uq_found = None
    for constraint in table.constraints:
        if getattr(constraint, "name", None) == "uq_deliverable_section":
            uq_found = constraint
            break

    assert uq_found is not None, (
        "UniqueConstraint 'uq_deliverable_section' 未在 ORM 中声明。"
        f"\n  已有约束: {[c.name for c in table.constraints if hasattr(c, 'name')]}"
    )

    # 验证约束列
    constraint_cols = {col.name for col in uq_found.columns}
    expected_cols = {"word_export_task_id", "section_code"}
    assert constraint_cols == expected_cols, (
        f"约束列不匹配: 实际={sorted(constraint_cols)}, 预期={sorted(expected_cols)}"
    )


def test_r067_rollback_exists_and_valid():
    """R067 回滚文件存在且包含 DROP TABLE IF EXISTS deliverable_section_state。"""
    assert R067_PATH.exists(), f"R067 回滚文件不存在: {R067_PATH}"
    content = R067_PATH.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS deliverable_section_state" in content, (
        "R067 回滚文件不包含 'DROP TABLE IF EXISTS deliverable_section_state'"
    )
