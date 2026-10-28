"""跨 sheet 溯源在真实 async 请求链里拿到规范 addr_id（acnr-foundation-defect-closure T20，需求 8.1~8.3，design §9.3；pg_only）。

真 PG：外层事务里建【测试】项目与底稿（E1 的 ``univer_snapshot`` 用目录权威名「货币资金分析表E1-14」等），会话以 SAVEPOINT
方式加入，结束整体回滚。经生产注册的 router（``tests/authz_world.build_app``）用 httpx 真发
``GET /api/custom-query/cross-sheet-trace``，只 override ``get_current_user`` 与 ``get_db``；不 mock ``_sync_resolve``、
``exact_identity`` 与 ``resolve_instance``。审计写入换成本地记录器（不写共享库），同时用它核对审计记的是规范 addr_id。

覆盖：登记格 ``resolved=true`` / ``in_catalog=true``；sheet 已识别、A1 合法但未登记的 ``E1-14!Z99`` ``resolved=true`` /
``in_catalog=false`` / addr_id ``E1/E1-14/Z99`` / jump_route 非空（R2-F8）；sheet 级底稿的 jump_route 来自 ``resolve_instance``，
项目只有父底稿时回落父底稿并带 ``sheet=``；目录外 sheet、A1 非法、父级内多义、禁止别名 ⇒ ``resolved=false`` + 中文原因；
响应旧字段一个不少（只增）。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.redis as core_redis
from app.models.base import ProjectStatus, UserRole
from app.models.core import Project
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
from app.routers import custom_query
from app.services.acnr.catalog import get_catalog
from app.services.custom_query import audit_helper
from tests.authz_world import AuthzWorld, build_app

pytestmark = pytest.mark.pg_only

TRACE = "/api/custom-query/cross-sheet-trace"
_E1_14 = get_catalog().sheets_by_addr_id["E1/E1-14"]["sheet_name"]
_E1_15 = get_catalog().sheets_by_addr_id["E1/E1-15"]["sheet_name"]
#: 起点 E1-14!C10 引用三处：登记格 E1-15!C8、未登记格 E1-14!Z99、目录外的表
_ROOT_FORMULA = f"='{_E1_15}'!C8+'{_E1_14}'!Z99+'不存在的表'!A1"
#: 响应节点的旧字段（只增不改）
_OLD_FIELDS = {"depth", "uri", "value", "formula", "truncated", "cycle", "missing", "addr_id", "wp_id",
               "jump_route", "resolved"}


def _snapshot(cells: dict[str, dict[str, dict]]) -> dict:
    """{sheet 名: {A1: {"v"/"f"}}} ⇒ ``parsed_data.univer_snapshot``。"""
    def idx(a1: str) -> tuple[str, str]:
        col = "".join(ch for ch in a1 if ch.isalpha())
        row = int(a1[len(col):])
        num = 0
        for ch in col:
            num = num * 26 + ord(ch) - 64
        return str(row - 1), str(num - 1)

    sheets = []
    for name, by_a1 in cells.items():
        data: dict[str, dict] = {}
        for a1, cell in by_a1.items():
            r, c = idx(a1)
            data.setdefault(r, {})[c] = cell
        sheets.append({"name": name, "cellData": data})
    return {"univer_snapshot": {"sheets": sheets}}


class World:
    def __init__(self, aw: AuthzWorld, project_id: uuid.UUID, wp_ids: dict, audits: list) -> None:
        self.aw, self.pid, self.wp_ids, self.audits = aw, str(project_id), wp_ids, audits
        self.api = build_app(custom_query.router)

    def client(self, user):
        return self.aw.client_for_app(self.api, user=user, replace_rls=False)


async def _paper(s: AsyncSession, pid: uuid.UUID, code: str, parsed: dict) -> uuid.UUID:
    idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=code, wp_name=f"【测试】{code}")
    s.add(idx)
    await s.flush()
    wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path=f"{code}.xlsx",
                      source_type=WpSourceType.template, parsed_data=parsed)
    s.add(wp)
    await s.flush()
    return wp.id


@pytest.fixture
async def world(monkeypatch):
    from app.core.config import settings

    audits: list = []

    async def _record(**kwargs):
        audits.append(kwargs)
        return True

    monkeypatch.setattr(audit_helper, "record_cross_sheet_trace", _record)
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            try:
                async with AsyncSession(bind=conn, expire_on_commit=False,
                                        join_transaction_mode="create_savepoint") as s:
                    aw = AuthzWorld(s, monkeypatch)
                    monkeypatch.setattr(core_redis, "redis_client", aw.redis)
                    monkeypatch.setattr(core_redis, "_redis_client", aw.redis)
                    pid = uuid.uuid4()
                    s.add(Project(id=pid, name="【测试】跨 sheet 溯源端到端", client_name="【测试】跨 sheet 溯源端到端",
                                  status=ProjectStatus.execution, template_type="listed", report_scope="standalone",
                                  audit_year=2025, scenario="normal"))
                    await s.flush()
                    e1 = _snapshot({_E1_14: {"C10": {"f": _ROOT_FORMULA, "v": 0}},
                                    _E1_15: {"C8": {"v": 222}}})
                    ids = {"E1": await _paper(s, pid, "E1", e1),
                           # 只有 E1-15 有 sheet 级底稿：它的 jump_route 由 resolve_instance 给出
                           "E1-15": await _paper(s, pid, "E1-15", {}),
                           "F2": await _paper(s, pid, "F2", _snapshot({"底稿目录": {"A1": {"v": 1}}})),
                           "D5": await _paper(s, pid, "D5", _snapshot({"底稿目录": {"A1": {"v": 1}}}))}
                    try:
                        yield World(aw, pid, ids, audits)
                    finally:
                        await aw.redis.aclose()
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()


async def _trace(world: World, wp_code: str, sheet: str, cell: str) -> list[dict]:
    admin = await world.aw.user(UserRole.admin)
    async with world.client(admin) as c:
        resp = await c.get(TRACE, params={"wp_code": wp_code, "sheet_name": sheet, "cell_ref": cell,
                                          "project_id": world.pid})
    assert resp.status_code == 200, resp.text
    chain = resp.json()["chain"]
    for node in chain:
        assert _OLD_FIELDS <= set(node), node
        assert (node["addr_id"] is None) == (node["unresolved_reason"] is not None), node
    return chain


async def test_registered_unregistered_and_outside_nodes(world: World):
    chain = await _trace(world, "E1", _E1_14, "C10")
    got = [(n["uri"], n["addr_id"], n["resolved"], n["in_catalog"]) for n in chain]
    assert got == [
        (f"{_E1_14}!C10", "E1/E1-14/C10", True, True),
        (f"{_E1_15}!C8", "E1/E1-15/C8", True, True),
        (f"{_E1_14}!Z99", "E1/E1-14/Z99", True, False),
        ("不存在的表!A1", None, False, False),
    ]
    root, sheet_level, unregistered, outside = chain
    assert "E1/E1-14/C10" in get_catalog().cells_by_addr_id
    assert "E1/E1-14/Z99" not in get_catalog().cells_by_addr_id
    assert sheet_level["value"] == 222
    # 项目只有父底稿 E1：回落父底稿并带 sheet= 定位到 E1-14
    e1 = str(world.wp_ids["E1"])
    for node in (root, unregistered):
        assert node["wp_id"] == e1 and node["jump_route"] == f"/workpapers/{e1}?sheet=E1-14", node
    # E1-15 有 sheet 级底稿：jump_route 来自 resolve_instance
    e1_15 = str(world.wp_ids["E1-15"])
    assert sheet_level["wp_id"] == e1_15 and sheet_level["jump_route"] == f"/workpapers/{e1_15}?sheet=E1-15"
    assert outside["wp_id"] is None and outside["jump_route"] is None
    assert "不存在的表" in outside["unresolved_reason"]
    # 审计记的是规范 addr_id，未解析节点退回 uri
    assert len(world.audits) == 1
    recorded = list(world.audits[0]["addr_ids"])
    assert {"E1/E1-14/C10", "E1/E1-15/C8", "E1/E1-14/Z99", "不存在的表!A1"} <= set(recorded)


@pytest.mark.parametrize(
    ("wp_code", "sheet", "cell", "needles"),
    [
        ("E1", _E1_14, "A1B", ("A1B", "合法的 A1")),
        ("F2", "底稿目录", "A1", ("F2-33", "F2-34")),
        ("D5", "底稿目录", "A1", ("底稿目录",)),
    ],
    ids=["A1 非法", "父级内多义", "禁止别名"],
)
async def test_unresolvable_root_has_chinese_reason(world: World, wp_code, sheet, cell, needles):
    chain = await _trace(world, wp_code, sheet, cell)
    root = chain[0]
    assert root["resolved"] is False and root["addr_id"] is None and root["in_catalog"] is False
    assert root["wp_id"] is None and root["jump_route"] is None
    for needle in needles:
        assert needle in root["unresolved_reason"], root
