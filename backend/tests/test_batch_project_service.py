"""批量建项服务 Property-Based Tests + 单元测试。

Feature: project-creation-enhancement
Properties 10-11 + unit tests
"""

import uuid

import pytest
import pytest_asyncio
import hypothesis.strategies as st
from hypothesis import given, settings, HealthCheck
from openpyxl import Workbook
from io import BytesIO
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.services.uscc_validator import (
    USCC_CHARSET,
    _CHAR_TO_VALUE,
    _WEIGHTS,
    validate_uscc,
)
from app.services.batch_project_service import (
    BatchImportResult,
    BatchValidateResponse,
    generate_template,
    parse_and_import,
    validate_batch,
    export_projects,
    _TEMPLATE_COLUMNS,
)


# ---------------------------------------------------------------------------
# 辅助：构造合法 USCC
# ---------------------------------------------------------------------------

def _compute_check_digit(prefix: str) -> str:
    """根据 17 位前缀计算第 18 位校验码字符。"""
    total = 0
    for i in range(17):
        total += _CHAR_TO_VALUE[prefix[i]] * _WEIGHTS[i]
    remainder = total % 31
    check_digit = 31 - remainder
    if check_digit == 31:
        check_digit = 0
    return USCC_CHARSET[check_digit]


def make_valid_uscc(prefix_17: str) -> str:
    """从 17 位前缀构造合法 18 位 USCC。"""
    return prefix_17 + _compute_check_digit(prefix_17)


FIXED_USCC_PREFIX = "91110000710931130"
FIXED_USCC = make_valid_uscc(FIXED_USCC_PREFIX)


# ---------------------------------------------------------------------------
# DB Fixtures（in-memory SQLite）
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def engine():
    """创建测试用 in-memory SQLite 引擎。"""
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
    if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
        SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """创建独立的 DB session。"""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# 辅助：创建包含数据行的 Excel 文件
# ---------------------------------------------------------------------------

def _make_import_excel(rows: list[list]) -> bytes:
    """构造包含给定数据行的 Excel 文件 bytes。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append(_TEMPLATE_COLUMNS)
    for row in rows:
        ws.append(row)
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Property 10: 批量导入结果计数一致性
# **Validates: Requirements 5.6**
#
# For any batch import file with N rows, success_count + fail_count == N,
# and len(failures) == fail_count.
# ---------------------------------------------------------------------------

# Strategy: generate N rows with mix of valid/invalid data
_uscc_prefix_st = st.text(alphabet=USCC_CHARSET, min_size=17, max_size=17)


@given(
    n_valid=st.integers(min_value=0, max_value=3),
    n_invalid=st.integers(min_value=0, max_value=3),
    prefix=_uscc_prefix_st,
)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_batch_import_count_consistency(n_valid: int, n_invalid: int, prefix: str, engine):
    """Property 10: success_count + fail_count == N, len(failures) == fail_count."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    rows: list[list] = []

    # Generate valid rows with unique USCCs
    for i in range(n_valid):
        # Ensure unique USCC per row by modifying prefix suffix
        p = prefix[:15] + USCC_CHARSET[i % len(USCC_CHARSET)] + USCC_CHARSET[(i + 5) % len(USCC_CHARSET)]
        uscc = make_valid_uscc(p)
        rows.append([
            f"客户{i}",
            uscc,
            f"简称{i}",
            2090 + i,  # unique year to avoid collision
            "年报审计",
            "企业会计准则",
            "单户",
        ])

    # Generate invalid rows (empty company_code)
    for i in range(n_invalid):
        rows.append([
            f"无效客户{i}",
            "",  # empty USCC → fail
            f"无效简称{i}",
            2025,
            "年报审计",
            "企业会计准则",
            "单户",
        ])

    if not rows:
        return  # N=0, nothing to test

    file_bytes = _make_import_excel(rows)

    async with factory() as db:
        result = await parse_and_import(file_bytes, db)

    total_rows = n_valid + n_invalid
    assert result.success_count + result.fail_count == total_rows
    assert len(result.failures) == result.fail_count


