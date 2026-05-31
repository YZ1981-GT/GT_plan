"""StandardUnificationService — 多准则状态统一源读写服务

Requirements: 1.2, 1.3, 1.4, 1.5
Spec: multi-standard-unification

建立项目"适用准则"的单一结构化真理源 `projects.applicable_standard_v2`：

    {
        "entity_type": "soe" | "listed" | "private",
        "scope": "standalone" | "consolidated",
        "stage": "normal" | "ipo" | "transfer" | "restructure" | "fraud_response",
    }

核心职责：
- ``get_standard``：读取统一准则源（优先 v2，缺失时从 wizard_state / 旧字段推断回退）
- ``set_standard``：写入 v2（权威）+ 双写旧字段（迁移期向后兼容）+ 发 STANDARD_CHANGED 事件
- ``derive_from_wizard``：从 wizard_state.basic_info.data 推断结构化 standard

设计要点：
- 永不返回 None：``get_standard`` 始终返回结构化 dict（向后兼容，需求 1.3/1.4）
- JSONB 变更需重新赋值新 dict / flag_modified 才能被 SQLAlchemy 检测（在 ``set_standard`` 中处理）
"""
from __future__ import annotations

import copy
import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.core import Project
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 准则维度合法取值（与 requirements.md 需求 1.1 一致）
# ---------------------------------------------------------------------------

VALID_ENTITY_TYPES = ("soe", "listed", "private")
VALID_SCOPES = ("standalone", "consolidated")
VALID_STAGES = ("normal", "ipo", "transfer", "restructure", "fraud_response")

# 默认结构化 standard（无法推断时使用，需求 6.3）
DEFAULT_STANDARD: dict[str, str] = {
    "entity_type": "soe",
    "scope": "standalone",
    "stage": "normal",
}


