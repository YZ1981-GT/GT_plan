"""自定义底稿（componentType=custom）的独立导出路径。

## 为什么必须独立一条路径

自定义底稿的既有两条导出路径**都不可用**（2026-08-06 实证）：

1. `POST /api/workpapers/{id}/export-xlsx` → 第一步 `load_schema(wp_code)` 对自定义
   编号必 `FileNotFoundError`（`wp_render_schema/` 下没有它的 yaml）⇒ **500**。
2. `WpExportEngine._export_xlsx` → `export_workpaper_xlsx` 读
   `html_data[sheet]["rows"]`（`dynamic_table` 形态），而自定义底稿是
   `{"cells": {"B5": {...}}}` 形态 ⇒ 抛异常后被
   `except (TemplateNotFoundError, Exception)` **吞掉并回退空白 workbook**，
   于是**返回 200 但文件内容不全** —— 比 500 更坏（用户拿去归档才发现）。

## 本模块的口径

**xlsx 文件本体就是权威**，所以导出 = 原样交付该文件（再由调用方嵌元数据）。
既不需要 schema，也不需要把 `cells` 投影回 `rows`。

🔴 **禁 fail-open 回退空白 workbook**：文件缺失/损坏时抛 `CustomExportError`，
   让调用方返回明确错误。导出是交付件动作，「静默给一个空文件」是最坏结果。

spec: .kiro/specs/custom-workpaper-dual-mode-formula-and-batch/ Wave 5 Task 16
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CustomExportError(Exception):
    """自定义底稿导出失败（文件缺失 / 不是合法 xlsx / 读取失败）。

    🔴 有意不继承 HTTPException：本模块是 service 层，HTTP 语义由路由层决定。
    """


def _resolve_file(file_path: str | None) -> Path:
    """解析底稿文件路径。

    🔴 `working_paper.file_path` 存的是**相对 `backend/` 的相对路径**
    （`storage\\...`，Windows 反斜杠）—— 直接 `Path(x).exists()` 在仓库根下
    必落空（平台已记铁律）。故依次尝试 CWD / backend / 仓库根。
    """
    if not file_path:
        raise CustomExportError("底稿文件路径为空，请重新生成底稿")

    raw = str(file_path).replace("\\", "/")
    backend_root = Path(__file__).resolve().parents[2]      # -> backend/
    repo_root = backend_root.parent

    for base in (Path.cwd(), backend_root, repo_root):
        p = (base / raw) if not Path(raw).is_absolute() else Path(raw)
        if p.is_file():
            return p
    # 绝对路径直接判一次
    ap = Path(raw)
    if ap.is_file():
        return ap
    raise CustomExportError(f"底稿文件不存在: {file_path}")


def export_custom_workpaper(
    wp: Any, project_meta: dict[str, Any] | None = None
) -> BytesIO:
    """把自定义底稿的 xlsx 本体读成字节流返回。

    Args:
        wp: `WorkingPaper`（只用到 `file_path`）
        project_meta: 兼容既有导出签名，本路径不消费
            （xlsx 本体已含被审计单位/期间等表头，重复写入反而覆盖用户内容）

    Returns:
        `BytesIO`（游标已 seek(0)），可直接交给 `MetadataCodec.embed_xlsx`

    Raises:
        CustomExportError: 文件缺失 / 不是合法 xlsx / 读取失败
    """
    fp = _resolve_file(getattr(wp, "file_path", None))

    try:
        data = fp.read_bytes()
    except OSError as exc:
        raise CustomExportError(f"读取底稿文件失败: {exc}") from exc

    if not data:
        raise CustomExportError(f"底稿文件为空: {fp.name}")

    # 合法性校验：必须能被 openpyxl 打开（xlsx 是 zip，损坏文件在这里暴露）
    # 🔴 校验而非"尽力而为"—— 导出损坏文件与导出空文件同样坏
    buf = BytesIO(data)
    try:
        import openpyxl

        wb = openpyxl.load_workbook(buf, read_only=True, data_only=False)
        try:
            if not wb.sheetnames:
                raise CustomExportError(f"底稿文件没有任何 sheet: {fp.name}")
        finally:
            wb.close()
    except CustomExportError:
        raise
    except Exception as exc:  # noqa: BLE001 — 打不开就是坏文件，必须报错
        raise CustomExportError(f"底稿文件不是合法 xlsx: {exc}") from exc

    out = BytesIO(data)
    out.seek(0)
    logger.info(
        "custom 导出: 直接交付 xlsx 本体 path=%s size=%d", fp.name, len(data)
    )
    return out
