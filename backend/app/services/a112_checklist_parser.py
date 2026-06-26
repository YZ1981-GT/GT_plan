"""A1-12 重大事项决定程序核查表 — 专属 DOCX 解析器

输出 A112ChecklistData 结构（区别于通用 checklist_docx_parser 的 sections/toc 格式）。
专属格式：categories / items(item-N) / signatures，供 GtA112DualChecklist.vue 消费。
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from docx import Document

logger = logging.getLogger(__name__)

# ─── 模板路径 ────────────────────────────────────────────────────────────────

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "wp_templates" / "A"


def _find_a112_template() -> Path | None:
    """查找 A1-12 模板文件."""
    for f in _TEMPLATE_DIR.iterdir():
        if f.suffix.lower() == ".docx" and "A1-12" in f.name:
            return f
    return None


# ─── 正则 ────────────────────────────────────────────────────────────────────

_CATEGORY_RE = re.compile(r"^[一二三四五六七八九十]+、")
_ITEM_SEQ_RE = re.compile(r"^(\d+)[、．.]")
_CATEGORY_TAG_RE = re.compile(r"[（(]([A-Z]\d+)[,，)）]")

# 头部信息正则
_ENTITY_RE = re.compile(r"被审计单位(?:名称)?[：:]\s*(.+?)(?:\s{2,}截止日|$)")
_PERIOD_END_RE = re.compile(r"截止日[：:]\s*(.+)")
_BUSINESS_CLASS_RE = re.compile(r"鉴证业务分类|业务分类")
_FIRST_ENGAGEMENT_RE = re.compile(r"是否首次承接")

# 签字区正则
_SIGNATURE_ROLES = ["项目负责经理", "项目合伙人", "项目质量复核合伙人", "质量复核合伙人", "质量控制复核人"]
_ROLE_RE = re.compile(r"(" + "|".join(_SIGNATURE_ROLES) + r")")


# ─── 主解析函数 ──────────────────────────────────────────────────────────────


def parse_a112_checklist(docx_path: str | Path | None = None) -> dict:
    """解析 A1-12 DOCX 为 A112ChecklistData 结构.

    Args:
        docx_path: DOCX 文件路径。若为 None，使用默认模板路径。

    Returns:
        A112ChecklistData dict:
        {
          "header": {...},
          "categories": [...],
          "signatures": [...]
        }

    解析规则:
    1. 头部信息从段落正则提取（被审计单位/截止日/业务分类/首次承接）
    2. 表格第 0 行为 category 标题 + 表头（跳过 col1/col2）
    3. 以"一、"/"二、" 开头的行为 category 分隔
    4. Category 1（第一类）: rows 1-14, 14 fixed items
    5. Category 2（第二类）: row 15 标题 + row 16 空行, allow_custom=true
    6. 每行解析为 A112CheckItem（seq/description/category_tag）
    7. 签字区从段落提取 4 角色
    """
    # 解析路径
    if docx_path is None:
        docx_path = _find_a112_template()
    else:
        docx_path = Path(docx_path)

    if docx_path is None or not docx_path.exists():
        logger.warning("A1-12 DOCX 文件不存在: %s", docx_path)
        return _empty_result()

    try:
        doc = Document(str(docx_path))
    except Exception as e:  # noqa: BLE001
        logger.warning("A1-12 DOCX 解析失败: %s", e)
        return _empty_result()

    # ─── 1. 头部信息 ─────────────────────────────────────────────────────
    header = _extract_header(doc)

    # ─── 2. 表格解析 ─────────────────────────────────────────────────────
    categories = _extract_categories(doc)

    # ─── 3. 签字区 ───────────────────────────────────────────────────────
    signatures = _extract_signatures(doc)

    return {
        "header": header,
        "categories": categories,
        "signatures": signatures,
    }


# ─── 头部提取 ────────────────────────────────────────────────────────────────


def _extract_header(doc: Document) -> dict:
    """从段落提取头部信息."""
    header = {
        "entity_name": None,
        "period_end": None,
        "business_class": None,
        "is_first_engagement": None,
    }

    for para in doc.paragraphs[:15]:
        text = para.text.strip().replace("\xa0", " ")
        if not text:
            continue

        # 被审计单位
        m = _ENTITY_RE.search(text)
        if m:
            val = m.group(1).strip()
            # 过滤纯空白或模板占位（如 "截止日："被误匹配）
            if val and not val.startswith("截止日"):
                header["entity_name"] = val

        # 截止日
        m = _PERIOD_END_RE.search(text)
        if m:
            val = m.group(1).strip()
            if val:
                header["period_end"] = val

        # 业务分类
        if _BUSINESS_CLASS_RE.search(text):
            # 通常格式: "鉴证业务分类：A类     B类     C类"
            # 实际填写时会有勾选标记，此处从模板提取无法确定选中项
            # 留 None，由 field_overrides 中的用户选择覆盖
            pass

        # 首次承接
        if _FIRST_ENGAGEMENT_RE.search(text):
            # 同上，模板中无法确定选中状态
            pass

    return header


# ─── 表格解析 ────────────────────────────────────────────────────────────────


def _extract_categories(doc: Document) -> list[dict]:
    """从表格提取 categories 和 items."""
    if not doc.tables:
        logger.warning("A1-12 DOCX 无表格")
        return []

    tbl = doc.tables[0]
    categories: list[dict] = []
    current_cat: dict | None = None
    cat_idx = 0
    item_seq = 0

    for ri in range(len(tbl.rows)):
        cell0_text = tbl.cell(ri, 0).text.strip().replace("\xa0", " ")

        if not cell0_text:
            # 空行（如 row 16），跳过
            continue

        # 检测 category 标题
        if _CATEGORY_RE.match(cell0_text):
            cat_idx += 1
            current_cat = {
                "id": f"cat-{cat_idx}",
                "title": cell0_text,
                "items": [],
                "allow_custom": cat_idx >= 2,  # 第二类及以后允许自定义
            }
            categories.append(current_cat)
            continue

        # 普通条目行
        if current_cat is None:
            # 条目出现在第一个 category 之前，创建默认 category
            cat_idx += 1
            current_cat = {
                "id": f"cat-{cat_idx}",
                "title": "核查事项",
                "items": [],
                "allow_custom": False,
            }
            categories.append(current_cat)

        item_seq += 1

        # 提取 category_tag（括号内标签如 (A1)、(A2)）
        tag_match = _CATEGORY_TAG_RE.search(cell0_text)
        category_tag = tag_match.group(1) if tag_match else None

        current_cat["items"].append({
            "id": f"item-{item_seq}",
            "seq": item_seq,
            "description": cell0_text,
            "category_tag": category_tag,
        })

    return categories


# ─── 签字区提取 ──────────────────────────────────────────────────────────────


def _extract_signatures(doc: Document) -> list[dict]:
    """从段落提取签字区 4 角色."""
    # 标准 4 角色（按固定顺序输出）
    standard_roles = [
        "项目负责经理",
        "项目合伙人",
        "质量复核合伙人",
        "质量控制复核人",
    ]

    found_roles: set[str] = set()

    for para in doc.paragraphs:
        text = para.text.strip().replace("\xa0", " ")
        if not text:
            continue
        m = _ROLE_RE.search(text)
        if m:
            role = m.group(1)
            # 统一名称：项目质量复核合伙人 → 质量复核合伙人
            if role == "项目质量复核合伙人":
                role = "质量复核合伙人"
            found_roles.add(role)

    # 确保标准 4 角色都在（即使文档中缺失）
    signatures = []
    for role in standard_roles:
        signatures.append({
            "role": role,
            "name": None,
            "date": None,
        })

    return signatures


# ─── Round-Trip: format_to_docx ──────────────────────────────────────────────


def format_to_docx(checklist_data: dict) -> io.BytesIO:
    """将 A112ChecklistData 格式化回 DOCX（BytesIO），支持 round-trip 验证.

    生成的 DOCX 结构与解析器预期一致：
    - 头部段落（被审计单位/截止日）在前 15 行
    - 第一个表格包含 category 标题行 + item 行（3 列）
    - 签字段落包含角色名称

    **Validates: Requirements 7.1, 7.2**

    Args:
        checklist_data: parse_a112_checklist 输出的 dict

    Returns:
        BytesIO 包含完整 DOCX 文件字节
    """
    doc = Document()

    # ─── 1. 头部段落 ─────────────────────────────────────────────────────
    header = checklist_data.get("header", {})
    entity_name = header.get("entity_name") or ""
    period_end = header.get("period_end") or ""

    # 标题
    doc.add_paragraph("A1-12 重大事项决定程序的履行情况核查表")

    # 被审计单位 + 截止日（合并一行，与原模板格式一致）
    if entity_name or period_end:
        header_line = f"被审计单位：{entity_name}  截止日：{period_end}"
    else:
        header_line = "被审计单位：  截止日："
    doc.add_paragraph(header_line)

    # 业务分类行
    doc.add_paragraph("鉴证业务分类：A类  B类  C类")
    # 首次承接行
    doc.add_paragraph("是否首次承接：是  否")

    # ─── 2. 表格（categories + items）────────────────────────────────────
    categories = checklist_data.get("categories", [])

    # 计算总行数：每个 category 一个标题行 + 该 category 的 items
    total_rows = sum(1 + len(cat.get("items", [])) for cat in categories)
    if total_rows == 0:
        total_rows = 1  # 至少一行空表格

    tbl = doc.add_table(rows=total_rows, cols=3)

    row_idx = 0
    for cat in categories:
        # category 标题行
        tbl.cell(row_idx, 0).text = cat.get("title", "")
        tbl.cell(row_idx, 1).text = ""
        tbl.cell(row_idx, 2).text = ""
        row_idx += 1

        # item 行
        for item in cat.get("items", []):
            tbl.cell(row_idx, 0).text = item.get("description", "")
            tbl.cell(row_idx, 1).text = ""  # 是否适用
            tbl.cell(row_idx, 2).text = ""  # 索引号
            row_idx += 1

    # ─── 3. 签字段落 ─────────────────────────────────────────────────────
    signatures = checklist_data.get("signatures", [])
    doc.add_paragraph("")  # 空行分隔
    for sig in signatures:
        role = sig.get("role", "")
        name = sig.get("name") or ""
        date_val = sig.get("date") or ""
        doc.add_paragraph(f"{role}：{name}  日期：{date_val}")

    # ─── 4. 序列化为 BytesIO ─────────────────────────────────────────────
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# ─── 空结果 ──────────────────────────────────────────────────────────────────


def _empty_result() -> dict:
    """DOCX 不存在或异常时返回空结构."""
    return {
        "header": {
            "entity_name": None,
            "period_end": None,
            "business_class": None,
            "is_first_engagement": None,
        },
        "categories": [],
        "signatures": [
            {"role": "项目负责经理", "name": None, "date": None},
            {"role": "项目合伙人", "name": None, "date": None},
            {"role": "质量复核合伙人", "name": None, "date": None},
            {"role": "质量控制复核人", "name": None, "date": None},
        ],
    }
