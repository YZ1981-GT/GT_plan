"""SQL Schema 漂移检测器（migration-runner-resilience spec / Sprint 2）

启动时对比 ORM `Base.metadata` 与实际 PG schema，发现以下 4 类漂移并写入
`schema_drift_log` 表：

- ``orm_extra``：ORM 定义了但 DB 缺失的列/表（最高优先，业务接口运行时会 500）
- ``db_extra``：DB 有但 ORM 没定义的列/表（INFO 级，多为历史残留）
- ``type_mismatch``：列存在但类型/可空性不一致（WARN 级，可能数据不一致）
- ``enum_mismatch``：PG enum 缺少 Python Enum 中定义的值（WARN，运行时插入会爆）

`/api/health` 端点消费 `schema_drift_log`，drift>0 → status=degraded → 前端
DegradedBanner 暴露给运维（避免业务 500 才发现）。

设计原则：
- 纯检测，不自动修复（避免误删 / 误改）
- 失败不阻塞启动（异常吞掉 + WARN 日志）
- 60s timeout（防止漏接表卡住启动）
- KNOWN_ALLOWLIST 屏蔽系统/历史残留表
"""

from __future__ import annotations

import asyncio
import enum as _enum_mod
import logging
from dataclasses import dataclass
from typing import Iterable, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("audit_platform.schema_drift")

DriftType = Literal["orm_extra", "db_extra", "type_mismatch", "enum_mismatch"]


@dataclass(frozen=True)
class DriftItem:
    table: str
    column: str | None
    drift_type: DriftType
    detail: str


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
        # 符号约定迁移(V064)产生的备份表，迁移完成后未清理
        "_sign_migration_backup",
        # 科目类别修正迁移(migrate_account_category_correction.py)的回滚备份表，
        # 一次性脚本快照 (project_id,table,record_id,old_category)，需保留以支持 --rollback
        "_category_correction_backup",
    })

    # 列级 allowlist：DB 有但 ORM 不需映射的列（历史残留 / 已弃用）
    KNOWN_COLUMN_ALLOWLIST: frozenset[tuple[str, str]] = frozenset({
        ("cell_annotations", "sheet_name"),       # 旧版列，已被 sheet_id 取代
        ("adjustments", "status"),                # 旧 status 列，业务改用 review_status
        ("projects", "template_version_id"),      # 旧关联列，不再 ORM 映射
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
        """扫描所有 4 类 drift 并返回（已过滤 allowlist）。"""
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

        # 过滤 allowlist + 外部租户表（Metabase/Quartz 共库污染）+ 列级 allowlist
        return [
            it for it in items
            if it.table not in self.KNOWN_ALLOWLIST
            and not self._is_external_tenant_table(it.table)
            and (it.table, it.column) not in self.KNOWN_COLUMN_ALLOWLIST
        ]

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
        """对比 PG enum 类型 vs Python Enum 类。

        策略：找所有继承 ``(str, enum.Enum)`` 的类，按类名 snake_case 推断 PG enum 名，
        若 PG 中存在该 enum 类型，对比值集合。
        """
        items: list[DriftItem] = []

        # 收集 Python enum
        python_enums: dict[str, set[str]] = {}
        try:
            import app.models  # noqa: F401
            for module_name in dir(__import__("app.models", fromlist=["*"])):
                pass  # __init__.py 已经触发 import

            # 遍历 sys.modules 里以 app.models 开头的模块，找 Enum 子类
            import sys
            for mod_name, mod in list(sys.modules.items()):
                if not mod_name.startswith("app.models"):
                    continue
                if mod is None:
                    continue
                for attr_name in dir(mod):
                    obj = getattr(mod, attr_name, None)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, _enum_mod.Enum)
                        and obj is not _enum_mod.Enum
                        and obj.__module__.startswith("app.models")
                    ):
                        # 类名（如 OpinionTypeEnum）→ 推断 PG enum 名
                        # 简单策略：保留原类名 + camel→snake 两版都试
                        class_name = obj.__name__
                        pg_candidates = {
                            class_name,
                            self._camel_to_snake(class_name),
                            self._camel_to_snake(class_name).replace("_enum", ""),
                        }
                        values = {m.value for m in obj}
                        for cand in pg_candidates:
                            python_enums[cand] = values
        except Exception as e:
            logger.warning("[SchemaDrift] 收集 Python Enum 失败: %s", e)
            return items

        if not python_enums:
            return items

        # 查 PG 所有 enum 类型 + 值
        async with self._engine.begin() as conn:
            rows = await conn.execute(text("""
                SELECT t.typname, e.enumlabel
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                ORDER BY t.typname, e.enumsortorder
            """))
            db_enums: dict[str, set[str]] = {}
            for row in rows.fetchall():
                name = row[0]
                val = row[1]
                if name not in db_enums:
                    db_enums[name] = set()
                db_enums[name].add(val)

        # 对比：仅在 Python 和 DB 都存在的 enum 名上做 diff
        for name, py_vals in python_enums.items():
            if name not in db_enums:
                continue
            db_vals = db_enums[name]
            missing_in_db = py_vals - db_vals
            if missing_in_db:
                items.append(DriftItem(
                    table=name, column=None,
                    drift_type="enum_mismatch",
                    detail=f"PG enum {name} 缺少 Python Enum 值: {sorted(missing_in_db)}",
                ))
        return items

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
