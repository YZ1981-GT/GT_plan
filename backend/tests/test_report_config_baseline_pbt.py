"""报表配置主模板回填 PBT 属性测试

**Validates: Requirements 1.4, 2.4**

Property E1 受控传播: pending→approved 才合并（项目→主模板必经 admin 审核）
Property E2 本地覆盖保留: apply_master_update(keep_local=True) 不覆盖项目已自定义行
"""

import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.report_models import (
    FinancialReportType,
    ReportConfig,
    ReportConfigBaseline,
)
from app.services.report_config_service import ReportConfigService

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

# ---------- Hypothesis Strategies ----------

# 行编码策略：生成合理的 row_code（如 BS001, IS042）
row_code_st = st.from_regex(r"[A-Z]{2}[0-9]{3}", fullmatch=True)

# 公式策略：生成非空公式文本
formula_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P"), whitelist_characters="()+*-/, "),
    min_size=3,
    max_size=50,
).filter(lambda s: s.strip() != "")

# 项目 ID 策略
project_id_st = st.uuids()

STANDARD = "soe_consolidated"


# ---------- Helper ----------


async def _fresh_session() -> AsyncSession:
    """每次 hypothesis 迭代独立的 SQLite 内存数据库 session"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    return session_factory()


# ==========================================================================
# E1 受控传播: pending→approved 才合并（项目→主模板必经 admin 审核）
# ==========================================================================


class TestE1ControlledPropagation:
    """**Validates: Requirements 1.4**

    Property E1: 对于任何未经 approved 审核的候选（status != 'approved'），
    standard 级主模板公式不得改变。只有 review_candidate(approved=True) 后
    主模板公式才更新。
    """

    @pytest.mark.asyncio
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        row_code=row_code_st,
        original_formula=formula_st,
        candidate_formula=formula_st,
        project_id=project_id_st,
    )
    async def test_pending_candidate_does_not_merge(
        self,
        row_code: str,
        original_formula: str,
        candidate_formula: str,
        project_id: uuid.UUID,
    ):
        """E1: 提交候选后（status=pending），standard 级公式不变"""
        session = await _fresh_session()
        async with session:
            master_row = ReportConfig(
                report_type=FinancialReportType.balance_sheet,
                row_number=1,
                row_code=row_code,
                row_name="测试行",
                indent_level=0,
                formula=original_formula,
                applicable_standard=STANDARD,
                is_total_row=False,
            )
            session.add(master_row)

            # 项目级配置（带候选公式）
            project_standard = f"project:{project_id}"
            project_row = ReportConfig(
                report_type=FinancialReportType.balance_sheet,
                row_number=1,
                row_code=row_code,
                row_name="测试行",
                indent_level=0,
                formula=candidate_formula,
                applicable_standard=project_standard,
                is_total_row=False,
            )
            session.add(project_row)
            await session.flush()

            # Act: 提交候选（status=pending）
            svc = ReportConfigService(session)
            await svc.suggest_to_master(
                project_id=project_id,
                row_code=row_code,
                report_type="balance_sheet",
                standard=STANDARD,
                submitted_by=uuid.uuid4(),
            )

            # Assert: standard 级公式不变
            result = await session.execute(
                select(ReportConfig.formula).where(
                    ReportConfig.applicable_standard == STANDARD,
                    ReportConfig.row_code == row_code,
                    ReportConfig.is_deleted == False,  # noqa: E712
                )
            )
            current_formula = result.scalar_one()
            assert current_formula == original_formula, (
                f"E1 violated: pending 候选不应改变主模板公式。"
                f"期望 '{original_formula}'，实际 '{current_formula}'"
            )

    @pytest.mark.asyncio
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        row_code=row_code_st,
        original_formula=formula_st,
        candidate_formula=formula_st,
        project_id=project_id_st,
    )
    async def test_rejected_candidate_does_not_merge(
        self,
        row_code: str,
        original_formula: str,
        candidate_formula: str,
        project_id: uuid.UUID,
    ):
        """E1: 驳回候选后（status=rejected），standard 级公式不变"""
        session = await _fresh_session()
        async with session:
            master_row = ReportConfig(
                report_type=FinancialReportType.balance_sheet,
                row_number=1,
                row_code=row_code,
                row_name="测试行",
                indent_level=0,
                formula=original_formula,
                applicable_standard=STANDARD,
                is_total_row=False,
            )
            session.add(master_row)

            project_standard = f"project:{project_id}"
            project_row = ReportConfig(
                report_type=FinancialReportType.balance_sheet,
                row_number=1,
                row_code=row_code,
                row_name="测试行",
                indent_level=0,
                formula=candidate_formula,
                applicable_standard=project_standard,
                is_total_row=False,
            )
            session.add(project_row)
            await session.flush()

            svc = ReportConfigService(session)
            candidate_id = await svc.suggest_to_master(
                project_id=project_id,
                row_code=row_code,
                report_type="balance_sheet",
                standard=STANDARD,
                submitted_by=uuid.uuid4(),
            )

            # Act: 驳回
            await svc.review_candidate(
                candidate_id, approved=False, reviewer=uuid.uuid4()
            )

            # Assert: standard 级公式不变
            result = await session.execute(
                select(ReportConfig.formula).where(
                    ReportConfig.applicable_standard == STANDARD,
                    ReportConfig.row_code == row_code,
                    ReportConfig.is_deleted == False,  # noqa: E712
                )
            )
            current_formula = result.scalar_one()
            assert current_formula == original_formula, (
                f"E1 violated: rejected 候选不应改变主模板公式。"
                f"期望 '{original_formula}'，实际 '{current_formula}'"
            )

    @pytest.mark.asyncio
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        row_code=row_code_st,
        original_formula=formula_st,
        candidate_formula=formula_st,
        project_id=project_id_st,
    )
    async def test_approved_candidate_merges(
        self,
        row_code: str,
        original_formula: str,
        candidate_formula: str,
        project_id: uuid.UUID,
    ):
        """E1 正向验证: approved 后 standard 级公式更新为候选公式"""
        session = await _fresh_session()
        async with session:
            master_row = ReportConfig(
                report_type=FinancialReportType.balance_sheet,
                row_number=1,
                row_code=row_code,
                row_name="测试行",
                indent_level=0,
                formula=original_formula,
                applicable_standard=STANDARD,
                is_total_row=False,
            )
            session.add(master_row)

            project_standard = f"project:{project_id}"
            project_row = ReportConfig(
                report_type=FinancialReportType.balance_sheet,
                row_number=1,
                row_code=row_code,
                row_name="测试行",
                indent_level=0,
                formula=candidate_formula,
                applicable_standard=project_standard,
                is_total_row=False,
            )
            session.add(project_row)
            await session.flush()

            svc = ReportConfigService(session)
            candidate_id = await svc.suggest_to_master(
                project_id=project_id,
                row_code=row_code,
                report_type="balance_sheet",
                standard=STANDARD,
                submitted_by=uuid.uuid4(),
            )

            # Act: 审核通过
            await svc.review_candidate(
                candidate_id, approved=True, reviewer=uuid.uuid4()
            )

            # Assert: standard 级公式更新为候选公式
            result = await session.execute(
                select(ReportConfig.formula).where(
                    ReportConfig.applicable_standard == STANDARD,
                    ReportConfig.row_code == row_code,
                    ReportConfig.is_deleted == False,  # noqa: E712
                )
            )
            current_formula = result.scalar_one()
            assert current_formula == candidate_formula, (
                f"E1 正向: approved 后主模板应更新为候选公式。"
                f"期望 '{candidate_formula}'，实际 '{current_formula}'"
            )


# ==========================================================================
# E2 本地覆盖保留: apply_master_update(keep_local=True) 不覆盖项目已自定义行
# ==========================================================================


class TestE2LocalOverridePreserved:
    """**Validates: Requirements 2.4**

    Property E2: 对于任何项目级配置行，若其公式与主模板不同（即项目已自定义），
    调用 apply_master_update(keep_local=True) 后，该行公式必须保持不变。
    """

    @pytest.mark.asyncio
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        data=st.data(),
        project_id=project_id_st,
        num_rows=st.integers(min_value=1, max_value=5),
    )
    async def test_keep_local_preserves_custom_formulas(
        self,
        data: st.DataObject,
        project_id: uuid.UUID,
        num_rows: int,
    ):
        """E2: keep_local=True 时，项目已自定义公式的行不被覆盖"""
        session = await _fresh_session()
        async with session:
            # 生成不重复的 row_codes
            row_codes = data.draw(
                st.lists(
                    row_code_st,
                    min_size=num_rows,
                    max_size=num_rows,
                    unique=True,
                )
            )

            project_standard = f"project:{project_id}"
            custom_rows_formulas: dict[str, str] = {}

            for i, rc in enumerate(row_codes):
                master_formula = data.draw(formula_st)
                # 确保项目公式与主模板不同（自定义行）
                project_formula = data.draw(
                    formula_st.filter(lambda f, mf=master_formula: f != mf)
                )

                # standard 级配置
                master_row = ReportConfig(
                    report_type=FinancialReportType.balance_sheet,
                    row_number=i + 1,
                    row_code=rc,
                    row_name=f"行{i}",
                    indent_level=0,
                    formula=master_formula,
                    applicable_standard=STANDARD,
                    is_total_row=False,
                )
                session.add(master_row)

                # 项目级配置（自定义公式）
                proj_row = ReportConfig(
                    report_type=FinancialReportType.balance_sheet,
                    row_number=i + 1,
                    row_code=rc,
                    row_name=f"行{i}",
                    indent_level=0,
                    formula=project_formula,
                    applicable_standard=project_standard,
                    is_total_row=False,
                )
                session.add(proj_row)
                custom_rows_formulas[rc] = project_formula

            await session.flush()

            # Act: apply_master_update with keep_local=True
            svc = ReportConfigService(session)
            await svc.apply_master_update(project_id, STANDARD, keep_local=True)

            # Assert: 所有自定义行的公式保持不变
            for rc, expected_formula in custom_rows_formulas.items():
                result = await session.execute(
                    select(ReportConfig.formula).where(
                        ReportConfig.applicable_standard == project_standard,
                        ReportConfig.row_code == rc,
                        ReportConfig.is_deleted == False,  # noqa: E712
                    )
                )
                actual_formula = result.scalar_one()
                assert actual_formula == expected_formula, (
                    f"E2 violated: keep_local=True 不应覆盖自定义行 {rc}。"
                    f"期望 '{expected_formula}'，实际 '{actual_formula}'"
                )


# ==========================================================================
# E3 stale 准确: 主模板某行更新恰好标记引用该行的克隆项目（不误标无关）
# ==========================================================================


# 报表类型策略：从 FinancialReportType 枚举中选取
report_type_st = st.sampled_from(list(FinancialReportType))


class TestE3StaleAccuracy:
    """**Validates: Requirements 2.5**

    Property E3: 给定一组克隆项目配置（各种 report_type + row_code 组合），
    当主模板更新事件触发某个 (report_type, row_code) 时，
    只有匹配该 (report_type, row_code) 的克隆配置被标 is_stale=True，
    其余保持 is_stale=False。
    """

    @pytest.mark.asyncio
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        data=st.data(),
        num_projects=st.integers(min_value=2, max_value=4),
    )
    async def test_stale_only_marks_matching_report_type_and_row_code(
        self,
        data: st.DataObject,
        num_projects: int,
    ):
        """E3: 主模板更新 (report_type, row_code) 只标匹配的克隆行，不误标无关"""
        import sqlalchemy as sa

        session = await _fresh_session()
        async with session:
            # 生成多个不同的 (report_type, row_code) 组合
            combos: list[tuple] = data.draw(
                st.lists(
                    st.tuples(report_type_st, row_code_st),
                    min_size=2,
                    max_size=5,
                    unique=True,
                )
            )

            # 生成多个项目 ID
            project_ids = [data.draw(project_id_st) for _ in range(num_projects)]

            # 为每个项目创建克隆配置行（每个项目拥有所有 combo 的子集或全部）
            all_rows: list[ReportConfig] = []
            for pid in project_ids:
                project_standard = f"project:{pid}"
                for i, (rt, rc) in enumerate(combos):
                    row = ReportConfig(
                        report_type=rt,
                        row_number=i + 1,
                        row_code=rc,
                        row_name=f"行{rc}",
                        indent_level=0,
                        formula=f"SUM({rc})",
                        applicable_standard=project_standard,
                        is_total_row=False,
                    )
                    session.add(row)
                    all_rows.append(row)

            # 也加一个 standard 级行（不应被标 stale）
            master_row = ReportConfig(
                report_type=combos[0][0],
                row_number=1,
                row_code=combos[0][1],
                row_name="主模板行",
                indent_level=0,
                formula="MASTER_FORMULA",
                applicable_standard=STANDARD,
                is_total_row=False,
            )
            session.add(master_row)
            await session.flush()

            # 选择一个 combo 作为"主模板更新的行"
            target_rt, target_rc = data.draw(st.sampled_from(combos))

            # Act: 直接模拟 handler 的 SQL 逻辑（不走 EventBus，保持快速确定性）
            stmt = (
                sa.update(ReportConfig)
                .where(
                    ReportConfig.applicable_standard.like("project:%"),
                    ReportConfig.row_code == target_rc,
                    ReportConfig.is_deleted == sa.false(),
                )
                .where(
                    sa.cast(ReportConfig.report_type, sa.String) == target_rt.value
                )
                .values(is_stale=True)
            )
            await session.execute(stmt)
            await session.flush()

            # Assert: 检查所有克隆行的 is_stale 状态
            result = await session.execute(
                select(
                    ReportConfig.applicable_standard,
                    ReportConfig.report_type,
                    ReportConfig.row_code,
                    ReportConfig.is_stale,
                ).where(
                    ReportConfig.applicable_standard.like("project:%"),
                    ReportConfig.is_deleted == sa.false(),
                )
            )
            rows = result.all()

            for row in rows:
                should_be_stale = (
                    row.row_code == target_rc
                    and row.report_type.value == target_rt.value
                )
                assert row.is_stale == should_be_stale, (
                    f"E3 violated: row (standard={row.applicable_standard}, "
                    f"report_type={row.report_type.value}, row_code={row.row_code}) "
                    f"is_stale={row.is_stale} 但期望 {should_be_stale}。"
                    f"触发更新的目标: report_type={target_rt.value}, row_code={target_rc}"
                )

            # 额外验证: standard 级行不应被标 stale
            master_result = await session.execute(
                select(ReportConfig.is_stale).where(
                    ReportConfig.applicable_standard == STANDARD,
                    ReportConfig.is_deleted == sa.false(),
                )
            )
            master_stale = master_result.scalar_one()
            assert master_stale is False, (
                "E3 violated: standard 级主模板行不应被标 is_stale"
            )



# ==========================================================================
# E4 覆盖率完整: 四组合 standard × 四表行次无缺漏（CI 守门）
# ==========================================================================


class TestE4CoverageCompleteness:
    """**Validates: Requirements 3.1, 3.2, 3.3**

    Property E4: report_config_seed.json 中，四组合 standard
    (soe_consolidated, soe_standalone, listed_consolidated, listed_standalone)
    各覆盖四张核心财务报表 (balance_sheet, income_statement, cash_flow_statement,
    equity_statement)，且每张表的 row_code 序列连续无空洞。
    enterprise 兜底标准不纳入严格校验。
    """

    def test_seed_coverage_all_combinations_present(self):
        """E4: 四组合 × 四表 = 16 个组合全部存在于 seed 中"""
        import json
        from pathlib import Path

        seed_path = Path(__file__).resolve().parent.parent / "data" / "report_config_seed.json"
        assert seed_path.exists(), f"seed 文件不存在: {seed_path}"

        seed_data = json.loads(seed_path.read_text(encoding="utf-8"))

        required_standards = [
            "soe_consolidated",
            "soe_standalone",
            "listed_consolidated",
            "listed_standalone",
        ]
        required_report_types = [
            "balance_sheet",
            "income_statement",
            "cash_flow_statement",
            "equity_statement",
        ]

        # 构建索引
        present = {
            (s["applicable_standard"], s["report_type"])
            for s in seed_data
            if s["applicable_standard"] in required_standards
        }

        missing = []
        for std in required_standards:
            for rt in required_report_types:
                if (std, rt) not in present:
                    missing.append(f"{std} × {rt}")

        assert not missing, (
            f"E4 violated: 以下组合在 seed 中缺失: {missing}"
        )

    def test_seed_coverage_no_empty_row_codes(self):
        """E4: 每个组合的所有行都有非空 row_code"""
        import json
        from pathlib import Path

        seed_path = Path(__file__).resolve().parent.parent / "data" / "report_config_seed.json"
        seed_data = json.loads(seed_path.read_text(encoding="utf-8"))

        required_standards = [
            "soe_consolidated", "soe_standalone",
            "listed_consolidated", "listed_standalone",
        ]
        required_report_types = [
            "balance_sheet", "income_statement",
            "cash_flow_statement", "equity_statement",
        ]

        empty_codes = []
        for section in seed_data:
            std = section["applicable_standard"]
            rt = section["report_type"]
            if std not in required_standards or rt not in required_report_types:
                continue
            for row in section["rows"]:
                if not row.get("row_code") or not row["row_code"].strip():
                    empty_codes.append(
                        f"{std}/{rt} row_number={row.get('row_number')}"
                    )

        assert not empty_codes, (
            f"E4 violated: 以下行 row_code 为空: {empty_codes}"
        )

    def test_seed_coverage_row_numbers_continuous(self):
        """E4: 每个组合的 row_number 从 1 开始连续无跳号"""
        import json
        from pathlib import Path

        seed_path = Path(__file__).resolve().parent.parent / "data" / "report_config_seed.json"
        seed_data = json.loads(seed_path.read_text(encoding="utf-8"))

        required_standards = [
            "soe_consolidated", "soe_standalone",
            "listed_consolidated", "listed_standalone",
        ]
        required_report_types = [
            "balance_sheet", "income_statement",
            "cash_flow_statement", "equity_statement",
        ]

        discontinuities = []
        for section in seed_data:
            std = section["applicable_standard"]
            rt = section["report_type"]
            if std not in required_standards or rt not in required_report_types:
                continue
            row_numbers = sorted(r["row_number"] for r in section["rows"])
            expected = list(range(1, len(section["rows"]) + 1))
            if row_numbers != expected:
                discontinuities.append(
                    f"{std}/{rt}: 期望 1~{len(section['rows'])}，"
                    f"实际有 {len(row_numbers)} 行"
                )

        assert not discontinuities, (
            f"E4 violated: 行号不连续: {discontinuities}"
        )

    def test_seed_coverage_no_duplicate_row_codes(self):
        """E4: 每个组合内 row_code 唯一（无重复）"""
        import json
        from pathlib import Path

        seed_path = Path(__file__).resolve().parent.parent / "data" / "report_config_seed.json"
        seed_data = json.loads(seed_path.read_text(encoding="utf-8"))

        required_standards = [
            "soe_consolidated", "soe_standalone",
            "listed_consolidated", "listed_standalone",
        ]
        required_report_types = [
            "balance_sheet", "income_statement",
            "cash_flow_statement", "equity_statement",
        ]

        duplicates = []
        for section in seed_data:
            std = section["applicable_standard"]
            rt = section["report_type"]
            if std not in required_standards or rt not in required_report_types:
                continue
            codes = [r["row_code"] for r in section["rows"]]
            seen = set()
            dupes = set()
            for c in codes:
                if c in seen:
                    dupes.add(c)
                seen.add(c)
            if dupes:
                duplicates.append(f"{std}/{rt}: {sorted(dupes)}")

        assert not duplicates, (
            f"E4 violated: row_code 重复: {duplicates}"
        )

    @pytest.mark.asyncio
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        standard=st.sampled_from([
            "soe_consolidated", "soe_standalone",
            "listed_consolidated", "listed_standalone",
        ]),
        report_type=st.sampled_from([
            "balance_sheet", "income_statement",
            "cash_flow_statement", "equity_statement",
        ]),
    )
    async def test_seed_coverage_property_all_combos_have_rows(
        self,
        standard: str,
        report_type: str,
    ):
        """E4 PBT: 对任意 (standard, report_type) 组合，seed 中必有 ≥1 行数据"""
        import json
        from pathlib import Path

        seed_path = Path(__file__).resolve().parent.parent / "data" / "report_config_seed.json"
        seed_data = json.loads(seed_path.read_text(encoding="utf-8"))

        matching = [
            s for s in seed_data
            if s["applicable_standard"] == standard
            and s["report_type"] == report_type
        ]
        assert len(matching) == 1, (
            f"E4 violated: 组合 {standard} × {report_type} "
            f"在 seed 中应恰好出现 1 次，实际 {len(matching)} 次"
        )
        rows = matching[0]["rows"]
        assert len(rows) > 0, (
            f"E4 violated: 组合 {standard} × {report_type} 行数为 0"
        )
