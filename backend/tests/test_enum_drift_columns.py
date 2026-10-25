"""离线守卫：枚举漂移按「列」判定（spec migration-integrity-and-enum-drift-closure Requirement 4 / 5）。

旧 ``_diff_enums`` 的三处缺陷各有一例（①按类名猜类型名 ②比较 ``.value`` 而非 SQLAlchemy 实际发送的
成员名 ③标签不限 schema），外加两个旧误报样本（confirmation_risk_level_enum / workpaper_task_status_enum
—— 库里存的正是成员名）与两个真缺口（gt_wp_coding.wp_type / workpaper_review_records.review_status）。
真库侧见 ``test_migration_integrity_pg.py``。
"""
from __future__ import annotations

import enum
from collections import defaultdict

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.schema_drift_detector import (
    CRITICAL_DRIFT_TYPES,
    OrmEnumColumn,
    SchemaDriftDetector,
    collect_orm_enum_columns,
    diff_enum_columns,
)

PUBLIC_ENUM = ("USER-DEFINED", "public")


class RiskLevel(str, enum.Enum):
    """与 ConfirmationRiskLevel 同形：成员名 ``pass_`` ≠ 值 ``pass``。"""
    high = "high"
    pass_ = "pass"


class TaskStatus(str, enum.Enum):
    """与 WorkpaperTaskStatus 同形：成员名大写、值小写。"""
    PENDING = "pending"
    FAILED = "failed"


def _metadata() -> sa.MetaData:
    md = sa.MetaData()
    sa.Table(
        "t_native", md,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("risk", sa.Enum(RiskLevel, name="risk_level_enum")),
        sa.Column("status", sa.Enum(TaskStatus, name="task_status_enum")),
        sa.Column("plain", sa.String(20)),
        sa.Column("loose", sa.Enum(TaskStatus, name="loose_enum", native_enum=False)),
    )
    sa.Table(
        "t_other_schema", md,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("risk", sa.Enum(RiskLevel, name="risk_level_enum")),
        schema="archive",
    )
    return md


def test_collect_takes_labels_sqlalchemy_actually_sends() -> None:
    """旧缺陷 ②：期望标签取 ``Enum.enums``（成员名），不是 ``.value``。"""
    cols = {(c.table, c.column): c for c in collect_orm_enum_columns(_metadata())}
    assert set(cols) == {("t_native", "risk"), ("t_native", "status")}, "只收 public 表上的原生枚举列"
    assert cols[("t_native", "risk")].labels == {"high", "pass_"}
    assert cols[("t_native", "status")].labels == {"PENDING", "FAILED"}
    assert cols[("t_native", "risk")].type_name == "risk_level_enum"


def test_member_name_labels_in_db_are_not_reported() -> None:
    """两个旧误报：库里存的就是成员名 ⇒ 不报。"""
    orm = collect_orm_enum_columns(_metadata())
    db_columns = {
        ("t_native", "risk"): (*PUBLIC_ENUM, "risk_level_enum"),
        ("t_native", "status"): (*PUBLIC_ENUM, "task_status_enum"),
    }
    db_enums = {"risk_level_enum": frozenset({"high", "pass_"}),
                "task_status_enum": frozenset({"PENDING", "FAILED"})}
    assert diff_enum_columns(orm, db_columns, db_enums) == []


def test_db_holding_values_instead_of_names_is_reported() -> None:
    orm = collect_orm_enum_columns(_metadata())
    db_columns = {("t_native", "status"): (*PUBLIC_ENUM, "task_status_enum")}
    items = diff_enum_columns(orm, db_columns, {"task_status_enum": frozenset({"pending", "failed"})})
    assert [(i.table, i.column, i.drift_type) for i in items] == [("t_native", "status", "enum_mismatch")]
    assert "FAILED" in items[0].detail and "PENDING" in items[0].detail