class StandardUnificationService:
    """统一准则状态源读写服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    async def get_standard(self, project_id: UUID) -> dict:
        """读取项目的统一准则状态。

        优先读 ``applicable_standard_v2``；若为空则从 ``wizard_state`` /
        旧字段（template_type / report_scope / scenario）推断回退。

        始终返回结构化 dict（永不返回 None），保证各模块向后兼容
        （需求 1.3、1.4）。
        """
        project = await self._get_project(project_id)
        return self._read_standard(project)

    def derive_from_wizard(self, wizard_state: dict | None) -> dict:
        """从向导状态推断结构化 standard（纯函数，无 DB / 无副作用）。

        读取 ``wizard_state.basic_info.data`` 下的 ``template_type`` /
        ``report_scope``（以及可选的 ``stage`` / ``scenario``）映射为结构化
        准则；缺失或非法值时回退到默认值
        ``{entity_type: "soe", scope: "standalone", stage: "normal"}``。

        需求 1.2。
        """
        basic: dict = {}
        if wizard_state:
            basic = (wizard_state or {}).get("basic_info", {}).get("data", {}) or {}

        template_type = str(basic.get("template_type") or "").lower()
        report_scope = str(basic.get("report_scope") or "").lower()
        # stage 可来自向导的 stage 或 scenario 字段，缺失则默认 normal
        stage_raw = str(basic.get("stage") or basic.get("scenario") or "").lower()

        return {
            "entity_type": template_type if template_type in VALID_ENTITY_TYPES else DEFAULT_STANDARD["entity_type"],
            "scope": report_scope if report_scope in VALID_SCOPES else DEFAULT_STANDARD["scope"],
            "stage": stage_raw if stage_raw in VALID_STAGES else DEFAULT_STANDARD["stage"],
        }

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    async def set_standard(
        self,
        project_id: UUID,
        new_standard: dict,
        changed_by: UUID,
        year: int | None = None,
    ) -> dict:
        """写入统一准则状态（权威源）+ 双写旧字段 + 发 STANDARD_CHANGED 事件。

        步骤：
        1. 读取当前 standard 作为 ``old_standard``
        2. 写 ``applicable_standard_v2``（权威）
        3. 双写旧字段 ``template_type`` / ``report_scope``（迁移期向后兼容，需求 1.4）
           并同步 ``wizard_state.basic_info.data`` 中的对应字段
        4. 提交
        5. 发 ``STANDARD_CHANGED`` 事件（``publish_immediate`` 不经 debounce，需求 1.5）

        返回归一化后的新 standard。
        """
        project = await self._get_project(project_id)

        # 1. 捕获旧状态（在任何变更之前）
        old_standard = self._read_standard(project)

        # 归一化新 standard，确保三个维度齐全且合法
        normalized = self._normalize_standard(new_standard)

        # 2. 写权威源（赋新 dict 以便 SQLAlchemy 检测 JSONB 变更）
        project.applicable_standard_v2 = dict(normalized)

        # 3. 双写旧字段（迁移期向后兼容）
        project.template_type = normalized["entity_type"]
        project.report_scope = normalized["scope"]

        # 同步 wizard_state 嵌套字段（深拷贝 + 重新赋值 + flag_modified
        # 确保 JSONB 就地变更被 SQLAlchemy 检测）
        if project.wizard_state:
            ws = copy.deepcopy(project.wizard_state)
            basic_info = ws.setdefault("basic_info", {})
            if not isinstance(basic_info, dict):
                basic_info = {}
                ws["basic_info"] = basic_info
            data = basic_info.setdefault("data", {})
            if not isinstance(data, dict):
                data = {}
                basic_info["data"] = data
            data["template_type"] = normalized["entity_type"]
            data["report_scope"] = normalized["scope"]
            project.wizard_state = ws
            flag_modified(project, "wizard_state")

        # 4. flush（本方法只 flush 不 commit，事务提交由调用方（router/wizard）统一管理。）
        await self.db.flush()

        logger.info(
            "StandardUnificationService: project %s standard %s -> %s (changed_by=%s)",
            project_id,
            old_standard,
            normalized,
            changed_by,
        )

        # 5. 发 STANDARD_CHANGED 事件（立即触发，不经 debounce）
        payload = EventPayload(
            event_type=EventType.STANDARD_CHANGED,
            project_id=project_id,
            year=year,
            extra={
                "old_standard": old_standard,
                "new_standard": normalized,
                "changed_by": str(changed_by),
            },
        )
        await event_bus.publish_immediate(payload)

        return normalized

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _read_standard(self, project: Project) -> dict:
        """从已加载的 Project 读取结构化准则（v2 优先，否则回退推断）。"""
        v2 = project.applicable_standard_v2
        if isinstance(v2, dict) and v2:
            return self._normalize_standard(v2)
        return self._derive_from_project(project)

    def _derive_from_project(self, project: Project) -> dict:
        """从项目的 wizard_state + 旧字段推断结构化准则。

        以 ``wizard_state`` 推断为基础，再用项目上的旧专用列
        （template_type / report_scope / scenario）覆盖（这些列为权威迁移源）。
        """
        derived = self.derive_from_wizard(project.wizard_state)

        if project.template_type:
            tt = str(project.template_type).lower()
            if tt in VALID_ENTITY_TYPES:
                derived["entity_type"] = tt

        if project.report_scope:
            rs = str(project.report_scope).lower()
            if rs in VALID_SCOPES:
                derived["scope"] = rs

        scenario = getattr(project, "scenario", None)
        if scenario:
            sc = str(scenario).lower()
            if sc in VALID_STAGES:
                derived["stage"] = sc

        return derived

    @staticmethod
    def _normalize_standard(standard: dict | None) -> dict:
        """归一化结构化 standard：补齐缺失维度、非法值回退默认。

        保证返回的 dict 始终含 entity_type / scope / stage 三个合法维度。
        """
        src = standard if isinstance(standard, dict) else {}

        entity_type = str(src.get("entity_type") or "").lower()
        scope = str(src.get("scope") or "").lower()
        stage = str(src.get("stage") or "").lower()

        return {
            "entity_type": entity_type if entity_type in VALID_ENTITY_TYPES else DEFAULT_STANDARD["entity_type"],
            "scope": scope if scope in VALID_SCOPES else DEFAULT_STANDARD["scope"],
            "stage": stage if stage in VALID_STAGES else DEFAULT_STANDARD["stage"],
        }

    async def _get_project(self, project_id: UUID) -> Project:
        """加载项目，不存在则抛 ValueError。"""
        result = await self.db.execute(
            sa.select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        return project
