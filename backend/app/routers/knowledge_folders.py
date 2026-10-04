"""知识库文件夹与文档管理 API

支持树形目录、文档 CRUD、项目组权限、批量操作。
CRUD 钩子：upload/update/delete 后触发向量索引联动（修 §21.3.1 断裂）。
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.knowledge_access_policy import (
    KnowledgeAccessPolicy,
    KnowledgeAccessSubject,
    KnowledgeResource,
    KnowledgeWritePolicy,
)
from app.models.knowledge_models import KnowledgeAccessLevel
from app.services.knowledge_folder_service import (
    KnowledgeDocumentService,
    KnowledgeFolderService,
    normalize_folder_create_input,
)
from app.services.knowledge_upload_service import (
    extract_text_with_ocr as _extract_text_with_ocr,
    store_uploaded_files,
)
from app.services.wp_visibility.denial import ExternalNotFound

_logger = logging.getLogger(__name__)


#: 可见但无管理权时的 403 文案（资源对该用户可见，不构成存在性枚举）
_MANAGE_DENIED = "只有资料的创建者或系统管理员可以执行此操作"
_READONLY_DENIED = "只读账号不能修改知识库"


def _require_write_role(current_user: User) -> None:
    """知识资产写动作的角色上界：系统角色 readonly 一律 403（spec knowledge-base-retrieval-and-authz-closure 6.4）。"""
    if not KnowledgeWritePolicy.role_allows_write(getattr(current_user, "role", None)):
        raise HTTPException(status_code=403, detail=_READONLY_DENIED)


async def _authorize_folder_create(
    db: AsyncSession, current_user: User, folder_id: UUID
) -> None:
    """创建类入口的知识资产写权限门（Feature dsh-agent-panel-integration Req 2.1/2.5）。

    只取判权三元组 → 判定 → 拒绝；不存在与无权对外同构为不可枚举 404，
    绝不在拒绝前读取文件夹 name / 文档正文。可见但角色为 readonly → 403。
    """
    subject = await KnowledgeAccessPolicy.resolve_subject(db, current_user)
    folder = await KnowledgeAccessPolicy.load_folder_permission(db, folder_id)
    if folder is None or not KnowledgeAccessPolicy.can_create_in_folder(subject, folder):
        raise ExternalNotFound()
    _require_write_role(current_user)


async def _authorize_folder_manage(
    db: AsyncSession, current_user: User, folder_id: UUID
) -> KnowledgeAccessSubject:
    """文件夹删除 / 重命名：不可读 → 404；可读但非创建者且非管理员（或 readonly）→ 403。"""
    subject = await KnowledgeAccessPolicy.resolve_subject(db, current_user)
    folder = await KnowledgeAccessPolicy.load_folder_permission(db, folder_id)
    if folder is None or not KnowledgeAccessPolicy.can_read(subject, folder):
        raise ExternalNotFound()
    if not KnowledgeWritePolicy.can_manage(
        subject, visible=True, owner_id=folder.created_by, role=getattr(current_user, "role", None)
    ):
        raise HTTPException(status_code=403, detail=_MANAGE_DENIED)
    return subject


async def _authorize_document_read(
    db: AsyncSession, current_user: User, doc_id: UUID
) -> tuple[KnowledgeAccessSubject, KnowledgeResource]:
    """文档预览 / 下载 / 管理前置：不可读（含不存在、已删除）→ 404 同构。"""
    subject = await KnowledgeAccessPolicy.resolve_subject(db, current_user)
    perm = await KnowledgeAccessPolicy.load_document_permission(db, doc_id)
    if perm is None or not KnowledgeAccessPolicy.can_read_document(subject, perm[0], perm[1]):
        raise ExternalNotFound()
    return subject, perm[0]


async def _document_chain(db: AsyncSession, doc_id: UUID) -> list:
    """文档所在版本链（同文件夹同名的未删除版本；AT-3 版本链的定义口径）。"""
    from app.models.knowledge_models import KnowledgeDocument as _KD
    import sqlalchemy as _sa

    anchor = (
        await db.execute(_sa.select(_KD.folder_id, _KD.name).where(_KD.id == doc_id))
    ).one()
    return list(
        (
            await db.execute(
                _sa.select(_KD).where(
                    _KD.folder_id == anchor.folder_id,
                    _KD.name == anchor.name,
                    _KD.is_deleted == _sa.false(),
                )
            )
        ).scalars().all()
    )


def _assert_chain_manageable(chain: list, subject: KnowledgeAccessSubject, current_user: User) -> None:
    """版本链内任一版本无管理权 → 403（改名 / 移动作用于整条链，不能只动一部分）。"""
    role = getattr(current_user, "role", None)
    for version in chain:
        if not KnowledgeWritePolicy.can_manage(
            subject, visible=True, owner_id=version.created_by, role=role
        ):
            raise HTTPException(status_code=403, detail=_MANAGE_DENIED)


router = APIRouter(prefix="/api/knowledge-library", tags=["知识库管理"])


# ---------------------------------------------------------------------------
# 向量索引联动钩子（修 §21.3.1 联动断裂）
# ---------------------------------------------------------------------------

async def _trigger_index_update(
    project_ids: list | None,
    doc_id: UUID,
    content_text: str | None,
    doc_version: int | None = None,
    mark_previous_stale: bool = False,
    previous_doc_id: UUID | None = None,
) -> None:
    """CRUD 提交后触发 incremental_update 建向量索引（可选加速层）。

    非阻塞：失败仅 log 不影响 CRUD 主流程。幂等（R3）：incremental_update 内部 upsert。
    P2-2.2: mark_previous_stale=True 时，先将旧版本索引标记 stale。

    🔴 使用**独立会话**（spec knowledge-base-retrieval-and-authz-closure Req 1.5）：索引写路径在
    当前环境必然失败（无唯一索引承接 ON CONFLICT、embedding 502，见 design §十一），而
    incremental_update 内部会 commit —— 用请求会话执行时，任一语句失败都会让请求会话进入
    aborted，同一请求里后续文件的正文读取随之全部失败。文档本身已在调用前提交，
    独立会话能看到它；索引缺席时检索由文档词法层兜住。
    """
    if not content_text:
        return
    if not project_ids:
        return

    from app.core.database import async_session
    from app.services.knowledge_index_service import KnowledgeIndexService

    async with async_session() as index_db:
        index_svc = KnowledgeIndexService(index_db)

        # P2-2.2: 文档更新后标记旧索引 stale
        if mark_previous_stale and previous_doc_id:
            try:
                await index_svc.mark_index_stale(previous_doc_id)
                await index_db.commit()
            except Exception as exc:
                await index_db.rollback()
                _logger.warning(
                    "[KB Hook] mark_index_stale failed for prev_doc=%s: %s",
                    previous_doc_id, exc,
                )

        for pid in project_ids:
            try:
                await index_svc.incremental_update(
                    project_id=UUID(str(pid)),
                    source_type="knowledge_doc",
                    source_id=doc_id,
                    content=content_text,
                    doc_version=doc_version,
                )
            except Exception as exc:
                await index_db.rollback()
                _logger.warning(
                    "[KB Hook] incremental_update failed for doc=%s project=%s: %s",
                    doc_id, pid, exc,
                )


async def _trigger_index_delete(
    db: AsyncSession,
    doc_id: UUID,
) -> None:
    """删除文档后同步删除向量索引条目。

    非阻塞：失败仅 log 不影响 CRUD 主流程。

    🔴 必须包在 SAVEPOINT 里：本钩子与「软删文档」在**同一事务**、且在 commit 之前执行。
    PostgreSQL 中任一语句失败会让整个事务进入 aborted 状态，此后 COMMIT 等价于 ROLLBACK ——
    只 try/except 吞掉异常，会把调用方已执行的软删一并静默回滚，接口却照样返回「文档已删除」。
    （2026-09-29 真库实测：枚举缺 knowledge_doc 致本 UPDATE 失败，删除接口 200 但文档仍在。）
    SAVEPOINT 让失败只回滚本钩子自己的语句，主事务保持可提交。
    """
    from sqlalchemy import update, func
    from app.models.ai_models import KnowledgeIndex, KnowledgeSourceType

    try:
        async with db.begin_nested():
            await db.execute(
                update(KnowledgeIndex)
                .where(
                    KnowledgeIndex.source_type == KnowledgeSourceType.knowledge_doc,
                    KnowledgeIndex.source_id == doc_id,
                    KnowledgeIndex.is_deleted == False,  # noqa: E712
                )
                .values(is_deleted=True, updated_at=func.now())
            )
    except Exception as exc:
        _logger.warning(
            "[KB Hook] index delete failed for doc=%s: %s", doc_id, exc,
        )


class FolderCreateRequest(BaseModel):
    name: str
    parent_id: str | None = None
    access_level: str = "public"
    project_ids: list[str] | None = None


class DocumentCreateRequest(BaseModel):
    name: str
    content_text: str | None = None
    file_type: str | None = None
    tags: list[str] | None = None
    access_level: str | None = None
    project_ids: list[str] | None = None


@router.get("/tree")
async def get_folder_tree(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取知识库完整文件夹树（权限过滤；每个节点带 ``can_manage`` / ``can_create``）"""
    subject = await KnowledgeAccessPolicy.resolve_subject(db, current_user)
    svc = KnowledgeFolderService(db)
    tree = await svc.get_folder_tree(subject, role=getattr(current_user, "role", None))
    return tree


