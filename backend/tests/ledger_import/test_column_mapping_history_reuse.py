"""F52 / Sprint 8.37: 列映射历史复用集成测试。

覆盖范围：
1. ``build_file_fingerprint`` 对相同输入稳定、对不同输入区分；
2. ``ImportOrchestrator.apply_history_reuse`` 命中 30 天内的历史记录时
   自动覆盖 ``ColumnMatch.standard_field`` 并标记 ``auto_applied_from_history``；
3. 历史记录超出窗口（> 30 天）时不应用；
4. file_fingerprint 不同（例如 sheet 名不同）时不应用；
5. 覆盖父记录链（``override_parent_id``）的写入路径。

Fixture 模式：SQLite 内存库 + PG JSONB/UUID 降级，同 test_cross_project_isolation.py。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容适配：PG JSONB/UUID 降级到 JSON/uuid（必须在 Base.metadata 构建前生效）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.column_mapping_models  # noqa: E402, F401
from app.models.column_mapping_models import ImportColumnMappingHistory  # noqa: E402
from app.services.ledger_import.column_mapping_service import (  # noqa: E402
    ColumnMappingService,
    DEFAULT_FINGERPRINT_REUSE_WINDOW,
)
from app.services.ledger_import.detection_types import (  # noqa: E402
    ColumnMatch,
    FileDetection,
    LedgerDetectionResult,
    SheetDetection,
)
from app.services.ledger_import.orchestrator import ImportOrchestrator  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _make_sheet(
    *,
    sheet_name: str = "科目余额表",
    header_cells: list[str] | None = None,
    column_mappings: list[ColumnMatch] | None = None,
    table_type: str = "balance",
) -> SheetDetection:
    """构造一份带 header_cells 和 column_mappings 的 SheetDetection。"""
    headers = header_cells or [
        "科目编码",
        "科目名称",
        "期初余额",
        "借方金额",
        "贷方金额",
        "期末余额",
    ]
    cols = column_mappings or [
        ColumnMatch(
            column_index=0,
            column_header=headers[0],
            standard_field=None,
            column_tier="extra",
            confidence=30,
            source="header_fuzzy",
        ),
        ColumnMatch(
            column_index=1,
            column_header=headers[1],
            standard_field=None,
            column_tier="extra",
            confidence=30,
            source="header_fuzzy",
        ),
    ]
    return SheetDetection(
        file_name="数据.xlsx",
        sheet_name=sheet_name,
        row_count_estimate=100,
        header_row_index=0,
        data_start_row=1,
        table_type=table_type,  # type: ignore[arg-type]
        table_type_confidence=85,
        confidence_level="medium",
        column_mappings=cols,
        preview_rows=[headers],
        detection_evidence={"header_cells": headers},
    )


def _make_detection(sheet: SheetDetection) -> LedgerDetectionResult:
    return LedgerDetectionResult(
        upload_token="test-token",
        files=[
            FileDetection(
                file_name=sheet.file_name,
                file_size_bytes=1024,
                file_type="xlsx",
                sheets=[sheet],
            )
        ],
    )


# ---------------------------------------------------------------------------
# build_file_fingerprint 稳定性
# ---------------------------------------------------------------------------


def test_file_fingerprint_stable_for_same_inputs() -> None:
    headers = ["科目编码", "科目名称", "期初余额"]
    fp1 = ColumnMappingService.build_file_fingerprint("余额表", headers)
    fp2 = ColumnMappingService.build_file_fingerprint("余额表", headers)
    assert fp1 == fp2
    assert len(fp1) == 40  # SHA1 十六进制


def test_file_fingerprint_differs_for_different_sheet_names() -> None:
    headers = ["科目编码", "科目名称"]
    fp1 = ColumnMappingService.build_file_fingerprint("科目余额表", headers)
    fp2 = ColumnMappingService.build_file_fingerprint("序时账", headers)
    assert fp1 != fp2


def test_file_fingerprint_differs_for_different_headers() -> None:
    fp1 = ColumnMappingService.build_file_fingerprint("余额表", ["科目编码", "科目名称"])
    fp2 = ColumnMappingService.build_file_fingerprint("余额表", ["account_code", "name"])
    assert fp1 != fp2


def test_file_fingerprint_includes_software_hint() -> None:
    headers = ["科目编码", "科目名称"]
    fp_no_hint = ColumnMappingService.build_file_fingerprint("余额表", headers)
    fp_hint = ColumnMappingService.build_file_fingerprint(
        "余额表", headers, software_hint="yonyou_U8"
    )
    assert fp_no_hint != fp_hint


def test_file_fingerprint_case_insensitive_and_strip() -> None:
    headers_a = ["科目编码", "科目名称"]
    headers_b = ["  科目编码 ", "科目名称"]
    fp_a = ColumnMappingService.build_file_fingerprint("余额表", headers_a)
    fp_b = ColumnMappingService.build_file_fingerprint(" 余额表 ", headers_b)
    assert fp_a == fp_b


def test_file_fingerprint_only_takes_first_20_headers() -> None:
    base = [f"列{i}" for i in range(20)]
    fp1 = ColumnMappingService.build_file_fingerprint("表", base)
    fp2 = ColumnMappingService.build_file_fingerprint("表", base + ["第 21 列"])
    assert fp1 == fp2


# ---------------------------------------------------------------------------
# apply_history_reuse 命中
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_history_reuse_hits_within_window(db_session: AsyncSession) -> None:
    project_id = uuid.uuid4()
    headers = ["科目编码", "科目名称", "借方金额", "贷方金额"]
    fp = ColumnMappingService.build_file_fingerprint("科目余额表", headers)

    # 准备历史记录（正向格式：standard_field → header_name）
    now = datetime.now(timezone.utc)
    record = ImportColumnMappingHistory(
        id=uuid.uuid4(),
        project_id=project_id,
        software_fingerprint="yonyou_balance",
        table_type="balance",
        column_mapping={
            "account_code": "科目编码",
            "account_name": "科目名称",
            "debit_amount": "借方金额",
            "credit_amount": "贷方金额",
        },
        file_fingerprint=fp,
        used_count=1,
        created_at=now,
        last_used_at=now,
    )
    db_session.add(record)
    await db_session.flush()

    # 构造 detection：所有列 standard_field=None
    cols = [
        ColumnMatch(
            column_index=i,
            column_header=h,
            standard_field=None,
            column_tier="extra",
            confidence=30,
            source="header_fuzzy",
        )
        for i, h in enumerate(headers)
    ]
    sheet = _make_sheet(sheet_name="科目余额表", header_cells=headers, column_mappings=cols)
    detection = _make_detection(sheet)

    result = await ImportOrchestrator.apply_history_reuse(
        db_session, detection, project_id=project_id
    )

    applied_cols = result.files[0].sheets[0].column_mappings
    mapped = {c.column_header: c for c in applied_cols}
    assert mapped["科目编码"].standard_field == "account_code"
    assert mapped["科目编码"].auto_applied_from_history is True
    assert mapped["科目编码"].history_mapping_id == str(record.id)
    assert mapped["科目编码"].source == "history_reuse"
    assert mapped["科目编码"].confidence >= 90

    assert mapped["借方金额"].standard_field == "debit_amount"
    assert mapped["借方金额"].column_tier == "key"

    # detection_evidence 带上命中信息
    evidence = result.files[0].sheets[0].detection_evidence
    assert evidence.get("history_reuse", {}).get("hit") is True
    assert evidence["history_reuse"]["mapping_id"] == str(record.id)


@pytest.mark.asyncio
async def test_apply_history_reuse_no_hit_when_fingerprint_mismatch(
    db_session: AsyncSession,
) -> None:
    project_id = uuid.uuid4()
    stored_fp = ColumnMappingService.build_file_fingerprint("旧表", ["a", "b"])
    now = datetime.now(timezone.utc)
    record = ImportColumnMappingHistory(
        id=uuid.uuid4(),
        project_id=project_id,
        software_fingerprint="yonyou_balance",
        table_type="balance",
        column_mapping={"account_code": "科目编码"},
        file_fingerprint=stored_fp,
        used_count=1,
        created_at=now,
        last_used_at=now,
    )
    db_session.add(record)
    await db_session.flush()

    # detection 的 fingerprint 不同（sheet 名不同）
    headers = ["科目编码", "科目名称"]
    sheet = _make_sheet(sheet_name="新表", header_cells=headers)
    detection = _make_detection(sheet)

    result = await ImportOrchestrator.apply_history_reuse(
        db_session, detection, project_id=project_id
    )
    cols = result.files[0].sheets[0].column_mappings
    assert all(c.auto_applied_from_history is False for c in cols)


@pytest.mark.asyncio
async def test_apply_history_reuse_respects_30_day_window(
    db_session: AsyncSession,
) -> None:
    project_id = uuid.uuid4()
    headers = ["科目编码", "科目名称"]
    fp = ColumnMappingService.build_file_fingerprint("科目余额表", headers)

    # 准备一条"31 天前"的历史记录
    old_time = datetime.now(timezone.utc) - timedelta(days=31)
    record = ImportColumnMappingHistory(
        id=uuid.uuid4(),
        project_id=project_id,
        software_fingerprint="yonyou_balance",
        table_type="balance",
        column_mapping={"account_code": "科目编码"},
        file_fingerprint=fp,
        created_at=old_time,
        last_used_at=old_time,
    )
    db_session.add(record)
    await db_session.flush()

    sheet = _make_sheet(sheet_name="科目余额表", header_cells=headers)
    detection = _make_detection(sheet)

    result = await ImportOrchestrator.apply_history_reuse(
        db_session, detection, project_id=project_id, window_days=30
    )
    cols = result.files[0].sheets[0].column_mappings
    assert all(c.auto_applied_from_history is False for c in cols)


@pytest.mark.asyncio
async def test_apply_history_reuse_picks_latest_within_window(
    db_session: AsyncSession,
) -> None:
    project_id = uuid.uuid4()
    headers = ["科目编码", "科目名称"]
    fp = ColumnMappingService.build_file_fingerprint("科目余额表", headers)

    # 两条记录，后者较新
    old_rec = ImportColumnMappingHistory(
        id=uuid.uuid4(),
        project_id=project_id,
        software_fingerprint="yonyou_balance",
        table_type="balance",
        column_mapping={"account_code": "科目编码"},
        file_fingerprint=fp,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        last_used_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(old_rec)
    new_rec = ImportColumnMappingHistory(
        id=uuid.uuid4(),
        project_id=project_id,
        software_fingerprint="yonyou_balance",
        table_type="balance",
        column_mapping={
            "account_code": "科目编码",
            "account_name": "科目名称",
        },
        file_fingerprint=fp,
        override_parent_id=old_rec.id,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
        last_used_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(new_rec)
    await db_session.flush()

    sheet = _make_sheet(sheet_name="科目余额表", header_cells=headers)
    detection = _make_detection(sheet)
    result = await ImportOrchestrator.apply_history_reuse(
        db_session, detection, project_id=project_id
    )
    cols = {c.column_header: c for c in result.files[0].sheets[0].column_mappings}
    # 新记录命中，mapping_id = new_rec.id
    assert cols["科目编码"].history_mapping_id == str(new_rec.id)


@pytest.mark.asyncio
async def test_save_with_file_fingerprint_and_override_parent(
    db_session: AsyncSession,
) -> None:
    project_id = uuid.uuid4()
    headers = ["科目编码"]
    fp = ColumnMappingService.build_file_fingerprint("表", headers)
    parent = await ColumnMappingService.save_with_file_fingerprint(
        db_session,
        project_id=project_id,
        software_fingerprint="yonyou_balance",
        table_type="balance",
        column_mapping={"account_code": "科目编码"},
        file_fingerprint=fp,
    )
    assert parent.override_parent_id is None
    assert parent.file_fingerprint == fp

    # 修改后再保存一版（覆盖链）
    child = await ColumnMappingService.save_with_file_fingerprint(
        db_session,
        project_id=project_id,
        software_fingerprint="yonyou_balance",
        table_type="balance",
        column_mapping={
            "account_code": "科目编码",
            "account_name": "科目名称",
        },
        file_fingerprint=fp,
        override_parent_id=parent.id,
    )
    assert child.override_parent_id == parent.id


@pytest.mark.asyncio
async def test_find_by_file_fingerprint_returns_none_when_no_fingerprint(
    db_session: AsyncSession,
) -> None:
    project_id = uuid.uuid4()
    result = await ColumnMappingService.find_by_file_fingerprint(
        db_session, project_id=project_id, file_fingerprint=""
    )
    assert result is None


def test_default_reuse_window_is_30_days() -> None:
    assert DEFAULT_FINGERPRINT_REUSE_WINDOW == timedelta(days=30)
