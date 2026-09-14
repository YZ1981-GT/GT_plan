"""F2-22 存货监盘计划 — 结构化字段 ↔ G2-6-2 风格 docx 双向同步.

结构化真源：checklist_responses.item_id = ``F2-22-fields``（remark=JSON）。
在线编辑真源：项目 OnlyOffice 缓存 ``{storage}/F2-22.docx``。

填充：用 ``${field_id}`` 占位符替换（模板由本模块维护的 G2-6-2 结构生成）。
回抽：优先按章节标题正则切分（用户大段改写后仍可用）；再回退占位符残留。
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FIELDS_ITEM_ID = "F2-22-fields"
NOTE_ITEM_ID = "F2-22-note"

# 与前端 F2_22_FIELDS 对齐的可同步字段（不含 section header）
F2_22_SYNC_FIELDS: tuple[str, ...] = (
    "entityName",
    "auditYear",
    "bsDate",
    "purpose",
    "scope",
    "warehouses",
    "countDate",
    "auditors",
    "clientStaff",
    "assignment",
    "prep",
    "inventoryComposition",
    "countMethod",
    "requirements",
    "remoteWarehouse",
    "fraudRisk",
    "expertNeeded",
    "planDate",
    "teamName",
)

_PLACEHOLDER_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

# 章节切分：G2-6-2 编号标题 → 字段
_SECTION_EXTRACTORS: list[tuple[str, re.Pattern[str]]] = [
    (
        "purpose",
        re.compile(
            r"1[．.\s]*监盘目的[：:]\s*(.*?)(?=\n\s*2[．.\s]*监盘范围|\Z)",
            re.S,
        ),
    ),
    (
        "scope",
        re.compile(
            r"2[．.\s]*监盘范围[：:]\s*(.*?)(?=\n\s*3[．.\s]*监盘地点|\Z)",
            re.S,
        ),
    ),
    (
        "warehouses",
        re.compile(
            r"3[．.\s]*监盘地点[：:]\s*(.*?)(?=\n\s*4[．.\s]*监盘时间|\Z)",
            re.S,
        ),
    ),
    (
        "countDate",
        re.compile(
            r"4[．.\s]*监盘时间[：:]\s*(.*?)(?=\n\s*5[．.\s]*参与人员|\Z)",
            re.S,
        ),
    ),
    (
        "prep",
        re.compile(
            r"6[．.\s]*监盘前准备(?:工作)?[：:]\s*(.*?)(?=\n\s*7[．.\s]*监盘方式|\Z)",
            re.S,
        ),
    ),
    (
        "countMethod",
        re.compile(
            r"7[．.\s]*监盘方式[：:]\s*(.*?)(?=\n\s*8[．.\s]*监盘要求|\Z)",
            re.S,
        ),
    ),
    (
        "requirements",
        re.compile(
            r"8[．.\s]*监盘要求[：:]\s*(.*?)(?=\n\s*9[．.\s]*特别关注|\n\s*致同|\Z)",
            re.S,
        ),
    ),
]


def _format_cn_date(val: str) -> str:
    """YYYY-MM-DD → 2025年12月29日；已是中文则原样返回。"""
    s = (val or "").strip()
    if not s:
        return s
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        return f"{m.group(1)}年{int(m.group(2))}月{int(m.group(3))}日"
    return s


def _normalize_iso_date(val: str) -> str:
    """中文/杂格式日期 → YYYY-MM-DD；无法解析则原样。"""
    s = (val or "").strip()
    if not s or "[" in s:  # 占位如 [月][日]
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m2 = re.match(r"^(\d{4})[./-](\d{1,2})[./-](\d{1,2})", s)
    if m2:
        return f"{m2.group(1)}-{int(m2.group(2)):02d}-{int(m2.group(3)):02d}"
    return s


def parse_fields_json(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): ("" if v is None else str(v)) for k, v in data.items()}


def build_placeholder_map(
    fields: dict[str, str],
    *,
    project_context: dict[str, Any] | None = None,
) -> dict[str, str]:
    """构造 ``${id}`` → 值；空值保留占位符以便在 OO 中继续填写。"""
    ctx = project_context or {}
    merged = dict(fields)
    if not merged.get("entityName") and ctx.get("client_name"):
        merged["entityName"] = str(ctx["client_name"])
    if not merged.get("auditYear") and ctx.get("audit_year"):
        merged["auditYear"] = str(ctx["audit_year"])
    if not merged.get("bsDate") and ctx.get("bs_date"):
        merged["bsDate"] = str(ctx["bs_date"])
    if not merged.get("teamName"):
        merged["teamName"] = merged.get("teamName") or "XXXX审计小组"

    # 特别关注合并段（docx 第 9 节）
    special_parts = []
    for key, label in (
        ("remoteWarehouse", "异地/代管"),
        ("fraudRisk", "舞弊风险"),
        ("expertNeeded", "专家需求"),
    ):
        val = (merged.get(key) or "").strip()
        if val:
            special_parts.append(f"{label}：{val}")
    if special_parts and not merged.get("specialNotes"):
        merged["specialNotes"] = "\n".join(special_parts)

    result: dict[str, str] = {}
    for fid in (*F2_22_SYNC_FIELDS, "specialNotes"):
        token = f"${{{fid}}}"
        val = (merged.get(fid) or "").strip()
        if fid in ("planDate", "bsDate") and val:
            val = _format_cn_date(val)
        result[token] = val if val else token
    return result


def fill_plan_docx(
    template_path: Path,
    target_path: Path,
    fields: dict[str, str],
    *,
    project_context: dict[str, Any] | None = None,
) -> Path:
    """从模板填充并写入 target（OnlyOffice 缓存路径）。"""
    from docx import Document

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_path, target_path)
    doc = Document(str(target_path))
    replacements = build_placeholder_map(fields, project_context=project_context)

    def _replace_paragraph_text(paragraph: Any) -> None:
        text = paragraph.text or ""
        if not text or "${" not in text:
            return
        new_text = text
        for key, val in replacements.items():
            if key in new_text:
                new_text = new_text.replace(key, val)
        if new_text == text:
            return
        # 整段替换，避免占位符被拆到多个 run
        for run in paragraph.runs:
            run.text = ""
        if paragraph.runs:
            paragraph.runs[0].text = new_text
        else:
            paragraph.add_run(new_text)

    for paragraph in doc.paragraphs:
        _replace_paragraph_text(paragraph)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _replace_paragraph_text(paragraph)

    doc.save(str(target_path))
    return target_path


def _clean_section_body(text: str) -> str:
    t = (text or "").strip()
    # 去掉仍残留的 ${id}
    t = _PLACEHOLDER_RE.sub("", t).strip()
    return t


def extract_fields_from_docx(docx_path: Path) -> dict[str, str]:
    """从已编辑 docx 回抽字段。"""
    from docx import Document

    doc = Document(str(docx_path))
    paras = [p.text.strip() for p in doc.paragraphs if p.text is not None]
    # 去掉空段，保留顺序；全文用双换行拼，便于标题边界
    nonempty = [t for t in paras if t]
    full = "\n".join(nonempty)
    out: dict[str, str] = {}

    # 文首：索引号下一行=单位，再下一行=年度标题
    for i, t in enumerate(nonempty):
        if t.startswith("索引号"):
            if i + 1 < len(nonempty) and "监盘计划" not in nonempty[i + 1]:
                cand = nonempty[i + 1]
                if not cand.startswith("根据") and "${" not in cand:
                    out["entityName"] = cand
            if i + 2 < len(nonempty):
                m_year = re.search(r"(\d{4})\s*年存货监盘计划", nonempty[i + 2])
                if m_year:
                    out["auditYear"] = m_year.group(1)
            break
    m_bs = re.search(r"(\d{4}[-年]\d{1,2}[-月]\d{1,2}日?)\s*资产负债表", full)
    if m_bs:
        out["bsDate"] = _normalize_iso_date(
            m_bs.group(1).replace("年", "-").replace("月", "-").replace("日", "")
        ) or _normalize_iso_date(m_bs.group(1))

    for field_id, pattern in _SECTION_EXTRACTORS:
        m = pattern.search(full)
        if not m:
            continue
        body = _clean_section_body(m.group(1))
        if not body or body.startswith("${"):
            continue
        if field_id == "prep":
            comp = re.search(
                r"(?:（4）|\(4\))\s*经分析[^\n]*\n?(.*)",
                body,
                re.S,
            )
            if not comp:
                comp = re.search(r"存货构成[了解分析]*[：:]?\s*(.*)", body, re.S)
            if comp:
                out["inventoryComposition"] = _clean_section_body(comp.group(1))
                prep_main = body[: comp.start()].strip()
                # 去掉「（4）经分析…」标题行本身
                prep_main = re.sub(
                    r"(?:（4）|\(4\))\s*经分析[^\n]*$",
                    "",
                    prep_main,
                ).strip()
                out["prep"] = _clean_section_body(prep_main) or out.get("prep", "")
            else:
                out["prep"] = body
        elif field_id == "countMethod":
            # 去掉蓝色提示框
            body = re.sub(r"【提示：.*?】", "", body, flags=re.S).strip()
            out["countMethod"] = body
        else:
            out[field_id] = body

    # 第 5 节人员
    m5 = re.search(
        r"5[．.\s]*参与人员及分工[：:]?\s*(.*?)(?=\n\s*6[．.\s]*监盘前准备|\Z)",
        full,
        re.S,
    )
    if m5:
        block = m5.group(1)
        m_aud = re.search(r"项目组监盘人员[：:]\s*(.+)", block)
        m_cli = re.search(r"被审计单位配合人员[：:]\s*(.+)", block)
        m_asg = re.search(r"分工[：:]\s*(.*)", block, re.S)
        if m_aud:
            out["auditors"] = m_aud.group(1).strip()
        if m_cli:
            out["clientStaff"] = m_cli.group(1).strip()
        if m_asg:
            out["assignment"] = _clean_section_body(m_asg.group(1))

    # 第 9 节特别关注
    m9 = re.search(
        r"9[．.\s]*特别关注[^\n：:]*[：:]?\s*(.*?)(?=\n\s*致同|\Z)",
        full,
        re.S,
    )
    if m9:
        special = _clean_section_body(m9.group(1))
        if special and not special.startswith("${"):
            for key, label in (
                ("remoteWarehouse", "异地"),
                ("fraudRisk", "舞弊"),
                ("expertNeeded", "专家"),
            ):
                mm = re.search(rf"{label}[^\n：:]*[：:]\s*(.+)", special)
                if mm:
                    out[key] = mm.group(1).strip()
            if not any(out.get(k) for k in ("remoteWarehouse", "fraudRisk", "expertNeeded")):
                out["remoteWarehouse"] = special

    # 落款：致同 之后的小组名 + 日期
    m_sign = re.search(
        r"致同会计师事务所\n([^\n]+)\n([^\n]*20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)",
        full,
    )
    if m_sign:
        team = m_sign.group(1).strip()
        if team and not team.startswith("${") and "[" not in team:
            out["teamName"] = team
        plan_raw = re.sub(r"\s+", "", m_sign.group(2))
        plan_iso = _normalize_iso_date(plan_raw)
        if plan_iso:
            out["planDate"] = plan_iso

    for fid in list(out.keys()):
        if not out[fid] or out[fid].startswith("${") or out[fid] == f"${{{fid}}}":
            del out[fid]

    return out


def merge_extracted_into_existing(
    existing: dict[str, str],
    extracted: dict[str, str],
) -> dict[str, str]:
    merged = dict(existing)
    for k, v in extracted.items():
        if v and v.strip():
            merged[k] = v.strip()
    return merged


def create_g2_6_2_template_docx(target: Path) -> Path:
    """生成带 ``${}`` 占位符的 F2-22 / G2-6-2 结构模板。"""
    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(12)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    def add(text: str, *, bold: bool = False, blue: bool = False) -> None:
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = bold
        if blue:
            run.font.color.rgb = RGBColor(0x00, 0x70, 0xC0)

    add("索引号：G2-6-2")
    add("${entityName}", bold=True)
    add("${auditYear}年存货监盘计划", bold=True)
    add("")
    add(
        "根据《中国注册会计师审计准则第1311号——存货监盘》的要求，"
        "为了对${entityName}（以下简称该公司或公司）${bsDate}资产负债表上存货的"
        "存在性、所有权、品质状况等情况进行验证，我所决定对该公司存货进行监盘，"
        "特制定本监盘计划。"
    )
    add("1．监盘目的：", bold=True)
    add("${purpose}")
    add("2．监盘范围：", bold=True)
    add("${scope}")
    add("3．监盘地点：", bold=True)
    add("${warehouses}")
    add("4．监盘时间：", bold=True)
    add("${countDate}")
    add("5．参与人员及分工：", bold=True)
    add("项目组监盘人员：${auditors}")
    add("被审计单位配合人员：${clientStaff}")
    add("分工：")
    add("${assignment}")
    add("6．监盘前准备工作：", bold=True)
    add("${prep}")
    add("（4）经分析了解存货构成：")
    add("${inventoryComposition}")
    add("7．监盘方式：", bold=True)
    add("${countMethod}")
    add(
        "【提示：存货盘点需审计人员现场亲自监盘；如因特殊情况需要视频盘点，"
        "应详细说明原因和合理性，并详细记录监盘过程、项目地理位置和坐标信息，"
        "核实视频中盘点人员身份，确保视频监盘程序的有效性。】",
        blue=True,
    )
    add("8．监盘要求：", bold=True)
    add("${requirements}")
    add("9．特别关注事项：", bold=True)
    add("${specialNotes}")
    add("")
    add("致同会计师事务所")
    add("${teamName}")
    add("${planDate}")

    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(target))
    return target