@router.post("/folders")
async def create_folder(
    data: FolderCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建文件夹（子文件夹须先通过父文件夹的知识资产写权限门）

    入参非法 → 422（中文原因）。项目组文件夹还要求**创建者本人**属于所选项目之一：
    否则按 ``KnowledgeAccessPolicy`` 创建者自己也看不到它，等于建了一个死文件夹。
    """
    try:
        _, level, project_ids = normalize_folder_create_input(
            data.name, data.access_level, data.project_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if data.parent_id:
        await _authorize_folder_create(db, current_user, UUID(data.parent_id))
    else:
        _require_write_role(current_user)

    if level == KnowledgeAccessLevel.project_group:
        subject = await KnowledgeAccessPolicy.resolve_subject(db, current_user)
        requested = frozenset(UUID(pid) for pid in project_ids or [])
        if not subject.is_member_of_any(requested):
            raise HTTPException(
                status_code=422,
                detail="项目组权限的文件夹须包含你参与的项目，否则创建后你自己也无法看到它",
            )

    svc = KnowledgeFolderService(db)
    folder = await svc.create_folder(
        name=data.name,
        parent_id=UUID(data.parent_id) if data.parent_id else None,
        access_level=data.access_level,
        project_ids=project_ids,
        created_by=current_user.id,
    )
    await db.commit()
    return {"id": str(folder.id), "name": folder.name, "message": "文件夹创建成功"}


@router.get("/folders/{folder_id}/documents")
async def list_documents(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出文件夹下的文档（权限过滤；每行带 ``can_manage``，前端据此显示删除/改名/移动）"""
    subject = await KnowledgeAccessPolicy.resolve_subject(db, current_user)
    svc = KnowledgeDocumentService(db)
    docs = await svc.list_documents(folder_id, subject)
    role = getattr(current_user, "role", None)
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "tags": d.tags,
            "version": d.version,
            "access_level": d.access_level.value if d.access_level else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            # 正文为空（扫描件 / 空文件 / 抽取失败）⇒ AI 检索与对话读不到内容，界面据此提示
            # （spec knowledge-upload-robustness-and-consumer-wiring R4.2）
            "has_text": bool(d.content_text and d.content_text.strip()),
            "can_manage": KnowledgeWritePolicy.can_manage(
                subject, visible=True, owner_id=d.created_by, role=role
            ),
        }
        for d in docs
    ]