# ---------------------------------------------------------------------------
# Property 11: 批量导出/导入回环解析
# **Validates: Requirements 5.8, 5.9**
#
# For any set of existing projects, exporting them to Excel and then parsing
# that Excel through the batch import parser SHALL successfully parse every row.
# ---------------------------------------------------------------------------

@given(prefix=_uscc_prefix_st)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_export_import_round_trip(prefix: str, engine):
    """Property 11: Export → re-parse → all rows parseable (field structure compatible)."""
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.project_wizard_service import create_project

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        # Create a project
        uscc = make_valid_uscc(prefix)
        data = BasicInfoSchema(
            client_name="回环测试客户",
            audit_year=2060,
            project_type="annual",
            accounting_standard="enterprise",
            company_code=uscc,
            short_name="回环简称",
            report_scope="standalone",
        )
        project = await create_project(data, db)

        # Export
        export_output = await export_projects([project.id], db)
        export_bytes = export_output.getvalue()

    # 验证导出 Excel 列值正确（包括 accounting_standard 中文反映射）
    from openpyxl import load_workbook as _load_wb
    _wb = _load_wb(BytesIO(export_bytes), read_only=True)
    _ws = _wb["数据"]
    _exported_row = list(_ws.iter_rows(min_row=2, max_row=2, values_only=True))[0]
    assert _exported_row[0] == "回环测试客户"  # 客户名称
    assert _exported_row[2] == "回环简称"  # 项目简称
    assert _exported_row[5] == "企业会计准则"  # accounting_standard 正确反映射
    assert _exported_row[6] == "单户"  # report_scope 正确反映射

    # Parse the exported file in a fresh session (to avoid uniqueness collision,
    # we test that parsing succeeds structurally by checking no format errors)
    async with factory() as db2:
        # The exported file will fail uniqueness (same project exists),
        # but the parsing itself should work — we verify the errors are
        # ONLY uniqueness-related, not format/structure errors.
        result = await parse_and_import(export_bytes, db2)

        # Every row should be parseable: either success (if unique) or
        # uniqueness error (not a parsing/format error)
        for failure in result.failures:
            for err in failure.errors:
                # Structure/format errors would mention things like:
                # "为必填项", "格式错误", "无效"
                # Uniqueness errors mention "已存在"
                assert "已存在" in err, (
                    f"Round-trip produced non-uniqueness error: {err}"
                )


# ---------------------------------------------------------------------------
# Unit Test: 空文件
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_file_returns_zero(db_session):
    """Empty Excel (no data rows) → success=0, fail=0."""
    file_bytes = _make_import_excel([])
    result = await parse_and_import(file_bytes, db_session)
    assert result.success_count == 0
    assert result.fail_count == 0
    assert result.failures == []


# ---------------------------------------------------------------------------
# Unit Test: 全部无效行
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_invalid_rows(db_session):
    """All rows invalid → fail_count == row count, success_count == 0.
    Note: fully empty rows are skipped (not counted as failures).
    """
    rows = [
        ["有客户名", "INVALID_USCC", "", "abc", "无效类型", "无效准则", "无效范围"],
        ["客户", "12345", "简称", "2025", "年报审计", "企业会计准则", "单户"],  # USCC too short
        ["客户B", "", "简称B", "2025", "年报审计", "企业会计准则", "单户"],  # empty USCC
    ]
    file_bytes = _make_import_excel(rows)
    result = await parse_and_import(file_bytes, db_session)
    assert result.success_count == 0
    assert result.fail_count == 3
    assert len(result.failures) == 3


# ---------------------------------------------------------------------------
# Unit Test: 混合有效/无效行
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_valid_invalid(db_session):
    """Mix of valid and invalid rows → correct counts."""
    uscc1 = make_valid_uscc("91320000715837650")
    rows = [
        # Valid row
        ["好客户", uscc1, "好简称", 2025, "年报审计", "企业会计准则", "单户"],
        # Invalid row (no short_name)
        ["另一客户", FIXED_USCC, "", 2025, "年报审计", "企业会计准则", ""],
    ]
    file_bytes = _make_import_excel(rows)
    result = await parse_and_import(file_bytes, db_session)
    assert result.success_count == 1
    assert result.fail_count == 1
    assert result.failures[0].row_number == 3  # row 3 (header is row 1, data starts row 2)
    assert "项目简称为必填项" in result.failures[0].errors


