"""a17_summary_service — A17-1 重大事项概要 章节定义 + 拉取服务

提供:
- get_chapter_definitions() → 返回 16 章定义（缓存）
- pull_chapter_data(db, project_id, chapter_id) → 从上游模块拉取章节数据

P1 MVP:
  - ch01/ch02/ch05/ch08~ch15 等 partial 章节可从关联模块拉取摘要
  - ch07/ch16 手工章节返回提示
  - 其余章节返回"数据源未就绪"
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, User
from app.services.issue_hints_service import get_issue_hints
from app.services.workpaper_summaries_service import get_workpaper_summary

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_CHAPTER_DEFS_PATH = _DATA_DIR / "a17_chapter_definitions.json"


@lru_cache(maxsize=1)
def _load_chapter_definitions() -> list[dict]:
    """加载并缓存 16 章定义 JSON"""
    try:
        return json.loads(_CHAPTER_DEFS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Failed to load a17_chapter_definitions.json: %s", e)
        return []


def get_chapter_definitions() -> list[dict]:
    """返回 A17-1 全部章节定义（16 章）"""
    return _load_chapter_definitions()


async def pull_chapter_data(
    db: AsyncSession, project_id: UUID, chapter_id: str
) -> dict:
    """从上游数据源拉取指定章节的数据。

    返回:
        {content: str|None, source_label: str|None, message: str|None}
    """
    chapters = get_chapter_definitions()
    chapter = next((ch for ch in chapters if ch["id"] == chapter_id), None)

    if chapter is None:
        return {"content": None, "source_label": None, "message": "未知章节"}

    ds = chapter.get("data_source", {})
    ds_type = ds.get("type", "auto")
    ready = ds.get("ready")

    # ── 手工章节（ch07, ch16）──
    if ds_type == "manual":
        return {
            "content": None,
            "source_label": None,
            "message": "此章节为手工填写",
        }

    # ── ch01: 项目信息拉取 ──
    if chapter_id == "A17-1-ch01":
        return await _pull_ch01_project_info(db, project_id)

    # ── ch02: 独立性（A17-7 签署 + A10-1）──
    if chapter_id == "A17-1-ch02":
        return await _pull_ch02_independence(db, project_id)

    # ── ch05: 业务咨询 + 专业分歧（A17-3 / A17-4 填写进度）──
    if chapter_id == "A17-1-ch05":
        return await _pull_ch05_consultation(db, project_id)

    # ── ch08: 分析性复核（A1-13 / A1-14）──
    if chapter_id == "A17-1-ch08":
        return await _pull_ch08_analytical_review(db, project_id)

    # ── ch09: 关联方（A7 / A7-1）──
    if chapter_id == "A17-1-ch09":
        return await _pull_ch09_related_party(db, project_id)

    # ── ch10: 持续经营（A15 / A15-1）──
    if chapter_id == "A17-1-ch10":
        return await _pull_ch10_going_concern(db, project_id)

    # ── ch11: 期后事项（A11 / A11-1）──
    if chapter_id == "A17-1-ch11":
        return await _pull_ch11_subsequent_events(db, project_id)

    # ── ch12: KAM（A17-2-1）──
    if chapter_id == "A17-1-ch12":
        return await _pull_ch12_kam(db, project_id)

    # ── ch13: 其他信息（A8 / A8-2 stub）──
    if chapter_id == "A17-1-ch13":
        return await _pull_ch13_other_info(db, project_id)

    # ── ch14: 财务报表审计结论（audit_report + A13 错报）──
    if chapter_id == "A17-1-ch14":
        return await _pull_ch14_audit_conclusion(db, project_id)

    # ── ch15: 其他特殊考虑事项（issue_tickets + A13 + A14）──
    if chapter_id == "A17-1-ch15":
        return await _pull_ch15_special_matters(db, project_id)

    # ── 其余章节: 数据源未就绪 ──
    if ready is True:
        # 标记 ready 但非 ch01 → 未来扩展点
        return {
            "content": None,
            "source_label": None,
            "message": "数据源接口待实现",
        }

    # partial 或 false
    return {
        "content": None,
        "source_label": None,
        "message": "数据源未就绪",
    }


async def _pull_ch01_project_info(db: AsyncSession, project_id: UUID) -> dict:
    """ch01: 从项目信息拉取审计业务约定范围数据"""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if project is None:
        return {
            "content": None,
            "source_label": None,
            "message": "项目不存在",
        }

    # 获取签字合伙人名称
    partner_name: str | None = None
    if project.partner_id:
        partner_stmt = select(User.username).where(User.id == project.partner_id)
        partner_result = await db.execute(partner_stmt)
        partner_name = partner_result.scalar_one_or_none()

    # 格式化审计期间
    period_start = (
        project.audit_period_start.strftime("%Y年%m月%d日")
        if project.audit_period_start
        else "未设置"
    )
    period_end = (
        project.audit_period_end.strftime("%Y年%m月%d日")
        if project.audit_period_end
        else "未设置"
    )

    lines = [
        f"被审计单位：{project.client_name}",
        f"审计期间：{period_start} 至 {period_end}",
    ]
    if partner_name:
        lines.append(f"签字会计师：{partner_name}")
    if project.business_category:
        lines.append(f"业务分类：{project.business_category} 类")

    content = "\n".join(lines)

    return {
        "content": content,
        "source_label": "project_info",
    }


async def _get_wp_id(db: AsyncSession, project_id: UUID, wp_code: str) -> UUID | None:
    result = await db.execute(
        text(
            """
            SELECT wp.id FROM working_paper wp
            JOIN wp_index wi ON wi.id = wp.wp_index_id
            WHERE wp.project_id = :pid AND wi.wp_code = :code AND wp.is_deleted = false
            LIMIT 1
            """
        ),
        {"pid": str(project_id), "code": wp_code},
    )
    val = result.scalar_one_or_none()
    return UUID(str(val)) if val else None


async def _count_checklist_filled(db: AsyncSession, wp_id: UUID) -> tuple[int, int]:
    total_r = await db.execute(
        text("SELECT COUNT(*) FROM checklist_responses WHERE wp_id = :wp_id"),
        {"wp_id": str(wp_id)},
    )
    filled_r = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM checklist_responses
            WHERE wp_id = :wp_id AND conclusion IS NOT NULL AND conclusion <> ''
            """
        ),
        {"wp_id": str(wp_id)},
    )
    return int(filled_r.scalar() or 0), int(total_r.scalar() or 0)


