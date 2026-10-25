"""SQL Schema 漂移检测器（migration-runner-resilience spec / Sprint 2）

启动时对比 ORM `Base.metadata` 与实际 PG schema，发现以下 5 类漂移并写入
`schema_drift_log` 表：

- ``orm_extra``：ORM 定义了但 DB 缺失的列/表（最高优先，业务接口运行时会 500）
- ``db_extra``：DB 有但 ORM 没定义的列/表（INFO 级，多为历史残留）
- ``type_mismatch``：列存在但类型/可空性不一致（WARN 级，可能数据不一致）
- ``enum_mismatch``：ORM 原生枚举列与 public 实际列类型 / 标签不符（运行时查询或插入会爆）
- ``checksum_drift``：已应用迁移被事后编辑且未在 ``migration_drift_ledger`` 逐条登记

`/api/health` 端点消费 `schema_drift_log`，critical 漂移（:data:`CRITICAL_DRIFT_TYPES`，
单一真源）>0 → status=degraded → 前端 DegradedBanner 暴露给运维（避免业务 500 才发现）。

设计原则：
- 纯检测，不自动修复（避免误删 / 误改）
- 失败不阻塞启动（异常吞掉 + WARN 日志）
- 60s timeout（防止漏接表卡住启动）
- KNOWN_ALLOWLIST 屏蔽系统/历史残留表
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable, Literal, Mapping

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("audit_platform.schema_drift")

DriftType = Literal["orm_extra", "db_extra", "type_mismatch", "enum_mismatch", "checksum_drift"]

#: 会让业务接口运行时失败（或让「已应用迁移的编辑」静默丢失）的漂移类型 —— health degraded 判定与
#: 启动日志的 critical 计数**只**引用这里（spec migration-integrity-and-enum-drift-closure 3.3）。
#: INFO 级 db_extra 与 WARN 级 type_mismatch 只作可观测展示，否则共库残留噪音会让 health 永远 degraded。
CRITICAL_DRIFT_TYPES: frozenset[str] = frozenset({"orm_extra", "enum_mismatch", "checksum_drift"})


@dataclass(frozen=True)
class DriftItem:
    table: str
    column: str | None
    drift_type: DriftType
    detail: str


def count_critical(items: Iterable[DriftItem]) -> int:
    return sum(1 for it in items if it.drift_type in CRITICAL_DRIFT_TYPES)


# ---------------------------------------------------------------------------
# 枚举漂移：按「列」判定（spec migration-integrity-and-enum-drift-closure Requirement 4）
# ---------------------------------------------------------------------------
#
# 旧实现按 Python 枚举**类名** snake_case 猜 PG 类型名、比较 ``member.value``、查 pg_type 不限 schema，
# 三处各自致错：漏配 / 错配（同模块两个同名 ApprovalStatus 后者遮蔽前者）、把 SQLAlchemy 实际发送的
# **成员名**（``Enum.enums``）当成缺失值误报、把 tmp_* 残留 schema 的同名类型标签并进来。
# 现在的判据只取 SQLAlchemy 自己会发给 DB 的东西：列上声明的类型名与 ``Enum.enums``。

@dataclass(frozen=True)
class OrmEnumColumn:
    table: str
    column: str
    #: 列类型上声明的 PG 枚举类型名（``sa.Enum(name=...)``；传枚举类时 SQLAlchemy 默认取类名小写）
    type_name: str
    #: SQLAlchemy 实际发送的标签（``Enum.enums``：默认是成员**名**，设了 values_callable 才是值）
    labels: frozenset[str]


def collect_orm_enum_columns(metadata: sa.MetaData) -> list[OrmEnumColumn]:
    """metadata 中所有 public 表上 ``native_enum=True`` 的枚举列（非原生枚举按 VARCHAR 绑定，不参与）。"""
    out: list[OrmEnumColumn] = []
    for table in metadata.tables.values():
        if table.schema not in (None, "public"):
            continue
        for col in table.columns:
            t = col.type
            if isinstance(t, sa.Enum) and t.native_enum and t.name:
                out.append(OrmEnumColumn(table.name, col.name, t.name, frozenset(t.enums)))
    return sorted(out, key=lambda c: (c.table, c.column))


def diff_enum_columns(
    orm_columns: Iterable[OrmEnumColumn],
    db_columns: Mapping[tuple[str, str], tuple[str, str, str]],
    db_enums: Mapping[str, frozenset[str]],
) -> list[DriftItem]:
    """纯函数判定。

    * ``db_columns``：public 列 ``(table, column) -> (data_type, udt_schema, udt_name)``
      （information_schema.columns）
    * ``db_enums``：**public** 下枚举类型名 -> 标签集合（pg_enum ⋈ pg_type ⋈ pg_namespace）

    列在 DB 不存在 → 不报（归 orm_extra）；列不是 public 下的同名枚举类型（含 varchar）→ 报；
    否则 ORM 标签 − DB 标签 非空 → 报。
    """
    items: list[DriftItem] = []
    for c in orm_columns:
        actual = db_columns.get((c.table, c.column))
        if actual is None:
            continue
        data_type, udt_schema, udt_name = actual
        if data_type != "USER-DEFINED" or udt_schema != "public" or udt_name != c.type_name:
            shown = udt_name if data_type == "USER-DEFINED" else data_type
            items.append(DriftItem(
                table=c.table, column=c.column, drift_type="enum_mismatch",
                detail=(
                    f"ORM 声明原生枚举 {c.type_name}，DB 列类型是 {udt_schema}.{shown} —— "
                    f"asyncpg 按 ::{c.type_name} 绑定参数，按该列查询 / 写入会失败"
                ),
            ))
            continue
        missing = c.labels - db_enums.get(udt_name, frozenset())
        if missing:
            items.append(DriftItem(
                table=c.table, column=c.column, drift_type="enum_mismatch",
                detail=(
                    f"public.{udt_name} 缺少 ORM 会写入的标签 {sorted(missing)} "
                    f"（SQLAlchemy 发送 Enum.enums，写入这些值会 invalid input value）"
                ),
            ))
    return items


_ENUM_COLUMN_SQL = """
    SELECT table_name, column_name, data_type, udt_schema, udt_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
