"""知识库访问策略 · 公共单一真源（Task 1 / 组件 KnowledgeAccessPolicy）

Feature: dsh-agent-panel-integration
Requirements:
  - 2.1：私有 ContextBuilder 方法 SHALL NOT 充当跨路由授权 API —— 本模块把
    ``ContextBuilder._check_folder_access`` / ``_check_doc_access`` / ``_user_has_access``
    与 ``KnowledgeFolderService.list_folders`` / ``KnowledgeDocumentService.list_documents``
    中三份重复的 access-level 判定收敛为唯一公共 policy。
  - 2.2：复用平台既有知识库可见性语义，不新造第二套权限算法。
  - 2.5：无权与不存在对外同构（调用方负责非枚举响应；本模块只回布尔判定）。
Design: "Components and Interfaces → 1. ResourceAccessResolver"（"知识库需提取公开 policy
  service，tree/list/read/create 共用"）。

**单一真源**：知识资源（folder / document）的可见性与创建权判定只在本模块实现。
``tree`` / ``list`` / ``read`` / ``create`` 四类入口都必须显式传入 ``KnowledgeAccessSubject``
（current user + project scope），不允许再出现"不传 subject 就不过滤"的旁路。

**纯判定 + 一次取数**：``resolve_subject()`` 做唯一一次 IO（读 ``ProjectUser`` 项目成员关系），
其余全部是纯函数，便于在授权前完成判定、在读取 label/正文前拒绝。

**角色不参与本模块**：角色只是动作上界（见 ``app.services.ai_chat.access``），
知识库可见性由 access_level + 项目成员关系 + 创建者决定；``admin`` 不在本层自动绕过
（与既有实现一致，Req 2.2 "不因角色自动绕过知识库或资源级权限"）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ProjectUser
from app.models.knowledge_models import (
    KnowledgeAccessLevel,
    KnowledgeDocument,
    KnowledgeFolder,
)

logger = logging.getLogger(__name__)

__all__ = [
    "KnowledgeAccessSubject",
    "KnowledgeResource",
    "KnowledgeAccessPolicy",
    "ANONYMOUS_SUBJECT",
]


def _coerce_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _coerce_project_ids(raw: Any) -> frozenset[UUID]:
    """把 JSONB ``project_ids``（可能是 str/UUID 混合列表）规范为 ``frozenset[UUID]``。

    无法解析的元素被丢弃（fail-closed：解析不出的项目 ID 不构成允许项）。
    """
    if not raw:
        return frozenset()
    if isinstance(raw, (str, UUID)):
        raw = [raw]
    out: set[UUID] = set()
    try:
        for item in raw:
            parsed = _coerce_uuid(item)
            if parsed is not None:
                out.add(parsed)
    except TypeError:  # 非可迭代 → 空集（fail-closed）
        return frozenset()
    return frozenset(out)


@dataclass(frozen=True)
class KnowledgeAccessSubject:
    """判定主体：当前用户 + 其项目成员范围（不可变）。

    - ``user_id``：None 表示未认证/无有效身份 —— private 资源恒不可见、创建恒被拒。
    - ``project_ids``：该用户 active ``ProjectUser`` 的项目集合（project_group 判定用）。
    """

    user_id: UUID | None
    project_ids: frozenset[UUID] = frozenset()

    def is_member_of_any(self, project_ids: frozenset[UUID]) -> bool:
        return bool(self.project_ids & project_ids)


#: 无身份主体（未认证 / 身份解析失败）。private 不可见、project_group 不可见、无创建权。
ANONYMOUS_SUBJECT = KnowledgeAccessSubject(user_id=None, project_ids=frozenset())


@dataclass(frozen=True)
class KnowledgeResource:
    """folder / document 的归一化权限视图（只含判定所需字段，不含 label/正文）。

    ``access_level is None`` 只对 document 有效，表示"继承文件夹权限"。
    """

    access_level: KnowledgeAccessLevel | None
    project_ids: frozenset[UUID]
    created_by: UUID | None

    @classmethod
    def of_folder(cls, folder: KnowledgeFolder) -> "KnowledgeResource":
        return cls(
            access_level=folder.access_level,
            project_ids=_coerce_project_ids(folder.project_ids),
            created_by=_coerce_uuid(folder.created_by),
        )

    @classmethod
    def of_document(cls, document: KnowledgeDocument) -> "KnowledgeResource":
        return cls(
            access_level=document.access_level,
            project_ids=_coerce_project_ids(document.project_ids),
            created_by=_coerce_uuid(document.created_by),
        )

    @classmethod
    def of_row(
        cls,
        access_level: KnowledgeAccessLevel | str | None,
        project_ids: Any,
        created_by: Any,
    ) -> "KnowledgeResource":
        """从裸 SQL row 字段构造（避免调用方为了判权而先 SELECT 整行正文）。"""
        level: KnowledgeAccessLevel | None
        if access_level is None or isinstance(access_level, KnowledgeAccessLevel):
            level = access_level
        else:
            try:
                level = KnowledgeAccessLevel(str(access_level))
            except ValueError:
                # 未知 access_level → fail-closed（当 private 处理：非创建者一律不可见）
                logger.warning("未知 knowledge access_level: %r（fail-closed）", access_level)
                level = KnowledgeAccessLevel.private
        return cls(
            access_level=level,
            project_ids=_coerce_project_ids(project_ids),
            created_by=_coerce_uuid(created_by),
        )


class KnowledgeAccessPolicy:
    """知识库可见性/创建权唯一判定面（纯函数 + 一个 subject 解析器）。"""

    # ------------------------------------------------------------------
    # subject 解析（唯一 IO）
    # ------------------------------------------------------------------
    @staticmethod
    async def resolve_subject(db: AsyncSession, user: Any) -> KnowledgeAccessSubject:
        """解析当前用户的判定主体（项目成员关系来自 active ``ProjectUser``）。

        用户缺失/无 id → ``ANONYMOUS_SUBJECT``。查询异常 → 只保留 user_id、项目集合为空
        （fail-closed：project_group 资源不可见，private 仍归创建者）。
        """
        user_id = _coerce_uuid(getattr(user, "id", None))
        if user_id is None:
            return ANONYMOUS_SUBJECT
        try:
            rows = (
                await db.execute(
                    sa.select(ProjectUser.project_id).where(
                        ProjectUser.user_id == user_id,
                        ProjectUser.is_deleted == sa.false(),
                    )
                )
            ).scalars().all()
        except Exception as exc:  # noqa: BLE001 — 成员关系查询失败 → 空集（fail-closed）
            logger.warning("知识库 subject 解析失败 user=%s: %s", user_id, exc)
            return KnowledgeAccessSubject(user_id=user_id, project_ids=frozenset())
        return KnowledgeAccessSubject(
            user_id=user_id,
            project_ids=frozenset(p for p in (_coerce_uuid(r) for r in rows) if p is not None),
        )

    # ------------------------------------------------------------------
    # 读判定
    # ------------------------------------------------------------------
    @staticmethod
    def can_read(subject: KnowledgeAccessSubject, resource: KnowledgeResource) -> bool:
        """单个资源的可见性判定（``access_level is None`` 视为"继承"，由调用方先判父级）。

        - ``public``：全所可见。
        - ``project_group``：subject 至少属于资源声明的一个项目。
        - ``private``：仅创建者。
        - 其他（含 None 的裸调用）：None 表示继承 → 由 ``can_read_document`` 处理；
          未知取值在 ``KnowledgeResource.of_row`` 已 fail-closed 收敛为 private。
        """
        level = resource.access_level
        if level is None or level == KnowledgeAccessLevel.public:
            return True
        if level == KnowledgeAccessLevel.project_group:
            return subject.is_member_of_any(resource.project_ids)
        if level == KnowledgeAccessLevel.private:
            return subject.user_id is not None and resource.created_by == subject.user_id
        return False

    @staticmethod
    def can_read_folder(
        subject: KnowledgeAccessSubject, folder: KnowledgeFolder
    ) -> bool:
        """文件夹可见性（folder.access_level 非空，不存在继承语义）。"""
        return KnowledgeAccessPolicy.can_read(subject, KnowledgeResource.of_folder(folder))

    @staticmethod
    def can_read_document(
        subject: KnowledgeAccessSubject,
        document: KnowledgeResource,
        folder: KnowledgeResource | None,
    ) -> bool:
        """文档可见性：文档自身 access_level 优先；为 None 时**完整继承**文件夹三元组。

        与旧 ``list_documents`` 的差异（有意修正）：
          1. 旧实现在文档 access_level 为 None 时直接放行，依赖"文件夹已在 list_folders
             过滤过"的假设 —— 而 route 从未传 subject，假设不成立。此处显式判定父文件夹。
          2. 旧实现对 ``private`` 文档没有 owner 分支，创建者也看不到自己的私有文档。
             此处与 ``_user_has_access`` 的完整语义统一（private → 创建者可见）。
        """
        if document.access_level is None:
            if folder is None:
                return False  # 继承但父级未知 → fail-closed
            return KnowledgeAccessPolicy.can_read(subject, folder)
        return KnowledgeAccessPolicy.can_read(subject, document)

    # ------------------------------------------------------------------
    # 写判定（知识资产创建）
    # ------------------------------------------------------------------
    @staticmethod
    def can_create_in_folder(
        subject: KnowledgeAccessSubject, folder: KnowledgeResource
    ) -> bool:
        """能否在该文件夹下创建知识资产（文档/子文件夹）。

        资源级要求：必须有有效身份 **且** 对目标文件夹可见。角色上界另由
        ``app.services.ai_chat.access`` 的 action capability 施加（Req 2.2：角色只作上界）。
        """
        if subject.user_id is None:
            return False
        return KnowledgeAccessPolicy.can_read(subject, folder)

    # ------------------------------------------------------------------
    # 批量过滤（tree / list 共用）
    # ------------------------------------------------------------------
    @staticmethod
    def filter_folders(
        subject: KnowledgeAccessSubject, folders: list[KnowledgeFolder]
    ) -> list[KnowledgeFolder]:
        return [f for f in folders if KnowledgeAccessPolicy.can_read_folder(subject, f)]

    @staticmethod
    def filter_documents(
        subject: KnowledgeAccessSubject,
        documents: list[KnowledgeDocument],
        folder: KnowledgeResource | None,
    ) -> list[KnowledgeDocument]:
        return [
            d
            for d in documents
            if KnowledgeAccessPolicy.can_read_document(
                subject, KnowledgeResource.of_document(d), folder
            )
        ]

    # ------------------------------------------------------------------
    # 授权后的取数（先判权，再读 label/正文）
    # ------------------------------------------------------------------
    @staticmethod
    async def load_folder_permission(
        db: AsyncSession, folder_id: UUID
    ) -> KnowledgeResource | None:
        """只取判权三元组（不取 name / description / 文档正文）。

        返回 None 表示文件夹不存在或已软删 —— 调用方对"不存在"与"无权"使用同一非枚举响应。
        """
        row = (
            await db.execute(
                sa.select(
                    KnowledgeFolder.access_level,
                    KnowledgeFolder.project_ids,
                    KnowledgeFolder.created_by,
                ).where(
                    KnowledgeFolder.id == folder_id,
                    KnowledgeFolder.is_deleted == sa.false(),
                )
            )
        ).first()
        if row is None:
            return None
        return KnowledgeResource.of_row(row[0], row[1], row[2])

    @staticmethod
    async def load_document_permission(
        db: AsyncSession, document_id: UUID
    ) -> tuple[KnowledgeResource, KnowledgeResource | None] | None:
        """只取文档与其父文件夹的判权三元组（不取 name / content_text / summary）。

        返回 ``(document, folder)``；文档不存在/已软删返回 None。
        """
        row = (
            await db.execute(
                sa.select(
                    KnowledgeDocument.access_level,
                    KnowledgeDocument.project_ids,
                    KnowledgeDocument.created_by,
                    KnowledgeFolder.access_level.label("folder_access_level"),
                    KnowledgeFolder.project_ids.label("folder_project_ids"),
                    KnowledgeFolder.created_by.label("folder_created_by"),
                )
                .outerjoin(KnowledgeFolder, KnowledgeDocument.folder_id == KnowledgeFolder.id)
                .where(
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.is_deleted == sa.false(),
                )
            )
        ).first()
        if row is None:
            return None
        document = KnowledgeResource.of_row(row[0], row[1], row[2])
        folder: KnowledgeResource | None = None
        if row[3] is not None or row[4] is not None or row[5] is not None:
            folder = KnowledgeResource.of_row(row[3], row[4], row[5])
        return document, folder
