"""
账龄分析服务 — 支持三年段/五年段/自定义分段

功能：
1. 从精细化规则加载账龄预设（三年段/五年段）
2. 从项目配置加载自定义分段
3. 按账龄分段汇总应收账款余额
4. 计算各段坏账计提金额
5. 账龄迁徙率分析（本期vs上期）
6. 适用于应收账款(1122)/应收票据(1121)/其他应收款(1221)/合同资产(1141)
"""
import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "wp_fine_rules"


def get_aging_presets(wp_code: str = "D2") -> dict:
    """获取账龄预设方案"""
    fp = _DATA_DIR / f"d2_receivable.json"
    if not fp.exists():
        return _default_presets()
    try:
        with open(fp, "r", encoding="utf-8-sig") as f:
            rule = json.load(f)
        return rule.get("aging_presets", _default_presets())
    except Exception:
        return _default_presets()


def _default_presets() -> dict:
    return {
        "three_year": {
            "name": "三年段",
            "segments": [
                {"key": "within_1y", "label": "1年以内", "min_days": 0, "max_days": 365, "default_rate": 0.05},
                {"key": "1_to_2y", "label": "1-2年", "min_days": 366, "max_days": 730, "default_rate": 0.10},
                {"key": "2_to_3y", "label": "2-3年", "min_days": 731, "max_days": 1095, "default_rate": 0.30},
                {"key": "over_3y", "label": "3年以上", "min_days": 1096, "max_days": None, "default_rate": 1.00},
            ],
        },
        "five_year": {
            "name": "五年段",
            "segments": [
                {"key": "within_1y", "label": "1年以内", "min_days": 0, "max_days": 365, "default_rate": 0.05},
                {"key": "1_to_2y", "label": "1-2年", "min_days": 366, "max_days": 730, "default_rate": 0.10},
                {"key": "2_to_3y", "label": "2-3年", "min_days": 731, "max_days": 1095, "default_rate": 0.20},
                {"key": "3_to_4y", "label": "3-4年", "min_days": 1096, "max_days": 1460, "default_rate": 0.50},
                {"key": "4_to_5y", "label": "4-5年", "min_days": 1461, "max_days": 1825, "default_rate": 0.80},
                {"key": "over_5y", "label": "5年以上", "min_days": 1826, "max_days": None, "default_rate": 1.00},
            ],
        },
    }


async def get_project_aging_config(
    db: AsyncSession, project_id: UUID
) -> dict:
    """获取项目的账龄配置（预设类型+自定义分段+计提比例）"""
    from app.models.core import Project
    result = await db.execute(sa.select(Project.wizard_state).where(Project.id == project_id))
    ws = result.scalar_one_or_none()
    if not ws or not isinstance(ws, dict):
        return {"preset": "three_year", "custom_segments": [], "custom_rates": {}}

    aging_cfg = ws.get("aging_config", {})
    return {
        "preset": aging_cfg.get("preset", "three_year"),
        "custom_segments": aging_cfg.get("custom_segments", []),
        "custom_rates": aging_cfg.get("custom_rates", {}),
    }


def get_effective_segments(
    preset_key: str,
    custom_segments: list[dict] | None = None,
    custom_rates: dict | None = None,
) -> list[dict]:
    """获取生效的账龄分段（预设+自定义覆盖）

    优先级：自定义分段 > 预设分段
    自定义计提比例覆盖预设默认比例
    """
    if preset_key == "custom" and custom_segments:
        return custom_segments

    presets = get_aging_presets()
    preset = presets.get(preset_key, presets.get("three_year", {}))
    segments = preset.get("segments", [])

    # 自定义计提比例覆盖
    if custom_rates:
        for seg in segments:
            if seg["key"] in custom_rates:
                seg["default_rate"] = custom_rates[seg["key"]]

    return segments


async def calculate_aging_provision(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_code: str = "1122",
    preset_key: str = "three_year",
    custom_segments: list[dict] | None = None,
    custom_rates: dict | None = None,
) -> dict:
    """计算账龄坏账计提

    返回：
    {
        "preset": "three_year",
        "segments": [
            {"key": "within_1y", "label": "1年以内", "balance": 1000000, "rate": 0.05, "provision": 50000},
            ...
        ],
        "total_balance": 5000000,
        "total_provision": 250000,
        "provision_rate": 0.05,
    }
    """
    segments = get_effective_segments(preset_key, custom_segments, custom_rates)

    # 从辅助余额表按账龄维度汇总
    # 实际数据需要从tb_aux_balance按aux_type='账龄'分组
    from app.models.audit_platform_models import TbAuxBalance
    try:
        result = await db.execute(
            sa.select(
                TbAuxBalance.aux_name,
                sa.func.sum(TbAuxBalance.closing_balance).label("balance"),
            ).where(
                TbAuxBalance.project_id == project_id,
                TbAuxBalance.year == year,
                TbAuxBalance.account_code.startswith(account_code[:4]),
                TbAuxBalance.is_deleted == sa.false(),
            ).group_by(TbAuxBalance.aux_name)
        )
        aging_data = {row[0]: float(row[1] or 0) for row in result.all()}
    except Exception:
        aging_data = {}

    # 按分段匹配
    seg_results = []
    total_balance = 0
    total_provision = 0

    for seg in segments:
        label = seg["label"]
        rate = seg.get("default_rate", 0)
        # 从aging_data中匹配（按标签关键词）
        balance = 0
        for aging_label, amt in aging_data.items():
            if aging_label and _match_aging_label(aging_label, seg):
                balance += amt

        provision = round(balance * rate, 2)
        total_balance += balance
        total_provision += provision

        seg_results.append({
            "key": seg["key"],
            "label": label,
            "balance": balance,
            "rate": rate,
            "provision": provision,
        })

    return {
        "preset": preset_key,
        "account_code": account_code,
        "segments": seg_results,
        "total_balance": total_balance,
        "total_provision": total_provision,
        "provision_rate": round(total_provision / max(total_balance, 1), 4),
    }


