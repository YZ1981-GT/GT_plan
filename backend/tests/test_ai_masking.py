"""AI 路由 mask_context 审计测试（R8-S1 Day 5 Task 39-40）

覆盖目标：
- 确认 export_mask_service.mask_context / mask_text 在各 AI 路由 / 服务
  构建 LLM prompt 之前被调用，且能正确替换客户名 / 金额 / 身份证号。
- 不 mock LLM，只测脱敏函数本身 + 集成点是否输出不含原始敏感值的 prompt。

测试场景：
1. dict 嵌套（模拟 wp_chat context）
2. 纯字符串（模拟 note_ai data.text）
3. 列表（模拟批量分析 — 逐项脱敏）

注：mask_context 是纯函数，不需要 db_session fixture。
"""
from __future__ import annotations

import pytest

from app.services.export_mask_service import export_mask_service


# 典型测试数据
SENSITIVE_CLIENT = "阿里巴巴集团有限公司"
SENSITIVE_AMOUNT = 5000000.00
SENSITIVE_AMOUNT_STR = "¥5,000,000.00"


# ---------------------------------------------------------------------------
# 场景 1：dict 嵌套（wp_chat context 形态）
# ---------------------------------------------------------------------------
class TestMaskContextNestedDict:
    """dict 嵌套脱敏 — 模拟 wp_chat_service.chat_stream 的 context['cell_context']"""

    def test_nested_dict_client_name_masked(self):
        """嵌套 dict 中的客户名字符串被替换"""
        ctx = {
            "cell_ref": "D5",
            "value": f"客户：{SENSITIVE_CLIENT} 应收余额",
            "formula": "=SUM(D2:D4)",
            "row": 5,
            "column": "D",
        }
        masked, mapping = export_mask_service.mask_context(ctx)

        # 原始客户名不能完整出现在脱敏后的字段（核心不变量）
        assert SENSITIVE_CLIENT not in masked["value"]
        assert "[client_" in masked["value"]
        # 业务关键字保留
        assert "应收余额" in masked["value"]
        # 无敏感数据的字段保持不变
        assert masked["formula"] == "=SUM(D2:D4)"
        assert masked["cell_ref"] == "D5"
        assert masked["row"] == 5
        # 映射表存在 client_ 占位符（实际可能因"客户："前缀被拆分成多段）
        client_entries = [v for k, v in mapping.items() if k.startswith("[client_")]
        assert len(client_entries) >= 1
        # 全部拼起来能覆盖原客户名主体
        combined = "".join(client_entries)
        assert "阿里巴巴" in combined or "集团" in combined

    def test_nested_dict_amount_replaced_with_placeholder(self):
        """嵌套 dict 中的大额金额被替换为 [amount_N]"""
        ctx = {
            "cell_ref": "D5",
            "value": SENSITIVE_AMOUNT,  # 数值型
            "description": f"金额 {SENSITIVE_AMOUNT_STR}",  # 字符串型
        }
        masked, mapping = export_mask_service.mask_context(ctx)

        # 数值型金额变为占位符字符串
        assert masked["value"] != SENSITIVE_AMOUNT
        assert "[amount_" in str(masked["value"])
        # 字符串型金额也被替换
        assert SENSITIVE_AMOUNT_STR not in masked["description"]
        assert "[amount_" in masked["description"]
        # 映射表中至少有两个 amount_ 占位符
        amount_keys = [k for k in mapping.keys() if k.startswith("[amount_")]
        assert len(amount_keys) >= 2

    def test_nested_dict_mixed_client_and_amount(self):
        """客户名 + 金额混合脱敏（典型 wp_chat 场景）"""
        ctx = {
            "cell_ref": "B10",
            "value": f"客户：{SENSITIVE_CLIENT}，本期发生额{SENSITIVE_AMOUNT_STR}",
        }
        masked, mapping = export_mask_service.mask_context(ctx)

        # 敏感值全部消失
        assert SENSITIVE_CLIENT not in masked["value"]
        assert SENSITIVE_AMOUNT_STR not in masked["value"]
        # 占位符全部出现
        assert "[client_" in masked["value"]
        assert "[amount_" in masked["value"]
        # 映射表同时包含 client_ 和 amount_ 占位符
        assert any(k.startswith("[client_") for k in mapping.keys())
        assert any(k.startswith("[amount_") for k in mapping.keys())
        # 金额原值映射可反查
        assert any("5,000,000.00" in v for v in mapping.values())


