"""BulkExportService — 项目级底稿批量导出编排（Req 1/3/6）

编排流程：
  build_manifest → for each exportable entry → export_tab → ZipAssembler.write
  → 写 manifest.json（含 sha256）+ README.txt → finalize

fail-soft：单 Tab 导出失败 → log warning, skip that tab, continue with rest。
mode=data + only_with_data：空表（无数据行）标 skipped("no_data")。
service 只 flush 不 commit。

Requirements: 1.1, 1.2, 1.7, 3.1, 3.2, 3.3, 6.3
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
from typing import Any, Literal, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bulk_tab.manifest_builder import (
    BulkManifest,
    ManifestFileEntry,
    ManifestSkippedEntry,
    build_manifest,
)
from app.services.bulk_tab.single_tab_adapter import export_tab
from app.services.bulk_tab.zip_handler import ZipAssembler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Progress callback protocol
# ---------------------------------------------------------------------------


class ProgressCallback(Protocol):
    """SSE 进度回调协议。"""

    def tick(self, message: str = "") -> None: ...


# ---------------------------------------------------------------------------
# Helper: SHA-256
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
    """计算 bytes 的 SHA-256 hex digest。"""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Helper: 检测空 xlsx（mode=data + only_with_data）
# ---------------------------------------------------------------------------


def _is_empty_xlsx(xlsx_bytes: bytes) -> bool:
    """检测 xlsx 文件是否为空数据文件（仅有表头、无数据行）。

    策略：用 openpyxl 只读模式打开，检查第一个 sheet 的数据行数。
    若仅有 0~1 行（可能是表头）则视为空。

    对于无法解析的文件（非 xlsx），保守返回 False（不跳过）。
    """
    try:
        import openpyxl

        wb = openpyxl.load_workbook(
            io.BytesIO(xlsx_bytes), read_only=True, data_only=True
        )
        ws = wb.active
        if ws is None:
            wb.close()
            return True

        # 统计非空行数（跳过表头行）
        row_count = 0
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                # 第一行通常是表头
                continue
            # 判断该行是否有任何非空值
            if any(cell is not None and str(cell).strip() != "" for cell in row):
                row_count += 1
                if row_count > 0:
                    # 有至少 1 行数据即非空
                    wb.close()
                    return False

        wb.close()
        return row_count == 0
    except Exception:
        # 解析失败保守不跳过
        logger.debug("_is_empty_xlsx: 无法解析 xlsx，保守返回 False")
        return False


# ---------------------------------------------------------------------------
# Helper: README.txt 渲染
# ---------------------------------------------------------------------------


def _render_readme(manifest: BulkManifest) -> str:
    """生成 README.txt 内容（Req 1.7）。

    包含：
    - ZIP 使用说明
    - 导出信息（项目/模式/循环/导出时间）
    - 逐 Tab 文件列表（含编制提示链接引导）
    """
    mode_label = "模板" if manifest.mode == "template" else "数据"
    lines: list[str] = [
        f"# 项目级底稿批量{mode_label}包",
        "",
        "## 使用说明",
        "",
    ]

    if manifest.mode == "template":
        lines.extend([
            "1. 解压本 ZIP 到本地文件夹。",
            "2. 按需打开各 Excel 文件，参照编制提示填写数据。",
            "3. 填写完毕后，将整个文件夹重新压缩为 ZIP（保持目录结构不变）。",
            "4. 在系统中选择「导入全部数据」上传 ZIP 即可批量导入。",
            "",
            "注意事项：",
            "- 请勿修改文件名或目录结构，否则导入时将无法识别。",
            "- 请勿修改表头行（第一行），仅在数据行填写。",
            "- 支持部分导入：未修改的文件可删除，系统会跳过缺失文件。",
        ])
    else:
        lines.extend([
            "1. 本 ZIP 包含项目当前所有已填写数据的导出快照。",
            "2. 可用于项目归档、离线查看或跨人协作。",
            "3. 如需将修改后的数据导回，请保持目录结构后重新上传。",
        ])

    lines.extend([
        "",
        "## 导出信息",
        "",
        f"- 项目ID: {manifest.project_id}",
        f"- 审计年度: {manifest.audit_year}",
        f"- 导出模式: {mode_label}",
        f"- 审计循环: {', '.join(manifest.cycles)}",
        f"- 导出时间: {manifest.exported_at}",
        f"- 导出人: {manifest.exported_by}",
        f"- 平台版本: {manifest.platform_version}",
        "",
        "## 文件清单",
        "",
    ])

    for f in manifest.files:
        if f.sha256:
            # 已成功导出的文件
            lines.append(f"- [{f.sheet_code}] {f.sheet_name}")
            lines.append(f"  路径: {f.zip_path}")
            lines.append(f"  编制提示: 请参照系统内该 Tab 的编制指导进行填写。")
            lines.append("")

    if manifest.skipped:
        lines.extend([
            "## 跳过的 Tab",
            "",
        ])
        for s in manifest.skipped:
            lines.append(f"- [{s.sheet_code}] {s.sheet_name} — 原因: {s.skip_reason}")

    lines.append("")
    lines.append("---")
    lines.append("本文件由系统自动生成，请勿手动修改。")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------


async def export(
    db: AsyncSession,
    project_id: UUID,
    cycles: list[str] | None,
    mode: Literal["template", "data"],
    *,
    only_with_data: bool = False,
    exported_by: str = "",
    platform_version: str = "",
    audit_year: int = 0,
    progress: Any | None = None,
) -> io.BytesIO:
    """批量导出底稿为 ZIP。

    编排流程：
    1. build_manifest 获取 BulkManifest
    2. 遍历 manifest.exportable() 逐 Tab 调 export_tab
    3. mode=data + only_with_data 时检测空表跳过
    4. 计算 sha256 更新 entry
    5. 写 manifest.json + README.txt
    6. finalize 返回 BytesIO

    fail-soft: 单 Tab 失败 → log warning, skip, continue。
    service 只 flush 不 commit。

    Args:
        db: AsyncSession（只 flush 不 commit）。
        project_id: 项目 UUID。
        cycles: 审计循环列表（如 ["D"]）。None 导出全部。
        mode: "template" 或 "data"。
        only_with_data: mode=data 时是否仅导出有数据的 Tab（Req 3.3）。
        exported_by: 导出人用户名。
        platform_version: 平台版本号。
        audit_year: 审计年度。
        progress: SSE 进度回调（可选）。

    Returns:
        BytesIO 包含完整 ZIP。

    Raises:
        AcnrCatalogUnavailableError: ACNR catalog 不可用。
    """
    # ─── Step 1: Build manifest ───────────────────────────────────────
    manifest = await build_manifest(
        db=db,
        project_id=project_id,
        cycles=cycles,
        mode=mode,
        exported_by=exported_by,
        platform_version=platform_version,
        audit_year=audit_year,
    )

    # ─── Step 2: Create ZipAssembler ──────────────────────────────────
    zip_assembler = ZipAssembler()

    # ─── Step 3: Export each tab ──────────────────────────────────────
    exportable_entries = manifest.exportable()
    exported_count = 0
    skipped_count = 0

    for entry in exportable_entries:
        try:
            # 调用 SingleTabIeAdapter.export_tab
            xlsx_bytes = await export_tab(
                db=db,
                wp_id=entry.wp_id,
                api_prefix=entry.api_prefix,
                sheet_code=entry.sheet_code,
                mode=mode,
            )
        except KeyError:
            # api_prefix 未注册 → skip_reason=no_adapter（fail-soft）
            logger.warning(
                "bulk_export: skip %s — no_adapter (api_prefix=%s)",
                entry.sheet_code,
                entry.api_prefix,
            )
            manifest.skipped.append(
                ManifestSkippedEntry(
                    addr_id=entry.addr_id,
                    sheet_code=entry.sheet_code,
                    sheet_name=entry.sheet_name,
                    parent_wp_code=entry.parent_wp_code,
                    skip_reason="no_adapter",
                )
            )
            # 从 files 中移除此 entry（通过清空 sha256 标记，后续不写入）
            entry.sha256 = ""
            skipped_count += 1
            if progress:
                progress.tick(f"跳过 {entry.sheet_code}（无适配器）")
            continue
        except Exception as exc:
            # 其他异常 → fail-soft，记日志跳过
            logger.warning(
                "bulk_export: skip %s — export_tab failed: %s",
                entry.sheet_code,
                exc,
                exc_info=True,
            )
            manifest.skipped.append(
                ManifestSkippedEntry(
                    addr_id=entry.addr_id,
                    sheet_code=entry.sheet_code,
                    sheet_name=entry.sheet_name,
                    parent_wp_code=entry.parent_wp_code,
                    skip_reason="export_failed",
                )
            )
            entry.sha256 = ""
            skipped_count += 1
            if progress:
                progress.tick(f"跳过 {entry.sheet_code}（导出失败）")
            continue

        # ─── mode=data + only_with_data → 检测空表 ────────────────────
        if mode == "data" and only_with_data and _is_empty_xlsx(xlsx_bytes):
            logger.info(
                "bulk_export: skip %s — no_data (empty xlsx)",
                entry.sheet_code,
            )
            manifest.skipped.append(
                ManifestSkippedEntry(
                    addr_id=entry.addr_id,
                    sheet_code=entry.sheet_code,
                    sheet_name=entry.sheet_name,
                    parent_wp_code=entry.parent_wp_code,
                    skip_reason="no_data",
                )
            )
            entry.sha256 = ""
            skipped_count += 1
            if progress:
                progress.tick(f"跳过 {entry.sheet_code}（无数据）")
            continue

        # ─── 计算 sha256 并写入 ZIP ───────────────────────────────────
        file_hash = _sha256(xlsx_bytes)
        entry.sha256 = file_hash

        zip_assembler.write(entry.zip_path, xlsx_bytes)
        exported_count += 1

        if progress:
            progress.tick(f"已导出 {entry.sheet_code} ({exported_count})")

    # ─── Step 4: 从 manifest.files 中移除未成功导出的 entries ─────────
    # 保留 sha256 非空的 entries 在 files 中（已成功导出）
    manifest.files = [f for f in manifest.files if f.sha256]

    # ─── Step 5: Write manifest.json ──────────────────────────────────
    manifest_json = json.dumps(
        manifest.to_dict(),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    zip_assembler.write("manifest.json", manifest_json)

    # ─── Step 6: Write README.txt ─────────────────────────────────────
    readme_text = _render_readme(manifest).encode("utf-8")
    zip_assembler.write("README.txt", readme_text)

    # ─── Step 7: Finalize ─────────────────────────────────────────────
    logger.info(
        "bulk_export: project=%s mode=%s cycles=%s exported=%d skipped=%d",
        project_id,
        mode,
        cycles,
        exported_count,
        skipped_count,
    )

    return zip_assembler.finalize()
