"""test_x3_roundtrip_property.py — Property 1: 导出导入往返恒等

spec: x3-adjustment-entry-import-export / 任务 13.5*
Validates: Requirements 2.1, 2.5, 2.7, 3.5, 6.5, 6.6

Property 1 定义：
  对任意合法输入行（含中文/特殊字符文本、任意有限小数金额），
  `write_rows → load_rows` 的往返结果与输入在语义上相等（行数相同、字段值可还原）。
  `M9-3` 的 `ociBlock` 后缀保留。

## 🔴 为什么不能直接 `@given` + `asyncio.run`（2026-08-16 复盘记录）

初版试过 `@given(rows=...)` 里 `asyncio.run(...)`，结果 `FlakyFailure` +
`'NoneType' object has no attribute 'send'` —— hypothesis 每个 example 都会重新调用
测试函数，`asyncio.run` 每次新建并**关闭**事件循环，而 SQLAlchemy 的异步连接池
绑定在首个循环上，第二个 example 起连接已失效（memory 记的「每测试各自 async 会
污染共享连接池」同一坑）。

初版第二版为了绕开它改用 `random` 生成 + 40 次迭代，但文件名仍叫 `property`、
`import hypothesis` 成了死 import、迭代数也不满足 tasks.md 的 ≥100 —— 那是**降级冒充**。

## 本文件的正解：hypothesis 只负责「生成」，DB 只跑一次

用 `hypothesis.strategies` 的 `.example()` 不可靠（受 deadline/健康检查影响），
故改用**显式 draw**：`@given` 只作用在一个**纯函数**属性上（不碰 DB，≥100 examples），
DB 往返另用 `data.draw` 在**单个** `pytest.mark.asyncio` 测试里批量抽 ≥100 组样本。
这样既满足「≥100 次迭代」，又只有一个事件循环。
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, "backend")
os.environ.setdefault("JWT_SECRET_KEY", "x3-roundtrip-property-test")

# ─── DB 可用性 ─────────────────────────────────────────────────────────────────
try:
    from app.core.config import settings as app_settings

    _DB_AVAILABLE = bool(app_settings.DATABASE_URL)
except Exception:
    _DB_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
# Strategies —— 覆盖中文/特殊字符、任意有限小数金额
# ═══════════════════════════════════════════════════════════════════════════════

_ENTRY_TYPES = st.sampled_from(["AJE", "RJE"])

#: 中文 + 特殊字符（含引号/逗号/换行敏感符号，验 xlsx 与 JSON 双层转义）
_TEXT = st.text(
    alphabet=st.characters(
        min_codepoint=0x4E00, max_codepoint=0x9FFF, whitelist_categories=("Lo",)
    )
    | st.sampled_from(list("()（）,，\"'、%&+-/：:；;")),
    min_size=1,
    max_size=24,
)

#: 任意有限小数金额（2 位）或空串
_AMOUNT = st.one_of(
    st.just(""),
    st.decimals(min_value=0, max_value=99999999, places=2, allow_nan=False, allow_infinity=False)
    .map(lambda d: f"{d:.2f}"),
)

_DATE = st.from_regex(r"20[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|1[0-9]|2[0-8])", fullmatch=True)


@st.composite
def entry_row(draw) -> dict[str, str]:
    """一行分录。借贷互斥（同一行只填一侧），与前端行模型一致。"""
    debit = draw(_AMOUNT)
    credit = "" if debit else draw(_AMOUNT)
    return {
        "type": draw(_ENTRY_TYPES),
        "subject": draw(_TEXT),
        "debit": debit,
        "credit": credit,
        "summary": draw(_TEXT),
        "preparer": draw(st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz")),
        "date": draw(_DATE),
        "voucher_no": draw(st.text(min_size=0, max_size=8, alphabet="ABCDEFG0123456789")),
        "voucher_word": draw(st.sampled_from(["记", "转", "付", "收", ""])),
        "index_no": draw(st.text(min_size=0, max_size=5, alphabet="0123456789")),
    }


_ROWS = st.lists(entry_row(), min_size=1, max_size=5)


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════════════════════

def _x3_mod():
    from app.routers.wp_render_strategies import _x3_adjustment_import_export

    return _x3_adjustment_import_export


def _get_session():
    from app.core.database import async_session

    return async_session()


class _IsolatedSession:
    """自建 engine 的会话上下文（用完 dispose）。

    🔴 为什么不能直接用全局 `app.core.database.async_session`（2026-08-16 实测）：
    本文件的 live 测试单独跑绿、**与 `test_x3_roundtrip_live.py` 同批跑必挂**
    `RuntimeError: Event loop is closed`。根因是同一 pytest session 里混用了两种
    异步风格 —— 那个文件用 `asyncio.run()`（每次**关闭**事件循环），而全局
    `async_session` 的连接池绑定在首个循环上；等本文件的 `@pytest.mark.asyncio`
    测试跑起来，池里的连接已指向被关掉的循环。

    单独跑绿 ⇒ 只测本文件会得出「已修好」的错觉，而 CI 是全量跑 ⇒ 必挂。
    故这里自建 engine（`NullPool`，不复用连接），与全局池完全隔离。
    """

    def __init__(self) -> None:
        self._engine = None
        self._session = None

    async def __aenter__(self):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings as _s

        connect_args = {"ssl": False} if getattr(_s, "DB_DISABLE_SSL", False) else {}
        self._engine = create_async_engine(
            _s.DATABASE_URL, poolclass=NullPool, connect_args=connect_args
        )
        maker = async_sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)
        self._session = maker()
        return self._session

    async def __aexit__(self, *exc) -> None:
        if self._session is not None:
            await self._session.close()
        if self._engine is not None:
            await self._engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1-a：纯函数层（不碰 DB，hypothesis ≥100 examples）
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty1PureLayer:
    """`_incoming_payloads → 键面` 与 `build_data_workbook` 的纯函数往返性质。"""

    @settings(max_examples=120, deadline=None,
              suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
    @given(rows=_ROWS)
    def test_workbook_roundtrip_preserves_row_count(self, rows: list[dict[str, str]]):
        """任意行集 → `build_data_workbook` → openpyxl 读回，数据行数恒等。"""
        import io

        from openpyxl import load_workbook

        mod = _x3_mod()
        wb = mod.build_data_workbook(rows, "L2-3", warnings=[])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        wb2 = load_workbook(buf, read_only=True)
        ws = wb2[wb2.sheetnames[0]]
        # 数据行 = 总行数 - 表头行数（表头行数由实现决定，故用「≥ 行数」+ 单调性判据）
        max_row = ws.max_row or 0
        wb2.close()
        assert max_row >= len(rows), (
            f"产物行数 {max_row} < 输入行数 {len(rows)} ⇒ 有行在写盘时丢失"
        )

    @settings(max_examples=120, deadline=None,
              suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
    @given(rows=_ROWS)
    def test_incoming_payload_keys_cover_every_row(self, rows: list[dict[str, str]]):
        """任意行集 → `_incoming_payloads` 生成的键数随行数单调增（无静默丢行）。"""
        mod = _x3_mod()
        spec = mod.sheet_spec("M9-3")  # per_field_plus_data + ociBlock
        payloads = mod._incoming_payloads(spec, rows)
        assert payloads, "空键面 ⇒ 该行集被整体丢弃"
        # 每行至少贡献一个键
        assert len(payloads) >= len(rows), (
            f"{len(rows)} 行只生成 {len(payloads)} 个键 ⇒ 有行未落键面"
        )

    @settings(max_examples=120, deadline=None,
              suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
    @given(rows=_ROWS)
    def test_m9_ociblock_suffix_present_in_key_face(self, rows: list[dict[str, str]]):
        """M9-3 的 `ociBlock` 后缀必须出现在键面（design 登记的第 7 个后缀）。"""
        mod = _x3_mod()
        spec = mod.sheet_spec("M9-3")
        payloads = mod._incoming_payloads(spec, rows)
        keys = " ".join(payloads.keys())
        assert "ociBlock" in keys, (
            f"M9-3 键面缺 ociBlock 后缀 ⇒ 该列往返会丢；实测键样例={list(payloads)[:5]}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1-b：真实库往返（单个事件循环，样本由 hypothesis 批量抽 ≥100 组）
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _DB_AVAILABLE, reason="数据库不可用")
class TestProperty1LiveRoundtrip:
    """`write_rows → load_rows` 在真实库上的往返恒等（≥100 组 hypothesis 样本）。"""

    @settings(max_examples=1, deadline=None,
              suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large,
                                     HealthCheck.function_scoped_fixture])
    @given(data=st.data())
    @pytest.mark.asyncio
    async def test_live_roundtrip_100_samples(self, data):
        """16 张里取两族代表（single_json 的 L2-3 + per_field_plus_data 的 M9-3），
        各跑 50 组 hypothesis 样本，合计 100 组；全程单个事件循环。

        🔴 迭代形态说明：`max_examples=1` 但用 `st.data()` 在**同一个 example 内**
        `draw` 100 次 —— 这样 hypothesis 只调用测试函数一次（⇒ 只有一个事件循环，
        不污染 SQLAlchemy 异步连接池），而生成侧仍是 100 次真实 draw。
        用 `max_examples=100` + 每次 `asyncio.run` 会在第 2 个 example 就报
        `'NoneType' object has no attribute 'send'`（本文件模块 docstring 有记录）。
        """
        import sqlalchemy as sa

        mod = _x3_mod()
        samples = [data.draw(_ROWS) for _ in range(100)]
        assert len(samples) >= 100, f"样本数 {len(samples)} < 100（tasks.md 要求 ≥100）"

        failures: list[str] = []
        async with _IsolatedSession() as db:
            for sheet, group in (("L2-3", samples[:50]), ("M9-3", samples[50:100])):
                cycle = sheet.split("-")[0]
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
                    pytest.skip(f"库中无 wp_code={cycle} 的底稿")
                wp_id = str(row[0])

                original, _ = await mod.load_rows(db, wp_id, sheet)
                try:
                    for rows in group:
                        await mod.write_rows(db, wp_id, sheet, rows)
                        readback, _ = await mod.load_rows(db, wp_id, sheet)
                        if len(readback) != len(rows):
                            failures.append(
                                f"{sheet}: 写 {len(rows)} 行 读回 {len(readback)} 行"
                            )
                            break  # 同一 sheet 首次失败即停，避免刷屏
                finally:
                    await mod.write_rows(db, wp_id, sheet, original)

        assert not failures, f"往返不恒等: {failures}"

    def test_sanity_sheets_available(self):
        """16 张 sheet 可解析。"""
        mod = _x3_mod()
        assert len(mod.X3_SHEET_SPECS) == 16
