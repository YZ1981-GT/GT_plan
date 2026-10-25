"""知识库上传写入管线 + 正文抽取链（从 ``routers/knowledge_folders.py`` 抽出）。

spec: knowledge-upload-robustness-and-consumer-wiring（R1 逐文件容错 / R2 解码 / R3 落盘名）
+ knowledge-base-retrieval-and-authz-closure（5.7 项目知识文件夹上传共用本管线）。

抽出原因：路由文件超过行数门禁（800）。🔴 **协作者由路由注入、不在本模块直接引用**：
真库守卫 ``test_knowledge_upload_robustness_pg.py`` 把路由模块上的 ``_insert_document_isolated``
换成无 SAVEPOINT 的旧实现做反向对照，并断言「现行路径 is 生产函数」；上传类测试替换路由上的
``_trigger_index_update`` 隔离索引钩子。若本模块自己 import 这些函数，替换点就落不到生产路径上，
守卫会在不知情中验证别的东西。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.services.knowledge_folder_service import KnowledgeDocumentService

_logger = logging.getLogger("app.routers.knowledge_folders")

#: 单文件写库（须在 SAVEPOINT 内执行）：``(db, svc, **fields) -> KnowledgeDocument``
InsertDocument = Callable[..., Awaitable[Any]]
#: 非纯文本正文抽取：``(file_path, content, filename_lower) -> str | None``
ExtractText = Callable[[str, bytes, str], Awaitable[str | None]]
#: 提交后的索引钩子：``(project_ids, doc_id, content_text, **kw) -> None``（失败不抛）
TriggerIndexUpdate = Callable[..., Awaitable[None]]


async def extract_text_with_ocr(
    file_path: str, content: bytes, filename_lower: str
) -> str | None:
    """提取文档全文 → Markdown 文本

    多级降级链：
      1. **anydoc**（Rust，毫秒级，含旧格式 .doc/.xls/.ppt）—— 主路径
      2. **MarkItDown**（纯 Python，补 anydoc 不覆盖的 HTML/JSON/XML）
      3. **MinerU OCR**（扫描件 PDF；由 anydoc 的 needs_ocr 信号**精准触发**）
      4. **pypdf / python-docx** —— 最后兜底（pypdf 是 PyPDF2 的延续，后者已停更且未声明依赖）

    设计要点：
      - anydoc 对图片型 PDF 明确回 "no extractable text ... OCR is required"，
        据此**跳过无意义的 markitdown 尝试直接进 OCR**，而不是盲目走完整条链。
      - anydoc 报 permanent（Encrypted / 真正不支持的格式）时同样不再往下试。
      - 其它扩展名（.txt/.md）由调用方直读，不进本函数。
    """
    _log = _logger
    needs_ocr = False

    # ── 主路径：anydoc（Rust，快且覆盖旧二进制格式） ──
    try:
        from app.services.anydoc_service import convert_bytes_detailed

        res = convert_bytes_detailed(content, filename_lower)
        if res.ok and res.text:
            _log.info(
                "[KB Extract] anydoc extracted %d chars from %s", len(res.text), file_path
            )
            return res.text

        needs_ocr = res.needs_ocr
        if res.needs_ocr:
            # 扫描件：markitdown 同样无文本层可提，直接进 OCR 分支
            _log.info("[KB Extract] anydoc says OCR required for %s", file_path)
        elif res.permanent:
            # 加密 / 格式确实不支持：记录后不再重试其他引擎
            _log.info(
                "[KB Extract] anydoc permanent failure (%s) for %s: %s",
                res.error_code, file_path, res.message[:160],
            )
            return None
        else:
            _log.info(
                "[KB Extract] anydoc miss (%s), trying MarkItDown for %s",
                res.error_code, file_path,
            )
    except Exception as exc:
        _log.warning("[KB Extract] anydoc failed (%s), trying MarkItDown for %s", exc, file_path)

    # ── 降级 1：MarkItDown（补 anydoc 不支持的格式；扫描件跳过） ──
    if not needs_ocr:
        try:
            from app.services.markitdown_service import convert_bytes_to_markdown

            md_text = convert_bytes_to_markdown(content, filename_lower)
            if md_text:
                _log.info(
                    "[KB Extract] MarkItDown extracted %d chars from %s",
                    len(md_text),
                    file_path,
                )
                return md_text
            _log.info("[KB Extract] MarkItDown empty/unsupported, trying fallback for %s", file_path)
        except Exception as exc:
            _log.warning("[KB Extract] MarkItDown failed (%s), trying fallback for %s", exc, file_path)

    # ── 降级 2：MinerU OCR（扫描件 PDF） ──
    if filename_lower.endswith(".pdf"):
        try:
            from app.services.mineru_service import MinerUService

            mineru = MinerUService()
            if await mineru.is_available():
                result = await mineru.recognize_for_ocr(file_path)
                text = (result.get("text") or "").strip()
                if text:
                    _log.info(
                        "[KB Extract] MinerU OCR extracted %d chars from %s",
                        len(text),
                        file_path,
                    )
                    return text[:50000]
                _log.warning("[KB Extract] MinerU returned empty text, falling back for %s", file_path)
            elif needs_ocr:
                # 已确知是扫描件却没有可用 OCR 引擎：显式记录 ERROR，
                # 别让调用方把「抽取为空」误当成「文档本身没内容」
                from app.core.config import settings as _settings

                _log.error(
                    "[KB Extract] %s 是扫描件但 MinerU 不可用（MINERU_ENABLED=%s），"
                    "文本抽取为空并非文档本身无内容",
                    file_path,
                    getattr(_settings, "MINERU_ENABLED", "?"),
                )
        except Exception as exc:
            _log.warning("[KB Extract] MinerU failed (%s), falling back for %s", exc, file_path)

    # ── 降级 3：pypdf / python-docx ──
    try:
        if filename_lower.endswith(".pdf"):
            import io
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            pages_text = []
            for page in reader.pages[:50]:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            fallback_text = "\n".join(pages_text).strip()
            if fallback_text:
                _log.info("[KB Extract] pypdf fallback extracted %d chars", len(fallback_text))
                return fallback_text[:50000]
        elif filename_lower.endswith(".docx"):
            import io
            from docx import Document as DocxDocument

            doc_obj = DocxDocument(io.BytesIO(content))
            paragraphs = [p.text for p in doc_obj.paragraphs if p.text.strip()]
            fallback_text = "\n".join(paragraphs).strip()
            if fallback_text:
                _log.info("[KB Extract] python-docx fallback extracted %d chars", len(fallback_text))
                return fallback_text[:50000]
    except Exception as exc:
        _log.warning("[KB Extract] Fallback extraction also failed: %s", exc)

    return None


def _knowledge_storage_base(folder_id: UUID):
    from app.core.config import settings
    from pathlib import Path

    storage_root = Path(settings.STORAGE_ROOT)
    if not storage_root.is_absolute():
        # 相对路径时，确保相对于 backend/ 目录
        backend_root = Path(__file__).resolve().parent.parent.parent
        storage_root = backend_root / settings.STORAGE_ROOT
    base = storage_root / "knowledge" / str(folder_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


#: 落盘名里保留的原名字节上限：唯一前缀 33 + 150 + 20 ≤ 255（ext4 单个文件名上限，按字节计）
_DISK_NAME_STEM_MAX = 150
_DISK_NAME_SUFFIX_MAX = 20
_UNSAFE_DISK_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _truncate_utf8(text: str, max_bytes: int) -> str:
    raw = text.encode("utf-8")
    return text if len(raw) <= max_bytes else raw[:max_bytes].decode("utf-8", errors="ignore")


def disk_file_name(display_name: str) -> str:
    """落盘名 = 唯一前缀 + 清洗截断后的原名（保留扩展名）；展示名原样存数据库。

    - 截断按 UTF-8 **字节**：ext4 单个文件名上限 255 字节，中文每字 3 字节，按字符数截会超限；
      超限时 ``open`` 抛错，旧实现把它吞掉 ⇒ 长中文名文件静默上传失败。
    - Windows 保留字符与控制字符替换为 ``_``：``a:b.txt`` 在 NTFS 上会写进备用数据流。
    """
    from pathlib import Path

    p = Path(display_name)
    suffix = _truncate_utf8(p.suffix, _DISK_NAME_SUFFIX_MAX)
    stem = _truncate_utf8(p.stem if p.suffix else p.name, _DISK_NAME_STEM_MAX)
    name = _UNSAFE_DISK_CHARS.sub("_", f"{stem}{suffix}").rstrip(". ")
    return f"{uuid4().hex}_{name}"


def _remove_quietly(path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - 删除失败只记日志
        _logger.warning("[KB Upload] 清理落盘文件失败 %s: %s", path, exc)


#: PostgreSQL SQLSTATE → 界面原因（不回显 SQL 与异常原文：可能含路径与参数）
_SQLSTATE_REASONS: dict[str, str] = {
    "22001": "名称或类型超出长度限制，无法保存",
    "22021": "文件内容含无法存储的字符",
    "22P05": "文件内容含无法存储的字符",
    "23505": "与已有文档冲突，请刷新后重试",
}


def upload_failure_reason(exc: BaseException) -> str:
    """写库失败 → 中文可读原因（spec knowledge-upload-robustness-and-consumer-wiring R1.2）。"""
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate in _SQLSTATE_REASONS:
        return _SQLSTATE_REASONS[sqlstate]
    return "保存失败，请重试；多次失败请联系管理员"


async def store_uploaded_files(
    db: AsyncSession,
    folder_id: UUID,
    files: list[UploadFile],
    current_user: User,
    background_tasks: BackgroundTasks | None,
    *,
    insert_document: InsertDocument,
    extract_text: ExtractText,
    trigger_index_update: TriggerIndexUpdate,
) -> dict:
    """上传落盘 + 文本抽取 + 建文档 + 提交 + 索引钩子（文件夹上传与项目上传共用）。

    调用方必须先完成写权限判定（本函数不判权）。三个协作者由路由注入（见模块 docstring）：
    ``insert_document`` 单文件写库（须自带 SAVEPOINT）· ``extract_text`` 非纯文本正文抽取 ·
    ``trigger_index_update`` 提交后的索引钩子（独立会话、失败不抛）。
    """
    from pathlib import Path

    from app.models.knowledge_models import DOCUMENT_NAME_MAX_LEN, strip_nul
    from app.services.knowledge_folder_service import (
        CONTENT_TEXT_MAX_CHARS,
        PLAIN_TEXT_EXTENSIONS,
        decode_text_bytes,
    )

    svc = KnowledgeDocumentService(db)
    storage_base = _knowledge_storage_base(folder_id)
    _logger.info("[KB Upload] received %d files for folder %s", len(files), folder_id)

    uploaded: list[dict] = []
    #: 逐文件失败明细（中文原因，供界面展示；spec knowledge-upload-robustness-and-consumer-wiring R1.2）
    failed: list[dict] = []
    #: 本请求已落盘的文件：末尾 commit 失败时一并删除，不留孤儿
    written: list[Path] = []
    for file in files:
        if not file.filename:
            _logger.warning("[KB Upload] skipping file with empty filename")
            continue
        # 展示名只取文件名（去掉路径前缀）；落盘名加唯一前缀：
        #   ① 同名重传会建 v2 版本链（AT-3），若落盘名 = 展示名，v2 会**覆盖** v1 的物理文件，
        #      v1 的 storage_path 随之指向新内容 → 历史版本内容静默丢失、回滚取回错字节；
        #   ② 顺带排除 ".." / 盘符等异常文件名拼出目录外路径的可能。
        raw_name = strip_nul(file.filename)
        safe_name = (Path(raw_name).name or raw_name).strip() or "未命名文件"
        if len(safe_name) > DOCUMENT_NAME_MAX_LEN:
            failed.append({
                "filename": f"{safe_name[:60]}…",
                "reason": f"文件名过长（上限 {DOCUMENT_NAME_MAX_LEN} 字），请改名后重传",
            })
            continue
        file_path = storage_base / disk_file_name(safe_name)
        try:
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as exc:  # noqa: BLE001 - 单个文件落盘失败不阻断其他文件
            _logger.warning("[KB Upload] 落盘失败 %s: %s", safe_name, exc)
            _remove_quietly(file_path)
            failed.append({"filename": safe_name, "reason": "文件写入存储失败，请重试"})
            continue
        written.append(file_path)

        # 提取正文（可选，失败不阻断）：纯文本按真实编码解码（GBK / UTF-16 / BOM）；
        # 其余格式走 extract_text（= extract_text_with_ocr：anydoc → MarkItDown → MinerU → 兜底解析）
        content_text = None
        try:
            if Path(safe_name).suffix.lower() in PLAIN_TEXT_EXTENSIONS:
                content_text = decode_text_bytes(content)[:CONTENT_TEXT_MAX_CHARS]
            else:
                content_text = await extract_text(
                    str(file_path), content, safe_name.lower()
                )
        except Exception:  # noqa: BLE001 - 文本提取失败不阻断文件保存
            content_text = None

        try:
            doc = await insert_document(
                db,
                svc,
                folder_id=folder_id,
                name=safe_name,
                file_type=Path(safe_name).suffix or None,
                file_size=len(content),
                storage_path=str(file_path),
                content_text=content_text,
                created_by=current_user.id,
            )
        except Exception as exc:  # noqa: BLE001 - 单个文件写库失败不阻断其他文件
            _logger.warning("[KB Upload] 写库失败 %s: %s", safe_name, exc)
            _remove_quietly(file_path)
            written.remove(file_path)
            failed.append({"filename": safe_name, "reason": upload_failure_reason(exc)})
            continue
        uploaded.append({
            "id": str(doc.id),
            "name": doc.name,
            "filename": doc.name,
            "size": len(content),
            # 只有抽到非空正文才算：扫描件 / 空文件入库后 AI 检索不到它的内容，界面要如实告知
            "text_extracted": bool(content_text and content_text.strip()),
            "version": doc.version,
            "previous_version_id": str(doc.previous_version_id) if doc.previous_version_id else None,
        })

    try:
        await db.commit()
    except Exception:
        for path in written:
            _remove_quietly(path)
        raise

    # §21.3.1 联动钩子：上传文档后触发向量索引（独立会话，失败不影响本请求）
    import sqlalchemy as _sa
    from app.models.knowledge_models import KnowledgeDocument as _KD
    from app.models.knowledge_models import KnowledgeFolder as _KF

    try:
        folder_project_ids = (
            await db.execute(_sa.select(_KF.project_ids).where(_KF.id == folder_id))
        ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        folder_project_ids = None

    for file_info in uploaded:
        try:
            doc_uuid = UUID(file_info["id"])
            if file_info.get("text_extracted"):
                row = (
                    await db.execute(
                        _sa.select(_KD.content_text, _KD.project_ids).where(_KD.id == doc_uuid)
                    )
                ).one_or_none()
                if row:
                    doc_content, doc_project_ids = row
                    # 优先使用文档级 project_ids，否则继承文件夹级
                    effective_pids = doc_project_ids or folder_project_ids
                    # P2-2.2: 文档新版本创建时标记旧版本索引 stale
                    prev_id_str = file_info.get("previous_version_id")
                    prev_id = UUID(prev_id_str) if prev_id_str else None
                    is_version_update = (file_info.get("version") or 1) > 1
                    await trigger_index_update(
                        effective_pids, doc_uuid, doc_content,
                        doc_version=file_info.get("version"),
                        mark_previous_stale=is_version_update,
                        previous_doc_id=prev_id,
                    )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("[KB Hook] upload index hook failed for doc=%s: %s", file_info.get("id"), exc)

    # V119: 触发完整索引流水线 (background task)
    if background_tasks:
        from app.services.indexing_pipeline import run_indexing_pipeline
        for file_info in uploaded:
            background_tasks.add_task(run_indexing_pipeline, UUID(file_info["id"]))

    return {
        "uploaded": len(uploaded),
        "files": uploaded,
        "failed": failed,
        "folder_id": str(folder_id),
    }
