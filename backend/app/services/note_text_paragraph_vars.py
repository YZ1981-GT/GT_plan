"""Sprint A.4.3 — 附注段落变量自动收集器.

从多个来源汇集 Jinja 模板渲染所需的变量字典：

- Project ORM 字段（name / company_name / parent_company_name /
  template_type / year / consol_level / report_scope / etc.）
- ``Project.wizard_state.basic_info.data``（registration_authority /
  registered_capital / business_scope / list_date / list_exchange / etc.）
- 当前章节级 ``DisclosureNote.text_template_vars``（A.1.3 字段）
- consolidation 数据（subsidiary_count / parent_company / 简单子公司清单）
- prior_notes 摘要（cross-year 段落使用）
- 派生字段（``is_listed`` = (template_type == 'listed') / 当前 ``year``）

主要 API:
- ``async def collect_paragraph_vars(db, project_id, year, *, section_id=None,
   prior_notes_cache=None) -> dict``
- ``def merge_paragraph_vars(*sources: dict) -> dict``  # 纯函数版本，单测友好

收集顺序（覆盖优先级，后者覆盖前者）：
1. Project ORM 字段（最低优先级）
2. wizard_state.basic_info.data
3. consolidation 数据（subsidiary_count / parent_company）
4. prior_notes 摘要
5. 当前章节级 ``text_template_vars``（最高优先级，用户编辑过的会覆盖一切）

异常容忍：任何子源加载失败 → 跳过 + warning，不阻塞渲染。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 纯函数：合并优先级
# ---------------------------------------------------------------------------


def merge_paragraph_vars(*sources: dict[str, Any] | None) -> dict[str, Any]:
    """合并多个变量来源（后者覆盖前者，None / {} 跳过）.

    实现细节：
    - 浅合并（不递归 deep merge）
    - ``None`` 值会覆盖前面的非 None（语义上"显式置空"）；如果想跳过
      ``None``，请在传入前自行过滤
    - 输出新 dict，不修改入参
    """
    out: dict[str, Any] = {}
    for src in sources:
        if not src:
            continue
        out.update(src)
    return out


# ---------------------------------------------------------------------------
# 子源工具
# ---------------------------------------------------------------------------


_PROJECT_DIRECT_FIELDS = (
    "name",
    "client_name",
    "template_type",
    "report_scope",
    "parent_company_name",
    "ultimate_company_name",
    "consol_level",
    "scenario",
    "company_code",
)


def project_to_vars(project: Any) -> dict[str, Any]:
    """从 ``Project`` ORM 对象抽取常用基本变量.

    输出键：
    - ``project_name`` / ``client_name`` / ``company_name``（client_name 别名）
    - ``parent_company_name`` / ``ultimate_company_name``
    - ``template_type`` / ``is_listed``（派生）/ ``is_soe``（派生）
    - ``year`` 不来源于 project（wizard 不一定锁），由调用方覆盖
    - ``consol_level`` / ``scenario`` / ``report_scope`` / ``company_code``
    """
    if project is None:
        return {}
    out: dict[str, Any] = {}
    for field in _PROJECT_DIRECT_FIELDS:
        try:
            val = getattr(project, field, None)
        except Exception:  # pragma: no cover
            val = None
        if val is None:
            continue
        # 枚举 → 转字符串值
        out[field] = getattr(val, "value", val)

    # 友好别名
    if "name" in out:
        out["project_name"] = out["name"]
    if "client_name" in out:
        out.setdefault("company_name", out["client_name"])

    # 派生字段
    template_type = out.get("template_type")
    if template_type is not None:
        out["is_listed"] = template_type == "listed"
        out["is_soe"] = template_type == "soe"
    return out


def basic_info_to_vars(wizard_state: dict | None) -> dict[str, Any]:
    """从 ``project.wizard_state`` 抽取 basic_info.data（双 fallback path）.

    - ``state.steps.basic_info.data`` (新 schema)
    - ``state.basic_info.data``       (旧 schema)
    """
    state = wizard_state or {}
    if not isinstance(state, dict):
        return {}
    nested = state.get("steps")
    if isinstance(nested, dict):
        candidate = nested.get("basic_info", {})
        if isinstance(candidate, dict):
            data = candidate.get("data")
            if isinstance(data, dict):
                return dict(data)
    flat = state.get("basic_info", {})
    if isinstance(flat, dict):
        data = flat.get("data")
        if isinstance(data, dict):
            return dict(data)
    return {}


# ---------------------------------------------------------------------------
# 集团 / 合并：subsidiaries
# ---------------------------------------------------------------------------


async def _load_consolidation_vars(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> dict[str, Any]:
    """从 ``consol_scope`` 加载子公司清单 / 数量.

    输出键：
    - ``subsidiary_count`` 包含在合并范围内的子公司数（int）
    - ``subsidiaries`` 简化清单 ``[{"name", "company_code", "ownership_ratio"}]``
    - ``has_consolidation`` bool

    任意异常都吞掉，返回 ``{}``。
    """
    try:
        from app.models.consolidation_models import ConsolScope
    except Exception:  # pragma: no cover - defensive
        return {}
    try:
        result = await db.execute(
            sa.select(ConsolScope).where(
                ConsolScope.project_id == project_id,
                ConsolScope.year == year,
                ConsolScope.is_included == sa.true(),
                ConsolScope.is_deleted == sa.false(),
            )
        )
        rows = result.scalars().all()
    except Exception as exc:  # pragma: no cover - DB failures tolerated
        logger.warning("collect_paragraph_vars: load consol_scope failed: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass
        return {}
    if not rows:
        return {"subsidiary_count": 0, "subsidiaries": [], "has_consolidation": False}
    subs: list[dict[str, Any]] = []
    for r in rows:
        subs.append(
            {
                "name": r.company_name,
                "company_code": r.company_code,
                "ownership_ratio": (
                    float(r.ownership_ratio) if r.ownership_ratio is not None else None
                ),
            }
        )
    return {
        "subsidiary_count": len(subs),
        "subsidiaries": subs,
        "has_consolidation": True,
    }


# ---------------------------------------------------------------------------
# 顶层：collect
# ---------------------------------------------------------------------------


async def collect_paragraph_vars(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    section_id: str | None = None,
    section_text_template_vars: dict | None = None,
    prior_notes_cache: dict[str, str] | None = None,
) -> dict[str, Any]:
    """收集渲染附注段落所需的全部变量.

    Args:
        db: AsyncSession
        project_id: 项目 ID
        year: 报告年度（覆盖 project 中可能的过期值）
        section_id: 当前章节 ``section_id``，可选。如果给出会优先尝试加载
            该章节的 ``text_template_vars`` （DisclosureNote 上的字段）。
        section_text_template_vars: 直接传入的章节级覆盖（最高优先级，
            优先于 DB 查询，单测 / 渲染前预览场景）
        prior_notes_cache: 上年附注 text_content 字典（避免重复查询）。
            若给出会派生 ``has_prior_notes`` / ``prior_notes_count``。

    Returns:
        合并后的变量字典，包含：
        - 基本字段（project_name / company_name / template_type / is_listed / ...）
        - basic_info.data（registration_authority / list_date / ...）
        - consolidation（subsidiary_count / subsidiaries）
        - prior 摘要（has_prior_notes / prior_notes_count）
        - 当前章节级覆盖
        - ``year``（报告年度）
    """
    # 1) 加载 Project（基本字段 + wizard_state）
    project_vars: dict[str, Any] = {}
    wizard_vars: dict[str, Any] = {}
    section_vars_db: dict[str, Any] = {}
    try:
        from app.models.core import Project

        result = await db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        project = result.scalar_one_or_none()
        if project is not None:
            project_vars = project_to_vars(project)
            wizard_vars = basic_info_to_vars(project.wizard_state)
    except Exception as exc:  # pragma: no cover
        logger.warning("collect_paragraph_vars: load project failed: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass

    # 2) 章节级 text_template_vars（DB）
    if section_id and section_text_template_vars is None:
        try:
            from app.models.report_models import DisclosureNote

            res = await db.execute(
                sa.select(DisclosureNote.text_template_vars).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.section_id == section_id,
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
            row = res.first()
            if row is not None and isinstance(row[0], dict):
                section_vars_db = dict(row[0])
        except Exception as exc:  # pragma: no cover
            logger.warning("collect_paragraph_vars: load section vars failed: %s", exc)
            try:
                await db.rollback()
            except Exception:
                pass

    # 3) 合并基线
    consol_vars = await _load_consolidation_vars(db, project_id, year)

    # 4) prior summary
    prior_vars: dict[str, Any] = {}
    if prior_notes_cache is not None:
        prior_vars["has_prior_notes"] = bool(prior_notes_cache)
        prior_vars["prior_notes_count"] = len(prior_notes_cache)

    # 5) year（最终保证 year 来自调用方 / not Project）
    year_vars = {"year": year, "report_year": year}

    # 优先级（后者覆盖前者）：
    #   project_vars  <  wizard_vars  <  consol_vars  <  prior_vars
    #     <  year_vars  <  section_vars_db  <  section_text_template_vars (param)
    return merge_paragraph_vars(
        project_vars,
        wizard_vars,
        consol_vars,
        prior_vars,
        year_vars,
        section_vars_db,
        section_text_template_vars or {},
    )
