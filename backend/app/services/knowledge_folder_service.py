"""知识库文件夹与文档管理服务

支持：
- 树形文件夹 CRUD（嵌套）
- 文档 CRUD（单个/批量上传）
- 项目组权限过滤
- 预制分类文件夹初始化
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_models import (
    KnowledgeAccessLevel,
    KnowledgeDocument,
    KnowledgeFolder,
)

logger = logging.getLogger(__name__)

# 预制分类（与现有 knowledge_service 的 9 个分类对应）
PRESET_CATEGORIES = [
    {"category": "workpaper_templates", "name": "底稿模板库"},
    {"category": "regulations", "name": "监管规定库"},
    {"category": "accounting_standards", "name": "会计准则库"},
    {"category": "quality_control", "name": "质控标准库"},
    {"category": "audit_procedures", "name": "审计程序库"},
    {"category": "industry_guides", "name": "行业指引库"},
    {"category": "prompts", "name": "提示词库"},
    {"category": "report_templates", "name": "报告模板库"},
    {"category": "notes", "name": "笔记库"},
]


class KnowledgeFolderService:
    """知识库文件夹管理"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def init_preset_folders(self) -> int:
        """初始化预制分类文件夹（幂等）"""
        count = 0
        for preset in PRESET_CATEGORIES:
            existing = await self.db.execute(
                sa.select(KnowledgeFolder).where(
                    KnowledgeFolder.category == preset["category"],
                    KnowledgeFolder.parent_id.is_(None),
                    KnowledgeFolder.is_deleted == sa.false(),
                )
            )
            if existing.scalar_one_or_none():
                continue
            folder = KnowledgeFolder(
                id=uuid.uuid4(),
                name=preset["name"],
                category=preset["category"],
                parent_id=None,
                access_level=KnowledgeAccessLevel.public,
            )
            self.db.add(folder)
            count += 1
        await self.db.flush()
        return count

    async def create_folder(
        self,
        name: str,
        parent_id: UUID | None = None,
        access_level: str = "public",
        project_ids: list[str] | None = None,
        created_by: UUID | None = None,
    ) -> KnowledgeFolder:
        """创建文件夹"""
        folder = KnowledgeFolder(
            id=uuid.uuid4(),
            name=name,
            parent_id=parent_id,
            access_level=KnowledgeAccessLevel(access_level),
            project_ids=project_ids,
            created_by=created_by,
        )
        self.db.add(folder)
        await self.db.flush()
        return folder

    async def list_folders(
        self,
        parent_id: UUID | None = None,
        user_project_ids: list[UUID] | None = None,
    ) -> list[KnowledgeFolder]:
        """列出文件夹（含权限过滤）"""
        query = sa.select(KnowledgeFolder).where(
            KnowledgeFolder.is_deleted == sa.false(),
        )
        if parent_id:
            query = query.where(KnowledgeFolder.parent_id == parent_id)
        else:
            query = query.where(KnowledgeFolder.parent_id.is_(None))

        result = await self.db.execute(query.order_by(KnowledgeFolder.name))
        folders = list(result.scalars().all())

        # 权限过滤
        if user_project_ids is not None:
            filtered = []
            for f in folders:
                if f.access_level == KnowledgeAccessLevel.public:
                    filtered.append(f)
                elif f.access_level == KnowledgeAccessLevel.project_group:
                    if f.project_ids and any(str(pid) in [str(x) for x in f.project_ids] for pid in user_project_ids):
                        filtered.append(f)
                # private: 只有创建者可见（需要 user_id 参数，暂跳过）
            return filtered

        return folders

    async def get_folder_tree(self, user_project_ids: list[UUID] | None = None) -> list[dict]:
        """获取完整文件夹树（递归）"""
        top_folders = await self.list_folders(parent_id=None, user_project_ids=user_project_ids)
        tree = []
        for folder in top_folders:
            node = await self._build_tree_node(folder, user_project_ids)
            tree.append(node)
        return tree

    async def _build_tree_node(self, folder: KnowledgeFolder, user_project_ids: list[UUID] | None) -> dict:
        """递归构建树节点"""
        children = await self.list_folders(parent_id=folder.id, user_project_ids=user_project_ids)
        child_nodes = []
        for child in children:
            child_nodes.append(await self._build_tree_node(child, user_project_ids))

        # 统计文档数
        doc_count_q = await self.db.execute(
            sa.select(sa.func.count()).select_from(KnowledgeDocument).where(
                KnowledgeDocument.folder_id == folder.id,
                KnowledgeDocument.is_deleted == sa.false(),
            )
        )
        doc_count = doc_count_q.scalar() or 0

        return {
            "id": str(folder.id),
            "name": folder.name,
            "category": folder.category,
            "access_level": folder.access_level.value,
            "project_ids": folder.project_ids,
            "doc_count": doc_count,
            "children": child_nodes,
        }

    async def delete_folder(self, folder_id: UUID) -> None:
        """软删除文件夹（含子文件夹和文档）"""
        # 递归删除子文件夹
        children = await self.db.execute(
            sa.select(KnowledgeFolder).where(
                KnowledgeFolder.parent_id == folder_id,
                KnowledgeFolder.is_deleted == sa.false(),
            )
        )
        for child in children.scalars().all():
            await self.delete_folder(child.id)

        # 软删除文件夹下的文档
        await self.db.execute(
            sa.update(KnowledgeDocument).where(
                KnowledgeDocument.folder_id == folder_id,
            ).values(is_deleted=True)
        )

        # 软删除文件夹本身
        await self.db.execute(
            sa.update(KnowledgeFolder).where(
                KnowledgeFolder.id == folder_id,
            ).values(is_deleted=True)
        )


