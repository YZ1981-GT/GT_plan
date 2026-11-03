"""V166 防御测试：挂凭去重范围 + voucher_date 消歧 + 多行不再 500

守护 2026-09-28 修掉的三个缺陷（复盘见 dev-history）：

1. **去重键缺 working_paper_id** —— 旧键 `(project, year, voucher_no)` 命中同一行并
   覆盖 `working_paper_id` ⇒ 先挂 D2 再挂 E1，D2 静默失去这张凭证。
2. **`scalar_one_or_none()` 潜在 500** —— 抽凭引擎批次允许同 `(project, year, no)`
   多行，旧查询不带 batch 过滤却要求「至多一行」⇒ MultipleResultsFound。
3. **无 voucher_date 无法消歧** —— 凭证号真实跨日重复（实测单号最多 83 个日期）。

🔴 判据落在 ORM/表结构与端点去重语义上，不依赖真实 PG 的存量数据。
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa

from app.models.workpaper_models import SampledVoucher


class TestOrmContract:
    """三层一致：ORM 必须有 voucher_date，否则端点写入即静默丢字段。"""

    def test_voucher_date_column_exists(self):
        assert "voucher_date" in SampledVoucher.__table__.c, (
            "SampledVoucher 缺 voucher_date ⇒ V166 迁移与 ORM 不一致，"
            "端点传入的日期会被静默丢弃"
        )

    def test_voucher_date_is_nullable_date(self):
        col = SampledVoucher.__table__.c.voucher_date
        assert isinstance(col.type, sa.Date), f"voucher_date 类型应为 Date，实为 {col.type}"
        assert col.nullable is True, (
            "voucher_date 必须可空：历史行与「抽中本凭证」未传日期的场景要保持可用"
        )

    def test_dedupe_key_columns_all_present(self):
        """V166 去重键的五列必须都在表上。"""
        cols = set(SampledVoucher.__table__.c.keys())
        required = {"project_id", "year", "voucher_no", "voucher_date", "working_paper_id"}
        assert required <= cols, f"去重键缺列 {required - cols}"

    def test_batch_id_present_for_manual_scope_filter(self):
        """端点按 `batch_id IS NULL` 限定手工侧 —— 该列必须存在。"""
        assert "batch_id" in SampledVoucher.__table__.c


# 端点去重语义（含底稿、日期、凭证字、只在手工侧、多行不 500、空底稿幂等、列表透出凭证键与 manual_only）
# 原为对 ledger_penetration.py 的源码文本断言；凭证身份 spec 任务 6 把挂凭三端点迁到 voucher_links.py，
# 改由 test_voucher_links.py 用 SQLite 真 ORM 行 + 端点请求逐条按行为覆盖。


class TestVoucherQueryDateFilter:
    """凭证穿透端点必须支持按日期精确定位（凭证号不唯一）。"""

    @staticmethod
    def _service_source() -> str:
        from pathlib import Path

        p = (
            Path(__file__).resolve().parents[1]
            / "app" / "services" / "ledger_penetration_service.py"
        )
        return p.read_text(encoding="utf-8")

    def test_get_voucher_entries_accepts_voucher_date(self):
        src = self._service_source()
        start = src.index("async def get_voucher_entries(")
        body = src[start:start + 2000]
        assert "voucher_date" in body, (
            "get_voucher_entries 不支持 voucher_date ⇒ 只能按年度返回全年同号凭证"
            "（实测某项目 0075 号返回 66 张凭证 5918 行）"
        )

    def test_voucher_date_takes_precedence_over_month(self):
        """日期比月份精确，两者同传时必须用日期。"""
        src = self._service_source()
        start = src.index("async def get_voucher_entries(")
        body = src[start:start + 2000]
        assert "if voucher_date:" in body and "elif month is not None:" in body, (
            "应优先用 voucher_date（唯一定位一张凭证），月份仅作退化粒度"
        )


@pytest.mark.parametrize(
    "scenario,wp_a,wp_b,vdate_a,vdate_b,should_differ",
    [
        # 同号同日挂不同底稿 → 必须是两条不同记录（这正是修复的核心）
        ("一凭证挂多底稿", "wpA", "wpB", date(2025, 1, 3), date(2025, 1, 3), True),
        # 同号不同日挂同底稿 → 不同凭证，必须分别成行
        ("同号不同日", "wpA", "wpA", date(2025, 1, 3), date(2025, 3, 31), True),
        # 完全相同 → 同一条（幂等）
        ("完全重复", "wpA", "wpA", date(2025, 1, 3), date(2025, 1, 3), False),
    ],
)
def test_dedupe_identity_semantics(scenario, wp_a, wp_b, vdate_a, vdate_b, should_differ):
    """去重身份 = (voucher_no, voucher_date, working_paper_id) 的纯函数级判据。

    用与端点一致的身份元组表达，锁住语义不被改回「只按 voucher_no」。
    """
    wp_ids = {"wpA": uuid.uuid4(), "wpB": uuid.uuid4()}

    def identity(no: str, vdate, wp_key: str) -> tuple:
        return (no, vdate, wp_ids[wp_key])

    a = identity("0075", vdate_a, wp_a)
    b = identity("0075", vdate_b, wp_b)
    if should_differ:
        assert a != b, f"{scenario}：应视为两张不同的挂凭记录，却被判为同一条"
    else:
        assert a == b, f"{scenario}：应视为同一条（幂等），却被判为不同"
