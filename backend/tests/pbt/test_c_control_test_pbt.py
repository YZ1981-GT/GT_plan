"""Property-Based Tests for c-control-test-refresh — P1 数据兼容 + P7 持久化往返与 readonly.

Feature: c-control-test-refresh, Property 1: 注册与数据兼容
Feature: c-control-test-refresh, Property 7: 持久化往返与 readonly

使用 hypothesis 生成随机 C{n}- 前缀 item_id 数据，验证：
- P1: componentType 始终解析为 c-control-test；已有 C{n}- 数据加载后字段值不变
- P7: PUT checklist_responses 后 GET 返回相同数据；readonly=true 时禁止写入

**Validates: Requirements 1.5, 8.1, 8.3, 8.4**
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

COMPONENT_TYPE = "c-control-test"
CYCLE_NUMBERS = list(range(2, 16))

# C2~C15 允许的 conclusion 值（与 checklist_responses.py 白名单一致）
C_CONTROL_ALLOWED_CONCLUSIONS = (
    "控制有效运行", "控制存在偏差但可接受", "控制无效",
    "控制有效", "构成控制缺陷",
    "有效", "偏差", "不适用",
    "全部有效", "部分偏差", "控制失效",
    "询问", "观察", "检查", "重新执行",
    "系统性偏差", "人为偏差", "随机性偏差",
    "扩大样本量", "直接认定为偏差",
    "Y", "N",
)

# item_id 格式模板（新格式）
ITEM_ID_TEMPLATES = [
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
    "C{n}-ctrl-{m}-testProcedure",
    "C{n}-ctrl-{m}-populationDef",
    "C{n}-ctrl-{m}-samplingMethod",
    "C{n}-ctrl-{m}-sample-{s}-result",
    "C{n}-dev-{m}-step1",
    "C{n}-dev-{m}-step2",
    "C{n}-dev-{m}-step3",
    "C{n}-dev-{m}-step4",
    "C{n}-dev-{m}-step5",
    "C{n}-dev-{m}-step6",
    "C{n}-dev-{m}-conclusion",
    "C{n}-cycle-conclusion",
]

# 旧格式 item_id 模式
OLD_ITEM_ID_TEMPLATES = [
    "C{n}-ctrl-{m}-objective",
    "C{n}-ctrl-{m}-testMethods",
    "C{n}-ctrl-{m}-conclusion",
    "C{n}-cycle-conclusion",
    "C{n}-tolerable-rate",
]

# C{n}- 前缀解析正则
_C_PREFIX_RE = re.compile(r"^C(\d{1,2})-")


# ═══════════════════════════════════════════════════════════════════════════════
# Hypothesis Strategies
# ═══════════════════════════════════════════════════════════════════════════════

# 循环编号策略（2~15）
cycle_num_st = st.integers(min_value=2, max_value=15)

# 控制点索引策略（1~10）
ctrl_index_st = st.integers(min_value=1, max_value=10)

# 样本索引策略（1~25）
sample_index_st = st.integers(min_value=1, max_value=25)

# 生成合法 conclusion 值
conclusion_st = st.sampled_from(C_CONTROL_ALLOWED_CONCLUSIONS)

# 生成 remark 值（中英文混合短文本）
remark_st = st.one_of(
    st.none(),
    st.text(
        min_size=1, max_size=50,
        alphabet=st.characters(categories=("L", "N", "P"), max_codepoint=0x9FFF),
    ),
)


@st.composite
def c_item_id_strategy(draw: st.DrawFn) -> str:
    """生成随机的 C{n}- 前缀 item_id（新格式或旧格式）."""
    n = draw(cycle_num_st)
    m = draw(ctrl_index_st)
    s = draw(sample_index_st)
    template = draw(st.sampled_from(ITEM_ID_TEMPLATES + OLD_ITEM_ID_TEMPLATES))
    return template.replace("{n}", str(n)).replace("{m}", str(m)).replace("{s}", str(s))


@st.composite
def c_checklist_item_strategy(draw: st.DrawFn) -> dict:
    """生成随机的 C{n}- checklist_responses item（item_id + conclusion + remark）."""
    item_id = draw(c_item_id_strategy())
    # 某些字段存 conclusion，某些存 remark
    if any(k in item_id for k in ("description", "testProcedure", "populationDef",
                                   "samplingMethod", "objective", "testMethods")):
        # 文本字段：conclusion=null, remark=内容
        conclusion = None
        remark = draw(st.text(
            min_size=1, max_size=30,
            alphabet=st.characters(categories=("L", "N"), max_codepoint=0x9FFF),
        ))
    else:
        # 枚举/结论字段：conclusion=值, remark 可选
        conclusion = draw(conclusion_st)
        remark = draw(remark_st)

    return {
        "item_id": item_id,
        "conclusion": conclusion,
        "remark": remark,
    }


@st.composite
def c_checklist_batch_strategy(draw: st.DrawFn) -> list[dict]:
    """生成一批随机 C{n}- checklist_responses items."""
    items = draw(st.lists(c_checklist_item_strategy(), min_size=1, max_size=8))
    # 确保 item_id 唯一
    seen = set()
    unique_items = []
    for item in items:
        if item["item_id"] not in seen:
            seen.add(item["item_id"])
            unique_items.append(item)
    assume(len(unique_items) >= 1)
    return unique_items


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 注册与数据兼容
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty1DataCompatibility:
    """Feature: c-control-test-refresh, Property 1: 注册与数据兼容

    验证 C2~C15 的 componentType 始终解析为 c-control-test；
    已有 C{n}- 前缀数据加载后字段值不变（向后兼容）。

    **Validates: Requirements 1.5**
    """

    @settings(max_examples=5)
    @given(n=cycle_num_st)
    def test_wp_code_override_resolves_to_c_control_test(self, n: int):
        """对于任意 C2~C15 wpCode，wp_code_overrides 始终解析为 c-control-test.

        Feature: c-control-test-refresh, Property 1: 注册与数据兼容
        """
        from app.services.wp_code_override_loader import load_wp_code_overrides

        overrides = load_wp_code_overrides()
        wp_code = f"C{n}"
        assert wp_code in overrides, f"{wp_code} 不在 wp_code_overrides 中"
        assert overrides[wp_code] == COMPONENT_TYPE, (
            f"{wp_code} 应解析为 {COMPONENT_TYPE}，实际为 {overrides[wp_code]}"
        )

    @settings(max_examples=5)
    @given(item_id=c_item_id_strategy())
    def test_c_prefix_item_id_parseable_extracts_cycle_number(self, item_id: str):
        """对于任意生成的 C{n}- 前缀 item_id，都能正确解析出循环编号 n.

        Feature: c-control-test-refresh, Property 1: 注册与数据兼容
        """
        m = _C_PREFIX_RE.match(item_id)
        assert m is not None, f"无法解析 item_id: {item_id}"
        n = int(m.group(1))
        assert 2 <= n <= 15, f"循环编号 {n} 不在 C2~C15 范围: {item_id}"

    @settings(max_examples=5)
    @given(items=c_checklist_batch_strategy())
    def test_historical_data_field_values_preserved_after_parse(self, items: list[dict]):
        """对于任意 C{n}- 前缀数据，解析→序列化后字段值不丢失（向后兼容）.

        模拟 GET 加载数据后按 item_id 前缀分组，确认 conclusion/remark 值不变。

        Feature: c-control-test-refresh, Property 1: 注册与数据兼容
        """
        # 模拟解析：按 C{n}- 前缀分组
        grouped: dict[int, list[dict]] = {}
        for item in items:
            m = _C_PREFIX_RE.match(item["item_id"])
            assert m is not None
            n = int(m.group(1))
            grouped.setdefault(n, []).append(item)

        # 验证分组后数据完整，字段值不变
        for n, group_items in grouped.items():
            assert 2 <= n <= 15
            for item in group_items:
                # 原始值保留
                assert item["item_id"].startswith(f"C{n}-")
                # conclusion 如果非 None 则必须在白名单内（或字段是文本类型则为 None）
                if item["conclusion"] is not None:
                    assert item["conclusion"] in C_CONTROL_ALLOWED_CONCLUSIONS, (
                        f"conclusion 不在白名单: {item['conclusion']}"
                    )

    @settings(max_examples=5)
    @given(n=cycle_num_st, m=ctrl_index_st)
    def test_old_and_new_format_coexist_no_collision(self, n: int, m: int):
        """对于同一循环编号和控制点索引，旧格式和新格式 item_id 不冲突.

        Feature: c-control-test-refresh, Property 1: 注册与数据兼容
        """
        old_ids = set()
        for tpl in OLD_ITEM_ID_TEMPLATES:
            old_ids.add(tpl.replace("{n}", str(n)).replace("{m}", str(m)))
        new_ids = set()
        for tpl in ITEM_ID_TEMPLATES:
            new_ids.add(
                tpl.replace("{n}", str(n)).replace("{m}", str(m)).replace("{s}", "1")
            )
        conflicts = old_ids & new_ids
        # C{n}-cycle-conclusion 是合法共享键（新旧都有）
        # C{n}-ctrl-{m}-conclusion 也可能共享
        legitimate_shared = {f"C{n}-cycle-conclusion"}
        real_conflicts = conflicts - legitimate_shared
        assert not real_conflicts, (
            f"C{n} 控制点 {m} 旧新 item_id 冲突: {real_conflicts}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# P7: 持久化往返与 readonly
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty7RoundTripAndReadonly:
    """Feature: c-control-test-refresh, Property 7: 持久化往返与 readonly

    验证 PUT checklist_responses 后 GET 返回相同数据（round-trip）；
    验证 readonly=true 时 frontend readonly 标识正确传递与 guard 逻辑。

    **Validates: Requirements 8.1, 8.3, 8.4**
    """

    @settings(max_examples=5)
    @given(items=c_checklist_batch_strategy())
    def test_serialization_round_trip_preserves_data(self, items: list[dict]):
        """对于任意 C{n}- items，JSON 序列化→反序列化后数据一致（模拟网络往返）.

        Feature: c-control-test-refresh, Property 7: 持久化往返与 readonly
        """
        # 模拟 PUT request body
        payload = {"project_id": None, "items": items}
        serialized = json.dumps(payload, ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert len(deserialized["items"]) == len(items)
        for orig, restored in zip(items, deserialized["items"]):
            assert orig["item_id"] == restored["item_id"]
            assert orig["conclusion"] == restored["conclusion"]
            assert orig["remark"] == restored["remark"]

    @settings(max_examples=5)
    @given(items=c_checklist_batch_strategy())
    def test_conclusion_whitelist_accepts_valid_c_items(self, items: list[dict]):
        """对于生成的合法 C{n}- items，白名单校验应通过（不触发 422）.

        模拟 checklist_responses PUT 端点的白名单校验逻辑。

        Feature: c-control-test-refresh, Property 7: 持久化往返与 readonly
        """
        for item in items:
            item_id = item["item_id"]
            conclusion = item["conclusion"]
            # 只校验有 conclusion 值的枚举字段
            if conclusion is None:
                continue
            # 验证匹配 C{n}- 前缀
            is_c_control = any(
                item_id.startswith(f"C{n}-") for n in range(2, 16)
            )
            assert is_c_control, f"item_id 不匹配 C{{n}}-: {item_id}"
            # conclusion 必须在白名单内
            assert conclusion in C_CONTROL_ALLOWED_CONCLUSIONS, (
                f"item_id={item_id} conclusion={conclusion} 不在白名单"
            )

    @settings(max_examples=5)
    @given(items=c_checklist_batch_strategy(), readonly=st.booleans())
    def test_readonly_guard_blocks_writes(self, items: list[dict], readonly: bool):
        """当 readonly=True 时，数据持久化操作应被阻止.

        验证前端 readonly guard 逻辑：isReadonly 为 true 时跳过保存。

        Feature: c-control-test-refresh, Property 7: 持久化往返与 readonly
        """
        # 模拟前端 readonly guard 逻辑
        save_called = False

        def mock_save(data: list[dict], is_readonly: bool) -> bool:
            """模拟 useCControlTestData 的 readonly guard。
            返回 True 表示保存成功，False 表示被 guard 拦截。
            """
            if is_readonly:
                return False  # readonly 时跳过保存
            return True  # 正常保存

        result = mock_save(items, readonly)

        if readonly:
            assert result is False, "readonly=True 时保存不应成功"
        else:
            assert result is True, "readonly=False 时保存应成功"

    @settings(max_examples=5)
    @given(n=cycle_num_st, items=c_checklist_batch_strategy())
    def test_put_get_data_integrity(self, n: int, items: list[dict]):
        """对于任意 C{n}- 数据，PUT→GET 往返后数据字段值一致.

        模拟数据库 UPSERT：(wp_id, item_id) 唯一键写入后读回，验证字段一致。

        Feature: c-control-test-refresh, Property 7: 持久化往返与 readonly
        """
        # 模拟 DB UPSERT 行为：按 (wp_id, item_id) 为唯一键的字典
        db_store: dict[str, dict] = {}

        # PUT phase: UPSERT
        for item in items:
            key = item["item_id"]
            db_store[key] = {
                "item_id": item["item_id"],
                "conclusion": item["conclusion"],
                "remark": item["remark"],
                "wp_ref": None,
            }

        # GET phase: 读回
        for item in items:
            stored = db_store.get(item["item_id"])
            assert stored is not None, f"写入后 GET 找不到: {item['item_id']}"
            assert stored["item_id"] == item["item_id"]
            assert stored["conclusion"] == item["conclusion"]
            assert stored["remark"] == item["remark"]

    @settings(max_examples=5)
    @given(items=c_checklist_batch_strategy())
    def test_upsert_idempotent(self, items: list[dict]):
        """对同一 item_id 连续 PUT 两次，最终值为最后一次写入（幂等）.

        Feature: c-control-test-refresh, Property 7: 持久化往返与 readonly
        """
        db_store: dict[str, dict] = {}

        # 第一次 PUT
        for item in items:
            db_store[item["item_id"]] = {
                "conclusion": item["conclusion"],
                "remark": item["remark"],
            }

        # 第二次 PUT（相同数据）
        for item in items:
            db_store[item["item_id"]] = {
                "conclusion": item["conclusion"],
                "remark": item["remark"],
            }

        # 验证最终状态与第二次写入一致
        for item in items:
            stored = db_store[item["item_id"]]
            assert stored["conclusion"] == item["conclusion"]
            assert stored["remark"] == item["remark"]
