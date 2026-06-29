"""A17-6 总结会会议纪要 — 结构化数据 ↔ Word 双向同步服务

职责：
- generate_docx(wp_id, project_id, db): 从 checklist_responses → 填充模板 docx → 返回路径
- sync_docx_to_responses(wp_id, project_id, db, user_id): 从 docx 解析 → 回写 DB

设计：
- 模板中以"会议议题"段落后的编号列表(1.~10.)定位各议题边界
- 元信息区以表格形式存在模板中（第一个Table）
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 10项会议议题标题前缀
AGENDA_PREFIXES = [f"{i}." for i in range(1, 11)]
AGENDA_CN_PREFIXES = [f"{i}、" for i in range(1, 11)]

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
TEMPLATE_PATH = _BACKEND_ROOT / "wp_templates" / "A" / "A17-6  总结会会议记要.docx"
STORAGE_BASE = _BACKEND_ROOT / "storage" / "projects"


def _get_project_file(project_id: UUID) -> Path:
    """获取项目级 A17-6 docx 存储路径"""
    return STORAGE_BASE / str(project_id) / "workpapers" / "A" / "A17-6.docx"


def _ensure_project_file(project_id: UUID) -> Path:
    """确保项目存储中有 A17-6 docx（首次从模板复制）"""
    fp = _get_project_file(project_id)
    if not fp.exists():
        fp.parent.mkdir(parents=True, exist_ok=True)
        if TEMPLATE_PATH.exists():
            shutil.copy2(TEMPLATE_PATH, fp)
        else:
            raise FileNotFoundError(f"A17-6 模板不存在: {TEMPLATE_PATH}")
    return fp


def _match_agenda_num(text: str) -> Optional[int]:
    """匹配段落文本对应的议题号（1-10）"""
    text = text.strip()
    for i, (prefix, cn_prefix) in enumerate(zip(AGENDA_PREFIXES, AGENDA_CN_PREFIXES)):
        if text.startswith(prefix) or text.startswith(cn_prefix):
            return i + 1
    return None


def parse_docx(file_path: Path) -> tuple[dict[int, str], dict[str, str]]:
    """从 docx 解析 10 项议题内容 + 元信息

    Returns:
        (agenda_dict, meta_dict)
    """
    from docx import Document

    doc = Document(str(file_path))
    agenda: dict[int, list[str]] = {}
    meta: dict[str, str] = {}
    current_item: Optional[int] = None

    # 解析表格中的元信息（第一个table）
    if doc.tables:
        table = doc.tables[0]
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) >= 2:
                key = cells[0].replace("：", "").replace(":", "").strip()
                val = cells[1].strip() if len(cells) > 1 else ""
                if "被审计单位" in key or "单位名称" in key:
                    meta["client_name"] = val
                elif "索引" in key:
                    meta["index_no"] = val
                elif "截止日" in key or "会计期间" in key or "期间" in key:
                    meta["period"] = val
                elif "编制人" in key:
                    meta["preparer"] = val
                elif "复核人" in key:
                    meta["reviewer"] = val
                elif "会议地点" in key or "地点" in key:
                    meta["meeting_place"] = val
                elif "会议时间" in key or "时间" in key:
                    meta["meeting_time"] = val
                elif "组织者" in key:
                    meta["organizer"] = val
                elif "召开" in key or "召集" in key:
                    meta["convener"] = val
                elif "记录" in key:
                    meta["recorder"] = val

    # 解析段落中的10项议题
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        item_num = _match_agenda_num(text)
        if item_num:
            current_item = item_num
            # 议题标题后的同行内容
            # 去掉编号前缀取剩余文本
            for prefix in AGENDA_PREFIXES + AGENDA_CN_PREFIXES:
                if text.startswith(prefix):
                    remaining = text[len(prefix):].strip()
                    # 去掉议题标题（找到第一个句号或逗号后的内容）
                    agenda[current_item] = []
                    if remaining:
                        # 有些模板议题标题和内容在同一段落
                        agenda[current_item].append(remaining)
                    break
        elif current_item is not None:
            agenda.setdefault(current_item, []).append(text)

    agenda_result = {k: "\n".join(v) for k, v in agenda.items() if v}
    return agenda_result, meta


async def generate_docx(wp_id: UUID, project_id: UUID, db: AsyncSession) -> Path:
    """从 checklist_responses 读取数据，填充到 docx 模板，返回文件路径"""
    from docx import Document

    # 1. 确保项目文件存在
    file_path = _ensure_project_file(project_id)

    # 2. 从 DB 加载数据
    result = await db.execute(
        sa.text(
            "SELECT item_id, conclusion, remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE 'a176-%'"
        ),
        {"wp_id": str(wp_id)},
    )

    meta_values: dict[str, str] = {}
    agenda_values: dict[int, str] = {}

    for row in result.fetchall():
        item_id = row.item_id
        if item_id.startswith("a176-meta-"):
            key = item_id.removeprefix("a176-meta-")
            meta_values[key] = row.conclusion or row.remark or ""
        elif item_id.startswith("a176-agenda-"):
            try:
                idx = int(item_id.removeprefix("a176-agenda-"))
                if 1 <= idx <= 10:
                    agenda_values[idx] = row.remark or row.conclusion or ""
            except ValueError:
                pass

    # 3. 打开模板文件并填充
    doc = Document(str(file_path))

    # 3a. 填充表格元信息（第一个表格）
    if doc.tables:
        table = doc.tables[0]
        for row in table.rows:
            cells = row.cells
            if len(cells) >= 2:
                key_text = cells[0].text.strip().replace("：", "").replace(":", "")
                if "被审计单位" in key_text or "单位名称" in key_text:
                    if meta_values.get("client_name"):
                        cells[1].text = meta_values["client_name"]
                elif "截止日" in key_text or "会计期间" in key_text:
                    if meta_values.get("period"):
                        cells[1].text = meta_values["period"]
                elif "编制人" in key_text:
                    if meta_values.get("preparer"):
                        cells[1].text = meta_values["preparer"]
                elif "复核人" in key_text:
                    if meta_values.get("reviewer"):
                        cells[1].text = meta_values["reviewer"]
                elif "会议地点" in key_text or "地点" in key_text:
                    if meta_values.get("meeting_place"):
                        cells[1].text = meta_values["meeting_place"]
                elif "会议时间" in key_text or "时间" in key_text:
                    if meta_values.get("meeting_time"):
                        cells[1].text = meta_values["meeting_time"]
                elif "组织者" in key_text:
                    if meta_values.get("organizer"):
                        cells[1].text = meta_values["organizer"]
                elif "召开" in key_text or "召集" in key_text:
                    if meta_values.get("convener"):
                        cells[1].text = meta_values["convener"]
                elif "记录" in key_text:
                    if meta_values.get("recorder"):
                        cells[1].text = meta_values["recorder"]

    # 3b. 填充议题内容（定位段落中的编号列表）
    current_item: Optional[int] = None
    item_start_indices: dict[int, int] = {}
    item_end_indices: dict[int, int] = {}

    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        item_num = _match_agenda_num(text)
        if item_num:
            if current_item is not None:
                item_end_indices[current_item] = i
            current_item = item_num
            item_start_indices[current_item] = i + 1

    if current_item is not None:
        item_end_indices[current_item] = len(doc.paragraphs)

    # 对每个有新内容的议题，在其后续段落中写入
    for idx, content in agenda_values.items():
        if idx not in item_start_indices or not content:
            continue
        start = item_start_indices[idx]
        end = item_end_indices.get(idx, start)

        lines = content.split("\n")
        for para_idx in range(start, end):
            if lines:
                doc.paragraphs[para_idx].text = lines.pop(0)
            else:
                doc.paragraphs[para_idx].text = ""

        # 多余行追加到最后一个段落
        if lines:
            last_idx = min(end - 1, len(doc.paragraphs) - 1)
            if last_idx >= start:
                doc.paragraphs[last_idx].text += "\n" + "\n".join(lines)

    # 4. 保存
    doc.save(str(file_path))
    logger.info("A17-6 docx generated: %s", file_path)
    return file_path


async def sync_docx_to_responses(
    wp_id: UUID, project_id: UUID, db: AsyncSession, user_id: UUID
) -> int:
    """从项目存储的 docx 解析内容，回写到 checklist_responses"""
    from datetime import datetime, timezone

    file_path = _get_project_file(project_id)
    if not file_path.exists():
        logger.warning("A17-6 docx 不存在，无法同步: %s", file_path)
        return 0

    agenda_dict, meta_dict = parse_docx(file_path)
    if not agenda_dict and not meta_dict:
        return 0

    now = datetime.now(timezone.utc)
    count = 0

    # 回写 meta
    for key, value in meta_dict.items():
        if not value:
            continue
        item_id = f"a176-meta-{key}"
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, updated_by, created_at, updated_at)
                VALUES (:pid, :wp_id, :item_id, :conclusion, NULL, :uid, :now, :now)
                ON CONFLICT (wp_id, item_id) DO UPDATE SET
                    conclusion = EXCLUDED.conclusion,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = EXCLUDED.updated_at
            """),
            {"pid": str(project_id), "wp_id": str(wp_id), "item_id": item_id, "conclusion": value, "uid": str(user_id), "now": now},
        )
        count += 1

    # 回写 agenda
    for idx, content in agenda_dict.items():
        if not content.strip():
            continue
        item_id = f"a176-agenda-{idx}"
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, updated_by, created_at, updated_at)
                VALUES (:pid, :wp_id, :item_id, NULL, :remark, :uid, :now, :now)
                ON CONFLICT (wp_id, item_id) DO UPDATE SET
                    remark = EXCLUDED.remark,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = EXCLUDED.updated_at
            """),
            {"pid": str(project_id), "wp_id": str(wp_id), "item_id": item_id, "remark": content, "uid": str(user_id), "now": now},
        )
        count += 1

    await db.commit()
    logger.info("A17-6 docx→responses synced %d items", count)
    return count
