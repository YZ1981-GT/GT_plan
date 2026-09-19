"""母公司附注章节判定与取数上下文切换（Task 12 / 13）。

本模块把「某个附注章节是不是母公司章」以及「母公司章该从哪个项目取数」收敛成
单一入口，供 ``disclosure_engine`` 在构造 resolver ``ctx`` 时调用。

判定真源
--------
``backend/data/note_template_variant_matrix.json`` 的顶层 additive 字段
``parent_company_sections: {listed?, soe?}``（Task 10 落地）。**不新增变体键**、
不读模板 JSON 的章节树 —— 章节树里母公司子节的 ``section_number`` 就是该字段的取值，
两者由 ``test_variant_matrix.py`` 交叉锁死。

取数口径
--------
母公司章的数字来自**同企业代码、同年度、``report_scope='standalone'`` 的兄弟项目**
（母公司单体），经 ``parent_company_scope.resolve_parent_standalone_project`` 定位。
与报表侧「公司（母公司个别）」列**共用同一 helper**，两个交付件的母公司数不会打架。

🔴 四条实现约定（勿"优化"掉）
---------------------------
1. **不新建取数管道**。母公司章仍走既有 ``_build_with_binding`` → 7 个
   ``SOURCE_RESOLVERS``，只把 ctx 里的 ``project_id`` 与 ``_tb_cache`` 换成母公司
   单体项目的。需求 8.2 的字面要求即此。
2. **兄弟项目缺失 → 金额 None 而非 0**（需求 8.4）。做法是把 ``_tb_cache`` 换成
   **空 dict** —— ``resolve_trial_balance`` 在缓存为空时 ``return None``，天然产出
   None；而「留用合并项目的缓存」会让母公司章显示合并数（比 0 更坏，是**错数**）。
3. **章节号按 md 截断值逐字比对**。listed 侧「投资收益」的 section_number 实测是
   ``十六、投资收益（注：以``（md 重建 10 字符截断），soe 侧「现金流量表补充资料」是
   ``十二、现金流量表补充资``。matrix 里存的就是截断值 ⇒ 直接相等比对即可，
   **禁做前缀/包含匹配**（``十二、投资收益`` 是另一个子节，包含匹配会串章）。
4. **判定默认走两版并集**（``template_type=None``）。实测两版母公司章节号前缀互斥
   （listed 全部 ``十六、`` / soe 全部 ``十二、``）且集合**交集为空**，故并集判定
   无歧义；调用方拿不到 ``template_type`` 时（``_build_with_binding`` 只有
   ``section_number``）不必再查一次项目。守卫按「交集为空」锁死该前提 —— 一旦两版
   出现同名章节号，守卫打红提醒调用方必须显式传 ``template_type``。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.note_section_catalog import (
    normalize_report_scope,
    normalize_template_type,
)
from app.services.parent_company_scope import resolve_parent_standalone_project

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_MATRIX_PATH = _DATA_DIR / "note_template_variant_matrix.json"

#: matrix 顶层 additive 字段名（与 Task 10 的幂等脚本 / 守卫共用同一字面量）
PARENT_SECTIONS_FIELD = "parent_company_sections"

#: 母公司取数溯源在 resolver ctx / 载荷里的键（Task 13，前端溯源面板消费）
PARENT_SOURCE_META_KEY = "_parent_company_source"

#: 「本项目未建母公司单体」标记键（需求 8.4：金额留 None + 显式标记缺失）
PARENT_PROJECT_MISSING_KEY = "parent_project_missing"

#: 溯源载荷的三个必备键（需求 8.5 逐字对应；守卫按此断言键集完备）
PARENT_SOURCE_META_KEYS: tuple[str, ...] = (
    "source_project_name",
    "source_company_code",
    "source_scope",
)

__all__ = [
    "PARENT_SECTIONS_FIELD",
    "PARENT_SOURCE_META_KEY",
    "PARENT_PROJECT_MISSING_KEY",
    "PARENT_SOURCE_META_KEYS",
    "ParentCompanySource",
    "ParentScopeCache",
    "build_parent_source_meta",
    "is_parent_company_section",
    "load_parent_company_sections",
    "parent_source_payload",
    "resolve_parent_company_source",
    "resolve_parent_scope_for_notes",
]


@lru_cache(maxsize=1)
def load_parent_company_sections() -> dict[str, frozenset[str]]:
    """按变体返回母公司章节号集合 ``{"listed": {...}, "soe": {...}}``。

    读不到 / 结构异常 → 返回两个空集合（母公司章判定退化为「都不是」，
    取数走原合并项目路径 = 零回归），并记 WARNING。**不抛异常**：附注生成是
    交付件路径，判据文件缺失不应让整份附注生成失败。
    """
    empty: dict[str, frozenset[str]] = {"listed": frozenset(), "soe": frozenset()}
    try:
        raw = json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))
    except Exception as err:  # pragma: no cover - defensive
        logger.warning(
            "母公司章判据加载失败（%s）：%s；母公司章取数退化为合并项目口径",
            _MATRIX_PATH,
            err,
        )
        return empty

    out: dict[str, set[str]] = {"listed": set(), "soe": set()}
    for account in raw.get("accounts") or []:
        if not isinstance(account, dict):
            continue
        sections = account.get(PARENT_SECTIONS_FIELD)
        if not isinstance(sections, dict):
            continue
        for variant in ("listed", "soe"):
            code = sections.get(variant)
            if isinstance(code, str) and code.strip():
                out[variant].add(code.strip())
    return {k: frozenset(v) for k, v in out.items()}


def is_parent_company_section(
    note_section: str | None, template_type: str | None = None
) -> bool:
    """该章节号是否属母公司章。

    比对**逐字相等**（章节号可能是 md 截断值，见模块 docstring 约定 3）。

    ``template_type`` 缺省时走两版**并集**（约定 4：两版集合交集为空，无歧义）。
    显式传入时只查该变体，供需要严格区分的调用方使用。
    """
    code = (note_section or "").strip()
    if not code:
        return False
    sections = load_parent_company_sections()
    if template_type is None:
        return any(code in codes for codes in sections.values())
    variant = normalize_template_type(template_type)
    return code in sections.get(variant, frozenset())


@dataclass(frozen=True)
class ParentCompanySource:
    """母公司章取数来源。

    Attributes:
        project_id: 母公司单体项目 id；``None`` = 未定位到（合法状态）。
        project_name: 来源项目名（溯源展示用）。
        company_code: 来源项目企业代码。
        missing: ``True`` 表示本项目未建母公司单体 ⇒ 金额须留 None 不填 0。
    """

    project_id: UUID | None
    project_name: str | None
    company_code: str | None
    missing: bool

    @property
    def scope(self) -> str:
        """来源口径。定位成功恒为 ``standalone``（母公司单体）。"""
        return "standalone"


@dataclass(frozen=True)
class ParentScopeCache:
    """一次母公司口径解析的结果（供 engine 按 ``(project_id, year)`` 缓存）。

    Attributes:
        project_id: 发起解析的项目（通常是合并项目）。
        year: 附注会计年度。
        is_consolidated: 该项目是否为合并口径。``False`` 时母公司章不做切换
            （母公司章 ``scope='consolidated_only'``，单体项目本不该出现它）。
        source: 取数来源。``is_consolidated=False`` 时恒为 ``missing=True``。
        resolution_failed: 口径**解析本身失败**（项目读不到 / DB 异常）。

    🔴 ``resolution_failed`` 与 ``is_consolidated=False`` 必须是两态，不能合并 ——
    前者是「不知道该取哪个项目」⇒ 调用方必须**留空**；后者是「确定不是合并项目」⇒
    按原路径取数不改行为。两者都返 ``is_consolidated=False`` 会让 DB 抖动时母公司章
    静默显示**合并口径金额**（错数，比取不到更坏）。守卫
    ``test_parent_company_note_sourcing`` 有该分支的专项断言。
    """

    project_id: UUID
    year: int
    is_consolidated: bool
    source: ParentCompanySource
    resolution_failed: bool = False

    def matches(self, project_id: UUID, year: int) -> bool:
        """该缓存是否适用于给定 ``(project_id, year)``。"""
        return self.project_id == project_id and self.year == year

    @property
    def parent_project_id(self) -> UUID | None:
        """母公司单体项目 id；``None`` = 未定位到（调用方须留空不填 0）。"""
        return self.source.project_id


async def resolve_parent_company_source(
    db: AsyncSession, project: Project | None
) -> ParentCompanySource:
    """定位母公司章的取数来源项目。

    非合并项目 / 无兄弟项目 / 定位异常一律返回 ``missing=True`` 的结果 ——
    调用方据此把金额留 None（需求 8.4），**不得回落到合并项目自身**。

    与 ``parent_company_scope`` 的分工：helper 本身不 fail-open（异常原样抛出，
    避免「接线错」被伪装成「无母公司单体」）；本层是附注生成路径，故在此兜住异常
    并记 WARNING —— 但兜住后的处置是「留空」而非「用合并数」，错数风险为零。
    """
    if project is None:
        return ParentCompanySource(None, None, None, True)
    try:
        parent = await resolve_parent_standalone_project(db, project)
    except Exception as err:  # pragma: no cover - defensive
        logger.warning(
            "母公司章取数来源定位失败（project=%s）：%s；该章金额留空",
            getattr(project, "id", None),
            err,
        )
        return ParentCompanySource(None, None, None, True)

    if parent is None:
        logger.info(
            "母公司章取数来源缺失：项目 %s 未建母公司单体（同代码同年度 standalone 兄弟），"
            "该章金额留空不填 0",
            getattr(project, "id", None),
        )
        return ParentCompanySource(None, None, None, True)

    return ParentCompanySource(
        project_id=parent.id,
        project_name=getattr(parent, "name", None),
        company_code=getattr(parent, "company_code", None),
        missing=False,
    )


async def resolve_parent_scope_for_notes(
    db: AsyncSession, project_id: UUID, year: int
) -> ParentScopeCache:
    """按项目 id 解析母公司口径（附注取数入口）。

    先读项目本体判断是否合并口径 —— 非合并直接短路（**不查兄弟项目**，零额外查询），
    合并才经共享 helper 定位同代码 standalone 兄弟。

    定位字段不齐 / 项目不存在 / 查询异常 → ``is_consolidated=False`` +
    ``missing=True``，调用方按原路径取数或留空，绝不回落合并数当母公司数。
    """
    import sqlalchemy as sa

    missing = ParentCompanySource(None, None, None, True)
    try:
        result = await db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        project = result.scalar_one_or_none()
    except Exception as err:  # pragma: no cover - defensive
        logger.warning(
            "母公司口径解析：读取项目 %s 失败：%s；母公司章取数留空",
            project_id,
            err,
        )
        return ParentScopeCache(
            project_id, year, False, missing, resolution_failed=True
        )

    if project is None:
        logger.warning(
            "母公司口径解析：项目 %s 不存在或已软删；母公司章取数留空",
            project_id,
        )
        return ParentScopeCache(
            project_id, year, False, missing, resolution_failed=True
        )

    if normalize_report_scope(project.report_scope) != "consolidated":
        return ParentScopeCache(project_id, year, False, missing)

    source = await resolve_parent_company_source(db, project)
    return ParentScopeCache(project_id, year, True, source)


def parent_source_payload(source: ParentCompanySource) -> dict[str, Any]:
    """Task 13：母公司取数溯源载荷（三项 + 缺失标记）。

    键名与需求 8.5 逐字对应：``source_project_name`` / ``source_company_code`` /
    ``source_scope``；缺失时另带 ``parent_project_missing: true`` 供前端显示
    「本项目未建母公司单体」灰态，且 ``source_scope`` 置 ``None``（没有来源就
    没有来源口径，写死 ``standalone`` 会让前端误以为已定位到项目）。
    """
    payload: dict[str, Any] = {
        "source_project_name": source.project_name,
        "source_company_code": source.company_code,
        "source_scope": source.scope,
    }
    if source.missing:
        payload[PARENT_PROJECT_MISSING_KEY] = True
        payload["source_scope"] = None
    return payload


def build_parent_source_meta(scope: ParentScopeCache) -> dict[str, Any]:
    """从 ``ParentScopeCache`` 构造溯源载荷（``parent_source_payload`` 的薄壳）。"""
    return parent_source_payload(scope.source)
