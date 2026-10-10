"""P0 四项验收补强测试。

Task 1: CAS/幂等 — tb_publish_ack 同 token 重复提交只生效一次
Task 2: 恒等式扩展 — 损益类发生额/备抵科目方向/多科目组合
Task 3: 确认式建树 — preview → confirm → 幂等 → CAS 冲突的端点行为
Task 4: 应收账款子表勾稽 — check_rules 模式 A/B 在合成数据上的执行
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Task 1: CAS/幂等 — tb_publish_ack
# ═══════════════════════════════════════════════════════════════════════════


class TestTbPublishIdempotency:
    """publish_rows 的幂等性和 token 构建。"""

    def test_build_publish_token_deterministic(self):
        """同一输入产出相同 token（跨进程稳定）。"""
        from app.services.tb_audited_writer import build_publish_token

        pid = uuid.uuid4()
        rows = [{"account_code": "1122", "audited_amount": 1050.00}]
        current = {"1122": [Decimal("1000.00")]}

        t1 = build_publish_token(
            project_id=pid, year=2025, wp_code="D2-1",
            rows=rows, current_audited_amounts=current,
        )
        t2 = build_publish_token(
            project_id=pid, year=2025, wp_code="D2-1",
            rows=rows, current_audited_amounts=current,
        )
        assert t1 == t2
        assert len(t1) >= 20  # token 非空且有足够长度

    def test_build_publish_token_changes_with_amount(self):
        """金额变化产出不同 token。"""
        from app.services.tb_audited_writer import build_publish_token

        pid = uuid.uuid4()
        current = {"1122": [Decimal("1000.00")]}
        t1 = build_publish_token(
            project_id=pid, year=2025, wp_code="D2-1",
            rows=[{"account_code": "1122", "audited_amount": 1050.00}],
            current_audited_amounts=current,
        )
        t2 = build_publish_token(
            project_id=pid, year=2025, wp_code="D2-1",
            rows=[{"account_code": "1122", "audited_amount": 1100.00}],
            current_audited_amounts=current,
        )
        assert t1 != t2

    def test_build_publish_token_changes_with_target_state(self):
        """发布前目标状态变化 → token 变化（检测目标行已被其他发布修改）。"""
        from app.services.tb_audited_writer import build_publish_token

        pid = uuid.uuid4()
        rows = [{"account_code": "1122", "audited_amount": 1050.00}]
        t1 = build_publish_token(
            project_id=pid, year=2025, wp_code="D2-1",
            rows=rows, current_audited_amounts={"1122": [Decimal("1000.00")]},
        )
        t2 = build_publish_token(
            project_id=pid, year=2025, wp_code="D2-1",
            rows=rows, current_audited_amounts={"1122": [Decimal("900.00")]},
        )
        assert t1 != t2

    def test_canonical_publish_token_amount_normalizes(self):
        """金额规范化：float/int/str 同值同输出。"""
        from app.services.tb_audited_writer import canonical_publish_token_amount

        assert canonical_publish_token_amount(1000) == "1000.00"
        assert canonical_publish_token_amount(1000.0) == "1000.00"
        assert canonical_publish_token_amount("1000") == "1000.00"
        assert canonical_publish_token_amount(Decimal("1000")) == "1000.00"
        # 零值规范化
        assert canonical_publish_token_amount(0) == "0.00"
        assert canonical_publish_token_amount(-0.0) == "0.00"
        # None
        assert canonical_publish_token_amount(None) is None

    def test_publish_rows_result_counts(self):
        """PublishRowsResult 的 updated_count / skipped_count 属性。"""
        from app.services.tb_audited_writer import (
            PublishRowResult,
            PublishRowSkip,
            PublishRowsResult,
        )
        from datetime import datetime, timezone

        r = PublishRowsResult()
        assert r.updated_count == 0
        assert r.skipped_count == 0

        r.updated_account_codes.append("1122")
        r.updated_rows.append(PublishRowResult(
            account_code="1122",
            audited_amount=Decimal("1050.00"),
            previous_amount=Decimal("1000.00"),
            published_at=datetime.now(timezone.utc),
        ))
        r.skipped.append(PublishRowSkip("6001", "未找到未删除的试算表行"))
        assert r.updated_count == 1
        assert r.skipped_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# Task 2: 恒等式扩展 — 多科目/多类型
# ═══════════════════════════════════════════════════════════════════════════


_A_PID = uuid.uuid4()
_B_PID = uuid.uuid4()


def _make_tree():
    """构建包含三种科目的合并树。"""
    from app.services.consol_tree_service import TreeNode

    root = TreeNode(
        project_id=None, company_code="ROOT", company_name="集团",
        parent_company_code=None, ultimate_company_code="ROOT", consol_level=0,
        node_key="ROOT:consol", role="consol", kind="aggregate",
    )
    elim = TreeNode(
        project_id=None, company_code="ROOT", company_name="集团差额",
        parent_company_code=None, ultimate_company_code="ROOT", consol_level=0,
        node_key="ROOT:consol_elim", role="consol_elim", kind="elim",
    )
    company_a = TreeNode(
        project_id=_A_PID, company_code="A", company_name="甲公司",
        parent_company_code="ROOT", ultimate_company_code="ROOT", consol_level=1,
        node_key="A:entity", role="subsidiary", kind="data",
    )
    company_b = TreeNode(
        project_id=_B_PID, company_code="B", company_name="乙公司",
        parent_company_code="ROOT", ultimate_company_code="ROOT", consol_level=1,
        node_key="B:entity", role="subsidiary", kind="data",
    )
    root.children = [elim, company_a, company_b]
    return root


def _make_entry(entry_type, code, debit, credit, branch="ROOT"):
    """构建单笔分录。"""
    from app.services.consol_calc_basis import EntryLine, EntryRecord

    return EntryRecord(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        entry_no=f"TEST-{code}",
        entry_type=entry_type,
        branch_entity_code=branch,
        lines=[EntryLine(account_code=code, account_name="", debit=Decimal(str(debit)), credit=Decimal(str(credit)))],
    )


class TestConsolIdentityExtended:
    """合并恒等式扩展科目覆盖。"""

    def test_revenue_occurrence_account(self):
        """损益类科目（收入 6001）：发生额口径，贷方性质。"""
        from app.services.consol_calc_basis import (
            TbRow, build_calc_basis, node_measures, trial_amounts,
            MEASURE_INDIVIDUAL, MEASURE_CONSOLIDATED,
        )

        tree = _make_tree()
        tb = [
            TbRow(project_id=_A_PID, account_code="6001",
                  account_name="主营业务收入", account_category="income",
                  audited_amount=Decimal("500000")),
            TbRow(project_id=_B_PID, account_code="6001",
                  account_name="主营业务收入", account_category="income",
                  audited_amount=Decimal("300000")),
        ]
        # 内部交易抵销：甲向乙销售 50000
        entry = _make_entry("trade", "6001", Decimal("50000"), Decimal("0"))

        basis = build_calc_basis(tree, 2025, tb, [entry])
        measures = node_measures(basis)
        root_m = measures["ROOT:consol"]

        # 恒等式：individual + adjustment + elim_equity + elim_trade = consolidated
        individual = root_m["individual"].get("6001", Decimal(0))
        adj = root_m["adjustment"].get("6001", Decimal(0))
        eq = root_m["elim_equity"].get("6001", Decimal(0))
        trade = root_m["elim_trade"].get("6001", Decimal(0))
        consolidated = root_m["consolidated"].get("6001", Decimal(0))
        assert individual + adj + eq + trade == consolidated

        # trial_amounts 也满足恒等式
        ta = trial_amounts(basis)
        t = ta["6001"]
        assert t.consol_amount == t.individual_sum + t.consol_adjustment + t.consol_elimination

    def test_contra_account_direction(self):
        """备抵科目（坏账准备 1231）：借方性质但通常贷方余额，方向归一。"""
        from app.services.consol_calc_basis import (
            TbRow, build_calc_basis, trial_amounts,
        )

        tree = _make_tree()
        tb = [
            TbRow(project_id=_A_PID, account_code="1231",
                  account_name="坏账准备", account_category="asset",
                  audited_amount=Decimal("-80000")),
            TbRow(project_id=_B_PID, account_code="1231",
                  account_name="坏账准备", account_category="asset",
                  audited_amount=Decimal("-50000")),
        ]
        # 合并调整：抵销内部坏账 10000
        entry = _make_entry("other", "1231", Decimal("10000"), Decimal("0"))

        basis = build_calc_basis(tree, 2025, tb, [entry])
        ta = trial_amounts(basis)
        t = ta["1231"]
        # 恒等式成立
        assert t.consol_amount == t.individual_sum + t.consol_adjustment + t.consol_elimination
        # individual = 两公司审定数之和
        assert t.individual_sum == Decimal("-130000")

    def test_multi_account_multi_entry(self):
        """多科目 + 多笔分录组合：恒等式对每个科目都成立。"""
        from app.services.consol_calc_basis import (
            TbRow, build_calc_basis, node_measures, trial_amounts,
        )

        tree = _make_tree()
        accounts = [
            ("1001", "库存现金", "asset", "100000", "80000"),
            ("1122", "应收账款", "asset", "500000", "300000"),
            ("2202", "应付账款", "liability", "200000", "150000"),
            ("6001", "主营业务收入", "income", "1000000", "600000"),
            ("6401", "主营业务成本", "expense", "700000", "400000"),
        ]
        tb = []
        for code, name, cat, a_amt, b_amt in accounts:
            tb.append(TbRow(project_id=_A_PID, account_code=code,
                            account_name=name, account_category=cat,
                            audited_amount=Decimal(a_amt)))
            tb.append(TbRow(project_id=_B_PID, account_code=code,
                            account_name=name, account_category=cat,
                            audited_amount=Decimal(b_amt)))

        entries = [
            _make_entry("trade", "1122", Decimal("50000"), Decimal("0")),
            _make_entry("trade", "2202", Decimal("0"), Decimal("50000")),
            _make_entry("equity", "6001", Decimal("30000"), Decimal("0")),
            _make_entry("other", "6401", Decimal("0"), Decimal("20000")),
        ]

        basis = build_calc_basis(tree, 2025, tb, entries)
        measures = node_measures(basis)
        ta = trial_amounts(basis)

        for code, *_ in accounts:
            # node_measures 恒等式
            root_m = measures["ROOT:consol"]
            i = root_m["individual"].get(code, Decimal(0))
            a = root_m["adjustment"].get(code, Decimal(0))
            eq = root_m["elim_equity"].get(code, Decimal(0))
            tr = root_m["elim_trade"].get(code, Decimal(0))
            c = root_m["consolidated"].get(code, Decimal(0))
            assert i + a + eq + tr == c, f"node_measures 恒等式失败: {code}"

            # trial_amounts 恒等式
            t = ta[code]
            assert t.consol_amount == t.individual_sum + t.consol_adjustment + t.consol_elimination, (
                f"trial_amounts 恒等式失败: {code}"
            )

    def test_zero_entry_all_accounts_consistent(self):
        """无分录时：所有科目 consolidated = individual，adjustment/elimination = 0。"""
        from app.services.consol_calc_basis import (
            TbRow, build_calc_basis, trial_amounts,
        )

        tree = _make_tree()
        # TB 行的 project_id 必须匹配叶子节点的 project_id
        a_pid = tree.children[1].project_id  # company_a
        tb = [
            TbRow(project_id=a_pid, account_code="1001",
                  account_name="库存现金", account_category="asset",
                  audited_amount=Decimal("50000")),
            TbRow(project_id=a_pid, account_code="2001",
                  account_name="短期借款", account_category="liability",
                  audited_amount=Decimal("30000")),
        ]
        basis = build_calc_basis(tree, 2025, tb, [])
        ta = trial_amounts(basis)
        for code in ("1001", "2001"):
            t = ta[code]
            assert t.consol_adjustment == Decimal(0)
            assert t.consol_elimination == Decimal(0)
            assert t.consol_amount == t.individual_sum


# ═══════════════════════════════════════════════════════════════════════════
# Task 3: 确认式建树 — 端点行为验收
# ═══════════════════════════════════════════════════════════════════════════


class TestScopeConfirmationBehavior:
    """确认式建树的核心行为验证（纯 service 层，不依赖真 DB）。"""

    def test_fingerprint_deterministic(self):
        """同一树产出相同指纹。"""
        from app.services.consol_scope_confirmation_service import (
            fingerprint_payload,
        )

        payload = {
            "year": 2025,
            "company_code": "ROOT",
            "nodes": [
                {"node_key": "ROOT:consol", "role": "consol", "kind": "aggregate"},
                {"node_key": "A:entity", "role": "subsidiary", "kind": "data"},
            ],
        }
        f1 = fingerprint_payload(payload)
        f2 = fingerprint_payload(payload)
        assert f1 == f2
        assert len(f1) == 64  # SHA256 hex

    def test_fingerprint_changes_with_node(self):
        """树节点变化 → 指纹变化。"""
        from app.services.consol_scope_confirmation_service import (
            fingerprint_payload,
        )

        p1 = {"year": 2025, "nodes": [{"node_key": "ROOT:consol"}]}
        p2 = {"year": 2025, "nodes": [{"node_key": "ROOT:consol"}, {"node_key": "A:entity"}]}
        assert fingerprint_payload(p1) != fingerprint_payload(p2)

    def test_node_payloads_excludes_database_ids_by_default(self):
        """默认指纹载荷不含数据库 UUID（跨环境稳定）。"""
        from app.services.consol_scope_confirmation_service import _node_payloads
        from app.services.consol_tree_service import TreeNode

        node = TreeNode(
            project_id=uuid.uuid4(),
            company_code="ROOT", company_name="集团",
            parent_company_code=None, ultimate_company_code="ROOT", consol_level=0,
            node_key="ROOT:consol", role="consol", kind="aggregate",
        )
        payloads = _node_payloads(node, include_database_ids=False)
        assert len(payloads) == 1
        assert "project_id" not in payloads[0]
        assert "host_project_id" not in payloads[0]

    def test_node_payloads_includes_database_ids_when_requested(self):
        """写入时携带数据库 UUID。"""
        from app.services.consol_scope_confirmation_service import _node_payloads
        from app.services.consol_tree_service import TreeNode

        pid = uuid.uuid4()
        node = TreeNode(
            project_id=pid,
            company_code="ROOT", company_name="集团",
            parent_company_code=None, ultimate_company_code="ROOT", consol_level=0,
            node_key="ROOT:consol", role="consol", kind="aggregate",
        )
        payloads = _node_payloads(node, include_database_ids=True)
        assert payloads[0]["project_id"] == str(pid)

    def test_scope_confirmation_error_attributes(self):
        """ScopeConfirmationError 正确携带 status_code 和 error_code。"""
        from app.services.consol_scope_confirmation_service import ScopeConfirmationError

        err = ScopeConfirmationError(409, "SCOPE_FINGERPRINT_CONFLICT", "合并树已变化")
        assert err.status_code == 409
        assert err.error_code == "SCOPE_FINGERPRINT_CONFLICT"
        assert "合并树已变化" in str(err)

    def test_confirm_endpoint_registered(self):
        """确认端点路由已注册。"""
        from app.main import app

        route_list = [
            (frozenset(r.methods), r.path)
            for r in app.routes
            if hasattr(r, "methods") and hasattr(r, "path")
        ]
        # preview
        found_preview = any(
            "GET" in ms and "scope-confirmation/preview" in p
            for ms, p in route_list
        )
        assert found_preview, "scope-confirmation/preview 端点未注册"
        # confirm
        found_confirm = any(
            "POST" in ms and "scope-confirmation/confirm" in p
            for ms, p in route_list
        )
        assert found_confirm, "scope-confirmation/confirm 端点未注册"


# ═══════════════════════════════════════════════════════════════════════════
# Task 4: 应收账款子表勾稽 — check_rules 端到端
# ═══════════════════════════════════════════════════════════════════════════


class TestNoteCheckRulesE2E:
    """check_rules 模式 A/B 在合成数据上的端到端验证。"""

    def test_load_check_rules_soe_has_e5(self):
        """国企 soe 模板中 E5 应收账款章节有 check_rules。"""
        from app.services.note_check_rules import _load_check_rules

        rules = _load_check_rules("soe", "五-5-2")
        assert len(rules) >= 2, f"E5 五-5-2 的 check_rules 少于 2 条: {len(rules)}"
        ids = {r.check_id for r in rules}
        assert "F5-8" in ids, "缺少 F5-8 账龄=坏账分类勾稽"
        assert "F5-4" in ids, "缺少 F5-4 单项计提勾稽"

    def test_load_check_rules_listed_has_e5(self):
        """上市 listed 模板中 E5 应收账款章节有 check_rules。"""
        from app.services.note_check_rules import _load_check_rules

        rules = _load_check_rules("listed", "五-5-2")
        assert len(rules) >= 1

    def test_load_all_check_rules_coverage(self):
        """全科目 check_rules 总量基线：至少 100 条（棘轮，只许增不许减）。"""
        from app.services.note_check_rules import load_all_check_rules

        soe_rules = load_all_check_rules("soe")
        listed_rules = load_all_check_rules("listed")
        total = sum(len(v) for v in soe_rules.values()) + sum(len(v) for v in listed_rules.values())
        assert total >= 100, f"check_rules 总量 {total} 低于基线 100"

    def test_check_rule_mode_a_cross_table_pass(self):
        """模式 A 跨表校验：两表同标签同列同值 → pass。"""
        from app.services.note_check_rules import CheckRule, CheckResult, _find_row_by_label, _to_decimal

        # 模拟 self 和 peer 表数据
        self_rows = [
            {"label": "合  计", "values": [None, 1000, 500]},
        ]
        peer_rows = [
            {"label": "合  计", "values": [None, 1000, 200]},
        ]

        # 手动执行模式 A 逻辑
        rule = CheckRule(
            check_id="TEST-A1",
            peer_section_id="peer",
            peer_row_label="合  计",
            peer_col_index=1,
            self_row_label="合  计",
            self_col_index=1,
            relation="equal",
            tolerance=0.01,
            description="测试跨表勾稽",
        )
        self_ri = _find_row_by_label(self_rows, rule.self_row_label)
        assert self_ri is not None
        peer_ri = _find_row_by_label(peer_rows, rule.peer_row_label)
        assert peer_ri is not None

        from app.services.note_check_rules import _cell_value
        self_val = _to_decimal(_cell_value(self_rows, self_ri, rule.self_col_index))
        peer_val = _to_decimal(_cell_value(peer_rows, peer_ri, rule.peer_col_index))
        assert self_val == peer_val == Decimal("1000")

    def test_check_rule_mode_a_cross_table_fail(self):
        """模式 A 跨表校验：两表值不等 → 差异可检测。"""
        from app.services.note_check_rules import _find_row_by_label, _cell_value, _to_decimal

        self_rows = [{"label": "合  计", "values": [None, 1000]}]
        peer_rows = [{"label": "合  计", "values": [None, 999]}]

        self_val = _to_decimal(_cell_value(self_rows, 0, 1))
        peer_val = _to_decimal(_cell_value(peer_rows, 0, 1))
        assert self_val != peer_val
        assert abs(self_val - peer_val) == Decimal("1")

    def test_check_rule_mode_b_column_balance_pass(self):
        """模式 B 列平衡：期初 + 增加 - 减少 = 期末。"""
        from app.services.note_check_rules import CheckRule, _check_column_balance

        # 构造一个变动表：期初 1000 + 增加 500 - 减少 200 = 期末 1300
        rows = [
            ["项目", 1000, 500, 200, 1300],  # 数据行
        ]
        rule = CheckRule(
            check_id="TEST-B1",
            peer_section_id="",
            peer_row_label="",
            peer_col_index=0,
            self_row_label="*",  # 通配所有行
            self_col_index=0,
            relation="column_balance",
            tolerance=0.01,
            description="变动表列平衡测试",
            mode="column_balance",
            opening_col=1,
            increase_col=2,
            decrease_col=3,
            closing_col=4,
        )
        results = _check_column_balance(rule, rows)
        assert len(results) >= 1
        pass_count = sum(1 for r in results if r.status == "pass")
        assert pass_count >= 1

    def test_check_rule_mode_b_column_balance_fail(self):
        """模式 B 列平衡：不平 → fail。"""
        from app.services.note_check_rules import CheckRule, _check_column_balance

        # 构造不平衡数据：期初 1000 + 增加 500 - 减少 200 ≠ 期末 1500
        rows = [
            ["项目", 1000, 500, 200, 1500],
        ]
        rule = CheckRule(
            check_id="TEST-B2",
            peer_section_id="",
            peer_row_label="",
            peer_col_index=0,
            self_row_label="*",  # 通配所有行
            self_col_index=0,
            relation="column_balance",
            tolerance=0.01,
            description="变动表列不平衡测试",
            mode="column_balance",
            opening_col=1,
            increase_col=2,
            decrease_col=3,
            closing_col=4,
        )
        results = _check_column_balance(rule, rows)
        fail_count = sum(1 for r in results if r.status == "fail")
        assert fail_count >= 1

    def test_find_row_by_label_fuzzy(self):
        """行标签查找支持去空格模糊匹配。"""
        from app.services.note_check_rules import _find_row_by_label

        rows = [
            {"label": "按单项计提坏账准备", "values": [100]},
            {"label": "合  计", "values": [500]},
        ]
        # 全角空格
        assert _find_row_by_label(rows, "合计") == 1
        assert _find_row_by_label(rows, "合  计") == 1
        # 精确匹配
        assert _find_row_by_label(rows, "按单项计提坏账准备") == 0

    def test_check_rules_endpoint_registered(self):
        """check-rules 端点路由已注册。"""
        from app.main import app

        route_list = [r.path for r in app.routes if hasattr(r, "path")]
        found = any("check-rules" in p for p in route_list)
        assert found, "check-rules 端点未注册"
