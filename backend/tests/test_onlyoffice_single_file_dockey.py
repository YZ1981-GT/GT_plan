"""单文件共享模型 + doc_key 一致性测试

直接测试 helper 函数 `_resolve_wp_file` 和 `_generate_doc_key`，验证：
1. 同 wp_code 不同 sheet 返回相同 doc_key
2. 文件首次复制后存在
3. 后续复用（同 wp_code 再次调用返回同一路径，不重复复制）
4. mtime 变化 → key 变
5. 单文件命名：{wp_code}.xlsx 而非 {wp_code}_{sheet_name}.xlsx
6. 不同 wp_code 不同 key（即使 mtime 相同）
7. 无模板无文件 → FileNotFoundError

Validates: Requirements R4, R5
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import settings as app_settings
from app.routers.wp_onlyoffice_router import (
    _generate_doc_key,
    _resolve_wp_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    """使用 tmp_path 作为 STORAGE_ROOT"""
    monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def project_id():
    """固定的测试项目 ID"""
    return uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def template_file(tmp_path):
    """创建一个模板 xlsx 文件"""
    template = tmp_path / "templates" / "D0.xlsx"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_bytes(b"PK\x03\x04template-xlsx-content-here")
    return template


# ---------------------------------------------------------------------------
# Tests: doc_key 一致性
# ---------------------------------------------------------------------------


class TestDocKeyConsistency:
    """doc_key 一致性：同 wp_code 共享同一 key，mtime 变则 key 变

    Validates: Requirements R5
    """

    def test_same_wp_code_different_sheet_same_doc_key(self, tmp_path):
        """同 wp_code 不同 sheet 返回相同 doc_key

        同一物理文件被多个 sheet 共享时，doc_key 仅依赖 wp_code + mtime，
        不包含 sheet_name，因此所有 sheet 得到相同 key。
        """
        file_path = tmp_path / "D0.xlsx"
        file_path.write_bytes(b"shared workbook content")

        # 模拟不同 sheet 请求同一 wp_code（概念上不同 sheet，但同一物理文件）
        key_sheet_a = _generate_doc_key(file_path, "D0")
        key_sheet_b = _generate_doc_key(file_path, "D0")
        key_sheet_c = _generate_doc_key(file_path, "D0")

        assert key_sheet_a == key_sheet_b
        assert key_sheet_b == key_sheet_c
        assert len(key_sheet_a) == 32  # MD5 hex digest

    def test_mtime_change_produces_different_key(self, tmp_path):
        """mtime 变化 → doc_key 变化

        文件被保存（mtime 改变）后 OnlyOffice 需要新 key 以重新加载文档。
        """
        file_path = tmp_path / "D0.xlsx"
        file_path.write_bytes(b"version 1")
        key_before = _generate_doc_key(file_path, "D0")

        # 强制修改 mtime（使用 os.utime 确保纳秒级变化）
        stat = file_path.stat()
        new_mtime_ns = stat.st_mtime_ns + 1_000_000  # 加 1ms
        os.utime(file_path, ns=(stat.st_atime_ns, new_mtime_ns))

        key_after = _generate_doc_key(file_path, "D0")

        assert key_before != key_after

    def test_different_wp_code_different_key_same_mtime(self, tmp_path):
        """不同 wp_code 产生不同 doc_key，即使 mtime 相同

        doc_key = hash(wp_code + mtime_ns)，wp_code 不同则 key 必定不同。
        """
        file_a = tmp_path / "D0.xlsx"
        file_b = tmp_path / "D1.xlsx"
        file_a.write_bytes(b"same content")
        file_b.write_bytes(b"same content")

        # 确保两个文件 mtime 完全相同
        stat_a = file_a.stat()
        os.utime(file_b, ns=(stat_a.st_atime_ns, stat_a.st_mtime_ns))

        key_a = _generate_doc_key(file_a, "D0")
        key_b = _generate_doc_key(file_b, "D1")

        assert key_a != key_b

    def test_doc_key_is_deterministic(self, tmp_path):
        """同一文件 + 同一 wp_code 多次调用结果稳定"""
        file_path = tmp_path / "D2.xlsx"
        file_path.write_bytes(b"stable content")

        keys = [_generate_doc_key(file_path, "D2") for _ in range(10)]
        assert len(set(keys)) == 1  # 所有结果相同


# ---------------------------------------------------------------------------
# Tests: 单文件共享模型
# ---------------------------------------------------------------------------


class TestResolveSingleFile:
    """单文件共享模型：按 wp_code 命名，首次复制，后续复用

    Validates: Requirements R4
    """

    def test_file_copied_from_template_on_first_call(self, storage_root, project_id, template_file):
        """文件首次复制后存在

        当项目存储中不存在 {wp_code}.xlsx 但模板文件存在时，
        从模板整本复制一次生成 WP_File。
        """
        result = _resolve_wp_file(project_id, "D0", template_file)

        assert result.exists()
        assert result.read_bytes() == template_file.read_bytes()

    def test_subsequent_call_reuses_file(self, storage_root, project_id, template_file):
        """后续复用：同 wp_code 再次调用返回同一路径，不重复复制

        第二次调用时文件已存在，直接返回既有路径而不再复制。
        """
        result1 = _resolve_wp_file(project_id, "D0", template_file)

        # 修改已有文件内容以验证不被覆盖
        result1.write_bytes(b"modified-by-user-edit")

        result2 = _resolve_wp_file(project_id, "D0", template_file)

        assert result1 == result2
        # 内容仍然是用户修改后的，说明没有重复复制
        assert result2.read_bytes() == b"modified-by-user-edit"

    def test_file_named_wp_code_xlsx(self, storage_root, project_id, template_file):
        """单文件命名：文件名为 {wp_code}.xlsx 而非 {wp_code}_{sheet_name}.xlsx

        验证单文件模型的命名规则（去掉了 per-sheet 后缀）。
        """
        result = _resolve_wp_file(project_id, "D0", template_file)

        assert result.name == "D0.xlsx"
        # 确认不是 per-sheet 命名
        assert "_" not in result.name.replace(".xlsx", "")

    def test_file_named_with_complex_wp_code(self, storage_root, project_id, template_file):
        """复杂 wp_code（含连字符/数字）也正确命名"""
        result = _resolve_wp_file(project_id, "D2-6", template_file)

        assert result.name == "D2-6.xlsx"
        assert result.exists()

    def test_no_template_no_file_raises_file_not_found(self, storage_root, project_id):
        """无模板无文件 → FileNotFoundError

        既不存在已有文件，也没有可复制的模板时抛出异常。
        """
        with pytest.raises(FileNotFoundError, match="OnlyOffice 文件不存在且无模板可复制"):
            _resolve_wp_file(project_id, "NONEXISTENT", None)

    def test_no_template_no_file_with_none_path(self, storage_root, project_id):
        """template_path 为 None 时同样抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            _resolve_wp_file(project_id, "D0", None)

    def test_no_template_nonexistent_path(self, storage_root, project_id, tmp_path):
        """template_path 指向不存在的文件时抛出 FileNotFoundError"""
        fake_template = tmp_path / "nonexistent_template.xlsx"
        assert not fake_template.exists()

        with pytest.raises(FileNotFoundError):
            _resolve_wp_file(project_id, "D0", fake_template)

    def test_existing_file_returns_directly(self, storage_root, project_id):
        """项目存储中已有文件 → 直接返回，不需要模板"""
        # 预先创建文件
        storage_dir = (
            storage_root / "projects" / str(project_id) / "workpapers" / "onlyoffice"
        )
        storage_dir.mkdir(parents=True)
        existing = storage_dir / "D0.xlsx"
        existing.write_bytes(b"pre-existing content")

        # 不提供模板也能成功
        result = _resolve_wp_file(project_id, "D0", None)
        assert result == existing
        assert result.read_bytes() == b"pre-existing content"

    def test_single_file_per_wp_code(self, storage_root, project_id, template_file):
        """每个 wp_code 至多一个 xlsx 文件

        验证项目存储目录下同一 wp_code 只有一个文件。
        """
        _resolve_wp_file(project_id, "D0", template_file)

        storage_dir = (
            storage_root / "projects" / str(project_id) / "workpapers" / "onlyoffice"
        )
        xlsx_files = list(storage_dir.glob("D0*.xlsx"))
        assert len(xlsx_files) == 1
        assert xlsx_files[0].name == "D0.xlsx"