def test_type_is_resolved_per_column_not_by_class_name() -> None:
    """旧缺陷 ①：两个同名枚举类（模块里后者遮蔽前者）各自映射不同 PG 类型，按列各查各的。"""
    first = enum.Enum("ApprovalStatus", {"pending": "pending"}, type=str)
    second = enum.Enum("ApprovalStatus", {"draft": "draft", "approved": "approved"}, type=str)
    md = sa.MetaData()
    sa.Table("a", md, sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("s", sa.Enum(first, name="approval_status_enum")))
    sa.Table("b", md, sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("s", sa.Enum(second, name="review_status_enum")))
    db_columns = {("a", "s"): (*PUBLIC_ENUM, "approval_status_enum"),
                  ("b", "s"): (*PUBLIC_ENUM, "review_status_enum")}
    db_enums = {"approval_status_enum": frozenset({"pending"}),
                "review_status_enum": frozenset({"draft"})}
    items = diff_enum_columns(collect_orm_enum_columns(md), db_columns, db_enums)
    assert [(i.table, i.column) for i in items] == [("b", "s")]
    assert "approved" in items[0].detail


def test_column_typed_by_a_non_public_type_is_reported() -> None:
    """旧缺陷 ③ 的列侧：同名类型但在别的 schema，不算对上。"""
    orm = [OrmEnumColumn("t", "c", "risk_level_enum", frozenset({"high"}))]
    items = diff_enum_columns(orm, {("t", "c"): ("USER-DEFINED", "tmp_x", "risk_level_enum")},
                              {"risk_level_enum": frozenset({"high"})})
    assert [(i.table, i.column) for i in items] == [("t", "c")]


def test_native_enum_over_varchar_column_is_reported() -> None:
    """真缺口 1 同形：ORM 原生枚举、DB 列是 varchar。"""
    orm = [OrmEnumColumn("gt_wp_coding", "wp_type", "gt_wp_type", frozenset({"general"}))]
    items = diff_enum_columns(orm, {("gt_wp_coding", "wp_type"): ("character varying", "pg_catalog", "varchar")}, {})
    assert len(items) == 1 and "character varying" in items[0].detail
    assert items[0].drift_type in CRITICAL_DRIFT_TYPES


def test_missing_column_is_left_to_orm_extra() -> None:
    orm = [OrmEnumColumn("t", "c", "e", frozenset({"x"}))]
    assert diff_enum_columns(orm, {}, {"e": frozenset()}) == []


# ── 真实 ORM metadata ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def real_columns() -> list[OrmEnumColumn]:
    SchemaDriftDetector._import_all_models()
    from app.models.base import Base

    return collect_orm_enum_columns(Base.metadata)


def test_columns_sharing_a_pg_type_declare_identical_labels(real_columns) -> None:
    """真缺口 2 这一类的离线判据：同一个 PG 枚举类型只有一套标签，映射到它的所有列必须声明同一套。"""
    by_type: dict[str, dict[frozenset[str], list[str]]] = defaultdict(lambda: defaultdict(list))
    for c in real_columns:
        by_type[c.type_name][c.labels].append(f"{c.table}.{c.column}")
    conflicts = {name: {tuple(sorted(k)): v for k, v in sets.items()}
                 for name, sets in by_type.items() if len(sets) > 1}
    assert conflicts == {}


def test_review_record_shares_review_status_labels(real_columns) -> None:
    cols = {(c.table, c.column): c for c in real_columns}
    assert cols[("workpaper_review_records", "review_status")].labels == \
        cols[("risk_assessments", "review_status")].labels == {"draft", "pending_review", "approved", "rejected"}


def test_gt_wp_type_binds_as_plain_varchar(real_columns) -> None:
    """真缺口 1：原生枚举声明会让 asyncpg 渲染 ``$1::gt_wp_type``，而库里没有这个类型。"""
    from app.models.gt_coding_models import GTWpCoding

    assert ("gt_wp_coding", "wp_type") not in {(c.table, c.column) for c in real_columns}
    sql = str(sa.select(GTWpCoding.id).where(GTWpCoding.wp_type == "general")
              .compile(dialect=postgresql.asyncpg.dialect()))
    assert "gt_wp_type" not in sql, sql
