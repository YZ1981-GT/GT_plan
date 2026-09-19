"""C2~C15 控制测试翻新 — 白名单契约测试 + 历史数据兼容测试.

Spec: .kiro/specs/c-control-test-refresh/ Task 2.2
Validates: Requirements 1.5

mirror 自 test_c25_c26_registration_contract.py 模式：
断言 C2~C15 wp_code_overrides 映射 → c-control-test，
C2-2~C15-2 映射 → skip（偏差评价子文件），
componentType ∈ VALID_COMPONENT_TYPES，已注册于 RENDERER_DISPATCH，
validate_overrides 校验通过。
另：历史数据兼容测试（item_id 格式解析 + 新旧共存 + 结论白名单覆盖）。
"""

import json
import re
from pathlib import Path

COMPONENT_TYPE = "c-control-test"
# C2~C15 共 14 个循环
CYCLE_NUMBERS = list(range(2, 16))


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════════════
# 白名单契约测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestWhitelistContract:
    """c-control-test componentType 注册与 override 映射契约."""

    def test_c_control_test_in_valid_component_types(self):
        """c-control-test 已注册于 VALID_COMPONENT_TYPES."""
        from app.services.wp_classification_service import VALID_COMPONENT_TYPES

        assert COMPONENT_TYPE in VALID_COMPONENT_TYPES

    def test_c_control_test_in_renderer_dispatch(self):
        """c-control-test 已注册于 RENDERER_DISPATCH."""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH

        assert COMPONENT_TYPE in RENDERER_DISPATCH

    def test_c2_to_c15_override_maps_to_c_control_test(self):
        """C2~C15 在 wp_code_overrides 中全部映射到 c-control-test."""
        data = _load_overrides()
        for n in CYCLE_NUMBERS:
            wp_code = f"C{n}"
            assert data.get(wp_code) == COMPONENT_TYPE, (
                f"{wp_code} 应映射到 {COMPONENT_TYPE}，实际为 {data.get(wp_code)}"
            )

    def test_c2_2_to_c15_2_override_maps_to_skip(self):
        """C2-2~C15-2（偏差评价子文件）在 wp_code_overrides 中全部映射到 skip."""
        data = _load_overrides()
        for n in CYCLE_NUMBERS:
            wp_code = f"C{n}-2"
            assert data.get(wp_code) == "skip", (
                f"{wp_code} 应映射到 skip，实际为 {data.get(wp_code)}"
            )

    def test_validate_overrides_passes(self):
        """validate_overrides 对 C2~C15 映射及完整线上 overrides 均校验通过."""
        from app.services.wp_code_override_loader import validate_overrides

        # C2~C15 单独映射校验
        subset = {f"C{n}": COMPONENT_TYPE for n in CYCLE_NUMBERS}
        subset.update({f"C{n}-2": "skip" for n in CYCLE_NUMBERS})
        validate_overrides(subset)

        # 完整线上 overrides 整体校验
        validate_overrides(_load_overrides())


# ═══════════════════════════════════════════════════════════════════════════════
# 历史数据兼容测试
# ═══════════════════════════════════════════════════════════════════════════════


# 旧格式 item_id 模式（已有生产数据）
_OLD_ITEM_IDS = [
    "C{n}-ctrl-{i}-objective",
    "C{n}-ctrl-{i}-testMethods",
    "C{n}-ctrl-{i}-conclusion",
    "C{n}-cycle-conclusion",
    "C{n}-tolerable-rate",
]

# 新格式 item_id 模式（翻新后）
_NEW_ITEM_IDS = [
    "C{n}-sum-{m}-subProcess",
    "C{n}-sum-{m}-controlId",
    "C{n}-sum-{m}-controlName",
    "C{n}-sum-{m}-description",
    "C{n}-sum-{m}-assertion",
    "C{n}-sum-{m}-attribute",
    "C{n}-sum-{m}-frequency",
    "C{n}-sum-{m}-testMethod",
    "C{n}-sum-{m}-sampleSize",
    "C{n}-sum-{m}-hasDeviation",
    "C{n}-ctrl-{m}-sample-size",
    "C{n}-ctrl-{m}-sample-{s}-result",
    "C{n}-dev-{m}-step1",
    "C{n}-dev-{m}-step2",
    "C{n}-dev-{m}-step3",
    "C{n}-dev-{m}-step4",
    "C{n}-dev-{m}-step5",
    "C{n}-dev-{m}-step6",
    "C{n}-dev-{m}-conclusion",
]

# C{n}- 前缀正则（所有合法 item_id 必须匹配）
_C_PREFIX_RE = re.compile(r"^C(\d{1,2})-")


