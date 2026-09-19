"""单元测试：_prefill_word_template 增强版占位符替换

验证 task 2.1 + 2.2 的全部要求：
1. 新增 token 支持：entity_name, period_end, preparer, current_date, client_name, audit_period, partner_name
2. period_end/current_date 格式：YYYY年MM月DD日
3. 空值保留：对应值为 None 时保留 {{token}} 不替换
4. 替换后记录审计日志 logger.info
5. 快照幂等：已有快照不重复预填
6. 原模板文件始终不修改

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""
from __future__ import annotations

import logging
import shutil
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 需要 python-docx
from docx import Document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_docx(tmp_path: Path, tokens: list[str]) -> Path:
    """创建含指定占位符 token 的临时 docx 文件。"""
    doc = Document()
    for token in tokens:
        doc.add_paragraph(f"前缀 {token} 后缀")
    fp = tmp_path / "test_template.docx"
    doc.save(str(fp))
    return fp


def _create_test_docx_with_table(tmp_path: Path, tokens: list[str]) -> Path:
    """创建含表格占位符的临时 docx 文件。"""
    doc = Document()
    doc.add_paragraph("标题段落")
    table = doc.add_table(rows=len(tokens), cols=2)
    for i, token in enumerate(tokens):
        table.rows[i].cells[0].text = f"字段{i}"
        table.rows[i].cells[1].text = token
    fp = tmp_path / "test_table_template.docx"
    doc.save(str(fp))
    return fp


def _extract_full_text(fp: Path) -> str:
    """从 docx 提取全部文本（段落+表格）。"""
    doc = Document(str(fp))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    parts.append(para.text)
    return "\n".join(parts)


def _make_mock_wp(file_path: str, wp_index_id=None) -> MagicMock:
    """创建 mock WorkingPaper 对象。"""
    wp = MagicMock()
    wp.file_path = file_path
    wp.wp_index_id = wp_index_id
    return wp


def _make_mock_user(user_id: uuid.UUID | None = None, username: str = "test_user") -> MagicMock:
    """创建 mock User 对象。"""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.username = username
    return user


def _make_mock_db(
    *,
    client_name: str | None = "北京测试科技有限公司",
    project_name: str | None = "测试项目",
    audit_period_end: date | None = date(2025, 12, 31),
    partner_name: str | None = "张合伙人",
    staff_name: str | None = "李助理",
    wp_code: str | None = None,
) -> AsyncMock:
    """创建 mock AsyncSession，根据 SQL 文本/stmt 返回不同结果。

    wp_code: 如果提供，WpIndex 查询返回此 wp_code；否则返回 None。
    """
    db = AsyncMock()

    async def _execute(stmt, params=None):
        # 处理 sa.select(WpIndex.wp_code) 调用
        sql_text = ""
        if hasattr(stmt, 'text'):
            sql_text = str(stmt.text)
        else:
            sql_text = str(stmt)

        # WpIndex.wp_code 查询（sa.select 生成的语句）
        if "wp_index" in sql_text.lower() and "wp_code" in sql_text.lower():
            result = MagicMock()
            result.scalar_one_or_none.return_value = wp_code
            return result

        if "SELECT name, client_name, audit_period_end FROM projects" in sql_text:
            result = MagicMock()
            if client_name or project_name or audit_period_end:
                row = MagicMock()
                row.__getitem__ = lambda self, i: [project_name, client_name, audit_period_end][i]
                result.first.return_value = row
            else:
                result.first.return_value = None
            return result

        if "project_assignments" in sql_text and "partner" in sql_text:
            result = MagicMock()
            if partner_name:
                row = MagicMock()
                row.__getitem__ = lambda self, i: [partner_name][i]
                result.first.return_value = row
            else:
                result.first.return_value = None
            return result

        if "staff_members" in sql_text and "user_id" in sql_text:
            result = MagicMock()
            if staff_name:
                row = MagicMock()
                row.__getitem__ = lambda self, i: [staff_name][i]
                result.first.return_value = row
            else:
                result.first.return_value = None
            return result

        # 默认返回空
        result = MagicMock()
        result.first.return_value = None
        result.scalar_one_or_none.return_value = None
        return result

    db.execute = _execute
    return db


# ---------------------------------------------------------------------------
# Tests: Token Replacement (task 2.1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_new_tokens_replaced(tmp_path: Path, monkeypatch) -> None:
    """所有新增 token 在有值时被正确替换。"""
    from app.routers.wp_editor_router import _prefill_word_template

    tokens = [
        "{{entity_name}}", "{{period_end}}", "{{preparer}}",
        "{{current_date}}", "{{client_name}}", "{{audit_period}}", "{{partner_name}}",
    ]
    fp = _create_test_docx(tmp_path, tokens)
    project_id = uuid.uuid4()

    # 使 snapshot_path 指向 tmp_path 下（通过 monkeypatch Path 构造）
    # 不使用 wp_index_id，wp_code 将 fallback 到 file_path.stem
    wp = _make_mock_wp(str(fp), wp_index_id=None)
    user = _make_mock_user()
    db = _make_mock_db()

    # monkeypatch snapshot_path 使其不存在（使用 tmp_path 子目录作为 storage root）
    snapshot_dir = tmp_path / "storage" / str(project_id) / "workpapers"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Patch Path 构造使 snapshot_path 落在 tmp_path 下
    original_path = Path

    def _patched_path_init(self, *args):
        """让 f"storage/{project_id}/workpapers/..." 重定向到 tmp_path 下"""
        pass  # not needed with monkeypatch approach

    # 更直接的方式：设置 wp.file_path 使 stem 已知，patch snapshot 检查
    # 由于函数内部用 Path(f"storage/{project_id}/workpapers/{wp_code}.docx")
    # 我们需要让这个路径在 tmp_path 下。最简单的方法是 monkeypatch。
    # 但实际上让 snapshot_path 不存在就行了—— storage/ 相对路径在测试 cwd 下不存在即可。
    # 确保 cwd 下不存在 storage/{project_id}/workpapers/ 目录

    # 清理防止之前测试残留
    import os
    target_snapshot = Path(f"storage/{project_id}/workpapers/test_template.docx")
    target_snapshot.parent.mkdir(parents=True, exist_ok=True)

    # 确保快照不存在
    if target_snapshot.exists():
        target_snapshot.unlink()

    try:
        result = await _prefill_word_template(db, wp, project_id, user=user)

        assert result is True
        # 读取快照文件（预填后内容写到 snapshot_path）
        text = _extract_full_text(target_snapshot)

        # 所有 token 都不应残留
        for token in tokens:
            assert token not in text, f"Token {token} 未被替换"

        # 验证实际值出现
        assert "北京测试科技有限公司" in text  # entity_name / client_name
        assert "2025年12月31日" in text  # period_end
        assert "李助理" in text  # preparer
        assert "张合伙人" in text  # partner_name
        # current_date 是动态的，验证格式
        today = date.today()
        expected_date = today.strftime("%Y年%m月%d日")
        assert expected_date in text  # current_date
        assert "2025-12-31" in text  # audit_period

        # 验证原模板未修改
        original_text = _extract_full_text(fp)
        for token in tokens:
            assert token in original_text, f"原模板中 {token} 不应被修改"
    finally:
        # 清理 snapshot
        if target_snapshot.exists():
            target_snapshot.unlink()
        # 清理创建的目录
        _cleanup_storage_dir(project_id)


@pytest.mark.asyncio
async def test_period_end_date_format(tmp_path: Path) -> None:
    """period_end 和 current_date 格式为 YYYY年MM月DD日。"""
    from app.routers.wp_editor_router import _prefill_word_template

    fp = _create_test_docx(tmp_path, ["{{period_end}}", "{{current_date}}"])
    project_id = uuid.uuid4()
    wp = _make_mock_wp(str(fp), wp_index_id=None)
    user = _make_mock_user()
    db = _make_mock_db(audit_period_end=date(2024, 6, 15))

    target_snapshot = Path(f"storage/{project_id}/workpapers/test_template.docx")
    target_snapshot.parent.mkdir(parents=True, exist_ok=True)
    if target_snapshot.exists():
        target_snapshot.unlink()

    try:
        await _prefill_word_template(db, wp, project_id, user=user)

        text = _extract_full_text(target_snapshot)
        assert "2024年06月15日" in text
        today = date.today()
        assert today.strftime("%Y年%m月%d日") in text
    finally:
        if target_snapshot.exists():
            target_snapshot.unlink()
        _cleanup_storage_dir(project_id)


@pytest.mark.asyncio
async def test_none_value_preserves_token(tmp_path: Path) -> None:
    """空值保留：对应值为 None 时保留 {{token}} 不替换。"""
    from app.routers.wp_editor_router import _prefill_word_template

    tokens = ["{{entity_name}}", "{{partner_name}}", "{{preparer}}", "{{current_date}}"]
    fp = _create_test_docx(tmp_path, tokens)
    project_id = uuid.uuid4()

    # 项目信息全空，partner 为 None，不传 user（preparer 为 None）
    db = _make_mock_db(
        client_name=None,
        project_name=None,
        audit_period_end=None,
        partner_name=None,
        staff_name=None,
    )
    wp = _make_mock_wp(str(fp), wp_index_id=None)

    target_snapshot = Path(f"storage/{project_id}/workpapers/test_template.docx")
    target_snapshot.parent.mkdir(parents=True, exist_ok=True)
    if target_snapshot.exists():
        target_snapshot.unlink()

    try:
        result = await _prefill_word_template(db, wp, project_id, user=None)

        text = _extract_full_text(target_snapshot)

        # entity_name, partner_name, preparer 值为 None → 保留 token
        assert "{{entity_name}}" in text
        assert "{{partner_name}}" in text
        assert "{{preparer}}" in text
        # current_date 始终有值（today()），应被替换
        assert "{{current_date}}" not in text
    finally:
        if target_snapshot.exists():
            target_snapshot.unlink()
        _cleanup_storage_dir(project_id)


@pytest.mark.asyncio
async def test_partial_none_replacement(tmp_path: Path) -> None:
    """部分字段为 None 时：有值的替换，无值的保留。"""
    from app.routers.wp_editor_router import _prefill_word_template

    tokens = ["{{entity_name}}", "{{partner_name}}", "{{current_date}}"]
    fp = _create_test_docx(tmp_path, tokens)
    project_id = uuid.uuid4()
    wp = _make_mock_wp(str(fp), wp_index_id=None)
    user = _make_mock_user()

    # partner_name 为 None，其他有值
    db = _make_mock_db(partner_name=None)

    target_snapshot = Path(f"storage/{project_id}/workpapers/test_template.docx")
    target_snapshot.parent.mkdir(parents=True, exist_ok=True)
    if target_snapshot.exists():
        target_snapshot.unlink()

    try:
        result = await _prefill_word_template(db, wp, project_id, user=user)

        assert result is True
        text = _extract_full_text(target_snapshot)

        # entity_name 被替换
        assert "{{entity_name}}" not in text
        assert "北京测试科技有限公司" in text
        # partner_name 保留
        assert "{{partner_name}}" in text
        # current_date 被替换
        assert "{{current_date}}" not in text
    finally:
        if target_snapshot.exists():
            target_snapshot.unlink()
        _cleanup_storage_dir(project_id)


@pytest.mark.asyncio
async def test_table_tokens_replaced(tmp_path: Path) -> None:
    """表格中的占位符也被替换。"""
    from app.routers.wp_editor_router import _prefill_word_template

    tokens = ["{{entity_name}}", "{{partner_name}}"]
    fp = _create_test_docx_with_table(tmp_path, tokens)
    project_id = uuid.uuid4()
    wp = _make_mock_wp(str(fp), wp_index_id=None)
    user = _make_mock_user()
    db = _make_mock_db()

    target_snapshot = Path(f"storage/{project_id}/workpapers/test_table_template.docx")
    target_snapshot.parent.mkdir(parents=True, exist_ok=True)
    if target_snapshot.exists():
        target_snapshot.unlink()

    try:
        result = await _prefill_word_template(db, wp, project_id, user=user)

        assert result is True
        text = _extract_full_text(target_snapshot)
        assert "北京测试科技有限公司" in text
        assert "张合伙人" in text
    finally:
        if target_snapshot.exists():
            target_snapshot.unlink()
        _cleanup_storage_dir(project_id)


@pytest.mark.asyncio
async def test_audit_logging(tmp_path: Path, caplog) -> None:
    """替换后记录审计日志 logger.info。"""
    from app.routers.wp_editor_router import _prefill_word_template

    fp = _create_test_docx(tmp_path, ["{{entity_name}}", "{{current_date}}"])
    project_id = uuid.uuid4()
    wp = _make_mock_wp(str(fp), wp_index_id=None)
    user = _make_mock_user()
    db = _make_mock_db()

    target_snapshot = Path(f"storage/{project_id}/workpapers/test_template.docx")
    target_snapshot.parent.mkdir(parents=True, exist_ok=True)
    if target_snapshot.exists():
        target_snapshot.unlink()

    try:
        with caplog.at_level(logging.INFO, logger="app.routers.wp_editor_router"):
            result = await _prefill_word_template(db, wp, project_id, user=user)

        assert result is True
        # 检查日志包含 prefill 和 fields 信息
        assert any("prefill" in record.message and "fields=" in record.message
                   for record in caplog.records), (
            f"未找到预期的 prefill 日志，实际日志: {[r.message for r in caplog.records]}"
        )
    finally:
        if target_snapshot.exists():
            target_snapshot.unlink()
        _cleanup_storage_dir(project_id)


@pytest.mark.asyncio
async def test_no_placeholders_returns_false(tmp_path: Path) -> None:
    """无占位符的文件直接返回 False。"""
    from app.routers.wp_editor_router import _prefill_word_template

    doc = Document()
    doc.add_paragraph("这是一段没有占位符的普通文本")
    fp = tmp_path / "no_placeholders.docx"
    doc.save(str(fp))

    project_id = uuid.uuid4()
    wp = _make_mock_wp(str(fp), wp_index_id=None)
    db = _make_mock_db()

    target_snapshot = Path(f"storage/{project_id}/workpapers/no_placeholders.docx")
    target_snapshot.parent.mkdir(parents=True, exist_ok=True)
    if target_snapshot.exists():
        target_snapshot.unlink()

    try:
        result = await _prefill_word_template(db, wp, project_id, user=None)
        assert result is False
    finally:
        if target_snapshot.exists():
            target_snapshot.unlink()
        _cleanup_storage_dir(project_id)


@pytest.mark.asyncio
async def test_nonexistent_file_returns_false(tmp_path: Path) -> None:
    """文件不存在时返回 False。"""
    from app.routers.wp_editor_router import _prefill_word_template

    project_id = uuid.uuid4()
    wp = _make_mock_wp(str(tmp_path / "nonexistent.docx"), wp_index_id=None)
    db = _make_mock_db()

    result = await _prefill_word_template(db, wp, project_id, user=None)
    assert result is False


@pytest.mark.asyncio
async def test_backward_compat_old_tokens(tmp_path: Path) -> None:
    """向后兼容：旧 token {{client_name}}, {{audit_period}}, {{date}} 仍可替换。"""
    from app.routers.wp_editor_router import _prefill_word_template

    tokens = ["{{client_name}}", "{{audit_period}}", "{{date}}"]
    fp = _create_test_docx(tmp_path, tokens)
    project_id = uuid.uuid4()
    wp = _make_mock_wp(str(fp), wp_index_id=None)
    user = _make_mock_user()
    db = _make_mock_db()

    target_snapshot = Path(f"storage/{project_id}/workpapers/test_template.docx")
    target_snapshot.parent.mkdir(parents=True, exist_ok=True)
    if target_snapshot.exists():
        target_snapshot.unlink()

    try:
        result = await _prefill_word_template(db, wp, project_id, user=user)

        assert result is True
        text = _extract_full_text(target_snapshot)
        assert "{{client_name}}" not in text
        assert "{{audit_period}}" not in text
        assert "{{date}}" not in text
        assert "北京测试科技有限公司" in text
        assert "2025-12-31" in text
    finally:
        if target_snapshot.exists():
            target_snapshot.unlink()
        _cleanup_storage_dir(project_id)


# ---------------------------------------------------------------------------
# Tests: Snapshot Idempotency (task 2.2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_idempotent_skip_prefill(tmp_path: Path) -> None:
    """快照已存在时返回 False，不执行预填。Validates: Requirement 3.4"""
    from app.routers.wp_editor_router import _prefill_word_template

    tokens = ["{{entity_name}}", "{{current_date}}"]
    fp = _create_test_docx(tmp_path, tokens)
    project_id = uuid.uuid4()
    wp = _make_mock_wp(str(fp), wp_index_id=None)
    user = _make_mock_user()
    db = _make_mock_db()

    # 预先创建快照文件（模拟已经预填过）
    snapshot_path = Path(f"storage/{project_id}/workpapers/test_template.docx")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    # 创建一个不同内容的快照（模拟用户已编辑）
    edited_doc = Document()
    edited_doc.add_paragraph("用户已编辑的内容，无占位符")
    edited_doc.save(str(snapshot_path))

    # 记录快照内容用于后续比较
    original_bytes = snapshot_path.read_bytes()

    try:
        result = await _prefill_word_template(db, wp, project_id, user=user)

        # 快照已存在 → 返回 False（不重复预填）
        assert result is False
        # 快照内容未被修改（byte-for-byte 不变）
        assert snapshot_path.read_bytes() == original_bytes
        # wp.file_path 应更新为快照路径
        assert wp.file_path == str(snapshot_path)
    finally:
        if snapshot_path.exists():
            snapshot_path.unlink()
        _cleanup_storage_dir(project_id)


@pytest.mark.asyncio
async def test_original_template_never_modified(tmp_path: Path) -> None:
    """原模板文件始终不修改。Validates: Requirement 3.5"""
    from app.routers.wp_editor_router import _prefill_word_template

    tokens = ["{{entity_name}}", "{{period_end}}", "{{current_date}}"]
    fp = _create_test_docx(tmp_path, tokens)
    project_id = uuid.uuid4()
    wp = _make_mock_wp(str(fp), wp_index_id=None)
    user = _make_mock_user()
    db = _make_mock_db()

    # 记录原模板内容
    original_bytes = fp.read_bytes()

    target_snapshot = Path(f"storage/{project_id}/workpapers/test_template.docx")
    target_snapshot.parent.mkdir(parents=True, exist_ok=True)
    if target_snapshot.exists():
        target_snapshot.unlink()

    try:
        result = await _prefill_word_template(db, wp, project_id, user=user)

        assert result is True
        # 原模板 byte-for-byte 不变
        assert fp.read_bytes() == original_bytes
        # 快照存在且包含替换后的值
        assert target_snapshot.exists()
        text = _extract_full_text(target_snapshot)
        assert "北京测试科技有限公司" in text
    finally:
        if target_snapshot.exists():
            target_snapshot.unlink()
        _cleanup_storage_dir(project_id)


@pytest.mark.asyncio
async def test_wp_code_from_wp_index(tmp_path: Path) -> None:
    """wp_code 优先从 wp_index 表查询获取（非 file_path stem）。"""
    from app.routers.wp_editor_router import _prefill_word_template

    tokens = ["{{entity_name}}"]
    fp = _create_test_docx(tmp_path, tokens)
    project_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()
    wp = _make_mock_wp(str(fp), wp_index_id=wp_index_id)
    user = _make_mock_user()
    # mock db 返回 wp_code = "A9-1"
    db = _make_mock_db(wp_code="A9-1")

    target_snapshot = Path(f"storage/{project_id}/workpapers/A9-1.docx")
    target_snapshot.parent.mkdir(parents=True, exist_ok=True)
    if target_snapshot.exists():
        target_snapshot.unlink()

    try:
        result = await _prefill_word_template(db, wp, project_id, user=user)

        assert result is True
        # 快照应在 wp_code 命名的路径
        assert target_snapshot.exists()
        # wp.file_path 应更新为快照路径
        assert wp.file_path == str(target_snapshot)
    finally:
        if target_snapshot.exists():
            target_snapshot.unlink()
        _cleanup_storage_dir(project_id)


@pytest.mark.asyncio
async def test_snapshot_dir_created_automatically(tmp_path: Path) -> None:
    """快照目录不存在时自动创建。"""
    from app.routers.wp_editor_router import _prefill_word_template

    tokens = ["{{current_date}}"]
    fp = _create_test_docx(tmp_path, tokens)
    project_id = uuid.uuid4()
    wp = _make_mock_wp(str(fp), wp_index_id=None)
    db = _make_mock_db()

    target_snapshot = Path(f"storage/{project_id}/workpapers/test_template.docx")
    # 确保目录不存在
    if target_snapshot.parent.exists():
        shutil.rmtree(target_snapshot.parent)

    try:
        result = await _prefill_word_template(db, wp, project_id, user=None)

        assert result is True
        assert target_snapshot.exists()
        assert target_snapshot.parent.is_dir()
    finally:
        if target_snapshot.exists():
            target_snapshot.unlink()
        _cleanup_storage_dir(project_id)


# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------

def _cleanup_storage_dir(project_id: uuid.UUID) -> None:
    """清理测试产生的 storage 目录。"""
    storage_dir = Path(f"storage/{project_id}")
    if storage_dir.exists():
        shutil.rmtree(storage_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Property-Based Tests: 占位符替换完备性 (Property 3)
# ---------------------------------------------------------------------------

import tempfile

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# 生成器：可打印非空字符串（排除 {{ }} 以避免混淆占位符检测）
_printable_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), blacklist_characters="{}"),
    min_size=1,
    max_size=50,
)


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    entity_name=_printable_text,
    preparer=_printable_text,
    period_end=st.dates(
        min_value=date(2000, 1, 1),
        max_value=date(2099, 12, 31),
    ),
)
@pytest.mark.asyncio
async def test_property_placeholder_replacement_completeness(
    entity_name: str, preparer: str, period_end: date, tmp_path: Path
) -> None:
    """Property 3: 占位符替换完备性

    对于任意非空 entity_name/preparer 和任意 period_end 日期，
    预填后文档不含已替换 token 且包含实际值。

    **Validates: Requirements 3.1, 3.2**
    """
    from app.routers.wp_editor_router import _prefill_word_template

    # 使用独立临时目录避免跨 hypothesis example 冲突
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # 待测试的 token（这些在字段有值时必须被替换）
        tokens = ["{{entity_name}}", "{{period_end}}", "{{preparer}}", "{{current_date}}"]
        fp = _create_test_docx(td_path, tokens)
        project_id = uuid.uuid4()
        wp = _make_mock_wp(str(fp), wp_index_id=None)
        user = _make_mock_user(username=preparer)

        # 构建 mock db，注入随机生成的值
        db = _make_mock_db(
            client_name=entity_name,
            project_name=entity_name,
            audit_period_end=period_end,
            partner_name="某合伙人",
            staff_name=preparer,
        )

        target_snapshot = Path(f"storage/{project_id}/workpapers/test_template.docx")
        target_snapshot.parent.mkdir(parents=True, exist_ok=True)
        if target_snapshot.exists():
            target_snapshot.unlink()

        try:
            result = await _prefill_word_template(db, wp, project_id, user=user)

            assert result is True, "预填应返回 True（有占位符被替换）"

            text = _extract_full_text(target_snapshot)

            # 断言 1: 已替换的 token 不再出现
            assert "{{entity_name}}" not in text, f"{{{{entity_name}}}} 未被替换, text={text!r}"
            assert "{{period_end}}" not in text, f"{{{{period_end}}}} 未被替换, text={text!r}"
            assert "{{preparer}}" not in text, f"{{{{preparer}}}} 未被替换, text={text!r}"
            assert "{{current_date}}" not in text, f"{{{{current_date}}}} 未被替换, text={text!r}"

            # 断言 2: 实际值出现在文档中
            assert entity_name in text, f"entity_name={entity_name!r} 未出现在文档中"

            # period_end 格式为 YYYY年MM月DD日
            expected_period = period_end.strftime("%Y年%m月%d日")
            assert expected_period in text, f"period_end={expected_period!r} 未出现在文档中"

            # preparer 值出现
            assert preparer in text, f"preparer={preparer!r} 未出现在文档中"

            # current_date 格式为 YYYY年MM月DD日（动态值，验证格式正确）
            today = date.today()
            expected_today = today.strftime("%Y年%m月%d日")
            assert expected_today in text, f"current_date={expected_today!r} 未出现在文档中"

        finally:
            if target_snapshot.exists():
                target_snapshot.unlink()
            _cleanup_storage_dir(project_id)


# ---------------------------------------------------------------------------
# Property-Based Tests: 空值占位符保留 (Property 4)
# ---------------------------------------------------------------------------

# All supported tokens and their corresponding mock db/user field keys
_ALL_TOKENS = [
    "{{entity_name}}",
    "{{period_end}}",
    "{{preparer}}",
    "{{current_date}}",
    "{{client_name}}",
    "{{audit_period}}",
    "{{partner_name}}",
]

# Tokens that are always non-None (current_date is always today())
_ALWAYS_AVAILABLE_TOKENS = {"{{current_date}}"}


@st.composite
def _nullable_fields_strategy(draw):
    """生成一组字段，随机选择哪些为 None，哪些有值。

    确保至少有一个字段为 None 且至少有一个字段有值（不含 current_date）。
    """
    # 可控字段（排除 current_date，因为它始终有值）
    controllable_fields = [
        "client_name",
        "audit_period_end",
        "partner_name",
        "staff_name",
    ]

    # 随机选择哪些字段为 None（至少1个为 None，至少1个有值）
    none_count = draw(st.integers(min_value=1, max_value=len(controllable_fields) - 1))
    none_fields = draw(
        st.lists(
            st.sampled_from(controllable_fields),
            min_size=none_count,
            max_size=none_count,
            unique=True,
        )
    )

    # 构建 mock db 参数
    db_kwargs = {}
    for field in controllable_fields:
        if field in none_fields:
            db_kwargs[field] = None
        else:
            # 提供非空默认值
            if field == "client_name":
                db_kwargs[field] = "测试公司"
            elif field == "audit_period_end":
                db_kwargs[field] = date(2025, 12, 31)
            elif field == "partner_name":
                db_kwargs[field] = "王合伙人"
            elif field == "staff_name":
                db_kwargs[field] = "赵助理"

    # project_name 跟 client_name 保持一致（entity_name 来源）
    db_kwargs["project_name"] = db_kwargs.get("client_name")

    # 是否传 user（影响 preparer 是否有值——staff_name 为 None 时 preparer 为 None）
    has_user = db_kwargs.get("staff_name") is not None

    return db_kwargs, none_fields, has_user


# Token 与字段的映射关系（用于判断哪些 token 应保留/替换）
_TOKEN_FIELD_MAP = {
    "{{entity_name}}": "client_name",
    "{{client_name}}": "client_name",
    "{{period_end}}": "audit_period_end",
    "{{audit_period}}": "audit_period_end",
    "{{preparer}}": "staff_name",
    "{{partner_name}}": "partner_name",
    "{{current_date}}": None,  # 始终有值
}


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
@pytest.mark.asyncio
async def test_property_null_value_preserves_tokens(data, tmp_path: Path) -> None:
    """Property 4: 空值占位符保留

    随机选择哪些字段为 None，验证：
    - 空值字段对应的 token 保留在输出文档中
    - 非空字段对应的 token 被替换（不再出现）
    - current_date 始终被替换（因为值始终可用）

    **Validates: Requirements 3.3**
    """
    from app.routers.wp_editor_router import _prefill_word_template

    db_kwargs, none_fields, has_user = data.draw(_nullable_fields_strategy())

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # 创建包含所有 token 的测试文档
        fp = _create_test_docx(td_path, _ALL_TOKENS)
        project_id = uuid.uuid4()
        wp = _make_mock_wp(str(fp), wp_index_id=None)
        user = _make_mock_user(username="赵助理") if has_user else None
        db = _make_mock_db(**db_kwargs)

        target_snapshot = Path(f"storage/{project_id}/workpapers/test_template.docx")
        target_snapshot.parent.mkdir(parents=True, exist_ok=True)
        if target_snapshot.exists():
            target_snapshot.unlink()

        try:
            result = await _prefill_word_template(db, wp, project_id, user=user)

            assert result is True, "预填应返回 True（文档包含占位符）"

            text = _extract_full_text(target_snapshot)

            # 验证每个 token 的保留/替换行为
            for token, field in _TOKEN_FIELD_MAP.items():
                if field is None:
                    # current_date 始终有值 → 不应保留
                    assert token not in text, (
                        f"{token} 应被替换（current_date 始终有值），但仍出现在文档中"
                    )
                elif field in none_fields:
                    # 字段为 None → token 应保留
                    assert token in text, (
                        f"{token} 对应字段 {field} 为 None，应保留但未找到。"
                        f" none_fields={none_fields}, text={text!r}"
                    )
                else:
                    # 字段有值 → token 应被替换
                    assert token not in text, (
                        f"{token} 对应字段 {field} 有值，应被替换但仍出现。"
                        f" none_fields={none_fields}, text={text!r}"
                    )

        finally:
            if target_snapshot.exists():
                target_snapshot.unlink()
            _cleanup_storage_dir(project_id)


# ---------------------------------------------------------------------------
# Property-Based Tests: 快照幂等性 (Property 5)
# ---------------------------------------------------------------------------


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    snapshot_text=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=1,
        max_size=100,
    ),
)
@pytest.mark.asyncio
async def test_property_snapshot_idempotent(snapshot_text: str, tmp_path: Path) -> None:
    """Property 5: 快照幂等性

    对于任意已存在的快照文件（含随机文本内容），调用 _prefill_word_template 时：
    1. 函数返回 False（快照已存在，跳过预填）
    2. 快照文件内容 byte-for-byte 不变
    3. wp.file_path 更新为快照路径

    **Validates: Requirements 3.4, 3.5**
    """
    from app.routers.wp_editor_router import _prefill_word_template

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # 创建含占位符的模板文件（模拟原始模板）
        tokens = ["{{entity_name}}", "{{period_end}}", "{{current_date}}"]
        fp = _create_test_docx(td_path, tokens)
        project_id = uuid.uuid4()
        wp = _make_mock_wp(str(fp), wp_index_id=None)
        user = _make_mock_user()
        db = _make_mock_db()

        # 构建快照路径并创建含随机内容的快照 docx
        snapshot_path = Path(f"storage/{project_id}/workpapers/test_template.docx")
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)

        # 用随机文本内容创建快照 docx（模拟用户已编辑的文档）
        snapshot_doc = Document()
        snapshot_doc.add_paragraph(snapshot_text)
        snapshot_doc.save(str(snapshot_path))

        # 记录快照原始字节
        original_bytes = snapshot_path.read_bytes()

        try:
            result = await _prefill_word_template(db, wp, project_id, user=user)

            # 断言 1: 返回 False（快照已存在，不重复预填）
            assert result is False, (
                f"快照已存在时应返回 False，但返回了 {result}。"
                f" snapshot_text={snapshot_text!r}"
            )

            # 断言 2: 快照文件 byte-for-byte 不变
            assert snapshot_path.read_bytes() == original_bytes, (
                f"快照文件内容被修改！snapshot_text={snapshot_text!r}"
            )

            # 断言 3: wp.file_path 更新为快照路径
            assert wp.file_path == str(snapshot_path), (
                f"wp.file_path 应为 {str(snapshot_path)}，"
                f"实际为 {wp.file_path}"
            )

        finally:
            if snapshot_path.exists():
                snapshot_path.unlink()
            _cleanup_storage_dir(project_id)
