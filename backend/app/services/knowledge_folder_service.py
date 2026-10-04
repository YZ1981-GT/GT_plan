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
from app.services.knowledge_access_policy import (
    KnowledgeAccessPolicy,
    KnowledgeAccessSubject,
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

#: 与 ``KnowledgeFolder.name`` 列宽一致（String(200)），超长在 PG 端是 500 而非可读错误
FOLDER_NAME_MAX_LEN = 200

#: 纯文本类扩展名：正文由 :func:`decode_text_bytes` 按真实编码解码，不走 anydoc / MarkItDown
#: （2026-09-30 实测 anydoc 把 GBK 编码的 CSV 按 Latin-1 解读，正文全成乱码；中文 Windows
#: 下 Excel 另存的 CSV 默认就是 GBK）
PLAIN_TEXT_EXTENSIONS: frozenset[str] = frozenset({".txt", ".md", ".csv"})

#: 正文截断上限（与抽取链 anydoc / MarkItDown / pypdf 口径一致）
CONTENT_TEXT_MAX_CHARS = 50_000


#: 判为 UTF-16 至少需要的 0 字节数（绝对下限）
_UTF16_MIN_ZERO_BYTES = 4


def _utf16_byte_order(sample: bytes) -> str | None:
    """无 BOM 时按 NUL 字节分布猜 UTF-16 字节序。

    UTF-16 里每个 ASCII 字符（换行、数字、字母）都带一个 0 字节，且全部落在同一奇偶位；
    UTF-8 / GBK 文本本身不含 0 字节。要求「一侧 ≥10% 且 ≥4 个、另一侧 ≤2%」。

    🔴 绝对下限不能省：只按比例判时，19 字节的「前半段\\x00后半段」（UTF-8，一个 NUL）
    恰好让一侧占 1/9 ≥ 10%，被误判成 UTF-16 解出乱码（2026-09-30 真库守卫抓到；
    同一句多带 4 个 ASCII 字符的纯函数样本比例不够，侥幸没暴露）。
    """
    half = len(sample) // 2
    if half < 2:
        return None
    even = sample[0::2].count(0)
    odd = sample[1::2].count(0)
    need = max(_UTF16_MIN_ZERO_BYTES, 0.1 * half)
    if odd >= need and even <= 0.02 * half:
        return "utf-16-le"
    if even >= need and odd <= 0.02 * half:
        return "utf-16-be"
    return None


def decode_text_bytes(content: bytes) -> str:
    """纯文本按真实编码解码（spec knowledge-upload-robustness-and-consumer-wiring R3）。

    顺序：BOM（UTF-8 / UTF-16）→ 无 BOM 的 UTF-16（NUL 分布）→ 严格 UTF-8 → GB18030 →
    UTF-8 替换解码。GB18030 是 GBK 的超集，覆盖中文 Windows「记事本 / Excel 另存」的默认编码。

    旧实现一律 ``decode('utf-8', errors='ignore')``：GBK 文本静默变成乱码（上传「成功」
    但 AI 永远检索不到），UTF-16 文本留下大量 NUL 让写库失败。NUL 由 ORM 层统一剔除，
    本函数不重复处理。
    """
    if not content:
        return ""
    if content.startswith(b"\xef\xbb\xbf"):
        return content[3:].decode("utf-8", errors="replace")
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16", errors="replace")
    order = _utf16_byte_order(content[:4096])
    if order:
        return content.decode(order, errors="replace")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        pass
    lossy = content.decode("utf-8", errors="replace")
    # 严格 UTF-8 失败后在「有坏字节的 UTF-8」与 GBK 之间裁决：看合法多字节字符与替换符之比。
    #   · 被截断 / 零星损坏的 UTF-8：合法多字节字符远多于替换符 → 保留 UTF-8
    #   · GBK：按 UTF-8 读几乎每个汉字都变替换符，合法多字节字符寥寥 → 改用 GB18030
    # 不按「替换符占全文比例」判：大半是 ASCII 的 GBK 文件（数字 + 几个中文表头）比例很低，
    # 会被误留在 UTF-8，恰好把仅有的中文变成乱码。
    bad = lossy.count("\ufffd")
    good = sum(1 for ch in lossy if ord(ch) > 0x7F) - bad
    if good >= 4 * bad:
        return lossy
    try:
        return content.decode("gb18030")
    except UnicodeDecodeError:
        return lossy

#: 项目知识文件夹的子槽位（spec knowledge-base-retrieval-and-authz-closure 5.8 / design §六）
PROJECT_FOLDER_SLOTS: dict[str, str] = {
    "ai_notes": "AI 对话笔记",
    "consultation": "A17-3 咨询附件",
}


def _project_root_key(project_id: UUID) -> str:
    return f"project:{project_id}"


def _project_slot_key(project_id: UUID, slot: str) -> str:
    return f"project:{project_id}:{slot}"


async def _find_system_folder(db: AsyncSession, system_key: str) -> KnowledgeFolder | None:
    """按 ``system_key`` 取未删除的系统文件夹（部分唯一索引保证至多一行）。"""
    return (
        await db.execute(
            sa.select(KnowledgeFolder).where(
                KnowledgeFolder.system_key == system_key,
                KnowledgeFolder.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()


async def _ensure_system_folder(
    db: AsyncSession,
    *,
    system_key: str,
    name: str,
    parent_id: UUID | None,
    project_id: UUID,
) -> KnowledgeFolder:
    """按 ``system_key`` 定位或创建系统文件夹（并发安全，不回滚调用方事务）。

    - 先查未删除同键；
    - 无则在 **SAVEPOINT** 内插入并 flush；并发下撞部分唯一索引 → 只回滚该 SAVEPOINT，
      再重查拿到对方建好的那一份。🔴 不得 ``db.rollback()``：那会连调用方已 flush 的写
      （如 AI 笔记的幂等收据）一起回滚（旧 note_service 即此缺陷）。
    - 系统文件夹 ``created_by`` 为空 ⇒ 按管理权规则只有管理员能改名 / 删除。
    """
    from sqlalchemy.exc import IntegrityError

    existing = await _find_system_folder(db, system_key)
    if existing is not None:
        return existing
    folder = KnowledgeFolder(
        id=uuid.uuid4(),
        name=name[:FOLDER_NAME_MAX_LEN],
        parent_id=parent_id,
        system_key=system_key,
        access_level=KnowledgeAccessLevel.project_group,
        project_ids=[str(project_id)],
        created_by=None,
    )
    try:
        async with db.begin_nested():
            db.add(folder)
            await db.flush()
    except IntegrityError:
        # 失败的对象已随 SAVEPOINT 回滚被逐出会话；重查拿到并发方建好的那一份
        existing = await _find_system_folder(db, system_key)
        if existing is None:
            raise
        return existing
    return folder


async def ensure_project_folder(
    db: AsyncSession, project_id: UUID, slot: str
) -> KnowledgeFolder:
    """项目知识文件夹（单一真源）：``{项目名}（项目资料）/ {槽位名}``，均为该项目的项目组可见。

    AI 笔记转存（``slot="ai_notes"``）与 A17-3 咨询附件上传（``slot="consultation"``）共用。
    只 flush 不 commit（调用方统一提交）。项目不存在 → ``ValueError``。
    """
    if slot not in PROJECT_FOLDER_SLOTS:
        raise ValueError(f"未知的项目知识文件夹槽位：{slot}")
    from app.models.core import Project

    project_name = (
        await db.execute(sa.select(Project.name).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project_name is None:
        raise ValueError(f"项目不存在：{project_id}")
    root = await _ensure_system_folder(
        db,
        system_key=_project_root_key(project_id),
        name=f"{project_name}（项目资料）",
        parent_id=None,
        project_id=project_id,
    )
    return await _ensure_system_folder(
        db,
        system_key=_project_slot_key(project_id, slot),
        name=PROJECT_FOLDER_SLOTS[slot],
        parent_id=root.id,
        project_id=project_id,
    )


def normalize_folder_create_input(
    name: str,
    access_level: str,
    project_ids: list[str] | None,
) -> tuple[str, KnowledgeAccessLevel, list[str] | None]:
    """校验并规范化「新建文件夹」入参，返回 ``(name, access_level, project_ids)``。

    不变量：``project_group`` 必须带至少一个合法项目 ID。
    否则 ``KnowledgeAccessPolicy.can_read`` 对任何人（**含创建者本人**）都判不可见 ——
    文件夹一创建就从目录树里消失，后续上传也被写权限门拒绝，用户只看到「建了却找不到/传不上」。

    非法项目 ID 直接拒绝而不是静默丢弃（静默丢弃会把「选错了」伪装成「建成功了」）。

    Raises:
        ValueError: 名称为空/超长、权限级别不支持、项目 ID 非法、项目组未指定项目。
    """
    # 先剔 NUL 再判空：PG 不能存 \x00，只含 NUL 的名称也不应被当成「有内容」
    clean_name = (name or "").replace("\x00", "").strip()
    if not clean_name:
        raise ValueError("文件夹名称不能为空")
    if len(clean_name) > FOLDER_NAME_MAX_LEN:
        raise ValueError(f"文件夹名称不能超过 {FOLDER_NAME_MAX_LEN} 个字符")

    try:
        level = KnowledgeAccessLevel(access_level)
    except ValueError:
        raise ValueError(f"不支持的权限级别：{access_level}") from None

    normalized: list[str] = []
    for raw in project_ids or []:
        try:
            pid = str(UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            raise ValueError(f"项目 ID 格式不合法：{raw}") from None
        if pid not in normalized:
            normalized.append(pid)

    if level == KnowledgeAccessLevel.project_group and not normalized:
        raise ValueError("项目组权限的文件夹必须至少指定一个项目")

    return clean_name, level, (normalized or None)


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
        """创建文件夹

        入参先经 :func:`normalize_folder_create_input` 校验（非法入参抛 ``ValueError``，
        router 映射为 422），保证不会建出「谁都看不见」的文件夹。
        """
        clean_name, level, normalized_ids = normalize_folder_create_input(
            name, access_level, project_ids
        )
        folder = KnowledgeFolder(
            id=uuid.uuid4(),
            name=clean_name,
            parent_id=parent_id,
            access_level=level,
            project_ids=normalized_ids,
            created_by=created_by,
        )
        self.db.add(folder)
        await self.db.flush()
        return folder

    async def list_folders(
        self,
        subject: KnowledgeAccessSubject,
        parent_id: UUID | None = None,
    ) -> list[KnowledgeFolder]:
        """列出文件夹（权限过滤走公共 ``KnowledgeAccessPolicy``）。

        ``subject`` 为必填：调用方必须显式传入 current user + project scope
        （Feature dsh-agent-panel-integration Req 2.1/2.2）。旧签名允许"两个参数都不传
        就不过滤"，等价于匿名可读全部文件夹 —— 该旁路已删除。
        """
        query = sa.select(KnowledgeFolder).where(
            KnowledgeFolder.is_deleted == sa.false(),
        )
        if parent_id:
            query = query.where(KnowledgeFolder.parent_id == parent_id)
        else:
            query = query.where(KnowledgeFolder.parent_id.is_(None))

        result = await self.db.execute(query.order_by(KnowledgeFolder.name))
        folders = list(result.scalars().all())
        return KnowledgeAccessPolicy.filter_folders(subject, folders)

    async def get_folder_tree(
        self, subject: KnowledgeAccessSubject, *, role: object = None
    ) -> list[dict]:
        """获取完整文件夹树（递归；每层都经同一 policy 过滤）。

        每个节点附 ``can_manage``（改名 / 删除）与 ``can_create``（上传 / 新建子文件夹），
        由 ``KnowledgeWritePolicy`` 按当前用户角色判定；``doc_count`` 只计当前用户可读的文档
        （旧实现计全部未删除文档 ⇒ 他人私有文档的数量被泄露）。
        """
        top_folders = await self.list_folders(subject, parent_id=None)
        tree = []
        for folder in top_folders:
            node = await self._build_tree_node(folder, subject, role)
            tree.append(node)
        return tree

    async def _build_tree_node(
        self, folder: KnowledgeFolder, subject: KnowledgeAccessSubject, role: object = None
    ) -> dict:
        """递归构建树节点"""
        from app.services.knowledge_access_policy import KnowledgeResource, KnowledgeWritePolicy

        children = await self.list_folders(subject, parent_id=folder.id)
        child_nodes = []
        for child in children:
            child_nodes.append(await self._build_tree_node(child, subject, role))

        folder_res = KnowledgeResource.of_folder(folder)
        rows = (
            await self.db.execute(
                sa.select(
                    KnowledgeDocument.access_level,
                    KnowledgeDocument.project_ids,
                    KnowledgeDocument.created_by,
                ).where(
                    KnowledgeDocument.folder_id == folder.id,
                    KnowledgeDocument.is_deleted == sa.false(),
                )
            )
        ).all()
        doc_count = sum(
            1
            for access, pids, owner in rows
            if KnowledgeAccessPolicy.can_read_document(
                subject, KnowledgeResource.of_row(access, pids, owner), folder_res
            )
        )

        return {
            "id": str(folder.id),
            "name": folder.name,
            "category": folder.category,
            "access_level": folder.access_level.value,
            "project_ids": folder.project_ids,
            "doc_count": doc_count,
            "is_system": bool(folder.system_key),
            "can_manage": KnowledgeWritePolicy.can_manage(
                subject, visible=True, owner_id=folder.created_by, role=role
            ),
            "can_create": KnowledgeWritePolicy.can_create(subject, folder_res, role),
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
        """创建文档（AT-3：同 (folder_id, name) 第二次创建自动建版本链）"""
        version, prev_id = await self._resolve_version_chain(folder_id, name)
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
            version=version,
            previous_version_id=prev_id,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def _resolve_version_chain(
        self, folder_id: UUID, name: str
    ) -> tuple[int, UUID | None]:
        """计算新版本号 + previous_version_id（AT-3 KB 接入）"""
        latest = (
            await self.db.execute(
                sa.select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.folder_id == folder_id,
                    KnowledgeDocument.name == name,
                    KnowledgeDocument.is_deleted == sa.false(),
                )
                .order_by(KnowledgeDocument.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            return 1, None
        return (latest.version or 1) + 1, latest.id

    async def list_versions(self, doc_id: UUID) -> list[dict]:
        """列出 doc_id 所属版本链（按 version 升序）

        AT-3 KB 接入：通过 doc_id 反查 (folder_id, name) 锁定链
        doc_id 不存在时返回 []
        """
        entry = (
            await self.db.execute(
                sa.select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            )
        ).scalar_one_or_none()
        if entry is None:
            return []
        result = await self.db.execute(
            sa.select(KnowledgeDocument)
            .where(
                KnowledgeDocument.folder_id == entry.folder_id,
                KnowledgeDocument.name == entry.name,
                KnowledgeDocument.is_deleted == sa.false(),
            )
            .order_by(KnowledgeDocument.version.asc())
        )
        return [self._doc_to_dict(d) for d in result.scalars().all()]

    async def rollback_to_version(
        self,
        doc_id: UUID,
        version_id: UUID,
        created_by: UUID | None = None,
    ) -> dict:
        """回滚到指定历史版本：复制旧版本元数据创建 version=N+1 新行

        AT-3 KB 接入：跨链回滚被拒绝（version_id 必须与 doc_id 同链）
        """
        entry = (
            await self.db.execute(
                sa.select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            )
        ).scalar_one_or_none()
        if entry is None:
            raise ValueError(f"doc_id 不存在: {doc_id}")
        target = (
            await self.db.execute(
                sa.select(KnowledgeDocument).where(KnowledgeDocument.id == version_id)
            )
        ).scalar_one_or_none()
        if target is None:
            raise ValueError(f"version_id 不存在: {version_id}")
        if target.folder_id != entry.folder_id or target.name != entry.name:
            raise ValueError(
                f"跨链回滚被拒绝：version_id={version_id} 不属于 doc_id={doc_id} 所在链"
            )

        new_version, prev_id = await self._resolve_version_chain(entry.folder_id, entry.name)
        new_doc = KnowledgeDocument(
            id=uuid.uuid4(),
            folder_id=target.folder_id,
            name=target.name,
            content_text=target.content_text,
            file_type=target.file_type,
            file_size=target.file_size,
            storage_path=target.storage_path,
            tags=target.tags,
            access_level=target.access_level,
            project_ids=target.project_ids,
            created_by=created_by,
            version=new_version,
            previous_version_id=prev_id,
        )
        self.db.add(new_doc)
        await self.db.flush()
        return self._doc_to_dict(new_doc)

    @staticmethod
    def _doc_to_dict(d: KnowledgeDocument) -> dict:
        return {
            "id": str(d.id),
            "folder_id": str(d.folder_id),
            "name": d.name,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "storage_path": d.storage_path,
            "version": getattr(d, "version", 1),
            "previous_version_id": (
                str(d.previous_version_id) if getattr(d, "previous_version_id", None) else None
            ),
            "is_deleted": d.is_deleted,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }

    async def list_documents(
        self,
        folder_id: UUID,
        subject: KnowledgeAccessSubject,
    ) -> list[KnowledgeDocument]:
        """列出文件夹下的文档（权限过滤走公共 ``KnowledgeAccessPolicy``）。

        先判定父文件夹是否可见：不可见（含不存在）直接返回空列表，不读任何文档 name/正文
        （Feature dsh-agent-panel-integration Req 2.1/2.5：拒绝先于 label/正文读取）。
        文档自身 access_level 为 None 时完整继承父文件夹三元组，不再依赖"上层已过滤"假设。
        """
        folder = await KnowledgeAccessPolicy.load_folder_permission(self.db, folder_id)
        if folder is None or not KnowledgeAccessPolicy.can_read(subject, folder):
            return []

        result = await self.db.execute(
            sa.select(KnowledgeDocument).where(
                KnowledgeDocument.folder_id == folder_id,
                KnowledgeDocument.is_deleted == sa.false(),
            ).order_by(KnowledgeDocument.name)
        )
        docs = list(result.scalars().all())
        return KnowledgeAccessPolicy.filter_documents(subject, docs, folder)

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
