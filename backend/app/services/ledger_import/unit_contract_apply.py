"""账套导入：由作业合同构造 staged 单位归一合同，并在写入前换算金额。

spec `platform-global-display-settings-closure` 任务 8 / R8 / AC-14~AC-17。

## 为什么单独成模块

`pipeline.py`（923 行）已在行数门白名单里、只剩约 5% 余量。按项目纪律
**「超限优先抽模块不抬白名单」**，把「构造合同 + 换算金额」这两块从 pipeline
抽出，pipeline 只保留两处一行调用。

## 三条纪律（每条都对应一次真实风险）

1. **摘要口径必须与 detect 端点逐值相同** —— 优先读 detect 缓存在 bundle
   manifest 里的 `unit_detection`；缓存缺失（旧 bundle / 测试直调）时按同一
   builder 现算（逐 file/sheet 的 `amount_unit` + bundle 逐文件 sha256/size）。
   两边口径不同会让 `UNIT_DETECTION_CHANGED` 在真实导入时必现。
2. **合同构造 fail closed** —— 确认 digest 与摘要不一致、确认人与作业创建人
   不一致、unsupported、缺 `created_by` 一律抛，**不静默降级为「按元处理」**
   （那会把万元数据当成元存进库，是最危险的一类静默错数）。
3. **金额只换算一次** —— 换算发生在 converter 之后、写入 staged 之前；金额字段
   清单复用 `ledger_unit_inspector.AMOUNT_FIELDS`（与只读巡检同一来源），
   换算内核复用 `ledger_amount_kernel.convert_amount`（Decimal + ROUND_HALF_UP
   到 0.01，None 原样保留，NaN/Inf 与非数字 fail closed）。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

__all__ = [
    "build_staged_unit_contract",
    "normalize_row_amounts",
    "unit_normalization_payload",
]


def build_staged_unit_contract(
    *,
    detections: dict[str, Any],
    file_sources: list[tuple[str, Any]],
    unit_confirmation: dict[str, Any] | None,
    created_by: UUID | None,
    job_id: UUID | None = None,
):
    """由 `ImportJob.options["unit_confirmation"]` 构造不可变单位合同。

    Parameters
    ----------
    detections:
        pipeline 的 `{path: FileDetection}`（detect + identify 之后）。
    file_sources:
        `[(filename, Path)]`，用于定位 bundle 目录读 manifest 缓存与文件 hash。
    unit_confirmation:
        `ImportJob.options` 里持久化的确认合同 wire dict。`None` = 旧作业 /
        测试直调 ⇒ **返回 None，不构造、不换算**（既有行为逐字节不变）。
    created_by:
        作业创建人（= 确认人）。给出合同时为 `None` ⇒ 抛（无法验证确认人）。

    Raises
    ------
    RuntimeError
        `UnitContractError` 的 `code` + 原因（确认摘要漂移 / 确认人缺失 /
        unsupported / 合同字段非法）。**不返回 None 表示失败。**
    """
    if unit_confirmation is None:
        return None

    from app.schemas.ledger_unit_contract import UnitConfirmationInput
    from app.services.ledger_import.unit_normalization import (
        UnitContractError,
        build_confirmed_unit_contract,
    )

    if created_by is None:
        raise RuntimeError(
            "UNIT_CONTRACT_INVALID: 作业缺少创建人，无法校验单位确认人"
        )

    try:
        confirmation = UnitConfirmationInput.model_validate(unit_confirmation)
    except Exception as exc:  # noqa: BLE001 - pydantic 异常类型很多，统一转换
        raise RuntimeError(
            f"UNIT_CONTRACT_INVALID: 单位确认合同无法解析：{exc}"
        ) from exc

    detection = _resolve_detection_summary(
        detections=detections, file_sources=file_sources, job_id=job_id,
    )
    try:
        contract = build_confirmed_unit_contract(
            detection=detection,
            confirmation=confirmation,
            confirmed_by=created_by,
            job_created_by=created_by,
        )
    except UnitContractError as exc:
        raise RuntimeError(f"{exc.code}: {exc}") from exc

    logger.info(
        "Pipeline %s unit contract built: source=%s factor=%s digest=%s",
        job_id, contract.source_unit, contract.factor, contract.contract_digest[:12],
    )
    return contract


def _resolve_detection_summary(
    *,
    detections: dict[str, Any],
    file_sources: list[tuple[str, Any]],
    job_id: UUID | None,
):
    """按 detect 端点的同一口径解析 `UnitDetectionSummary`。

    优先级：manifest 缓存（detect 阶段写入，逐字段与预览相同）→ 现算。
    """
    from app.schemas.ledger_unit_contract import UnitDetectionSummary
    from app.services.ledger_import.unit_detection_wire import (
        read_cached_unit_detection,
    )
    from app.services.ledger_import.unit_normalization import summarize_detected_units

    bundle_dir = _bundle_dir_of(file_sources)
    if bundle_dir is not None:
        cached = read_cached_unit_detection(bundle_dir)
        if cached is not None:
            try:
                return UnitDetectionSummary.model_validate(cached)
            except Exception as exc:  # noqa: BLE001 - 缓存损坏 ⇒ 现算
                logger.warning(
                    "Pipeline %s 缓存的 unit_detection 无法解析（改按现算）：%s",
                    job_id, exc,
                )

    sheets: list[tuple[str, str, str | None]] = []
    for file_detection in detections.values():
        file_name = getattr(file_detection, "file_name", "") or ""
        for sheet in getattr(file_detection, "sheets", None) or []:
            evidence = getattr(sheet, "detection_evidence", None) or {}
            raw_unit = evidence.get("amount_unit")
            sheets.append(
                (
                    file_name,
                    getattr(sheet, "sheet_name", "") or "",
                    str(raw_unit) if raw_unit else None,
                )
            )

    file_hashes = None
    if bundle_dir is not None:
        try:
            from app.services.ledger_import_upload_service import (
                LedgerImportUploadService,
            )

            file_hashes, _manifest = (
                LedgerImportUploadService.load_bundle_unit_evidence_from_path(bundle_dir)
            )
        except Exception as exc:  # noqa: BLE001 - 证据缺失不阻断检测（与 detect 同口径）
            logger.warning(
                "Pipeline %s bundle 单位证据读取失败（摘要按无 hash 口径）：%s",
                job_id, exc,
            )
            file_hashes = None

    return summarize_detected_units(sheets=sheets, file_hashes=file_hashes).summary


def _bundle_dir_of(file_sources: list[tuple[str, Any]]) -> Path | None:
    """从 `[(filename, Path)]` 推断 bundle 目录（含 manifest.json 的那一层）。"""
    for _name, source in file_sources or []:
        try:
            candidate = Path(str(source)).parent
        except Exception:  # noqa: BLE001 - 非路径型 source 直接跳过
            continue
        if (candidate / "manifest.json").exists():
            return candidate
    return None


def unit_normalization_payload(contract) -> dict[str, Any]:
    """合同 → `source_summary["unit_normalization"]` 的持久化形状。

    `contract` 的 JSON 形态即 `normalized_v1` 的完整证据：
    `classify_dataset_unit` 只看 `contract.contract_digest`（64 位小写 hex），
    `base_token_resolver` 读同一字段，前端 `useDatasetUnitPresentation` 读
    `contract.factor`。三者同一来源，不允许各自再拼一份。
    """
    return {
        "version": "normalized_v1",
        "contract": contract.model_dump(mode="json"),
    }


def normalize_row_amounts(
    rows: list[dict[str, Any]],
    *,
    table_name: str,
    factor: Decimal,
    job_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """按 `factor` 换算一条写入批次里的金额列（**只换算一次**）。

    - `factor == 1`（来源即元）⇒ **原样返回同一个 list**（不复制、不量化）；
    - 只换算 `AMOUNT_FIELDS[table_name]` 里的列（与只读巡检同一清单）；
    - `None` / 空串原样保留（缺数 ≠ 零）；
    - 非法非空值 / NaN / ±Infinity / 溢出 ⇒ 抛（不写 0 冒充有数据）。
    """
    if factor == 1 or not rows:
        return rows

    from app.services.ledger_amount_kernel import LedgerAmountError, convert_amount
    from app.services.ledger_unit_inspector import AMOUNT_FIELDS

    fields = AMOUNT_FIELDS.get(table_name)
    if not fields:
        return rows

    converted: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        new_row = dict(row)
        for field in fields:
            if field not in new_row:
                continue
            try:
                new_row[field] = convert_amount(
                    new_row[field],
                    factor,
                    file=str(row.get("source_file") or ""),
                    sheet=str(row.get("source_sheet") or ""),
                    row=index,
                    field=field,
                )
            except LedgerAmountError as exc:
                raise RuntimeError(
                    f"{exc.code}: {table_name} 第 {index} 行 {field} 无法按单位换算"
                    f"（source_unit factor={factor}, job={job_id}）"
                ) from exc
        converted.append(new_row)
    return converted
