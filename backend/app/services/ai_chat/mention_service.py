"""Mention 聚合搜索与授权加载服务（Task 14）

Feature: dsh-agent-panel-integration
Requirements:
  - 5.2：服务端单一 MentionType schema 覆盖 7 类（复用 MENTION_RESOURCE_TYPES）
  - 5.3：GET /api/ai-chat/mentionable 在 ResourceAccessResolver 后统一返回
  - 5.5：label 与正文由服务端授权后加载，客户端 assertion 不可信
  - 5.6：搜索失败/超时/能力不可用与成功空结果使用不同状态
  - 5.7：mention 搜索、直接 ID 加载使用同一授权决策
  - 5.8：全宿主迁移后删除 extra_scopes 字段、旧 URL 和旧消费方
  - 5.9：jump route 点击仍由目标页面重新授权
Design: "Components and Interfaces → 7. Mention 聚合搜索"

单一入口：``MentionSearchService.search()`` —— 聚合七类资源，统一经
``ResourceAccessResolver.filter_visible_resources()`` 过滤后返回。

``load_mention_context()`` —— 加载已授权 mention 的正文用于 ContextBuilder。
"""

from __future__ import annotations

import asyncio
import enum
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.contracts import (
    REPORT_HOST_IDS,
    AccessDecision,
    AiChatAction,
    HostRef,
    HostType,
    ResourceType,
)
from app.services.ai_chat.host_context import (
    REPORT_LABELS,
    AuthorizedHostContext,
)

logger = logging.getLogger(__name__)

__all__ = [
    "MentionCandidate",
    "MentionSearchResult",
    "MentionSearchService",
    "MentionContentItem",
    "MentionTypeStatus",
    "PROJECT_REQUIRED_MENTION_TYPES",
    "load_mention_context",
]


class MentionTypeStatus(str, enum.Enum):
    """单个资源类型的搜索状态（Req 5.6：失败/超时/能力不可用与成功空结果必须可区分）。

    前端 ``useAiMention.TypeSearchStatus`` 镜像本枚举取值，由 vitest 对账。

    ``project_required`` 是"当前宿主没有项目绑定，该类型压根搜不了"，与
    ``empty``（真的搜了、没匹配）语义完全不同 —— 混用会让审计师在受限全局知识模式下
    看到"无匹配结果"，误以为库里没有底稿/附注/报表。
    """

    success = "success"
    empty = "empty"
    error = "error"
    unavailable = "unavailable"
    timeout = "timeout"
    project_required = "project_required"


#: 地址坐标 mention 展示哪些域，以及"一张表"由 ``AddressEntry`` 的哪些字段确定。
#:
#: 🔴 **表级而非单元格级**：地址目录本身登记到单元格（"资产负债表 > 存货 > 期末"），
#: 但 AI 拿到整张表就能自己做分析，让审计师去挑单元格既啰嗦、又会因为同一坐标在
#: 多个来源重复登记而列出好几条一模一样的候选。因此这里把 ``cell`` 维度**聚合掉**：
#: 候选 = 表（uri 去掉 ``#cell``），正文 = 该表全部列的当前值。
#:
#: 🔴 **只登记 tb / aux 两域**：``report`` / ``note`` / ``wp`` 的表级引用已经由
#: 「报表」「附注」「底稿」三个 mention 类型提供（同名、同粒度），再列一遍会让
#: 同一张资产负债表在候选里出现两次。四表数据（试算表 / 辅助余额）没有任何其他
#: mention 类型能引用 —— 这才是地址坐标域独有的价值。
#: 要把某个域加回来，在此登记一行即可（值 = 构成一张表的字段名元组）。
_ADDRESS_MENTION_DOMAINS: dict[str, tuple[str, ...]] = {
    "tb": ("source",),          # tb://1001            一个科目的全部列
    "aux": ("source", "path"),  # aux://1001/成本中心   科目 × 辅助维度
}

#: 地址 label 的层级分隔符（``address_registry`` 各 build_*_entries 的统一约定）。
_ADDRESS_LABEL_SEP = " > "

#: 表级正文里单表最多纳入的辅助维度行数（超出由 token 预算再裁剪）。
_AUX_ROW_LIMIT = 60

#: ``trial_balance`` 列 → 中文展示名（给 AI 看的表格正文，不是公式列名体系）。
#:
#: 与 ``formula_engine.COLUMN_ALIASES`` 不同层：那张表是"公式里可以写哪些列名"
#: （中文 → 规范字段名），这里是"把这一行试算表数据念给模型听"。
_TB_CONTENT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("opening_balance", "期初余额"),
    ("unadjusted_amount", "未审数"),
    ("aje_adjustment", "AJE调整"),
    ("rje_adjustment", "RJE调整"),
    ("audited_amount", "审定数"),
)


