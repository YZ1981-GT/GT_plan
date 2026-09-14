"""AI 结论草稿 prompt 模板

Task 2.1 (workpaper-ai-conclusion-copilot spec):
为 D1-C / D2-C 科目结论生成提供 prompt 模板。

Prompt 禁止：
- 编造函证数据、坏账计算结果、附件内容或程序状态
- 对缺失数据做出确定性判断
- 输出未来源化的确定性结论

Requirements: 1.1, 1.2, 2.5
"""

from __future__ import annotations

import json
from typing import Any


CONCLUSION_PROMPT_TEMPLATE = """你是一名审计助理，需要基于以下结构化底稿数据生成科目结论草稿。

## 审计目标
基于 {account_name} 科目（工作包 {account_package_id}），验证期末余额的存在性、完整性、准确性和列报。

## 可引用的上下文数据
{context_json}

## 缺失资料（以下信息不可用，不得编造或假设）
{missing_items}

## 输出要求
1. 审计目标
2. 已执行程序清单（仅基于 program_status_summary 数据列出）
3. 关键发现和差异说明
4. 结论（仅基于可引用数据得出）
5. 引用来源列表（标注每条结论依据的具体数据来源）
6. 缺失资料提示（列出 missing 中的所有项目）

## 禁止事项
- 不得编造函证数据或假设函证回函结果
- 不得编造坏账计算结果或 ECL 测算数据
- 不得编造附件内容或引用不存在的文档
- 不得编造程序状态或假设程序已完成
- 不得对缺失数据做出确定性判断
- 所有结论必须有引用来源支撑，不得输出未来源化的确定性结论
"""


def build_conclusion_prompt(
    account_name: str,
    account_package_id: str,
    context: dict[str, Any],
    missing: list[dict[str, Any]],
) -> str:
    """构建结论草稿 prompt

    Args:
        account_name: 科目名称
        account_package_id: 工作包 ID
        context: 结构化上下文数据（不含 missing）
        missing: 缺失上下文列表

    Returns:
        格式化后的 prompt 文本
    """
    # 构建上下文 JSON（排除 missing，已单独展示）
    context_for_prompt = {k: v for k, v in context.items() if k != "missing" and v}

    # 格式化 missing 项
    if missing:
        missing_text = "\n".join(
            f"- [{item.get('source', '未知')}] {item.get('reason', '未知原因')}：{item.get('impact', '')}"
            for item in missing
        )
    else:
        missing_text = "（无缺失资料）"

    return CONCLUSION_PROMPT_TEMPLATE.format(
        account_name=account_name,
        account_package_id=account_package_id,
        context_json=json.dumps(context_for_prompt, ensure_ascii=False, indent=2),
        missing_items=missing_text,
    )