# ---------------------------------------------------------------------------
# Unit Test: generate_template 结构验证
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_template_structure():
    """Template has correct sheets and column headers."""
    from openpyxl import load_workbook

    output = await generate_template()
    wb = load_workbook(output)

    assert "数据" in wb.sheetnames
    assert "说明事项" in wb.sheetnames

    ws_data = wb["数据"]
    headers = [cell.value for cell in ws_data[1]]
    assert headers == _TEMPLATE_COLUMNS


# ---------------------------------------------------------------------------
# Unit Test: generate_template 集团架构两列 + 说明事项规则（Task 7.1）
# **Validates: Requirements 6.1, 6.2, 6.3**
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_template_group_columns_and_rules():
    """Template 数据 header 含集团架构两列，说明事项含两字段填写规则，数据表含示例行。"""
    from openpyxl import load_workbook

    output = await generate_template()
    wb = load_workbook(BytesIO(output.getvalue()))

    # Req 6.1: 数据 header 末尾追加两列
    ws_data = wb["数据"]
    headers = [cell.value for cell in ws_data[1]]
    assert headers[-2] == "上级企业代码(parent)"
    assert headers[-1] == "最终控制方代码(ultimate)"
    assert len(headers) == 9

    # Req 6.2: 说明事项 sheet 含两字段填写规则 + 18 位 USCC 格式要求
    ws_notes = wb["说明事项"]
    notes_text = "\n".join(
        str(cell)
        for row in ws_notes.iter_rows(values_only=True)
        for cell in row
        if cell is not None
    )
    assert "上级企业代码(parent)" in notes_text
    assert "最终控制方代码(ultimate)" in notes_text
    assert "18位统一社会信用代码" in notes_text
    # 字段为选填
    assert "选填" in notes_text

    # Req 6.3: 数据表提供示例数据行展示集团层级（最终控制方→上级→子公司）
    data_rows = list(ws_data.iter_rows(min_row=2, values_only=True))
    # 至少一行示例，且每行宽度与 header 一致（9 列）
    assert len(data_rows) >= 1
    for r in data_rows:
        assert len(r) == 9
    # 示例行中存在自引用最终控制方（顶层）与子公司指向上级的层级关系
    ultimate_codes = {r[8] for r in data_rows}
    parent_codes = {r[7] for r in data_rows if r[7]}
    company_codes = {r[1] for r in data_rows}
    # 子公司的上级代码应指向同批次中某企业的企业代码（构成层级）
    assert parent_codes & company_codes


# ===========================================================================
# validate_batch 测试（group-tree-architecture Task 7.2）
# Requirements: 8.1, 8.2, 8.3, 8.4, 7.3, 7.6
# ===========================================================================

# 构造三个互不相同的合法 USCC 用于集团层级测试
_USCC_ULTIMATE = make_valid_uscc("91110000100000000")
_USCC_PARENT = make_valid_uscc("91110000200000000")
_USCC_CHILD = make_valid_uscc("91110000300000000")


def _row(client, code, short, year, parent="", ultimate=""):
    """构造 9 列数据行（与 _TEMPLATE_COLUMNS 对齐）。"""
    return [client, code, short, year, "年报审计", "企业会计准则", "单户", parent, ultimate]


async def _count_projects(db) -> int:
    from sqlalchemy import func, select as _select
    from app.models.core import Project
    res = await db.execute(_select(func.count()).select_from(Project))
    return res.scalar_one()


