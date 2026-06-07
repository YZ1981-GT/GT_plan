"""附注语义 sidecar 候选生成脚本

基于现有模板 JSON 为试点章节生成 semantic sidecar 候选，
包含 section_id / table_id / row_id / col_id / row_type 建议。

输入:
    - backend/data/note_template_soe.json
    - backend/data/note_template_listed.json

输出:
    - backend/data/generated/note_semantic_sidecars.preview.json （sidecar 候选 JSON）
    - docs/reference/note-semantic-sidecar-diff.md （diff 报告）

⚠️ 本脚本不覆盖主模板文件。

Usage:
    python backend/scripts/gen/generate_note_semantic_sidecars.py

Validates: Requirements 11.1, 11.2
"""
from __future__ import annotations

import json
import pathlib
import re
import unicodedata
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# 路径定义
# ---------------------------------------------------------------------------

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent.parent
DATA_DIR = BACKEND_DIR / "data"
GENERATED_DIR = DATA_DIR / "generated"
DOCS_DIR = BACKEND_DIR.parent / "docs" / "reference"

SOE_PATH = DATA_DIR / "note_template_soe.json"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
OUTPUT_JSON = GENERATED_DIR / "note_semantic_sidecars.preview.json"
OUTPUT_MD = DOCS_DIR / "note-semantic-sidecar-diff.md"

# ---------------------------------------------------------------------------
# 试点章节 section_id 清单
# ---------------------------------------------------------------------------

