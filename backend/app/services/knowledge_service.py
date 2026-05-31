"""
⚠️ DEPRECATED — 计划删除日期：2026-07-01

KnowledgeService（旧文件系统知识库）已废弃。
唯一调用方 reference_doc_service 的降级分支已移除（retrieval-kernel-unification spec Task 1）。

替代方案：
- 知识文件检索 → KnowledgeIndexService.semantic_search(scope="knowledge_doc")
- 知识文件 CRUD → knowledge_folder_service（KnowledgeDocument/KnowledgeFolder 模型）

本文件仅作为 deprecated 标记存在，禁止新增调用。
超过限期（2026-07-01）后应彻底删除本文件。
"""

import warnings

warnings.warn(
    "KnowledgeService 已废弃，将于 2026-07-01 删除。"
    "请使用 KnowledgeIndexService.semantic_search 替代。",
    DeprecationWarning,
    stacklevel=2,
)


class KnowledgeService:
    """DEPRECATED: 旧文件系统知识库服务，禁止新增调用。"""

    @staticmethod
    def list_documents(category: str = "") -> list[dict]:
        """DEPRECATED: 返回空列表，文件系统知识库已废弃。"""
        warnings.warn(
            "KnowledgeService.list_documents 已废弃",
            DeprecationWarning,
            stacklevel=2,
        )
        return []

    @staticmethod
    def get_document_content(category: str, name: str) -> str:
        """DEPRECATED: 返回空字符串，文件系统知识库已废弃。"""
        warnings.warn(
            "KnowledgeService.get_document_content 已废弃",
            DeprecationWarning,
            stacklevel=2,
        )
        return ""
