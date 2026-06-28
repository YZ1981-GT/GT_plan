"""A17-1 结构化数据 ↔ Word 双向同步服务

职责：
- generate_docx(wp_id, db): 从 checklist_responses 读取 16 章数据 → 填充到模板 docx → 返回文件路径
- parse_docx(file_path): 从 docx 解析 16 章内容 → 返回 {chapter_num: content} dict
- sync_docx_to_responses(wp_id, file_path, db): 解析 docx → 回写 checklist_responses

设计：
- 以 Title 样式段落定位章节边界（稳定：用户在 OO 中不太会删标题）
- 每章内容取 Title 后到下一个 Title 前的所有段落拼接
- 回写时只更新 textarea 类型章节的 remark 字段
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 16 章标题前缀（用于匹配 Title 段落）
CHAPTER_PREFIXES = [
    "一、", "二、", "三、", "四、", "五、", "六、",
    "七、", "八、", "九、", "十、", "十一、", "十二、",
    "十三、", "十四、", "十五、", "十六、",
]

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
TEMPLATE_PATH = _BACKEND_ROOT / "wp_templates" / "A" / "A17-1 重大事项概要汇总.docx"
STORAGE_BASE = _BACKEND_ROOT / "storage" / "projects"


def _get_project_file(project_id: UUID) -> Path:
    """获取项目级 A17-1 docx 存储路径"""
    return STORAGE_BASE / str(project_id) / "workpapers" / "A" / "A17-1.docx"


def _ensure_project_file(project_id: UUID) -> Path:
    """确保项目存储中有 A17-1 docx（首次从模板复制）"""
    fp = _get_project_file(project_id)
    if not fp.exists():
        fp.parent.mkdir(parents=True, exist_ok=True)
        if TEMPLATE_PATH.exists():
            shutil.copy2(TEMPLATE_PATH, fp)
        else:
            raise FileNotFoundError(f"A17-1 模板不存在: {TEMPLATE_PATH}")
    return fp


def _match_chapter_num(text: str) -> Optional[int]:
    """匹配标题文本对应的章节号（1-16）"""
    text = text.strip()
    for i, prefix in enumerate(CHAPTER_PREFIXES):
        if text.startswith(prefix):
            return i + 1
    return None


def parse_docx(file_path: Path) -> dict[int, str]:
    """从 docx 解析 16 章内容，返回 {chapter_num: content_text}"""
    from docx import Document

    doc = Document(str(file_path))
    chapters: dict[int, list[str]] = {}
    current_ch: Optional[int] = None

    for para in doc.paragraphs:
        if para.style.name == "Title":
            ch_num = _match_chapter_num(para.text)
            if ch_num:
                current_ch = ch_num
                chapters[current_ch] = []
                continue
            else:
                # 非章节标题（如"附件："），停止
                current_ch = None
        elif current_ch is not None:
            text = para.text.strip()
            if text:
                chapters[current_ch].append(text)

    return {k: "\n".join(v) for k, v in chapters.items()}


async def generate_docx(wp_id: UUID, project_id: UUID, db: AsyncSession) -> Path:
    """从 checklist_responses 读取 16 章数据，填充到 docx 模板，返回文件路径"""
    from docx import Document

    # 1. 确保项目文件存在（首次复制模板）
    file_path = _ensure_project_file(project_id)

    # 2. 从 DB 加载 textarea 章节内容
    result = await db.execute(
        sa.text(
            "SELECT item_id, conclusion, remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE 'a171-ch%'"
        ),
        {"wp_id": str(wp_id)},
    )
    ch_contents: dict[int, str] = {}
    ch_tables: dict[int, list[dict]] = {}  # ch6, ch8
    ch_yn: dict[int, dict] = {}  # ch9-12

    for row in result.fetchall():
        item_id = row.item_id
        if item_id.endswith("-content"):
            try:
                num_str = item_id.removeprefix("a171-ch").removesuffix("-content")
                ch_num = int(num_str)
                if 1 <= ch_num <= 16 and row.remark:
                    ch_contents[ch_num] = row.remark
            except (ValueError, AttributeError):
                pass
        elif item_id.endswith("-table"):
            try:
                num_str = item_id.removeprefix("a171-ch").removesuffix("-table")
                ch_num = int(num_str)
                if row.remark:
                    import json
                    data = json.loads(row.remark)
                    if isinstance(data, list):
                        ch_tables[ch_num] = data
            except (ValueError, json.JSONDecodeError):
                pass
        elif item_id.endswith("-yn"):
            try:
                num_str = item_id.removeprefix("a171-ch").removesuffix("-yn")
                ch_num = int(num_str)
                ch_yn[ch_num] = {"answer": row.conclusion, "explanation": row.remark}
            except ValueError:
                pass

    # 2b. 特殊处理第三章：从独立 item_id 组装成文本
    # GtA171Chapter3 组件用 a171-ch3-toggle/s1-rows/s2-materiality/s2-conclusion/s3-hours
    ch3_items: dict[str, str] = {}
    try:
        ch3_result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'a171-ch3-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in ch3_result.fetchall():
            ch3_items[row.item_id] = row.conclusion or row.remark or ""
    except Exception:
        pass

    if ch3_items.get("a171-ch3-toggle") == "N" or not ch3_items.get("a171-ch3-toggle"):
        ch_contents[3] = "审计工作按总体审计策略进行，本期未对审计计划做重大修改。"
    else:
        parts = []
        # 区块1：修改轮次
        if ch3_items.get("a171-ch3-s1-applicable") != "N":
            rows_json = ch3_items.get("a171-ch3-s1-rows", "")
            if rows_json:
                try:
                    import json as _json
                    mod_rows = _json.loads(rows_json)
                    if isinstance(mod_rows, list) and mod_rows:
                        parts.append("1、对审计计划的修改及理由\n")
                        for i, r in enumerate(mod_rows):
                            parts.append(f"第{i+1}次修改：{r.get('time', '')} 原计划：{r.get('original', '')} → 修改为：{r.get('updated', '')} 理由：{r.get('reason', '')} 程序：{r.get('procedure', '')}")
                except Exception:
                    pass
        # 区块2：重要性水平
        if ch3_items.get("a171-ch3-s2-applicable") != "N":
            parts.append("\n2、重要性水平的再评估\n")
            mat_json = ch3_items.get("a171-ch3-s2-materiality", "")
            if mat_json:
                try:
                    import json as _json
                    mat_data = _json.loads(mat_json)
                    if isinstance(mat_data, list):
                        labels = ["确定基准", "PM", "TE", "SAD"]
                        for i, m in enumerate(mat_data):
                            label = labels[i] if i < len(labels) else f"项{i+1}"
                            parts.append(f"{label}：计划={m.get('plan', '')} 完成={m.get('actual', '')}")
                except Exception:
                    pass
            conclusion = ch3_items.get("a171-ch3-s2-conclusion", "")
            if conclusion:
                parts.append(f"分析结论：{conclusion}")
        # 区块3：工时
        if ch3_items.get("a171-ch3-s3-applicable") != "N":
            hours = ch3_items.get("a171-ch3-s3-hours", "")
            if hours:
                parts.append(f"\n3、项目完成工时情况\n{hours}")
        ch_contents[3] = "\n".join(parts) if parts else "审计工作按总体审计策略进行，本期未对审计计划做重大修改。"

    # 3. 打开 docx，定位各章节并替换内容
    doc = Document(str(file_path))
    current_ch: Optional[int] = None
    ch_start_indices: dict[int, int] = {}  # chapter_num → first content paragraph index
    ch_end_indices: dict[int, int] = {}    # chapter_num → last content paragraph index (exclusive)

    # 第一遍：找到各章的段落范围
    for i, para in enumerate(doc.paragraphs):
        if para.style.name == "Title":
            ch_num = _match_chapter_num(para.text)
            if ch_num:
                if current_ch is not None:
                    ch_end_indices[current_ch] = i
                current_ch = ch_num
                ch_start_indices[current_ch] = i + 1
            else:
                if current_ch is not None:
                    ch_end_indices[current_ch] = i
                current_ch = None

    # 最后一章的结束
    if current_ch is not None:
        ch_end_indices[current_ch] = len(doc.paragraphs)

    # 第二遍：对有新内容的章节，清空原内容段落并写入新内容
    # 注意：只处理 textarea 类型章节（1-5, 7, 13-16），table/yn 章节不覆盖
    TEXTAREA_CHAPTERS = {1, 2, 3, 4, 5, 7, 13, 14, 15, 16}

    for ch_num in sorted(ch_contents.keys()):
        if ch_num not in TEXTAREA_CHAPTERS:
            continue
        if ch_num not in ch_start_indices:
            continue

        content = ch_contents[ch_num]
        start = ch_start_indices[ch_num]
        end = ch_end_indices.get(ch_num, start)

        # 清空现有内容段落（保留第一个段落用于写入）
        if start < end:
            # 保留第一个段落，修改其文本
            doc.paragraphs[start].text = content.split("\n")[0] if content else ""
            # 其余段落清空
            lines = content.split("\n")[1:] if content else []
            for idx in range(start + 1, end):
                if lines:
                    doc.paragraphs[idx].text = lines.pop(0)
                else:
                    doc.paragraphs[idx].text = ""

            # 如果新内容行数 > 可用段落数，追加到最后一个段落
            if lines:
                remaining = "\n".join(lines)
                last_idx = min(end - 1, len(doc.paragraphs) - 1)
                doc.paragraphs[last_idx].text += "\n" + remaining

    # 3b. 写入 table 章节 (ch6, ch8) — 在对应章节 Title 后的段落中写为文本表格
    for ch_num, rows in ch_tables.items():
        if ch_num not in ch_start_indices or not rows:
            continue
        start = ch_start_indices[ch_num]
        end = ch_end_indices.get(ch_num, start)
        # 将表格数据格式化为文本行
        if ch_num == 6:
            lines = ["【风险应对措施执行情况表】"]
            for row in rows:
                risk = row.get("risk", "")
                response = row.get("response", "")
                result_text = row.get("result", "")
                conclusion = row.get("conclusion", "")
                if risk:
                    lines.append(f"• 风险：{risk}")
                    if response: lines.append(f"  应对：{response}")
                    if result_text: lines.append(f"  执行：{result_text}")
                    if conclusion: lines.append(f"  结论：{conclusion}")
        elif ch_num == 8:
            lines = ["【已审财务报表分析表】"]
            for row in rows:
                item = row.get("item", "")
                amount = row.get("amount", "")
                note = row.get("note", "")
                if item:
                    lines.append(f"• {item}：{amount or ''} {note or ''}")
        else:
            continue
        content = "\n".join(lines)
        if start < end:
            doc.paragraphs[start].text = content

    # 3c. 写入 yn 章节 (ch9-12) — 结论性文字
    YN_TEMPLATES = {
        9: ("经审计，关联方及关联方交易不存在重大错报。", "经审计，关联方及关联方交易存在以下情况需关注："),
        10: ("经评估，被审计单位持续经营假设运用适当，不存在重大不确定性。", "经评估，被审计单位持续经营存在以下重大不确定性："),
        11: ("经审计，期后事项不存在需要调整或披露的事项。", "经审计，期后事项存在以下需要关注的情况："),
        12: ("不适用（非上市公司审计）。", "拟在审计报告中沟通以下关键审计事项："),
    }
    for ch_num, yn_data in ch_yn.items():
        if ch_num not in ch_start_indices:
            continue
        start = ch_start_indices[ch_num]
        end = ch_end_indices.get(ch_num, start)
        answer = yn_data.get("answer")
        explanation = yn_data.get("explanation") or ""
        templates = YN_TEMPLATES.get(ch_num)
        if not templates:
            continue
        if answer == "N":
            text = templates[0]
        elif answer == "Y":
            text = templates[1] + ("\n" + explanation if explanation else "")
        else:
            text = ""
        if text and start < end:
            doc.paragraphs[start].text = text

    # 4. 保存
    doc.save(str(file_path))
    logger.info("A17-1 docx generated: %s (chapters: %s)", file_path, list(ch_contents.keys()))
    return file_path


async def sync_docx_to_responses(
    wp_id: UUID, project_id: UUID, db: AsyncSession, user_id: UUID
) -> int:
    """从项目存储的 docx 解析内容，回写到 checklist_responses"""
    from datetime import datetime, timezone
    import json

    file_path = _get_project_file(project_id)
    if not file_path.exists():
        logger.warning("A17-1 docx 不存在，无法同步: %s", file_path)
        return 0

    chapters = parse_docx(file_path)
    if not chapters:
        return 0

    now = datetime.now(timezone.utc)
    count = 0

    # textarea 章节（跳过 ch3，它有独立 item_id）
    TEXTAREA_CHAPTERS = {1, 2, 4, 5, 7, 13, 14, 15, 16}
    for ch_num, content in chapters.items():
        if ch_num not in TEXTAREA_CHAPTERS:
            continue
        if not content.strip():
            continue

        item_id = f"a171-ch{ch_num}-content"
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

    # ch3 特殊处理：从 docx 文本解析回独立 item_id
    ch3_text = chapters.get(3, "")
    if ch3_text:
        # 判断是否有修改
        has_mod = "未对审计计划做重大修改" not in ch3_text
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, updated_by, created_at, updated_at)
                VALUES (:pid, :wp_id, 'a171-ch3-toggle', :conclusion, NULL, :uid, :now, :now)
                ON CONFLICT (wp_id, item_id) DO UPDATE SET
                    conclusion = EXCLUDED.conclusion, updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at
            """),
            {"pid": str(project_id), "wp_id": str(wp_id), "conclusion": "Y" if has_mod else "N", "uid": str(user_id), "now": now},
        )
        # 如果有修改，把完整文本存入工时字段作为参考（用户切回结构化视图后可重新整理）
        if has_mod:
            await db.execute(
                sa.text("""
                    INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, updated_by, created_at, updated_at)
                    VALUES (:pid, :wp_id, 'a171-ch3-s3-hours', NULL, :remark, :uid, :now, :now)
                    ON CONFLICT (wp_id, item_id) DO UPDATE SET
                        remark = EXCLUDED.remark, updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at
                """),
                {"pid": str(project_id), "wp_id": str(wp_id), "remark": ch3_text, "uid": str(user_id), "now": now},
            )
        count += 1

    # table 章节 (ch6, ch8) — 从文本反解析
    TABLE_CHAPTERS = {6, 8}
    for ch_num in TABLE_CHAPTERS:
        content = chapters.get(ch_num, "")
        if not content:
            continue
        rows = _parse_table_from_text(ch_num, content)
        if rows:
            item_id = f"a171-ch{ch_num}-table"
            await db.execute(
                sa.text("""
                    INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, updated_by, created_at, updated_at)
                    VALUES (:pid, :wp_id, :item_id, NULL, :remark, :uid, :now, :now)
                    ON CONFLICT (wp_id, item_id) DO UPDATE SET
                        remark = EXCLUDED.remark,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = EXCLUDED.updated_at
                """),
                {"pid": str(project_id), "wp_id": str(wp_id), "item_id": item_id, "remark": json.dumps(rows, ensure_ascii=False), "uid": str(user_id), "now": now},
            )
            count += 1

    # yn 章节 (ch9-12) — 从文本判断 Y/N
    YN_CHAPTERS = {9, 10, 11, 12}
    YN_NEGATIVE_KEYWORDS = ["不存在", "不适用", "未发现", "不存在重大"]
    for ch_num in YN_CHAPTERS:
        content = chapters.get(ch_num, "")
        if not content:
            continue
        # 判断是否为否定结论
        answer = "N" if any(kw in content for kw in YN_NEGATIVE_KEYWORDS) else "Y"
        explanation = content if answer == "Y" else None
        item_id = f"a171-ch{ch_num}-yn"
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, updated_by, created_at, updated_at)
                VALUES (:pid, :wp_id, :item_id, :conclusion, :remark, :uid, :now, :now)
                ON CONFLICT (wp_id, item_id) DO UPDATE SET
                    conclusion = EXCLUDED.conclusion,
                    remark = EXCLUDED.remark,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = EXCLUDED.updated_at
            """),
            {"pid": str(project_id), "wp_id": str(wp_id), "item_id": item_id, "conclusion": answer, "remark": explanation, "uid": str(user_id), "now": now},
        )
        count += 1

    await db.commit()
    logger.info("A17-1 docx→responses synced %d chapters", count)
    return count


def _parse_table_from_text(ch_num: int, content: str) -> list[dict]:
    """从 docx 解析出的文本中反解析表格数据"""
    rows: list[dict] = []
    lines = content.split("\n")

    if ch_num == 6:
        # 格式: • 风险：xxx / 应对：xxx / 执行：xxx / 结论：xxx
        current: dict = {}
        for line in lines:
            line = line.strip()
            if line.startswith("• 风险：") or line.startswith("•风险："):
                if current.get("risk"):
                    rows.append(current)
                current = {"risk": line.split("：", 1)[1] if "：" in line else "", "response": "", "result": "", "conclusion": ""}
            elif line.startswith("应对：") or line.startswith("  应对："):
                current["response"] = line.split("：", 1)[1] if "：" in line else ""
            elif line.startswith("执行：") or line.startswith("  执行："):
                current["result"] = line.split("：", 1)[1] if "：" in line else ""
            elif line.startswith("结论：") or line.startswith("  结论："):
                current["conclusion"] = line.split("：", 1)[1] if "：" in line else ""
        if current.get("risk"):
            rows.append(current)

    elif ch_num == 8:
        # 格式: • 项目名：金额 说明
        for line in lines:
            line = line.strip()
            if line.startswith("• ") or line.startswith("•"):
                text = line.lstrip("• ")
                if "：" in text:
                    item, rest = text.split("：", 1)
                    rows.append({"item": item, "amount": None, "note": rest.strip()})
                else:
                    rows.append({"item": text, "amount": None, "note": ""})

    return rows