async def _wp_progress_line(db: AsyncSession, project_id: UUID, wp_code: str) -> str:
    """通用底稿进度一行摘要。"""
    wp_id = await _get_wp_id(db, project_id, wp_code)
    if wp_id is None:
        return f"{wp_code}：项目内无底稿"
    filled, total = await _count_checklist_filled(db, wp_id)
    if total == 0:
        return f"{wp_code}：底稿已关联（尚无 checklist 记录）"
    return f"{wp_code}：已填写 {filled}/{total} 项"


async def _pull_ch02_independence(db: AsyncSession, project_id: UUID) -> dict:
    """ch02: A17-7/A17-7A 电子签署进度 + A10-1"""
    lines: list[str] = []
    try:
        from app.models.review_workflow_models import IndependenceSigningTask

        for template_code in ("A17-7", "A17-7A"):
            base_filters = (
                IndependenceSigningTask.project_id == project_id,
                IndependenceSigningTask.template_code == template_code,
            )
            total_stmt = (
                select(func.count())
                .select_from(IndependenceSigningTask)
                .where(*base_filters)
            )
            signed_stmt = (
                select(func.count())
                .select_from(IndependenceSigningTask)
                .where(*base_filters, IndependenceSigningTask.status == "signed")
            )
            total = int((await db.execute(total_stmt)).scalar() or 0)
            signed = int((await db.execute(signed_stmt)).scalar() or 0)
            if total == 0:
                lines.append(f"{template_code}：尚未发起独立性签署")
            else:
                lines.append(f"{template_code}：已签署 {signed}/{total} 人")
    except Exception as e:
        logger.warning("ch02 independence signing 查询失败: %s", e)
        lines.append("A17-7 签署进度：查询失败")

    lines.append(await _wp_progress_line(db, project_id, "A10-1"))
    return {"content": "\n".join(lines), "source_label": "A17-7+A10-1"}


async def _pull_ch05_consultation(db: AsyncSession, project_id: UUID) -> dict:
    """ch05: A17-3 / A17-4 核对填写进度摘要"""
    lines: list[str] = []
    for code in ("A17-3", "A17-4"):
        wp_id = await _get_wp_id(db, project_id, code)
        if wp_id is None:
            lines.append(f"{code}：项目内无底稿")
            continue
        filled, total = await _count_checklist_filled(db, wp_id)
        if total == 0:
            lines.append(f"{code}：尚无 checklist 记录（docx 弹窗底稿）")
        else:
            lines.append(f"{code}：已填写 {filled}/{total} 项")
    return {
        "content": "\n".join(lines),
        "source_label": "A17-3+A17-4",
    }


