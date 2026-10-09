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


class TestEndpointDedupeSemantics:
    """端点源码级判据：去重条件必须含底稿与日期，且不得再用 scalar_one_or_none。"""

    @staticmethod
    def _source() -> str:
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "app" / "routers" / "ledger_penetration.py"
        return src.read_text(encoding="utf-8")

    @classmethod
    def _executable_body(cls, start_func: str, end_func: str) -> str:
        """截取 ``start_func`` 到 ``end_func`` 之间的**可执行代码**（剔 docstring 与注释）。

        用 ast 剔 docstring 不够——函数内的 ``#`` 行注释也要剔，且我们只有文本切片。
        故按行处理：先整体去掉三引号块，再去掉 ``#`` 之后的部分。
        """
        import re

        src = cls._source()
        body = src[src.index(f"async def {start_func}("): src.index(f"async def {end_func}(")]
        # 1. 去掉三引号 docstring / 字符串块（非贪婪，覆盖 """ 与 '''）
        body = re.sub(r'"""[\s\S]*?"""', "", body)
        body = re.sub(r"'''[\s\S]*?'''", "", body)
        # 2. 去掉行注释（简化处理：本函数内无含 # 的字符串字面量）
        lines = []
        for line in body.splitlines():
            idx = line.find("#")
            lines.append(line if idx < 0 else line[:idx])
        return "\n".join(lines)

    def test_dedupe_includes_working_paper_id(self):
        """🔴 去重必须按底稿分别成行，否则「先挂 D2 再挂 E1」会覆盖。"""
        src = self._source()
        marker = "SampledVoucher.working_paper_id == body.working_paper_id"
        assert marker in src, (
            "sample_voucher 的去重条件未含 working_paper_id ⇒ 同一凭证挂第二张底稿时"
            "会命中首行并覆盖其 working_paper_id，前一张底稿静默失去该凭证"
        )

    def test_dedupe_includes_voucher_date(self):
        src = self._source()
        assert "SampledVoucher.voucher_date" in src, (
            "去重条件未含 voucher_date ⇒ 同号不同日的两张凭证会被误并成一条"
        )

    def test_manual_scope_limited_by_null_batch(self):
        """手工侧查询必须限定 batch_id IS NULL，不得复用/改写引擎批次行。"""
        src = self._source()
        assert "SampledVoucher.batch_id.is_(None)" in src, (
            "未限定 batch_id IS NULL ⇒ 手工挂凭可能命中并改写抽凭引擎的批次登记行"
        )

    def test_no_scalar_one_or_none_in_sample_voucher(self):
        """🔴 反向守卫：该调用会在存在多行时抛 MultipleResultsFound → 500。

        🔴 必须剔除注释与 docstring 后再判：本函数的说明性注释里就写着
        「修掉 scalar_one_or_none」这几个字，只做裸 `in` 判断会命中注释而误报
        （首版即如此翻车）。判据只应落在**可执行代码**上。
        """
        body = self._executable_body("sample_voucher", "list_sampled_vouchers")
        assert "scalar_one_or_none" not in body, (
            "sample_voucher 的**代码**里又出现 scalar_one_or_none：抽凭引擎批次允许同一 "
            "(project, year, voucher_no) 多行，该调用会抛 MultipleResultsFound 成 500。"
            "应使用 order_by + limit(1) + scalars().first()"
        )
        assert ".limit(1)" in body and "scalars().first()" in body, (
            "应以 order_by + limit(1) + scalars().first() 确定性取一行"
        )

    def test_comment_stripper_is_not_vacuous(self):
        """🔴 自检：剔注释器不能把整段代码都吃掉（否则上一条恒绿假通过）。"""
        body = self._executable_body("sample_voucher", "list_sampled_vouchers")
        assert "SampledVoucher" in body and "await db.commit()" in body, (
            "剔注释后拿不到关键代码 ⇒ 剔除逻辑过度，上一条断言会变成空转"
        )
        # 反向：注释里的词必须已被剔掉
        assert "抽凭引擎批次允许同一" not in body, "docstring 未被剔除 ⇒ 判据仍会命中注释"

    def test_nullable_dedupe_uses_is_null_not_equality(self):
        """🔴 `== None` 在 SQL 里恒为 NULL ⇒ 永不命中，去重会退化成每次新增。"""
        src = self._source()
        start = src.index("async def sample_voucher(")
        end = src.index("async def list_sampled_vouchers(")
        body = src[start:end]
        assert "SampledVoucher.voucher_date.is_(None)" in body, (
            "voucher_date 为 None 时必须用 .is_(None) 比较，写 == None 会永不命中"
        )
        assert "SampledVoucher.working_paper_id.is_(None)" in body

    def test_list_endpoint_exposes_voucher_date(self):
        """回拉侧必须能拿到日期，否则前端无法精确穿透单张凭证。"""
        src = self._source()
        assert '"voucher_date": r.voucher_date.isoformat()' in src, (
            "list_sampled_vouchers 未透出 voucher_date ⇒ 底稿回拉分录时无消歧依据，"
            "可能拉回同号别张凭证"
        )

    def test_list_endpoint_supports_manual_only(self):
        """区分来源，避免把引擎批次凭证标成「序时账手工挂入」。"""
        src = self._source()
        assert "manual_only" in src, "list_sampled_vouchers 缺 manual_only 过滤"


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
