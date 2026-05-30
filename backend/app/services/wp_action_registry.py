"""底稿动作注册表 — functional_type → 动作配置

设计原则（design §2）：
  - 配置驱动：新增 functional_type 只需在 ACTION_REGISTRY 添加条目
  - 不改框架代码：前端 useWpFunctionalActions 读注册表渲染按钮+弹窗
  - 后端取数端点已就绪（CutoffTest/Monthly/Aging/Sampling）

每个 ActionConfig 描述：
  - label: 按钮文案（中文）
  - description: 动作说明
  - endpoint: 后端取数端点路径（相对 /api/projects/{project_id}/）
  - method: HTTP 方法
  - params_schema: 参数 JSON Schema（前端弹窗渲染用）
  - fill_strategy: 填充策略（replace_rows / append_rows / merge_cells）
  - requires_llm: 是否依赖 LLM（L2 动作标记）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ActionConfig:
    """单个动作配置"""
    label: str
    description: str
    endpoint: str
    method: str = "POST"
    params_schema: dict[str, Any] = field(default_factory=dict)
    fill_strategy: str = "replace_rows"
    requires_llm: bool = False
    icon: str = "⚡"


# ─── 动作注册表（单一来源） ─────────────────────────────────────────────────────

ACTION_REGISTRY: dict[str, list[ActionConfig]] = {
    "cutoff": [
        ActionConfig(
            label="截止测试取数",
            description="从序时账提取期末前后 N 天交易，填回截止测试底稿",
            endpoint="sampling/cutoff-test",
            params_schema={
                "type": "object",
                "properties": {
                    "account_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "title": "科目编码",
                        "description": "选择需要测试的科目",
                    },
                    "year": {"type": "integer", "title": "会计年度"},
                    "days_before": {
                        "type": "integer",
                        "title": "期末前天数",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 30,
                    },
                    "days_after": {
                        "type": "integer",
                        "title": "期末后天数",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 30,
                    },
                    "amount_threshold": {
                        "type": "number",
                        "title": "金额阈值",
                        "default": 10000,
                        "minimum": 0,
                    },
                },
                "required": ["account_codes", "year"],
            },
            fill_strategy="replace_rows",
            icon="📅",
        ),
    ],
    "aging": [
        ActionConfig(
            label="账龄分析取数",
            description="FIFO 先进先出核销算法，按账龄区间分析应收/应付余额",
            endpoint="sampling/aging-analysis",
            params_schema={
                "type": "object",
                "properties": {
                    "account_code": {"type": "string", "title": "科目编码"},
                    "base_date": {
                        "type": "string",
                        "format": "date",
                        "title": "基准日期",
                        "description": "账龄计算基准日（通常为期末日）",
                    },
                    "year": {"type": "integer", "title": "会计年度"},
                    "aging_brackets": {
                        "type": "array",
                        "title": "账龄区间",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "min_days": {"type": "integer", "minimum": 0},
                                "max_days": {"type": "integer"},
                            },
                            "required": ["label", "min_days"],
                        },
                        "default": [
                            {"label": "1年以内", "min_days": 0, "max_days": 365},
                            {"label": "1-2年", "min_days": 366, "max_days": 730},
                            {"label": "2-3年", "min_days": 731, "max_days": 1095},
                            {"label": "3年以上", "min_days": 1096},
                        ],
                    },
                },
                "required": ["account_code", "base_date"],
            },
            fill_strategy="replace_rows",
            icon="📊",
        ),
    ],
    "monthly_analysis": [
        ActionConfig(
            label="月度分析取数",
            description="按月汇总序时账数据，生成月度借贷发生额及累计余额",
            endpoint="sampling/monthly-detail",
            params_schema={
                "type": "object",
                "properties": {
                    "account_code": {"type": "string", "title": "科目编码"},
                    "year": {"type": "integer", "title": "会计年度"},
                },
                "required": ["account_code", "year"],
            },
            fill_strategy="replace_rows",
            icon="📈",
        ),
    ],
    "sampling": [
        ActionConfig(
            label="抽凭取数",
            description="从序时账按抽样方式（分层/随机/大额/MUS）抽取样本",
            endpoint="sampling/execute",
            params_schema={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "title": "抽样方式",
                        "enum": ["stratified", "random", "top_n", "mus"],
                        "enumNames": ["分层抽样", "随机抽样", "大额抽样", "货币单位抽样"],
                        "default": "random",
                    },
                    "account_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "title": "科目编码",
                    },
                    "year": {"type": "integer", "title": "会计年度"},
                    "sample_size": {
                        "type": "integer",
                        "title": "样本量",
                        "default": 25,
                        "minimum": 1,
                        "maximum": 200,
                    },
                    "amount_threshold": {
                        "type": "number",
                        "title": "大额阈值",
                        "description": "大额抽样时的金额阈值",
                    },
                },
                "required": ["method", "account_codes", "year"],
            },
            fill_strategy="append_rows",
            icon="🎯",
        ),
    ],
    "contract_ledger": [
        ActionConfig(
            label="合同台账识别",
            description="上传合同文件 → LLM 识别关键字段 → 逐份确认 → 填回台账",
            endpoint="wp-ai/contract-recognize",
            params_schema={
                "type": "object",
                "properties": {
                    "attachment_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "title": "合同附件",
                        "description": "选择已上传的合同文件",
                    },
                },
                "required": ["attachment_ids"],
            },
            fill_strategy="append_rows",
            requires_llm=True,
            icon="📄",
        ),
    ],
    "confirmation": [
        ActionConfig(
            label="函证生成",
            description="根据明细数据自动生成函证底稿",
            endpoint="sampling/confirmation-generate",
            params_schema={
                "type": "object",
                "properties": {
                    "account_code": {"type": "string", "title": "科目编码"},
                    "year": {"type": "integer", "title": "会计年度"},
                    "threshold": {
                        "type": "number",
                        "title": "函证金额阈值",
                        "default": 100000,
                    },
                },
                "required": ["account_code", "year"],
            },
            fill_strategy="replace_rows",
            icon="✉️",
        ),
    ],
}


# ─── 工具函数 ────────────────────────────────────────────────────────────────

def get_actions(functional_type: str) -> list[ActionConfig]:
    """获取指定 functional_type 的所有可用动作"""
    return ACTION_REGISTRY.get(functional_type, [])


def get_all_functional_types() -> list[str]:
    """获取所有已注册的 functional_type"""
    return list(ACTION_REGISTRY.keys())


def get_action_config(functional_type: str, label: str) -> ActionConfig | None:
    """按 functional_type + label 精确查找动作配置"""
    for action in ACTION_REGISTRY.get(functional_type, []):
        if action.label == label:
            return action
    return None
