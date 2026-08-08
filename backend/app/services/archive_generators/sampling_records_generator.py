"""归档章节 05 — 抽样记录汇总生成器

spec: sampling-evaluation-and-governance-closure R8
Validates: Requirements 8.1, 8.2, 8.3, 8.5, 8.6

## 为什么需要它

2026-08-05 实证：`archive_completeness_service` / `completeness_service` /
`archive_manifest_service` 中 `sampling` / `抽样` / `抽凭` 的提及数**全为 0** ——
归档包完全不感知抽样。而 CAS 1314 的记录要求（总体、样本量确定依据、抽样框版本、
随机种子、偏差、推断错报、错报上限、结论）本身就是归档件的组成部分：
监管抽查时若无法一次性看到全项目的抽样记录，只能逐张底稿点开。

## 数据来源

`sampling_records`（可查询侧投影，与 `workpaper_extraction_log.extraction_criteria`
同一次写入）+ JOIN `wp_index.wp_code` 定位底稿。已撤销批次已由
`undo_sampling_registration` 软删，本章节自动排除。

## 记录不完整的批次单独列出

判定复用 `sampling_qc_rules.evaluate_sampling_completeness`（与 QC-12 同一判据），
避免两处各写一套导致「QC 说不合规、归档说完整」这种打架。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _fmt_amount(value: Decimal | None) -> str:
    """金额渲染。`None` 显示「未记录」而非 0 —— 两者含义完全不同。"""
    if value is None:
        return "未记录"
    return f"{value:,.2f}"


def _fmt_int(value: int | None) -> str:
    return "未记录" if value is None else str(value)


async def generate_sampling_records(project_id: UUID, db: AsyncSession) -> bytes | None:
    """生成抽样记录汇总文本。

    Returns:
        UTF-8 字节。**无抽样批次时也返回内容**（说明「本项目未执行抽样程序」）而非 None ——
        归档件里「明确说明未执行」与「章节缺失」的审计含义不同（R8.5）。
        生成失败时返回占位说明，不抛出（R8.6：不得让归档整体失败）。
    """
    try:
        return await _generate(project_id, db)
    except Exception:  # noqa: BLE001 — 章节生成失败不得阻断归档
        logger.warning("抽样记录归档章节生成失败，输出占位说明 project=%s", project_id, exc_info=True)
        return (
            "抽样记录汇总\n\n"
            "本章节生成失败，未能读取抽样记录。请联系技术支持后重新生成归档包。\n"
            "（原始留痕仍保存在 workpaper_extraction_log.extraction_criteria，未丢失。）\n"
        ).encode("utf-8")


async def _generate(project_id: UUID, db: AsyncSession) -> bytes:
    from app.models.core import Project
    from app.models.workpaper_models import SampledVoucher, SamplingRecord, WorkingPaper, WpIndex
    from app.services.sampling_qc_rules import (
        SamplingBatchView,
        evaluate_sampling_completeness,
    )

    project = (
        await db.execute(sa.select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    project_name = project.name if project else str(project_id)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    rows = (
        await db.execute(
            sa.select(SamplingRecord, WpIndex.wp_code)
            .select_from(SamplingRecord)
            .join(
                WorkingPaper,
                WorkingPaper.id == SamplingRecord.working_paper_id,
                isouter=True,
            )
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id, isouter=True)
            .where(
                SamplingRecord.project_id == project_id,
                SamplingRecord.is_deleted == sa.false(),
            )
            .order_by(WpIndex.wp_code, SamplingRecord.created_at)
        )
    ).all()

    lines: list[str] = [
        "抽样记录汇总（CAS 1314）",
        f"项目: {project_name}",
        f"生成时间: {now_str}",
        "",
    ]

    if not rows:
        lines += [
            "本项目未执行抽样程序。",
            "",
            "说明：本章节列示 CAS 1314 要求记录的抽样事项（总体、样本量确定依据、",
            "抽样框版本、随机种子、偏差、推断错报、错报上限、结论）。已撤销的抽凭批次",
            "不在此列示。",
        ]
        return "\n".join(lines).encode("utf-8")

    lines.append(f"抽样批次总数: {len(rows)}")
    lines.append("")

    incomplete: list[str] = []

    for idx, (rec, wp_code) in enumerate(rows, 1):
        # 已抽凭证数（按批次统计，排除软删）
        voucher_count = 0
        if rec.batch_id is not None:
            voucher_count = int(
                (
                    await db.execute(
                        sa.select(sa.func.count()).select_from(SampledVoucher).where(
                            SampledVoucher.batch_id == rec.batch_id,
                            SampledVoucher.is_deleted == sa.false(),
                        )
                    )
                ).scalar()
                or 0
            )

        lines.append(f"批次 {idx}：{wp_code or '底稿编码未知'}")
        lines.append(f"  批次标识: {rec.batch_id or '未记录'}")
        lines.append(f"  抽样目的: {rec.sampling_purpose or '未记录'}")
        lines.append(f"  总体描述: {rec.population_description or '未记录'}")
        lines.append(f"  总体金额: {_fmt_amount(rec.population_total_amount)}")
        lines.append(f"  总体笔数: {_fmt_int(rec.population_total_count)}")
        lines.append(f"  样本量: {rec.sample_size}")
        lines.append(f"  已登记凭证数: {voucher_count}")
        lines.append(f"  样本量确定依据: {rec.sampling_method_description or '未记录'}")
        lines.append(f"  抽样方法: {rec.sampling_method or '未记录'}")
        lines.append(f"  随机种子: {_fmt_int(rec.random_seed)}")
        lines.append(f"  抽样框版本: {rec.dataset_id or '未记录'}")
        lines.append(f"  偏差笔数: {_fmt_int(rec.deviations_found)}")
        lines.append(f"  已知错报: {_fmt_amount(rec.misstatements_found)}")
        lines.append(f"  推断错报: {_fmt_amount(rec.projected_misstatement)}")
        lines.append(f"  错报上限: {_fmt_amount(rec.upper_misstatement_limit)}")
        conclusion = rec.conclusion or "未记录"
        lines.append("  结论:")
        for seg in str(conclusion).split("\n"):
            lines.append(f"    {seg}")
        lines.append("")

        # 完整性判定：与 QC-12 共用判据。投影表没有 conclusion_confirmed 列，
        # 故按「结论文本是否存在」+「推断错报是否记录」两项作投影侧的等价判定，
        # 并在消息里说明来源，避免与 QC-12 的措辞冲突。
        view = SamplingBatchView(
            batch_id=str(rec.batch_id) if rec.batch_id else None,
            criteria={
                "evaluation": {
                    "projected": (
                        str(rec.projected_misstatement)
                        if rec.projected_misstatement is not None
                        else None
                    ),
                    "upper_limit": (
                        str(rec.upper_misstatement_limit)
                        if rec.upper_misstatement_limit is not None
                        else None
                    ),
                    "conclusion_message": rec.conclusion,
                    # 投影表无该列 → 有结论文本即视为已确认，避免对全部批次误报
                    "conclusion_confirmed": bool(rec.conclusion),
                }
            },
            wp_code=wp_code,
        )
        incomplete.extend(evaluate_sampling_completeness([view]))

    if incomplete:
        lines.append("─" * 60)
        lines.append("记录不完整的抽样批次（须补齐后归档）")
        lines.append("")
        for msg in incomplete:
            lines.append(f"  · {msg}")
        lines.append("")

    return "\n".join(lines).encode("utf-8")


#: 归档章节前缀。**06 而非 05** —— 05 已被「AI 贡献明细」占用，而
#: `archive_section_registry.register` 对同 order_prefix 是**覆盖**语义
#: （后注册的顶掉先注册的），用 05 会静默删掉 AI 贡献明细章节。
#: 新增归档章节前必须先 `list_all()` 查已占前缀。
ARCHIVE_SECTION_PREFIX = "06"
ARCHIVE_SECTION_FILENAME = "06-抽样记录汇总.txt"
