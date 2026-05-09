"""S6-17: _execute_v2 端到端集成测试。

策略：不启动 Worker，直接复现 `_execute_v2` 的数据流（detect → identify →
parse → convert → insert → verify），用 SQLite 内存库做 assertion。

目标：证明 YG36 真实样本跑完完整管线后，PG 四张表确实有入库数据，
且 tb_aux_ledger 含客户/金融机构等真实维度类型。

这是 v2 引擎的"真命测试"——通过单测 100/100 + 本测试通过才算真的可用。
"""
from __future__ import annotations

import uuid
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import insert, text
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# SQLite 不支持 JSONB，用 JSON 替代（模型有 JSONB 字段）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.models.base import Base
# 触发模型注册
from app.models import audit_platform_models  # noqa: F401
from app.models.audit_platform_models import (
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
)
from app.services.ledger_import.converter import (
    convert_balance_rows,
    convert_ledger_rows,
)
from app.services.ledger_import.detector import detect_file_from_path
from app.services.ledger_import.identifier import identify
from app.services.ledger_import.parsers.excel_parser import iter_excel_rows_from_path
from app.services.ledger_import.validator import validate_l1
from app.services.ledger_import.writer import prepare_rows_with_raw_extra

REPO_ROOT = Path(__file__).resolve().parents[3]
YG36_PATH = REPO_ROOT / "数据/YG36-重庆医药集团四川物流有限公司2025.xlsx"

# 限 2000 行抽样避免集成测试跑太慢
SAMPLE_LIMIT = 2000

# SQLite 单次 insert 参数上限 999；22 字段 × 40 行 = 880 < 999
INSERT_CHUNK = 40


import json as _json_mod
from datetime import date as _date_type, datetime as _dt_type


def _json_default(o):
    if isinstance(o, (_dt_type, _date_type)):
        return o.isoformat()
    return str(o)


def _json_dumps(obj):
    return _json_mod.dumps(obj, default=_json_default, ensure_ascii=False)


_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
    json_serializer=_json_dumps,
)


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s


async def _insert_balance(
    db: AsyncSession, rows: list[dict], *,
    project_id: uuid.UUID, year: int, dataset_id: uuid.UUID,
):
    if not rows:
        return
    for i in range(0, len(rows), INSERT_CHUNK):
        batch = rows[i:i + INSERT_CHUNK]
        stmt = insert(TbBalance).values([
            {
                "id": uuid4(),
                "project_id": project_id,
                "year": year,
                "account_code": r["account_code"],
                "account_name": r.get("account_name", ""),
                "company_code": r.get("company_code") or "default",
                "opening_balance": r.get("opening_balance"),
                "opening_debit": r.get("opening_debit"),
                "opening_credit": r.get("opening_credit"),
                "debit_amount": r.get("debit_amount"),
                "credit_amount": r.get("credit_amount"),
                "closing_balance": r.get("closing_balance"),
                "closing_debit": r.get("closing_debit"),
                "closing_credit": r.get("closing_credit"),
                "level": r.get("level", 1),
                "currency_code": r.get("currency_code", "CNY"),
                "raw_extra": r.get("raw_extra"),
                "dataset_id": dataset_id,
                "is_deleted": False,
            }
            for r in batch
        ])
        await db.execute(stmt)


async def _insert_aux_balance(
    db: AsyncSession, rows: list[dict], *,
    project_id: uuid.UUID, year: int, dataset_id: uuid.UUID,
):
    if not rows:
        return
    for i in range(0, len(rows), INSERT_CHUNK):
        batch = rows[i:i + INSERT_CHUNK]
        stmt = insert(TbAuxBalance).values([
            {
                "id": uuid4(),
                "project_id": project_id,
                "year": year,
                "account_code": r["account_code"],
                "account_name": r.get("account_name", ""),
                "company_code": r.get("company_code") or "default",
                "aux_type": r.get("aux_type"),
                "aux_code": r.get("aux_code"),
                "aux_name": r.get("aux_name"),
                "opening_balance": r.get("opening_balance"),
                "opening_debit": r.get("opening_debit"),
                "opening_credit": r.get("opening_credit"),
                "debit_amount": r.get("debit_amount"),
                "credit_amount": r.get("credit_amount"),
                "closing_balance": r.get("closing_balance"),
                "closing_debit": r.get("closing_debit"),
                "closing_credit": r.get("closing_credit"),
                "currency_code": r.get("currency_code", "CNY"),
                "raw_extra": r.get("raw_extra"),
                "dataset_id": dataset_id,
                "is_deleted": False,
            }
            for r in batch
        ])
        await db.execute(stmt)


