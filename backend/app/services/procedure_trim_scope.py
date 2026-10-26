# -*- coding: utf-8 -*-
"""底稿裁剪 — 科目数据可用性（「一键智能裁剪」的数据存在性判据）。

判定逻辑在 :mod:`app.services.trim_subject_scope`（以本项目科目映射后的标准科目为准，
四表单一来源的科目口径，余额 / 期初 / 本期发生 / 客户未映射科目四路判定）；本模块只保留
对外接口 ``GET /api/projects/{pid}/procedure-scope/data-availability`` 的返回结构。

spec: .kiro/specs/procedure-trim-generation-delegation-chain/ 需求 1

🔴 旧实现读 ``account_package_registry.json`` + ``procedure_trim_account_map.json`` 两份静态
码表（H3 写成 1503/1504 等 16 处错码，且只看期末），已整体下线；补充码表文件已删除。
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trim_subject_scope import (
    STATE_NO_DATA,
    STATE_UNKNOWN,
    STATE_WITH_DATA,
    TrialBalanceUnavailable,
    evaluate_subjects,
)

logger = logging.getLogger(__name__)


async def resolve_subject_data_availability(
    db: AsyncSession, project_id: UUID, year: int
) -> dict:
    """返回科目 / 循环数据可用性。

    返回::

        {
          "tb_empty": bool,                 # 试算表完全无非零科目（未导入）→ 调用方不裁
          "subject_with_data": [wp_code],   # 有数据的底稿主码
          "subject_no_data":   [wp_code],   # 确认无数据的底稿主码
          "subject_unknown":   [wp_code],   # 无法判定（调用方退回循环级或保留，不得当无数据）
          "cycles_with_data":  [cycle],     # 有数据的业务循环（兜底粒度）
          "evidence": {wp_code: {...}},     # 命中科目、期初 / 期末 / 借 / 贷合计、来源
        }

    试算表查询失败 → ``tb_empty=True`` + ``error``（调用方据此 fail-safe 不裁）。
    """
    try:
        availability = await evaluate_subjects(db, project_id, year)
    except TrialBalanceUnavailable as e:
        logger.warning(
            "procedure_trim_scope 试算表查询失败 project=%s year=%s: %s", project_id, year, e
        )
        return {
            "tb_empty": True,
            "subject_with_data": [],
            "subject_no_data": [],
            "subject_unknown": [],
            "cycles_with_data": [],
            "evidence": {},
            "error": "试算表查询失败，本次不做自动裁剪",
        }
    return {
        "tb_empty": availability.tb_empty,
        "subject_with_data": availability.codes_in(STATE_WITH_DATA),
        "subject_no_data": availability.codes_in(STATE_NO_DATA),
        "subject_unknown": availability.codes_in(STATE_UNKNOWN),
        "cycles_with_data": availability.cycles_with_data,
        "evidence": {code: ev.as_dict() for code, ev in availability.evidence.items()},
    }


__all__ = ["resolve_subject_data_availability"]