def _table_level_label(cell_label: str) -> str:
    """单元格级 label → 表级 label（去掉最后一段列名）。

    各域 ``build_*_entries`` 的 label 约定都是 ``表 > 对象 > … > 列``
    （如 ``试算表 > 1001 库存现金 > 审定数``），因此去掉末段即表级名称 ——
    不在此重拼一份命名逻辑，避免与 registry 的命名漂移。
    """
    parts = [p.strip() for p in cell_label.split(_ADDRESS_LABEL_SEP) if p.strip()]
    if len(parts) <= 1:
        return cell_label.strip()
    return _ADDRESS_LABEL_SEP.join(parts[:-1])


def _address_sublabel(columns: list[str]) -> str:
    """表级候选的副标签：告诉审计师这张表有哪些列可用。"""
    if not columns:
        return "数据表"
    preview = "、".join(columns[:3])
    suffix = "…" if len(columns) > 3 else ""
    return f"{len(columns)} 列：{preview}{suffix}"


#: 必须有项目绑定才能搜索的资源类型（无绑定时报 ``project_required``，不谎报"没搜到"）。
#:
#: 知识文档/知识库**不在**此列：知识资产可跨项目共享，无项目绑定时按
#: ``KnowledgeAccessPolicy`` 判权后仍可引用。
PROJECT_REQUIRED_MENTION_TYPES: frozenset[ResourceType] = frozenset(
    {
        ResourceType.workpaper,
        ResourceType.note,
        ResourceType.report,
        ResourceType.address,
    }
)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MentionCandidate:
    """单条 mention 搜索结果（Req 5.3 统一响应形状）。

    前端可直接序列化为 ``{type, id, label, sublabel, jump_route}``。
    ``jump_route`` 是前端路由路径，点击后由目标页面重新鉴权（Req 5.9）。
    """

    type: str
    id: str
    label: str
    sublabel: str = ""
    jump_route: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "type": self.type,
            "id": self.id,
            "label": self.label,
            "sublabel": self.sublabel,
            "jump_route": self.jump_route,
        }


@dataclass
class MentionSearchResult:
    """聚合搜索结果（含状态信号，Req 5.6）。"""

    items: list[MentionCandidate] = field(default_factory=list)
    #: 各类型的搜索状态；取值域真源 = ``MentionTypeStatus``
    type_status: dict[str, str] = field(default_factory=dict)
    total_before_filter: int = 0


@dataclass(frozen=True)
class MentionContentItem:
    """加载后的 mention 正文条目（供 ContextBuilder 消费）。"""

    type: str
    id: str
    label: str
    content: str
    token_estimate: int = 0
    #: 授权决策（保留以供 manifest 记录 cycle_scope 裁剪）
    status: str = "included"  # included / trimmed / denied / unavailable


# ---------------------------------------------------------------------------
# 搜索配置
# ---------------------------------------------------------------------------

#: 每类资源搜索结果数上限
_PER_TYPE_LIMIT = 10
#: 并行搜索超时（秒）
_SEARCH_TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# 资源类型 → 搜索/加载策略
# ---------------------------------------------------------------------------