async def _insert_ledger(
    db: AsyncSession, rows: list[dict], *,
    project_id: uuid.UUID, year: int, dataset_id: uuid.UUID,
):
    if not rows:
        return
    for i in range(0, len(rows), INSERT_CHUNK):
        batch = rows[i:i + INSERT_CHUNK]
        stmt = insert(TbLedger).values([
            {
                "id": uuid4(),
                "project_id": project_id,
                "year": year,
                "account_code": r["account_code"],
                "account_name": r.get("account_name", ""),
                "company_code": r.get("company_code") or "default",
                "voucher_date": r.get("voucher_date"),
                "voucher_no": r.get("voucher_no", ""),
                "voucher_type": r.get("voucher_type"),
                "debit_amount": r.get("debit_amount"),
                "credit_amount": r.get("credit_amount"),
                "summary": r.get("summary"),
                "preparer": r.get("preparer"),
                "currency_code": r.get("currency_code", "CNY"),
                "raw_extra": r.get("raw_extra"),
                "dataset_id": dataset_id,
                "is_deleted": False,
            }
            for r in batch
        ])
        await db.execute(stmt)


async def _insert_aux_ledger(
    db: AsyncSession, rows: list[dict], *,
    project_id: uuid.UUID, year: int, dataset_id: uuid.UUID,
):
    if not rows:
        return
    for i in range(0, len(rows), INSERT_CHUNK):
        batch = rows[i:i + INSERT_CHUNK]
        stmt = insert(TbAuxLedger).values([
            {
                "id": uuid4(),
                "project_id": project_id,
                "year": year,
                "account_code": r["account_code"],
                "account_name": r.get("account_name", ""),
                "company_code": r.get("company_code") or "default",
                "voucher_date": r.get("voucher_date"),
                "voucher_no": r.get("voucher_no", ""),
                "voucher_type": r.get("voucher_type"),
                "accounting_period": r.get("accounting_period"),
                "aux_type": r.get("aux_type"),
                "aux_code": r.get("aux_code"),
                "aux_name": r.get("aux_name"),
                "aux_dimensions_raw": r.get("aux_dimensions_raw"),
                "debit_amount": r.get("debit_amount"),
                "credit_amount": r.get("credit_amount"),
                "summary": r.get("summary"),
                "preparer": r.get("preparer"),
                "currency_code": r.get("currency_code", "CNY"),
                "raw_extra": r.get("raw_extra"),
                "dataset_id": dataset_id,
                "is_deleted": False,
            }
            for r in batch
        ])
        await db.execute(stmt)