async def _pull_ch08_analytical_review(db: AsyncSession, project_id: UUID) -> dict:
    """ch08: A1-13 / A1-14 分析性复核 — 显著/关注变动计数"""
    proj = (
        await db.execute(select(Project.audit_period_end).where(Project.id == project_id))
    ).scalar_one_or_none()
    year = proj.year if proj else None

    lines: list[str] = []
    configs = [("A1-13", "standalone"), ("A1-14", "consolidated")]

    for code, scope in configs:
        wp_id = await _get_wp_id(db, project_id, code)
        if wp_id is None:
            lines.append(f"{code}：项目内无底稿")
            continue
        if year is None:
            lines.append(await _wp_progress_line(db, project_id, code))
            continue
        try:
            from app.services.analytical_review_service import get_analytical_review_data

            data = await get_analytical_review_data(
                db, project_id, year, wp_code=code, scope=scope
            )
            sig = att = 0
            for sheet_key in ("bs_horizontal", "bs_vertical", "is_horizontal", "is_vertical"):
                for row in data.get(sheet_key, {}).get("rows", []):
                    st = row.get("status")
                    if st == "significant":
                        sig += 1
                    elif st == "attention":
                        att += 1
            lines.append(f"{code}：显著变动 {sig} 项，关注 {att} 项（{year} 年度报表）")
        except Exception as e:
            logger.warning("ch08 analytical_review %s 失败: %s", code, e)
            lines.append(await _wp_progress_line(db, project_id, code))

    if all("无底稿" in line for line in lines):
        return {
            "content": None,
            "source_label": None,
            "message": "项目内无 A1-13/A1-14 底稿",
        }
    return {"content": "\n".join(lines), "source_label": "A1-13+A1-14"}

async def _pull_ch09_related_party(db: AsyncSession, project_id: UUID) -> dict:
    summary = await get_workpaper_summary(db, project_id, "related_party")
    if not summary.get("ready"):
        return {
            "content": None,
            "source_label": None,
            "message": summary.get("reason", "A7-1 数据源未就绪"),
        }
    lines = [summary["summary_text"]]
    if await _get_wp_id(db, project_id, "A7"):
        lines.append("A7 程序表：已关联（请查阅 A7 执行结论）")
    return {
        "content": "\n".join(lines),
        "source_label": "A7+A7-1",
    }


async def _pull_ch10_going_concern(db: AsyncSession, project_id: UUID) -> dict:
    summary = await get_workpaper_summary(db, project_id, "going_concern")
    if not summary.get("ready"):
        return {
            "content": None,
            "source_label": None,
            "message": summary.get("reason", "A15-1 数据源未就绪"),
        }
    lines = [summary["summary_text"]]
    if await _get_wp_id(db, project_id, "A15"):
        lines.append("A15 程序表：已关联（请查阅 A15 裁剪与执行说明）")
    return {
        "content": "\n".join(lines),
        "source_label": "A15+A15-1",
    }


async def _pull_ch11_subsequent_events(db: AsyncSession, project_id: UUID) -> dict:
    """ch11: A11 程序表 + A11-1 期后事项底稿"""
    lines: list[str] = []
    if await _get_wp_id(db, project_id, "A11"):
        lines.append("A11 期后事项程序表：已关联")
    lines.append(await _wp_progress_line(db, project_id, "A11-1"))
    if not any("已关联" in line or "已填写" in line for line in lines):
        return {
            "content": None,
            "source_label": None,
            "message": "A11/A11-1 数据源未就绪",
        }
    return {"content": "\n".join(lines), "source_label": "A11+A11-1"}


async def _pull_ch12_kam(db: AsyncSession, project_id: UUID) -> dict:
    """ch12: 从 A17-2-1 拉取 KAM 条目摘要"""
    wp_id = await _get_wp_id(db, project_id, "A17-2-1")
    if wp_id is None:
        return {
            "content": None,
            "source_label": None,
            "message": "项目内无 A17-2-1 底稿",
        }

    result = await db.execute(
        text(
            """
            SELECT item_id, conclusion, remark
            FROM checklist_responses
            WHERE wp_id = :wp_id AND item_id LIKE 'A17-2-1-KAM%'
            ORDER BY item_id
            """
        ),
        {"wp_id": str(wp_id)},
    )
    rows = result.fetchall()
    if not rows:
        return {
            "content": None,
            "source_label": None,
            "message": "A17-2-1 尚无 KAM 条目，请先在 KAM 底稿中维护",
        }

    lines = [f"关键审计事项：{len(rows)} 条"]
    for row in rows[:12]:
        title = (row.conclusion or "").strip() or row.item_id.replace("A17-2-1-KAM-", "KAM-")
        lines.append(f"  - {title}")
    if len(rows) > 12:
        lines.append(f"  … 另有 {len(rows) - 12} 条未列出")
    return {"content": "\n".join(lines), "source_label": "A17-2-1"}