class KnowledgeDocumentService:
    """知识库文档管理"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_document(
        self,
        folder_id: UUID,
        name: str,
        content_text: str | None = None,
        file_type: str | None = None,
        file_size: int = 0,
        storage_path: str | None = None,
        tags: list[str] | None = None,
        access_level: str | None = None,
        project_ids: list[str] | None = None,
        created_by: UUID | None = None,
    ) -> KnowledgeDocument:
        """创建文档"""
        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            folder_id=folder_id,
            name=name,
            content_text=content_text,
            file_type=file_type,
            file_size=file_size,
            storage_path=storage_path,
            tags=tags,
            access_level=KnowledgeAccessLevel(access_level) if access_level else None,
            project_ids=project_ids,
            created_by=created_by,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def list_documents(
        self,
        folder_id: UUID,
        user_project_ids: list[UUID] | None = None,
    ) -> list[KnowledgeDocument]:
        """列出文件夹下的文档（含权限过滤）"""
        result = await self.db.execute(
            sa.select(KnowledgeDocument).where(
                KnowledgeDocument.folder_id == folder_id,
                KnowledgeDocument.is_deleted == sa.false(),
            ).order_by(KnowledgeDocument.name)
        )
        docs = list(result.scalars().all())

        if user_project_ids is None:
            return docs

        # 权限过滤：文档自身权限 > 继承文件夹权限
        filtered = []
        for doc in docs:
            doc_access = doc.access_level
            if doc_access is None:
                # 继承文件夹权限 — 已在 list_folders 中过滤
                filtered.append(doc)
            elif doc_access == KnowledgeAccessLevel.public:
                filtered.append(doc)
            elif doc_access == KnowledgeAccessLevel.project_group:
                if doc.project_ids and any(str(pid) in [str(x) for x in doc.project_ids] for pid in user_project_ids):
                    filtered.append(doc)
        return filtered

    async def delete_document(self, doc_id: UUID) -> None:
        """软删除文档"""
        await self.db.execute(
            sa.update(KnowledgeDocument).where(
                KnowledgeDocument.id == doc_id,
            ).values(is_deleted=True)
        )

    async def batch_create(
        self,
        folder_id: UUID,
        documents: list[dict],
        created_by: UUID | None = None,
    ) -> int:
        """批量创建文档"""
        count = 0
        for doc_data in documents:
            await self.create_document(
                folder_id=folder_id,
                name=doc_data.get("name", ""),
                content_text=doc_data.get("content_text"),
                file_type=doc_data.get("file_type"),
                file_size=doc_data.get("file_size", 0),
                storage_path=doc_data.get("storage_path"),
                tags=doc_data.get("tags"),
                created_by=created_by,
            )
            count += 1
        return count