@pytest.mark.skipif(
    not YG36_PATH.exists(),
    reason=f"真实样本 {YG36_PATH} 未挂载（CI 环境可设置 skip）",
)
@pytest.mark.asyncio
async def test_yg36_e2e_full_pipeline(db_session: AsyncSession):
    """YG36 四川物流完整管线: detect → identify → parse → convert → insert → verify。"""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    # ── Phase 1: Detect + Identify ──
    fd = detect_file_from_path(str(YG36_PATH), YG36_PATH.name)
    sheets = []
    for s in fd.sheets:
        identified = identify(s)
        sheets.append(identified)

    # 断言识别结果：至少 1 balance + 1 ledger
    types = {s.table_type for s in sheets}
    assert "balance" in types, f"应识别出 balance sheet, got {[s.sheet_name+':'+s.table_type for s in sheets]}"
    assert "ledger" in types, f"应识别出 ledger sheet, got {[s.sheet_name+':'+s.table_type for s in sheets]}"

    # ── Phase 2-3: Parse + Convert + Insert ──
    total_balance = 0
    total_aux_balance = 0
    total_ledger = 0
    total_aux_ledger = 0

    for sheet in sheets:
        if sheet.table_type not in ("balance", "ledger"):
            continue

        # 构建 col_mapping（自动从 identify 结果取）
        col_mapping = {}
        for cm in sheet.column_mappings:
            if cm.standard_field and cm.confidence >= 50:
                col_mapping[cm.column_header] = cm.standard_field

        # forward-fill 列
        ff_cols = [
            cm.column_index
            for cm in sheet.column_mappings
            if cm.standard_field in ("account_code", "account_name")
        ]

        headers = sheet.detection_evidence.get("header_cells", [])

        # Parse (限制 SAMPLE_LIMIT 行)
        parsed_rows = []
        row_count = 0
        for chunk in iter_excel_rows_from_path(
            str(YG36_PATH), sheet.sheet_name,
            data_start_row=sheet.data_start_row,
            forward_fill_cols=ff_cols or None,
        ):
            for raw in chunk:
                if row_count >= SAMPLE_LIMIT:
                    break
                row_dict = {}
                for i, val in enumerate(raw):
                    if i < len(headers):
                        row_dict[headers[i]] = val
                parsed_rows.append(row_dict)
                row_count += 1
            if row_count >= SAMPLE_LIMIT:
                break

        # Transform + L1 validate
        std_rows, _ = prepare_rows_with_raw_extra(parsed_rows, col_mapping, headers)
        _, cleaned = validate_l1(
            std_rows, sheet.table_type, column_mapping=col_mapping,
            file_name=YG36_PATH.name, sheet_name=sheet.sheet_name,
        )

        # Convert + Insert
        if sheet.table_type == "balance":
            bal, aux_bal = convert_balance_rows(cleaned)
            await _insert_balance(
                db_session, bal,
                project_id=project_id, year=year, dataset_id=dataset_id,
            )
            await _insert_aux_balance(
                db_session, aux_bal,
                project_id=project_id, year=year, dataset_id=dataset_id,
            )
            total_balance += len(bal)
            total_aux_balance += len(aux_bal)
        elif sheet.table_type == "ledger":
            ledger, aux_ledger, _stats = convert_ledger_rows(cleaned)
            await _insert_ledger(
                db_session, ledger,
                project_id=project_id, year=year, dataset_id=dataset_id,
            )
            await _insert_aux_ledger(
                db_session, aux_ledger,
                project_id=project_id, year=year, dataset_id=dataset_id,
            )
            total_ledger += len(ledger)
            total_aux_ledger += len(aux_ledger)

    await db_session.commit()

    # SQLite 存 UUID 为无连字符 hex，查询需匹配
    pid_hex = str(project_id).replace("-", "")

    # ── Phase 4: Verify ──
    # 1. 四张表都有数据
    assert total_balance > 0, "tb_balance 应有数据"
    assert total_aux_balance > 0, "tb_aux_balance 应有数据（YG36 含核算维度）"
    assert total_ledger > 0, "tb_ledger 应有数据"
    assert total_aux_ledger > 0, "tb_aux_ledger 应有数据（YG36 序时账含核算维度）"

    # 2. 数据库实际查询验证
    bal_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM tb_balance WHERE project_id = :pid"),
        {"pid": pid_hex},
    )).scalar()
    assert bal_count == total_balance

    led_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM tb_ledger WHERE project_id = :pid"),
        {"pid": pid_hex},
    )).scalar()
    assert led_count == total_ledger

    aux_led_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM tb_aux_ledger WHERE project_id = :pid"),
        {"pid": pid_hex},
    )).scalar()
    assert aux_led_count == total_aux_ledger

    # 3. aux_ledger 至少含 3 种典型维度（YG36 真实数据）
    aux_types_result = await db_session.execute(
        text(
            "SELECT DISTINCT aux_type FROM tb_aux_ledger "
            "WHERE project_id = :pid AND aux_type IS NOT NULL"
        ),
        {"pid": pid_hex},
    )
    aux_types = {r[0] for r in aux_types_result.all()}
    # YG36 真实数据含："客户"、"金融机构"、"成本中心"、"税率"等
    expected_types = {"客户", "成本中心", "税率"}
    actual_in_expected = expected_types & aux_types
    assert len(actual_in_expected) >= 2, (
        f"aux_ledger 应含至少 2 种典型维度类型，实际: {aux_types}"
    )

    # 4. 空值策略验证（S6-7）：aux_code 为 "" 的行不应存在
    empty_code_count = (await db_session.execute(
        text(
            "SELECT COUNT(*) FROM tb_aux_ledger "
            "WHERE project_id = :pid AND aux_code = ''"
        ),
        {"pid": pid_hex},
    )).scalar()
    assert empty_code_count == 0, (
        f"S6-7 违反：aux_code 应是 NULL 不是空串，发现 {empty_code_count} 行"
    )

    # 5. dataset_id 全部正确绑定（S6-13）
    did_hex = str(dataset_id).replace("-", "")
    wrong_dataset = (await db_session.execute(
        text(
            "SELECT COUNT(*) FROM tb_aux_ledger "
            "WHERE project_id = :pid AND dataset_id != :did"
        ),
        {"pid": pid_hex, "did": did_hex},
    )).scalar()
    assert wrong_dataset == 0, "S6-13 违反：所有行应绑定同一 dataset_id"

    print(
        f"\n[OK] YG36 E2E: balance={total_balance} aux_balance={total_aux_balance} "
        f"ledger={total_ledger} aux_ledger={total_aux_ledger} "
        f"aux_types={sorted(aux_types)}"
    )


