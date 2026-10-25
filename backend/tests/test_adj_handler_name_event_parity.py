"""test_adj_handler_name_event_parity.py — handler 名实相符守卫.

spec: adj-formula-repair-and-approval-gate-wiring · 阶段 0 任务 0.4
属性 P10（名实相符）· P12（双向变异守卫）

修复前红（on_event_adjustment_approved 订阅 BATCH_COMMITTED 而非 APPROVED）、
阶段 3 任务 3.5 完成后绿。

🔴 复盘重组：本文件曾与 test_adj_formula_resolution.py 内的
`TestHandlerNameRealityGuard` 职责重复且互有缺漏（那边多综合守卫与
batch_committed 用例、这边多 EventType 成员存在断言）。现取两版并集收敛到本文件，
resolver 相关用例归位到 test_adj_formula_resolution.py 的 Smoke 类。

Validates: Requirements 5.1, 5.2, 5.3
"""
from __future__ import annotations

import ast
from pathlib import Path

_IMPL_FILE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "event_handlers"
    / "_impl.py"
)


class TestHandlerNameEventParity:
    """扫 event_handlers/_impl.py 中 handler 函数名与订阅事件的名实一致性。"""

    @staticmethod
    def _parse_subscription_pairs() -> list[tuple[str, str]]:
        """用 AST 解析 ``event_bus.subscribe(EventType.X, handler)`` 对。"""
        source = _IMPL_FILE.read_bytes().decode("utf-8")
        tree = ast.parse(source, filename=str(_IMPL_FILE))
        pairs: list[tuple[str, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "subscribe"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "event_bus"
                and len(node.args) == 2
            ):
                continue
            event_arg, handler_arg = node.args
            if not (
                isinstance(event_arg, ast.Attribute)
                and isinstance(event_arg.value, ast.Name)
                and event_arg.value.id == "EventType"
                and isinstance(handler_arg, ast.Name)
                and handler_arg.id.startswith("on_event_")
            ):
                continue
            pairs.append((event_arg.attr, handler_arg.id))
        return pairs

    @staticmethod
    def _parse_all_subscription_pairs() -> list[tuple[str, str]]:
        """解析所有显式 ``event_bus.subscribe(EventType.X, handler)`` 调用。"""
        source = _IMPL_FILE.read_bytes().decode("utf-8")
        tree = ast.parse(source, filename=str(_IMPL_FILE))
        pairs: list[tuple[str, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "subscribe"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "event_bus"
                and len(node.args) == 2
            ):
                continue
            event_arg, handler_arg = node.args
            if (
                isinstance(event_arg, ast.Attribute)
                and isinstance(event_arg.value, ast.Name)
                and event_arg.value.id == "EventType"
                and isinstance(handler_arg, ast.Name)
            ):
                pairs.append((event_arg.attr, handler_arg.id))
        return pairs

    @classmethod
    def _adjustment_downstream_event_sets(cls) -> dict[str, set[str]]:
        """按下游职责归并审批/撤回订阅，避免用文本邻近关系判定。"""
        pairs = cls._parse_all_subscription_pairs()
        categories = {
            "workpaper_stale": {"_mark_workpapers_stale_by_account"},
            "adjustment_sse": {"_notify_adjustment_event_sse"},
            "report_and_note_stale": {"_mark_reports_stale_on_adjustment"},
            "disclosure_note_stale": {
                "on_event_adjustment_approved",
                "on_event_adjustment_review_revoked",
            },
        }
        return {
            category: {
                event_name
                for event_name, handler_name in pairs
                if handler_name in handler_names
            }
            for category, handler_names in categories.items()
        }

    def test_approved_and_revoked_events_have_equal_downstream_subscriptions(self):
        """审批与撤回必须逐类命中同一组四类下游订阅。"""
        event_sets = self._adjustment_downstream_event_sets()
        required = {"ADJUSTMENT_APPROVED", "ADJUSTMENT_REVIEW_REVOKED"}
        for category, subscribed in event_sets.items():
            assert required <= subscribed, (
                f"{category} 未同时订阅审批和撤回事件：{sorted(subscribed)}"
            )

        approved_categories = {
            category for category, subscribed in event_sets.items()
            if "ADJUSTMENT_APPROVED" in subscribed
        }
        revoked_categories = {
            category for category, subscribed in event_sets.items()
            if "ADJUSTMENT_REVIEW_REVOKED" in subscribed
        }
        assert approved_categories == revoked_categories == set(event_sets), (
            "审批与撤回下游订阅集合不相等："
            f"approved={sorted(approved_categories)}, "
            f"revoked={sorted(revoked_categories)}"
        )

    def test_ast_subscription_scanner_detects_multiline_mutation(self):
        """变异证明：AST 能识别多行 subscribe，且不依赖注释/字符串文本。"""
        source = """
from app.models.audit_platform_schemas import EventType

def register(event_bus, handler):
    event_bus.subscribe(
        EventType.ADJUSTMENT_REVIEW_REVOKED,
        handler,
    )
# event_bus.subscribe(EventType.ADJUSTMENT_APPROVED, fake_handler)
"""
        tree = ast.parse(source)
        calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "subscribe"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "event_bus"
                and len(node.args) == 2
            ):
                continue
            event_arg, handler_arg = node.args
            if (
                isinstance(event_arg, ast.Attribute)
                and isinstance(event_arg.value, ast.Name)
                and event_arg.value.id == "EventType"
                and isinstance(handler_arg, ast.Name)
            ):
                calls.append((event_arg.attr, handler_arg.id))
        assert calls == [("ADJUSTMENT_REVIEW_REVOKED", "handler")]

    def test_approved_handler_subscribes_to_approved_event(self):
        """P10: handler 名含 'approved' → 订阅事件值含 'approved'。

        当前已修正（任务 3.5）：on_event_adjustment_approved 订阅
        ADJUSTMENT_APPROVED。若有人改回 ADJUSTMENT_BATCH_COMMITTED 此测试立刻红。
        """
        pairs = self._parse_subscription_pairs()
        assert len(pairs) > 0, "未找到任何 on_event_* 订阅对，源码扫描失败"

        approved_handlers = [
            (handler, event) for event, handler in pairs
            if "approved" in handler.lower()
        ]
        assert len(approved_handlers) > 0, (
            "未找到名称含 'approved' 的 handler，"
            "on_event_adjustment_approved 可能被重命名或删除"
        )

        for handler_name, event_name in approved_handlers:
            assert "approved" in event_name.lower(), (
                f"名实不符：handler '{handler_name}' 名含 'approved'，"
                f"但订阅了 EventType.{event_name}（不含 'approved'）。"
                f"应订阅含 'approved' 语义的事件（如 ADJUSTMENT_APPROVED）。"
            )

    def test_mutation_proof_ledger_activated_name_reality(self):
        """P12 变异证明（正样本 1）：on_event_ledger_activated 名实相符。

        同一扫描器对它应通过——证明扫描器不是恒红。
        """
        pairs = self._parse_subscription_pairs()

        ledger_handlers = [
            (handler, event) for event, handler in pairs
            if handler == "on_event_ledger_activated"
        ]
        assert len(ledger_handlers) == 1, (
            f"期望恰 1 个 on_event_ledger_activated 订阅，得到 {len(ledger_handlers)}"
        )

        handler_name, event_name = ledger_handlers[0]
        # "activated" 在函数名和事件名里都出现
        assert "activated" in handler_name.lower()
        assert "activated" in event_name.lower(), (
            f"on_event_ledger_activated 应订阅含 'activated' 的事件，"
            f"实际订阅 EventType.{event_name}"
        )

    def test_mutation_proof_workpaper_reviewed_name_reality(self):
        """P12 变异证明（正样本 2）：on_event_workpaper_reviewed 名实相符。

        同一逻辑对 workpaper_reviewed → WORKPAPER_REVIEW_PASSED 应通过。
        两者共享 'review' 词根（reviewed / review_passed）。
        """
        pairs = self._parse_subscription_pairs()

        review_handlers = [
            (handler, event) for event, handler in pairs
            if handler == "on_event_workpaper_reviewed"
        ]
        assert len(review_handlers) == 1, (
            f"期望恰 1 个 on_event_workpaper_reviewed 订阅，得到 {len(review_handlers)}"
        )

        handler_name, event_name = review_handlers[0]
        # "review" 词根在两边都出现（reviewed / REVIEW_PASSED）
        assert "review" in handler_name.lower()
        assert "review" in event_name.lower(), (
            f"on_event_workpaper_reviewed 应订阅含 'review' 的事件，"
            f"实际订阅 EventType.{event_name}"
        )

    def test_batch_committed_handler_has_matching_name(self):
        """P10: on_event_adjustment_batch_committed 名实相符。

        任务 3.6 新建了独立命名的 handler 订阅 ADJUSTMENT_BATCH_COMMITTED，
        验证它的名字也与事件匹配（不复用 approved 命名）。
        """
        pairs = self._parse_subscription_pairs()

        batch_handlers = [
            (handler, event) for event, handler in pairs
            if handler == "on_event_adjustment_batch_committed"
        ]
        assert len(batch_handlers) == 1, (
            f"期望恰 1 个 on_event_adjustment_batch_committed 订阅，"
            f"得到 {len(batch_handlers)}"
        )

        handler_name, event_name = batch_handlers[0]
        assert "batch_committed" in handler_name.lower()
        assert "batch_committed" in event_name.lower(), (
            f"on_event_adjustment_batch_committed 应订阅含 'batch_committed' 的事件，"
            f"实际订阅 EventType.{event_name}"
        )

    def test_all_on_event_handlers_have_semantic_match(self):
        """综合守卫：每个 on_event_* handler 的名称与订阅事件值至少共享一个语义词根。

        这比逐个 handler 写断言更健壮——新增 on_event_* handler 若名实不符会自动红。
        """
        pairs = self._parse_subscription_pairs()
        assert len(pairs) >= 4, (
            f"期望至少 4 个 on_event_* 订阅对，得到 {len(pairs)}；"
            f"源码结构可能变化"
        )

        # 从 handler 名提取语义词根（去掉 on_event_ 前缀）
        # 从事件名取全小写
        # 要求二者至少有一个 >=4 字符的公共子串
        failures = []
        for event_name, handler_name in pairs:
            handler_stem = handler_name.replace("on_event_", "").lower()
            event_lower = event_name.lower()

            # 提取 handler stem 中所有 >=4 字符的词片段
            handler_words = {w for w in handler_stem.split("_") if len(w) >= 4}
            event_words = {w for w in event_lower.split("_") if len(w) >= 4}

            shared = handler_words & event_words
            if not shared:
                failures.append(
                    f"  {handler_name} → EventType.{event_name}: "
                    f"无共享语义词根（handler 词: {handler_words}, "
                    f"event 词: {event_words}）"
                )

        assert not failures, (
            "以下 on_event_* handler 名与订阅事件无共享语义词根（名实不符）：\n"
            + "\n".join(failures)
        )

    def test_event_type_adjustment_approved_exists(self):
        """P7 前置：EventType 枚举中存在 ADJUSTMENT_APPROVED 成员。

        修复前红（枚举无此成员）。阶段 3 任务 3.1 新增后转绿。
        """
        from app.models.audit_platform_schemas import EventType

        assert hasattr(EventType, "ADJUSTMENT_APPROVED"), (
            "EventType 枚举缺少 ADJUSTMENT_APPROVED 成员"
        )
        assert EventType.ADJUSTMENT_APPROVED.value == "adjustment.approved"
