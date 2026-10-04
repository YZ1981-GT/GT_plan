"""TB 变更历史 ← 调整复核/撤回事件的订阅与标签守卫。

chain-closure-phase3-push-rollout 任务 3：
- ADJUSTMENT_APPROVED / ADJUSTMENT_REVIEW_REVOKED 必须被 _record_tb_change_on_adjustment 订阅
- op_map 必须为两个事件提供中文 operation_type 标签（「复核通过」/「撤回复核」）

修复前红：去掉 op_map 中的 approved/revoked 条目 → 标签退化为 'unknown'
修复后绿：op_map 包含两个条目，订阅集合包含两个事件
改回即红：同修复前
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

_IMPL_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "event_handlers" / "_impl.py"


class TestTbChangeHistoryReviewEvents:
    """守卫：复核/撤回事件被 TB 变更历史 handler 订阅且 operation_type 有中文标签。"""

    @staticmethod
    def _parse_subscribe_calls() -> list[tuple[str, str]]:
        """返回 (event_type_name, handler_name) 列表，来自 _impl.py 中 event_bus.subscribe 调用。"""
        source = _IMPL_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, str(_IMPL_PATH))
        pairs: list[tuple[str, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # event_bus.subscribe(EventType.X, handler)
            if not (isinstance(func, ast.Attribute) and func.attr == "subscribe"):
                continue
            if len(node.args) < 2:
                continue
            et_node = node.args[0]
            handler_node = node.args[1]
            et_name = ""
            if isinstance(et_node, ast.Attribute):
                et_name = et_node.attr
            handler_name = ""
            if isinstance(handler_node, ast.Name):
                handler_name = handler_node.id
            if et_name and handler_name:
                pairs.append((et_name, handler_name))
        return pairs

    def test_approved_event_subscribed_to_tb_change_history(self):
        """ADJUSTMENT_APPROVED 必须有 _record_tb_change_on_adjustment 订阅。"""
        pairs = self._parse_subscribe_calls()
        matched = [
            (et, h) for et, h in pairs
            if et == "ADJUSTMENT_APPROVED" and h == "_record_tb_change_on_adjustment"
        ]
        assert len(matched) >= 1, (
            "_record_tb_change_on_adjustment 未订阅 ADJUSTMENT_APPROVED，"
            "复核通过事件不会进入试算表变更历史"
        )

    def test_revoked_event_subscribed_to_tb_change_history(self):
        """ADJUSTMENT_REVIEW_REVOKED 必须有 _record_tb_change_on_adjustment 订阅。"""
        pairs = self._parse_subscribe_calls()
        matched = [
            (et, h) for et, h in pairs
            if et == "ADJUSTMENT_REVIEW_REVOKED" and h == "_record_tb_change_on_adjustment"
        ]
        assert len(matched) >= 1, (
            "_record_tb_change_on_adjustment 未订阅 ADJUSTMENT_REVIEW_REVOKED，"
            "撤回复核事件不会进入试算表变更历史"
        )

    def test_op_map_has_approved_label(self):
        """op_map 必须为 adjustment.approved 提供中文标签。"""
        source = _IMPL_PATH.read_text(encoding="utf-8")
        # 从源码中找 op_map 字典，检查是否包含 "adjustment.approved" 键
        assert '"adjustment.approved"' in source or "'adjustment.approved'" in source, (
            "op_map 缺少 adjustment.approved 条目，"
            "复核通过的试算表变更历史 operation_type 将退化为 'unknown'"
        )
        # 验证对应的值是中文标签「复核通过」
        assert "复核通过" in source, (
            "op_map[adjustment.approved] 的标签不是「复核通过」"
        )

    def test_op_map_has_revoked_label(self):
        """op_map 必须为 adjustment.review_revoked 提供中文标签。"""
        source = _IMPL_PATH.read_text(encoding="utf-8")
        assert '"adjustment.review_revoked"' in source or "'adjustment.review_revoked'" in source, (
            "op_map 缺少 adjustment.review_revoked 条目，"
            "撤回复核的试算表变更历史 operation_type 将退化为 'unknown'"
        )
        assert "撤回复核" in source, (
            "op_map[adjustment.review_revoked] 的标签不是「撤回复核」"
        )

    def test_approved_and_revoked_tb_history_subscriptions_symmetric(self):
        """APPROVED 与 REVOKED 的 TB 变更历史订阅必须同时存在（对齐守卫补充）。"""
        pairs = self._parse_subscribe_calls()
        approved = any(
            et == "ADJUSTMENT_APPROVED" and h == "_record_tb_change_on_adjustment"
            for et, h in pairs
        )
        revoked = any(
            et == "ADJUSTMENT_REVIEW_REVOKED" and h == "_record_tb_change_on_adjustment"
            for et, h in pairs
        )
        assert approved == revoked, (
            "TB 变更历史订阅不对称："
            f"APPROVED={'已订阅' if approved else '缺'}, "
            f"REVOKED={'已订阅' if revoked else '缺'}"
        )
        assert approved and revoked, "两个事件都未订阅 TB 变更历史"


class TestReviewEventPayloadCarriesOperator:
    """守卫：复核/撤回事件载荷包含 operator_id（TB 变更历史需要）。"""

    @staticmethod
    def _find_event_publish_blocks(source: str, event_type_name: str) -> list[str]:
        """从源码中提取发布指定事件类型的代码块。"""
        tree = ast.parse(source)
        blocks = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # event_bus.publish(EventPayload(...))
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "publish":
                for arg in node.args:
                    if isinstance(arg, ast.Call):
                        src = ast.get_source_segment(source, arg)
                        if src and event_type_name in src:
                            blocks.append(src)
        return blocks

    def test_approved_event_carries_operator_id(self):
        """ADJUSTMENT_APPROVED 事件载荷的 extra 必须包含 operator_id。"""
        router_path = Path(__file__).resolve().parents[1] / "app" / "routers" / "adjustments.py"
        source = router_path.read_text(encoding="utf-8")
        blocks = self._find_event_publish_blocks(source, "ADJUSTMENT_APPROVED")
        assert blocks, "未找到发布 ADJUSTMENT_APPROVED 事件的代码块"
        # 至少一个块包含 operator_id
        assert any("operator_id" in b for b in blocks), (
            "ADJUSTMENT_APPROVED 事件载荷缺少 operator_id，"
            "TB 变更历史 handler 将因 early return 跳过记录"
        )

    def test_revoked_event_carries_operator_id(self):
        """ADJUSTMENT_REVIEW_REVOKED 事件载荷的 extra 必须包含 operator_id。"""
        router_path = Path(__file__).resolve().parents[1] / "app" / "routers" / "adjustments.py"
        source = router_path.read_text(encoding="utf-8")
        blocks = self._find_event_publish_blocks(source, "ADJUSTMENT_REVIEW_REVOKED")
        assert blocks, "未找到发布 ADJUSTMENT_REVIEW_REVOKED 事件的代码块"
        assert any("operator_id" in b for b in blocks), (
            "ADJUSTMENT_REVIEW_REVOKED 事件载荷缺少 operator_id，"
            "TB 变更历史 handler 将因 early return 跳过记录"
        )