@router.post("/folders/{folder_id}/documents")
async def create_document(
    folder_id: UUID,
    data: DocumentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建文档（文本内容；先过知识资产写权限门）"""
    await _authorize_folder_create(db, current_user, folder_id)
    svc = KnowledgeDocumentService(db)
    doc = await svc.create_document(
        folder_id=folder_id,
        name=data.name,
        content_text=data.content_text,
        file_type=data.file_type,
        tags=data.tags,
        access_level=data.access_level,
        project_ids=data.project_ids,
        created_by=current_user.id,
    )
    await db.commit()

    # §21.3.1 联动钩子：创建文档后触发向量索引（独立会话，失败不影响本请求）
    await _trigger_index_update(data.project_ids, doc.id, data.content_text)

    return {"id": str(doc.id), "name": doc.name, "message": "文档创建成功"}


async def _insert_document_isolated(db: AsyncSession, svc: "KnowledgeDocumentService", **fields):
    """单个文件写库，在 SAVEPOINT 内执行：失败只回滚本文件（R1.1）。

    🔴 flush 失败（PG 约束 / 编码错误）会让整个事务 aborted：只 try/except 吞异常时，
    同批后续文件全部 ``PendingRollbackError``、末尾 commit 抛出 —— 单个文件的问题被放大成
    整批丢失（2026-09-30 真库实测）。独立成函数便于真库守卫换回旧实现做反向对照。
    """
    async with db.begin_nested():
        return await svc.create_document(**fields)


async def _store_uploaded_files(
    db: AsyncSession,
    folder_id: UUID,
    files: list[UploadFile],
    current_user: User,
    background_tasks: BackgroundTasks | None,
) -> dict:
    """文件夹上传与项目上传共用的写入管线（实现见 ``knowledge_upload_service.store_uploaded_files``）。

    三个协作者按**本模块属性**在调用时取值注入：真库守卫替换的是本模块的
    ``_insert_document_isolated`` / ``_trigger_index_update``，替换必须作用于生产路径。
    """
    return await store_uploaded_files(
        db,
        folder_id,
        files,
        current_user,
        background_tasks,
        insert_document=_insert_document_isolated,
        extract_text=_extract_text_with_ocr,
        trigger_index_update=_trigger_index_update,
    )


@router.post("/folders/{folder_id}/upload")
async def upload_documents(
    folder_id: UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
):
    """批量上传文档文件（先过知识资产写权限门）"""
    await _authorize_folder_create(db, current_user, folder_id)
    return await _store_uploaded_files(db, folder_id, files, current_user, background_tasks)


@router.post("/projects/{project_id}/upload")
async def upload_project_documents(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    slot: str = "consultation",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    background_tasks: BackgroundTasks = None,
):
    """上传到项目知识文件夹（``{项目名}（项目资料）/ {槽位名}``，项目组可见）。

    spec knowledge-base-retrieval-and-authz-closure 5.7：A17-3 咨询记录的「相关文件」此前上传到
    不存在的 ``/api/knowledge-base/projects/{pid}/documents``，恒失败。项目文件夹由
    ``ensure_project_folder`` 幂等定位；写权限按**项目**判定（edit 权限；admin 放行），
    不按文件夹 —— 系统文件夹 ``created_by`` 为空，创建者规则不适用。
    """
    from app.services.knowledge_folder_service import PROJECT_FOLDER_SLOTS, ensure_project_folder

    if slot not in PROJECT_FOLDER_SLOTS:
        raise HTTPException(status_code=422, detail=f"不支持的项目文件夹：{slot}")
    try:
        folder = await ensure_project_folder(db, project_id, slot)
    except ValueError:
        raise ExternalNotFound() from None
    return await _store_uploaded_files(db, folder.id, files, current_user, background_tasks)


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除文件夹（含子文件夹和文档）。

    不可读 → 404；非创建者且非管理员 / readonly → 403（spec knowledge-base-retrieval-and-authz-closure 6.2）。
    """
    await _authorize_folder_manage(db, current_user, folder_id)
    svc = KnowledgeFolderService(db)
    await svc.delete_folder(folder_id)
    await db.commit()
    return {"message": "文件夹已删除"}


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除文档（单个版本）。

    不可读 → 404；非创建者且非管理员 / readonly → 403（spec knowledge-base-retrieval-and-authz-closure 6.2）。
    """
    subject, document = await _authorize_document_read(db, current_user, doc_id)
    if not KnowledgeWritePolicy.can_manage(
        subject, visible=True, owner_id=document.created_by, role=getattr(current_user, "role", None)
    ):
        raise HTTPException(status_code=403, detail=_MANAGE_DENIED)
    svc = KnowledgeDocumentService(db)
    await svc.delete_document(doc_id)

    # §21.3.1 联动钩子：删除文档后同步删向量索引
    await _trigger_index_delete(db, doc_id)

    await db.commit()
    return {"message": "文档已删除"}


@router.post("/init-presets")
async def init_preset_folders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """初始化预制分类文件夹（幂等；只读账号不可执行）"""
    _require_write_role(current_user)
    svc = KnowledgeFolderService(db)
    count = await svc.init_preset_folders()
    await db.commit()
    return {"message": f"初始化了 {count} 个预制文件夹", "created": count}


@router.get("/search")
async def search_documents(
    q: str,
    context: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """知识库页面全文搜索（文档名 / 正文 / 标签；browse 模式：当前用户可读即可见）。

    spec knowledge-base-retrieval-and-authz-closure 6.6 / design §十 C7：旧实现对全部未删除
    文档做 ILIKE、**不做任何权限过滤**，任何登录用户都能枚举他人私有文档的名称。现改走
    与 RAG 同一套词法检索与判定面。``context``（底稿编码 + 科目名）保留为排序加分。
    响应形状向后兼容，追加 ``snippet`` / ``score`` / ``can_manage``。
    """
    from app.services.knowledge_doc_search import DocSearchRequest, KnowledgeDocSearch
    from app.services.knowledge_access_policy import KnowledgeRetrievalMode

    query = (q or "").strip()
    if not query:
        return []
    subject = await KnowledgeAccessPolicy.resolve_subject(db, current_user)
    search = KnowledgeDocSearch(db)
    hits = await search.search(
        DocSearchRequest(
            query=query,
            mode=KnowledgeRetrievalMode.browse,
            subject=subject,
            top_k=50,
            boost_terms=tuple((context or "").split()[:3]),
        )
    )
    paths = await search.folder_paths(h.meta.folder_id for h in hits)
    role = getattr(current_user, "role", None)
    out = []
    for h in hits:
        fp = paths.get(h.meta.folder_id)
        out.append({
            "id": str(h.meta.doc_id),
            "name": h.meta.name,
            "file_type": h.meta.file_type,
            "file_size": h.meta.file_size,
            "folder_name": fp.name if fp else None,
            "folder_path": fp.path if fp else None,
            "folder_id": str(h.meta.folder_id),
            "created_at": h.meta.created_at.isoformat() if h.meta.created_at else None,
            "snippet": h.snippet[:200],
            "score": h.score,
            "can_manage": KnowledgeWritePolicy.can_manage(
                subject, visible=True, owner_id=h.meta.created_by, role=role
            ),
        })
    return out


class RenameRequest(BaseModel):
    name: str


class MoveRequest(BaseModel):
    target_folder_id: str


def _clean_name(raw: str | None, *, max_len: int) -> str:
    from app.models.knowledge_models import strip_nul

    # 先剔 NUL 再判空 / 判长：只含 NUL 的名称不应被当成「有内容」放行
    name = strip_nul(raw or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="名称不能为空")
    if len(name) > max_len:
        raise HTTPException(status_code=422, detail=f"名称不能超过 {max_len} 个字符")
    return name


@router.put("/folders/{folder_id}/rename")
async def rename_folder(
    folder_id: UUID,
    data: RenameRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重命名文件夹（不可读 → 404；非创建者且非管理员 / readonly → 403）"""
    from app.models.knowledge_models import KnowledgeFolder
    from app.services.knowledge_folder_service import FOLDER_NAME_MAX_LEN

    new_name = _clean_name(data.name, max_len=FOLDER_NAME_MAX_LEN)
    await _authorize_folder_manage(db, current_user, folder_id)
    folder = await db.get(KnowledgeFolder, folder_id)
    folder.name = new_name
    await db.commit()
    return {"id": str(folder.id), "name": folder.name, "message": "重命名成功"}


@router.put("/documents/{doc_id}")
async def rename_document(
    doc_id: UUID,
    data: RenameRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重命名文档（作用于整条版本链；spec knowledge-base-retrieval-and-authz-closure 6.3 / 6.5）。

    前端早就调用 ``PUT /documents/{id}`` 改名，后端却没有这条路由（恒 405）。
    版本链 = 同文件夹同名的未删除版本：只改单行会把其余版本留在旧名下，下次同名上传
    接到旧链上（design §十 C8）。目标名已被同文件夹其它文档占用 → 409。
    """
    from app.models.knowledge_models import KnowledgeDocument as _KD
    import sqlalchemy as _sa

    new_name = _clean_name(data.name, max_len=500)
    subject, _ = await _authorize_document_read(db, current_user, doc_id)
    chain = await _document_chain(db, doc_id)
    _assert_chain_manageable(chain, subject, current_user)
    if chain and chain[0].name == new_name:
        return {"id": str(doc_id), "name": new_name, "renamed": 0, "message": "名称未变化"}
    clash = (
        await db.execute(
            _sa.select(_sa.func.count()).select_from(_KD).where(
                _KD.folder_id == chain[0].folder_id,
                _KD.name == new_name,
                _KD.is_deleted == _sa.false(),
            )
        )
    ).scalar_one()
    if clash:
        raise HTTPException(status_code=409, detail="该文件夹下已有同名文档")
    for version in chain:
        version.name = new_name
    await db.commit()
    return {"id": str(doc_id), "name": new_name, "renamed": len(chain), "message": "重命名成功"}


@router.put("/documents/{doc_id}/move")
async def move_document(
    doc_id: UUID,
    data: MoveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """移动文档到其他文件夹（整条版本链一起移动）。

    文档不可读 → 404；目标文件夹不可见 → 404；对目标无创建权 / 链内有无管理权的版本 → 403；
    目标已有同名文档 → 409（否则两条同名链会在目标里合成一条错乱的版本链）。
    """
    from app.models.knowledge_models import KnowledgeDocument as _KD
    import sqlalchemy as _sa

    try:
        target_id = UUID(str(data.target_folder_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="目标文件夹 ID 格式不合法") from None

    subject, _ = await _authorize_document_read(db, current_user, doc_id)
    target = await KnowledgeAccessPolicy.load_folder_permission(db, target_id)
    if target is None or not KnowledgeAccessPolicy.can_read(subject, target):
        raise ExternalNotFound()
    if not KnowledgeWritePolicy.can_create(subject, target, getattr(current_user, "role", None)):
        raise HTTPException(status_code=403, detail="你没有向目标文件夹添加资料的权限")
    chain = await _document_chain(db, doc_id)
    _assert_chain_manageable(chain, subject, current_user)
    if chain[0].folder_id == target_id:
        return {"id": str(doc_id), "new_folder_id": str(target_id), "moved": 0, "message": "已在该文件夹中"}
    clash = (
        await db.execute(
            _sa.select(_sa.func.count()).select_from(_KD).where(
                _KD.folder_id == target_id,
                _KD.name == chain[0].name,
                _KD.is_deleted == _sa.false(),
            )
        )
    ).scalar_one()
    if clash:
        raise HTTPException(status_code=409, detail="目标文件夹下已有同名文档")
    for version in chain:
        version.folder_id = target_id
    await db.commit()
    return {
        "id": str(doc_id),
        "name": chain[0].name,
        "new_folder_id": str(target_id),
        "moved": len(chain),
        "message": "移动成功",
    }


@router.get("/documents/{doc_id}/preview")
async def preview_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """文档预览（返回文本内容或下载链接）。不可读 → 404 同构（旧实现任何登录用户可读任意文档）。"""
    from app.models.knowledge_models import KnowledgeDocument
    from pathlib import Path

    await _authorize_document_read(db, current_user, doc_id)
    doc = await db.get(KnowledgeDocument, doc_id)
    base = {"id": str(doc.id), "name": doc.name, "file_type": doc.file_type, "folder_id": str(doc.folder_id)}

    # 文本类文档直接返回内容
    if doc.content_text:
        return {**base, "preview_type": "text", "content": doc.content_text[:100000]}  # 最多 100K 字符

    # 二进制文档返回下载链接
    if doc.storage_path and Path(doc.storage_path).exists():
        return {
            **base,
            "preview_type": "download",
            "download_url": f"/api/knowledge-library/documents/{doc_id}/download",
        }

    return {**base, "preview_type": "unavailable", "message": "无法预览"}


@router.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载文档文件。不可读 → 404 同构。"""
    from app.models.knowledge_models import KnowledgeDocument
    from fastapi.responses import FileResponse
    from pathlib import Path

    await _authorize_document_read(db, current_user, doc_id)
    doc = await db.get(KnowledgeDocument, doc_id)
    if not doc.storage_path:
        raise HTTPException(status_code=404, detail="该文档没有原始文件")
    file_path = Path(doc.storage_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(file_path, filename=doc.name)