def _match_aging_label(data_label: str, segment: dict) -> bool:
    """匹配辅助余额的账龄标签到分段"""
    label = segment["label"]
    key = segment["key"]

    # 精确匹配
    if label in data_label or data_label in label:
        return True

    # 关键词匹配
    kw_map = {
        "within_1y": ["1年以内", "一年以内", "0-1年"],
        "1_to_2y": ["1-2年", "一至二年", "1至2年"],
        "2_to_3y": ["2-3年", "二至三年", "2至3年"],
        "3_to_4y": ["3-4年", "三至四年", "3至4年"],
        "4_to_5y": ["4-5年", "四至五年", "4至5年"],
        "over_3y": ["3年以上", "三年以上"],
        "over_5y": ["5年以上", "五年以上"],
        "within_3m": ["3个月以内", "三个月以内"],
        "3m_to_6m": ["3-6个月", "三至六个月"],
        "6m_to_1y": ["6个月至1年", "六个月至一年", "6-12个月"],
        "within_6m": ["6个月以内", "六个月以内"],
    }
    for kw in kw_map.get(key, []):
        if kw in data_label:
            return True
    return False


# ═══════════════════════════════════════════
# 存货库龄分析（扩展）
# ═══════════════════════════════════════════

INVENTORY_AGING_PRESETS = {
    "three_year": {
        "name": "三年段",
        "segments": [
            {"key": "within_1y", "label": "1年以内", "min_days": 0, "max_days": 365, "default_rate": 0},
            {"key": "1_to_2y", "label": "1-2年", "min_days": 366, "max_days": 730, "default_rate": 0.10},
            {"key": "2_to_3y", "label": "2-3年", "min_days": 731, "max_days": 1095, "default_rate": 0.30},
            {"key": "over_3y", "label": "3年以上", "min_days": 1096, "max_days": None, "default_rate": 0.50},
        ],
    },
    "five_year": {
        "name": "五年段",
        "segments": [
            {"key": "within_1y", "label": "1年以内", "min_days": 0, "max_days": 365, "default_rate": 0},
            {"key": "1_to_2y", "label": "1-2年", "min_days": 366, "max_days": 730, "default_rate": 0.10},
            {"key": "2_to_3y", "label": "2-3年", "min_days": 731, "max_days": 1095, "default_rate": 0.20},
            {"key": "3_to_4y", "label": "3-4年", "min_days": 1096, "max_days": 1460, "default_rate": 0.40},
            {"key": "4_to_5y", "label": "4-5年", "min_days": 1461, "max_days": 1825, "default_rate": 0.60},
            {"key": "over_5y", "label": "5年以上", "min_days": 1826, "max_days": None, "default_rate": 1.00},
        ],
    },
}


def get_inventory_aging_presets() -> dict:
    """获取存货库龄预设方案"""
    return INVENTORY_AGING_PRESETS


async def calculate_inventory_aging(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    preset_key: str = "three_year",
    custom_rates: dict | None = None,
) -> dict:
    """计算存货库龄跌价准备

    存货跌价准备与应收坏账的区别：
    - 应收账款按账龄+迁徙率计提
    - 存货按可变现净值vs账面价值计提（库龄只是辅助参考）
    - 库龄超长的存货更可能需要计提跌价
    """
    presets = INVENTORY_AGING_PRESETS.get(preset_key, INVENTORY_AGING_PRESETS["three_year"])
    segments = presets.get("segments", [])

    if custom_rates:
        for seg in segments:
            if seg["key"] in custom_rates:
                seg["default_rate"] = custom_rates[seg["key"]]

    # 从辅助余额表按库龄维度汇总
    from app.models.audit_platform_models import TbAuxBalance
    try:
        result = await db.execute(
            sa.select(
                TbAuxBalance.aux_name,
                sa.func.sum(TbAuxBalance.closing_balance).label("balance"),
            ).where(
                TbAuxBalance.project_id == project_id,
                TbAuxBalance.year == year,
                TbAuxBalance.account_code.startswith("140"),
                TbAuxBalance.is_deleted == sa.false(),
            ).group_by(TbAuxBalance.aux_name)
        )
        aging_data = {row[0]: float(row[1] or 0) for row in result.all()}
    except Exception:
        aging_data = {}

    seg_results = []
    total_balance = 0
    total_provision = 0

    for seg in segments:
        balance = 0
        for label, amt in aging_data.items():
            if label and _match_aging_label(label, seg):
                balance += amt
        provision = round(balance * seg.get("default_rate", 0), 2)
        total_balance += balance
        total_provision += provision
        seg_results.append({
            "key": seg["key"], "label": seg["label"],
            "balance": balance, "rate": seg.get("default_rate", 0), "provision": provision,
        })

    return {
        "type": "inventory",
        "preset": preset_key,
        "segments": seg_results,
        "total_balance": total_balance,
        "total_provision": total_provision,
        "provision_rate": round(total_provision / max(total_balance, 1), 4),
        "note": "存货跌价准备应以可变现净值测试为准，库龄分析仅作辅助参考",
    }