# ---------------------------------------------------------------------------
# (a) 有效批次 → valid=True，tree_preview 有预期结构
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_batch_valid(db_session):
    """有效批次：无错误，valid=True，tree_preview 含集团树。"""
    rows = [
        # 最终控制方（合并，自引 ultimate）
        _row("集团有限公司", _USCC_ULTIMATE, "集团", 2025, "", _USCC_ULTIMATE),
        # 子公司（parent 指向 ultimate）
        _row("子公司有限公司", _USCC_CHILD, "子公司", 2025, _USCC_ULTIMATE, _USCC_ULTIMATE),
    ]
    file_bytes = _make_import_excel(rows)
    resp = await validate_batch(file_bytes, db_session)

    assert isinstance(resp, BatchValidateResponse)
    assert resp.valid is True
    assert resp.total_rows == 2
    assert resp.errors == []
    # tree_preview 应含一棵以 ultimate 为根的集团树
    assert len(resp.tree_preview) >= 1
    group = next(t for t in resp.tree_preview if t["ultimateCode"] == _USCC_ULTIMATE)
    assert group["children"]  # 根节点存在


# ---------------------------------------------------------------------------
# (b) 重复 company_code → valid=False + 报重复行号（Req 7.6）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_batch_duplicate_company_code(db_session):
    """同批次重复 company_code → valid=False，错误含重复行号。"""
    rows = [
        _row("公司A", _USCC_PARENT, "简称A", 2025, "", _USCC_ULTIMATE),
        _row("公司B", _USCC_PARENT, "简称B", 2025, "", _USCC_ULTIMATE),  # 与上行重复
    ]
    file_bytes = _make_import_excel(rows)
    resp = await validate_batch(file_bytes, db_session)

    assert resp.valid is False
    # 两行（row 2、row 3）都应报重复
    err_rows = {e.row_number for e in resp.errors}
    assert 2 in err_rows and 3 in err_rows
    all_errs = "\n".join(e for re in resp.errors for e in re.errors)
    assert "重复" in all_errs
    # 重复消息应含对方行号
    assert "2" in all_errs and "3" in all_errs


# ---------------------------------------------------------------------------
# (c) 非法 USCC → valid=False + 格式错误（Req 7.3, 8.4）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_batch_invalid_uscc(db_session):
    """非法 company_code 格式 → valid=False，errors 含格式错误。"""
    rows = [
        _row("公司X", "INVALID123", "简称X", 2025, "", ""),  # 非 18 位
    ]
    file_bytes = _make_import_excel(rows)
    resp = await validate_batch(file_bytes, db_session)

    assert resp.valid is False
    assert len(resp.errors) == 1
    assert resp.errors[0].row_number == 2
    assert any("18" in e or "代码" in e for e in resp.errors[0].errors)


@pytest.mark.asyncio
async def test_validate_batch_invalid_parent_ultimate_uscc(db_session):
    """非法 parent/ultimate 代码 → valid=False，errors 含格式错误。"""
    rows = [
        _row("公司Y", _USCC_CHILD, "简称Y", 2025, "BADPARENT", "BADULTIMATE"),
    ]
    file_bytes = _make_import_excel(rows)
    resp = await validate_batch(file_bytes, db_session)

    assert resp.valid is False
    errs = resp.errors[0].errors
    assert any("上级企业代码" in e for e in errs)
    assert any("最终控制方代码" in e for e in errs)


# ---------------------------------------------------------------------------
# (d) DB count 不变（Property 13 — dry-run 不入库）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_batch_no_persistence(db_session):
    """validate_batch 调用后 DB project count 不变（Property 13）。"""
    before = await _count_projects(db_session)
    rows = [
        _row("集团有限公司", _USCC_ULTIMATE, "集团", 2025, "", _USCC_ULTIMATE),
        _row("子公司有限公司", _USCC_CHILD, "子公司", 2025, _USCC_ULTIMATE, _USCC_ULTIMATE),
    ]
    file_bytes = _make_import_excel(rows)
    await validate_batch(file_bytes, db_session)
    after = await _count_projects(db_session)
    assert before == after == 0