class MentionSearchService:
    """Mention 聚合搜索唯一入口。

    所有搜索结果**先**经 ``ResourceAccessResolver.filter_visible_resources()``
    过滤，再返回 label / jump_route 等展示字段（Req 5.5 / 5.7）。
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._resolver = ResourceAccessResolver(db)

    async def search(
        self,
        *,
        user: Any,
        host: AuthorizedHostContext,
        query: str,
        type_filter: str | None = None,
        limit: int = _PER_TYPE_LIMIT,
    ) -> MentionSearchResult:
        """执行多类型聚合搜索。

        Args:
            user: 当前用户
            host: 已授权宿主上下文
            query: 搜索关键词
            type_filter: 可选的单一类型过滤（前端选了某个 tab 时使用）
            limit: 每类最大返回数
        """
        # 构造 host AccessDecision 供 filter_visible_resources 使用
        host_decision = AccessDecision(
            allowed=True,
            principal_id=host.principal_id,
            project_id=host.project_id,
            cycle_scope=host.cycle_scope,
            allowed_actions=host.allowed_actions,
            scope_unbounded=host.scope_unbounded,
        )

        # 确定要搜索的类型
        from app.services.ai_chat.run_contract import MENTION_RESOURCE_TYPES

        target_types: list[ResourceType]
        if type_filter:
            try:
                rt = ResourceType(type_filter)
                if rt not in MENTION_RESOURCE_TYPES:
                    return MentionSearchResult(
                        type_status={type_filter: MentionTypeStatus.unavailable.value}
                    )
                target_types = [rt]
            except ValueError:
                return MentionSearchResult(
                    type_status={type_filter: MentionTypeStatus.unavailable.value}
                )
        else:
            target_types = sorted(MENTION_RESOURCE_TYPES, key=lambda t: t.value)

        result = MentionSearchResult()

        # 无项目绑定时，项目类资源压根无法搜索 ⇒ 报 project_required 而非 empty。
        # 受限全局知识模式（host.project_id is None）下四类项目资源本就取不到，
        # 把它当"没匹配"会让用户以为库里没有底稿/附注/报表（Req 5.6）。
        searchable: list[ResourceType] = []
        for rt in target_types:
            if host_decision.project_id is None and rt in PROJECT_REQUIRED_MENTION_TYPES:
                result.type_status[rt.value] = MentionTypeStatus.project_required.value
            else:
                searchable.append(rt)

        if not searchable:
            return result

        # 并行搜索各类型
        #
        # ``host.year`` 必须一路传到地址坐标搜索：``build_trial_balance_entries`` /
        # ``build_aux_entries`` 都按 ``year`` 过滤业务表，此前这里写死 0 ⇒
        # **试算表与辅助余额两域恒空**，地址坐标候选里只剩不按年度过滤的 report 域。
        tasks = [
            self._search_type(user, host_decision, rt, query, limit, host.year)
            for rt in searchable
        ]

        try:
            outcomes = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=_SEARCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            # 全局超时：已完成的结果保留，未完成标 timeout
            for rt in searchable:
                if rt.value not in result.type_status:
                    result.type_status[rt.value] = MentionTypeStatus.timeout.value
            return result

        for rt, outcome in zip(searchable, outcomes):
            if isinstance(outcome, Exception):
                # 🔴 ERROR 而非 WARNING：这里唯一会捕到的就是接线错误（字段名/表名写错、
                # 签名不匹配），历史上 4 个类型因此长期恒 error 却只留 WARNING 无人发现。
                logger.error(
                    "mention 搜索 %s 类型失败（接线错误优先排查字段名）: %s: %s",
                    rt.value, type(outcome).__name__, outcome,
                    exc_info=outcome,
                )
                result.type_status[rt.value] = MentionTypeStatus.error.value
            elif isinstance(outcome, list):
                result.items.extend(outcome)
                result.type_status[rt.value] = (
                    MentionTypeStatus.success.value
                    if outcome
                    else MentionTypeStatus.empty.value
                )
            else:
                result.type_status[rt.value] = MentionTypeStatus.empty.value

        result.total_before_filter = len(result.items)
        return result

    # ------------------------------------------------------------------
    # 内部：按类型搜索
    # ------------------------------------------------------------------

    async def _search_type(
        self,
        user: Any,
        host_decision: AccessDecision,
        resource_type: ResourceType,
        query: str,
        limit: int,
        year: int | None = None,
    ) -> list[MentionCandidate]:
        """搜索单一资源类型并过滤可见性。"""
        # ① 原始搜索（不含权限，只查 label/ID）
        raw_candidates = await self._raw_search(
            resource_type, query, limit, host_decision, year
        )
        if not raw_candidates:
            return []

        # ② 授权过滤（Req 5.7：与直接 ID 访问同一判定）
        visible_ids = await self._resolver.filter_visible_resources(
            user, host_decision, resource_type,
            [c.id for c in raw_candidates],
            AiChatAction.search,
        )
        visible_set = set(visible_ids)

        # ③ 只返回可见的（Req 2.5：不泄露存在性）
        return [c for c in raw_candidates if c.id in visible_set]

    async def _raw_search(
        self,
        resource_type: ResourceType,
        query: str,
        limit: int,
        host_decision: AccessDecision,
        year: int | None = None,
    ) -> list[MentionCandidate]:
        """按资源类型执行原始搜索（无权限过滤）。

        每种资源类型使用对应业务表的 ILIKE 搜索。
        """
        q = f"%{query}%" if query else "%"
        project_id = host_decision.project_id

        if resource_type is ResourceType.workpaper:
            return await self._search_workpapers(q, project_id, limit)
        elif resource_type is ResourceType.note:
            return await self._search_notes(q, project_id, limit)
        elif resource_type is ResourceType.report:
            return await self._search_reports(q, project_id, limit)
        elif resource_type is ResourceType.knowledge_doc:
            return await self._search_knowledge_docs(q, project_id, limit)
        elif resource_type is ResourceType.knowledge_folder:
            return await self._search_knowledge_folders(q, project_id, limit)
        elif resource_type is ResourceType.address:
            return await self._search_address(q, project_id, limit, year)
        elif resource_type is ResourceType.attachment:
            # 附件不作为 mentionable 搜索项（已通过 MENTION_RESOURCE_TYPES 排除）
            return []
        return []

    # ------------------------------------------------------------------
    # 各类型搜索实现
    # ------------------------------------------------------------------

    async def _search_workpapers(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """底稿搜索：wp_name / wp_code ILIKE。"""
        from app.models.workpaper_models import WorkingPaper, WpIndex

        if project_id is None:
            return []

        stmt = (
            sa.select(
                WorkingPaper.id,
                WpIndex.wp_code,
                WpIndex.wp_name,
            )
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
                sa.or_(
                    WpIndex.wp_name.ilike(pattern),
                    WpIndex.wp_code.ilike(pattern),
                ),
            )
            .limit(limit)
        )
        rows = (await self._db.execute(stmt)).all()
        return [
            MentionCandidate(
                type=ResourceType.workpaper.value,
                id=str(r.id),
                label=r.wp_name or r.wp_code or "",
                sublabel=r.wp_code or "",
                jump_route=f"/workpapers/{r.id}",
            )
            for r in rows
            if r.id is not None
        ]

    async def _search_notes(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """附注搜索：``section_title`` / ``note_section`` ILIKE。

        章节号字段是 ``note_section``（``section_number`` 在 ``DisclosureNote`` 上不存在，
        旧代码引用它使本类型恒抛 AttributeError）。label 形态与
        ``host_context._label_note`` 保持一致，审计师在两处看到同一个名字。
        """
        from app.models.report_models import DisclosureNote

        if project_id is None:
            return []

        stmt = (
            sa.select(
                DisclosureNote.id,
                DisclosureNote.section_title,
                DisclosureNote.note_section,
            )
            .where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.is_deleted == sa.false(),
                sa.or_(
                    DisclosureNote.section_title.ilike(pattern),
                    DisclosureNote.note_section.ilike(pattern),
                ),
            )
            .order_by(DisclosureNote.sort_index, DisclosureNote.note_section)
            .limit(limit)
        )
        rows = (await self._db.execute(stmt)).all()
        return [
            MentionCandidate(
                type=ResourceType.note.value,
                id=str(r.id),
                label=r.section_title or r.note_section or "",
                sublabel=f"附注 {r.note_section}" if r.note_section else "附注",
                jump_route=f"/disclosure-notes/{r.id}",
            )
            for r in rows
            if r.id is not None
        ]

    async def _search_reports(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """报表搜索：候选 = 六张固定报表，按中文名匹配。

        ``financial_report`` 是**行级**表（每行一个 ``row_code`` / ``row_name``），既没有
        "报表实例"行，也没有 ``report_name`` 列 —— 旧代码引用它使本类型恒抛 AttributeError，
        而且即便字段名改对，按 ``row_name`` ILIKE 也会为同一张报表返回几十条重复候选。

        因此候选集来自枚举真源 ``REPORT_HOST_IDS`` + 中文名真源 ``REPORT_LABELS``，
        再用实际行数据校验该 ``(project, report_type)`` **已生成**：未生成的报表不进候选，
        避免用户引用一张空表（与 ``host_context._locate_report`` 的实例化校验同一语义）。

        行级引用（"资产负债表 > 存货 > 期末"）由地址坐标域提供，两者不重叠。
        """
        from app.models.report_models import FinancialReport

        if project_id is None:
            return []

        # 该项目下已生成的报表类型及其最新年度（报表实例由 project+year+type 确定）
        rows = (
            await self._db.execute(
                sa.select(
                    FinancialReport.report_type,
                    sa.func.max(FinancialReport.year).label("latest_year"),
                )
                .where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.is_deleted == sa.false(),
                )
                .group_by(FinancialReport.report_type)
            )
        ).all()
        latest_year_by_type = {r.report_type: r.latest_year for r in rows}

        # pattern 是 `%kw%` 形态（空 query 时为 `%`）；剥回关键词做中文名匹配
        keyword = pattern.strip("%").strip().lower()

        out: list[MentionCandidate] = []
        for report_type in sorted(REPORT_HOST_IDS):
            if report_type not in latest_year_by_type:
                continue  # 未生成 ⇒ 不进候选
            label = REPORT_LABELS.get(report_type, report_type)
            if keyword and keyword not in label.lower() and keyword not in report_type.lower():
                continue
            year = latest_year_by_type[report_type]
            out.append(
                MentionCandidate(
                    type=ResourceType.report.value,
                    id=report_type,
                    label=label,
                    sublabel=f"{year} 年度报表" if year else "财务报表",
                    jump_route=f"/reports/{report_type}",
                )
            )
            if len(out) >= limit:
                break
        return out

    async def _search_knowledge_docs(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """知识文档搜索：``name`` ILIKE（文档名字段是 ``name``，不是 ``title``）。

        **不按项目过滤**（``project_id`` 参数因此未使用，仅为 ``_raw_search`` 统一签名保留）：

        - 模型上没有 ``project_id``，只有 ``project_ids``（JSONB，仅当
          ``access_level='project_group'`` 时才限定可见项目）。旧代码引用
          ``KnowledgeDocument.project_id`` 使本类型恒抛 AttributeError。
        - 即便改成按 ``project_ids`` 过滤也是错的：``access_level='public'`` 的公共知识
          文档 ``project_ids`` 为 NULL，会被整体排除，而它们本应全所可引用。

        可见性判定唯一走 ``filter_visible_resources`` → ``KnowledgeAccessPolicy``，
        与直接按 ID 读取完全同一判定（Req 5.7 / Property 4）。
        """
        from app.models.knowledge_models import KnowledgeDocument

        stmt = (
            sa.select(
                KnowledgeDocument.id,
                KnowledgeDocument.name,
                KnowledgeDocument.folder_id,
            )
            .where(
                KnowledgeDocument.is_deleted == sa.false(),
                KnowledgeDocument.name.ilike(pattern),
            )
            .order_by(KnowledgeDocument.name)
            .limit(limit)
        )

        rows = (await self._db.execute(stmt)).all()
        return [
            MentionCandidate(
                type=ResourceType.knowledge_doc.value,
                id=str(r.id),
                label=r.name or "",
                sublabel="知识文档",
                jump_route=f"/knowledge/docs/{r.id}",
            )
            for r in rows
            if r.id is not None
        ]

    async def _search_knowledge_folders(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """知识文件夹搜索：``name`` ILIKE。

        与 ``_search_knowledge_docs`` 同理**不按项目过滤**：模型只有 ``project_ids``
        （JSONB），旧代码引用不存在的 ``KnowledgeFolder.project_id``；且公共文件夹
        （``access_level='public'``）的 ``project_ids`` 为 NULL，按项目过滤会把它们全排除。
        可见性交给 ``filter_visible_resources`` → ``KnowledgeAccessPolicy``。
        """
        from app.models.knowledge_models import KnowledgeFolder

        stmt = (
            sa.select(
                KnowledgeFolder.id,
                KnowledgeFolder.name,
            )
            .where(
                KnowledgeFolder.is_deleted == sa.false(),
                KnowledgeFolder.name.ilike(pattern),
            )
            .order_by(KnowledgeFolder.name)
            .limit(limit)
        )

        rows = (await self._db.execute(stmt)).all()
        return [
            MentionCandidate(
                type=ResourceType.knowledge_folder.value,
                id=str(r.id),
                label=r.name or "",
                sublabel="知识文件夹",
                jump_route=f"/knowledge/folders/{r.id}",
            )
            for r in rows
            if r.id is not None
        ]

    async def _search_address(
        self,
        pattern: str,
        project_id: UUID | None,
        limit: int,
        year: int | None = None,
    ) -> list[MentionCandidate]:
        """地址坐标搜索 —— **表级**候选（Task 22/23）。

        地址目录登记到单元格，但 mention 候选聚合到**表**：一条候选 = 一张数据表，
        引用后 AI 拿到该表全部列的当前值自行分析，审计师不必去挑单元格。

        改造前的两个问题（本次修复）：

        1. 逐单元格列出 ⇒ 同一坐标被多个来源重复登记时，候选里出现好几条一模一样的
           "资产负债表 > 存货 > 期末"，而它们指向同一个数。
        2. 向 registry 传 ``year=0`` ⇒ ``build_trial_balance_entries`` /
           ``build_aux_entries`` 按 ``year`` 过滤业务表后恒空，**试算表与辅助余额
           两域从未出现在候选里**，只剩不按年度过滤的 report 域行级坐标。

        参与的域与聚合层级见 ``_ADDRESS_MENTION_DOMAINS``。
        """
        if project_id is None or year is None:
            # 四表数据按 (project, year) 定位；没有年度就没有可引用的表，
            # 不用 year=0 去查一张必然为空的表（Req 3.4：不猜测）。
            return []

        from app.services.address_registry import address_registry, build_uri

        keyword = pattern.strip("%").strip().lower()

        # 表级分组：table_uri → {label, columns, jump_route, haystack}
        groups: dict[str, dict[str, Any]] = {}

        for domain, key_fields in _ADDRESS_MENTION_DOMAINS.items():
            try:
                entries = await address_registry.get_domain(
                    self._db, str(project_id), year, "soe", domain
                )
            except Exception as exc:
                # 🔴 ERROR 而非 WARNING：这里捕到的是取数/接线故障，
                # 静默降级会让整个域"看起来只是没数据"。
                logger.error(
                    "地址坐标 %s 域加载失败: %s: %s",
                    domain, type(exc).__name__, exc, exc_info=exc,
                )
                continue

            for entry in entries or []:
                source = (getattr(entry, "source", "") or "").strip()
                if not source:
                    continue
                # 表级 URI 完全由 _ADDRESS_MENTION_DOMAINS 声明的字段派生：
                # 未登记的维度被丢弃（tb 域不含 path、两域都不含 cell ⇒ 聚合掉列）。
                # 🔴 不要退化成"只判断有没有 path" —— 那样声明里的其他字段就成了
                # 没人消费的注释，改它不会改变行为（假绿第①源）。
                parts = {
                    field: (getattr(entry, field, "") or "").strip()
                    for field in ("source", "path", "cell")
                }
                table_uri = build_uri(
                    domain,
                    parts["source"] if "source" in key_fields else "",
                    parts["path"] if "path" in key_fields else "",
                    parts["cell"] if "cell" in key_fields else "",
                )
                table_path = parts["path"] if "path" in key_fields else ""

                group = groups.get(table_uri)
                if group is None:
                    label = _table_level_label(getattr(entry, "label", "") or "")
                    group = groups[table_uri] = {
                        "label": label or table_uri,
                        "columns": [],
                        # tb/aux 的 jump_route 只按 source 定位（与 cell 无关），
                        # 因此表级直接复用第一条的路由
                        "jump_route": getattr(entry, "jump_route", "") or "",
                        "haystack": f"{label} {source} {table_path}".lower(),
                    }

                column = (getattr(entry, "cell", "") or "").strip()
                if column and column not in group["columns"]:
                    group["columns"].append(column)

        # 排序：先按域的声明顺序（试算表在辅助余额之前 —— 前者是审计师的主入口，
        # 后者动辄上万个维度组合），同域内按 label。不依赖中文字符的 Unicode 序。
        domain_rank = {d: i for i, d in enumerate(_ADDRESS_MENTION_DOMAINS)}

        def _sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, str]:
            table_uri, group = item
            domain = table_uri.split("://", 1)[0]
            return (domain_rank.get(domain, len(domain_rank)), group["label"])

        out: list[MentionCandidate] = []
        for table_uri, group in sorted(groups.items(), key=_sort_key):
            if keyword and keyword not in group["haystack"]:
                continue
            out.append(
                MentionCandidate(
                    type=ResourceType.address.value,
                    id=table_uri,
                    label=group["label"],
                    sublabel=_address_sublabel(group["columns"]),
                    jump_route=group["jump_route"],
                )
            )
            if len(out) >= limit:
                break
        return out


# ---------------------------------------------------------------------------
# Mention 正文加载（供 ContextBuilder 消费）
# ---------------------------------------------------------------------------


#: mention 正文单条纳入上下文的最大字符数（超出由 ContextBuilder 的 token 预算再裁剪）。
_MENTION_CONTENT_CHARS = 2000

#: 资源类型 → 宿主类型：mention 正文加载复用"以该资源为宿主"的既有解析与 loader。
#:
#: 地址坐标不是宿主类型（走 ``_load_address_content``）；attachment 不作为 mention 资源。
_MENTION_HOST_TYPE: dict[ResourceType, HostType] = {
    ResourceType.workpaper: HostType.workpaper,
    ResourceType.note: HostType.note,
    ResourceType.report: HostType.report,
    ResourceType.knowledge_doc: HostType.knowledge_doc,
    ResourceType.knowledge_folder: HostType.knowledge_folder,
}


async def load_mention_context(
    db: AsyncSession,
    *,
    user: Any,
    host: AuthorizedHostContext,
    mentions: list[tuple[ResourceType, str]],
) -> list[MentionContentItem]:
    """加载已授权 mention 的正文。

    每条 mention 独立走「授权 → 反查 label → 加载正文」，任一条失败不影响其他条。
    返回的 ``MentionContentItem.status`` 区分 included / denied / unavailable。

    由 NativeEngine 在 _build_context 后调用，把 mention 正文注入到 context 中。

    ## 三件事全部复用既有单一真源

    ==========  =================================================================
    授权         ``HostContextResolver.resolve`` —— 以被引用资源为宿主判定，
                 与用户直接打开该资源发起对话**完全同一条**判定路径
                 （Req 5.7 / Property 4：不存在"搜索不可见但直接 ID 可读"的旁路）。
                 它还顺带校验 project/year 断言，跨项目引用按 host_context_mismatch 拒绝。
    label        同上 resolve 的 ③label 阶段（授权通过后才读展示名）。
    正文         ``ContextBuilder.load_document_content`` —— 每宿主专属 loader 的
                 唯一分派表（Req 3.7）。
    ==========  =================================================================

    历史缺陷（本次修复）：本函数曾自带第二套正文 SQL，其中
    ``WorkingPaper.content`` / ``DisclosureNote.content`` / ``FinancialReport.content`` /
    ``KnowledgeDocument.content`` **四个属性在模型上都不存在**（真实列分别是
    ``parsed_data`` / ``text_content`` / 行级 ``row_name+金额`` / ``content_text``）。
    AttributeError 被 fail-open 吞成 ``status="unavailable"``，用户选中的引用从未真正
    进入上下文，而 AI 照常作答。
    """
    if not mentions:
        return []

    from app.services.ai_chat.host_context import (
        HostContextDenial,
        HostContextResolver,
    )
    from app.services.doc_ai_context_builder import ContextBuilder

    resolver = ResourceAccessResolver(db)
    host_resolver = HostContextResolver(db, access=resolver)
    builder = ContextBuilder(db)
    host_decision = AccessDecision(
        allowed=True,
        principal_id=host.principal_id,
        project_id=host.project_id,
        cycle_scope=host.cycle_scope,
        allowed_actions=host.allowed_actions,
        scope_unbounded=host.scope_unbounded,
    )

    def _denied(resource_type: ResourceType, resource_id: str) -> MentionContentItem:
        return MentionContentItem(
            type=resource_type.value,
            id=resource_id,
            label="",
            content="",
            status="denied",
        )

    items: list[MentionContentItem] = []
    for resource_type, resource_id in mentions:
        try:
            # ── 地址坐标：非宿主资源，走专属授权 + 取值 ──────────────────────
            if resource_type is ResourceType.address:
                decision = await resolver.authorize_resource(
                    user, host_decision, resource_type, resource_id, AiChatAction.read,
                )
                if not decision.allowed:
                    items.append(_denied(resource_type, resource_id))
                    continue
                content, label = await _load_address_content(
                    db, resource_id, host.project_id, host.year
                )
                items.append(
                    MentionContentItem(
                        type=resource_type.value,
                        id=resource_id,
                        label=label or "",
                        content=content or "",
                        token_estimate=len(content) // 3 if content else 0,
                        status="included" if content else "unavailable",
                    )
                )
                continue

            host_type = _MENTION_HOST_TYPE.get(resource_type)
            if host_type is None:
                # 未接入的资源域（attachment）⇒ fail-closed，不冒充"已引用"
                items.append(
                    MentionContentItem(
                        type=resource_type.value,
                        id=resource_id,
                        label="",
                        content="",
                        status="unavailable",
                    )
                )
                continue

            # ── ①②③ 授权 + 反查 + label（唯一真源）──────────────────────────
            outcome = await host_resolver.resolve(
                user,
                HostRef(
                    type=host_type,
                    id=resource_id,
                    project_id_assertion=host.project_id,
                    year_assertion=host.year,
                ),
                AiChatAction.read,
            )
            if isinstance(outcome, HostContextDenial):
                items.append(_denied(resource_type, resource_id))
                continue

            # ── 正文（唯一分派表）───────────────────────────────────────────
            content = await builder.load_document_content(outcome)
            if not content:
                items.append(
                    MentionContentItem(
                        type=resource_type.value,
                        id=outcome.resource_id,
                        label=outcome.display_label,
                        content="",
                        status="unavailable",
                    )
                )
                continue

            content = content[:_MENTION_CONTENT_CHARS]
            items.append(
                MentionContentItem(
                    type=resource_type.value,
                    id=outcome.resource_id,
                    label=outcome.display_label,
                    content=content,
                    token_estimate=len(content) // 3,  # 粗估 token 数
                    status="included",
                )
            )

        except Exception as exc:
            # 🔴 ERROR 而非 WARNING：本分支唯一会捕到的是接线错误（字段名/签名写错），
            # 历史上正文加载因此整条恒 unavailable 却只留 WARNING 无人发现。
            logger.error(
                "mention 正文加载失败 %s/%s: %s: %s",
                resource_type.value, resource_id, type(exc).__name__, exc,
                exc_info=exc,
            )
            items.append(
                MentionContentItem(
                    type=resource_type.value,
                    id=resource_id,
                    label="",
                    content="",
                    status="unavailable",
                )
            )

    return items


async def _load_address_content(
    db: AsyncSession,
    resource_id: str,
    project_id: UUID | None,
    year: int | None = None,
) -> tuple[str | None, str | None]:
    """加载地址坐标**表级**正文（Req 6.7：当前值经授权后才进入上下文）。

    ``resource_id`` 是表级 URI（``tb://1001`` / ``aux://1122/客户A``），由
    ``_search_address`` 产出。返回 ``(context_text, label)``。

    改造前这里按 formula_ref/URI 找**单个**条目，正文只有坐标元信息
    （域名 / URI / 公式引用），而 ``AddressEntry.value`` 在所有
    ``build_*_entries`` 里**都没赋值** ⇒ 恒 None ⇒ AI 拿到的是一句
    "地址坐标: 试算表 > 1001 库存现金 > 审定数 | 域: tb | …"，**一个数字都没有**。
    现在直接读业务表，把整张表的当前值给模型。
    """
    if not resource_id or not project_id:
        return None, None

    from app.services.address_registry import parse_uri

    parts = parse_uri(resource_id.strip())
    if not parts:
        return None, None

    domain = parts["domain"]
    source = parts["source"]
    path = parts["path"]

    if domain == "tb":
        return await _load_trial_balance_table(db, source, project_id, year)
    if domain == "aux":
        return await _load_aux_table(db, source, path, project_id, year)

    # 其余域不作为地址坐标 mention 展示（见 _ADDRESS_MENTION_DOMAINS），
    # 若历史会话里存着旧的单元格级 URI，明确报不可用而不是编一段元信息。
    logger.info("地址坐标 %s 域不再作为表级引用提供正文: %s", domain, resource_id)
    return None, None


async def _load_trial_balance_table(
    db: AsyncSession,
    account_code: str,
    project_id: UUID,
    year: int | None,
) -> tuple[str | None, str | None]:
    """试算表单科目全部列的当前值。

    🔴 走 ``get_active_filter`` 而不是裸写 ``is_deleted == false``（平台铁律）：
    四表按数据集版本存储（active / superseded 各一份行），裸过滤会把历史版本
    一起查出来 ⇒ 同一科目返回多行、金额看起来翻倍。
    """
    from app.models.audit_platform_models import TrialBalance
    from app.services.dataset_query import get_active_filter
    from app.services.doc_ai_context_builder import _fmt_amount

    if year is None:
        # 四表按 (project, year) 定位；没有年度不猜（与 _search_address 同一约束）
        return None, None

    active = await get_active_filter(db, TrialBalance.__table__, project_id, year)
    row = (
        await db.execute(
            sa.select(TrialBalance)
            .where(active, TrialBalance.standard_account_code == account_code)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None, None

    account_name = (row.account_name or "").strip()
    label = f"试算表 > {account_code} {account_name}".strip()

    # 不输出 account_category：它是英文枚举（AccountCategory.asset），中文化需要
    # 再引一份映射，而科目码首位已表达资产/负债/权益/成本/损益。
    lines = [f"[{label}]"]
    for attr, column_label in _TB_CONTENT_COLUMNS:
        lines.append(f"{column_label}: {_fmt_amount(getattr(row, attr, None))}")
    return "\n".join(lines), label


async def _load_aux_table(
    db: AsyncSession,
    account_code: str,
    dimension: str,
    project_id: UUID,
    year: int | None,
) -> tuple[str | None, str | None]:
    """辅助余额表某科目 × 某维度的全部明细行。

    ``tb_aux_balance`` 按维度**冗余存储**（memory 铁律），同一
    (科目, 维度名) 可能横跨多个 ``aux_type`` ⇒ 逐行列出并带上辅助类型，
    不做跨 aux_type 的求和（那会双算）。

    🔴 走 ``get_active_filter``（平台铁律）：裸写 ``is_deleted == false`` 会把
    superseded 数据集的行一起查出来。实测同一银行账户因此输出了两条完全相同的
    明细（仅 ``dataset_id`` 不同），模型会误以为存在两个账户各 1000 元。
    """
    from app.models.audit_platform_models import TbAuxBalance
    from app.services.dataset_query import get_active_filter
    from app.services.doc_ai_context_builder import _fmt_amount

    if year is None:
        return None, None

    active = await get_active_filter(db, TbAuxBalance.__table__, project_id, year)
    conditions = [active, TbAuxBalance.account_code == account_code]
    if dimension:
        conditions.append(
            sa.or_(
                TbAuxBalance.aux_name == dimension,
                TbAuxBalance.aux_code == dimension,
            )
        )

    rows = (
        await db.execute(
            sa.select(
                TbAuxBalance.account_name,
                TbAuxBalance.aux_type_name,
                TbAuxBalance.aux_type,
                TbAuxBalance.aux_name,
                TbAuxBalance.aux_code,
                TbAuxBalance.opening_balance,
                TbAuxBalance.debit_amount,
                TbAuxBalance.credit_amount,
                TbAuxBalance.closing_balance,
            )
            .where(*conditions)
            .distinct()
            .limit(_AUX_ROW_LIMIT)
        )
    ).all()
    if not rows:
        return None, None

    account_name = (rows[0].account_name or "").strip()
    label = f"辅助余额 > {account_code} {account_name}".strip()
    if dimension:
        label = f"{label} > {dimension}"

    lines = [f"[{label}]"]
    for row in rows:
        aux_type_label = (row.aux_type_name or row.aux_type or "").strip()
        dim_label = (row.aux_name or row.aux_code or "").strip()
        prefix = f"{aux_type_label} · {dim_label}" if aux_type_label else dim_label
        lines.append(
            f"{prefix} | 期初 {_fmt_amount(row.opening_balance)}"
            f" | 借方 {_fmt_amount(row.debit_amount)}"
            f" | 贷方 {_fmt_amount(row.credit_amount)}"
            f" | 期末 {_fmt_amount(row.closing_balance)}"
        )
    return "\n".join(lines), label
