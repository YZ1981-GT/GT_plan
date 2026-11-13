"""三码入口一致性（spec consol-group-code-entry-consistency 任务 2.5）。

同一组输入（小写 / 全角 / 首尾空格 / 非法字符 / 中间空格）分别走四个写入口：

1. 单建（project_creation_coordinator 的上级/控制方规范化）；
2. 向导保存基本信息（BasicInfoSchema before validator + normalize_group_fields + update_step）；
3. 批量预校验（batch_project_workbook.parse_row）；
4. 拖拽改上级（reparent_project）。

断言：通过与否一致、入库值相同（规范化后的形态）、报错文案统一为 ``"{字段}：{原因}"``；
向导把企业代码改成同年度同口径已有代码 ⇒ 409。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from types import SimpleNamespace
from uuid import uuid4

from app.models.audit_platform_schemas import BasicInfoSchema, WizardStep
from app.models.base import Base, UserRole
from app.models.core import Project
from app.services import project_wizard_service as svc
from app.services.batch_project_workbook import parse_row
from app.services.group_links import normalize_group_fields, reparent_project
from app.services.project_creation_coordinator import create_project_for_actor

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

GROUP_CODE = "91110000100000000R"
PARENT_CODE = "911100002000000005"
CHILD_CODE = "91110000300000000G"
OTHER_CODE = "91110000710931130E"
INVALID_CODE = "91110000I109304510"  # 18 位但含 I（字符集外）→ USCC 校验必拒


def _admin_actor() -> SimpleNamespace:
    """真实 coordinator 链路需要 UserRole 枚举值，admin 走建项授权直通。"""
    return SimpleNamespace(id=uuid4(), role=UserRole.admin)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _info(**overrides) -> BasicInfoSchema:
    base = {
        "client_name": "测试子公司有限公司",
        "audit_year": 2025,
        "project_type": "annual",
        "accounting_standard": "enterprise",
        "company_code": CHILD_CODE,
        "short_name": "测试子公司",
        "report_scope": "standalone",
    }
    base.update(overrides)
    return BasicInfoSchema(**base)


async def _get(db: AsyncSession, project_id) -> Project:
    return (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()


# ───────────────────── 一致性矩阵：同一输入四入口同结论 ─────────────────────

# (名称, parent输入, 规范化后期望, 应通过)
PARENT_INPUT_CASES = [
    ("小写", PARENT_CODE.lower(), PARENT_CODE, True),
    ("全角", "９１１１００００２００００００００５", PARENT_CODE, True),
    ("首尾空格", f"  {PARENT_CODE} ", PARENT_CODE, True),
    ("非法字符", INVALID_CODE, INVALID_CODE, False),
    ("中间空格", PARENT_CODE[:9] + " " + PARENT_CODE[10:], None, False),
]


class TestNormalizeGroupFieldsConsistency:
    """normalize_group_fields：上级/控制方先规范化再校验、写回规范值。"""

    @pytest.mark.parametrize("name,raw,expected,should_pass", PARENT_INPUT_CASES)
    def test_parent_code_entries(self, name, raw, expected, should_pass):
        data = _info(parent_company_code=raw)
        if should_pass:
            normalize_group_fields(data)
            assert data.parent_company_code == expected
        else:
            with pytest.raises(HTTPException) as exc_info:
                normalize_group_fields(data)
            assert exc_info.value.status_code == 422
            detail = str(exc_info.value.detail)
            assert detail.startswith("上级企业代码："), f"文案须为「{{字段}}：{{原因}}」，得到 {detail}"

    def test_ultimate_code_normalized_and_written_back(self):
        data = _info(ultimate_company_code=f"  {GROUP_CODE.lower()} ")
        normalize_group_fields(data)
        assert data.ultimate_company_code == GROUP_CODE

    def test_empty_string_parent_becomes_none(self):
        data = _info(parent_company_code="   ")
        normalize_group_fields(data)
        assert data.parent_company_code is None


class TestBatchParseRowConsistency:
    """批量 parse_row：规范化后校验；文案与其他入口一致。"""

    @staticmethod
    def _row(parent: str = "", company: str = CHILD_CODE) -> list:
        row = ["测试公司", company, "简称", 2025, "年报审计", "企业会计准则", "单户",
               parent, "", "", "新建", "", ""]
        return row

    @pytest.mark.parametrize("name,raw,expected,should_pass", PARENT_INPUT_CASES)
    def test_parent_code_entries(self, name, raw, expected, should_pass):
        parsed, errors = parse_row(self._row(parent=raw))
        if should_pass:
            assert not [e for e in errors if e.startswith("上级企业代码")]
            assert parsed.parent_company_code == expected
        else:
            errs = [e for e in errors if e.startswith("上级企业代码：")]
            assert errs, f"应拒绝 {name} 输入，errors={errors}"
            # 文案与其他入口一致（无「格式错误：」旧形态）
            assert all(not e.startswith("上级企业代码格式错误") for e in errors)

    def test_company_code_error_has_field_label(self):
        _, errors = parse_row(self._row(company=INVALID_CODE))
        errs = [e for e in errors if e.startswith("企业代码：")]
        assert errs, "企业代码报错须带字段名"

    def test_lowercase_company_normalized(self):
        parsed, errors = parse_row(self._row(company=CHILD_CODE.lower()))
        assert not errors
        assert parsed.company_code == CHILD_CODE


class TestCreateProjectStoresNormalized:
    """create_project：企业代码入库写规范值（R1.2）。"""

    async def test_lowercase_company_code_stored_upper(self, db):
        data = _info(company_code=f" {CHILD_CODE.lower()} ")
        project = await svc.create_project(data, db, auto_commit=False)
        assert project.company_code == CHILD_CODE

    async def test_company_code_error_has_field_label(self, db):
        data = _info(company_code=INVALID_CODE)
        with pytest.raises(HTTPException) as exc_info:
            await svc.create_project(data, db, auto_commit=False)
        assert exc_info.value.status_code == 422
        assert str(exc_info.value.detail).startswith("企业代码：")


class TestCoordinatorNormalization:
    """单建 coordinator：上级/控制方规范化后传给授权与创建（只测纯校验段，授权在 actor=None 时跳过）。"""

    @pytest.mark.parametrize("name,raw,expected,should_pass", [
        (n, r, e, p) for n, r, e, p in PARENT_INPUT_CASES
    ])
    async def test_parent_code_rejected_before_any_db_work(self, name, raw, expected, should_pass, db):
        data = _info(parent_company_code=raw)
        if not should_pass:
            with pytest.raises(HTTPException) as exc_info:
                await create_project_for_actor(data, db, actor=None)
            assert exc_info.value.status_code == 422
            assert str(exc_info.value.detail).startswith("上级企业代码：")

    async def test_valid_lowercase_parent_passes_coordinator_check(self, db):
        # coordinator 对合法输入先规范化写回 data（后续流程照常）
        data = _info(parent_company_code=PARENT_CODE.lower())
        try:
            await create_project_for_actor(data, db, actor=None)
        except HTTPException as exc:
            # actor=None 时授权跳过；后续流程可能因库存查询等失败，但不应是 422 三码错误
            assert not str(exc.detail).startswith("上级企业代码")

    async def test_invalid_company_code_rejected_with_field_label(self, db):
        data = _info(company_code=INVALID_CODE)
        with pytest.raises(HTTPException) as exc_info:
            await create_project_for_actor(data, db, actor=None)
        assert exc_info.value.status_code == 422
        assert str(exc_info.value.detail).startswith("企业代码：")


class TestReparentNormalization:
    """reparent_project：服务层收到小写代码时入库规范值。"""

    @pytest_asyncio.fixture
    async def project(self, db) -> Project:
        data = _info()
        project = await svc.create_project(data, db, auto_commit=False)
        await db.flush()
        return project

    async def test_lowercase_parent_reparented_upper(self, db, project):
        # 建一个上级项目，避免「上级未建项」只影响 notices
        parent_data = _info(
            client_name="母公司", company_code=PARENT_CODE, short_name="母",
            report_scope="standalone",
        )
        await svc.create_project(parent_data, db, auto_commit=False)
        await reparent_project(db, project, PARENT_CODE.lower())
        refreshed = await db.get(Project, project.id)
        assert refreshed.parent_company_code == PARENT_CODE

    async def test_invalid_parent_rejected_with_label(self, db, project):
        with pytest.raises(HTTPException) as exc_info:
            await reparent_project(db, project, INVALID_CODE.lower())
        assert exc_info.value.status_code == 422
        assert str(exc_info.value.detail).startswith("上级企业代码：")


class TestWizardUniqueness:
    """update_step：企业代码 / 年度 / 口径变化时判唯一（排除自身），冲突 409。"""

    @pytest_asyncio.fixture
    async def two_projects(self, db):
        first = await svc.create_project(_info(), db, auto_commit=False)
        second = await svc.create_project(
            _info(company_code=OTHER_CODE, short_name="乙"), db, auto_commit=False
        )
        await db.flush()
        return first, second

    async def test_uniqueness_checker_excludes_current_project(self, db, two_projects):
        """唯一性检查排除自身后应通过，未排除时仍能发现重复项目。"""
        first, _ = two_projects
        is_unique, error = await svc.check_uniqueness(
            first.company_code,
            first.audit_year,
            first.report_scope,
            db,
            exclude_project_id=first.id,
        )
        assert is_unique is True
        assert error is None

        is_unique, error = await svc.check_uniqueness(
            first.company_code, first.audit_year, first.report_scope, db
        )
        assert is_unique is False
        assert error == "已存在该单位该年度的单户项目"

    async def test_duplicate_company_year_scope_returns_409(self, db, two_projects):
        first, second = two_projects
        before = (second.company_code, second.audit_year, second.report_scope, second.short_name)
        data = {
            "client_name": "测试子公司有限公司",
            "audit_year": 2025,
            "project_type": "annual",
            "accounting_standard": "enterprise",
            "company_code": first.company_code,  # 与 first 同码同年同口径
            "short_name": "测试子公司",
            "report_scope": "standalone",
        }
        with pytest.raises(HTTPException) as exc_info:
            await svc.update_step(
                second.id, WizardStep.basic_info, data, db, actor=_admin_actor()
            )
        assert exc_info.value.status_code == 409
        assert "已存在该单位该年度的单户项目" == exc_info.value.detail
        after = await _get(db, second.id)
        assert (after.company_code, after.audit_year, after.report_scope, after.short_name) == before

    async def test_changed_invalid_company_code_returns_422_without_modifying_project(
        self, db, two_projects
    ):
        _, second = two_projects
        before = (second.company_code, second.audit_year, second.report_scope, second.short_name)
        data = {
            "client_name": "测试子公司有限公司",
            "audit_year": second.audit_year,
            "project_type": "annual",
            "accounting_standard": "enterprise",
            "company_code": INVALID_CODE,
            "short_name": second.short_name,
            "report_scope": second.report_scope,
        }
        with pytest.raises(HTTPException) as exc_info:
            await svc.update_step(
                second.id, WizardStep.basic_info, data, db, actor=_admin_actor()
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail.startswith("企业代码：")
        after = await _get(db, second.id)
        assert (after.company_code, after.audit_year, after.report_scope, after.short_name) == before

    async def test_duplicate_audit_year_returns_409_without_modifying_project(
        self, db, two_projects
    ):
        first, _ = two_projects
        candidate = await svc.create_project(
            _info(company_code=first.company_code, audit_year=2026, short_name="丙"),
            db,
            auto_commit=False,
        )
        await db.flush()
        before = (candidate.company_code, candidate.audit_year, candidate.report_scope, candidate.short_name)
        data = {
            "client_name": "测试子公司有限公司",
            "audit_year": first.audit_year,
            "project_type": "annual",
            "accounting_standard": "enterprise",
            "company_code": first.company_code,
            "short_name": "丙",
            "report_scope": "standalone",
        }
        with pytest.raises(HTTPException) as exc_info:
            await svc.update_step(candidate.id, WizardStep.basic_info, data, db)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "已存在该单位该年度的单户项目"
        after = await _get(db, candidate.id)
        assert (after.company_code, after.audit_year, after.report_scope, after.short_name) == before

    async def test_duplicate_report_scope_returns_409_without_modifying_project(
        self, db, two_projects
    ):
        first, _ = two_projects
        candidate = await svc.create_project(
            _info(company_code=first.company_code, report_scope="consolidated", short_name="丙"),
            db,
            auto_commit=False,
        )
        await db.flush()
        before = (candidate.company_code, candidate.audit_year, candidate.report_scope, candidate.short_name)
        data = {
            "client_name": "测试子公司有限公司",
            "audit_year": first.audit_year,
            "project_type": "annual",
            "accounting_standard": "enterprise",
            "company_code": first.company_code,
            "short_name": "丙",
            "report_scope": "standalone",
        }
        with pytest.raises(HTTPException) as exc_info:
            await svc.update_step(candidate.id, WizardStep.basic_info, data, db)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "已存在该单位该年度的单户项目"
        after = await _get(db, candidate.id)
        assert (after.company_code, after.audit_year, after.report_scope, after.short_name) == before

    async def test_unchanged_company_code_no_uniqueness_rejection(self, db, two_projects):
        """保存时三键都没变（或只改名称）⇒ 不触发唯一性检查，照常保存。"""
        first, _ = two_projects
        data = {
            "client_name": "测试子公司有限公司改名",
            "audit_year": first.audit_year,
            "project_type": "annual",
            "accounting_standard": "enterprise",
            "company_code": first.company_code,
            "short_name": "测试子公司",
            "report_scope": first.report_scope,
        }
        response = await svc.update_step(first.id, WizardStep.basic_info, data, db)
        assert response.steps[WizardStep.basic_info.value].completed

    async def test_normalized_change_only_case_still_unique_checked(self, db, two_projects):
        """只改大小写（规范化后相同）⇒ 视为未变化，不触发唯一性 409。"""
        first, _ = two_projects
        data = {
            "client_name": "测试子公司有限公司",
            "audit_year": first.audit_year,
            "project_type": "annual",
            "accounting_standard": "enterprise",
            "company_code": first.company_code.lower(),  # 规范化后与库内一致
            "short_name": "测试子公司",
            "report_scope": first.report_scope,
        }
        response = await svc.update_step(first.id, WizardStep.basic_info, data, db)
        assert response.steps[WizardStep.basic_info.value].completed
        refreshed = await _get(db, first.id)
        assert refreshed.company_code == first.company_code


class TestSchemaBeforeValidator:
    """BasicInfoSchema before validator：三码先规范化再判长度。"""

    def test_padded_18_passes_length(self):
        # 带首尾空格的 18 位代码：原实现报长度错误，现规范化后通过
        schema = BasicInfoSchema.model_validate(
            _info(company_code=f" {CHILD_CODE} ").model_dump()
        )
        assert schema.company_code == CHILD_CODE

    def test_fullwidth_digits_normalized(self):
        schema = BasicInfoSchema.model_validate(
            _info(company_code="９１１１００００３００００００００Ｇ").model_dump()
        )
        assert schema.company_code == CHILD_CODE

    def test_lowercase_parent_normalized(self):
        schema = BasicInfoSchema.model_validate(
            _info(parent_company_code=PARENT_CODE.lower()).model_dump()
        )
        assert schema.parent_company_code == PARENT_CODE

    def test_blank_parent_becomes_none(self):
        schema = BasicInfoSchema.model_validate(
            _info(parent_company_code="  ").model_dump()
        )
        assert schema.parent_company_code is None


# ───────────────────── 四入口同一输入矩阵（任务 2.5） ─────────────────────

ENTRY_INPUT_CASES = [
    ("小写", PARENT_CODE.lower(), PARENT_CODE),
    ("全角", "９１１１００００２００００００００５", PARENT_CODE),
    ("首尾空格", f"  {PARENT_CODE} ", PARENT_CODE),
    ("非法字符", INVALID_CODE, None),
    ("中间空格", PARENT_CODE[:9] + " " + PARENT_CODE[10:], None),
    ("空字符串", "", None),
    ("None 空值", None, None),
]


class TestFourEntryConsistency:
    """同一原始上级代码必须经过四个真实入口得到同一结论和存储值。

    单建调用 ``create_project_for_actor``，向导调用真实 ``update_step``，批量调用
    ``parse_row``，拖拽调用真实 ``reparent_project``。四条路径不共享测试替身，
    只在测试层把空字符串与 ``None`` 归一为同一「无上级」业务值。
    """

    @staticmethod
    def _batch_row(raw_parent) -> list:
        return [
            "测试公司", GROUP_CODE, "简称", 2025, "年报审计", "企业会计准则", "单户",
            raw_parent, "", "", "新建", "", "",
        ]

    @staticmethod
    def _wizard_data(raw_parent) -> dict:
        # 保留原始输入，交给 update_step 内部的 BasicInfoSchema 真实解析。
        data = _info().model_dump(mode="json")
        data["parent_company_code"] = raw_parent
        return data

    @staticmethod
    def _detail(exc: HTTPException) -> str:
        assert isinstance(exc.detail, str), f"三码错误应为字符串 detail，得到 {exc.detail!r}"
        return exc.detail

    async def _assert_same_parent_input_across_entries(
        self, db, name, raw_parent, expected
    ):
        """覆盖成功规范化、失败校验及空值三态，拒绝任一入口自行猜测。"""
        # 1. 单建：走完整 coordinator（授权、锁、库存准备、create_project、提交）。
        # model_construct 只用于保留 API 已进入 coordinator 前的原始字段；coordinator
        # 自己的 NFKC / strip / upper 逻辑仍由真实生产代码执行。
        single_payload = _info(company_code=GROUP_CODE).model_dump(mode="python")
        single_payload["parent_company_code"] = raw_parent
        single_data = BasicInfoSchema.model_construct(**single_payload)
        try:
            single_project = await create_project_for_actor(single_data, db, _admin_actor())
        except HTTPException as exc:
            single = (False, self._detail(exc), None)
        else:
            single = (True, None, single_project.parent_company_code or None)

        # 2. 向导：先真实创建项目，再走生产 update_step，不重写保存逻辑。
        wizard_project = await svc.create_project(
            _info(company_code=CHILD_CODE), db, auto_commit=False,
        )
        await db.flush()
        try:
            await svc.update_step(
                wizard_project.id,
                WizardStep.basic_info,
                self._wizard_data(raw_parent),
                db,
            )
        except HTTPException as exc:
            wizard = (False, self._detail(exc), None)
        else:
            saved_wizard = await _get(db, wizard_project.id)
            wizard = (True, None, saved_wizard.parent_company_code or None)

        # 3. 批量：预校验只返回 ParsedRow，不把空字符串误当成有上级。
        parsed, errors = parse_row(self._batch_row(raw_parent))
        code_errors = [error for error in errors if error.startswith("上级企业代码")]
        if code_errors:
            assert len(code_errors) == 1, f"同一字段不应产生多条错误：{errors}"
            batch = (False, code_errors[0], None)
        else:
            batch = (True, None, parsed.parent_company_code or None)

        # 4. 拖拽：真实服务层先加拓扑锁、refresh，再写两口径字段。
        drag_project = await svc.create_project(
            _info(company_code=OTHER_CODE), db, auto_commit=False,
        )
        await db.flush()
        try:
            await reparent_project(db, drag_project, raw_parent)
        except HTTPException as exc:
            drag = (False, self._detail(exc), None)
        else:
            drag = (True, None, (await _get(db, drag_project.id)).parent_company_code or None)

        results = {"单建": single, "向导": wizard, "批量": batch, "拖拽": drag}
        assert {result[0] for result in results.values()} == {expected is not None or raw_parent in ("", None)}
        if expected is None and raw_parent not in ("", None):
            details = {entry: result[1] for entry, result in results.items()}
            assert len(set(details.values())) == 1, f"四入口错误文案不一致：{details}"
            assert next(iter(details.values())).startswith("上级企业代码：")
        else:
            values = {entry: result[2] for entry, result in results.items()}
            assert values == {entry: expected for entry in results}, f"四入口入库值不一致：{values}"

    @pytest.mark.parametrize(
        "name,raw_parent,expected",
        ENTRY_INPUT_CASES,
        ids=[case[0] for case in ENTRY_INPUT_CASES],
    )
    async def test_four_entry_matrix(self, db, name, raw_parent, expected):
        await self._assert_same_parent_input_across_entries(
            db, name, raw_parent, expected,
        )
