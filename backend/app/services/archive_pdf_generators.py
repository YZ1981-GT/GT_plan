"""归档 PDF 生成器 — 封面与签字流水

Refinement Round 1 — 需求 6 / Task 15

实现方案：HTML 模板 → LibreOffice headless 转 PDF（与 pdf_export_engine 一致）。
不依赖 python-docx（未安装），直接生成 HTML 再转换。

水印："本归档包由审计平台 v{ver} 于 {time} 自动生成，SHA-256: {hash}"
（hash 在归档包最终打包时才能计算，此处用占位符）

导出函数：
  - generate_project_cover_pdf(project_id, db) -> bytes | None
  - generate_signature_ledger_pdf(project_id, db) -> bytes | None
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

APP_VERSION = "1.0.0"
LIBREOFFICE_TIMEOUT = 60  # seconds

# 审计意见类型中文映射
OPINION_TYPE_LABELS: dict[str, str] = {
    "unqualified": "无保留意见",
    "qualified": "保留意见",
    "adverse": "否定意见",
    "disclaimer": "无法表示意见",
}

# 签字方式中文映射
SIGNATURE_METHOD_LABELS: dict[str, str] = {
    "electronic": "电子签名",
    "handwritten": "手写签名",
    "dual_verification": "双重验证",
}

# ---------------------------------------------------------------------------
# LibreOffice 检测与转换
# ---------------------------------------------------------------------------


def _find_libreoffice() -> str | None:
    """检测 LibreOffice 可执行文件路径。"""
    for cmd in ("libreoffice", "soffice"):
        path = shutil.which(cmd)
        if path:
            return path
    return None


def _html_to_pdf_weasyprint(html_content: str) -> bytes | None:
    """尝试使用 weasyprint 将 HTML 转为 PDF（比 LibreOffice 快）。

    weasyprint is optional dependency; install with: pip install weasyprint
    返回 PDF bytes，weasyprint 未安装或转换失败返回 None。
    """
    try:
        import weasyprint
        return weasyprint.HTML(string=html_content).write_pdf()
    except ImportError:
        return None
    except Exception as exc:
        logger.warning("[ARCHIVE_PDF] weasyprint conversion failed: %s", exc)
        return None


def _html_to_pdf_bytes(html_content: str) -> bytes | None:
    """将 HTML 内容转换为 PDF bytes。

    R1 Bug Fix 9: 优先尝试 weasyprint（更快），不可用时降级到 LibreOffice headless。
    # weasyprint is optional dependency; install with: pip install weasyprint
    """
    # 优先尝试 weasyprint（纯 Python，无需外部进程，速度更快）
    pdf = _html_to_pdf_weasyprint(html_content)
    if pdf is not None:
        return pdf

    # 降级到 LibreOffice headless
    lo_path = _find_libreoffice()
    if not lo_path:
        logger.warning("[ARCHIVE_PDF] Neither weasyprint nor LibreOffice available, cannot convert to PDF")
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        html_file = Path(tmpdir) / "input.html"
        html_file.write_text(html_content, encoding="utf-8")

        try:
            subprocess.run(
                [
                    lo_path,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmpdir,
                    str(html_file),
                ],
                timeout=LIBREOFFICE_TIMEOUT,
                capture_output=True,
                check=True,
            )
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as exc:
            logger.error("[ARCHIVE_PDF] LibreOffice conversion failed: %s", exc)
            return None

        pdf_file = Path(tmpdir) / "input.pdf"
        if pdf_file.exists():
            return pdf_file.read_bytes()

        logger.error("[ARCHIVE_PDF] PDF output not found after conversion")
        return None


# ---------------------------------------------------------------------------
# HTML 模板
# ---------------------------------------------------------------------------

_WATERMARK_TEXT = (
    "本归档包由审计平台 v{version} 于 {time} 自动生成，SHA-256: {hash}"
)

_COVER_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>项目封面</title>
<style>
body {{
    font-family: 仿宋_GB2312, SimSun, serif;
    font-size: 14pt;
    margin: 3cm;
    position: relative;
    min-height: 100vh;
}}
.title {{
    text-align: center;
    font-size: 22pt;
    font-weight: bold;
    margin-top: 80px;
    margin-bottom: 60px;
}}
.info-table {{
    width: 80%;
    margin: 0 auto;
    border-collapse: collapse;
}}
.info-table td {{
    padding: 12px 16px;
    font-size: 14pt;
    border-bottom: 1px solid #ccc;
}}
.info-table td:first-child {{
    font-weight: bold;
    width: 40%;
    color: #333;
}}
.watermark {{
    position: fixed;
    bottom: 20px;
    left: 0;
    right: 0;
    text-align: center;
    font-size: 8pt;
    color: #999;
}}
</style></head>
<body>
<div class="title">审计项目归档封面</div>
<table class="info-table">
<tr><td>客户名称</td><td>{client_name}</td></tr>
<tr><td>项目名称</td><td>{project_name}</td></tr>
<tr><td>会计期间</td><td>{period}</td></tr>
<tr><td>审计意见类型</td><td>{opinion_type}</td></tr>
<tr><td>审计报告文号</td><td>{report_number}</td></tr>
<tr><td>签字日期</td><td>{sign_date}</td></tr>
<tr><td>签字合伙人</td><td>{partner_name}</td></tr>
</table>
<div class="watermark">{watermark}</div>
</body></html>
"""

