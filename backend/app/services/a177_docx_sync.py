"""A17-7 独立性声明书 — 结构化数据 ↔ Word 双向同步服务

职责：
- generate_docx(wp_id, project_id, db): checklist_responses → docx
- sync_docx_to_responses(wp_id, project_id, db, user_id): docx → checklist_responses

设计：
- 以 Title 样式段落定位章节边界
- 5 章结构：声明正文+期间 / 承诺事项 / 签字表 / 合伙人确认 / 威胁记录
- 主存储：checklist_responses (item_id prefix = a177- / a177a-)
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
TEMPLATE_PATH = _BACKEND_ROOT / "wp_templates" / "A" / "A17-7 审计项目团队成员独立性声明书（适用于中国及国际审计准则）.docx"
TEMPLATE_PATH_A = _BACKEND_ROOT / "wp_templates" / "A" / "A17-7A审计项目团队成员独立性声明书（适用于中国及国际审计准则）-专业技术委员会审核委员适用.docx"
STORAGE_BASE = _BACKEND_ROOT / "storage" / "projects"


def _get_project_file(project_id: UUID, variant: str = "team") -> Path:
    filename = "A17-7.docx" if variant == "team" else "A17-7A.docx"
    return STORAGE_BASE / str(project_id) / "workpapers" / "A" / filename


def _ensure_project_file(project_id: UUID, variant: str = "team") -> Path:
    fp = _get_project_file(project_id, variant)
    if not fp.exists():
        fp.parent.mkdir(parents=True, exist_ok=True)
        template = TEMPLATE_PATH if variant == "team" else TEMPLATE_PATH_A
        if template.exists():
            shutil.copy2(template, fp)
        else:
            raise FileNotFoundError(f"A17-7 模板不存在: {template}")
    return fp


def _determine_variant_from_wp(wp_id: UUID, db_rows: list) -> str:
    """从已加载的 item_id 判断变体"""
    for row in db_rows:
        if row.item_id.startswith("a177a-"):
            return "committee"
    return "team"


async def generate_docx(wp_id: UUID, project_id: UUID, db: AsyncSession) -> Path:
    """从 checklist_responses → docx"""
    from docx import Document

    # 1. 加载所有 a177-/a177a- 开头的响应
    result = await db.execute(
        sa.text(
            "SELECT item_id, conclusion, remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND (item_id LIKE 'a177-%' OR item_id LIKE 'a177a-%')"
        ),
        {"wp_id": str(wp_id)},
    )
    rows = result.fetchall()
    variant = _determine_variant_from_wp(wp_id, rows)
    prefix = "a177a-" if variant == "committee" else "a177-"

    # 2. 解析数据
    period_data: dict = {}
    commitments: dict = {}
    sign_rows: list = []
    partner: dict = {"confirmed": None, "explanation": ""}
    threats: dict = {"economic": [], "loan": [], "business": []}

    for row in rows:
        item_id: str = row.item_id
        if not item_id.startswith(prefix):
            continue
        suffix = item_id[len(prefix):]
        remark = row.remark or ""
        conclusion = row.conclusion or ""

        if suffix.startswith("period-"):
            period_data[suffix.removeprefix("period-")] = remark
        elif suffix.startswith("commit-"):
            cid = suffix.removeprefix("commit-")
            commitments[cid] = {"answer": conclusion, "explanation": remark}
        elif suffix.startswith("sign-") and suffix != "sign-count":
            try:
                parsed = json.loads(remark)
                if isinstance(parsed, dict):
                    sign_rows.append(parsed)
            except (json.JSONDecodeError, TypeError):
                pass
        elif suffix == "partner-confirmed":
            partner["confirmed"] = conclusion
        elif suffix == "partner-explanation":
            partner["explanation"] = remark
        elif suffix.startswith("threat-economic-"):
            try:
                threats["economic"].append(json.loads(remark))
            except (json.JSONDecodeError, TypeError):
                pass
        elif suffix.startswith("threat-loan-"):
            try:
                threats["loan"].append(json.loads(remark))
            except (json.JSONDecodeError, TypeError):
                pass
        elif suffix.startswith("threat-business-"):
            try:
                threats["business"].append(json.loads(remark))
            except (json.JSONDecodeError, TypeError):
                pass

    # 3. 生成 docx
    file_path = _ensure_project_file(project_id, variant)
    doc = Document(str(file_path))

    # 简化策略：在文档末尾追加结构化摘要（不破坏原始模板格式）
    # 清空现有内容段落（标题后的段落）
    _fill_document(doc, period_data, commitments, sign_rows, partner, threats, variant)

    doc.save(str(file_path))
    logger.info("A17-7 docx generated: %s (variant=%s)", file_path, variant)
    return file_path


def _fill_document(
    doc, period_data: dict, commitments: dict, sign_rows: list,
    partner: dict, threats: dict, variant: str,
):
    """填充 docx 内容 — 在模板段落中寻找占位区域并替换"""
    from docx.shared import Pt

    # 策略：找到文档中的空段落或特定标记段落进行替换
    # 由于模板结构不确定，采用追加摘要方式
    # 先尝试清空模板中 [待填] 类占位符
    for para in doc.paragraphs:
        text = para.text
        # 替换期间占位符
        if "业务期间" in text and "[" in text:
            start = period_data.get("business-start", "")
            end = period_data.get("business-end", "")
            if start or end:
                para.text = text.replace("[待填]", f"{start} 至 {end}", 1)
        elif "财务报告期间" in text and "[" in text:
            start = period_data.get("report-start", "")
            end = period_data.get("report-end", "")
            if start or end:
                para.text = text.replace("[待填]", f"{start} 至 {end}", 1)

    # 在文档末尾追加结构化数据摘要
    doc.add_paragraph("")  # 空行分隔
    doc.add_paragraph("=" * 50)
    doc.add_paragraph("【结构化数据摘要 — 由系统自动生成】")

    # 承诺事项
    commitment_labels = {
        "economic": "经济利益",
        "loan": "贷款担保",
        "business": "商业关系",
        "family": "家庭关系",
        "employment": "雇佣关系",
    }
    if commitments:
        doc.add_paragraph("▪ 承诺事项确认：")
        for cid, data in commitments.items():
            label = commitment_labels.get(cid, cid)
            answer = "无威胁" if data.get("answer") == "Y" else ("存在威胁" if data.get("answer") == "N" else "未确认")
            line = f"  {label}：{answer}"
            if data.get("explanation"):
                line += f" — {data['explanation']}"
            doc.add_paragraph(line)

    # 签字
    if sign_rows:
        doc.add_paragraph(f"▪ 签字确认：共 {len(sign_rows)} 人")
        for r in sign_rows:
            name = r.get("name", "")
            signed = "✓" if r.get("signed") else "○"
            date = r.get("date", "")
            doc.add_paragraph(f"  {signed} {name} {date}")

    # 合伙人确认
    if partner.get("confirmed"):
        doc.add_paragraph(f"▪ 合伙人审查：{'确认无问题' if partner['confirmed'] == 'Y' else '发现问题'}")
        if partner.get("explanation"):
            doc.add_paragraph(f"  说明：{partner['explanation']}")

    # 威胁记录
    has_threats = any(threats.values())
    if has_threats:
        doc.add_paragraph("▪ 威胁记录：")
        for ttype, rows in threats.items():
            if rows:
                label = {"economic": "经济利益", "loan": "贷款担保", "business": "商业关系"}.get(ttype, ttype)
                doc.add_paragraph(f"  [{label}] {len(rows)} 条")
                for r in rows:
                    doc.add_paragraph(f"    - {r.get('member', '')}：{r.get('type', r.get('description', ''))} {r.get('measure', '')}")


async def sync_docx_to_responses(
    wp_id: UUID, project_id: UUID, db: AsyncSession, user_id: UUID,
) -> int:
    """从 docx 解析内容回写到 checklist_responses"""
    from datetime import datetime, timezone
    from docx import Document

    # 尝试两个变体的文件
    for variant in ("team", "committee"):
        file_path = _get_project_file(project_id, variant)
        if file_path.exists():
            break
    else:
        logger.warning("A17-7 docx 不存在，无法同步")
        return 0

    prefix = "a177a-" if variant == "committee" else "a177-"
    doc = Document(str(file_path))
    now = datetime.now(timezone.utc)
    count = 0

    # 解析文档中的结构化摘要区域
    in_summary = False
    current_section = ""
    sign_rows: list[dict] = []
    commitments: dict = {}

    for para in doc.paragraphs:
        text = para.text.strip()
        if "结构化数据摘要" in text:
            in_summary = True
            continue
        if not in_summary:
            continue

        if text.startswith("▪ 承诺事项"):
            current_section = "commitment"
        elif text.startswith("▪ 签字确认"):
            current_section = "signing"
        elif text.startswith("▪ 合伙人审查"):
            current_section = "partner"
            # Parse inline
            if "确认无问题" in text:
                await _upsert_response(db, project_id, wp_id, f"{prefix}partner-confirmed", "Y", None, user_id, now)
                count += 1
            elif "发现问题" in text:
                await _upsert_response(db, project_id, wp_id, f"{prefix}partner-confirmed", "N", None, user_id, now)
                count += 1
        elif text.startswith("▪ 威胁记录"):
            current_section = "threat"
        elif current_section == "commitment" and text.startswith("  "):
            # Parse commitment lines
            for cid, label in [("economic", "经济利益"), ("loan", "贷款担保"), ("business", "商业关系"), ("family", "家庭关系"), ("employment", "雇佣关系")]:
                if label in text:
                    answer = "Y" if "无威胁" in text else ("N" if "存在威胁" in text else None)
                    explanation = text.split("—", 1)[1].strip() if "—" in text else None
                    if answer:
                        await _upsert_response(db, project_id, wp_id, f"{prefix}commit-{cid}", answer, explanation, user_id, now)
                        count += 1
                    break
        elif current_section == "signing" and text.startswith("  "):
            # Parse sign row: ✓ Name Date or ○ Name Date
            signed = text.startswith("  ✓")
            parts = text.lstrip("  ✓○").strip().split()
            name = parts[0] if parts else ""
            date = parts[1] if len(parts) > 1 else None
            sign_rows.append({"name": name, "signed": signed, "date": date})

    # Write sign rows
    for i, row in enumerate(sign_rows):
        item_id = f"{prefix}sign-{i + 1}"
        await _upsert_response(db, project_id, wp_id, item_id, None, json.dumps(row, ensure_ascii=False), user_id, now)
        count += 1

    if count > 0:
        await db.commit()
    logger.info("A17-7 docx→responses synced %d items", count)
    return count


async def _upsert_response(
    db: AsyncSession, project_id: UUID, wp_id: UUID,
    item_id: str, conclusion: Optional[str], remark: Optional[str],
    user_id: UUID, now,
):
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
        {"pid": str(project_id), "wp_id": str(wp_id), "item_id": item_id, "conclusion": conclusion, "remark": remark, "uid": str(user_id), "now": now},
    )
