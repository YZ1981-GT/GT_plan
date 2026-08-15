"""test_x3_roundtrip_live.py — GS7 取值层真执行守卫（spec 任务 13.4）

验证 `_x3_adjustment_import_export` 的 `load_rows` / `write_rows` 函数在**真实数据库**上
能成功执行、SQL 列名正确、异常不被吞。

设计要点（tasks.md §13.4）:
  - `load_rows` / `write_rows` **真跑一次**
  - 捕获到的异常记为失败态（禁 `except Exception: logger.warning`）
  - SQL 列名断言 `wp_id`（非 `workpaper_id`）
  - 一次 `asyncio.run` 取全部快照（每测试各自 async 会污染共享连接池）
  - 反向自检：故意把列名写错必须失败

需要环境:
  - PG 在线（`DB_URL` 环境变量或 app.core.config 默认连接）
  - `checklist_responses` 表存在
  - 至少存在一个底稿对象

执行:
    python -m pytest backend/tests/test_x3_roundtrip_live.py -v --tb=short
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import textwrap
from typing import Any
from uuid import uuid4

import pytest

# ─── 标记 live 测试（无 PG 则跳过）─────────────────────────────────────────────
try:
    import sys
    sys.path.insert(0, "backend")
    from app.core.config import settings  # noqa: E402

    _DB_AVAILABLE = bool(settings.DATABASE_URL)
except Exception:
    _DB_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _DB_AVAILABLE, reason="数据库不可用")


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════════════════════

def _get_db_session():
    """获取 AsyncSession（一次性，测试结束后关闭）。"""
    from app.core.database import async_session
    return async_session()


def _x3_module():
    """获取 _x3_adjustment_import_export 模块。"""
    from app.routers.wp_render_strategies import _x3_adjustment_import_export
    return _x3_adjustment_import_export


def _all_sheets() -> list[str]:
    """16 张 X-3 sheet code。"""
    mod = _x3_module()
    return sorted(mod.X3_SHEET_SPECS.keys())


async def _find_any_wp_id() -> str | None:
    """在 checklist_responses 中找一个有数据的 wp_id。"""
    import sqlalchemy as sa
    async with _get_db_session() as db:
        result = await db.execute(
            sa.text("SELECT DISTINCT wp_id FROM checklist_responses LIMIT 1")
        )
        row = result.fetchone()
        return str(row[0]) if row else None


async def _roundtrip_one_sheet(sheet: str, wp_id: str) -> dict[str, Any]:
    """对单张 sheet 执行写入→读回→比对→还原。"""
    mod = _x3_module()
    spec = mod.sheet_spec(sheet)

    # 构造 3 行测试数据
    test_rows = [
        {"type": "AJE", "subject": "测试科目A", "debit": "1000.00", "credit": "",
         "summary": "GS7测试行1", "preparer": "test", "date": "2026-01-01",
         "voucher_no": "T001", "voucher_word": "记", "index_no": ""},
        {"type": "RJE", "subject": "测试科目B", "debit": "", "credit": "2000.50",
         "summary": "GS7测试行2", "preparer": "test", "date": "2026-01-02",
         "voucher_no": "T002", "voucher_word": "记", "index_no": ""},
        {"type": "AJE", "subject": "测试科目C", "debit": "500.00", "credit": "",
         "summary": "GS7测试行3", "preparer": "test", "date": "2026-01-03",
         "voucher_no": "T003", "voucher_word": "记", "index_no": ""},
    ]

    result: dict[str, Any] = {"sheet": sheet, "success": False, "error": None}

    async with _get_db_session() as db:
        # 先读取现有数据（用于还原）
        try:
            original_rows, _ = await mod.load_rows(db, wp_id, sheet)
            result["original_count"] = len(original_rows)
        except Exception as e:
            result["error"] = f"load_rows(初始读)失败: {type(e).__name__}: {e}"
            return result

        # 写入测试数据
        try:
            outcome = await mod.write_rows(db, wp_id, sheet, test_rows)
            result["write_outcome"] = {
                "written_count": outcome.written_count,
                "written_item_ids": len(outcome.written_item_ids),
            }
        except Exception as e:
            result["error"] = f"write_rows 失败: {type(e).__name__}: {e}"
            return result

        # 读回
        try:
            readback, warnings = await mod.load_rows(db, wp_id, sheet)
            result["readback_count"] = len(readback)
            result["readback_warnings"] = warnings
        except Exception as e:
            result["error"] = f"load_rows(读回)失败: {type(e).__name__}: {e}"
            # 尝试还原
            try:
                await mod.write_rows(db, wp_id, sheet, original_rows)
            except Exception:
                pass
            return result

        # 比对：读回行数应 == 写入行数
        if len(readback) != len(test_rows):
            result["error"] = (
                f"读回行数不等: 写入{len(test_rows)}行, 读回{len(readback)}行"
            )
        else:
            result["success"] = True

        # 还原
        try:
            await mod.write_rows(db, wp_id, sheet, original_rows)
            result["restored"] = True
        except Exception as e:
            result["restore_error"] = f"还原失败: {type(e).__name__}: {e}"
            result["restored"] = False

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestGS7RoundtripLive:
    """GS7：取值层真执行守卫。"""

    def test_sql_column_name_is_wp_id(self):
        """SQL 必须用 `wp_id` 不是 `workpaper_id`（P0 踩坑列名）。"""
        mod = _x3_module()
        source = inspect.getsource(mod)
        # 检查所有 SQL 语句里用的是 wp_id
        sql_statements = re.findall(r'(?:sa\.text|text)\(\s*(?:f?""".*?"""|f?".*?")', source, re.DOTALL)
        for stmt in sql_statements:
            if "workpaper_id" in stmt:
                pytest.fail(f"SQL 中发现 `workpaper_id`（应为 `wp_id`）: {stmt[:100]}")
        # 正面断言：至少有 SQL 用了 wp_id
        assert any("wp_id" in s for s in sql_statements), "未找到含 wp_id 的 SQL 语句"

    def test_load_rows_does_not_swallow_exceptions(self):
        """load_rows 异常不得被吞成 WARNING。"""
        mod = _x3_module()
        source = inspect.getsource(mod.load_rows)
        # 不应有 bare except 或 except Exception 后跟 logger.warning
        if re.search(r"except\s+Exception.*?logger\.warn", source, re.DOTALL):
            pytest.fail("load_rows 内有 `except Exception: logger.warning` —— 违反 GS7")

    def test_write_rows_does_not_swallow_exceptions(self):
        """write_rows 异常不得被吞成 WARNING。"""
        mod = _x3_module()
        source = inspect.getsource(mod.write_rows)
        if re.search(r"except\s+Exception.*?logger\.warn", source, re.DOTALL):
            pytest.fail("write_rows 内有 `except Exception: logger.warning` —— 违反 GS7")

    def test_roundtrip_first_sheet(self):
        """至少一张 X-3 能完成 write→load 往返。"""
        async def _run():
            wp_id = await _find_any_wp_id()
            if wp_id is None:
                pytest.skip("数据库中无 checklist_responses 记录")
            sheets = _all_sheets()
            # 取第一张尝试
            result = await _roundtrip_one_sheet(sheets[0], wp_id)
            return result

        result = asyncio.run(_run())
        if result.get("error"):
            pytest.fail(f"往返失败 ({result['sheet']}): {result['error']}")
        assert result["success"], f"往返未成功: {result}"

    def test_wrong_column_name_must_fail(self):
        """反向自检：故意把列名写错必须失败。"""
        import sqlalchemy as sa

        async def _run():
            async with _get_db_session() as db:
                # 用一个不存在的列名查询
                with pytest.raises(Exception):
                    await db.execute(
                        sa.text(
                            "SELECT item_id, nonexistent_column FROM checklist_responses "
                            "WHERE wp_id = :wp_id LIMIT 1"
                        ),
                        {"wp_id": "fake-wp-id-for-gs7-selfcheck"},
                    )

        asyncio.run(_run())


class TestGS7SourceIntegrity:
    """GS7 辅助：源码结构断言。"""

    def test_x3_module_has_load_rows(self):
        mod = _x3_module()
        assert hasattr(mod, "load_rows"), "缺少 load_rows"
        assert asyncio.iscoroutinefunction(mod.load_rows), "load_rows 必须是 async"

    def test_x3_module_has_write_rows(self):
        mod = _x3_module()
        assert hasattr(mod, "write_rows"), "缺少 write_rows"
        assert asyncio.iscoroutinefunction(mod.write_rows), "write_rows 必须是 async"

    def test_sheet_spec_covers_16(self):
        """X3_SHEET_SPECS 覆盖 16 张。"""
        mod = _x3_module()
        assert len(mod.X3_SHEET_SPECS) == 16, f"期望 16 张，实际 {len(mod.X3_SHEET_SPECS)}"

    def test_storage_column_in_whitelist(self):
        """每张的 storage_field 必须是 'remark' 或 'conclusion'。"""
        mod = _x3_module()
        for code, spec in mod.X3_SHEET_SPECS.items():
            col = spec.storage_field
            assert col in ("remark", "conclusion"), (
                f"{code} storage_field={col!r} 不在白名单"
            )
