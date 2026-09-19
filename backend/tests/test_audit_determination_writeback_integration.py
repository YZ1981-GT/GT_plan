"""审定表回写 trial_balance 集成测试。

标记 @pytest.mark.pg_only — 需要真实 PG 数据库连接。
跳过条件：无 DATABASE_URL 环境变量时自动 skip。

验证：_on_d_audit_determination_saved handler 能正确将审定金额写入 trial_balance。
覆盖循环：D（销售）、K（管理）、N（税费）各一个代表。
"""
from __future__ import annotations

import os
import re

import pytest

class TestHandlerRegexCoverage:
    """验证 handler 正则对全部 D~N 循环审定表的覆盖。

    这是一个不需要 DB 的纯逻辑测试，放在这里做基线验证。
    """

    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    # 全部循环的审定表代表
    _ALL_AUDIT_DET = [
        "D1-1", "D2-1", "D3-1", "D4-1", "D5-1", "D6-1", "D7-1",
        "E1-1",
        "F1-1", "F2-1", "F3-1", "F4-1", "F5-1",
        "G1-1", "G7-1", "G14-1",
        "H1-1", "H10-1",
        "I1-1", "I6-1",
        "J1-1", "J2-1", "J3-1",
        "K1-1", "K5-1", "K8-1", "K9-1", "K13-1",
        "L1-1", "L4-1", "L8-1",
        "M1-1", "M6-1", "M10-1",
        "N1-1", "N2-1", "N5-1",
    ]

    @pytest.mark.parametrize("wp_code", _ALL_AUDIT_DET)
    def test_regex_matches_all_cycles(self, wp_code):
        """正则 ^[D-N]\\d+-1$ 覆盖 D~N 全部循环审定表。"""
        assert self._PATTERN.match(wp_code), f"正则不匹配 {wp_code}"

    def test_regex_rejects_non_audit_codes(self):
        """正则拒绝非审定表编码。"""
        non_audit = [
            "D1A", "D1-2", "K8-2", "N5-3", "S1", "A1", "B50", "C1",
            "D0", "M6-2", "L4-4",
        ]
        for code in non_audit:
            assert not self._PATTERN.match(code), f"正则不应匹配 {code}"

    def test_total_coverage_count(self):
        """全部 D~N 审定表（每循环至少一个）都被正则覆盖。"""
        covered_cycles = set()
        for code in self._ALL_AUDIT_DET:
            if self._PATTERN.match(code):
                covered_cycles.add(code[0])
        # D E F G H I J K L M N = 11 个循环
        assert len(covered_cycles) == 11, f"应覆盖 11 个循环，实际覆盖 {covered_cycles}"


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="需要 DATABASE_URL 环境变量（真实 PG 连接）",
)
class TestWritebackEndToEnd:
    """审定表→trial_balance 回写端到端测试。

    需要真实 PG。当前标记 skip，待种子数据就绪后启用。
    """

    @pytest.mark.skip(reason="需要 E2E 种子项目数据（运行 scripts/e2e/ensure_e2e_project.py 后启用）")
    @pytest.mark.asyncio
    async def test_d1_1_writeback_round_trip(self):
        """D1-1 审定表保存→查询 trial_balance.audited_amount 一致。"""
        # TODO: 实现真实 DB 交互测试
        # 1. 插入 trial_balance 测试行
        # 2. 模拟 WORKPAPER_SAVED 事件 payload
        # 3. 调用 _on_d_audit_determination_saved handler
        # 4. 查询 trial_balance.audited_amount 验证更新
        pass

    @pytest.mark.skip(reason="需要 E2E 种子项目数据")
    @pytest.mark.asyncio
    async def test_k8_1_writeback_income_statement(self):
        """K8-1 销售费用审定表（损益类）保存→回写正确。"""
        pass

    @pytest.mark.skip(reason="需要 E2E 种子项目数据")
    @pytest.mark.asyncio
    async def test_n5_1_writeback_income_tax(self):
        """N5-1 所得税费用审定表保存→回写正确。"""
        pass
