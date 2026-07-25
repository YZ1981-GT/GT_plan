# -*- coding: utf-8 -*-
"""底稿裁剪 — 科目数据可用性判断（供"智能裁剪"精确到科目底稿级）。

依据两级判据判断某底稿程序对应的科目在本项目本年度是否有数据：

1. 科目底稿级（精确）：`account_package_registry.json` 的
   ``primary_wp_code -> account_code`` 映射（如 D2->1122、E1->1001/1002/1012），
   与试算表非零余额（审定优先、否则未审）比对。覆盖 registry 已登记的科目工作包
   （D 循环最全 + G/E1/F1-5 等）。

2. 业务循环级（兜底）：对 registry 未覆盖的底稿，退回按业务循环是否有数据判断
   （复用 `cycle_for_account` 启发式），保证 H/I/J/K/L/M/N 等未登记科目也能被
   合理裁剪，而非一律保留。

设计原则：宁松勿紧——无法判定时倾向"有数据/保留"，避免误裁；试算表未导入
（完全无非零科目）时由调用方 fail-safe 不裁。
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.b50_risk_reader import cycle_for_account

logger = logging.getLogger(__name__)

_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "account_package_registry.json"
)
# 裁剪专用补充映射（registry 未覆盖的 H/I/J/K/L/M/N 科目底稿）。
# 隔离于 registry，避免触发 resolve_package_sheets 聚合渲染 / 破坏契约测试。
_SUPPLEMENT_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "procedure_trim_account_map.json"
)

# 科目余额驱动的实质性循环（B/C 计划/控制类、A/S 非科目余额驱动，不参与）
_DATA_DRIVEN_CYCLES = set("DEFGHIJKLMN")


@lru_cache(maxsize=1)
def _load_wp_account_map() -> dict[str, list[str]]:
    """构建 ``{primary_wp_code: [数字科目码, ...]}``。

    - 仅保留 cycle ∈ D~N 的科目工作包（排除 B/C 控制测试的伪科目码如 "C2"）
    - account_code 支持逗号分隔多码（如 E1="1001,1002,1012"）
    - 仅保留纯数字科目码（排除 "C2"/"C3" 等非科目编码）
    """
    result: dict[str, list[str]] = {}

    # 1) 主源：account_package_registry（D1-D7/E1/F1-F5/G1-G14/H10/K0/L0 等）
    try:
        raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        for pkg in raw.get("packages", []):
            cyc = (pkg.get("cycle") or "").strip().upper()
            if cyc not in _DATA_DRIVEN_CYCLES:
                continue
            wp = (pkg.get("primary_wp_code") or "").strip().upper()
            codes_raw = pkg.get("account_code")
            if not wp or not codes_raw:
                continue
            codes = [c.strip() for c in str(codes_raw).split(",") if c.strip().isdigit()]
            if codes:
                result[wp] = codes
    except Exception as e:  # noqa: BLE001
        logger.warning("account_package_registry 读取失败: %s", e)

    # 2) 补充源：裁剪专用映射（registry 未覆盖的 H/I/J/K/L/M/N；registry 已有则不覆盖）
    try:
        supp = json.loads(_SUPPLEMENT_PATH.read_text(encoding="utf-8")).get("map", {})
        for wp_raw, codes_raw in supp.items():
            if not isinstance(codes_raw, list):
                continue
            wp = str(wp_raw).strip().upper()
            if not wp or wp[:1] not in _DATA_DRIVEN_CYCLES:
                continue
            codes = [str(c).strip() for c in codes_raw if str(c).strip().isdigit()]
            if codes:
                result.setdefault(wp, codes)  # registry 优先，不覆盖
    except Exception as e:  # noqa: BLE001
        logger.warning("procedure_trim_account_map 读取失败: %s", e)

    return result


async def _load_account_mapping(db: AsyncSession, project_id: UUID) -> dict[str, str]:
    """加载该项目的科目规则映射 ``{original_account_code: standard_account_code}``。

    企业科目编码因企业而异，此映射（项目向导 account_mapping 步骤建立）把企业原始码
    归一到统一标准码。用于对未标准化的 trial_balance 兜底归一。查询失败/无数据返回空 dict
    （不影响主判据——trial_balance 多数已存标准码，映射为空时判断退化为直接标准码匹配）。
    """
    try:
        result = await db.execute(
            sa.text(
                "SELECT original_account_code, standard_account_code "
                "FROM account_mapping "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(project_id)},
        )
        mapping: dict[str, str] = {}
        for row in result.fetchall():
            orig = (row.original_account_code or "").strip()
            std = (row.standard_account_code or "").strip()
            if orig and std and orig != std:
                mapping[orig] = std
        return mapping
    except Exception as e:  # noqa: BLE001
        logger.warning("account_mapping 读取失败 project=%s: %s", project_id, e)
        return {}


def _package_has_data(codes: list[str], nonzero_codes: set[str]) -> bool:
    """科目工作包的任一标准科目码（4 位一级码）在试算表有非零数据。

    前缀匹配：registry 记母科目码（如 1122），试算表可能是母码或子科目码
    （1122 / 1122.01 / 112201），均视为该科目有数据。
    """
    for rc in codes:
        for tbc in nonzero_codes:
            if tbc == rc or tbc.startswith(rc):
                return True
    return False


async def resolve_subject_data_availability(
    db: AsyncSession, project_id: UUID, year: int
) -> dict:
    """返回科目/循环数据可用性。

    返回::

        {
          "tb_empty": bool,                 # 试算表完全无非零科目（未导入）
          "subject_with_data": [wp_code],   # registry 覆盖且有数据的科目底稿前缀
          "subject_no_data":   [wp_code],   # registry 覆盖但无数据的科目底稿前缀
          "cycles_with_data":  [cycle],     # 有数据的业务循环（兜底粒度）
        }
    """
    wp_map = _load_wp_account_map()

    try:
        from app.models.audit_platform_models import TrialBalance
        from app.services.dataset_query import get_active_filter

        tb = TrialBalance.__table__
        active = await get_active_filter(db, tb, project_id, year)
        stmt = sa.select(
            tb.c.account_name,
            tb.c.standard_account_code,
            tb.c.unadjusted_amount,
            tb.c.audited_amount,
        ).where(active)
        rows = (await db.execute(stmt)).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "procedure_trim_scope 试算表查询失败 project=%s year=%s: %s",
            project_id, year, e,
        )
        # 查询失败：返回 tb_empty=True 让调用方 fail-safe 不裁
        return {
            "tb_empty": True,
            "subject_with_data": [],
            "subject_no_data": [],
            "cycles_with_data": [],
        }

    # 科目规则映射（该项目"最开始"建立的 original_account_code -> standard_account_code）。
    # 企业科目编码因企业而异，靠此映射归一到统一标准码：即便某项目 trial_balance 存的是
    # 企业原始码（未标准化），也能经映射补出标准码正确判断，不依赖硬编码假设。
    orig_to_std = await _load_account_mapping(db, project_id)

    nonzero_codes: set[str] = set()
    cycles_with_data: set[str] = set()
    for r in rows:
        amt = r.audited_amount if r.audited_amount is not None else r.unadjusted_amount
        try:
            amt = float(amt or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if abs(amt) < 1e-6:
            continue
        code = (r.standard_account_code or "").strip()
        if code:
            nonzero_codes.add(code)
            # 若 trial_balance 存的是企业原始码，经科目规则映射补出标准码
            mapped = orig_to_std.get(code)
            if mapped:
                nonzero_codes.add(mapped)
        cyc = cycle_for_account((r.account_name or "").strip(), code)
        if cyc in _DATA_DRIVEN_CYCLES:
            cycles_with_data.add(cyc)

    tb_empty = not nonzero_codes and not cycles_with_data

    subject_with_data: list[str] = []
    subject_no_data: list[str] = []
    for wp, codes in wp_map.items():
        if _package_has_data(codes, nonzero_codes):
            subject_with_data.append(wp)
        else:
            subject_no_data.append(wp)

    return {
        "tb_empty": tb_empty,
        "subject_with_data": sorted(subject_with_data),
        "subject_no_data": sorted(subject_no_data),
        "cycles_with_data": sorted(cycles_with_data),
    }