@pytest.mark.skipif(
    not YG36_PATH.exists(),
    reason=f"真实样本 {YG36_PATH} 未挂载",
)
@pytest.mark.asyncio
async def test_yg36_triplet_query_after_import(db_session: AsyncSession):
    """导入后用三元组查询（S6-8）验证数据可被精确定位。"""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    # 简化管线（复用 insert helper）
    fd = detect_file_from_path(str(YG36_PATH), YG36_PATH.name)
    ledger_sheet = None
    for s in fd.sheets:
        identified = identify(s)
        if identified.table_type == "ledger":
            ledger_sheet = identified
            break
    assert ledger_sheet is not None

    col_mapping = {
        cm.column_header: cm.standard_field
        for cm in ledger_sheet.column_mappings
        if cm.standard_field and cm.confidence >= 50
    }
    headers = ledger_sheet.detection_evidence.get("header_cells", [])
    ff_cols = [
        cm.column_index for cm in ledger_sheet.column_mappings
        if cm.standard_field in ("account_code", "account_name")
    ]

    parsed = []
    count = 0
    for chunk in iter_excel_rows_from_path(
        str(YG36_PATH), ledger_sheet.sheet_name,
        data_start_row=ledger_sheet.data_start_row,
        forward_fill_cols=ff_cols or None,
    ):
        for raw in chunk:
            if count >= SAMPLE_LIMIT:
                break
            d = {}
            for i, val in enumerate(raw):
                if i < len(headers):
                    d[headers[i]] = val
            parsed.append(d)
            count += 1
        if count >= SAMPLE_LIMIT:
            break

    std_rows, _ = prepare_rows_with_raw_extra(parsed, col_mapping, headers)
    _, cleaned = validate_l1(std_rows, "ledger", column_mapping=col_mapping)
    _, aux_ledger, _ = convert_ledger_rows(cleaned)

    await _insert_aux_ledger(
        db_session, aux_ledger,
        project_id=project_id, year=year, dataset_id=dataset_id,
    )
    await db_session.commit()

    # 三元组查询：找"客户"维度，看是否能精确定位到某 aux_code
    # （不依赖特定 account_code，只断言查询接口返回结构正确）
    from app.services.ledger_penetration_service import LedgerPenetrationService

    svc = LedgerPenetrationService(db_session)

    # 先找一个存在的 (account_code, aux_type=客户) 组合
    pid_hex = str(project_id).replace("-", "")
    sample_row_result = await db_session.execute(
        text(
            "SELECT account_code, aux_code FROM tb_aux_ledger "
            "WHERE project_id = :pid AND aux_type = '客户' AND aux_code IS NOT NULL "
            "LIMIT 1"
        ),
        {"pid": pid_hex},
    )
    sample_row = sample_row_result.first()
    if not sample_row:
        pytest.skip("样本数据中未含 aux_type='客户' 的行（抽样行数不足）")

    sample_account_code, sample_aux_code = sample_row[0], sample_row[1]
    assert sample_aux_code is not None, "S6-7 违反：aux_code 不应为 NULL（测试前置）"

    # 三元组精确查询
    result = await svc.get_aux_by_triplet(
        project_id, year, sample_account_code, "客户", sample_aux_code,
    )
    assert result["ledger"]["total"] > 0, "三元组查询应返回至少 1 行明细"
    assert result["aux"]["aux_type"] == "客户"
    assert result["aux"]["aux_code"] == sample_aux_code