"""

#: 🔴 必须限定 public：tmp_* 残留 schema 里的同名类型会把标签并进来，掩盖真缺口
_PUBLIC_ENUM_LABEL_SQL = """
    SELECT t.typname, e.enumlabel
    FROM pg_type t
    JOIN pg_enum e ON e.enumtypid = t.oid
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public'
"""


async def fetch_public_enum_catalog(conn) -> tuple[
    dict[tuple[str, str], tuple[str, str, str]], dict[str, frozenset[str]]
]:
    """在给定连接上读取 :func:`diff_enum_columns` 需要的两份 public 目录（真库守卫在回滚事务里复用）。"""
    col_rows = (await conn.execute(text(_ENUM_COLUMN_SQL))).fetchall()
    label_rows = (await conn.execute(text(_PUBLIC_ENUM_LABEL_SQL))).fetchall()
    db_columns = {(r[0], r[1]): (r[2], r[3], r[4]) for r in col_rows}
    labels: dict[str, set[str]] = {}
    for typname, label in label_rows:
        labels.setdefault(typname, set()).add(label)
    return db_columns, {k: frozenset(v) for k, v in labels.items()}


class SchemaDriftDetector:
    """启动时扫描 ORM ↔ DB schema 差异。

    使用方法（lifespan 中）::

        from app.core.schema_drift_detector import SchemaDriftDetector
        detector = SchemaDriftDetector(engine)
        items = await detector.scan()
        await detector.write_log(items)
    """

    # 系统/历史残留表，不参与 drift 计算
    KNOWN_ALLOWLIST: frozenset[str] = frozenset({
        # 迁移系统
        "schema_version",
        "schema_migration_failures",
        "schema_drift_log",
        # alembic 历史残留（spec Sprint 4 删除前会出现在此）
        "alembic_version",
        # PG 系统
        "pg_stat_statements",
        # 业务基础设施表（裸 SQL / 迁移管理，无 ORM 映射）
        "app_audit_log",
        "data_snapshots",
        "group_note_templates",
        "note_section_locks",
        "note_section_templates",
        "review_conversation_exports",
        "review_conversation_participants",
        "system_settings",
        "tb_aux_balance_summary",
        "wp_migration_snapshots",
        "wp_sheet_locks",
        # 历史残留表（一次性脚本产物 / 联动审计日志）
        "linkage_audit_log",
        "seed_load_history",
        # V117 工时统一后保留的旧表（work_hours 数据已迁移到 work_hour_entries）
        "work_hours_legacy",
        # 符号约定迁移(V064)产生的备份表，迁移完成后未清理
        "_sign_migration_backup",
        # 科目类别修正迁移(migrate_account_category_correction.py)的回滚备份表，
        # 一次性脚本快照 (project_id,table,record_id,old_category)，需保留以支持 --rollback
        "_category_correction_backup",
        "_note_guidance_split_backup",
        "_note_text_ch8_backup",
        # 附注治理一次性清理脚本的回滚备份表（用完保留以支持 --rollback）：
        # _note_ai_text_backup（清理 text_content 残留 AI 草稿）
        # _note_wrong_year_orphan_backup（清理错误年度孤儿披露记录）
        # _note_text_markdown_backup（清理 text_content 的 markdown 残留）
        "_note_ai_text_backup",
        "_note_wrong_year_orphan_backup",
        "_note_text_markdown_backup",
        # checklist_responses: 裸 SQL 迁移建表，无独立 ORM 模型（数据通过 raw SQL 操作）
        "checklist_responses",
        # custom_account_packages: 裸 SQL 迁移建表
        "custom_account_packages",
        # ── V154 Excel 模板覆盖层版本台账（有意不做 ORM 映射）────────────────────
        # 🔴 与下面 V149 那两张「未接通结构」不同：本表三层全接通
        #    （迁移 V154 + services/wp_template_override.py 的 6 个 async 函数 +
        #     routers/wp_template_override_router.py 已注册进 router_registry）。
        #    不映射 ORM 是**设计裁决**，理由是表上的三条约束全靠 DB 承载：
        #      · trg_wptov_immutable    —— 除 is_current 外全列不可变
        #      · trg_wptov_forbid_delete —— 禁止物理删除（回滚只改 is_current）
        #      · uq_wptov_one_current_per_scope —— is_current 唯一性靠部分唯一索引
        #    而 is_current 的转移必须走 CAS 式两步（先 demote 取回父版本再 INSERT，
        #    见 record_override_version）。一旦映射进 ORM，任何 `row.is_current = True`
        #    或 `session.delete(row)` 都能绕过这套顺序，Requirement 4.3「不删行」与
        #    Property 16「每次保存都接上父版本」就失去可执行判据。
        #    → 表名单一真源 = wp_template_override.OVERRIDE_VERSION_TABLE。
        #    本条与「无 ORM 模型」双向锁死，见 tests/test_schema_drift_detector.py
        #    的 test_v154_override_version_table_allowlisted_and_unmapped。
        "workpaper_template_override_version",
        # ── V149 MCP scoped token（dsh-agent-panel-integration Task 25）────────────
        # 🔴 这两张表当前是**未接通的结构**，不是历史残留：
        #    V149 注释写「持久化，跨进程可见」，而实现 `services/ai_chat/mcp_token.py`
        #    的撤销集与 `mcp_budget.py` 的配额都是**进程内 dict**（docstring 自述
        #    「撤销通过 revocation set（内存，进程级）」）。全后端对这两张表零读写。
        #    → 屏蔽 drift 噪音，但接通持久化（或回滚 V149）仍是待办；届时应删本条并
        #      补 ORM 模型，而不是让它长期停留在 allowlist 里。
        "ai_chat_mcp_call_log",
        "ai_chat_mcp_token_revocations",
        # ── V155 OO 内容修订号（有意不做 ORM 映射）──────────────────────────────
        # 🔴 与上面 V149 那两张「未接通结构」不同：本表三层全接通
        #    （迁移 V155 + services/onlyoffice_room_identity.py 的
        #     `_content_revision` 读 / `bump_oo_content_revision` 写，后者由 D2 的
        #     push_html_to_excel 在真的改写受管内容后调用）。
        #    不映射 ORM 是**设计裁决**：`revision` 的推进只允许走那条
        #      INSERT ... ON CONFLICT (wp_id, entry_id)
        #        DO UPDATE SET revision = <表名>.revision + 1
        #    —— 自增在 DB 侧原子完成，并发两次改写各得一个新号。一旦映射进 ORM，
        #    任何 `row.revision = x` 都能绕过它：读-改-写竞态下两次改写拿到同一个号
        #    ⇒ doc_key 不轮转 ⇒ 正好退回本表要解决的「服务端已写 756 行、OO 仍显示
        #    空模板」那个缺陷（V155 表头注释记的浏览器实测）。
        #    → 表名单一真源 = onlyoffice_room_identity.OO_CONTENT_REVISION_TABLE。
        #    本条与「无 ORM 模型」双向锁死，见 tests/test_schema_drift_detector.py
        #    的 test_v155_oo_content_revision_table_allowlisted_and_unmapped。
        "working_paper_oo_content_revision",
    })

    # 列级 allowlist：DB 有但 ORM 不需映射的列（历史残留 / 已弃用 / 有意只走裸 SQL）
    KNOWN_COLUMN_ALLOWLIST: frozenset[tuple[str, str]] = frozenset({
        ("cell_annotations", "sheet_name"),       # 旧版列，已被 sheet_id 取代
        ("adjustments", "status"),                # 旧 status 列，业务改用 review_status
        ("projects", "template_version_id"),      # 旧关联列，不再 ORM 映射
        # ── V151 workpaper-sync business content revision（有意不做 ORM 映射）──────
        # 🔴 `content_revision` 的推进必须走 CAS
        #    （`UPDATE working_paper SET content_revision = content_revision + 1
        #      WHERE id = :wp AND content_revision = :expected RETURNING content_revision`，
        #    见 services/workpaper_sync/repository.bump_content_revision），
        #    并且只允许经 `RevisionLockedRepository` 门面调用 —— 纯表示升级路径上
        #    `bump_content_revision` / `set_current_content_version` 在构造上不可达
        #    （变异检验 M21/M23 依赖这条）。一旦把两列映射进 `WorkingPaper` ORM，
        #    任何 `wp.content_revision = x` 都能绕过 CAS 与门面，Requirement 2.1 /
        #    Property 4「纯定义升级不推进 business revision」就失去可执行判据。
        #    → 因此这两列**有意**只走裸 SQL，不是漏映射。
        ("working_paper", "content_revision"),
        ("working_paper", "current_content_version_id"),
        # ── V149 ai_chat_runs 的 MCP 计量列（与上面两张 MCP 表同因，未接通）────────
        ("ai_chat_runs", "mcp_token_issued"),
        ("ai_chat_runs", "mcp_calls_used"),
        ("ai_chat_runs", "mcp_total_bytes"),
    })

    # ORM 定义但 DB 可能不存在的列（graceful 降级场景，如 pgvector 扩展未安装）
    KNOWN_ORM_EXTRA_COLUMN_ALLOWLIST: frozenset[tuple[str, str]] = frozenset({
        ("knowledge_index", "embedding_vec"),     # V119 pgvector 列，PG 扩展不可用时跳过
    })

    # 外部租户表前缀（与业务共用 audit_platform 库的第三方工具表）。
    #
    # 本机 audit-metabase 容器与业务后端共用同一 PG 库，导致 Metabase 自身的
    # ~180 张表（core_*/collection*/dashboard*/pulse*/query_*/transform*/
    # workspace*/qrtz_*（Quartz 调度器）/metabase_*/report_card*/v_* 视图等）
    # 全被 drift detector 当成「DB 多出来的表」误报为 db_extra，污染 health。
    #
    # 这些前缀下的表一律视为外部租户表，跳过 drift 计算（既非业务表也无需 ORM 映射）。
    # 若将来 Metabase 迁到独立 schema/库，可移除本过滤。
    EXTERNAL_TENANT_PREFIXES: tuple[str, ...] = (
        "metabase_",
        "qrtz_",          # Quartz 调度器
        "core_",          # core_user / core_session
        "v_",             # Metabase 视图（v_users / v_tables / v_query_log ...）
        "report_card",    # report_card / report_cardfavorite / report_dashboard*
        "pulse",          # pulse / pulse_card / pulse_channel*
        "collection",     # collection / collection_bookmark / collection_permission*
        "dashboard",      # dashboard_bookmark / dashboard_tab / dashboard_favorite
        "transform",      # transform / transform_job* / transform_run*
        "workspace",      # workspace / workspace_graph / workspace_*
        "query_",         # query_action / query_cache / query_execution / query_field / query_table
        "report_dashboard",  # report_dashboard / report_dashboardcard（Metabase 仪表盘）
        "permissions",    # permissions / permissions_group* / permissions_revision
        "notification",   # notification / notification_card / notification_*
        "search_index",   # search_index__* / search_index_metadata
        "moderation_",
        "metabot",        # metabot / metabot_conversation / metabot_message / metabot_prompt
        "timeline",       # timeline / timeline_event
        "remote_sync_",
        "model_index",
        "user_parameter_",
        "user_key_value",
        "parameter_card",
        "comment",        # comment / comment_reaction（Metabase 评论，非业务批注表）
    )

    # 精确名单（无统一前缀的 Metabase/外部单表）
    EXTERNAL_TENANT_EXACT: frozenset[str] = frozenset({
        "action", "http_action", "implicit_action", "query_action",
        "analysis_finding", "analysis_finding_error",
        "api_key", "application_permissions_revision",
        "audit_log", "auth_identity", "bookmark_ordering",
        "cache_config", "card_bookmark", "card_label",
        "channel", "channel_template", "cloud_migration",
        "connection_impersonations", "content_translation",
        "data_edit_undo_chain", "data_permissions", "databasechangelog",
        "db_router", "dependency", "dimension", "document", "document_bookmark",
        "field_usage", "glossary", "label", "login_history",
        "measure", "metric", "metric_important_field", "native_query_snippet",
        "persisted_info", "premium_features_token_cache",
        "python_library", "recent_views", "revision", "sandboxes",
        "secret", "segment", "semantic_search_token_tracking",
        "semantic_search_token_tracking", "sequences", "setting",
        "support_access_grant_log", "table_privileges", "task_history",
        "task_run", "tenant", "view_log", "query",
    })

    def _is_external_tenant_table(self, table: str) -> bool:
        """判断表是否属于外部租户（Metabase/Quartz 等共库工具），跳过 drift 计算。"""
        if table in self.EXTERNAL_TENANT_EXACT:
            return True
        return any(table.startswith(p) for p in self.EXTERNAL_TENANT_PREFIXES)

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def scan(self) -> list[DriftItem]:
        """扫描全部 5 类 drift 并返回（db_extra 已按 allowlist / 外部租户过滤）。"""
        # 仅 PG 支持 information_schema 完整查询；其他方言（SQLite 测试环境）退化
        if self._engine.dialect.name != "postgresql":
            logger.debug("[SchemaDrift] 非 PG 方言，跳过 schema diff（dialect=%s）",
                         self._engine.dialect.name)
            return []

        orm_tables = self._collect_orm_tables()
        db_tables = await self._collect_db_tables()

        items: list[DriftItem] = []
        items.extend(self._diff_tables(orm_tables, db_tables))
        items.extend(self._diff_columns(orm_tables, db_tables))
        items.extend(await self._diff_enums())
        items = self._apply_suppressions(items, frozenset(orm_tables))
        # checksum 漂移的 table 是迁移版本号（V128），与表名过滤无关，不进过滤
        items.extend(await self._diff_checksums())
        return items

    def _apply_suppressions(
        self, items: Iterable[DriftItem], orm_table_names: frozenset[str],
    ) -> list[DriftItem]:
        """三张过滤名单只描述「DB 有、ORM 无」的对象（系统表 / 裸 SQL 表 / 共库租户表 / 弃用列），
        所以**只**作用于 db_extra。

        🔴 ORM 表上的 orm_extra / type_mismatch / enum_mismatch 一律不过滤：此前外部租户前缀
        ``notification`` 命中 ORM 表 ``notifications``，该表的全部漂移（含 critical 的 orm_extra）
        被静默吞掉。外部租户前缀同理只作用于**不在 ORM 里**的表。
        """
        kept: list[DriftItem] = []
        for it in items:
            if it.drift_type == "db_extra" and (
                it.table in self.KNOWN_ALLOWLIST
                or (it.table not in orm_table_names and self._is_external_tenant_table(it.table))
                or (it.table, it.column) in self.KNOWN_COLUMN_ALLOWLIST
            ):
                continue
            kept.append(it)
        return kept

    async def write_log(self, items: list[DriftItem]) -> None:
        """覆盖式写入 schema_drift_log（DELETE + INSERT），保证仅保留当前快照。

        若表不存在（V026 尚未应用），创建 IF NOT EXISTS 兜底。
        """
        if self._engine.dialect.name != "postgresql":
            return

        async with self._engine.begin() as conn:
            # 兜底创建表（V026 通常已跑，此处冗余安全网）
            await conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS schema_drift_log (
                    id          SERIAL       PRIMARY KEY,
                    table_name  VARCHAR(100) NOT NULL,
                    column_name VARCHAR(100),
                    drift_type  VARCHAR(50)  NOT NULL,
                    detail      TEXT,
                    detected_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                )
            """)
            await conn.exec_driver_sql("DELETE FROM schema_drift_log")
            for it in items:
                await conn.execute(
                    text("""
                        INSERT INTO schema_drift_log
                          (table_name, column_name, drift_type, detail)
                        VALUES (:t, :c, :dt, :d)
                    """),
                    {"t": it.table, "c": it.column, "dt": it.drift_type, "d": it.detail},
                )

    @classmethod
    async def query_drift(cls, engine: AsyncEngine) -> list[DriftItem]:
        """查询 schema_drift_log（health endpoint 使用）。表不存在返回空列表。"""
        if engine.dialect.name != "postgresql":
            return []
        try:
            async with engine.begin() as conn:
                rows = await conn.execute(text(
                    "SELECT table_name, column_name, drift_type, detail "
                    "FROM schema_drift_log ORDER BY drift_type, table_name"
                ))
                return [
                    DriftItem(table=r[0], column=r[1], drift_type=r[2], detail=r[3] or "")
                    for r in rows.fetchall()
                ]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _collect_orm_tables(self) -> dict[str, dict]:
        """从 ORM Base.metadata 收集 {table_name: {col_name: {type, nullable}}}。

        必须先 import **所有** model 子模块，否则 Base.metadata 不完整
        （``app.models.__init__`` 只显式 import 了约 30 个模块 / 88 张表，
        而 ``backend/app/models/`` 下实际有 60+ 个模块）。不完整的 metadata
        会把大量真实业务表（staff_members / issue_tickets / work_hours 等）
        误判为 db_extra（DB 有但 ORM 未定义）。

        解决：用 pkgutil 遍历 app.models 包，import 每个子模块，
        触发所有 ``class Xxx(Base)`` 注册到 Base.metadata。
        """
        self._import_all_models()
        from app.models.base import Base

        result: dict[str, dict] = {}
        for table in Base.metadata.tables.values():
            cols: dict[str, dict] = {}
            for col in table.columns:
                cols[col.name] = {
                    "type": str(col.type).upper(),
                    "nullable": col.nullable,
                }
            result[table.name] = cols
        return result

    # Pydantic schema / 非 ORM 模块：不参与 Base.metadata 注册，跳过可避免
    # 热重载期间无意义 import 及误报（如 app.models.ai_schemas）。
    _SKIP_MODEL_MODULES: frozenset[str] = frozenset({
        "app.models.ai_schemas",
    })

    @staticmethod
    def _import_all_models() -> None:
        """遍历 app.models 包，import 所有子模块，确保 Base.metadata 完整。

        幂等：重复 import 已加载模块由 Python import 缓存兜底。
        单个子模块 import 失败不阻塞（记 WARN 继续），避免某个坏模块拖垮整个扫描。
        """
        import importlib
        import pkgutil

        import app.models as models_pkg

        for mod_info in pkgutil.walk_packages(
            models_pkg.__path__, prefix="app.models."
        ):
            if mod_info.name in SchemaDriftDetector._SKIP_MODEL_MODULES:
                continue
            # *_schemas 为 Pydantic DTO，非 SQLAlchemy ORM
            if mod_info.name.rsplit(".", 1)[-1].endswith("_schemas"):
                continue
            try:
                importlib.import_module(mod_info.name)
            except Exception as e:  # noqa: BLE001 — 坏模块不应阻塞 drift 扫描
                logger.warning(
                    "[SchemaDrift] import model 模块 %s 失败（跳过）: %s",
                    mod_info.name, e,
                )

    async def _collect_db_tables(self) -> dict[str, dict]:
        """查询 information_schema.columns 收集实际 DB schema。"""
        result: dict[str, dict] = {}
        async with self._engine.begin() as conn:
            rows = await conn.execute(text("""
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
            """))
            for row in rows.fetchall():
                table = row[0]
                col = row[1]
                if table not in result:
                    result[table] = {}
                result[table][col] = {
                    "type": (row[2] or "").upper(),
                    "nullable": row[3] == "YES",
                }
        return result

    def _diff_tables(
        self,
        orm: dict[str, dict],
        db: dict[str, dict],
    ) -> list[DriftItem]:
        """表级差异：ORM 有但 DB 没有 / DB 有但 ORM 没有。"""
        items: list[DriftItem] = []
        orm_set = set(orm.keys())
        db_set = set(db.keys())

        for table in orm_set - db_set:
            items.append(DriftItem(
                table=table, column=None,
                drift_type="orm_extra",
                detail=f"ORM 定义了表 {table} 但 DB 不存在（迁移可能漏跑）",
            ))
        for table in db_set - orm_set:
            items.append(DriftItem(
                table=table, column=None,
                drift_type="db_extra",
                detail=f"DB 有表 {table} 但 ORM 未定义（历史残留 / 手动建表）",
            ))
        return items

    def _diff_columns(
        self,
        orm: dict[str, dict],
        db: dict[str, dict],
    ) -> list[DriftItem]:
        """列级差异：ORM 多列 / DB 多列 / 类型不一致。

        类型对比做了简化：仅检测 PG 类型大类（VARCHAR/TEXT/INTEGER/...），
        不做精度匹配（VARCHAR(100) vs VARCHAR(255) 不报）。
        """
        items: list[DriftItem] = []
        for table in orm.keys() & db.keys():
            orm_cols = orm[table]
            db_cols = db[table]

            for col in orm_cols.keys() - db_cols.keys():
                if (table, col) in self.KNOWN_ORM_EXTRA_COLUMN_ALLOWLIST:
                    continue
                items.append(DriftItem(
                    table=table, column=col,
                    drift_type="orm_extra",
                    detail=f"ORM 定义了 {table}.{col} 但 DB 不存在（迁移漏跑）",
                ))
            for col in db_cols.keys() - orm_cols.keys():
                items.append(DriftItem(
                    table=table, column=col,
                    drift_type="db_extra",
                    detail=f"DB 有 {table}.{col} 但 ORM 未定义",
                ))
            for col in orm_cols.keys() & db_cols.keys():
                # 类型粗粒度对比（取首词作为类型大类）
                orm_type = self._normalize_type(orm_cols[col]["type"])
                db_type = self._normalize_type(db_cols[col]["type"])
                if orm_type and db_type and not self._types_compatible(orm_type, db_type):
                    items.append(DriftItem(
                        table=table, column=col,
                        drift_type="type_mismatch",
                        detail=f"{table}.{col}: ORM={orm_type} vs DB={db_type}",
                    ))
        return items

    @staticmethod
    def _normalize_type(t: str) -> str:
        """归一化类型：取首个空格/括号前的字段大类。

        例：
            'VARCHAR(100)' → 'VARCHAR'
            'CHARACTER VARYING' → 'VARCHAR'  # PG information_schema 用 character varying
            'TIMESTAMP WITH TIME ZONE' → 'TIMESTAMPTZ'
            'DATETIME' → 'TIMESTAMP'  # SQLAlchemy DateTime = PG TIMESTAMP
        """
        s = (t or "").strip().upper()
        if not s:
            return s
        # PG 别名归一
        aliases = {
            "CHARACTER VARYING": "VARCHAR",
            "CHARACTER": "CHAR",
            "TIMESTAMP WITHOUT TIME ZONE": "TIMESTAMP",
            "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ",
            "DOUBLE PRECISION": "FLOAT8",
            "INT": "INTEGER",
            "INT4": "INTEGER",
            "INT8": "BIGINT",
            "BOOL": "BOOLEAN",
            # SQLAlchemy ORM 类型 → PG 实际类型归一化（消除 type_mismatch 假阳性）
            "DATETIME": "TIMESTAMP",  # SA DateTime = PG TIMESTAMP/TIMESTAMPTZ
        }
        if s in aliases:
            return aliases[s]
        # 取首词去括号
        head = s.split("(")[0].split(" ")[0]
        return aliases.get(head, head)

    @staticmethod
    def _types_compatible(orm_type: str, db_type: str) -> bool:
        """判断两个归一化后的类型是否兼容（消除假阳性）。

        以下组合视为兼容（不报 type_mismatch）：
        - TIMESTAMP ↔ TIMESTAMPTZ（时区差异不影响数据存取）
        - CHAR ↔ UUID（SQLAlchemy UUID 报为 CHAR，PG 存为 UUID）
        - VARCHAR ↔ USER-DEFINED（Enum 列：ORM 用 VARCHAR，PG 用自定义 enum 类型）
        - FLOAT ↔ FLOAT8（同义）
        """
        if orm_type == db_type:
            return True
        # 定义兼容组（组内任意两个类型视为兼容）
        compat_groups = [
            {"TIMESTAMP", "TIMESTAMPTZ"},
            {"CHAR", "UUID"},
            {"VARCHAR", "USER-DEFINED"},
            {"FLOAT", "FLOAT8"},
        ]
        for group in compat_groups:
            if orm_type in group and db_type in group:
                return True
        return False

    async def _diff_enums(self) -> list[DriftItem]:
        """ORM 原生枚举列 ↔ public 实际列类型与标签（判定见 :func:`diff_enum_columns`）。

        采集失败不 fail-open 成「无漂移」：返回一条可见的 enum_mismatch，让 health 暴露扫描本身坏了。
        """
        try:
            self._import_all_models()
            from app.models.base import Base

            orm_columns = collect_orm_enum_columns(Base.metadata)
            async with self._engine.begin() as conn:
                db_columns, db_enums = await fetch_public_enum_catalog(conn)
        except Exception as e:  # noqa: BLE001 — 扫描失败要可见，不能静默
            logger.warning("[SchemaDrift] 枚举漂移扫描失败: %s", e)
            return [DriftItem(
                table="(enum_scan)", column=None, drift_type="enum_mismatch",
                detail=f"枚举漂移扫描失败，结果不可信：{type(e).__name__}: {e}"[:500],
            )]
        return diff_enum_columns(orm_columns, db_columns, db_enums)

    async def _diff_checksums(self) -> list[DriftItem]:
        """已应用迁移被事后编辑、且未在 ``migration_drift_ledger`` 逐条（三元组）登记的漂移。

        复用本检测器的引擎（``MigrationRunner(engine=...)`` 不持有、不关闭它）。采集失败同样返回一条
        可见项，而不是当作「无漂移」。
        """
        from app.core.migration_drift_ledger import unexplained_checksum_drift
        from app.core.migration_runner import MigrationRunner

        try:
            drifts = await MigrationRunner(engine=self._engine).detect_checksum_drift()
        except Exception as e:  # noqa: BLE001 — 扫描失败要可见，不能静默
            logger.warning("[SchemaDrift] checksum 漂移扫描失败: %s", e)
            return [DriftItem(
                table="(checksum_scan)", column=None, drift_type="checksum_drift",
                detail=f"迁移 checksum 漂移扫描失败，结果不可信：{type(e).__name__}: {e}"[:500],
            )]
        return [
            DriftItem(
                table=f"V{d.version}", column=None, drift_type="checksum_drift",
                detail=(
                    f"{d.filename} 应用后被编辑（登记 {d.stored_checksum[:12]}… / 当前 "
                    f"{(d.current_checksum or '文件缺失')[:12]}…），编辑内容不会在已有库上执行："
                    "现查真库确认效果、缺则写补齐迁移，再登记到 app/core/migration_drift_ledger.py"
                ),
            )
            for d in unexplained_checksum_drift(drifts)
        ]

    @staticmethod
    def _camel_to_snake(s: str) -> str:
        import re
        s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


async def run_drift_check_with_timeout(
    engine: AsyncEngine,
    timeout_seconds: float = 60.0,
) -> list[DriftItem]:
    """启动时调用：执行 drift 扫描 + 写库，超时不阻塞启动。"""
    detector = SchemaDriftDetector(engine)
    try:
        items = await asyncio.wait_for(detector.scan(), timeout=timeout_seconds)
        await detector.write_log(items)
        return items
    except asyncio.TimeoutError:
        logger.warning("[SchemaDrift] 扫描超时 %ds，跳过", timeout_seconds)
        return []
    except Exception as e:
        logger.warning("[SchemaDrift] 扫描失败（不阻塞启动）: %s", e)
        return []
