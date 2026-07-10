"""账龄配置端到端集成测试（aging-config-enhancement Task 14.2）

覆盖三条集成链路（后端可确定性验证的部分）：

1. 完整 PUT → EventBus 广播 → GET 链路
   - PUT 保存配置成功
   - save_config 后 event_bus.broadcast_raw 被以 "aging-config:changed" 调用
     （前端 useAgingConfig 监听同名 window 事件触发 refresh，见 useAgingConfig.ts）
   - GET 返回刚保存的配置（PUT→persist→GET 全链路一致）

2. 导入导出 XLSX 往返（真实 openpyxl workbook 序列化 → 反序列化 → 解析）
   - D2-2 三期科目（期初/期末未审/期末审定 × N 段）
   - D3-2 两期科目（期初/期末审定 × N 段）
   - 导出列头基于当前账龄配置生成（Req 8.1），导入按 label 匹配写回 nested 结构（Req 8.2）

3. D6 ECL 联动端到端属于前端逻辑，见
   audit-platform/frontend/src/components/workpaper/__tests__/useD6EclCalculation.integration.spec.ts

约定：参照 test_aging_config_api.py，构造仅挂载目标 router 的裸 FastAPI app，
覆盖 get_db / get_current_user 依赖，使用内存 SQLite。

Validates: Requirements 3.3, 9.2, 8.1, 8.2
"""

from __future__ import annotations

