"""TemplateService — 高级查询模块模板保存与分享（advanced-query-module Task 14.1）。

设计对应 design.md §Components 10「TemplateService（模板/分享/引用，R13）」。

职责（本任务 14.1 范围）：
  - 将查询保存为模板，持久化到 ``custom_query_templates`` 表。
  - 校验名称（长度 1–200 字符）与 scope（``global`` / ``personal`` / ``team`` /
    ``public``）；``personal`` 是真实四值模型 ``private`` 的别名（Glossary：
    private == "personal"），入库归一为 ``private``。
  - 非法名称 / 非法 scope / 非法分享项目标识 → ``TemplateInvalidError``
    （error_code ``TEMPLATE_INVALID``，含失败原因），**不创建任何部分模板记录**
    （校验全部通过后才 ``db.add``）。
  - 分享语义（写入路径）：``global`` / ``public`` 全员可见（无需 shared_project_ids，
    入库置空）；``private`` / ``team`` + 所有者显式分享 → 写入 ``shared_project_ids``，
    供 task 14.2 的可见性规则据此仅对有访问权的项目组成员放行。

铁律：
  - **service 只 flush 不 commit**（平台铁律）：本服务 ``db.add`` + ``await
    db.flush()`` 后返回 ORM 对象，事务提交由 router / 调用方负责。
  - **不建部分记录**：所有校验在 ``db.add`` 之前完成，任一校验失败即抛异常，
    此时数据库无任何写入。

Task 14.2 扩展（本文件同时实现）：
  - **可见性规则**（R13.3 / R13.4）：``global`` / ``public`` 全员（已认证用户）
    可见；``team`` + 显式分享 → 仅对 ``shared_project_ids`` 有访问权的项目组成员
    可见可执行；``private`` → 仅所有者本人可见。所有者对自己创建的模板恒可见
    （private 语义与此一致）。无分享 / 无访问权 → ``TemplateForbiddenError``
    （error_code ``TEMPLATE_FORBIDDEN``，HTTP 403）。
  - **执行**（R13.5）：按当前用户可访问项目范围套 Ownership_Check，仅返回有权行
    （复用 ``OwnershipGuard.filter_accessible_rows``；跨项目聚合行才施加，单项目
    结果由编排层 ``assert_target_accessible`` 项目级作用域保障）。
  - **失效引用降级**（R13.7）：模板引用已不可解析的 addr_id → 跳过该引用、在结果
    中标注失效项并保留其 addr_id、返回其余有效结果（**非整体失败**，区别于查询
    编排 R1.4 的「全有或全无」）。经 ``AddressingService.resolve_many`` 探测失效
    引用（非 all-or-nothing 出口）。
  - **结果引用到底稿**（R13.6）：走 R14 回写路径（``WritebackPreview`` /
    ``SnapshotWriter``），本服务只产出可回写的结果集与列元数据，回写自身归 task 15。

_Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_query_models import CustomQueryTemplate
from app.services.custom_query.addressing_service import (
    AddressingService,
    addressing_service,
)
from app.services.custom_query.ownership_guard import OwnershipGuard, ownership_guard

logger = logging.getLogger(__name__)

# ─── scope 模型（真实四值 + personal 别名）────────────────────────────────────
# 用户可输入的 scope（含 personal 别名）
VALID_INPUT_SCOPES: frozenset[str] = frozenset(
    {"global", "personal", "team", "public"}
)
# personal 是 private 的别名（Glossary：private == "personal"）
_SCOPE_ALIASES: dict[str, str] = {"personal": "private"}
# 入库的 canonical 四值模型
CANONICAL_SCOPES: frozenset[str] = frozenset({"private", "team", "public", "global"})
# 全员可见的 scope（无需 shared_project_ids）
_ALL_VISIBLE_SCOPES: frozenset[str] = frozenset({"global", "public"})

# 名称长度约束（R13.1 / R13.2）
NAME_MIN_LEN = 1
NAME_MAX_LEN = 200

# 错误码（design.md Error Handling：TEMPLATE_INVALID → HTTP 400，含原因）
ERR_CODE_TEMPLATE_INVALID = "TEMPLATE_INVALID"
# 错误码（design.md Error Handling：无分享/访问权 → TEMPLATE_FORBIDDEN → HTTP 403）
ERR_CODE_TEMPLATE_FORBIDDEN = "TEMPLATE_FORBIDDEN"


class TemplateInvalidError(Exception):
    """模板保存校验失败（R13.2）。

    携带 ``error_code``（``TEMPLATE_INVALID``）与描述性 ``message``（含失败原因），
    供 router 层转为统一错误契约（``detail={error_code, message}``，HTTP 400）。
    抛出时数据库无任何部分写入。
    """

    def __init__(self, message: str, *, error_code: str = ERR_CODE_TEMPLATE_INVALID) -> None:
        self.error_code = error_code
        self.message = message
        super().__init__(message)


class TemplateForbiddenError(Exception):
    """模板无分享 / 无访问权（R13.4）。

    携带 ``error_code``（``TEMPLATE_FORBIDDEN``）与描述性 ``message``，供 router
    层转为统一错误契约（``detail={error_code, message}``，HTTP 403）。校验在触达
    数据层之前完成，拒绝时不泄露模板内容。
    """

    def __init__(self, message: str, *, error_code: str = ERR_CODE_TEMPLATE_FORBIDDEN) -> None:
        self.error_code = error_code
        self.message = message
        super().__init__(message)


# ─── 执行结果契约（Task 14.2）────────────────────────────────────────────────
@dataclass
class StaleRef:
    """模板中已失效（不可解析）的引用（R13.7）。

    保留其原始 ``addr_id``（对失效引用而言，原始输入即 addr_id 身份），并附
    失效原因 ``error``（``unresolvable`` / ``resolve_unavailable`` / ``ambiguous``），
    供前端标注失效项、用户后续修复。
    """

    addr_id: str
    raw: str
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {"addr_id": self.addr_id, "raw": self.raw, "error": self.error}


@dataclass
class TemplateExecutionResult:
    """模板执行结果（R13.5 / R13.7）。

    - ``rows`` / ``columns`` / ``total``：仅含当前用户有权访问项目的行（R13.5）。
    - ``stale_refs``：被跳过的失效引用清单（保留 addr_id，R13.7）；非空不代表整体
      失败，其余有效结果照常返回。
    - ``warnings``：来自编排层的非致命告警（如未接线的集成钩子）。
    """

    template_id: Optional[uuid.UUID]
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    total: int = 0
    stale_refs: list[StaleRef] = field(default_factory=list)
    cache_hit: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        """JSON 可序列化视图（供 router 返回）。"""
        return {
            "template_id": str(self.template_id) if self.template_id else None,
            "columns": [
                c if isinstance(c, dict) else _column_to_dict(c) for c in self.columns
            ],
            "rows": self.rows,
            "total": self.total,
            "stale_refs": [s.to_dict() for s in self.stale_refs],
            "cache_hit": self.cache_hit,
            "warnings": self.warnings,
        }


def _column_to_dict(col: Any) -> dict:
    """将 ColumnMeta（或任意 dataclass/对象）转为 dict，容错未知形态。"""
    if hasattr(col, "__dict__"):
        return dict(col.__dict__)
    return {"value": col}


def _to_uuid(value: Any) -> uuid.UUID | None:
    """将 str / UUID / None 归一为 UUID，非法输入返回 None。"""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _is_template_visible(
    *,
    scope: str,
    owner_id: Any,
    shared_project_ids: Any,
    user_id: uuid.UUID | None,
    accessible_project_ids: set[uuid.UUID] | None,
) -> bool:
    """纯函数：判定模板对当前用户是否可见可执行（R13.3 / R13.4）。

    规则（``accessible_project_ids`` 为 ``None`` 表示 admin / partner 可访问全部项目）：
      - 所有者本人 → 恒可见（涵盖 ``private`` 仅所有者可见语义）。
      - ``global`` / ``public`` → 全员（已认证用户）可见。
      - ``team`` → 仅当 ``shared_project_ids`` 与用户可访问项目集合有交集
        （admin / partner 视为可访问全部 → 可见）。
      - ``private``（非所有者）→ 不可见。

    注意：``private`` 严格限所有者本人，即便 admin / partner 亦不可见他人私有模板
    （项目数据全访问权不等于他人模板隐私可见性，R13.3 明确 private 仅所有者可见）。
    """
    oid = _to_uuid(owner_id)
    if oid is not None and user_id is not None and oid == user_id:
        return True

    if scope in _ALL_VISIBLE_SCOPES:
        return True

    if scope == "team":
        if accessible_project_ids is None:  # admin / partner
            return True
        shared: set[uuid.UUID] = set()
        for raw in shared_project_ids or []:
            pid = _to_uuid(raw)
            if pid is not None:
                shared.add(pid)
        return bool(shared & accessible_project_ids)

    # private（非所有者）或未知 scope → 不可见（fail-closed）
    return False


def _normalize_scope(scope: Any) -> str:
    """校验并归一 scope；非法 → TemplateInvalidError。

    - 接受 ``global`` / ``personal`` / ``team`` / ``public``。
    - ``personal`` 归一为 canonical ``private``。
    - 其余（None / 空 / 非字符串 / 未知值）→ 非法。
    """
    if not isinstance(scope, str):
        raise TemplateInvalidError(
            f"scope 非法：期望 {sorted(VALID_INPUT_SCOPES)} 之一，实际类型 "
            f"{type(scope).__name__}"
        )
    normalized = scope.strip().lower()
    if normalized not in VALID_INPUT_SCOPES:
        raise TemplateInvalidError(
            f"scope 非法：'{scope}' 不属于 {sorted(VALID_INPUT_SCOPES)}"
        )
    return _SCOPE_ALIASES.get(normalized, normalized)


def _validate_name(name: Any) -> str:
    """校验名称长度（1–200 字符）；非法 → TemplateInvalidError。

    去除首尾空白后要求非空且不超过 200 字符（空白填充的名称视为空 → 非法）。
    """
    if not isinstance(name, str):
        raise TemplateInvalidError(
            f"名称非法：期望字符串，实际类型 {type(name).__name__}"
        )
    cleaned = name.strip()
    if len(cleaned) < NAME_MIN_LEN:
        raise TemplateInvalidError("名称非法：不能为空")
    if len(cleaned) > NAME_MAX_LEN:
        raise TemplateInvalidError(
            f"名称非法：长度 {len(cleaned)} 超过上限 {NAME_MAX_LEN} 字符"
        )
    return cleaned


def _normalize_shared_project_ids(
    canonical_scope: str, shared_project_ids: Any
) -> list[uuid.UUID]:
    """校验并归一显式分享的项目 id 列表；非法 UUID → TemplateInvalidError。

    - ``global`` / ``public``：全员可见，无需分享 → 一律置空（忽略传入值）。
    - ``private`` / ``team``：将传入项目标识逐个解析为 UUID（去重、保序），
      任一非法 → 非法（不建部分记录）。
    """
    if canonical_scope in _ALL_VISIBLE_SCOPES:
        return []
    if not shared_project_ids:
        return []
    if not isinstance(shared_project_ids, (list, tuple, set)):
        raise TemplateInvalidError(
            "shared_project_ids 非法：期望项目 id 列表"
        )
    result: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for raw in shared_project_ids:
        if isinstance(raw, uuid.UUID):
            pid = raw
        else:
            try:
                pid = uuid.UUID(str(raw))
            except (ValueError, TypeError, AttributeError):
                raise TemplateInvalidError(
                    f"shared_project_ids 含非法项目标识：'{raw}'"
                )
        if pid not in seen:
            seen.add(pid)
            result.append(pid)
    return result


class TemplateService:
    """查询模板保存与分享服务（Task 14.1）。

    只负责持久化（flush，不 commit）与写入路径校验；可见性 / 执行 / 失效引用降级
    归 task 14.2。
    """

    async def save_template(
        self,
        *,
        db: AsyncSession,
        creator_id: uuid.UUID,
        name: str,
        scope: str,
        config: Optional[dict] = None,
        description: Optional[str] = None,
        data_source: Optional[str] = None,
        shared_project_ids: Any = None,
        tags: Optional[list[str]] = None,
    ) -> CustomQueryTemplate:
        """保存查询为模板并持久化到 ``custom_query_templates``（R13.1）。

        校验顺序（任一失败即抛 TemplateInvalidError，此时无任何 db 写入 → 不建
        部分记录，R13.2）：
          1. 名称长度 1–200。
          2. scope ∈ {global, personal, team, public}，personal → private。
          3. shared_project_ids 全部可解析为 UUID（仅 private/team 生效）。

        校验全部通过后 ``db.add`` + ``await db.flush()``（**只 flush 不 commit**，
        提交由调用方负责）。

        分享语义（R13.3 写入路径）：
          - global / public → shared_project_ids 置空（全员可见）。
          - private / team + 显式分享 → 写入 shared_project_ids。
        """
        # ── 校验（在任何 db 写入之前，保证不建部分记录）──
        clean_name = _validate_name(name)
        canonical_scope = _normalize_scope(scope)
        shared = _normalize_shared_project_ids(canonical_scope, shared_project_ids)

        # ── 构造并持久化（只 flush 不 commit）──
        tpl = CustomQueryTemplate(
            id=uuid.uuid4(),
            name=clean_name,
            description=description,
            data_source=data_source,
            config=config or {},
            scope=canonical_scope,
            shared_project_ids=shared,
            tags=list(tags) if tags else [],
            creator_id=creator_id,
            created_by=creator_id,
        )
        db.add(tpl)
        await db.flush()  # 平台铁律：service 只 flush 不 commit（调用方 commit）
        return tpl

    # ── Task 14.2：可见性规则（R13.3 / R13.4）────────────────────────────────

    async def is_visible(
        self,
        template: CustomQueryTemplate,
        *,
        user: Any,
        db: AsyncSession,
        guard: OwnershipGuard | None = None,
    ) -> bool:
        """判定模板对当前用户是否可见可执行（R13.3 / R13.4）。

        复用 ``OwnershipGuard.get_accessible_project_ids`` 计算用户可访问项目集合
        （project_users ∪ project_assignments，admin / partner → 全部），再按
        scope / 分享 / 所有权规则判定（``_is_template_visible`` 纯函数）。
        """
        g = guard or ownership_guard
        accessible = await g.get_accessible_project_ids(user, db)
        user_id = _to_uuid(getattr(user, "id", None))
        return _is_template_visible(
            scope=template.scope,
            owner_id=template.owner_id,
            shared_project_ids=template.shared_project_ids,
            user_id=user_id,
            accessible_project_ids=accessible,
        )

    async def assert_executable(
        self,
        template: CustomQueryTemplate,
        *,
        user: Any,
        db: AsyncSession,
        guard: OwnershipGuard | None = None,
    ) -> None:
        """不可见 → ``TemplateForbiddenError``（HTTP 403，R13.4）。

        在触达任何数据层 / 执行查询之前调用；拒绝时不泄露模板内容。
        """
        if not await self.is_visible(template, user=user, db=db, guard=guard):
            raise TemplateForbiddenError("无权访问该模板：既非所有者，也无有效分享 / 访问权")

    # ── Task 14.2：执行 + 失效引用降级（R13.5 / R13.7）───────────────────────

    async def execute_template(
        self,
        template: CustomQueryTemplate,
        *,
        user: Any,
        project_id: Any,
        db: AsyncSession,
        executor: Optional[Callable[..., Awaitable[Any]]] = None,
        guard: OwnershipGuard | None = None,
        addressing: AddressingService | None = None,
    ) -> TemplateExecutionResult:
        """执行已保存模板（R13.4 / R13.5 / R13.7）。

        步骤：
          1. **可见性/访问权**（R13.4）：不可见 → ``TemplateForbiddenError`` 403，
             不触达数据层。
          2. **失效引用探测**（R13.7）：用 ``AddressingService.resolve_many``
             （**非** all-or-nothing 出口）逐项解析模板目标，``found=False`` 的引用
             归集为 ``stale_refs``（保留 addr_id + 失效原因）并从执行目标中剔除，
             其余有效目标继续执行 —— 非整体失败。
          3. **执行**（R13.5）：以有效目标构造 ``QueryRequest`` 交编排层
             （默认 ``query_orchestrator.execute``，可注入 ``executor`` 便于测试），
             编排层内部执行 Ownership_Check（``assert_target_accessible`` 项目级
             作用域）与取数。
          4. **归属过滤**（R13.5）：对携带 ``project_id`` 的跨项目聚合行复用
             ``OwnershipGuard.filter_accessible_rows`` 仅保留有权行（单项目结果不含
             project_id 列 → 由步骤 3 的项目级作用域保障，不误删）。

        service 只读、不写库、不 commit（平台铁律）。
        """
        g = guard or ownership_guard
        addr = addressing or addressing_service

        # step1: 可见性 / 访问权（R13.4）
        await self.assert_executable(template, user=user, db=db, guard=g)

        # step2: 失效引用探测（R13.7，非 all-or-nothing）
        config = template.config or {}
        raw_targets = [str(t) for t in (config.get("targets") or [])]
        stale_refs: list[StaleRef] = []
        valid_raws: list[str] = []
        if raw_targets:
            resolved = await addr.resolve_many(
                raw_targets, project_id=str(project_id) if project_id else None, db=db
            )
            for t in resolved:
                if t.found:
                    valid_raws.append(t.raw)
                else:
                    # 失效引用：保留其 addr_id（对失效引用原始输入即 addr_id 身份）
                    stale_refs.append(
                        StaleRef(addr_id=t.addr_id or t.raw, raw=t.raw, error=t.error)
                    )

        # step3: 执行有效目标（R13.5，编排层内做项目级 Ownership_Check + 取数）
        req = self._build_query_request(config, valid_raws, project_id)
        run = executor
        if run is None:
            from app.services.custom_query.query_orchestrator import query_orchestrator

            run = query_orchestrator.execute
        result = await run(req, user=user, db=db)

        rows = list(getattr(result, "rows", []) or [])
        columns = list(getattr(result, "columns", []) or [])
        warnings = list(getattr(result, "warnings", []) or [])
        cache_hit = bool(getattr(result, "cache_hit", False))

        # step4: 跨项目聚合行归属过滤（R13.5）——仅当行携带 project_id 才施加，
        #        避免误删单项目结果（与编排层 _run_pipeline 一致的防御式判定）。
        if rows and any(isinstance(r, dict) and "project_id" in r for r in rows):
            rows = await g.filter_accessible_rows(rows, user=user, db=db)

        return TemplateExecutionResult(
            template_id=getattr(template, "id", None),
            columns=columns,
            rows=rows,
            total=len(rows),
            stale_refs=stale_refs,
            cache_hit=cache_hit,
            warnings=warnings,
        )

    @staticmethod
    def _build_query_request(
        config: dict, valid_raws: list[str], project_id: Any
    ) -> Any:
        """从模板 config + 有效目标构造 ``QueryRequest``（惰性导入避免耦合/环）。

        防御式提取 entry / group_by / aggs / pivot / 分页；未知字段忽略。
        """
        from app.services.custom_query.query_orchestrator import (
            Agg,
            PivotConfig,
            QueryRequest,
        )

        entry = config.get("entry") or "business"

        group_by = [str(d) for d in (config.get("group_by") or [])]

        aggs: list[Agg] = []
        for a in config.get("aggs") or []:
            if isinstance(a, dict) and a.get("field"):
                aggs.append(
                    Agg(
                        field=str(a["field"]),
                        func=str(a.get("func", "sum")),
                        alias=a.get("alias"),
                    )
                )

        pivot = None
        pcfg = config.get("pivot")
        if isinstance(pcfg, dict):
            pivot = PivotConfig(
                row_dims=[str(x) for x in (pcfg.get("row_dims") or [])],
                col_dims=[str(x) for x in (pcfg.get("col_dims") or [])],
                value_field=pcfg.get("value_field"),
                agg=str(pcfg.get("agg", "sum")),
                max_cols=int(pcfg.get("max_cols", 512)),
            )

        def _int(v: Any, default: int) -> int:
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        return QueryRequest(
            entry=str(entry),
            project_id=str(project_id) if project_id is not None else "",
            targets=list(valid_raws),
            dsl=config.get("dsl") if isinstance(config.get("dsl"), dict) else None,
            group_by=group_by,
            aggs=aggs,
            pivot=pivot,
            page=_int(config.get("page"), 1),
            page_size=_int(config.get("page_size"), 100),
        )


# 模块级单例（与同包 addressing_service / ownership_guard / query_cache 一致）
template_service = TemplateService()