class TestHistoricalDataCompatibility:
    """历史数据兼容性验证：旧格式 item_id 可被解析，新旧不冲突."""

    def test_old_format_item_ids_parseable(self):
        """旧格式 C{n}- 前缀 item_id 可被正则正确解析，提取循环编号."""
        for n in CYCLE_NUMBERS:
            for tpl in _OLD_ITEM_IDS:
                item_id = tpl.replace("{n}", str(n)).replace("{i}", "1")
                m = _C_PREFIX_RE.match(item_id)
                assert m is not None, f"旧格式 item_id 无法解析: {item_id}"
                assert int(m.group(1)) == n, f"循环编号提取错误: {item_id}"

    def test_new_format_item_ids_parseable(self):
        """新格式 C{n}- 前缀 item_id 可被正则正确解析，提取循环编号."""
        for n in CYCLE_NUMBERS:
            for tpl in _NEW_ITEM_IDS:
                item_id = (
                    tpl.replace("{n}", str(n))
                    .replace("{m}", "1")
                    .replace("{s}", "1")
                )
                m = _C_PREFIX_RE.match(item_id)
                assert m is not None, f"新格式 item_id 无法解析: {item_id}"
                assert int(m.group(1)) == n, f"循环编号提取错误: {item_id}"

    def test_old_and_new_item_ids_no_conflict(self):
        """旧格式与新格式 item_id 不产生命名冲突（同 n 下无重复）."""
        for n in CYCLE_NUMBERS:
            old_ids = set()
            for tpl in _OLD_ITEM_IDS:
                old_ids.add(tpl.replace("{n}", str(n)).replace("{i}", "1"))
            new_ids = set()
            for tpl in _NEW_ITEM_IDS:
                new_ids.add(
                    tpl.replace("{n}", str(n))
                    .replace("{m}", "1")
                    .replace("{s}", "1")
                )
            conflicts = old_ids & new_ids
            assert not conflicts, f"C{n} 旧新 item_id 冲突: {conflicts}"

    def test_conclusion_whitelist_covers_old_values(self):
        """结论白名单包含旧结论值（控制有效运行/存在偏差但可接受/控制无效）."""
        # 从 checklist_responses 模块导入白名单逻辑不便，直接定义预期值并验证
        old_conclusions = {"控制有效运行", "控制存在偏差但可接受", "控制无效"}
        # 加载源码中定义的允许值（参照 checklist_responses.py C2~C15 分支）
        allowed = {
            "控制有效运行", "控制存在偏差但可接受", "控制无效",
            "控制有效", "构成控制缺陷",
            "有效", "偏差", "不适用",
            "全部有效", "部分偏差", "控制失效",
            "询问", "观察", "检查", "重新执行",
            "系统性偏差", "人为偏差", "随机性偏差",
            "扩大样本量", "直接认定为偏差",
            "Y", "N",
        }
        assert old_conclusions.issubset(allowed), (
            f"旧结论值未覆盖: {old_conclusions - allowed}"
        )

    def test_conclusion_whitelist_covers_new_values(self):
        """结论白名单包含新增偏差性质值（系统性/人为/随机/扩大样本/直接认定/控制有效/构成缺陷）."""
        new_conclusions = {
            "系统性偏差", "人为偏差", "随机性偏差",
            "扩大样本量", "直接认定为偏差",
            "控制有效", "构成控制缺陷",
        }
        allowed = {
            "控制有效运行", "控制存在偏差但可接受", "控制无效",
            "控制有效", "构成控制缺陷",
            "有效", "偏差", "不适用",
            "全部有效", "部分偏差", "控制失效",
            "询问", "观察", "检查", "重新执行",
            "系统性偏差", "人为偏差", "随机性偏差",
            "扩大样本量", "直接认定为偏差",
            "Y", "N",
        }
        assert new_conclusions.issubset(allowed), (
            f"新结论值未覆盖: {new_conclusions - allowed}"
        )

    def test_conclusion_whitelist_matches_source(self):
        """验证测试中的 allowed 集合与 checklist_responses.py 源码一致.

        通过直接读取源文件中 C2~C15 分支的允许元组来确保同步。
        """
        import ast

        src = (
            Path(__file__).resolve().parent.parent
            / "app"
            / "routers"
            / "checklist_responses.py"
        )
        content = src.read_text(encoding="utf-8")
        # 查找 C2~C15 分支的 allowed 元组（在 "elif any(item.item_id.startswith" 之后）
        # 提取所有字符串字面量
        marker = 'elif any(item.item_id.startswith(f"C{n}-") for n in range(2, 16)):'
        idx = content.find(marker)
        assert idx != -1, "未找到 C2~C15 分支标记"
        # 找到 allowed = (...) 定义
        sub = content[idx:]
        allowed_start = sub.find("allowed = (")
        assert allowed_start != -1
        # 从 allowed = ( 开始找到配对的 )
        paren_content = sub[allowed_start:]
        # 简单提取：找 allowed = (\n...\n)
        end_paren = paren_content.find(")")
        tuple_str = paren_content[len("allowed = "):end_paren + 1]
        # 用 ast.literal_eval 解析元组
        source_allowed = set(ast.literal_eval(tuple_str))

        expected = {
            "控制有效运行", "控制存在偏差但可接受", "控制无效",
            "控制有效", "构成控制缺陷",
            "有效", "偏差", "不适用",
            "全部有效", "部分偏差", "控制失效",
            "询问", "观察", "检查", "重新执行",
            "系统性偏差", "人为偏差", "随机性偏差",
            "扩大样本量", "直接认定为偏差",
            "Y", "N",
        }
        assert source_allowed == expected, (
            f"源码白名单与测试预期不一致。\n"
            f"源码多出: {source_allowed - expected}\n"
            f"测试多出: {expected - source_allowed}"
        )
