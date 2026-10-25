"""集团关系字段规范化与两口径同步（spec consol-tree-three-code-autobuild 任务 3）。

被测：``app.services.group_links`` + ``project_wizard_service.create_project / update_step`` 的接线。
真 SQLite + 真 ORM 行（不 mock resolver），覆盖：

- 需求 1.4：上级/控制方代码 USCC 校验 ⇒ 422 中文原因；
- 需求 1.5：上级=本企业**不拒绝**（本企业就是上级企业 / 三码相同即最终控制方），关系置空、说明只说一次；
- 需求 1.3：上级为空 ⇒ 关系强制为空；关系非法值 ⇒ 422；
- 需求 2.3 / 2.4：有上级无关系 ⇒ 按名称补默认；手选优先且保存后不被覆盖；
- 需求 1.8：建项继承同企业另一口径项目；保存外推到另一口径（ORM 列 + 向导回填数据）；
- 需求 1.9：控制方按上级**已填**值补齐；上级也没填则保持空；上级未变而清空不回填。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_schemas import BasicInfoSchema, WizardStep
from app.models.base import Base
from app.models.core import Project
from app.services import group_links
from app.services import project_wizard_service as svc

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 合法 18 位 USCC（校验位按模 31 现算，见 app.services.uscc_validator）
GROUP_CODE = "91110000100000000R"   # 集团（最终控制方）
PARENT_CODE = "911100002000000005"  # 母公司
CHILD_CODE = "91110000300000000G"   # 子公司
BRANCH_CODE = "91110000400000000U"  # 分公司
OTHER_CODE = "91110000710931130E"


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


def _ns(**kw) -> SimpleNamespace:
    """normalize_group_fields 只读写属性，替身足够（不连库的纯校验用例）。"""
    fields = {f: None for f in group_links.GROUP_FIELDS}
    fields.update({"company_code": CHILD_CODE, "client_name": "测试子公司有限公司"})
    fields.update(kw)
    return SimpleNamespace(**fields)


async def _get(db: AsyncSession, project_id) -> Project:
    return (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()


# ─────────────────────────── 规范化与校验（需求 1.3~1.5） ───────────────────────────


class TestNormalize:
    def test_blank_strings_become_none(self):
        data = _ns(parent_company_name="  ", parent_company_code="", relation_to_parent=" ",
                   ultimate_company_name="\t", ultimate_company_code="")
        group_links.normalize_group_fields(data)
        assert all(getattr(data, f) is None for f in group_links.GROUP_FIELDS)

    def test_values_are_stripped(self):
        data = _ns(parent_company_name=" 母公司 ", parent_company_code=f" {PARENT_CODE} ",
                   relation_to_parent=" 子公司 ")
        group_links.normalize_group_fields(data)
        assert data.parent_company_name == "母公司"
        assert data.parent_company_code == PARENT_CODE
        assert data.relation_to_parent == "subsidiary"

    @pytest.mark.parametrize(
        ("field", "label"),
        [("parent_company_code", "上级企业代码"), ("ultimate_company_code", "最终控制方代码")],
    )
    def test_invalid_uscc_rejected_with_field_label(self, field, label):
        data = _ns(**{field: "91110000710931130F"})  # 校验位错（正确为 E）
        with pytest.raises(HTTPException) as exc:
            group_links.normalize_group_fields(data)
        assert exc.value.status_code == 422
        assert exc.value.detail == f"{label}：统一社会信用代码校验码错误"

    def test_parent_equal_to_self_accepted_and_relation_cleared(self):
        """需求 1.5（2026-09-29 用户更正）：上级=本企业不拒绝，表示本企业就是上级企业；关系无意义 ⇒ 置空。"""
        data = _ns(parent_company_code=CHILD_CODE, relation_to_parent="branch")
        group_links.normalize_group_fields(data)
        assert data.parent_company_code == CHILD_CODE, "原值照存（回填时用户看到自己填的）"
        assert data.relation_to_parent is None

    def test_invalid_relation_rejected(self):
        data = _ns(parent_company_code=PARENT_CODE, relation_to_parent="联营企业")
        with pytest.raises(HTTPException) as exc:
            group_links.normalize_group_fields(data)
        assert exc.value.status_code == 422
        assert "与上级关系只能是 子公司 或 分公司" in exc.value.detail

    def test_relation_cleared_when_no_parent(self):
        data = _ns(parent_company_code=None, relation_to_parent="branch")
        group_links.normalize_group_fields(data)
        assert data.relation_to_parent is None

    def test_ultimate_may_equal_self(self):
        """控制方=本企业是合法的（集团顶层自己就是最终控制方）。"""
        data = _ns(ultimate_company_code=CHILD_CODE)
        group_links.normalize_group_fields(data)
        assert data.ultimate_company_code == CHILD_CODE


# ─────────────────────────── 建项：默认关系与控制方补齐 ───────────────────────────


class TestCreateDefaults:
    @pytest.mark.asyncio
    async def test_relation_defaults_by_name_branch(self, db):
        p = await svc.create_project(
            _info(client_name="某某有限公司临港店", company_code=BRANCH_CODE,
                  parent_company_code=PARENT_CODE),
            db,
        )
        assert p.relation_to_parent == "branch"
        assert any("已按企业名称默认为「分公司」" in n for n in p._group_notices)
        stored = p.wizard_state["steps"]["basic_info"]["data"]
        assert stored["relation_to_parent"] == "branch", "向导回填数据须与 ORM 列一致"

    @pytest.mark.asyncio
    async def test_relation_defaults_by_name_subsidiary(self, db):
        p = await svc.create_project(_info(parent_company_code=PARENT_CODE), db)
        assert p.relation_to_parent == "subsidiary"

    @pytest.mark.asyncio
    async def test_explicit_relation_wins_over_name(self, db):
        """名称像分公司但用户明确选了子公司 ⇒ 以手选为准（需求 2.4）。"""
        p = await svc.create_project(
            _info(client_name="某某有限公司临港店", parent_company_code=PARENT_CODE,
                  relation_to_parent="subsidiary"),
            db,
        )
        assert p.relation_to_parent == "subsidiary"
        assert not any("默认为" in n for n in p._group_notices)

    @pytest.mark.asyncio
    async def test_no_parent_no_relation(self, db):
        p = await svc.create_project(_info(relation_to_parent="branch"), db)
        assert p.parent_company_code is None
        assert p.relation_to_parent is None
        assert p._group_notices == []

    @pytest.mark.asyncio
    async def test_ultimate_copied_from_parent_filled_value(self, db):
        await svc.create_project(
            _info(client_name="母公司", company_code=PARENT_CODE, short_name="母公司",
                  parent_company_code=GROUP_CODE, ultimate_company_code=GROUP_CODE,
                  ultimate_company_name="某集团"),
            db,
        )
        child = await svc.create_project(_info(parent_company_code=PARENT_CODE), db)
        assert child.ultimate_company_code == GROUP_CODE
        assert child.ultimate_company_name == "某集团"
        assert any("最终控制方已按上级企业补齐" in n for n in child._group_notices)

    @pytest.mark.asyncio
    async def test_ultimate_not_guessed_when_parent_has_none(self, db):
        """上级自己没填控制方 ⇒ 保持为空，不推断「上级即控制方」。"""
        await svc.create_project(
            _info(client_name="母公司", company_code=PARENT_CODE, short_name="母公司"), db
        )
        child = await svc.create_project(_info(parent_company_code=PARENT_CODE), db)
        assert child.ultimate_company_code is None

    @pytest.mark.asyncio
    async def test_ultimate_lookup_is_year_scoped(self, db):
        """上级只在别的年度有控制方 ⇒ 不串年补齐。"""
        await svc.create_project(
            _info(client_name="母公司", company_code=PARENT_CODE, short_name="母公司",
                  audit_year=2024, ultimate_company_code=GROUP_CODE),
            db,
        )
        child = await svc.create_project(_info(parent_company_code=PARENT_CODE), db)
        assert child.ultimate_company_code is None

    @pytest.mark.asyncio
    async def test_explicit_ultimate_not_overwritten(self, db):
        await svc.create_project(
            _info(client_name="母公司", company_code=PARENT_CODE, short_name="母公司",
                  ultimate_company_code=GROUP_CODE),
            db,
        )
        child = await svc.create_project(
            _info(parent_company_code=PARENT_CODE, ultimate_company_code=OTHER_CODE), db
        )
        assert child.ultimate_company_code == OTHER_CODE

    @pytest.mark.asyncio
    async def test_self_parent_is_top_without_relation_or_ultimate_guess(self, db):
        """上级=本企业 ⇒ 顶层企业：不补关系、不拿自己当上级去补控制方，说明按顶层处理。"""
        p = await svc.create_project(
            _info(client_name="某某有限公司临港店", parent_company_code=CHILD_CODE), db
        )
        assert p.parent_company_code == CHILD_CODE
        assert p.relation_to_parent is None, "不能按名称给自己补「分公司」"
        assert p.ultimate_company_code is None
        assert p._group_notices == [
            "上级企业代码与本企业相同，已按「本企业就是上级企业」处理：本企业为集团顶层企业，不另建上级节点"
        ]

    @pytest.mark.asyncio
    async def test_three_codes_equal_is_ultimate(self, db):
        p = await svc.create_project(
            _info(parent_company_code=CHILD_CODE, ultimate_company_code=CHILD_CODE), db
        )
        assert p.relation_to_parent is None
        assert p._group_notices == ["三个代码相同，已按「本企业即为最终控制方（集团总部或母公司）」处理"]

    @pytest.mark.asyncio
    async def test_self_parent_notice_only_when_meaning_changes(self, db):
        """同一组代码再次保存不重复说明；从「顶层」改成「三码相同」时再说明一次。"""
        p = await svc.create_project(_info(parent_company_code=CHILD_CODE), db)
        payload = dict(p.wizard_state["steps"]["basic_info"]["data"])

        resaved = await svc.update_step(p.id, WizardStep.basic_info, dict(payload), db)
        assert resaved.notices == []

        payload["ultimate_company_code"] = CHILD_CODE
        upgraded = await svc.update_step(p.id, WizardStep.basic_info, dict(payload), db)
        assert upgraded.notices == ["三个代码相同，已按「本企业即为最终控制方（集团总部或母公司）」处理"]

    @pytest.mark.asyncio
    async def test_invalid_parent_code_rejected_before_insert(self, db):
        with pytest.raises(HTTPException) as exc:
            await svc.create_project(_info(parent_company_code="91110000710931130F"), db)
        assert exc.value.status_code == 422
        assert exc.value.detail.startswith("上级企业代码：")
        rows = (await db.execute(select(Project))).scalars().all()
        assert rows == [], "校验失败不得落库"


# ─────────────────────────── 两口径共享集团关系（需求 1.8） ───────────────────────────


class TestCounterpart:
    @pytest.mark.asyncio
    async def test_create_inherits_from_standalone(self, db):
        standalone = await svc.create_project(
            _info(parent_company_code=PARENT_CODE, parent_company_name="母公司",
                  relation_to_parent="subsidiary", ultimate_company_code=GROUP_CODE,
                  ultimate_company_name="某集团"),
            db,
        )
        consol = await svc.create_project(_info(report_scope="consolidated"), db)
        assert consol.id != standalone.id
        assert consol.parent_company_code == PARENT_CODE
        assert consol.parent_company_name == "母公司"
        assert consol.relation_to_parent == "subsidiary"
        assert consol.ultimate_company_code == GROUP_CODE
        assert any("已从同企业的单户项目" in n for n in consol._group_notices)

    @pytest.mark.asyncio
    async def test_create_does_not_override_explicit_values(self, db):
        await svc.create_project(
            _info(parent_company_code=PARENT_CODE, relation_to_parent="subsidiary"), db
        )
        consol = await svc.create_project(
            _info(report_scope="consolidated", parent_company_code=GROUP_CODE,
                  relation_to_parent="branch"),
            db,
        )
        assert consol.parent_company_code == GROUP_CODE
        assert consol.relation_to_parent == "branch"

    @pytest.mark.asyncio
    async def test_create_propagates_to_counterpart_when_different(self, db):
        """新建合并项目填了与单体不同的上级 ⇒ 单体同步为新值（ORM 列 + 向导回填）。"""
        standalone = await svc.create_project(
            _info(parent_company_code=PARENT_CODE, relation_to_parent="subsidiary"), db
        )
        consol = await svc.create_project(
            _info(report_scope="consolidated", parent_company_code=GROUP_CODE,
                  relation_to_parent="branch"),
            db,
        )
        assert any("已同步集团关系到同企业的单户项目" in n for n in consol._group_notices)
        refreshed = await _get(db, standalone.id)
        assert refreshed.parent_company_code == GROUP_CODE
        assert refreshed.relation_to_parent == "branch"
        wizard_data = refreshed.wizard_state["steps"]["basic_info"]["data"]
        assert wizard_data["parent_company_code"] == GROUP_CODE
        assert wizard_data["relation_to_parent"] == "branch"

    @pytest.mark.asyncio
    async def test_propagate_disabled_keeps_counterpart(self, db):
        """批量导入自动建的合并根：只继承不外推（propagate_group=False）。"""
        standalone = await svc.create_project(
            _info(parent_company_code=PARENT_CODE, relation_to_parent="subsidiary"), db
        )
        consol = await svc.create_project(
            _info(report_scope="consolidated", parent_company_code=GROUP_CODE),
            db,
            propagate_group=False,
        )
        assert not any("已同步" in n for n in consol._group_notices)
        refreshed = await _get(db, standalone.id)
        assert refreshed.parent_company_code == PARENT_CODE

    @pytest.mark.asyncio
    async def test_other_year_is_not_a_counterpart(self, db):
        await svc.create_project(
            _info(audit_year=2024, parent_company_code=PARENT_CODE), db
        )
        consol = await svc.create_project(_info(report_scope="consolidated"), db)
        assert consol.parent_company_code is None
        assert consol._group_notices == []

    @pytest.mark.asyncio
    async def test_update_step_propagates_and_reports(self, db):
        standalone = await svc.create_project(_info(), db)
        consol = await svc.create_project(_info(report_scope="consolidated"), db)
        payload = _info(report_scope="consolidated", parent_company_code=PARENT_CODE,
                        relation_to_parent="subsidiary").model_dump(mode="json")

        resp = await svc.update_step(consol.id, WizardStep.basic_info, payload, db)

        assert any("已同步集团关系到同企业的单户项目" in n for n in resp.notices)
        refreshed = await _get(db, standalone.id)
        assert refreshed.parent_company_code == PARENT_CODE
        assert refreshed.relation_to_parent == "subsidiary"
        # notices 不入库
        saved = await _get(db, consol.id)
        assert "notices" not in saved.wizard_state

    @pytest.mark.asyncio
    async def test_update_step_no_change_no_notice(self, db):
        await svc.create_project(_info(parent_company_code=PARENT_CODE,
                                       relation_to_parent="subsidiary"), db)
        consol = await svc.create_project(_info(report_scope="consolidated"), db)
        payload = _info(report_scope="consolidated", parent_company_code=PARENT_CODE,
                        relation_to_parent="subsidiary").model_dump(mode="json")
        resp = await svc.update_step(consol.id, WizardStep.basic_info, payload, db)
        assert resp.notices == []


# ─────────────────────────── 保存：手选不被覆盖 / 清空不回填 ───────────────────────────


class TestUpdateStep:
    @pytest.mark.asyncio
    async def test_manual_relation_survives_resave(self, db):
        """名称像分公司、用户手选子公司 ⇒ 再次保存（关系原样带回）仍为子公司（需求 2.4）。"""
        p = await svc.create_project(
            _info(client_name="某某有限公司临港店", parent_company_code=PARENT_CODE,
                  relation_to_parent="subsidiary"),
            db,
        )
        payload = p.wizard_state["steps"]["basic_info"]["data"]
        resp = await svc.update_step(p.id, WizardStep.basic_info, dict(payload), db)
        assert (await _get(db, p.id)).relation_to_parent == "subsidiary"
        assert resp.notices == []

    @pytest.mark.asyncio
    async def test_cleared_ultimate_not_refilled_when_parent_unchanged(self, db):
        await svc.create_project(
            _info(client_name="母公司", company_code=PARENT_CODE, short_name="母公司",
                  ultimate_company_code=GROUP_CODE),
            db,
        )
        child = await svc.create_project(_info(parent_company_code=PARENT_CODE), db)
        assert child.ultimate_company_code == GROUP_CODE

        payload = dict(child.wizard_state["steps"]["basic_info"]["data"])
        payload["ultimate_company_code"] = ""
        payload["ultimate_company_name"] = ""
        await svc.update_step(child.id, WizardStep.basic_info, payload, db)
        assert (await _get(db, child.id)).ultimate_company_code is None

    @pytest.mark.asyncio
    async def test_parent_change_refills_ultimate(self, db):
        await svc.create_project(
            _info(client_name="母公司", company_code=PARENT_CODE, short_name="母公司",
                  ultimate_company_code=GROUP_CODE),
            db,
        )
        child = await svc.create_project(_info(), db)
        payload = dict(child.wizard_state["steps"]["basic_info"]["data"])
        payload["parent_company_code"] = PARENT_CODE
        resp = await svc.update_step(child.id, WizardStep.basic_info, payload, db)
        refreshed = await _get(db, child.id)
        assert refreshed.ultimate_company_code == GROUP_CODE
        assert refreshed.relation_to_parent == "subsidiary"
        assert any("最终控制方已按上级企业补齐" in n for n in resp.notices)

    @pytest.mark.asyncio
    async def test_clearing_parent_clears_relation(self, db):
        p = await svc.create_project(
            _info(parent_company_code=PARENT_CODE, relation_to_parent="branch"), db
        )
        payload = dict(p.wizard_state["steps"]["basic_info"]["data"])
        payload["parent_company_code"] = None
        await svc.update_step(p.id, WizardStep.basic_info, payload, db)
        refreshed = await _get(db, p.id)
        assert refreshed.parent_company_code is None
        assert refreshed.relation_to_parent is None

    @pytest.mark.asyncio
    async def test_malformed_payload_is_422_not_500(self, db):
        p = await svc.create_project(_info(), db)
        with pytest.raises(HTTPException) as exc:
            await svc.update_step(p.id, WizardStep.basic_info, {"client_name": "缺字段"}, db)
        assert exc.value.status_code == 422
        assert exc.value.detail.startswith("基本信息字段缺失或格式错误：")
        assert "audit_year" in exc.value.detail

    @pytest.mark.asyncio
    async def test_legacy_consolidation_type_key_ignored(self, db):
        """旧客户端仍发 consolidation_type ⇒ 忽略，不落 ORM 列、不进向导回填数据。"""
        p = await svc.create_project(_info(), db)
        payload = dict(p.wizard_state["steps"]["basic_info"]["data"])
        payload["consolidation_type"] = "branch"
        await svc.update_step(p.id, WizardStep.basic_info, payload, db)
        refreshed = await _get(db, p.id)
        assert refreshed.consolidation_type is None
        assert "consolidation_type" not in refreshed.wizard_state["steps"]["basic_info"]["data"]


def test_find_counterpart_delegates_to_parent_company_scope():
    """同企业另一口径的定位必须委托 parent_company_scope（不在本模块自拼三条件）。"""
    import inspect
    import re

    src = inspect.getsource(group_links)
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"(?m)#.*$", "", code)
    body = code.split("async def find_counterpart", 1)[1].split("\ndef ", 1)[0]
    assert "resolve_parent_standalone_project" in body
    assert "resolve_consolidated_sibling" in body
    assert "report_scope ==" not in body and "Project.report_scope" not in body