async def _pull_ch13_other_info(db: AsyncSession, project_id: UUID) -> dict:
    """ch13: A8-2 其他信息阅读进度（MVP：A8-1 弹窗填写计数）"""
    wp_id = await _get_wp_id(db, project_id, "A8-1")
    if wp_id is None:
        return {
            "content": None,
            "source_label": None,
            "message": "项目内无 A8-1 底稿",
        }
    filled, total = await _count_checklist_filled(db, wp_id)
    content = f"A8-1 其他信息阅读记录：已填写 {filled}/{total or '—'} 项\n（A8-2 详细底稿待接入）"
    return {
        "content": content,
        "source_label": "A8-1",
    }


async def _pull_ch14_audit_conclusion(db: AsyncSession, project_id: UUID) -> dict:
    """ch14: 审计报告意见类型 + A13 错报摘要"""
    lines: list[str] = []
    try:
        from app.models.report_models import AuditReport

        report_stmt = (
            select(AuditReport)
            .where(
                AuditReport.project_id == project_id,
                AuditReport.is_deleted == False,  # noqa: E712
            )
            .order_by(AuditReport.year.desc())
            .limit(1)
        )
        report_result = await db.execute(report_stmt)
        report = report_result.scalar_one_or_none()
        if report is None:
            lines.append("尚未创建审计报告（请在报告模块初始化）")
        else:
            opinion = report.opinion_type
            opinion_str = opinion.value if hasattr(opinion, "value") else str(opinion)
            lines.append(f"拟出具审计意见：{opinion_str}")
            lines.append(f"报告年度：{report.year}；状态：{report.status}")
    except Exception as e:
        logger.warning("ch14 audit_report 查询失败: %s", e)
        lines.append("审计报告：查询失败")

    mis = await get_workpaper_summary(db, project_id, "misstatement")
    if mis.get("ready"):
        lines.append(mis["summary_text"])
    else:
        lines.append("A13 错报摘要：暂无数据")

    return {"content": "\n".join(lines), "source_label": "audit_report+A13"}


async def _pull_ch15_special_matters(db: AsyncSession, project_id: UUID) -> dict:
    """ch15: 其他特殊考虑事项 — 舞弊线索(issue_hints) + A13错报 + A14缺陷计数"""
    lines: list[str] = []

    # ── 1. issue_hints 舞弊线索 ──
    try:
        hints = await get_issue_hints(db, project_id)
        fraud = hints.get("fraud", {})
        fraud_count = fraud.get("count", 0)
        if fraud_count > 0:
            titles = [item["title"] for item in fraud.get("items", [])]
            lines.append(f"舞弊相关问题单：{fraud_count} 条")
            for t in titles:
                lines.append(f"  - {t}")
        else:
            lines.append("舞弊相关问题单：0 条")
        lines.append("（仅标题关键词启发式，召回不完备，仅供提示）")
    except Exception as e:
        logger.warning("ch15 issue_hints 查询失败: %s", e)
        lines.append("舞弊相关问题单：查询失败")

    # ── 2. A13 未更正错报计数 ──
    try:
        from app.models.audit_platform_models import UnadjustedMisstatement
        from sqlalchemy import func as sa_func

        mis_stmt = (
            select(sa_func.count())
            .select_from(UnadjustedMisstatement)
            .where(
                UnadjustedMisstatement.project_id == project_id,
                UnadjustedMisstatement.is_deleted == False,  # noqa: E712
            )
        )
        mis_result = await db.execute(mis_stmt)
        mis_count = mis_result.scalar() or 0
        lines.append(f"A13 未更正错报：{mis_count} 项")
    except Exception as e:
        logger.warning("ch15 A13 错报计数失败: %s", e)
        lines.append("A13 未更正错报：数据源未就绪")

    # ── 3. A14 内控缺陷计数 ──
    try:
        from app.models.phase15_models import IssueTicket
        from sqlalchemy import func as sa_func2

        def_count_stmt = (
            select(sa_func2.count())
            .select_from(IssueTicket)
            .where(
                IssueTicket.project_id == project_id,
                IssueTicket.category == "internal_control",
            )
        )
        def_result = await db.execute(def_count_stmt)
        def_count = def_result.scalar() or 0
        lines.append(f"A14 内控缺陷：{def_count} 项")
    except Exception as e:
        logger.warning("ch15 A14 缺陷计数失败: %s", e)
        lines.append("A14 内控缺陷：数据源未就绪")

    content = "\n".join(lines)
    return {
        "content": content,
        "source_label": "issue_hints+A13+A14",
    }