# ---------------------------------------------------------------------------
# (e) 批次内 parent-child → 嵌套 tree_preview（Req 7.2）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_batch_intra_batch_parent_child_nested(db_session):
    """批次内 A.parent = B.company_code → tree_preview 中 A 是 B 的后代。"""
    rows = [
        # ultimate 根
        _row("集团", _USCC_ULTIMATE, "集团", 2025, "", _USCC_ULTIMATE),
        # parent（挂在 ultimate 下）
        _row("中间控股", _USCC_PARENT, "中间", 2025, _USCC_ULTIMATE, _USCC_ULTIMATE),
        # child（parent 指向中间控股）
        _row("子公司", _USCC_CHILD, "子公司", 2025, _USCC_PARENT, _USCC_ULTIMATE),
    ]
    file_bytes = _make_import_excel(rows)
    resp = await validate_batch(file_bytes, db_session)

    assert resp.valid is True
    group = next(t for t in resp.tree_preview if t["ultimateCode"] == _USCC_ULTIMATE)

    # 收集所有节点 code → 找出 child 的祖先链
    def _find(node, code):
        if node["companyCode"] == code:
            return node
        for c in node["children"]:
            found = _find(c, code)
            if found:
                return found
        return None

    root = group["children"][0]  # ultimate 根节点
    assert root["companyCode"] == _USCC_ULTIMATE
    parent_node = _find(root, _USCC_PARENT)
    assert parent_node is not None
    child_node = _find(parent_node, _USCC_CHILD)
    assert child_node is not None  # child 是 parent 的后代


# ===========================================================================
# parse_and_import 三代码扩展测试（group-tree-architecture Task 8.1）
# Requirements: 7.1, 7.2, 7.4, 7.5
# ===========================================================================

