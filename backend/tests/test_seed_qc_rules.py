"""Tests for backend/scripts/seed_qc_rules.py

验证 QC 规则 seed 脚本的幂等性和数据完整性。
"""

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.models.base import Base
from app.models.qc_rule_models import QcRuleDefinition
from scripts.seed_qc_rules import SEED_RULES, seed_qc_rules

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


class TestSeedQcRules:
    """seed_qc_rules 函数测试。"""

    @pytest.mark.asyncio
    async def test_seed_inserts_all_rules(self, db_session):
        """首次 seed 应插入所有规则。"""
        inserted = await seed_qc_rules(db_session)
        assert inserted == len(SEED_RULES)

        # 验证数据库中有正确数量的规则
        result = await db_session.execute(
            select(QcRuleDefinition).where(
                QcRuleDefinition.is_deleted == False  # noqa: E712
            )
        )
        rules = result.scalars().all()
        assert len(rules) == len(SEED_RULES)

    @pytest.mark.asyncio
    async def test_seed_is_idempotent(self, db_session):
        """重复调用 seed 不应重复插入。"""
        first_count = await seed_qc_rules(db_session)
        assert first_count == len(SEED_RULES)

        second_count = await seed_qc_rules(db_session)
        assert second_count == 0

        # 总数不变
        result = await db_session.execute(
            select(QcRuleDefinition).where(
                QcRuleDefinition.is_deleted == False  # noqa: E712
            )
        )
        rules = result.scalars().all()
        assert len(rules) == len(SEED_RULES)

    @pytest.mark.asyncio
    async def test_seed_rule_codes_correct(self, db_session):
        """验证 seed 后的 rule_code 集合正确。"""
        await seed_qc_rules(db_session)

        result = await db_session.execute(
            select(QcRuleDefinition.rule_code).where(
                QcRuleDefinition.is_deleted == False  # noqa: E712
            )
        )
        codes = {row[0] for row in result.all()}

        expected_codes = {r["rule_code"] for r in SEED_RULES}
        assert codes == expected_codes

    @pytest.mark.asyncio
    async def test_seed_standard_ref_populated(self, db_session):
        """验证所有规则都有 standard_ref。"""
        await seed_qc_rules(db_session)

        result = await db_session.execute(
            select(QcRuleDefinition).where(
                QcRuleDefinition.is_deleted == False  # noqa: E712
            )
        )
        rules = result.scalars().all()

        for rule in rules:
            assert rule.standard_ref is not None, (
                f"Rule {rule.rule_code} missing standard_ref"
            )
            assert len(rule.standard_ref) > 0, (
                f"Rule {rule.rule_code} has empty standard_ref"
            )
            # 每个 ref 应有 code 和 name
            for ref in rule.standard_ref:
                assert "code" in ref, f"Rule {rule.rule_code} ref missing 'code'"
                assert "name" in ref, f"Rule {rule.rule_code} ref missing 'name'"

    @pytest.mark.asyncio
    async def test_seed_expression_type_all_python(self, db_session):
        """验证所有 seed 规则的 expression_type 都是 python 或 jsonpath。"""
        await seed_qc_rules(db_session)

        result = await db_session.execute(
            select(QcRuleDefinition).where(
                QcRuleDefinition.is_deleted == False  # noqa: E712
            )
        )
        rules = result.scalars().all()

        valid_types = {"python", "jsonpath"}
        for rule in rules:
            assert rule.expression_type in valid_types, (
                f"Rule {rule.rule_code} has expression_type={rule.expression_type}"
            )

    @pytest.mark.asyncio
    async def test_seed_all_enabled_by_default(self, db_session):
        """验证 seed 规则的启用状态正确（AL-02/04/05 为 deferred 禁用）。"""
        await seed_qc_rules(db_session)

        result = await db_session.execute(
            select(QcRuleDefinition).where(
                QcRuleDefinition.is_deleted == False  # noqa: E712
            )
        )
        rules = result.scalars().all()

        # AL-02, AL-04, AL-05 是 Python 类型 deferred 到 R6+，默认禁用
        deferred_rules = {"AL-02", "AL-04", "AL-05"}
        for rule in rules:
            if rule.rule_code in deferred_rules:
                assert rule.enabled is False, (
                    f"Rule {rule.rule_code} should be disabled (deferred to R6+)"
                )
            else:
                assert rule.enabled is True, (
                    f"Rule {rule.rule_code} should be enabled by default"
                )


class TestSeedRulesData:
    """验证 SEED_RULES 数据结构完整性（不需要 DB）。"""

    def test_all_rules_have_required_fields(self):
        """每条规则必须有所有必填字段。"""
        required_fields = [
            "rule_code", "severity", "scope", "title",
            "description", "expression_type", "expression",
        ]
        for rule in SEED_RULES:
            for field in required_fields:
                assert field in rule, (
                    f"Rule {rule.get('rule_code', '?')} missing field '{field}'"
                )

    def test_rule_codes_unique(self):
        """rule_code 不能重复。"""
        codes = [r["rule_code"] for r in SEED_RULES]
        assert len(codes) == len(set(codes))

    def test_rule_count(self):
        """应有 27 条规则（QC-01~14 + QC-19~26 + AL-01~05）。"""
        assert len(SEED_RULES) == 27

    def test_severity_values_valid(self):
        """severity 只能是 blocking/warning/info。"""
        valid = {"blocking", "warning", "info"}
        for rule in SEED_RULES:
            assert rule["severity"] in valid, (
                f"Rule {rule['rule_code']} has invalid severity: {rule['severity']}"
            )

    def test_scope_values_valid(self):
        """scope 只能是 workpaper/project/consolidation/audit_log。"""
        valid = {"workpaper", "project", "consolidation", "audit_log"}
        for rule in SEED_RULES:
            assert rule["scope"] in valid, (
                f"Rule {rule['rule_code']} has invalid scope: {rule['scope']}"
            )

    def test_expression_dotted_paths_valid(self):
        """验证所有 python 类型 expression 都是有效的 dotted path 格式。"""
        for rule in SEED_RULES:
            if rule["expression_type"] != "python":
                continue  # jsonpath 类型不需要 dotted path
            parts = rule["expression"].rsplit(".", 1)
            assert len(parts) == 2, (
                f"Rule {rule['rule_code']} expression '{rule['expression']}' "
                f"is not a valid dotted path"
            )
            module_path, class_name = parts
            assert module_path.startswith("app.services."), (
                f"Rule {rule['rule_code']} expression should start with 'app.services.'"
            )
            assert class_name[0].isupper(), (
                f"Rule {rule['rule_code']} class name '{class_name}' should be PascalCase"
            )
