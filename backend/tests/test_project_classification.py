"""项目质控分类 / 专项场景单一来源（spec trim-generation-plan-followup-optimizations R4）。

- ``project_classification.resolve``：分类 × 场景 × 报表模板矩阵、迁移前残留值、未登记值；
- 写入严格校验（未登记值 422）、旧客户端不发键不改库、显式清空、详情回填（TestClient 真发请求）；
- 登记值三处同步：参考标准 JSON / ORM CHECK / V219 迁移；模板 ``applicable_when`` 声明的标签全部可达。
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_schemas import BasicInfoSchema  # noqa: E402
from app.models.base import Base, ProjectStatus, UserRole  # noqa: E402
from app.models.core import Project  # noqa: E402
from app.routers.project_wizard import _to_project_response, router  # noqa: E402
from app.services import project_classification as pc  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[1]
_V219 = _BACKEND / "migrations" / "V219__project_category_scenario_split.sql"


# ── 解释矩阵 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("category", "scenario", "template_type", "code", "group", "defaulted", "resolved_scenario", "tags"),
    [
        (None, None, None, None, "C", True, "normal", set()),
        ("", "normal", "soe", None, "C", True, "normal", set()),
        (" a1 ", "normal", "soe", "A1", "A", False, "normal", {"listed"}),
        ("A2", "normal", None, "A2", "A", False, "normal", {"ipo"}),
        ("A5", "listed", "soe", "A5", "A", False, "listed", {"listed"}),
        ("B", None, None, "B", "B", False, "normal", set()),
        ("B1", "restructure", None, "B1", "B", False, "restructure", {"neeq", "restructuring"}),
        ("C", "fraud_response", "listed", "C", "C", False, "fraud_response", {"fraud_risk", "listed"}),
        # 迁移前残留在分类列的场景值：场景仍为 normal 时按场景解释，分类按未填写
        ("IPO", "normal", "soe", None, "C", True, "ipo", {"ipo"}),
        (" refinancing ", None, None, None, "C", True, "refinancing", {"refinancing"}),
        # 场景已非 normal 时以场景列为准
        ("IPO", "transfer", None, None, "C", True, "transfer", {"neeq"}),
        # 未登记值：分类按未填写、场景按 normal（宽松读取，永不抛错）
        ("D9", "integrated", None, None, "C", True, "normal", set()),
        ("上市公司", " IPO ", None, None, "C", True, "ipo", {"ipo"}),
    ],
)
def test_resolve_matrix(category, scenario, template_type, code, group, defaulted, resolved_scenario, tags):
    c = pc.resolve(category, scenario, template_type)
    assert (c.category_code, c.category_group, c.defaulted, c.scenario, set(c.tags)) == (
        code, group, defaulted, resolved_scenario, tags)
    assert c.is_ipo == ("ipo" in tags)
    assert c.is_refinancing == ("refinancing" in tags)
    assert c.is_capital_market == bool(tags & {"ipo", "listed", "neeq", "restructuring", "refinancing"})
    assert c.as_dict()["tags"] == sorted(tags)
    assert set(c.flags()) == {f"biz_{t}" for t in pc.ALL_TAGS}


def test_project_classification_reads_orm_attributes():
    project = Project(business_category="A4", scenario="normal", template_type="soe")
    assert pc.project_classification(project).is_refinancing is True


@pytest.mark.parametrize("value", ["IPO", "refinancing", "A9", "B7", "D", "上市公司", "A 1"])
def test_strict_category_rejects_unregistered_values(value):
    with pytest.raises(pc.ClassificationValueError):
        pc.normalize_category(value)


@pytest.mark.parametrize(("value", "expected"), [(None, None), ("", None), ("  ", None), (" b3 ", "B3"), ("c", "C")])
def test_strict_category_normalizes_registered_values(value, expected):
    assert pc.normalize_category(value) == expected


@pytest.mark.parametrize(("value", "expected"), [(None, "normal"), ("", "normal"), (" IPO ", "ipo"),
                                                 ("Refinancing", "refinancing")])
def test_strict_scenario_normalizes_registered_values(value, expected):
    assert pc.normalize_scenario(value) == expected


@pytest.mark.parametrize("value", ["integrated", "neeq", "上市", "restructuring"])
def test_strict_scenario_rejects_unregistered_values(value):
    with pytest.raises(pc.ClassificationValueError):
        pc.normalize_scenario(value)


def test_basic_info_schema_validates_and_normalizes():
    base = {"client_name": "【测试】分类", "audit_year": 2025, "project_type": "annual",
            "accounting_standard": "enterprise", "company_code": "91110000710931130E", "short_name": "分类"}
    parsed = BasicInfoSchema.model_validate({**base, "business_category": " a1 ", "scenario": "IPO"})
    assert (parsed.business_category, parsed.scenario) == ("A1", "ipo")
    assert {"business_category", "scenario"} <= parsed.model_fields_set
    omitted = BasicInfoSchema.model_validate(base)
    assert not ({"business_category", "scenario"} & omitted.model_fields_set), "没发的键不进 fields_set（不改库）"
    for bad in ({"business_category": "IPO"}, {"scenario": "integrated"}):
        with pytest.raises(ValidationError):
            BasicInfoSchema.model_validate({**base, **bad})


# ── 登记值三处同步 / 标签可达 ───────────────────────────────────────────────


def _in_list(sql: str, column: str) -> list[list[str]]:
    lists = []
    for match in re.finditer(rf"{column}\s+(?:NOT\s+)?IN\s*\(([^)]*)\)", sql, flags=re.IGNORECASE):
        lists.append(re.findall(r"'([^']*)'", match.group(1)))
    return lists


def test_registered_values_are_identical_in_reference_orm_and_migration():
    orm_checks = {c.name: str(c.sqltext) for c in Project.__table__.constraints if c.name and c.name.startswith("ck_projects_")}
    orm_categories = _in_list(orm_checks["ck_projects_business_category_registered"], "business_category")
    orm_scenarios = _in_list(orm_checks["ck_projects_scenario_registered"], "scenario")
    assert [set(x) for x in orm_categories] == [set(pc.category_codes())]
    assert [list(x) for x in orm_scenarios] == [list(pc.SCENARIOS)]

    sql = _V219.read_text(encoding="utf-8")
    check_block = sql[sql.index("ADD CONSTRAINT ck_projects_business_category_registered"):]
    assert set(_in_list(check_block, "business_category")[0]) == set(pc.category_codes())
    assert _in_list(check_block, "scenario")[0] == list(pc.SCENARIOS)
    precheck = sql[: sql.index("CREATE TABLE IF NOT EXISTS project_classification_v219_backup")]
    known = set(_in_list(precheck, "upper\\(btrim\\(business_category\\)\\)")[0])
    assert known == set(pc.category_codes()) | set(pc.LEGACY_SCENARIO_CATEGORIES), "预检放行 = 登记码 + 可搬迁旧值"
    assert _in_list(precheck, "scenario")[-1] == list(pc.SCENARIOS)
    assert set(pc.SCENARIO_LABELS) == set(pc.SCENARIOS)
    assert set(pc.SCENARIO_TAGS) == set(pc.SCENARIOS) - {"normal"}
    assert set(pc.LEGACY_SCENARIO_CATEGORIES.values()) <= set(pc.SCENARIOS)


def test_v219_backup_table_is_allowlisted_unmapped_and_owned_by_the_migration_pair():
    """备份表只给 R219 用：V219 建、R219 删、无 ORM；登记进漂移白名单（否则每次启动报一条 db_extra）。"""
    from app.core.schema_drift_detector import SchemaDriftDetector

    table = "project_classification_v219_backup"
    assert table in SchemaDriftDetector.KNOWN_ALLOWLIST
    assert table not in Base.metadata.tables
    assert f"CREATE TABLE IF NOT EXISTS {table}" in _V219.read_text(encoding="utf-8")
    r219 = (_BACKEND / "migrations" / "R219__rollback_project_category_scenario_split.sql").read_text(encoding="utf-8")
    assert f"DROP TABLE IF EXISTS {table}" in r219


def test_every_declared_template_tag_is_reachable():
    mapping = json.loads((_BACKEND / "data" / "wp_account_mapping.json").read_text(encoding="utf-8"))
    declared = {
        str(v).strip().lower()
        for m in mapping["mappings"]
        for v in ((m.get("applicable_when") or {}).get("business_category") or [])
    }
    assert declared, "映射表应当声明过业务分类适用性"
    reachable = set(pc.SCENARIO_TAGS.values()) | set(pc.CATEGORY_TAGS.values())
    assert declared <= reachable, f"有模板声明的标签任何项目都打不中：{sorted(declared - reachable)}"
    assert set(pc.CATEGORY_TAGS) <= set(pc.category_codes())


# ── 写读链（TestClient 真发请求） ───────────────────────────────────────────


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_admin"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


BASIC = {"client_name": "【测试】分类回填", "audit_year": 2025, "project_type": "annual",
         "accounting_standard": "enterprise", "company_code": "91110000710931130E", "short_name": "分类回填"}


@pytest_asyncio.fixture
async def http():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    api = FastAPI()
    api.include_router(router)

    async def _db():
        yield session

    user = _FakeUser()

    async def _user():
        return user

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        yield client, session
    await session.close()
    await engine.dispose()


async def _row(session: AsyncSession, pid: str) -> tuple[str | None, str]:
    session.expire_all()
    project = await session.get(Project, uuid.UUID(pid))
    return project.business_category, project.scenario


@pytest.mark.asyncio
async def test_create_save_and_readback_round_trip(http):
    client, session = http
    created = await client.post("/api/projects", json={**BASIC, "business_category": " a1 ", "scenario": "Listed"})
    assert created.status_code == 200, created.text
    body = created.json()
    pid = body["id"]
    assert (body["business_category"], body["scenario"]) == ("A1", "listed")
    assert body["project_classification"]["tags"] == ["listed"]
    assert await _row(session, pid) == ("A1", "listed")

    detail = (await client.get(f"/api/projects/{pid}")).json()
    assert (detail["business_category"], detail["scenario"]) == ("A1", "listed")

    # 旧客户端：不发这两个键 ⇒ 库里的值不动，向导里存的也是项目值（不是 null）
    saved = await client.put(f"/api/projects/{pid}/wizard/basic_info", json=BASIC)
    assert saved.status_code == 200, saved.text
    assert await _row(session, pid) == ("A1", "listed")
    stored = saved.json()["steps"]["basic_info"]["data"]
    assert (stored["business_category"], stored["scenario"]) == ("A1", "listed")

    # 新客户端：显式清空分类、改场景
    saved = await client.put(f"/api/projects/{pid}/wizard/basic_info",
                             json={**BASIC, "business_category": None, "scenario": "ipo"})
    assert saved.status_code == 200, saved.text
    assert await _row(session, pid) == (None, "ipo")
    detail = (await client.get(f"/api/projects/{pid}")).json()
    assert detail["project_classification"]["defaulted"] is True
    assert detail["project_classification"]["is_ipo"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"business_category": "IPO"}, {"business_category": "A9"}, {"scenario": "integrated"}])
async def test_unregistered_values_are_422_and_change_nothing(http, bad):
    client, session = http
    created = await client.post("/api/projects", json={**BASIC, "business_category": "B2"})
    pid = created.json()["id"]
    rejected = await client.put(f"/api/projects/{pid}/wizard/basic_info", json={**BASIC, **bad})
    assert rejected.status_code == 422, rejected.text
    assert await _row(session, pid) == ("B2", "normal")
    assert (await client.post("/api/projects", json={**BASIC, **bad, "company_code": "91110000710931131C"})
            ).status_code == 422


def test_response_presents_legacy_values_as_scenario():
    """迁移前残留：分类列 IPO、场景 normal ⇒ 详情显示「分类未填写 + 场景 IPO」，回填表单再保存即写成规范值。"""
    project = Project(id=uuid.uuid4(), name="【测试】旧值_2025", client_name="【测试】旧值", status=ProjectStatus.created,
                      business_category="IPO", scenario="normal", template_type="soe")
    project.created_at = __import__("datetime").datetime(2026, 10, 29)
    response = _to_project_response(project)
    assert (response.business_category, response.scenario) == (None, "ipo")
    assert response.project_classification["is_ipo"] is True


# ── 前后端登记值逐值一致（前端只读后端解释结果，选项与字段形状必须同口径） ─────────────────

_FRONTEND = _BACKEND.parent / "audit-platform" / "frontend" / "src"
_TS_TYPES = _FRONTEND / "types" / "projectClassification.ts"
_TS_IPO = _FRONTEND / "utils" / "ipoProjectUtils.ts"


def _ts_block(text: str, anchor: str, opener: str, closer: str) -> str:
    """取 ``anchor`` 之后第一对 ``opener … closer``（按括号配平，不被内层同类括号提前截断）。"""
    start = text.index(opener, text.index(anchor))
    depth = 0
    for i in range(start, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return text[start + 1: i]
    raise AssertionError(f"{anchor} 的括号不配平")


def test_frontend_scenario_options_match_backend_order_and_labels():
    text = _TS_TYPES.read_bytes().decode("utf-8")
    options = re.findall(r"\{\s*value:\s*'([^']+)',\s*label:\s*'([^']+)'\s*\}",
                         _ts_block(text, "export const SCENARIO_OPTIONS", "[", "]"))
    assert len(options) == len(pc.SCENARIOS), f"没解析出全部场景选项（解析口径失效？）：{options}"
    assert [v for v, _ in options] == list(pc.SCENARIOS)
    assert dict(options) == pc.SCENARIO_LABELS

    union_start = text.index("export type ProjectScenario")
    union = text[union_start: text.index("\n\n", union_start)]
    assert re.findall(r"'([^']+)'", union) == list(pc.SCENARIOS)

    groups = re.findall(r"value:\s*'([^']+)'", _ts_block(text, "export const CATEGORY_GROUP_OPTIONS", "[", "]"))
    assert groups == list(pc.CATEGORY_GROUPS)


def test_frontend_category_codes_match_reference():
    """前端 categoryGroupOfCode 按 CATEGORY_CODES 认登记码（A1-11 表里存的码归组用），须与参考标准逐值一致。"""
    text = _TS_TYPES.read_bytes().decode("utf-8")
    codes = re.findall(r"'([^']+)'", _ts_block(text, "export const CATEGORY_CODES", "[", "]"))
    assert len(codes) > 3, f"没解析出 CATEGORY_CODES（解析口径失效？）：{codes}"
    assert len(codes) == len(set(codes))
    assert set(codes) == set(pc.category_codes())
    assert all(pc.resolve(code).category_group == code[0] for code in codes)


def test_frontend_classification_interface_matches_as_dict_keys():
    text = _TS_TYPES.read_bytes().decode("utf-8")
    body = _ts_block(text, "export interface ProjectClassification", "{", "}")
    keys = re.findall(r"^\s*(\w+)\s*:", body, flags=re.MULTILINE)
    assert keys, "没解析出接口字段（解析口径失效？）"
    assert set(keys) == set(pc.resolve(None).as_dict()), "前端 ProjectClassification 字段与后端 as_dict() 不一致"


def test_frontend_capital_market_keywords_match_backend_tags():
    text = _TS_IPO.read_bytes().decode("utf-8")
    keywords = re.findall(r"'([^']+)'", _ts_block(text, "export const IPO_BIZ_KEYWORDS", "[", "]"))
    assert keywords, "没解析出 IPO_BIZ_KEYWORDS（解析口径失效？）"
    assert set(keywords) == set(pc.CAPITAL_MARKET_TAGS)
