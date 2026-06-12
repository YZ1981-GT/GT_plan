"""坏账 D2-3 科目编码解析 — 从标准科目表按名称查找，避免硬编码 1231/6701。

多企业/多准则场景下试算表 standard_account_code 仍以解析结果为准；
解析失败时回退到历史默认编码。
"""

from __future__ import annotations

from functools import lru_cache

from app.services.account_chart_service import resolve_standard_account_by_name


@lru_cache(maxsize=1)
def bad_debt_provision_account() -> tuple[str, str]:
    """坏账准备科目 (code, name)。"""
    try:
        return resolve_standard_account_by_name("坏账准备", preferred_codes=("1231",))
    except LookupError:
        return "1231", "坏账准备"


@lru_cache(maxsize=1)
def impairment_loss_account() -> tuple[str, str]:
    """信用/资产减值损失科目 (code, name)。"""
    try:
        return resolve_standard_account_by_name(
            "信用减值损失",
            name_aliases=("资产减值损失",),
            preferred_codes=("6702", "6701"),
        )
    except LookupError:
        return "6701", "信用减值损失"
