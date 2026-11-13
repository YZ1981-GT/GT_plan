"""凭证检查行索引（spec voucher-workflow-linkage-lineage-closure design §8，任务 5）

- 结论取值表：白名单字段、字段各自的取值（isConsistent 的「是」是正常，isAbnormal 的「是」是异常）、布尔值、未判定；
- 扫描：身份行按 ``_gt.vk``、旧行按「号|日期」；两列都读；纯文本与坏 JSON 跳过；只算本项目未删除底稿；
  可限定底稿；超过字典上限 / 单条载荷上限标 truncated；认出的行不重复计入里面的 ``_gt``。
"""

from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services import voucher_row_index as idx
from app.services.voucher_identity import VoucherKey

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

PROJECT, OTHER = uuid.uuid4(), uuid.uuid4()
WP_D2, WP_E1, WP_GONE, WP_OTHER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
COMPANY = "主体"


def _vk(no: str, d: str = "2025-03-05", vtype: str = "记") -> VoucherKey:
    return VoucherKey.of(year=2025, company_code=COMPANY, voucher_date=d, voucher_type=vtype, voucher_no=no)


def _row(no: str, **fields) -> dict:
    return {"voucherNo": no, "voucherDate": "2025-03-05", "_gt": {"vk": _vk(no).to_str(), "src": ["attach"]}, **fields}


class TestVerdict:
    @pytest.mark.parametrize(("row", "want"), [
        ({"isAbnormal": "是"}, "abnormal"),
        ({"isAbnormal": " 否 "}, "normal"),
        ({"abnormal": True}, "abnormal"),
        ({"abnormal": False}, "normal"),
        ({"checkResult": "ERR"}, "abnormal"),
        ({"checkResult": "√"}, "normal"),
        ({"auditConclusion": "差异可接受"}, "normal"),
        ({"auditConclusion": "存疑"}, "unknown"),
        ({"isConsistent": "是"}, "normal"),
        ({"isConsistent": "否"}, "abnormal"),
        ({"checkConclusion": "未取得权证"}, "abnormal"),
        ({"conclusion": "异常"}, "unknown"),  # conclusion 不在白名单
        ({"isAbnormal": "true"}, "unknown"),  # 字符串 true 不等于布尔 true
        ({"checkResult": "OK", "isAbnormal": "是"}, "abnormal"),  # 任一异常即异常
        ({}, "unknown"),
    ])
    def test_row_verdict(self, row, want):
        assert idx.row_verdict(row) == want

    def test_legacy_key_needs_number_and_date(self):
        assert idx.legacy_key(" 0007 ", "2025-03-05T00:00:00") == "0007|2025-03-05"
        assert idx.legacy_key("0007", "") is None
        assert idx.legacy_key("", "2025-03-05") is None


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(idx.CHECKLIST.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        uid = uuid.uuid4()
        session.add(User(id=uid, username="u", email="u@t.com", hashed_password="x", role="auditor"))
        for pid in (PROJECT, OTHER):
            session.add(Project(id=pid, name=f"索引 {pid.hex[:4]}", client_name="测试", created_by=uid,
                                project_type=ProjectType.annual, status=ProjectStatus.execution))
        for wp_id, pid, code, deleted in ((WP_D2, PROJECT, "D2", False), (WP_E1, PROJECT, "E1", False),
                                          (WP_GONE, PROJECT, "F3", True), (WP_OTHER, OTHER, "D2", False)):
            wi = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=code, wp_name=code, audit_cycle=code[0],
                         status=WpStatus.not_started)
            session.add(wi)
            session.add(WorkingPaper(id=wp_id, project_id=pid, wp_index_id=wi.id, file_path="x.xlsx",
                                     source_type=WpSourceType.template, file_version=1, is_deleted=deleted))
        await session.commit()
        yield session
    await engine.dispose()


