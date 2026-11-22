"""
preview / detect 的 `unit_detection` 接线（从 router 与 application_service 抽出）。

## 为什么单独成文件

`ledger_import_v2.py`（859 行）与 `ledger_import_application_service.py`（970 行）
都已在文件行数门的白名单里，加接线后会超出「基线 +5%」上限。按项目纪律
**「超限优先抽模块不抬白名单」**，把这段接线抽出来：

- `detection_diagnostics(result)` —— 把 `LedgerDetectionResult` 摊平成
  preview 诊断项形状（`file` / `sheet` / `amount_unit`）；
- `build_unit_detection_payload(diagnostics, project_id, upload_token)` ——
  由诊断项生成 **同一份** `UnitDetectionSummary` wire dict。

三条正式 preview/detect（`/account-chart/preview`、`/ledger/smart-preview`、
`/ledger-import/detect`）都必须经这里 —— 「同一 wire shape」靠单一实现，
而不是三处各写一遍再人工对拍（spec R8 / AC-14）。

本模块**不做任何判定**：标签映射、状态判定、digest 计算全在
`unit_normalization.py`（唯一运行时单源）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def detection_diagnostics(result: Any) -> list[dict[str, Any]]:
    """把 `LedgerDetectionResult` 摊平成 preview 诊断项形状。

    只做形状转换（`file` / `sheet` / `amount_unit`），不做任何判定 ——
    判定逻辑全在 `unit_normalization.summarize_detected_units`。
    """
    diagnostics: list[dict[str, Any]] = []
    for file_detection in getattr(result, "files", None) or []:
        file_name = getattr(file_detection, "file_name", "") or ""
        for sheet in getattr(file_detection, "sheets", None) or []:
            evidence = getattr(sheet, "detection_evidence", None) or {}
            diagnostics.append(
                {
                    "file": file_name,
                    "sheet": getattr(sheet, "sheet_name", "") or "",
                    "amount_unit": evidence.get("amount_unit"),
                }
            )
    return diagnostics


def build_unit_detection_payload(
    *,
    diagnostics: list[dict[str, Any]] | None,
    project_id: UUID | None = None,
    upload_token: str | None = None,
) -> dict[str, Any]:
    """由 preview/detect 的诊断项生成 **同一份** `UnitDetectionSummary`。

    `file_hashes` 只在有 `upload_token` 时读（bundle 证据）；读不到证据
    （旧 bundle 缺 hash）时**不让检测整体失败** —— 单位检测本身仍可用，
    但 `evidence_digest` 只由标签与 detector_version 决定，
    后续 submit 会因 bundle 证据不全而被 `UPLOAD_BUNDLE_INTEGRITY_FAILED`
    拦住（拒绝发生在**写入前**，而不是在这里静默放行）。
    """
    from app.services.ledger_import.unit_normalization import summarize_detected_units
    from app.services.ledger_import_upload_service import LedgerImportUploadService

    sheets: list[tuple[str, str, str | None]] = []
    for diag in diagnostics or []:
        file_name = str(diag.get("file") or "")
        sheet_name = str(diag.get("sheet") or "")
        raw_unit = diag.get("amount_unit")
        sheets.append((file_name, sheet_name, str(raw_unit) if raw_unit else None))

    file_hashes: dict[str, tuple[str, int]] | None = None
    if upload_token and project_id is not None:
        try:
            file_hashes, _manifest = LedgerImportUploadService.load_bundle_unit_evidence(
                project_id, upload_token, require_hashes=False
            )
        except Exception as exc:  # noqa: BLE001 - 证据缺失不阻断检测
            logger.warning("unit detection: bundle 证据读取失败（不阻断检测）: %s", exc)
            file_hashes = None

    detection = summarize_detected_units(sheets=sheets, file_hashes=file_hashes)
    return detection.summary.model_dump(mode="json")


def read_cached_unit_detection(bundle_dir: Path) -> dict[str, Any] | None:
    """读 detect 阶段缓存在 bundle manifest 里的 `unit_detection`（worker 侧使用）。

    返回 `None` 表示「没有缓存」（旧 bundle / 测试直调）—— 调用方按同一 builder
    现算即可。缓存存在但损坏时也返回 `None`（由调用方决定是否记录日志），
    不在这里抛：缓存缺失与缓存损坏对调用方是同一个处置（现算）。
    """
    manifest_path = Path(bundle_dir) / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 缺文件 / 坏 JSON 都视为无缓存
        return None
    cached = manifest.get("unit_detection")
    return cached if isinstance(cached, dict) else None


__all__ = ["build_unit_detection_payload", "detection_diagnostics", "read_cached_unit_detection"]
