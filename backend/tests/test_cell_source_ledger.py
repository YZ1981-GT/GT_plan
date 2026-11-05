"""账务查询单元格来源（spec citar-cell-source-hover R6，design §8）。

列级：取自导入文件哪个 sheet 的哪个表头（导入作业的确认映射）、推导方式；行级：舍弃的多列映射值、辅助明细汇总、人工修改；
没有映射记录时如实说明；序时账行单取；项目只读鉴权。
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import TbBalance, TbLedger  # noqa: E402
from app.models.base import Base, PermissionLevel  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, ProjectUserRole, User, UserRole  # noqa: E402
from app.models.dataset_models import DatasetStatus, ImportJob, LedgerDataset  # noqa: E402
from app.models.ledger_edit_models import LedgerManualEdit  # noqa: E402
from app.routers.cell_sources import router as src_router  # noqa: E402
from app.services.cell_source.ledger import balance_sources, journal_row_source, journal_sources  # noqa: E402

P = uuid.UUID("00000000-0000-0000-0000-00000000c701")
EDITOR = uuid.UUID("00000000-0000-0000-0000-00000000c702")
OUTSIDER = uuid.UUID("00000000-0000-0000-0000-00000000c703")
YEAR = 2025
DS, JOB = uuid.uuid4(), uuid.uuid4()
ROW_DISCARD, ROW_AUX, ROW_EDIT, LEDGER_ROW = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

CONFIRMED = [
    {"file_name": "00_余额表.xlsx", "sheet_name": "余额表", "table_type": "balance", "confirmed_by_user": True,
     "mapping_entries": [
         {"column_index": 0, "standard_field": "account_code", "original_header": "科目编号"},
         {"column_index": 1, "standard_field": "account_name", "original_header": "上级科目名称"},
         {"column_index": 2, "standard_field": "account_name", "original_header": "科目名称"},
         {"column_index": 3, "standard_field": "opening_debit", "original_header": "期初借方"},
         {"column_index": 4, "standard_field": "opening_credit", "original_header": "期初贷方"},
         {"column_index": 5, "standard_field": "year_debit", "original_header": "本年累计借方"},
         {"column_index": 6, "standard_field": "closing_balance", "original_header": "期末余额"},
     ]},
    {"file_name": "01_序时账.xlsx", "sheet_name": "序时账", "table_type": "ledger", "confirmed_by_user": False,
     "mapping_entries": [{"column_index": 0, "standard_field": "voucher_date", "original_header": "记账时间"},
                         {"column_index": 1, "standard_field": "amount", "original_header": "金额"}]},
]


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        s.add(User(id=EDITOR, username="导入人甲", email="i@t.local", hashed_password="x", role=UserRole.auditor))
        s.add(Project(id=P, name="账务来源_2025", client_name="账务来源", project_type=ProjectType.annual,
                      status=ProjectStatus.execution, created_by=EDITOR))
        await s.flush()
        s.add(ProjectUser(project_id=P, user_id=EDITOR, role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit))
        s.add(ImportJob(id=JOB, project_id=P, year=YEAR, custom_mapping={"confirmed_mappings": CONFIRMED}, created_by=EDITOR))
        await s.flush()
        s.add(LedgerDataset(id=DS, project_id=P, year=YEAR, status=DatasetStatus.active, job_id=JOB, activated_by=EDITOR))
        common = dict(project_id=P, year=YEAR, company_code="001", dataset_id=DS, opening_balance=Decimal(0),
                      debit_amount=Decimal(0), credit_amount=Decimal(0), closing_balance=Decimal(10))
        s.add(TbBalance(id=ROW_DISCARD, account_code="100101", account_name="现金", **common,
                        raw_extra={"_discarded_mappings": {"account_name": [{"header": "科目名称", "value": "备用金"}]}}))
        s.add(TbBalance(id=ROW_AUX, account_code="1122", account_name="应收账款", **common,
                        raw_extra={"_aggregated_from_aux": True, "_aux_row_count": 3}))
        s.add(TbBalance(id=ROW_EDIT, account_code="1002", account_name="银行存款", **common))
        s.add(LedgerManualEdit(project_id=P, year=YEAR, dataset_id=DS, table_name="balance", row_id=ROW_EDIT, action="edit",
                               before={"closing_balance": "8", "debit_amount": "0"}, after={"closing_balance": "10"},
                               reason="对账单核对", edited_by=EDITOR))
        s.add(TbLedger(id=LEDGER_ROW, project_id=P, year=YEAR, company_code="001", dataset_id=DS, voucher_date=date(YEAR, 3, 1),
                       voucher_no="记-1", account_code="1002", debit_amount=Decimal(5), credit_amount=Decimal(0),
                       raw_extra={"_discarded_mappings": {"voucher_date": [{"header": "凭证种类", "value": "记"}]}}))
        await s.commit()
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_balance_columns_list_mapped_headers_and_derivation(factory):
    async with factory() as s:
        cells = (await balance_sources(s, P, YEAR))["cells"]
    name = cells["col:account_name"]
    assert [i["label"] for i in name["items"]] == ["余额表.xlsx · 余额表 ·「上级科目名称」", "余额表.xlsx · 余额表 ·「科目名称」"]
    assert all("（用户确认）" in i["detail"] for i in name["items"])
    assert any("映射了多列" in n for n in name["notes"])
    assert "期初 = 期初借方 − 期初贷方" in cells["col:opening"]["notes"]
    assert any("本年累计" in n for n in cells["col:debit"]["notes"])
    assert "由 导入人甲 导入" in name["title"]


@pytest.mark.asyncio
async def test_balance_rows_special_cases(factory):
    async with factory() as s:
        cells = (await balance_sources(s, P, YEAR))["cells"]
    discard = cells[f"row:{ROW_DISCARD}"]
    assert discard["issue"] and "映射了多列" in discard["issue"]
    assert discard["items"][0]["label"] == "未采用「科目名称」：备用金" and discard["items"][0]["sign"] == "0"
    assert any("3 条辅助核算明细汇总" in n for n in cells[f"row:{ROW_AUX}"]["notes"])
    edit = cells[f"row:{ROW_EDIT}"]
    assert edit["kind"] == "manual" and edit["manual"]["by_name"] == "导入人甲"
    assert "导入原值：" in edit["manual"]["note"] and "期末 8" in edit["manual"]["note"] and "对账单核对" in edit["manual"]["note"]


@pytest.mark.asyncio
async def test_journal_columns_and_row(factory):
    async with factory() as s:
        cols = (await journal_sources(s, P, YEAR))["cells"]
        row = await journal_row_source(s, P, YEAR, LEDGER_ROW)
        missing = await journal_row_source(s, P, YEAR, uuid.uuid4())
    assert "（自动识别）" in cols["col:voucher_date"]["items"][0]["detail"]
    assert any("单金额列按借贷标识拆成" in n for n in cols["col:debit"]["notes"])
    assert row["items"][0]["label"] == "未采用「凭证种类」：记"
    assert missing is None


@pytest.mark.asyncio
async def test_no_mapping_record_is_stated(factory):
    async with factory() as s:
        job = await s.get(ImportJob, JOB)
        job.custom_mapping = None
        await s.commit()
        cells = (await balance_sources(s, P, YEAR))["cells"]
    assert cells["col:account_code"]["items"] == []
    assert any("没有保存字段映射记录" in n for n in cells["col:account_code"]["notes"])


@pytest.mark.asyncio
async def test_journal_row_ignores_superseded_dataset(factory):
    """旧版本（已被替代）数据集里的行不出来源：行来源只读当前生效数据集（真库 ABC 旧版 14,107 行带舍弃映射、新版 0 行）。"""
    old_ds, old_row = uuid.uuid4(), uuid.uuid4()
    async with factory() as s:
        s.add(LedgerDataset(id=old_ds, project_id=P, year=YEAR, status=DatasetStatus.superseded))
        s.add(TbLedger(id=old_row, project_id=P, year=YEAR, company_code="001", dataset_id=old_ds, voucher_date=date(YEAR, 1, 1),
                       voucher_no="旧-1", account_code="1002", debit_amount=Decimal(1), credit_amount=Decimal(0),
                       raw_extra={"_discarded_mappings": {"voucher_date": [{"header": "凭证种类", "value": "记"}]}}))
        await s.commit()
        assert await journal_row_source(s, P, YEAR, old_row) is None
        assert (await journal_row_source(s, P, YEAR, LEDGER_ROW)) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,status", [(EDITOR, 200), (OUTSIDER, 403)])
async def test_endpoints_require_project_access(factory, uid, status):
    class _U:
        id, username, is_active, role = uid, "u", True, UserRole.auditor

    app = FastAPI()
    app.include_router(src_router)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: _U()
    base = f"/api/projects/{P}/cell-sources/ledger"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        for url in (f"{base}/balance", f"{base}/journal", f"{base}/journal-row/{LEDGER_ROW}"):
            r = await c.get(url, params={"year": YEAR})
            assert r.status_code == status, (url, r.text)


# ── R9：来源项点开导入记录（job_mapping_view + /ledger-import/jobs/{id}/mappings） ──

from app.models.dataset_models import ArtifactStatus, ImportArtifact  # noqa: E402
from app.routers.ledger_datasets import router as import_router  # noqa: E402
from app.services.ledger_import.job_mapping_view import column_letter, job_mapping_view  # noqa: E402


@pytest.mark.asyncio
async def test_mapping_items_link_to_import_record_with_same_keys(factory):
    """卡片每个映射项链到产生当前数据集的导入作业，定位键与详情行的键逐一对得上；行级「未采用」项没有链接。"""
    async with factory() as s:
        bal = (await balance_sources(s, P, YEAR))["cells"]
        jou = (await journal_sources(s, P, YEAR))["cells"]
        view = await job_mapping_view(s, P, JOB)
    detail_keys = {c["locate"] for sh in view["sheets"] for c in sh["columns"]}
    assert [i["link"] for i in bal["col:account_name"]["items"]] == [
        {"page": "ledger_import", "code": str(JOB), "ref": "余额表.xlsx|余额表|1"},
        {"page": "ledger_import", "code": str(JOB), "ref": "余额表.xlsx|余额表|2"},
    ]
    col_items = [i for k, c in (*bal.items(), *jou.items()) if k.startswith("col:") for i in c["items"]]
    assert col_items and all(i["link"]["code"] == str(JOB) and i["link"]["ref"] in detail_keys for i in col_items)
    assert bal[f"row:{ROW_DISCARD}"]["items"][0]["link"] is None


@pytest.mark.asyncio
async def test_job_mapping_view_lists_files_sheets_columns(factory, tmp_path):
    async with factory() as s:
        view = await job_mapping_view(s, P, JOB)
        assert await job_mapping_view(s, uuid.uuid4(), JOB) is None  # 别的项目
        assert await job_mapping_view(s, P, uuid.uuid4()) is None
    assert view["job"]["created_by_name"] == "导入人甲" and view["job"]["status_label"]
    assert view["dataset"]["is_current"] is True and view["dataset"]["status_label"] == "当前生效"
    assert view["file_retained"] is False and view["has_mapping_record"] is True
    bal, led = view["sheets"]
    assert (bal["file"], bal["sheet"], bal["table_label"], bal["confirmed_by_user"]) == ("余额表.xlsx", "余额表", "科目余额表", True)
    assert bal["columns"][0] == {"column_index": 0, "column_letter": "A", "header": "科目编号", "field": "account_code",
                                 "field_label": "科目编码", "locate": "余额表.xlsx|余额表|0"}
    assert (led["table_label"], led["confirmed_by_user"]) == ("序时账", False)
    assert [c["field_label"] for c in led["columns"]] == ["凭证日期", "金额（单列）"]
    assert [column_letter(i) for i in (0, 25, 26, 51, None, "x")] == ["A", "Z", "AA", "AZ", "", ""]


def test_every_recognizable_field_has_chinese_label():
    """导入能识别的每个标准字段都有中文名（真库曾把「科目类别」显示成 category）；入库行数两种键写法都认、同表只计一次。"""
    from app.services.cell_source.ledger import FIELD_LABELS
    from app.services.ledger_import.identifier import HEADER_ALIASES, _RAW_HEADER_ALIASES
    from app.services.ledger_import.job_mapping_view import _records

    fields = set(_RAW_HEADER_ALIASES) | set(HEADER_ALIASES)
    assert fields, "别名表为空：判据抽不到值"
    assert sorted(f for f in fields if f not in FIELD_LABELS) == []
    assert all(any("\u4e00" <= ch <= "\u9fff" for ch in FIELD_LABELS[f]) for f in fields)
    assert _records({"balance_rows": 287, "ledger_rows": 14107, "aux_ledger_rows": 0, "tb_balance": 287}) == [
        {"label": "科目余额表", "count": 287}, {"label": "序时账", "count": 14107}]
    assert _records(None) == []


@pytest.mark.asyncio
async def test_job_mapping_view_artifact_and_missing_record(factory, tmp_path):
    """上传目录还在 ⇒ file_retained；已被导入消费 ⇒ 不在；旧作业没有映射记录如实标出。"""
    art = uuid.uuid4()
    async with factory() as s:
        s.add(ImportArtifact(id=art, project_id=P, upload_token="tok-r9", status=ArtifactStatus.active,
                             storage_uri=f"sharedfs://{tmp_path.as_posix()}"))
        job = await s.get(ImportJob, JOB)
        job.artifact_id = art
        await s.commit()
        assert (await job_mapping_view(s, P, JOB))["file_retained"] is True
        (await s.get(ImportArtifact, art)).status = ArtifactStatus.consumed
        job.custom_mapping = None
        await s.commit()
        view = await job_mapping_view(s, P, JOB)
    assert view["file_retained"] is False and view["has_mapping_record"] is False and view["sheets"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,job,status", [(EDITOR, JOB, 200), (OUTSIDER, JOB, 403), (EDITOR, uuid.uuid4(), 404)])
async def test_job_mappings_endpoint_access(factory, uid, job, status):
    class _U:
        id, username, is_active, role = uid, "u", True, UserRole.auditor

    app = FastAPI()
    app.include_router(import_router)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: _U()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/api/projects/{P}/ledger-import/jobs/{job}/mappings")
    assert r.status_code == status, r.text
    if status == 200:
        assert [sh["table_label"] for sh in r.json()["sheets"]] == ["科目余额表", "序时账"]