import io
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook, load_workbook
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project
from app.routers.aging_config import router as aging_router
from app.services import event_bus as event_bus_module
from app.services.aging_config_service import AgingPreset, resolve_segments
from app.routers.wp_render_strategies._cycle_import_export_common import (
    build_aging_headers,
    subject_aging_periods,
)
from app.routers.wp_render_strategies._d2_import_export import (
    _d2_2_export_values,
    _parse_d2_2_rows,
    get_d2_2_columns,
)
from app.routers.wp_render_strategies._d3_import_export import (
    _d3_2_dynamic_headers,
    _export_d3_2_row_dynamic,
    _parse_d3_2_row,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FIVE = resolve_segments(AgingPreset.FIVE_YEAR, None)   # 6 段
THREE = resolve_segments(AgingPreset.THREE_YEAR, None)  # 4 段

_LEGACY_FLAT_KEYS = {
    "priorAging1Year", "priorAging1to2", "priorAging2to3", "priorAging3to4",
    "priorAging4to5", "priorAgingOver5",
    "currentAging1Year", "currentAging1to2", "currentAging2to3", "currentAging3to4",
    "currentAging4to5", "currentAgingOver5",
    "auditedAging1Year", "auditedAging1to2", "auditedAging2to3", "auditedAging3to4",
    "auditedAging4to5", "auditedAgingOver5",
}


class _FakeUser:
    """轻量级用户替身（admin 角色）。"""

    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_manager"
        self.email = "manager@test.com"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


TEST_USER = _FakeUser()


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


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    """构造带依赖覆盖的测试 HTTP 客户端。"""
    app = FastAPI()
    app.include_router(aging_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return TEST_USER

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def project_id(db_session: AsyncSession) -> str:
    """在库中插入一个项目并返回其 id。"""
    pid = uuid.uuid4()
    project = Project(
        id=pid,
        name="集成测试项目",
        client_name="测试客户",
        status=ProjectStatus.created,
        wizard_state={},
    )
    db_session.add(project)
    await db_session.commit()
    return str(pid)


@pytest.fixture
def broadcast_spy(monkeypatch):
    """监听 event_bus.broadcast_raw 调用（记录 event_type + extra）。

    aging_config.put_aging_config 内部 `from app.services.event_bus import event_bus`
    后调用 event_bus.broadcast_raw(...)，故对单例实例方法打桩即可捕获。
    """
    calls: list[tuple[str, dict | None]] = []

    def _spy(event_type: str, extra: dict | None = None) -> None:
        calls.append((event_type, extra))

    monkeypatch.setattr(
        event_bus_module.event_bus, "broadcast_raw", _spy, raising=True
    )
    return calls


# ═══════════════════════════════════════════════════════════════════════════════
# 链路 1：完整 PUT → EventBus 广播 → GET
# ═══════════════════════════════════════════════════════════════════════════════


class TestPutEventBusGetChain:
    """Validates: Requirements 3.3 (配置变更→EventBus 通知前端刷新)"""

    @pytest.mark.asyncio
    async def test_put_broadcasts_aging_config_changed_then_get_returns_saved(
        self, client: AsyncClient, project_id: str, broadcast_spy
    ):
        """PUT 保存成功 → 广播 aging-config:changed → GET 返回刚保存的配置。"""
        payload = {
            "preset": "THREE_YEAR",
            "subject_overrides": {"F1": "THREE_YEAR"},
        }
        put_resp = await client.put(
            f"/api/projects/{project_id}/aging/config", json=payload
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["preset"] == "THREE_YEAR"

        # ── EventBus 广播被触发，事件名 + payload 正确（前端据此 refresh）
        assert len(broadcast_spy) == 1
        event_type, extra = broadcast_spy[0]
        assert event_type == "aging-config:changed"
        assert extra is not None
        assert extra["project_id"] == project_id
        assert extra["preset"] == "THREE_YEAR"

        # ── PUT → persist → GET 全链路一致
        get_resp = await client.get(f"/api/projects/{project_id}/aging/config")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["preset"] == "THREE_YEAR"
        assert len(body["effective_segments"]) == 4
        assert body["subject_overrides"] == {"F1": "THREE_YEAR"}

    @pytest.mark.asyncio
    async def test_custom_preset_put_broadcast_get_roundtrip(
        self, client: AsyncClient, project_id: str, broadcast_spy
    ):
        """CUSTOM 预设经 PUT→广播→GET 往返保留自定义段。"""
        payload = {
            "preset": "CUSTOM",
            "custom_segments": [
                {"key": "seg_1", "label": "6个月以内", "dayFrom": 0, "dayTo": 180},
                {"key": "seg_2", "label": "6个月-1年", "dayFrom": 181, "dayTo": 365},
                {"key": "seg_3", "label": "1年以上", "dayFrom": 366, "dayTo": None},
            ],
        }
        put_resp = await client.put(
            f"/api/projects/{project_id}/aging/config", json=payload
        )
        assert put_resp.status_code == 200

        assert len(broadcast_spy) == 1
        assert broadcast_spy[0][0] == "aging-config:changed"
        assert broadcast_spy[0][1]["preset"] == "CUSTOM"

        get_resp = await client.get(f"/api/projects/{project_id}/aging/config")
        body = get_resp.json()
        assert body["preset"] == "CUSTOM"
        assert [s["label"] for s in body["effective_segments"]] == [
            "6个月以内",
            "6个月-1年",
            "1年以上",
        ]

    @pytest.mark.asyncio
    async def test_validation_failure_does_not_broadcast(
        self, client: AsyncClient, project_id: str, broadcast_spy
    ):
        """校验失败（422）时不应广播事件（配置未变更）。"""
        payload = {
            "preset": "CUSTOM",
            "custom_segments": [
                {"key": "seg_1", "label": "唯一段", "dayFrom": 0, "dayTo": None},
            ],
        }
        resp = await client.put(
            f"/api/projects/{project_id}/aging/config", json=payload
        )
        assert resp.status_code == 422
        assert broadcast_spy == []


# ═══════════════════════════════════════════════════════════════════════════════
# 链路 2：导入导出 XLSX 往返（真实 openpyxl 序列化）
# ═══════════════════════════════════════════════════════════════════════════════


def _write_read_xlsx(header: list[str], values: list) -> tuple[list[str], tuple]:
    """把 header + 单行 values 写入真实 xlsx，序列化后反序列化，返回读回的列头 + 行元组。"""
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    ws.append(values)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    wb2 = load_workbook(buf, data_only=True)
    ws2 = wb2.active
    rows = list(ws2.iter_rows(values_only=True))
    wb2.close()
    read_header = [str(c).strip() if c is not None else "" for c in rows[0]]
    read_row = rows[1]
    return read_header, read_row


class TestExportImportXlsxRoundtrip:
    """Validates: Requirements 8.1 (动态列头), 8.2 (label 匹配导入)"""

    @pytest.mark.asyncio
    async def test_d2_2_three_period_xlsx_roundtrip(self):
        """D2-2 三期科目：导出列头基于配置 + 真实 xlsx 往返写回 nested 结构。"""
        segments = FIVE
        columns = get_d2_2_columns(segments)

        # 导出列头应基于当前账龄配置生成（Req 8.1）：每段 3 期列头
        for seg in segments:
            assert f"{seg.label}(期初)" in columns
            assert f"{seg.label}(期末未审)" in columns
            assert f"{seg.label}(期末审定)" in columns

        src = {
            "seq": 1, "customerName": "客户甲", "companyCode": "C001",
            "relationType": "非关联方",
            "priorUnadjusted": 100.0, "priorAje": 0.0, "priorRje": 0.0,
            "priorAudited": 100.0,
            "agingPrior": {s.key: float(i + 1) for i, s in enumerate(segments)},
            "debitOccurrence": 0.0, "creditOccurrence": 0.0, "endBalance": 100.0,
            "reclassification": 0.0, "currentUnadjusted": 100.0,
            "agingCurrent": {s.key: float(i + 10) for i, s in enumerate(segments)},
            "currentAje": 0.0, "currentRje": 0.0, "currentAudited": 100.0,
            "agingAudited": {s.key: float(i + 20) for i, s in enumerate(segments)},
            "creditRiskClassification": "账龄组合", "groupName": "组合A",
            "isConfirmation": True, "postPayment": 0.0, "remark": "",
        }
        exported = _d2_2_export_values(src, segments)

        read_header, read_row = _write_read_xlsx(columns, exported)
        row_dict = {h: v for h, v in zip(read_header, read_row) if h}

        parsed = _parse_d2_2_rows([row_dict], segments)
        assert len(parsed) == 1
        p = parsed[0]

        # 账龄值往返一致（按 label 匹配写回 nested keyed）
        for i, s in enumerate(segments):
            assert p["agingPrior"][s.key] == float(i + 1)
            assert p["agingCurrent"][s.key] == float(i + 10)
            assert p["agingAudited"][s.key] == float(i + 20)
        # 非账龄字段亦保留
        assert p["customerName"] == "客户甲"
        assert p["isConfirmation"] is True
        # 无 legacy flat 键（Property 11）
        assert not (_LEGACY_FLAT_KEYS & set(p.keys()))

    @pytest.mark.asyncio
    async def test_d3_2_two_period_xlsx_roundtrip(self):
        """D3-2 两期科目：导出列头 2N + 真实 xlsx 往返写回 nested 结构。"""
        segments = THREE
        headers = _d3_2_dynamic_headers(segments)

        # 两期列头（期初/期末审定），无「期末未审」（Req 8.1）
        for seg in segments:
            assert f"{seg.label}(期初)" in headers
            assert f"{seg.label}(期末审定)" in headers
            assert f"{seg.label}(期末未审)" not in headers

        src = {
            "rowId": "r1", "customerName": "供应商乙", "companyCode": "X01",
            "nature": "其他", "relationType": "非关联方",
            "priorUnadjusted": 50.0, "priorAdjustment": 0.0, "priorReclass": 0.0,
            "agingPrior": {s.key: float(i + 3) for i, s in enumerate(segments)},
            "debit": 0.0, "credit": 0.0, "entityReclass": 0.0,
            "endAje": 0.0, "endRje": 0.0,
            "agingAudited": {s.key: float(i + 7) for i, s in enumerate(segments)},
            "isConfirmed": "Y", "postPeriodSettlement": 0.0, "remark": "备注X",
        }
        exported = _export_d3_2_row_dynamic(src, segments)

        read_header, read_row = _write_read_xlsx(headers, exported)
        parsed = _parse_d3_2_row(tuple(read_row), read_header, segments)

        assert parsed["customerName"] == "供应商乙"
        assert parsed["isConfirmed"] == "Y"
        for i, s in enumerate(segments):
            assert parsed["agingPrior"][s.key] == float(i + 3)
            assert parsed["agingAudited"][s.key] == float(i + 7)

    @pytest.mark.asyncio
    async def test_d2_2_config_change_old_template_import_maps_by_label(self):
        """配置从 3 段升到 5 段后，导入旧(3段)模板 → 按 label 映射，缺段零初始化（Req 8.2/8.4）。"""
        old_segments = THREE           # 旧模板列头（3年段 4 段）
        new_segments = FIVE            # 当前项目配置（5年段 6 段）

        columns = get_d2_2_columns(old_segments)
        src = {
            "customerName": "客户丙",
            "agingPrior": {s.key: float(i + 1) for i, s in enumerate(old_segments)},
            "agingCurrent": {s.key: float(i + 1) for i, s in enumerate(old_segments)},
            "agingAudited": {s.key: float(i + 1) for i, s in enumerate(old_segments)},
        }
        exported = _d2_2_export_values(src, old_segments)
        read_header, read_row = _write_read_xlsx(columns, exported)
        row_dict = {h: v for h, v in zip(read_header, read_row) if h}

        # 按当前(5段)配置解析：共有段(within1/y1to2/y2to3)保留，新增段(y3to4/y4to5/over5)=0
        parsed = _parse_d2_2_rows([row_dict], new_segments)[0]
        for field in ("agingPrior", "agingCurrent", "agingAudited"):
            assert set(parsed[field].keys()) == {s.key for s in new_segments}
            assert parsed[field]["within1"] == 1.0
            assert parsed[field]["y3to4"] == 0.0
            assert parsed[field]["over5"] == 0.0

    @pytest.mark.asyncio
    async def test_export_headers_match_build_aging_headers(self):
        """导出列头顺序/格式与 build_aging_headers 一致（导出端与导入匹配端同源，Req 8.1）。"""
        for subject, segments in (("D2", FIVE), ("D3", THREE)):
            periods = subject_aging_periods(subject)
            expected = set(build_aging_headers(segments, periods))
            if subject == "D2":
                actual = set(get_d2_2_columns(segments))
            else:
                actual = set(_d3_2_dynamic_headers(segments))
            # 全部账龄列头都出现在导出列头集合中
            assert expected <= actual