PILOT_SECTION_IDS: dict[str, dict[str, str]] = {
    # 会计政策
    "accounting_policies": {
        "soe": "chapter-04-zhong-yao-kuai-ji-zheng-ce-kuai-ji-gu-ji",
        "listed": "chapter-03-zhong-yao-kuai-ji-zheng-ce-ji-kuai-ji-gu-ji",
    },
    # 应收账款
    "accounts_receivable": {
        "soe": "chapter-08-cai-wu-bao-biao-zhu-yao-xiang-mu-zhu-shi-ying-shou-zhang-kuan",
        "listed": "chapter-05-he-bing-cai-wu-bao-biao-xiang-mu-zhu-shi-ying-shou-zhang-kuan",
    },
    # 固定资产
    "fixed_assets": {
        "soe": "chapter-08-cai-wu-bao-biao-zhu-yao-xiang-mu-zhu-shi-gu-ding-zi-chan",
        "listed": "chapter-05-he-bing-cai-wu-bao-biao-xiang-mu-zhu-shi-gu-ding-zi-chan",
    },
    # 货币资金
    "cash_and_bank": {
        "soe": "chapter-08-cai-wu-bao-biao-zhu-yao-xiang-mu-zhu-shi-huo-bi-zi-jin",
        "listed": "chapter-05-he-bing-cai-wu-bao-biao-xiang-mu-zhu-shi-huo-bi-zi-jin",
    },
    # 关联方关系及其交易
    "related_party_transactions": {
        "soe": "chapter-11-guan-lian-fang-ji-guan-lian-jiao-yi-guan-lian-jiao-yi-qing-kuang",
        "listed": "chapter-11-guan-lian-fang-ji-guan-lian-jiao-yi-guan-lian-jiao-yi-qing-kuang",
    },
    # 关联方应收应付款项
    "related_party_receivables_payables": {
        "soe": "chapter-11-guan-lian-fang-ji-guan-lian-jiao-yi-guan-lian-fang-ying-shou-ying-fu-kuan-xiang",
        "listed": "chapter-11-guan-lian-fang-ji-guan-lian-jiao-yi-guan-lian-fang-ying-shou-ying-fu-kuan-xiang",
    },
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """将中文/英文文本转为稳定 slug（用于 table_id / col_id / row_id）。

    规则：
    1. 去除 HTML 标签（如 <br/>）
    2. 将中文转拼音首字母 fallback：直接用 unicode category 判断
    3. 非 ASCII 字符用下划线替换
    4. 连续下划线/空格归一化
    5. 去除首尾下划线
    """
    # 去除 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    # 替换空格和常用标点为下划线
    text = re.sub(r"[\s（）()【】\[\]、，。：；""'']+", "_", text)
    # 保留 ASCII 字母数字和下划线，中文字符保留
    cleaned = []
    for ch in text:
        if ch == "_":
            cleaned.append("_")
        elif ch.isascii() and (ch.isalnum() or ch == "_"):
            cleaned.append(ch.lower())
        elif unicodedata.category(ch).startswith("L"):
            # 非 ASCII 字母（含中文）直接保留
            cleaned.append(ch)
        else:
            cleaned.append("_")
    slug = "".join(cleaned)
    # 连续下划线归一化
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("_")
    return slug or "unnamed"


def _make_unique(slug: str, existing: set[str]) -> str:
    """确保 slug 在 existing 集合中唯一，重复时追加序号。"""
    if slug not in existing:
        existing.add(slug)
        return slug
    idx = 2
    while f"{slug}_{idx}" in existing:
        idx += 1
    unique = f"{slug}_{idx}"
    existing.add(unique)
    return unique


def _infer_row_type(row: dict) -> str:
    """从行的 is_total/label/row_type 推断语义 row_type。

    优先使用模板中已有的 row_type，否则按规则推断。
    """
    # 模板已有 row_type 则直接使用
    existing = row.get("row_type", "")
    if existing:
        # 统一映射
        mapping = {
            "header_label": "group_header",
            "total": "total",
            "subtotal": "subtotal",
            "data": "data",
        }
        return mapping.get(existing, existing)

    label = row.get("label", "").strip()
    is_total = row.get("is_total", False)

    if is_total:
        if "小计" in label:
            return "subtotal"
        return "total"

    if not label or label in ("", " "):
        return "blank"

    if "合计" in label:
        return "total"
    if "小计" in label:
        return "subtotal"
    if "提示" in label or label.startswith("【") or label.startswith("注："):
        return "note_tip"

    return "data"


def _infer_col_id(header: str, idx: int, existing: set[str]) -> str:
    """为列头生成稳定 col_id。"""
    slug = _slugify(header)
    if not slug or slug == "unnamed":
        slug = f"col_{idx}"
    return _make_unique(slug, existing)


def _infer_row_id(row: dict, idx: int, existing: set[str]) -> str:
    """为行生成稳定 row_id。"""
    label = row.get("label", "").strip()
    if label:
        slug = _slugify(label)
    else:
        slug = f"row_{idx}"
    return _make_unique(slug, existing)


def _generate_table_id(table: dict, idx: int, existing: set[str]) -> str:
    """为表生成稳定 table_id。"""
    name = table.get("name", "").strip()
    if name:
        slug = _slugify(name)
    else:
        slug = f"table_{idx}"
    return _make_unique(slug, existing)


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------


def _load_template(path: pathlib.Path) -> dict:
    """加载模板 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _find_section(sections: list[dict], section_id: str) -> dict | None:
    """在 sections 列表中查找指定 section_id 的章节。"""
    for s in sections:
        if s.get("section_id") == section_id:
            return s
    return None


def _process_section_tables(section: dict) -> list[dict]:
    """处理单个章节的表格，生成 sidecar 候选。"""
    tables = section.get("tables", [])
    if not tables:
        return []

    result = []
    table_id_set: set[str] = set()

    for t_idx, table in enumerate(tables):
        table_id = _generate_table_id(table, t_idx, table_id_set)

        # 生成列语义
        headers = table.get("headers", [])
        col_id_set: set[str] = set()
        columns = []
        for c_idx, header in enumerate(headers):
            col_id = _infer_col_id(header, c_idx, col_id_set)
            col_entry = {
                "col_id": col_id,
                "label": re.sub(r"<[^>]+>", "", header),  # 去 HTML
            }
            # 推断 amount_role
            amount_role = _infer_amount_role(header)
            if amount_role:
                col_entry["amount_role"] = amount_role
            columns.append(col_entry)

        # 生成行语义
        rows_data = table.get("rows", [])
        row_id_set: set[str] = set()
        rows = []
        for r_idx, row in enumerate(rows_data):
            row_id = _infer_row_id(row, r_idx, row_id_set)
            row_type = _infer_row_type(row)
            row_entry = {
                "row_id": row_id,
                "row_type": row_type,
                "label": row.get("label", ""),
            }
            rows.append(row_entry)

        result.append({
            "table_id": table_id,
            "name": table.get("name", ""),
            "columns": columns,
            "rows": rows,
            "source_table_index": t_idx,
        })

    return result


def _infer_amount_role(header: str) -> str | None:
    """从列头推断金额角色。"""
    header_clean = re.sub(r"<[^>]+>", "", header).strip()

    if "期末" in header_clean:
        return "closing"
    if "期初" in header_clean:
        return "opening"
    if "本期" in header_clean or "本年" in header_clean:
        return "current"
    if "上期" in header_clean or "上年" in header_clean:
        return "prior"
    return None


def generate_sidecars() -> dict:
    """主生成逻辑：为所有试点章节生成 sidecar 候选。"""
    soe_data = _load_template(SOE_PATH)
    listed_data = _load_template(LISTED_PATH)

    soe_sections = soe_data.get("sections", [])
    listed_sections = listed_data.get("sections", [])

    sidecars: list[dict] = []

    for semantic_id, variants in PILOT_SECTION_IDS.items():
        for template_type, section_id in variants.items():
            if template_type == "soe":
                section = _find_section(soe_sections, section_id)
            else:
                section = _find_section(listed_sections, section_id)

            if section is None:
                print(f"  ⚠️ 未找到 section: {section_id} ({template_type})")
                continue

            tables_sidecar = _process_section_tables(section)

            sidecar_entry = {
                "semantic_section_id": semantic_id,
                "template_type": template_type,
                "section_id": section_id,
                "section_title": section.get("section_title", ""),
                "section_number": section.get("section_number", ""),
                "content_type": section.get("content_type", "text"),
                "_semantic": {
                    "section_id": section_id,
                    "semantic_section_id": semantic_id,
                    "variant": f"{template_type}_standalone",
                },
                "_tables": tables_sidecar,
                "stats": {
                    "table_count": len(tables_sidecar),
                    "total_rows": sum(len(t["rows"]) for t in tables_sidecar),
                    "total_columns": sum(len(t["columns"]) for t in tables_sidecar),
                },
            }
            sidecars.append(sidecar_entry)

    return {
        "version": "1.0.0-preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": "附注语义 sidecar 候选预览（自动生成，不覆盖主模板）",
        "pilot_sections": list(PILOT_SECTION_IDS.keys()),
        "source_templates": [
            str(SOE_PATH.relative_to(BACKEND_DIR.parent)).replace("\\", "/"),
            str(LISTED_PATH.relative_to(BACKEND_DIR.parent)).replace("\\", "/"),
        ],
        "sidecars": sidecars,
    }


# ---------------------------------------------------------------------------
# diff 报告生成
# ---------------------------------------------------------------------------


def _generate_diff_report(result: dict) -> str:
    """生成 markdown diff 报告。"""
    lines: list[str] = []
    lines.append("# 附注语义 Sidecar Diff 报告")
    lines.append("")
    lines.append(f"> 自动生成时间：{result['generated_at']}")
    lines.append("> ⚠️ 本报告为 preview 候选，不代表最终写入模板的结构。")
    lines.append("")
    lines.append("## 概述")
    lines.append("")
    lines.append(f"- 试点章节数：{len(result['pilot_sections'])}")
    lines.append(f"- 生成 sidecar 条目数：{len(result['sidecars'])}")
    lines.append(f"- 来源模板：")
    for src in result["source_templates"]:
        lines.append(f"  - `{src}`")
    lines.append("")

    # 按 semantic_section_id 分组
    grouped: dict[str, list[dict]] = {}
    for sc in result["sidecars"]:
        key = sc["semantic_section_id"]
        grouped.setdefault(key, []).append(sc)

    lines.append("## 各章节 Sidecar 详情")
    lines.append("")

    for semantic_id, entries in grouped.items():
        lines.append(f"### {semantic_id}")
        lines.append("")

        for entry in entries:
            tmpl = entry["template_type"]
            lines.append(f"#### {tmpl} 版 — {entry['section_title']}")
            lines.append("")
            lines.append(f"- section_id: `{entry['section_id']}`")
            lines.append(f"- content_type: `{entry['content_type']}`")
            lines.append(f"- 表格数: {entry['stats']['table_count']}")
            lines.append(f"- 总行数: {entry['stats']['total_rows']}")
            lines.append(f"- 总列数: {entry['stats']['total_columns']}")
            lines.append("")

            if entry["_tables"]:
                lines.append("| # | table_id | name | columns | rows |")
                lines.append("|---|----------|------|---------|------|")
                for idx, tbl in enumerate(entry["_tables"]):
                    cols = ", ".join(c["col_id"] for c in tbl["columns"])
                    lines.append(
                        f"| {idx} | `{tbl['table_id']}` | {tbl['name']} "
                        f"| {cols} | {len(tbl['rows'])} 行 |"
                    )
                lines.append("")

                # 展示前 2 张表的行详情（不要太长）
                for tbl in entry["_tables"][:2]:
                    lines.append(f"<details><summary>{tbl['table_id']} 行详情</summary>")
                    lines.append("")
                    lines.append("| row_id | row_type | label |")
                    lines.append("|--------|----------|-------|")
                    for row in tbl["rows"]:
                        lines.append(
                            f"| `{row['row_id']}` | {row['row_type']} | {row['label']} |"
                        )
                    lines.append("")
                    lines.append("</details>")
                    lines.append("")
            else:
                lines.append("（无表格，为纯文本/政策条款章节）")
                lines.append("")

    # SOE vs Listed 对比
    lines.append("## SOE vs Listed 结构对比")
    lines.append("")
    lines.append("| semantic_section_id | SOE 表格数 | Listed 表格数 | SOE 总行数 | Listed 总行数 |")
    lines.append("|---------------------|-----------|--------------|-----------|--------------|")
    for semantic_id, entries in grouped.items():
        soe_entry = next((e for e in entries if e["template_type"] == "soe"), None)
        listed_entry = next((e for e in entries if e["template_type"] == "listed"), None)
        soe_tables = soe_entry["stats"]["table_count"] if soe_entry else "-"
        listed_tables = listed_entry["stats"]["table_count"] if listed_entry else "-"
        soe_rows = soe_entry["stats"]["total_rows"] if soe_entry else "-"
        listed_rows = listed_entry["stats"]["total_rows"] if listed_entry else "-"
        lines.append(
            f"| {semantic_id} | {soe_tables} | {listed_tables} | {soe_rows} | {listed_rows} |"
        )
    lines.append("")

    lines.append("## 注意事项")
    lines.append("")
    lines.append("1. 本 diff 报告是 **preview 候选**，需人工审核后方可正式采用。")
    lines.append("2. `table_id` / `row_id` / `col_id` 基于模板内容自动 slugify 生成，")
    lines.append("   正式版本可能需要人工调整为更语义化的标识。")
    lines.append("3. 会计政策章节（`accounting_policies`）为纯文本型，无表格 sidecar，")
    lines.append("   其条款化结构将通过 `_policy_clauses` 独立处理。")
    lines.append("4. 本脚本 **不覆盖** 主模板文件 `note_template_soe.json` / `note_template_listed.json`。")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("附注语义 sidecar 候选生成")
    print("=" * 60)
    print()

    # 检查输入文件
    if not SOE_PATH.exists():
        print(f"❌ 未找到 SOE 模板: {SOE_PATH}")
        return
    if not LISTED_PATH.exists():
        print(f"❌ 未找到 Listed 模板: {LISTED_PATH}")
        return

    print(f"📖 读取 SOE 模板: {SOE_PATH}")
    print(f"📖 读取 Listed 模板: {LISTED_PATH}")
    print()

    # 生成 sidecar
    result = generate_sidecars()

    # 确保输出目录存在
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # 写入 JSON
    OUTPUT_JSON.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ 输出 sidecar 候选 JSON: {OUTPUT_JSON}")

    # 写入 diff 报告
    diff_report = _generate_diff_report(result)
    OUTPUT_MD.write_text(diff_report, encoding="utf-8")
    print(f"✅ 输出 diff 报告: {OUTPUT_MD}")

    # 统计
    print()
    print("📊 统计:")
    print(f"  - 试点章节: {len(result['pilot_sections'])} 个")
    print(f"  - 生成 sidecar: {len(result['sidecars'])} 条")
    total_tables = sum(s["stats"]["table_count"] for s in result["sidecars"])
    total_rows = sum(s["stats"]["total_rows"] for s in result["sidecars"])
    print(f"  - 总表格数: {total_tables}")
    print(f"  - 总行数: {total_rows}")
    print()
    print("⚠️  本脚本不覆盖主模板。sidecar 候选需人工审核后方可采纳。")


if __name__ == "__main__":
    main()
