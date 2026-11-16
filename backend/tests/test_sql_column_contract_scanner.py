"""SQL 列契约扫描器的 ORM 属性映射守卫。"""

from __future__ import annotations


def test_orm_attribute_contract_uses_mapper_keys_for_reserved_column_aliases():
    from app.models.cf_verification_models import CfVerificationResult
    from scripts.check.check_sql_column_contract import _collect_orm_attributes

    attributes = _collect_orm_attributes()

    assert CfVerificationResult.__tablename__ in attributes
    assert "pass_" in attributes[CfVerificationResult.__tablename__]
    assert "pass" not in attributes[CfVerificationResult.__tablename__]


def test_physical_column_collection_still_uses_database_column_names():
    from app.models.cf_verification_models import CfVerificationResult
    from scripts.check.check_sql_column_contract import _collect_orm_columns

    columns = _collect_orm_columns()

    assert "pass" in columns[CfVerificationResult.__tablename__]
    assert "pass_" not in columns[CfVerificationResult.__tablename__]


def test_unknown_orm_attribute_remains_a_violation():
    from scripts.check.check_sql_column_contract import (
        _collect_orm_attributes,
        _collect_orm_class_to_table,
        _extract_orm_attr_refs,
    )

    refs = _extract_orm_attr_refs("select(CfVerificationResult.not_a_real_column)")
    class_to_table = _collect_orm_class_to_table()
    attributes = _collect_orm_attributes()

    assert refs == [("CfVerificationResult", "not_a_real_column", 1)]
    table = class_to_table["CfVerificationResult"]
    assert "not_a_real_column" not in attributes[table]