async def _get_project_by_code(db, code: str):
    """按 company_code 查询单个未删除项目（测试辅助）。"""
    from sqlalchemy import select as _select
    from app.models.core import Project
    res = await db.execute(
        _select(Project).where(
            Project.company_code == code,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    return res.scalars().first()


# ---------------------------------------------------------------------------
# (a) parent/ultimate 代码持久化到 Project（Req 7.1）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_and_import_persists_group_codes(engine):
    """导入后 parent_company_code / ultimate_company_code 持久化到 Project。"""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    rows = [
        # ultimate 根（合并，自引）
        _row("集团有限公司", _USCC_ULTIMATE, "集团", 2025, "", _USCC_ULTIMATE),
        # 子公司（parent 指向 ultimate）
        _row("子公司有限公司", _USCC_CHILD, "子公司", 2025, _USCC_ULTIMATE, _USCC_ULTIMATE),
    ]
    file_bytes = _make_import_excel(rows)

    async with factory() as db:
        result = await parse_and_import(file_bytes, db)
        assert result.success_count == 2

    async with factory() as db:
        child = await _get_project_by_code(db, _USCC_CHILD)
        assert child is not None
        assert child.parent_company_code == _USCC_ULTIMATE
        assert child.ultimate_company_code == _USCC_ULTIMATE


# ---------------------------------------------------------------------------
# (b) 批次内 A.parent = B.company_code → A.parent_project_id == B.id（Req 7.2）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_and_import_intra_batch_parent_link(engine):
    """同批次内 A.parent 指向 B.company_code → A.parent_project_id == B.id。"""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    rows = [
        # ultimate 根（合并）
        ["集团", _USCC_ULTIMATE, "集团", 2025, "年报审计", "企业会计准则",
         "合并", "", _USCC_ULTIMATE],
        # 中间控股（parent 指向 ultimate）
        _row("中间控股", _USCC_PARENT, "中间", 2025, _USCC_ULTIMATE, _USCC_ULTIMATE),
        # 子公司（parent 指向中间控股，B 尚未入库时引用）
        _row("子公司", _USCC_CHILD, "子公司", 2025, _USCC_PARENT, _USCC_ULTIMATE),
    ]
    file_bytes = _make_import_excel(rows)

    async with factory() as db:
        result = await parse_and_import(file_bytes, db)
        assert result.success_count == 3

    async with factory() as db:
        parent_proj = await _get_project_by_code(db, _USCC_PARENT)
        child_proj = await _get_project_by_code(db, _USCC_CHILD)
        assert parent_proj is not None and child_proj is not None
        # child.parent_project_id 指向 parent（同批次互引）
        assert child_proj.parent_project_id == parent_proj.id
        # parent.parent_project_id 指向 ultimate 根
        ultimate_proj = await _get_project_by_code(db, _USCC_ULTIMATE)
        assert parent_proj.parent_project_id == ultimate_proj.id


# ---------------------------------------------------------------------------
# (c) ultimate 无对应 consolidated 项目 → 自动创建合并根（Req 7.4）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_and_import_auto_creates_consolidated_root(engine):
    """ultimate 对应 consolidated 项目不存在 → 自动创建 report_scope='consolidated' 根。"""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # 只导入一个子公司，ultimate 指向一个未入库的最终控制方
    rows = [
        _row("子公司有限公司", _USCC_CHILD, "子公司", 2025, "", _USCC_ULTIMATE),
    ]
    file_bytes = _make_import_excel(rows)

    async with factory() as db:
        result = await parse_and_import(file_bytes, db)
        assert result.success_count == 1  # 自动合并根不计入 success_count

    async with factory() as db:
        root = await _get_project_by_code(db, _USCC_ULTIMATE)
        assert root is not None
        assert root.report_scope == "consolidated"
        assert root.ultimate_company_code == _USCC_ULTIMATE
        # 子公司 parent_project_id 应指向自动创建的合并根
        child = await _get_project_by_code(db, _USCC_CHILD)
        # 子公司 parent 为空（未填上级），故不应链接到根
        assert child.parent_company_code in (None, "")


# ---------------------------------------------------------------------------
# (d) ultimate 已有 consolidated 根 → 不重复创建（批次内自引根）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_and_import_no_duplicate_consolidated_root(engine):
    """批次内已含 company_code==ultimate 的合并根 → 不再额外自动创建。"""
    from sqlalchemy import select as _select, func as _func
    from app.models.core import Project

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    rows = [
        # 合并根本身在批次中（report_scope=合并/consolidated，自引 ultimate）
        ["集团有限公司", _USCC_ULTIMATE, "集团", 2025, "年报审计", "企业会计准则",
         "合并", "", _USCC_ULTIMATE],
        _row("子公司有限公司", _USCC_CHILD, "子公司", 2025, _USCC_ULTIMATE, _USCC_ULTIMATE),
    ]
    file_bytes = _make_import_excel(rows)

    async with factory() as db:
        result = await parse_and_import(file_bytes, db)
        assert result.success_count == 2

    async with factory() as db:
        # ultimate code 对应的项目只有一个（不重复创建）
        res = await db.execute(
            _select(_func.count()).select_from(Project).where(
                Project.company_code == _USCC_ULTIMATE,
                Project.is_deleted == False,  # noqa: E712
            )
        )
        assert res.scalar_one() == 1


# ===========================================================================
# Property-Based Tests (hypothesis) — group-tree-architecture
# Tasks 7.4 (Property 11), 7.5 (Property 12), 7.6 (Property 13),
#       7.7 (Property 14), 8.2 (Property 16)
# hypothesis 统一 max_examples=5（项目铁律，禁默认 100）
# ===========================================================================

# USCC 禁用字符（设计：排除 I / O / Z / S / V）
_FORBIDDEN_USCC_CHARS = "IOZSV"


# ---------------------------------------------------------------------------
# Feature: group-tree-architecture, Property 11: USCC format validation
# Validates: Requirements 7.3
#
# 复用现有 uscc_validator.validate_uscc：合规 18 字符 → True；
# 含 I/O/Z/S/V 或长度≠18 → False。
# ---------------------------------------------------------------------------

# 合法 18 位 USCC（由 17 位前缀 + 计算校验位构成）
_valid_uscc_st = _uscc_prefix_st.map(make_valid_uscc)


@given(prefix=_uscc_prefix_st)
@settings(max_examples=5)
def test_property11_valid_uscc_accepted(prefix: str):
    """Property 11（正向）：任意合法 18 位 USCC → validate_uscc 返回 True。"""
    code = make_valid_uscc(prefix)
    is_valid, err = validate_uscc(code)
    assert is_valid is True, f"合法 USCC {code} 被拒：{err}"
    assert err is None


@given(
    prefix=_uscc_prefix_st,
    pos=st.integers(min_value=0, max_value=17),
    bad_char=st.sampled_from(_FORBIDDEN_USCC_CHARS),
)
@settings(max_examples=5)
def test_property11_forbidden_char_rejected(prefix: str, pos: int, bad_char: str):
    """Property 11（反向-字符集）：在合法 USCC 中插入禁用字符 I/O/Z/S/V → False。"""
    code = make_valid_uscc(prefix)
    tampered = code[:pos] + bad_char + code[pos + 1:]
    assert len(tampered) == 18
    is_valid, err = validate_uscc(tampered)
    assert is_valid is False, f"含禁用字符 {bad_char} 的 {tampered} 应被拒"
    assert err is not None


@given(
    prefix=_uscc_prefix_st,
    extra=st.text(alphabet=USCC_CHARSET, min_size=1, max_size=4),
)
@settings(max_examples=5)
def test_property11_wrong_length_rejected(prefix: str, extra: str):
    """Property 11（反向-长度）：长度 ≠ 18 → False。"""
    code = make_valid_uscc(prefix)
    # 过长
    too_long, err1 = validate_uscc(code + extra)
    assert too_long is False and err1 is not None
    # 过短
    too_short, err2 = validate_uscc(code[: 18 - len(extra) - 1])
    assert too_short is False and err2 is not None


# ---------------------------------------------------------------------------
# Feature: group-tree-architecture, Property 12: Batch duplicate detection
# Validates: Requirements 7.6
#
# 含重复 company_code 的批次 → validate_batch valid=False，
# 且重复行的 errors 含"重复" + 涉及行号。
# ---------------------------------------------------------------------------

@given(
    prefix=_uscc_prefix_st,
    n_dup=st.integers(min_value=2, max_value=3),
)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_property12_batch_duplicate_detection(prefix: str, n_dup: int, engine):
    """Property 12：n_dup 行共用同一 company_code → valid=False 且报全部重复行号。"""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    dup_code = make_valid_uscc(prefix)
    rows = [
        _row(f"重复公司{i}", dup_code, f"简称{i}", 2025, "", dup_code)
        for i in range(n_dup)
    ]

    file_bytes = _make_import_excel(rows)
    async with factory() as db:
        resp = await validate_batch(file_bytes, db)

    assert resp.valid is False
    # 重复行号为 data 行 2..(n_dup+1)（header=row1）
    expected_rows = set(range(2, 2 + n_dup))
    err_rows = {e.row_number for e in resp.errors}
    assert expected_rows <= err_rows, f"期望重复行 {expected_rows} ⊆ {err_rows}"
    # 每个重复行的错误信息应提及"重复"
    dup_errs = [
        e for e in resp.errors if e.row_number in expected_rows
    ]
    for re_ in dup_errs:
        assert any("重复" in msg for msg in re_.errors)
    # 重复消息含其它重复行号（互引）
    all_msgs = "\n".join(m for e in dup_errs for m in e.errors)
    for rn in expected_rows:
        assert str(rn) in all_msgs


# ---------------------------------------------------------------------------
# Feature: group-tree-architecture, Property 13: Batch validation dry-run (no persistence)
# Validates: Requirements 8.1
#
# 任意批次（合法/非法混合）经 validate_batch 后，DB project count 不变。
# ---------------------------------------------------------------------------

@given(
    prefix=_uscc_prefix_st,
    n_valid=st.integers(min_value=0, max_value=2),
    n_invalid=st.integers(min_value=0, max_value=2),
)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_property13_validate_batch_no_persistence(
    prefix: str, n_valid: int, n_invalid: int, engine
):
    """Property 13：validate_batch 是 dry-run，调用前后 DB project count 不变。"""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    rows: list[list] = []
    for i in range(n_valid):
        p = prefix[:15] + USCC_CHARSET[i % len(USCC_CHARSET)] + USCC_CHARSET[(i + 7) % len(USCC_CHARSET)]
        code = make_valid_uscc(p)
        rows.append(_row(f"有效{i}", code, f"简称{i}", 2080 + i, "", code))
    for i in range(n_invalid):
        rows.append(_row(f"无效{i}", "BADCODE", f"无效简称{i}", 2025, "", ""))

    file_bytes = _make_import_excel(rows)

    async with factory() as db:
        before = await _count_projects(db)
        await validate_batch(file_bytes, db)
        after = await _count_projects(db)
        assert before == after, "validate_batch 不应写库（dry-run）"


# ---------------------------------------------------------------------------
# Feature: group-tree-architecture, Property 14: Batch validation error blocking
# Validates: Requirements 8.2, 8.4
#
# 含非法 company_code 行（格式错误/禁用字符/长度错误）→ valid=False，
# errors 非空，且该非法行有对应错误明细。
# ---------------------------------------------------------------------------

# 非法 company_code 生成器：长度错误 或 含禁用字符
def _bad_code_strategies():
    # 长度错误（短）
    short = st.text(alphabet=USCC_CHARSET, min_size=1, max_size=17)
    # 含禁用字符（构造 18 位但塞入 I/O/Z/S/V）
    with_forbidden = st.builds(
        lambda pfx, pos, ch: (lambda c: c[:pos] + ch + c[pos + 1:])(make_valid_uscc(pfx)),
        _uscc_prefix_st,
        st.integers(min_value=0, max_value=17),
        st.sampled_from(_FORBIDDEN_USCC_CHARS),
    )
    return st.one_of(short, with_forbidden)


@given(
    good_prefix=_uscc_prefix_st,
    bad_code=_bad_code_strategies(),
    bad_position=st.integers(min_value=0, max_value=1),
)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_property14_invalid_code_blocks_batch(
    good_prefix: str, bad_code: str, bad_position: int, engine
):
    """Property 14：批次含至少一非法 company_code 行 → valid=False + 该行有错误明细。"""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    good_code = make_valid_uscc(good_prefix)
    good_row = _row("合规公司", good_code, "合规简称", 2025, "", good_code)
    bad_row = _row("违规公司", bad_code, "违规简称", 2025, "", "")

    # 非法行放第一或第二位
    rows = [bad_row, good_row] if bad_position == 0 else [good_row, bad_row]
    bad_row_number = 2 if bad_position == 0 else 3

    file_bytes = _make_import_excel(rows)
    async with factory() as db:
        resp = await validate_batch(file_bytes, db)

    assert resp.valid is False, "含非法行的批次必须 valid=False"
    assert resp.errors, "errors 必须非空"
    # 非法行有对应错误明细
    bad_err = next((e for e in resp.errors if e.row_number == bad_row_number), None)
    assert bad_err is not None and bad_err.errors, "非法行应有错误明细"


# ---------------------------------------------------------------------------
# Feature: group-tree-architecture, Property 16: Batch intra-batch parent-child resolution
# Validates: Requirements 7.1, 7.2
#
# 批次内 A.parent = B.company_code → parse_and_import 后 A.parent_project_id == B.id。
# ---------------------------------------------------------------------------

@given(
    seed=st.integers(min_value=0, max_value=20),
    year=st.integers(min_value=2050, max_value=2099),
)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_property16_intra_batch_parent_child(seed: int, year: int, engine):
    """Property 16：A.parent = B.company_code（同批次）→ 导入后 A.parent_project_id == B.id。"""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 用不同前缀构造两个互不相同的合法 USCC（B 为根/parent，A 为子）
    pb = f"9111000000{seed:07d}"  # 17 位
    pa = f"9122000000{seed:07d}"
    code_b = make_valid_uscc(pb)
    code_a = make_valid_uscc(pa)
    assert code_a != code_b

    rows = [
        # B：最终控制方根（合并，自引 ultimate）
        ["集团B", code_b, "集团B", year, "年报审计", "企业会计准则", "合并", "", code_b],
        # A：parent 指向 B.company_code，同 ultimate
        _row("子公司A", code_a, "子公司A", year, code_b, code_b),
    ]
    file_bytes = _make_import_excel(rows)

    async with factory() as db:
        result = await parse_and_import(file_bytes, db)
        assert result.success_count == 2, result.failures

    async with factory() as db:
        proj_a = await _get_project_by_code(db, code_a)
        proj_b = await _get_project_by_code(db, code_b)
        assert proj_a is not None and proj_b is not None
        # A 是 B 的子节点：parent_project_id 指向 B
        assert proj_a.parent_project_id == proj_b.id
        assert proj_a.parent_company_code == code_b
