"""底稿级 LLM 上下文注入器

构建 system prompt，将底稿元信息 + 编制说明 + 已填数据摘要注入 LLM 对话。
遵循 vLLM 单条 system 消息约束，合并多 system 为一条。

需求: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class WpChatContext:
    """底稿 AI 对话上下文"""

    wp_code: str
    wp_name: str
    component_type: str
    client_name: str
    audit_period: str  # e.g. "2024-01-01 至 2024-12-31"
    business_category: str  # e.g. "C" (制造业)
    guidance_text: str  # from GuidanceService
    filled_data_summary: str  # summary of current data in workpaper


class ContextInjector:
    """构建底稿级 LLM system prompt"""

    SYSTEM_TEMPLATE = """你是一位经验丰富的审计助手，正在帮助审计人员编制底稿。

当前底稿信息：
- 底稿编码：{wp_code}
- 底稿名称：{wp_name}
- 类型：{component_type}
- 客户名称：{client_name}
- 审计期间：{audit_period}
- 行业类别：{business_category}

编制说明：
{guidance_text}

当前已填写数据摘要：
{filled_data_summary}

请根据以上上下文回答用户关于底稿编制的问题。回答应简洁、准确、符合中国注册会计师审计准则。"""

    MAX_GUIDANCE_TOKENS = 1500
    MAX_FILLED_DATA_TOKENS = 2000
    MAX_SYSTEM_PROMPT_TOKENS = 4000

    def build_system_prompt(self, ctx: WpChatContext) -> str:
        """构建单条 system prompt（保证总量 ≤ 4000 tokens）"""
        guidance = self._truncate_to_tokens(ctx.guidance_text, max_tokens=self.MAX_GUIDANCE_TOKENS)
        filled = self._truncate_to_tokens(ctx.filled_data_summary, max_tokens=self.MAX_FILLED_DATA_TOKENS)

        prompt = self.SYSTEM_TEMPLATE.format(
            wp_code=ctx.wp_code,
            wp_name=ctx.wp_name,
            component_type=ctx.component_type,
            client_name=ctx.client_name,
            audit_period=ctx.audit_period,
            business_category=ctx.business_category,
            guidance_text=guidance or "（暂无编制说明）",
            filled_data_summary=filled or "（暂无已填数据）",
        )

        # 最终总量截断保护
        prompt = self._truncate_to_tokens(prompt, max_tokens=self.MAX_SYSTEM_PROMPT_TOKENS)
        return prompt

    def _build_filled_data_summary(
        self, wp_code: str, component_type: str, wp_data: dict | None
    ) -> str:
        """按底稿类型生成已填数据摘要

        - 审定表(*-1): 科目名+审定金额前 10 行
        - 程序表(*A): 已完成步骤数/总步骤数
        - 其他: 非空字段数/总字段数
        """
        if not wp_data:
            return ""

        # 审定表（wp_code 以 -1 结尾）
        if re.search(r"-1$", wp_code):
            return self._summarize_determination_table(wp_data)

        # 程序表（wp_code 以 A 结尾且长度 > 1）
        if wp_code.endswith("A") and len(wp_code) > 1:
            return self._summarize_program_table(wp_data)

        # 其他类型：统计非空字段
        return self._summarize_generic(wp_data)

    def _summarize_determination_table(self, wp_data: dict) -> str:
        """审定表摘要：提取前 10 行科目+金额"""
        lines: list[str] = []
        rows = wp_data.get("rows") or wp_data.get("data") or []
        if isinstance(rows, list):
            for row in rows[:10]:
                if isinstance(row, dict):
                    account = row.get("account_name") or row.get("科目") or ""
                    amount = row.get("audited_amount") or row.get("金额") or ""
                    if account or amount:
                        lines.append(f"  科目: {account}, 金额: {amount}")
        if lines:
            return f"审定表数据（前{len(lines)}行）：\n" + "\n".join(lines)
        return ""

    def _summarize_program_table(self, wp_data: dict) -> str:
        """程序表摘要：已完成/总步骤数"""
        steps = wp_data.get("steps") or wp_data.get("programs") or []
        if not isinstance(steps, list):
            return ""
        total = len(steps)
        completed = sum(
            1 for s in steps
            if isinstance(s, dict) and s.get("completed", False)
        )
        return f"程序表进度：已完成 {completed}/{total} 步骤"

    def _summarize_generic(self, wp_data: dict) -> str:
        """通用摘要：非空字段数/总字段数"""
        if not isinstance(wp_data, dict):
            return ""
        total_fields = len(wp_data)
        non_empty = sum(1 for v in wp_data.values() if v is not None and v != "" and v != [])
        return f"已填写数据：{non_empty}/{total_fields} 个字段非空"

    def _truncate_to_tokens(self, text: str, max_tokens: int = 2000) -> str:
        """按完整行截断，不在单元格值中间断

        近似算法：1 token ≈ 2 个中文字符（≈ 4 bytes UTF-8）
        对于混合中英文，取 max(字符数/2, 英文单词数) 作为 token 估算
        简化实现：max_chars = max_tokens * 2
        """
        if not text:
            return ""

        max_chars = max_tokens * 2

        if len(text) <= max_chars:
            return text

        # 按行截断，保持完整行
        lines = text.split("\n")
        result_lines: list[str] = []
        current_chars = 0

        for line in lines:
            line_chars = len(line) + 1  # +1 for newline
            if current_chars + line_chars > max_chars:
                break
            result_lines.append(line)
            current_chars += line_chars

        # 至少保留第一行（即使超限也截断它）
        if not result_lines and lines:
            result_lines.append(lines[0][:max_chars])

        return "\n".join(result_lines)

    @staticmethod
    def merge_system_messages(messages: list[dict]) -> list[dict]:
        """合并多条 system 消息为一条（vLLM 约束：拒绝多条 system）

        将所有 role=system 的消息内容合并为单条，保持其他消息不变。
        合并后的 system 消息置于列表首位。
        """
        system_parts: list[str] = []
        other_messages: list[dict] = []

        for msg in messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if content:
                    system_parts.append(content)
            else:
                other_messages.append(msg)

        result: list[dict] = []
        if system_parts:
            merged_content = "\n\n".join(system_parts)
            result.append({"role": "system", "content": merged_content})

        result.extend(other_messages)
        return result
