"""A3-8 商誉减值测试 + A3-8-1 可收回金额测试 — 专属解析器

合并报表层面商誉减值测试。源模板：
  backend/wp_templates/A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx
  sheet: A3-8商誉减值测试 / A3-8-1可收回金额测试

模板单元格多为 Excel 公式占位（#DIV/0!），实际数据由用户在专属组件中录入。
本解析器输出**结构骨架 + 编制说明静态文本**，供 GtA38GoodwillImpairment.vue 消费。
公式计算在前端 composable 实时完成（不依赖模板公式）。
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "wp_templates" / "A"


def _find_template() -> Path | None:
    """查找 A3-8 模板文件（A3-7/A3-8 合并在同一 xlsx）。"""
    try:
        for f in _TEMPLATE_DIR.iterdir():
            if f.suffix.lower() == ".xlsx" and "A3-8" in f.name:
                return f
    except OSError:
        pass
    return None


# ─── 编制说明（来自模板 A3-8 / A3-8-1 编制说明区，静态只读） ──────────────────

_IMPAIRMENT_REASONS = [
    "被审计单位经营所处的经济、技术或者法律等环境发生重大变化，从而对企业产生不利影响",
    "监管当局采取的不利行动和评价",
    "不可预期的竞争",
    "核心人员流失",
    "被审计单位或其重要组成部分极有可能被变卖或处置",
    "被审计单位重要的资产组已进行了可收回性测试",
    "被审计单位子公司已确认了商誉减值",
    "已被分配商誉的资产组将被处置",
    "其他",
]

_GUIDANCE = {
    "impairment_reasons": _IMPAIRMENT_REASONS,
    "notes": [
        "无论是否存在减值迹象，年末必须对“商誉”进行减值测试。",
        "商誉应当结合与其相关的资产组或者资产组组合进行减值测试；相关资产组不应大于按 CAS 35 分部报告所确定的报告分部。",
        "(A)资产组的账面价值应是其在合并报表层面的账面价值。",
        "总部资产和商誉均不独立产生现金流；先将商誉分摊至相关资产组或资产组组合再测试。",
        "减值损失先全额冲减商誉，剩余按其他各项资产账面价值比例分摊，但不得减记至低于其可收回金额（CAS 8 第二十三条）。",
    ],
    "wacc_params": {
        "Ke": "权益成本 = Rf + β×(Rm-Rf)（CAPM）",
        "WACC": "税后 WACC = E/(D+E)×Ke + D/(D+E)×Kd×(1-税率)",
        "Rf": "无风险报酬率：通常取上市交易政府长期债券（10 年期国债名义利率）到期收益率",
        "Rm": "市场平均收益率：β=1 的市场组合要求收益率，建议用较长跨度几何平均",
        "beta": "β系数：资产组收益率与市场组合的相关性，反映相对市场组合的特定风险",
        "Kd": "税前债务成本：未来增量资金的边际成本，可取企业/可比企业长期债券到期收益率",
        "discount_rate": "折现率口径应与现金流口径一致；现金流为税前则折现率取税前。预测期最多 5 年。",
    },
}

# 减值损失二次分摊默认资产行
_DEFAULT_ALLOCATION_ASSETS = ["流动资产", "固定资产", "无形资产", "商誉"]


def _empty_impairment_row(idx: int) -> dict:
    return {
        "id": f"ag-{idx}",
        "name": "",
        "carrying_a": None,
        "goodwill_b1": None,
        "minority_b2": None,
        "recoverable": None,
        "reason": "",
        "remark": "",
    }


def _empty_allocation_row(idx: int, asset_type: str = "") -> dict:
    return {
        "id": f"al-{idx}",
        "asset_type": asset_type,
        "carrying": None,
        "minority": None,
        "recoverable": None,
    }


def parse_a3_8_goodwill(_template_path: str | None = None) -> dict:
    """解析 A3-8 / A3-8-1 为结构骨架.

    模板数据列均为公式占位，无实际可提取数值；本函数返回：
      - impairmentData：减值主表 1 空行 + 分摊表默认 4 资产行 + 编制说明
      - recoverableData：可收回金额骨架（公允价值 1 行 + DCF 5 年 + WACC 空）

    Args:
        _template_path: 预留参数（当前不读模板数值，仅用于存在性日志）

    Returns:
        {"impairmentData": {...}, "recoverableData": {...}}
    """
    tpl = _find_template()
    if tpl is None:
        logger.warning("A3-8 模板未找到，返回空骨架")

    impairment_data = {
        "impairment_rows": [_empty_impairment_row(1)],
        "allocation_rows": [
            _empty_allocation_row(i + 1, a)
            for i, a in enumerate(_DEFAULT_ALLOCATION_ASSETS)
        ],
        "guidance": _GUIDANCE,
    }

    recoverable_data = {
        "fair_value_rows": [
            {"id": "fv-1", "name": "", "fair_value": None, "disposal_cost": None}
        ],
        "dcf": {
            "cash_flows": [None, None, None, None, None],
            "base_cash_flow": None,
            "perpetual_growth": None,
            "discount_rate": None,
        },
        "wacc": {
            "tax_rate": None,
            "debt_d": None,
            "equity_e": None,
            "cost_debt_kd": None,
            "rf": None,
            "beta": None,
            "rm": None,
        },
    }

    return {"impairmentData": impairment_data, "recoverableData": recoverable_data}
