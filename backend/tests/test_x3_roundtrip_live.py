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


def _sample_rows() -> list[dict[str, str]]:
    """GS7 往返用的 3 行样本（每次返回新列表，避免被就地修改）。"""
    return [
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

    def test_roundtrip_all_16_sheets(self):
        """🔴 **16 张全部**完成 write→load 往返（单次 asyncio.run 防连接池污染）。

        2026-08-16 复盘修：初版只测 `sheets[0]`（L2-3）一张，却命名 `first_sheet`
        并被当成 GS7 的往返覆盖 —— 其余 15 张的取值层从未被真执行过。
        """
        async def _run():
            import sqlalchemy as sa

            failures: list[str] = []
            checked: list[str] = []
            async with _get_db_session() as db:
                for sheet in _all_sheets():
                    cycle = sheet.split("-")[0]
                    # 归属判据同 15.1：必须用该 sheet **自己的**底稿，禁别家顶替
                    r = await db.execute(
                        sa.text(
                            "SELECT wp.id::text FROM working_paper wp "
                            "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                            "WHERE wi.wp_code = :code "
                            "ORDER BY wp.updated_at DESC NULLS LAST LIMIT 1"
                        ),
                        {"code": cycle},
                    )
                    row = r.fetchone()
                    if row is None:
                        failures.append(f"{sheet}: 库中无 wp_code={cycle} 的底稿（无法验收）")
                        continue
                    wp_id = str(row[0])
                    mod = _x3_module()
                    try:
                        original, _ = await mod.load_rows(db, wp_id, sheet)
                        await mod.write_rows(db, wp_id, sheet, _sample_rows())
                        readback, _ = await mod.load_rows(db, wp_id, sheet)
                        if len(readback) != len(_sample_rows()):
                            failures.append(
                                f"{sheet}: 写入 {len(_sample_rows())} 行 读回 {len(readback)} 行"
                            )
                        await mod.write_rows(db, wp_id, sheet, original)
                        checked.append(sheet)
                    except Exception as exc:  # noqa: BLE001 — 记失败态，禁吞（GS7）
                        failures.append(f"{sheet}: {type(exc).__name__}: {exc}")
            return checked, failures

        checked, failures = asyncio.run(_run())
        assert not failures, f"往返失败 {len(failures)} 项: {failures}"
        # 反空转：必须是 16 个**互不相同**的 sheet，且与 X3_SHEET_SPECS 键集逐一相等
        assert len(set(checked)) == 16, f"应覆盖 16 张互不相同，实测 {len(set(checked))}: {sorted(checked)}"
        assert set(checked) == set(_all_sheets()), (
            f"覆盖面与 X3_SHEET_SPECS 不符，缺 {sorted(set(_all_sheets()) - set(checked))}"
        )

    def test_reverse_selfcheck_wrong_column_name_is_detected(self):
        """🔴 反向自检：把 SQL 里的 `wp_id` 换成 `workpaper_id`，列名守卫**必须**检出。

        2026-08-16 复盘修：初版反向自检是「查一个不存在的列，断言 SQLAlchemy 抛错」——
        那验证的是**第三方库的既有行为**，与本文件的列名守卫有没有效毫无关系
        （守卫被删掉它照样绿）。

        正确形态 = 对**守卫本身**做变异：把被扫的源码替换成写错列名的版本，
        喂给与 `test_sql_column_name_is_wp_id` 同一套判据，必须判出违规。
        """
        mod = _x3_module()
        source = inspect.getsource(mod)

        # 与 test_sql_column_name_is_wp_id 完全同一套提取 + 判定逻辑
        def _violations(src: str) -> list[str]:
            stmts = re.findall(
                r'(?:sa\.text|text)\(\s*(?:f?""".*?"""|f?".*?")', src, re.DOTALL
            )
            return [s[:80] for s in stmts if "workpaper_id" in s]

        # CONTROL：真实源码必须零违规
        assert _violations(source) == [], (
            f"真实源码里出现 workpaper_id: {_violations(source)}"
        )

        # MUTANT：把 wp_id 换成 workpaper_id ⇒ 判据必须检出（否则守卫空转）
        mutated = source.replace("wp_id = :wp_id", "workpaper_id = :wp_id")
        assert mutated != source, "变异未生效（源码里找不到 `wp_id = :wp_id`）⇒ 判据锚点已漂移"
        found = _violations(mutated)
        assert found, (
            "把 SQL 列名改成 workpaper_id 后判据仍未检出 ⇒ "
            "`test_sql_column_name_is_wp_id` 是空转守卫"
        )


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

    def test_storage_column_guard_really_executes(self):
        """🔴 `_storage_column()` 的运行期白名单校验必须**真的执行**（GS9 运行期侧）。

        为什么需要这条（2026-08-16 变异 X3 判 GREEN 后补）：
        GS9 后端侧（`test_x3_key_ledger.py`）全是**清单内数据断言**
        （读 `adjustment_ie_contract.json` 比 `mechanism` ↔ `storage_field`），
        没有任何一条会**执行** `_storage_column()`。故把该函数的校验短路成
        `if False and spec.storage_field not in allowed:` 后，GS1~GS9 照旧全绿
        ⇒ 「列名先被白名单校验、再拼进 SQL」这条运行期保证**结构性不可见**。

        判据形态 = 行为：造一个 `storage_field` 非法的替身 spec 喂给 `_storage_column()`，
        它**必须抛错**。校验被短路 ⇒ 返回非法列名而不抛 ⇒ 本条打红。
        （若不抛，那个非法列名会被 f-string 拼进 `SELECT {column}` / `UPDATE SET {column}`。）
        """
        mod = _x3_module()
        import dataclasses

        # 取一张真 spec，替换 storage_field 为非法值（不改生产数据，只造替身对象）
        real_spec = next(iter(mod.X3_SHEET_SPECS.values()))
        try:
            bad_spec = dataclasses.replace(real_spec, storage_field="evil_column")
        except Exception:
            # 非 dataclass（如 NamedTuple）时用 _replace
            bad_spec = real_spec._replace(storage_field="evil_column")  # type: ignore[attr-defined]

        with pytest.raises(Exception) as ei:
            mod._storage_column(bad_spec)
        msg = str(ei.value)
        assert "evil_column" in msg or "落库列" in msg, (
            f"_storage_column 抛错了但消息不含被拒的列名/理由: {msg!r}"
        )

        # 对照组：合法 spec 必须正常返回（防上面那条靠「函数恒抛」蒙对）
        assert mod._storage_column(real_spec) == real_spec.storage_field
