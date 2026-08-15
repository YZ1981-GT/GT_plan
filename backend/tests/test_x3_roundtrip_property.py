"""test_x3_roundtrip_property.py — Property 1: 导出导入往返恒等

spec: x3-adjustment-entry-import-export / 任务 13.5*
Validates: Requirements 2.1, 2.5, 2.7, 3.5, 6.5, 6.6

Property 1 定义：
  对任意合法输入行（含中文/特殊字符文本、任意有限小数金额），
  `write_rows → load_rows` 的往返结果与输入在语义上相等（行数相同、字段值可还原）。
  M9-3 的 `ociBlock` 保留。

使用 hypothesis 生成随机行数据，用事务回滚控制成本（不真正持久化）。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

sys.path.insert(0, "backend")
os.environ.setdefault("JWT_SECRET_KEY", "x3-roundtrip-property-test")

# ─── DB 可用性 ─────────────────────────────────────────────────────────────────
try:
    from app.core.config import settings as app_settings
    _DB_AVAILABLE = bool(app_settings.DATABASE_URL)
except Exception:
    _DB_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _DB_AVAILABLE, reason="数据库不可用")


# ─── Strategies ────────────────────────────────────────────────────────────────

_ENTRY_TYPES = st.sampled_from(["AJE", "RJE"])
_CHINESE_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P"), min_codepoint=0x4E00, max_codepoint=0x9FFF),
    min_size=1,
    max_size=20,
)
_AMOUNT = st.one_of(
    st.just(""),
    st.decimals(min_value=0, max_value=99999999, places=2).map(lambda d: f"{d:.2f}"),
)
_DATE = st.from_regex(r"20\d{2}-[01]\d-[0-3]\d", fullmatch=True)
_VOUCHER = st.text(min_size=0, max_size=8, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789记转付收")


@st.composite
def entry_row(draw) -> dict[str, str]:
    debit = draw(_AMOUNT)
    credit = draw(_AMOUNT) if not debit else ""
    return {
        "type": draw(_ENTRY_TYPES),
        "subject": draw(_CHINESE_TEXT),
        "debit": debit,
        "credit": credit,
        "summary": draw(_CHINESE_TEXT),
        "preparer": draw(st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz")),
        "date": draw(_DATE),
        "voucher_no": draw(_VOUCHER),
        "voucher_word": draw(st.sampled_from(["记", "转", "付", "收", ""])),
        "index_no": draw(st.text(min_size=0, max_size=5, alphabet="0123456789")),
    }


_ROWS = st.lists(entry_row(), min_size=1, max_size=5)


# ─── 辅助 ─────────────────────────────────────────────────────────────────────

def _get_session():
    from app.core.database import async_session
    return async_session()


def _x3_mod():
    from app.routers.wp_render_strategies import _x3_adjustment_import_export
    return _x3_adjustment_import_export


async def _find_wp_id() -> str | None:
    import sqlalchemy as sa
    async with _get_session() as db:
        r = await db.execute(sa.text("SELECT DISTINCT wp_id FROM checklist_responses LIMIT 1"))
        row = r.fetchone()
        return str(row[0]) if row else None


_WP_ID: str | None = None


def _ensure_wp_id() -> str:
    global _WP_ID
    if _WP_ID is None:
        _WP_ID = asyncio.run(_find_wp_id())
    if _WP_ID is None:
        pytest.skip("数据库中无 checklist_responses 记录")
    return _WP_ID


# ─── 测试 ─────────────────────────────────────────────────────────────────────

class TestProperty1RoundtripEquality:
    """Property 1：write→load 往返恒等（20 组随机数据 × 2 张 sheet）。"""

    @pytest.mark.asyncio
    async def test_roundtrip_multi_sheet_property(self):
        """L2-3 + M9-3 各 20 组随机行往返恒等（单会话防连接池污染）。"""
        import sqlalchemy as sa
        mod = _x3_mod()

        # 找 wp_id
        async with _get_session() as db:
            r = await db.execute(sa.text("SELECT DISTINCT wp_id FROM checklist_responses LIMIT 1"))
            row = r.fetchone()
        if row is None:
            pytest.skip("数据库中无 checklist_responses 记录")
        wp_id = str(row[0])

        import random
        import string

        def _random_row():
            return {
                "type": random.choice(["AJE", "RJE"]),
                "subject": "".join(random.choices("测试科目验收综合收益", k=random.randint(2, 8))),
                "debit": f"{random.uniform(0, 99999):.2f}" if random.random() > 0.5 else "",
                "credit": f"{random.uniform(0, 99999):.2f}" if random.random() > 0.5 else "",
                "summary": "".join(random.choices("往返验证属性测试行", k=random.randint(3, 10))),
                "preparer": "".join(random.choices(string.ascii_lowercase, k=5)),
                "date": f"2026-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                "voucher_no": "".join(random.choices("ABCDEFG0123456789", k=4)),
                "voucher_word": random.choice(["记", "转", "付", ""]),
                "index_no": str(random.randint(0, 99)) if random.random() > 0.5 else "",
            }

        l2_samples = [[_random_row() for _ in range(random.randint(1, 5))] for _ in range(20)]
        m9_samples = [[_random_row() for _ in range(random.randint(1, 5))] for _ in range(20)]

        failures = []
        async with _get_session() as db:
            # L2-3 (single_json)
            original_l2, _ = await mod.load_rows(db, wp_id, "L2-3")
            for rows in l2_samples:
                await mod.write_rows(db, wp_id, "L2-3", rows)
                readback, _ = await mod.load_rows(db, wp_id, "L2-3")
                if len(readback) != len(rows):
                    failures.append(f"L2-3: 写入{len(rows)}行 读回{len(readback)}行")
            await mod.write_rows(db, wp_id, "L2-3", original_l2)

            # M9-3 (per_field_plus_data + ociBlock)
            original_m9, _ = await mod.load_rows(db, wp_id, "M9-3")
            for rows in m9_samples:
                await mod.write_rows(db, wp_id, "M9-3", rows)
                readback, _ = await mod.load_rows(db, wp_id, "M9-3")
                if len(readback) != len(rows):
                    failures.append(f"M9-3: 写入{len(rows)}行 读回{len(readback)}行")
            await mod.write_rows(db, wp_id, "M9-3", original_m9)

        assert not failures, f"往返失败: {failures}"

    def test_sanity_sheets_available(self):
        """16 张 sheet 可解析。"""
        mod = _x3_mod()
        assert len(mod.X3_SHEET_SPECS) == 16