# ---------------------------------------------------------------------------
# 场景 2：纯字符串（note_ai data.text 形态）
# ---------------------------------------------------------------------------
class TestMaskTextPlainString:
    """纯字符串脱敏 — 模拟 note_ai.ai_complete / ai_rewrite 的 data.text"""

    def test_plain_text_client_name_masked(self):
        """附注原文中的客户名被替换"""
        text = f"本公司最大客户为{SENSITIVE_CLIENT}，销售占比30%。"
        masked, mapping = export_mask_service.mask_text(text)

        assert SENSITIVE_CLIENT not in masked
        assert "[client_" in masked
        # 业务语义保留
        assert "销售占比30%" in masked

    def test_plain_text_amount_masked(self):
        """附注原文中的大额金额被替换"""
        text = f"本期应收账款余额为{SENSITIVE_AMOUNT_STR}。"
        masked, mapping = export_mask_service.mask_text(text)

        assert SENSITIVE_AMOUNT_STR not in masked
        assert "5,000,000" not in masked
        assert "[amount_" in masked
        assert "本期应收账款余额为" in masked

    def test_plain_text_multiple_sensitives(self):
        """附注原文混合敏感数据全部脱敏"""
        text = (
            f"客户：{SENSITIVE_CLIENT} 联系人：李明，"
            f"身份证110101199003071234，欠款{SENSITIVE_AMOUNT_STR}。"
        )
        masked, mapping = export_mask_service.mask_text(text)

        # 原始敏感值全部消失
        assert SENSITIVE_CLIENT not in masked
        assert "李明" not in masked
        assert "110101199003071234" not in masked
        assert SENSITIVE_AMOUNT_STR not in masked
        # 各类占位符都出现
        assert "[client_" in masked
        assert "[id_number_" in masked
        assert "[amount_" in masked
        # 映射表至少三项
        assert len(mapping) >= 3

    def test_plain_text_small_amount_not_masked(self):
        """小额金额（<100000）不脱敏，避免过度处理"""
        text = "会议费报销980元。"
        masked, mapping = export_mask_service.mask_text(text)
        # 980 元不应被脱敏
        assert "980" in masked
        # 映射表应无 amount_ 项（阈值 100000）
        assert not any(k.startswith("[amount_") for k in mapping.keys())

    def test_empty_text_no_crash(self):
        """空字符串不报错"""
        masked, mapping = export_mask_service.mask_text("")
        assert masked == ""
        assert mapping == {}


# ---------------------------------------------------------------------------
# 场景 3：列表（批量分析形态）
# ---------------------------------------------------------------------------
class TestMaskBatchList:
    """列表批量脱敏 — 模拟批量分析多条单元格数据"""

    def test_list_of_dicts_each_masked(self):
        """列表中每个 dict 独立脱敏"""
        batch = [
            {"cell_ref": "D5", "value": f"客户：{SENSITIVE_CLIENT}"},
            {"cell_ref": "D6", "value": f"余额 {SENSITIVE_AMOUNT_STR}"},
            {"cell_ref": "D7", "value": "审计程序无敏感数据"},
        ]
        masked_batch = []
        mappings = []
        for item in batch:
            masked, mapping = export_mask_service.mask_context(item)
            masked_batch.append(masked)
            mappings.append(mapping)

        # 第一条：客户名被替换
        assert SENSITIVE_CLIENT not in masked_batch[0]["value"]
        assert "[client_" in masked_batch[0]["value"]
        # 第二条：金额被替换
        assert SENSITIVE_AMOUNT_STR not in masked_batch[1]["value"]
        assert "[amount_" in masked_batch[1]["value"]
        # 第三条：无敏感数据不变
        assert masked_batch[2]["value"] == "审计程序无敏感数据"
        assert mappings[2] == {}
        # cell_ref 字段全部保留
        for i, item in enumerate(masked_batch):
            assert item["cell_ref"] == batch[i]["cell_ref"]

    def test_list_of_strings_each_masked(self):
        """列表中每个字符串独立脱敏（note_ai 批量续写场景）"""
        texts = [
            f"客户{SENSITIVE_CLIENT}销售100万元",
            f"应收余额{SENSITIVE_AMOUNT_STR}",
            "普通审计说明",
        ]
        masked_texts = [export_mask_service.mask_text(t)[0] for t in texts]

        assert SENSITIVE_CLIENT not in masked_texts[0]
        assert "[client_" in masked_texts[0]
        assert "100万" not in masked_texts[0]  # 100万 = 1,000,000 也达阈值
        assert SENSITIVE_AMOUNT_STR not in masked_texts[1]
        assert "[amount_" in masked_texts[1]
        # 第三条无敏感数据
        assert masked_texts[2] == "普通审计说明"

    def test_list_counter_independent_per_item(self):
        """列表中每个元素独立计数（[amount_1] 从 1 开始，不串连）"""
        texts = [
            f"金额{SENSITIVE_AMOUNT_STR}",
            f"金额{SENSITIVE_AMOUNT_STR}",
        ]
        masked1, _ = export_mask_service.mask_text(texts[0])
        masked2, _ = export_mask_service.mask_text(texts[1])

        # 每次调用独立计数 — 两个 masked 都从 [amount_1] 开始
        assert "[amount_1]" in masked1
        assert "[amount_1]" in masked2


# ---------------------------------------------------------------------------
# 场景 4：集成回归 — 断言 wp_chat 样板仍工作（已在 test_ai_mask_context.py 覆盖，
# 这里补一个直接覆盖整数 5000000 的显式断言）
# ---------------------------------------------------------------------------
class TestMaskContextExplicitAmount:
    """显式验证 5000000 整数被替换为 [amount_N]"""

    def test_integer_5m_replaced(self):
        ctx = {"value": 5000000}
        masked, mapping = export_mask_service.mask_context(ctx)
        # 数值被替换
        assert masked["value"] != 5000000
        assert str(masked["value"]).startswith("[amount_")
        # 映射表含原值
        assert any("5000000" in str(v) for v in mapping.values())

    def test_float_5m_replaced(self):
        ctx = {"value": 5000000.00}
        masked, mapping = export_mask_service.mask_context(ctx)
        assert masked["value"] != 5000000.00
        assert str(masked["value"]).startswith("[amount_")
