"""R1 Task 14 单元测试：archive_section_registry

覆盖：
1. register 后 list_all 返回按 order_prefix 排序
2. 重复 register 同 prefix 覆盖旧注册
3. get_by_prefix 查找已注册/未注册章节
4. generate_all 调用所有 generator 并返回结果列表
5. R1 默认注册了 00/01/99 三个章节

Validates: Requirements 6 (refinement-round1-review-closure)
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from app.services import archive_section_registry
from app.services.archive_section_registry import (
    SectionDef,
    register,
    list_all,
    get_by_prefix,
    generate_all,
    clear,
    register_r1_sections,
)


FAKE_PROJECT_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def reset_registry():
    """每个测试前清空 registry，测试后恢复 R1 注册。"""
    clear()
    yield
    clear()
    register_r1_sections()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegisterAndListAll:
    """register + list_all 基本功能。"""

    def test_register_single(self):
        """注册一个章节后 list_all 返回它。"""
        async def gen(pid, db):
            return b"data"

        register("05", "05-test.pdf", gen, "测试章节")
        sections = list_all()
        assert len(sections) == 1
        assert sections[0].order_prefix == "05"
        assert sections[0].filename == "05-test.pdf"
        assert sections[0].description == "测试章节"

    def test_register_multiple_sorted(self):
        """注册多个章节后 list_all 按 order_prefix 排序。"""
        async def gen(pid, db):
            return None

        register("99", "99-last.jsonl", gen, "最后")
        register("00", "00-first.pdf", gen, "最先")
        register("50", "50-middle.pdf", gen, "中间")

        sections = list_all()
        prefixes = [s.order_prefix for s in sections]
        assert prefixes == ["00", "50", "99"]

    def test_register_duplicate_prefix_overwrites(self):
        """重复注册同 prefix 覆盖旧注册。"""
        async def gen_old(pid, db):
            return b"old"

        async def gen_new(pid, db):
            return b"new"

        register("01", "01-old.pdf", gen_old, "旧版")
        register("01", "01-new.pdf", gen_new, "新版")

        sections = list_all()
        assert len(sections) == 1
        assert sections[0].filename == "01-new.pdf"
        assert sections[0].description == "新版"
        assert sections[0].generator_func is gen_new


class TestGetByPrefix:
    """get_by_prefix 查找功能。"""

    def test_found(self):
        """已注册的 prefix 能找到。"""
        async def gen(pid, db):
            return None

        register("07", "07-test.pdf", gen)
        result = get_by_prefix("07")
        assert result is not None
        assert result.order_prefix == "07"

    def test_not_found(self):
        """未注册的 prefix 返回 None。"""
        result = get_by_prefix("99")
        assert result is None


class TestGenerateAll:
    """generate_all 调用所有 generator。"""

    @pytest.mark.asyncio
    async def test_generate_all_calls_generators(self):
        """generate_all 按顺序调用每个 generator 并返回结果。"""
        gen1 = AsyncMock(return_value=b"cover-pdf-bytes")
        gen2 = AsyncMock(return_value=b"ledger-pdf-bytes")

        register("00", "00-封面.pdf", gen1, "封面")
        register("01", "01-签字.pdf", gen2, "签字")

        fake_db = AsyncMock()
        results = await generate_all(FAKE_PROJECT_ID, fake_db)

        assert len(results) == 2
        assert results[0] == ("00-封面.pdf", b"cover-pdf-bytes")
        assert results[1] == ("01-签字.pdf", b"ledger-pdf-bytes")

        gen1.assert_called_once_with(FAKE_PROJECT_ID, fake_db)
        gen2.assert_called_once_with(FAKE_PROJECT_ID, fake_db)

    @pytest.mark.asyncio
    async def test_generate_all_handles_failure(self):
        """单个 generator 失败不中断整体，返回 None。"""
        gen_ok = AsyncMock(return_value=b"ok-data")
        gen_fail = AsyncMock(side_effect=RuntimeError("生成失败"))
        gen_ok2 = AsyncMock(return_value=b"ok-data-2")

        register("00", "00-ok.pdf", gen_ok)
        register("01", "01-fail.pdf", gen_fail)
        register("02", "02-ok2.pdf", gen_ok2)

        fake_db = AsyncMock()
        results = await generate_all(FAKE_PROJECT_ID, fake_db)

        assert len(results) == 3
        assert results[0] == ("00-ok.pdf", b"ok-data")
        assert results[1] == ("01-fail.pdf", None)  # 失败返回 None
        assert results[2] == ("02-ok2.pdf", b"ok-data-2")

    @pytest.mark.asyncio
    async def test_generate_all_empty_registry(self):
        """空 registry 返回空列表。"""
        fake_db = AsyncMock()
        results = await generate_all(FAKE_PROJECT_ID, fake_db)
        assert results == []


class TestR1DefaultRegistration:
    """R1 默认注册验证。"""

    def test_r1_sections_registered(self):
        """register_r1_sections 注册 00/01/04/99 四个章节。"""
        register_r1_sections()
        sections = list_all()
        prefixes = [s.order_prefix for s in sections]
        assert "00" in prefixes
        assert "01" in prefixes
        assert "04" in prefixes
        assert "99" in prefixes
        assert len(sections) == 4

    def test_r1_filenames(self):
        """R1 章节文件名正确。"""
        register_r1_sections()
        sections = list_all()
        filenames = {s.order_prefix: s.filename for s in sections}
        assert filenames["00"] == "00-项目封面.pdf"
        assert filenames["01"] == "01-签字流水.pdf"
        assert filenames["99"] == "99-审计日志.jsonl"

    def test_r1_descriptions(self):
        """R1 章节描述正确。"""
        register_r1_sections()
        sections = list_all()
        descs = {s.order_prefix: s.description for s in sections}
        assert "R1" in descs["00"]
        assert "R1" in descs["01"]
        assert "R1" in descs["99"]