async def _put(db, wp_id, item_id, *, remark=None, conclusion=None, project=PROJECT):
    await db.execute(sa.insert(idx.CHECKLIST).values(
        id=uuid.uuid4(), project_id=project, wp_id=wp_id, item_id=item_id,
        remark=json.dumps(remark, ensure_ascii=False) if isinstance(remark, (list, dict)) else remark,
        conclusion=json.dumps(conclusion, ensure_ascii=False) if isinstance(conclusion, (list, dict)) else conclusion,
    ))
    await db.commit()


@pytest.mark.asyncio
async def test_scan_identity_and_legacy_rows_with_verdicts(db):
    await _put(db, WP_D2, "D2-check-rows", remark=[_row("0001", isAbnormal="是"), _row("0002", checkResult="OK")])
    await _put(db, WP_E1, "E1-large", conclusion={"rows": [{"voucherNo": "0001", "date": "2025-03-05", "abnormal": False}]})
    await _put(db, WP_E1, "E1-note", remark="纯文本结论，提到 voucherNo 也不算行")
    await _put(db, WP_E1, "E1-bad", remark='[{"voucherNo": "0009", ')  # 坏 JSON
    result = await idx.scan_voucher_rows(db, PROJECT)
    assert not result.truncated
    got = sorted((h.wp_id == WP_D2, h.item_id, h.vk is not None, h.legacy, h.verdict) for h in result.hits)
    assert got == [
        (False, "E1-large", False, "0001|2025-03-05", "normal"),
        (True, "D2-check-rows", True, "0001|2025-03-05", "abnormal"),
        (True, "D2-check-rows", True, "0002|2025-03-05", "normal"),
    ]
    rows = result.rows_for(_vk("0001"))
    assert sorted((h.item_id, h.vk is None) for h in rows) == [("D2-check-rows", False), ("E1-large", True)]
    assert list(result.by_key()) == [_vk("0001").to_str(), _vk("0002").to_str()]


@pytest.mark.asyncio
async def test_scan_only_live_workpapers_of_the_project(db):
    await _put(db, WP_GONE, "gone", remark=[_row("0001")])
    await _put(db, WP_OTHER, "other", remark=[_row("0001")], project=OTHER)
    await _put(db, WP_OTHER, "other-mislabeled", remark=[_row("0001")])  # project_id 写成本项目、底稿属别的项目
    assert (await idx.scan_voucher_rows(db, PROJECT)).hits == []


@pytest.mark.asyncio
async def test_scan_limited_to_given_workpapers(db):
    await _put(db, WP_D2, "a", remark=[_row("0001")])
    await _put(db, WP_E1, "b", remark=[_row("0001")])
    hits = (await idx.scan_voucher_rows(db, PROJECT, wp_ids=[WP_E1])).hits
    assert [h.wp_id for h in hits] == [WP_E1]
    assert (await idx.scan_voucher_rows(db, PROJECT, wp_ids=[])).hits == []


@pytest.mark.asyncio
async def test_scan_caps_mark_truncated(db, monkeypatch):
    await _put(db, WP_D2, "many", remark=[_row(f"{i:04d}") for i in range(30)])
    capped = await idx.scan_voucher_rows(db, PROJECT, max_dicts=10)
    assert capped.truncated and len(capped.hits) < 30
    monkeypatch.setattr(idx, "MAX_PAYLOAD_CHARS", 50)
    big = await idx.scan_voucher_rows(db, PROJECT)
    assert big.truncated and big.hits == []


@pytest.mark.asyncio
async def test_row_with_gt_but_no_voucher_key_falls_back_to_number_and_date(db):
    manual = {"voucherNo": "0005", "voucherDate": "2025-03-05", "isAbnormal": "是", "_gt": {"vk": None, "src": ["manual"]}}
    await _put(db, WP_D2, "m", remark=[manual])
    (hit,) = (await idx.scan_voucher_rows(db, PROJECT)).hits
    assert (hit.vk, hit.legacy, hit.verdict) == (None, "0005|2025-03-05", "abnormal")