_LEDGER_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>签字流水</title>
<style>
body {{
    font-family: 仿宋_GB2312, SimSun, serif;
    font-size: 12pt;
    margin: 2cm 2.5cm;
    position: relative;
    min-height: 100vh;
}}
.title {{
    text-align: center;
    font-size: 18pt;
    font-weight: bold;
    margin-bottom: 30px;
}}
.subtitle {{
    text-align: center;
    font-size: 11pt;
    color: #666;
    margin-bottom: 20px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 10px;
}}
th, td {{
    padding: 8px 10px;
    border: 1px solid #333;
    text-align: center;
    font-size: 10pt;
}}
th {{
    background-color: #f0f0f0;
    font-weight: bold;
}}
td {{
    word-break: break-all;
}}
.watermark {{
    position: fixed;
    bottom: 20px;
    left: 0;
    right: 0;
    text-align: center;
    font-size: 8pt;
    color: #999;
}}
</style></head>
<body>
<div class="title">三级签字流水</div>
<div class="subtitle">{project_name} — {client_name}</div>
<table>
<thead>
<tr>
<th>序号</th>
<th>签字级别</th>
<th>签字角色</th>
<th>签字人</th>
<th>签字时间</th>
<th>签字方式</th>
<th>Gate Eval ID</th>
<th>验证哈希</th>
</tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
<div class="watermark">{watermark}</div>
</body></html>
"""

_LEDGER_ROW_TEMPLATE = """\
<tr>
<td>{index}</td>
<td>{level}</td>
<td>{role}</td>
<td>{signer_name}</td>
<td>{signed_at}</td>
<td>{method}</td>
<td style="font-size:8pt">{gate_eval_id}</td>
<td style="font-size:8pt">{verification_hash}</td>
</tr>
"""


# ---------------------------------------------------------------------------
# 数据查询辅助
# ---------------------------------------------------------------------------


async def _get_project(project_id: UUID, db: AsyncSession) -> Any | None:
    """查询 Project 对象。"""
    from app.models.core import Project

    result = await db.execute(
        sa.select(Project).where(Project.id == project_id)
    )
    return result.scalar_one_or_none()


async def _get_audit_report(project_id: UUID, db: AsyncSession) -> Any | None:
    """查询项目最新的 AuditReport。"""
    from app.models.report_models import AuditReport

    result = await db.execute(
        sa.select(AuditReport)
        .where(AuditReport.project_id == project_id)
        .order_by(AuditReport.year.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_signature_records(project_id: UUID, db: AsyncSession) -> list[Any]:
    """查询项目的签字记录（按 required_order 排序）。"""
    from app.models.extension_models import SignatureRecord

    result = await db.execute(
        sa.select(SignatureRecord)
        .where(
            SignatureRecord.object_type == "audit_report",
            SignatureRecord.object_id == project_id,
            SignatureRecord.is_deleted == False,  # noqa: E712
        )
        .order_by(
            sa.func.coalesce(SignatureRecord.required_order, 99),
            SignatureRecord.created_at,
        )
    )
    return list(result.scalars().all())


async def _get_user_display_name(user_id: UUID, db: AsyncSession) -> str:
    """获取用户显示名称。"""
    from app.models.core import User

    result = await db.execute(
        sa.select(User.username).where(User.id == user_id)
    )
    row = result.scalar_one_or_none()
    return row or "未知"


# ---------------------------------------------------------------------------
# 水印生成
# ---------------------------------------------------------------------------


def _build_watermark(hash_value: str | None = None) -> str:
    """生成水印文本。

    Args:
        hash_value: 归档包 SHA-256 哈希值。若为 None 则使用占位符
                    （首次生成时哈希尚未计算，归档完成后由 manifest_hash 字段记录真实值）。
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return _WATERMARK_TEXT.format(
        version=APP_VERSION,
        time=now_str,
        hash=hash_value or "见 manifest_hash",
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


async def generate_project_cover_pdf(
    project_id: UUID, db: AsyncSession
) -> bytes | None:
    """生成项目封面 PDF。

    查询 Project + AuditReport 数据，填充 HTML 模板，通过 LibreOffice 转 PDF。
    返回 PDF bytes，失败返回 None。
    """
    project = await _get_project(project_id, db)
    if project is None:
        logger.warning("[ARCHIVE_PDF] Project not found: %s", project_id)
        return None

    report = await _get_audit_report(project_id, db)

    # 构建封面数据
    client_name = project.client_name or "—"
    project_name = project.name or "—"

    # 会计期间
    period = "—"
    if project.audit_period_start and project.audit_period_end:
        period = f"{project.audit_period_start} 至 {project.audit_period_end}"
    elif report:
        period = f"{report.year} 年度"

    # 审计意见
    opinion_type = "—"
    if report and report.opinion_type:
        opinion_type = OPINION_TYPE_LABELS.get(
            report.opinion_type.value if hasattr(report.opinion_type, "value") else str(report.opinion_type),
            str(report.opinion_type),
        )

    # 报告文号（AuditReport 无 report_number 字段，从 paragraphs 或 signing_partner 推断）
    report_number = "—"
    if report and report.paragraphs and isinstance(report.paragraphs, dict):
        report_number = report.paragraphs.get("report_number", "—")

    # 签字日期
    sign_date = "—"
    if report and report.report_date:
        sign_date = str(report.report_date)

    # 签字合伙人
    partner_name = "—"
    if report and report.signing_partner:
        partner_name = report.signing_partner

    watermark = _build_watermark()

    html = _COVER_HTML_TEMPLATE.format(
        client_name=_escape_html(client_name),
        project_name=_escape_html(project_name),
        period=_escape_html(period),
        opinion_type=_escape_html(opinion_type),
        report_number=_escape_html(report_number),
        sign_date=_escape_html(sign_date),
        partner_name=_escape_html(partner_name),
        watermark=_escape_html(watermark),
    )

    pdf_bytes = _html_to_pdf_bytes(html)
    if pdf_bytes:
        logger.info("[ARCHIVE_PDF] Project cover PDF generated: %s", project_id)
    return pdf_bytes


async def generate_signature_ledger_pdf(
    project_id: UUID, db: AsyncSession
) -> bytes | None:
    """生成签字流水 PDF。

    列出三级签字（预留 N 级扩展）的时间戳、签字人、签字方式、gate_eval_id、验证哈希。
    返回 PDF bytes，失败返回 None。
    """
    project = await _get_project(project_id, db)
    if project is None:
        logger.warning("[ARCHIVE_PDF] Project not found: %s", project_id)
        return None

    signatures = await _get_signature_records(project_id, db)

    # 构建行数据
    rows_html = ""
    for idx, sig in enumerate(signatures, start=1):
        # 签字人名称
        signer_name = await _get_user_display_name(sig.signer_id, db)

        # 签字时间
        signed_at = "—"
        if sig.signature_timestamp:
            signed_at = sig.signature_timestamp.strftime("%Y-%m-%d %H:%M:%S")

        # 签字方式
        method = "电子签名"  # 默认
        if sig.signature_data and isinstance(sig.signature_data, dict):
            raw_method = sig.signature_data.get("method", "electronic")
            method = SIGNATURE_METHOD_LABELS.get(raw_method, raw_method)

        # Gate Eval ID
        gate_eval_id = "—"
        if sig.signature_data and isinstance(sig.signature_data, dict):
            gate_eval_id = sig.signature_data.get("gate_eval_id", "—")

        # 验证哈希
        verification_hash = "—"
        if sig.signature_data and isinstance(sig.signature_data, dict):
            verification_hash = sig.signature_data.get("verification_hash", "—")

        # 签字级别
        level = sig.signature_level or f"level{sig.required_order or idx}"

        # 签字角色
        role = sig.required_role or "—"

        rows_html += _LEDGER_ROW_TEMPLATE.format(
            index=idx,
            level=_escape_html(level),
            role=_escape_html(role),
            signer_name=_escape_html(signer_name),
            signed_at=_escape_html(signed_at),
            method=_escape_html(method),
            gate_eval_id=_escape_html(str(gate_eval_id)),
            verification_hash=_escape_html(str(verification_hash)),
        )

    if not rows_html:
        rows_html = '<tr><td colspan="8" style="text-align:center;color:#999">暂无签字记录</td></tr>'

    watermark = _build_watermark()

    html = _LEDGER_HTML_TEMPLATE.format(
        project_name=_escape_html(project.name or "—"),
        client_name=_escape_html(project.client_name or "—"),
        rows=rows_html,
        watermark=_escape_html(watermark),
    )

    pdf_bytes = _html_to_pdf_bytes(html)
    if pdf_bytes:
        logger.info("[ARCHIVE_PDF] Signature ledger PDF generated: %s", project_id)
    return pdf_bytes


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _escape_html(text: str) -> str:
    """简单 HTML 转义。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
