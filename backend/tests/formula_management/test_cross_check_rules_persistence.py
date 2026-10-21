"""表间审核规则落库 + report-cross-check year 契约 —— Phase 6 Task 6.2

## 这个文件在干什么

tasks.md Task 6.2 验收判据（集成）：
  · GET report-cross-check 带 year 返 200（§1 #13：后端 year 必填，前端不传恒 422）。
  · 新增/编辑规则落库（关闭再打开仍可见）。
  · 空结果显式「无结果」—— 未保存过规则时 GET 返空集，前端据此呈现「无结果」。

本测试覆盖后端侧契约（前端解析/UI「无结果」由 crossCheckKeyConsistency.spec.ts 与
FormulaManagerDialog 的 loadCrossCheckItems 实现保证；此处坐实后端端点行为）：

  · test_report_cross_check_requires_year —— 缺 year → 422（契约不变，前端须补 year）；
    带 year → 200，响应是**执行结果** `{issue_list, results, last_computed_at}`，
    results 为逐条勾稽（非规则列表）。
  · test_cross_check_rules_roundtrip —— PUT 规则 → GET 取回一致（落库 = 关闭再打开仍可见）。
  · test_cross_check_rules_empty_when_never_saved —— 从未保存 → GET 返 `{"rules": {}}`
    （空集，供前端显式「无结果」，不冒充静态示例）。
  · test_cross_check_rules_overwrite —— PUT 整体替换语义（第二次 PUT 覆盖第一次）。
  · 变异反证 test_put_strips_transient_fields —— PUT 落库只保留契约字段，`_editing`
    等 UI 瞬态字段不落库（防止把渲染态写进持久层）。

## 鉴权口径

用 admin 用户（admin 跳过项目权限检查，见 deps.assert_project_permission）走通
`require_project_access`；本测试只验「端点契约 + 落库往返」，跨项目越权坐实由
Task 5.1 §6.1 专测承接，不在此重复。dependency_overrides 覆盖**内层** get_db /
get_current_user（教训㉕①：不直接覆盖 require_project_access 工厂）。
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus
from app.models.core import Project, User, UserRole

# SQLite 无 JSONB —— 用 JSON 渲染（与既有鉴权端点测试同款）。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

_PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def seed(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="cc_admin",
        email="cc_admin@example.com",
        hashed_password="x",
        role=UserRole.admin,  # admin 跳过项目权限检查
    )
    db.add(user)
    project = Project(
        id=_PROJECT_ID,
        name="表间审核测试项目",
        client_name="测试客户",
        status=ProjectStatus.execution,
        is_deleted=False,
        wizard_state=None,  # 从未保存过规则
    )
    db.add(project)
    await db.flush()
    await db.commit()
    return user


def _make_app(db: AsyncSession, user: User) -> FastAPI:
    from app.routers import formula_logic_check as fc_router

    app = FastAPI()
    app.include_router(fc_router.router)

    async def _override_db():
        yield db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


def _rules_url() -> str:
    return f"/api/projects/{_PROJECT_ID}/formula/cross-check-rules"


def test_report_cross_check_requires_year(db: AsyncSession, seed: User):
    """缺 year → 422（契约不变）；带 year → 200，响应是执行结果（非规则列表）。"""
    app = _make_app(db, seed)
    client = TestClient(app)
    base = f"/api/projects/{_PROJECT_ID}/formula/report-cross-check"

    # 缺 year：FastAPI 必填查询参数校验失败 → 422（§1 #13 现状，前端须补 year）。
    resp_missing = client.get(base)
    assert resp_missing.status_code == 422, (
        f"缺 year 应 422（year 必填），实得 {resp_missing.status_code}: {resp_missing.text}"
    )

    # 带 year：200，响应是执行结果 {issue_list, results, last_computed_at}。
    resp = client.get(base, params={"year": 2025})
    assert resp.status_code == 200, f"带 year 应 200，实得 {resp.status_code}: {resp.text}"
    data = resp.json()
    body = data if "results" in data else data.get("data", {})
    assert "results" in body and "issue_list" in body, (
        f"响应应是执行结果（含 results / issue_list），实得键：{list(body)}"
    )
    assert isinstance(body["results"], list), "results 应为逐条勾稽执行结果（列表）"


def test_cross_check_rules_empty_when_never_saved(db: AsyncSession, seed: User):
    """从未保存过 → GET 返 {"rules": {}}（空集，供前端显式「无结果」）。"""
    app = _make_app(db, seed)
    client = TestClient(app)

    resp = client.get(_rules_url())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    rules = data.get("rules", data.get("data", {}).get("rules"))
    assert rules == {}, f"从未保存应返回空集，实得 {rules!r}"


def test_cross_check_rules_roundtrip(db: AsyncSession, seed: User):
    """PUT 规则 → GET 取回一致（落库 = 关闭再打开仍可见）。"""
    app = _make_app(db, seed)
    client = TestClient(app)

    payload = {
        "rules": {
            "cross_report_note": [
                {
                    "label": "BS货币资金 = 附注货币资金合计",
                    "left_ref": "REPORT('BS-002','期末')",
                    "operator": "=",
                    "right_ref": "NOTE('货币资金','合计','期末')",
                    "description": "用户新增规则",
                }
            ],
            "cross_report_wp": [
                {
                    "label": "BS应收账款 = D2-1审定数",
                    "left_ref": "REPORT('BS-008','期末')",
                    "operator": "=",
                    "right_ref": "WP('D2-1','审定数')",
                    "description": "",
                }
            ],
        }
    }

    put_resp = client.put(_rules_url(), json=payload)
    assert put_resp.status_code == 200, put_resp.text

    # 关闭再打开 = 重新 GET，应取回已保存规则。
    get_resp = client.get(_rules_url())
    assert get_resp.status_code == 200, get_resp.text
    data = get_resp.json()
    rules = data.get("rules", data.get("data", {}).get("rules"))

    assert set(rules) == {"cross_report_note", "cross_report_wp"}
    assert len(rules["cross_report_note"]) == 1
    rn = rules["cross_report_note"][0]
    assert rn["label"] == "BS货币资金 = 附注货币资金合计"
    assert rn["left_ref"] == "REPORT('BS-002','期末')"
    assert rn["right_ref"] == "NOTE('货币资金','合计','期末')"
    assert rn["description"] == "用户新增规则"


def test_cross_check_rules_overwrite(db: AsyncSession, seed: User):
    """PUT 整体替换：第二次 PUT 覆盖第一次（编辑/删除后的新全集生效）。

    formula-global-settings-sync（2026-10-20）：已有规则时 PUT 须带读接口下发的 ``loaded``
    版本令牌（缺失 428 且零写入；防止拿着过期列表整表覆盖别人的修改）。
    """
    app = _make_app(db, seed)
    client = TestClient(app)

    first = client.put(
        _rules_url(),
        json={"rules": {"cross_report_note": [{"label": "旧规则", "left_ref": "A", "right_ref": "B"}]}},
    )
    assert first.status_code == 200, first.text
    loaded = first.json()["loaded"]
    assert len(loaded) == 1
    # 第二次 PUT：删掉 report_note、改为 note_wp 一条（缺令牌 428 由
    # tests/formula_settings/test_tb_detail_and_cross_check.py 覆盖：本文件各请求共用一个会话，
    # 428 回滚会让注入的身份实例过期，无法在同步测试里重新载入）。
    second = client.put(_rules_url(), json={
        "rules": {"cross_note_wp": [{"label": "新规则", "left_ref": "X", "right_ref": "Y"}]}, "loaded": loaded})
    assert second.status_code == 200, second.text

    data = client.get(_rules_url()).json()
    rules = data.get("rules", data.get("data", {}).get("rules"))
    assert set(rules) == {"cross_note_wp"}, f"整体替换后应只剩新全集，实得 {set(rules)}"
    assert rules["cross_note_wp"][0]["label"] == "新规则"


def test_put_strips_transient_fields(db: AsyncSession, seed: User):
    """变异反证：PUT 落库只保留契约字段，UI 瞬态字段（_editing 等）不落库。

    若落库把整行透传（含 _editing/_leftVal/_pass），持久层会混入渲染态 ——
    下次读出带着上次的校验结果，误导用户。本测试断言落库后只有 5 个契约字段。
    """
    app = _make_app(db, seed)
    client = TestClient(app)

    client.put(
        _rules_url(),
        json={
            "rules": {
                "cross_report_note": [
                    {
                        "label": "带瞬态字段的规则",
                        "left_ref": "A",
                        "operator": "=",
                        "right_ref": "B",
                        "description": "d",
                        # 以下 UI 瞬态字段（pydantic 模型未声明 → 被忽略，不落库）
                        "_editing": True,
                        "_leftVal": 123,
                        "_pass": False,
                    }
                ]
            }
        },
    )

    data = client.get(_rules_url()).json()
    rules = data.get("rules", data.get("data", {}).get("rules"))
    stored = rules["cross_report_note"][0]
    # 读接口 = 契约字段 + 服务端元数据（规则编号 / 公式位 / 层级 / 待确认 / 版本令牌，2026-10-20 起）
    assert set(stored) == {"label", "left_ref", "operator", "right_ref", "description", "tolerance",
                           "rule_id", "slot_key", "layer", "pending", "version_token"}, (
        f"读出应只含契约字段与服务端元数据，实得 {set(stored)}（瞬态字段未被剔除 = 缺陷）"
    )
    # 落库定义只含契约字段：tests/formula_settings/test_tb_detail_and_cross_check.py 逐字段断言
