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
MIGRATIONS_DIR = REPO_ROOT / "backend" / "migrations"
V067_PATH = MIGRATIONS_DIR / "V067__deliverable_section_state.sql"
R067_PATH = MIGRATIONS_DIR / "R067__rollback.sql"
V141_PATH = MIGRATIONS_DIR / "V141__deliverable_section_rendered_block_hash.sql"
R141_PATH = MIGRATIONS_DIR / "R141__deliverable_section_rendered_block_hash.sql"

# 后续以 ALTER TABLE ... ADD COLUMN 追加到本表的列（additive 迁移）。
# 三层一致的 DDL 侧 = V067 CREATE TABLE ∪ 全部 ALTER ADD COLUMN —— 只解析 V067
# 会把新增列误判成 orm_extra 漂移。
_ALTER_ADD_RE = re.compile(
    r"ALTER\s+TABLE\s+(?:public\.)?deliverable_section_state\s+"
    r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>[a-z_][a-z0-9_]*)\s+(?P<type>[A-Za-z]+(?:\(\d+(?:,\s*\d+)?\))?)"
    r"(?P<rest>[^;]*)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_alter_added_columns() -> dict[str, dict]:
    """扫描全部 V*.sql，收集对本表的 ADD COLUMN 声明。"""
    added: dict[str, dict] = {}
    for path in sorted(MIGRATIONS_DIR.glob("V*.sql")):
        text = path.read_text(encoding="utf-8")
        if "deliverable_section_state" not in text:
            continue
        for m in _ALTER_ADD_RE.finditer(text):
            rest = (m.group("rest") or "").upper()
            added[m.group("name").lower()] = {
                "type": m.group("type").upper(),
                "nullable": "NOT NULL" not in rest,
                "has_default": "DEFAULT" in rest,
            }
    return added


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

    # DDL 定义的列 = V067 CREATE TABLE ∪ 后续 ALTER ADD COLUMN
    ddl_text = V067_PATH.read_text(encoding="utf-8")
    ddl_columns = set(_parse_ddl_columns(ddl_text).keys())
    ddl_columns |= set(_parse_alter_added_columns().keys())

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
        "rendered_block_hash",  # V141
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
    ddl_cols.update(_parse_alter_added_columns())

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
    ddl_cols.update(_parse_alter_added_columns())

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


# ---------------------------------------------------------------------------
# V141: rendered_block_hash（Rendered_Block_Hash）三层一致
# Spec: deliverable-lineage-wiring-and-writeback-closure Task 3
# **Validates: Requirements 4.1, 12.6**
# ---------------------------------------------------------------------------


def test_v141_migration_exists_and_is_idempotent():
    """V141 存在且用 ADD COLUMN IF NOT EXISTS（幂等可重入，需求 12.6）。"""
    assert V141_PATH.exists(), f"V141 迁移文件不存在: {V141_PATH}"
    content = V141_PATH.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS rendered_block_hash" in content, (
        "V141 必须用 ADD COLUMN IF NOT EXISTS 保证幂等"
    )
    assert "deliverable_section_state" in content


def test_r141_rollback_exists_and_is_idempotent():
    assert R141_PATH.exists(), f"R141 回滚文件不存在: {R141_PATH}"
    content = R141_PATH.read_text(encoding="utf-8")
    assert "DROP COLUMN IF EXISTS rendered_block_hash" in content


def test_v141_column_is_nullable_varchar64_in_all_three_layers():
    """DDL / ORM / service 三层一致：VARCHAR(64) 且可空。

    可空是语义要求（需求 4.4）：存量交付件无此值 → 人工编辑检测 fail-open。
    """
    from app.models.audit_platform_models import DeliverableSectionState

    added = _parse_alter_added_columns()
    assert "rendered_block_hash" in added, "V141 的 ADD COLUMN 未被解析到"
    assert added["rendered_block_hash"]["type"] == "VARCHAR(64)"
    assert added["rendered_block_hash"]["nullable"] is True

    col = DeliverableSectionState.__table__.columns["rendered_block_hash"]
    assert _normalize_sa_type(col.type) == "VARCHAR(64)"
    assert col.nullable is True


def test_v141_version_number_not_reused():
    """铁律：迁移版本号永不复用 —— V141 只能有一个文件。"""
    matches = sorted(MIGRATIONS_DIR.glob("V141__*.sql"))
    assert len(matches) == 1, f"V141 版本号被复用: {[m.name for m in matches]}"


def test_rendered_block_hash_domain_differs_from_snapshot_hash():
    """反向自检：两列语义不可互换。

    历史缺陷是拿 `source_snapshot_hash`（源数据域）去比块内文字哈希 ⇒ 永远不等。
    本断言钉住「计算入口是 block_text_hash 而非 compute_snapshot_hash_from_parts」，
    防后来者又把它们混用。
    """
    from app.services.deliverable_section_state_service import (
        compute_snapshot_hash_from_parts,
    )
    from app.services.section_anchor_utils import block_text_hash

    # 同一段文字，两个函数必须给出不同结果（哈希域不同）
    from docx import Document

    doc = Document()
    doc.add_paragraph("甲")
    block_hash = block_text_hash(list(doc.element.body))
    snapshot_hash = compute_snapshot_hash_from_parts(
        section_code="八、1",
        text_content="甲",
        table_data=None,
        audited_amounts=[],
    )
    assert block_hash != snapshot_hash
