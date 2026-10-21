"""通用标准两字段 builder 工厂。

大多数科目的附注主表只需 end_amount / prior_amount 两个字段，
数据来自 checklist_responses 的 `{WP_CODE}-adj-tb-amount`（期末）
和 `{WP_CODE}-1-audited-net` 或 `{WP_CODE}-1-tb-amount` 等审定数键。

本模块提供工厂函数 `make_standard_builder()`，按 wp_code + section 映射 +
审定数 item_id 键批量注册 builder，无需逐个写文件。

spec: backend-disclosure-payload-builder Phase 3~4
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.disclosure_payload_builder_service import (
    DisclosurePayloadBuilder,
    PayloadBuildResult,
    load_disclosure_entries,
    load_project_standard,
    load_project_template_type,
    register_builder,
)

logger = logging.getLogger(__name__)

_STANDARD_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "期初余额", "format": "amount"},
]


def _num(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except (ValueError, AttributeError):
            pass
    return 0.0


def make_standard_builder(
    wp_code: str,
    *,
    section: dict[str, str],          # {"listed": "五、xx", "soe": "八、xx"}
    main_table: str,                   # 主表名（附注模板的 section_title）
    end_keys: list[str] | None = None, # 期末审定数的 item_id 键（多个则取首个非零）
    prior_keys: list[str] | None = None,
    sheet_name: dict[str, str] | None = None,
) -> type[DisclosurePayloadBuilder]:
    """创建并注册一个标准两字段 builder。"""

    # 默认 item_id 键：{CODE}-adj-tb-amount / {CODE}-1-tb-amount / {CODE}-1-audited-net
    if end_keys is None:
        code = wp_code
        end_keys = [
            f"{code}-adj-tb-amount",
            f"{code}-1-tb-amount",
            f"{code}-1-audited-net",
        ]
    if prior_keys is None:
        prior_keys = []

    if sheet_name is None:
        sheet_name = {
            "listed": "附注披露信息(上市公司)",
            "soe": "附注披露信息(国企)",
        }

    class _Builder(DisclosurePayloadBuilder):
        wp_code_attr = wp_code

        async def build(self, db: AsyncSession, project_id: UUID, year: int) -> PayloadBuildResult | None:
            entries = await load_disclosure_entries(db, project_id, wp_code)
            if not entries:
                return None

            template_type = await load_project_template_type(db, project_id)
            variant = "soe" if "soe" in template_type.lower() else "listed"
            current_standard = await load_project_standard(db, project_id)

            sec = section.get(variant)
            if not sec:
                return None

            # 取期末审定数：依次尝试多个键，取首个非零
            end_val = 0.0
            for k in end_keys:
                v = _num(entries.get(k))
                if v != 0.0:
                    end_val = v
                    break

            prior_val = 0.0
            for k in prior_keys:
                v = _num(entries.get(k))
                if v != 0.0:
                    prior_val = v
                    break

            rows: list[dict[str, Any]] = [
                {"label": main_table, "end_amount": end_val, "prior_amount": prior_val},
                {"label": "合计", "end_amount": end_val, "prior_amount": prior_val, "is_total": True},
            ]

            return PayloadBuildResult(
                wp_code=wp_code,
                section_id=sec,
                sub_table_data={main_table: rows},
                sub_table_columns={main_table: _STANDARD_COLUMNS[:]},
                sheet_name=sheet_name.get(variant, sheet_name.get("soe", "")),
                current_standard=current_standard,
            )

    _Builder.__name__ = f"{wp_code}Builder"
    _Builder.__qualname__ = f"{wp_code}Builder"
    _Builder.wp_code = wp_code
    register_builder(_Builder)
    return _Builder


# ── 批量注册 Phase 3 + Phase 4 全部标准科目 ──────────────────────────────────

# 格式：(wp_code, section, main_table)
# section 取自 note_workpaper_sync_registry.json
# main_table 取自附注模板的 section_title

_STANDARD_SPECS: list[tuple[str, dict[str, str], str]] = [
    # Phase 3：D3~D7
    ("D3", {"listed": "五、38", "soe": "八、38"}, "预收款项"),
    ("D4", {"listed": "五、62", "soe": "八、64"}, "营业收入和营业成本"),
    ("D5", {"listed": "五、6", "soe": "八、6"}, "应收款项融资"),
    ("D6", {"listed": "五、10", "soe": "八、11"}, "合同资产"),
    ("D7", {"listed": "五、39", "soe": "八、39"}, "合同负债"),
    # Phase 3：F1 F3~F4
    ("F1", {"listed": "五、7", "soe": "八、7"}, "预付款项"),
    ("F3", {"listed": "五、36", "soe": "八、36"}, "应付票据"),
    ("F4", {"listed": "五、37", "soe": "八、37"}, "应付账款"),
    # Phase 3：H2~H5 + H6~H10
    ("H2", {"listed": "五、23", "soe": "八、23"}, "在建工程"),
    ("H3", {"listed": "五、21", "soe": "八、21"}, "投资性房地产"),
    ("H4", {"listed": "五、23", "soe": "八、23"}, "工程物资"),
    ("H5", {"listed": "", "soe": "八、25"}, "油气资产"),
    ("H6", {"listed": "五、22", "soe": "八、22"}, "固定资产清理"),
    ("H7", {"listed": "五、24", "soe": "八、24"}, "生产性生物资产"),
    ("H8", {"listed": "五、25", "soe": "八、26"}, "使用权资产"),
    ("H9", {"listed": "五、47", "soe": "八、52"}, "租赁负债"),
    ("H10", {"listed": "五、78", "soe": "八、75"}, "资产处置收益"),
    # Phase 3：I2~I6
    ("I2", {"listed": "五、27", "soe": "八、28"}, "开发支出"),
    ("I3", {"listed": "五、28", "soe": "八、29"}, "商誉"),
    ("I4", {"listed": "五、29", "soe": "八、30"}, "长期待摊费用"),
    ("I5", {"listed": "五、31", "soe": "八、32"}, "其他非流动资产"),
    ("I6", {"listed": "五、66", "soe": "八、67"}, "研发费用"),
    # Phase 4：G 循环
    ("G1", {"listed": "五、2", "soe": "八、2"}, "交易性金融资产"),
    ("G2", {"listed": "五、8", "soe": "八、9"}, "应收利息"),
    ("G3", {"listed": "五、8", "soe": "八、9"}, "应收股利"),
    ("G4", {"listed": "五、14", "soe": "八、15"}, "债权投资"),
    ("G5", {"listed": "五、16", "soe": "八、17"}, "长期应收款"),
    ("G6", {"listed": "五、15", "soe": "八、16"}, "其他债权投资"),
    ("G8", {"listed": "五、19", "soe": "八、19"}, "其他权益工具投资"),
    ("G9", {"listed": "五、20", "soe": "八、20"}, "其他非流动金融资产"),
    ("G10", {"listed": "五、34", "soe": "八、34"}, "交易性金融负债"),
    ("G11", {"listed": "五、69", "soe": "八、70"}, "投资收益"),
    ("G12", {"listed": "五、70", "soe": "八、71"}, "净敞口套期收益"),
    ("G13", {"listed": "五、75", "soe": "八、72"}, "公允价值变动收益"),
    ("G14", {"listed": "五、76", "soe": "八、73"}, "信用减值损失"),
    # Phase 4：J 循环
    ("J1", {"listed": "五、40", "soe": "八、40"}, "应付职工薪酬"),
    ("J2", {"listed": "五、49", "soe": "八、54"}, "长期应付职工薪酬"),
    # Phase 4：K 循环（K1 已单独实现）
    ("K2", {"listed": "五、13", "soe": "八、14"}, "其他流动资产"),
    ("K3", {"listed": "五、42", "soe": "八、42"}, "其他应付款"),
    ("K4", {"listed": "五、44", "soe": "八、48"}, "其他流动负债"),
    ("K5", {"listed": "五、50", "soe": "八、55"}, "预计负债"),
    ("K6", {"listed": "五、11", "soe": "八、12"}, "持有待售资产和持有待售负债"),
    ("K7", {"listed": "五、51", "soe": "八、56"}, "递延收益"),
    ("K8", {"listed": "五、64", "soe": "八、65"}, "销售费用"),
    ("K9", {"listed": "五、65", "soe": "八、66"}, "管理费用"),
    ("K10", {"listed": "五、68", "soe": "八、69"}, "其他收益"),
    ("K11", {"listed": "五、77", "soe": "八、74"}, "资产减值损失"),
    ("K12", {"listed": "五、79", "soe": "八、76"}, "营业外收入"),
    ("K13", {"listed": "五、80", "soe": "八、77"}, "营业外支出"),
    # Phase 4：L 循环
    ("L1", {"listed": "五、33", "soe": "八、33"}, "短期借款"),
    ("L2", {"listed": "五、42", "soe": "八、42"}, "应付利息"),
    ("L3", {"listed": "五、45", "soe": "八、49"}, "长期借款"),
    ("L4", {"listed": "五、46", "soe": "八、50"}, "应付债券"),
    ("L5", {"listed": "五、48", "soe": "八、53"}, "长期应付款"),
    ("L7", {"listed": "五、52", "soe": "八、57"}, "其他非流动负债"),
    ("L8", {"listed": "五、67", "soe": "八、68"}, "财务费用"),
    # Phase 4：M 循环
    ("M1", {"listed": "五、42", "soe": "八、42"}, "应付股利"),
    ("M2", {"listed": "五、53", "soe": "八、58"}, "实收资本"),
    ("M3", {"listed": "五、56", "soe": ""}, "库存股"),
    ("M4", {"listed": "五、55", "soe": "八、60"}, "资本公积"),
    ("M5", {"listed": "五、59", "soe": "八、62"}, "盈余公积"),
    ("M6", {"listed": "五、61", "soe": "八、63"}, "未分配利润"),
    ("M7", {"listed": "五、58", "soe": "八、61"}, "专项储备"),
    ("M8", {"listed": "五、60", "soe": "八、94"}, "其他综合收益"),
    ("M9", {"listed": "五、57", "soe": "八、79"}, "其他综合收益明细"),
    ("M10", {"listed": "五、54", "soe": "八、59"}, "其他权益工具"),
    # Phase 4：N 循环
    ("N1", {"listed": "五、30", "soe": "八、31"}, "递延所得税资产"),
    ("N2", {"listed": "五、41", "soe": "八、41"}, "应交税费"),
    ("N4", {"listed": "五、63", "soe": ""}, "所得税费用"),
    ("N5", {"listed": "五、81", "soe": "八、78"}, "外币货币性项目"),
]

for _code, _section, _table in _STANDARD_SPECS:
    # 跳过 section 全空的（如 H5 listed=None）
    _clean = {k: v for k, v in _section.items() if v}
    if _clean:
        make_standard_builder(_code, section=_clean, main_table=_table)
