"""从 Word 权威源同步附注模板 JSON。

长期工具，可重跑，幂等。

用法:
  python backend/scripts/seed/sync_note_templates_from_word.py [--dry-run] [--phase N] [--std soe|listed] [--verbose]

Phase:
  1  合并模板: 列不一致修复 + multi_header 写入
  2  合并模板: 缺失表新增
  3  合并模板: 非报表注释章节
  4  单体模板: columns.group 补齐
  all (默认) 全部执行
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DOCX_DIR = DATA_DIR / "audit_report_templates" / "disclosure_notes"

# 导入 multi_header_to_column_groups
sys.path.insert(0, str(ROOT / "scripts" / "seed"))
from seed_consol_note_sections import multi_header_to_column_groups


# ════════════════════════════════════════════════════════════════════
# Word 解析
# ════════════════════════════════════════════════════════════════════

def get_merge_grid(table) -> tuple[dict, int, int]:
    """解析 Word 表格合并单元格，返回 (grid, num_cols, num_rows)。"""
    tbl = table._tbl
    rows_xml = tbl.findall(qn("w:tr"))
    grid_elem = tbl.find(qn("w:tblGrid"))
    num_cols = len(grid_elem.findall(qn("w:gridCol"))) if grid_elem is not None else max(
        (len(r.findall(qn("w:tc"))) for r in rows_xml), default=0)
    num_rows = len(rows_xml)
    grid: dict[tuple[int, int], dict] = {}
    vmerge_owners: dict[int, int] = {}

    for ri, tr in enumerate(rows_xml):
        ci = 0
        for tc in tr.findall(qn("w:tc")):
            while (ri, ci) in grid:
                ci += 1
            tc_pr = tc.find(qn("w:tcPr"))
            colspan = 1
            if tc_pr is not None:
                gs = tc_pr.find(qn("w:gridSpan"))
                if gs is not None:
                    colspan = int(gs.get(qn("w:val"), "1"))
            is_vc = False
            if tc_pr is not None:
                vm = tc_pr.find(qn("w:vMerge"))
                if vm is not None:
                    if vm.get(qn("w:val"), "continue") == "restart":
                        for c in range(ci, ci + colspan):
                            vmerge_owners[c] = ri
                    else:
                        is_vc = True
            paragraphs = tc.findall(qn("w:p"))
            text = "\n".join(
                "".join(r.text or "" for r in p.findall(f".//{qn('w:t')}"))
                for p in paragraphs
            ).strip()
            if is_vc:
                for c in range(ci, ci + colspan):
                    grid[(ri, c)] = {"text": "", "is_merged": True}
                    owner = vmerge_owners.get(c, ri - 1)
                    if (owner, c) in grid and "rowspan" in grid[(owner, c)]:
                        grid[(owner, c)]["rowspan"] += 1
            else:
                grid[(ri, ci)] = {"text": text, "rowspan": 1, "colspan": colspan, "is_merged": False}
                for c in range(ci + 1, ci + colspan):
                    grid[(ri, c)] = {"text": "", "is_merged": True}
            ci += colspan

    return grid, num_cols, num_rows


def detect_header_row_count(grid: dict, num_rows: int, num_cols: int) -> int:
    """检测多级表头行数。"""
    max_covered = 0
    for r in range(min(num_rows, 5)):
        for c in range(num_cols):
            cell = grid.get((r, c))
            if cell and not cell.get("is_merged") and (cell.get("colspan", 1) > 1 or cell.get("rowspan", 1) > 1):
                max_covered = max(max_covered, r + cell.get("rowspan", 1) - 1)
    if max_covered == 0:
        return 1
    header_rows = max_covered + 1
    # 排除数据行被误归为表头
    for r in range(1, header_rows):
        col0 = grid.get((r, 0))
        if col0 and not col0.get("is_merged") and col0.get("text"):
            row_has_merge = any(
                grid.get((r, c), {}).get("colspan", 1) > 1 or grid.get((r, c), {}).get("rowspan", 1) > 1
                for c in range(num_cols)
                if grid.get((r, c)) and not grid.get((r, c), {}).get("is_merged")
            )
            if not row_has_merge:
                is_covered = any(grid.get((r, c), {}).get("is_merged") for c in range(num_cols))
                if not is_covered:
                    header_rows = r
                    break
    return min(max(header_rows, 1), 4)


def build_multi_header(grid: dict, n_hdr: int, num_cols: int) -> list[list[str]] | None:
    """构造标准化 multi_header（去换行/strip）。None 如果只有 1 行。"""
    if n_hdr < 2:
        return None
    mh: list[list[str]] = []
    for r in range(n_hdr):
        row = []
        for c in range(num_cols):
            cell = grid.get((r, c))
            if cell is None or cell.get("is_merged"):
                row.append("")
            else:
                row.append(cell["text"].replace("\n", "").strip())
        mh.append(row)
    return mh


def extract_word_data_rows(grid: dict, n_hdr: int, num_rows: int, num_cols: int) -> list[list[str]]:
    """提取 Word 表格数据行（去换行）。"""
    rows = []
    for r in range(n_hdr, num_rows):
        row = []
        for c in range(num_cols):
            cell = grid.get((r, c))
            if cell and not cell.get("is_merged"):
                row.append(cell["text"].replace("\n", "").strip())
            else:
                row.append("")
        rows.append(row)
    return rows


def extract_all_word_tables(docx_path: Path) -> list[dict]:
    """从 Word 文件提取所有表格元信息。"""
    doc = Document(str(docx_path))
    body = doc.element.body
    results = []
    table_idx = 0
    current_tag = ""
    last_para_text = ""  # 表格前最近的非空段落（用作 title）

    for elem in body:
        if elem.tag == qn("w:p"):
            runs = elem.findall(f".//{qn('w:t')}")
            text = "".join(r.text or "" for r in runs).strip()
            tag_m = re.search(r"\{\{table:([^}]+)\}\}", text)
            if tag_m:
                current_tag = tag_m.group(1)
                # tag 所在段落文本（去掉标签本身）可作为标题
                clean = re.sub(r"\{\{table:[^}]+\}\}", "", text).strip()
                clean = re.sub(r"##STYLE_REF[^#]*##", "", clean).strip()
                if clean:
                    last_para_text = clean
            elif text and not text.startswith("##"):
                last_para_text = text
        elif elem.tag == qn("w:tbl"):
            table = doc.tables[table_idx]
            grid, nc, nr = get_merge_grid(table)
            has_merge = any(
                grid.get((r, c), {}).get("colspan", 1) > 1 or grid.get((r, c), {}).get("rowspan", 1) > 1
                for r in range(min(4, nr)) for c in range(nc)
                if grid.get((r, c)) and not grid.get((r, c), {}).get("is_merged")
            )
            n_hdr = detect_header_row_count(grid, nr, nc) if has_merge else 1
            mh = build_multi_header(grid, n_hdr, nc)
            # 最后一行表头作为 leaf headers
            leaf_headers = []
            last_hdr_row = n_hdr - 1
            for c in range(nc):
                cell = grid.get((last_hdr_row, c))
                if cell and not cell.get("is_merged"):
                    leaf_headers.append(cell["text"].replace("\n", "").strip())
                else:
                    leaf_headers.append("")
            # 如果只有 1 行表头，leaf = 第 0 行
            if n_hdr == 1:
                leaf_headers = []
                for c in range(nc):
                    cell = grid.get((0, c))
                    if cell and not cell.get("is_merged"):
                        leaf_headers.append(cell["text"].replace("\n", "").strip())
                    else:
                        leaf_headers.append("")

            data_rows = extract_word_data_rows(grid, n_hdr, nr, nc)

            results.append({
                "idx": table_idx,
                "tag": current_tag,
                "title_text": last_para_text,  # Word 中表格前的段落文本
                "cols": nc,
                "rows_count": nr,
                "n_header_rows": n_hdr,
                "has_multi_header": has_merge and n_hdr >= 2,
                "multi_header": mh,
                "leaf_headers": leaf_headers,
                "data_rows": data_rows,
            })
            current_tag = ""
            last_para_text = ""
            table_idx += 1

    return results


# ════════════════════════════════════════════════════════════════════
# Tag 解析 & 匹配
# ════════════════════════════════════════════════════════════════════

def parse_tag(tag: str) -> dict | None:
    """解析 Word 表格 tag。"""
    if not tag:
        return None
    # 八、5:1 / 五、4:0
    m = re.match(r"^([一二三四五六七八九十]+)、(\d+):(\d+)$", tag)
    if m:
        return {"chapter": m.group(1), "section": int(m.group(2)), "section_name": None, "table_idx": int(m.group(3))}
    # 十一、关联交易情况:0
    m = re.match(r"^([一二三四五六七八九十]+)、([^:]+):(\d+)$", tag)
    if m:
        return {"chapter": m.group(1), "section": None, "section_name": m.group(2), "table_idx": int(m.group(3))}
    # 十六:0
    m = re.match(r"^([一二三四五六七八九十]+):(\d+)$", tag)
    if m:
        return {"chapter": m.group(1), "section": None, "section_name": None, "table_idx": int(m.group(2))}
    return None


def note_chapter_for_std(std: str) -> str:
    """报表注释章节号：国企=八，上市=五。"""
    return "八" if std == "soe" else "五"


# ════════════════════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════════════════════

def normalize_mh(mh: list[list[str]]) -> list[list[str]]:
    """标准化 multi_header。"""
    return [[cell.replace("\n", "").strip() if cell else "" for cell in row] for row in mh]


def align_row_columns(row: list[str], old_cols: int, new_cols: int) -> list[str]:
    """对齐行列数。"""
    if len(row) == new_cols:
        return row
    if len(row) < new_cols:
        return row + [""] * (new_cols - len(row))
    return row[:new_cols]


def build_flat_headers_from_mh(mh: list[list[str]]) -> list[str]:
    """从 multi_header 构建 flat headers（用于 JSON 的 headers 字段）。

    逻辑：取第一行作为顶层 headers。空串保留（占位用）。
    """
    if not mh:
        return []
    return list(mh[0])


# ════════════════════════════════════════════════════════════════════
# Phase 1: 合并模板 - 列不一致修复 + multi_header 补齐
# ════════════════════════════════════════════════════════════════════

def phase1_consol(word_tables: list[dict], json_data: list[dict], std: str, dry_run: bool, verbose: bool) -> int:
    """Phase 1: 合并模板列不一致修复 + multi_header 写入。返回更新数。"""
    note_ch = note_chapter_for_std(std)
    by_sid = {e["section_id"]: e for e in json_data}
    updated = 0

    for wt in word_tables:
        p = parse_tag(wt["tag"])
        if not p or p.get("chapter") != note_ch or p.get("section") is None:
            continue

        sid = f"五-{p['section']}-{p['table_idx'] + 1}"
        entry = by_sid.get(sid)
        if not entry:
            continue  # Phase 2 处理

        j_cols = len(entry.get("headers", []))
        w_cols = wt["cols"]

        # 情况 A: 列数一致，直接写入 multi_header
        if w_cols == j_cols:
            if wt["has_multi_header"] and wt["multi_header"]:
                mh = normalize_mh(wt["multi_header"])
                if len(mh) >= 2:
                    existing = entry.get("multi_header")
                    if existing and normalize_mh(existing) == mh:
                        continue  # 已一致
                    if not dry_run:
                        entry["multi_header"] = mh
                        cg = multi_header_to_column_groups(mh)
                        if cg:
                            entry["_column_groups"] = cg
                        elif "_column_groups" in entry:
                            del entry["_column_groups"]
                    updated += 1
                    if verbose:
                        print(f"    P1-A {sid}: 写入 mh ({len(mh)} 行)")
            continue

        # 情况 B: 列数不一致
        if not wt["has_multi_header"]:
            continue  # 单级表头列数不一致，Phase 5 校正

        mh = normalize_mh(wt["multi_header"]) if wt["multi_header"] else None
        if not mh or len(mh) < 2:
            continue

        # 策略：以 Word 列数为准，扩展或收缩 JSON
        if verbose:
            print(f"    P1-B {sid}: W={w_cols}col J={j_cols}col → 以 Word 为准")

        if not dry_run:
            # 更新 headers：取 mh 第一行
            entry["headers"] = list(mh[0])

            # 更新 rows：对齐列数
            new_rows = []
            for row in entry.get("rows", []):
                new_rows.append(align_row_columns(row, j_cols, w_cols))
            entry["rows"] = new_rows

            # 写入 multi_header
            entry["multi_header"] = mh
            cg = multi_header_to_column_groups(mh)
            if cg:
                entry["_column_groups"] = cg
            elif "_column_groups" in entry:
                del entry["_column_groups"]

        updated += 1

    return updated


# ════════════════════════════════════════════════════════════════════
# Phase 2: 合并模板 - 缺失表新增
# ════════════════════════════════════════════════════════════════════

def phase2_consol(word_tables: list[dict], json_data: list[dict], std: str, dry_run: bool, verbose: bool) -> int:
    """Phase 2: 从 Word 新增 JSON 中缺失的报表注释表。返回新增数。"""
    note_ch = note_chapter_for_std(std)
    existing_sids = {e["section_id"] for e in json_data}

    # 收集已有的 parent_section 信息（用于继承元数据）
    parent_info: dict[int, dict] = {}
    for e in json_data:
        ps = e.get("parent_seq", 0)
        if ps and ps not in parent_info:
            parent_info[ps] = {"parent_section": e.get("parent_section", ""), "parent_seq": ps}

    added = 0
    max_seq = max((e.get("seq", 0) for e in json_data), default=0)

    for wt in word_tables:
        p = parse_tag(wt["tag"])
        if not p or p.get("chapter") != note_ch or p.get("section") is None:
            continue

        sid = f"五-{p['section']}-{p['table_idx'] + 1}"
        if sid in existing_sids:
            continue

        # 构建新条目
        ps = p["section"]
        pi = parent_info.get(ps, {"parent_section": f"科目{ps}", "parent_seq": ps})
        max_seq += 1

        mh = normalize_mh(wt["multi_header"]) if wt.get("multi_header") else None
        headers = list(mh[0]) if mh else wt["leaf_headers"]

        new_entry = {
            "id": str(uuid.uuid4()),
            "standard": "listed" if std == "listed" else "soe",
            "section_id": sid,
            "parent_section": pi["parent_section"],
            "parent_seq": pi["parent_seq"],
            "title": wt.get("title_text") or pi["parent_section"] or "",
            "seq": max_seq,
            "headers": headers,
            "rows": wt["data_rows"],
            "multi_header": mh if mh and len(mh) >= 2 else None,
        }

        # _column_groups
        if new_entry["multi_header"]:
            cg = multi_header_to_column_groups(new_entry["multi_header"])
            if cg:
                new_entry["_column_groups"] = cg

        if verbose:
            print(f"    P2 +{sid}: {wt['cols']}col, mh={'Y' if mh else 'N'}, rows={len(wt['data_rows'])}")

        if not dry_run:
            json_data.append(new_entry)
            existing_sids.add(sid)

        added += 1

    return added


# ════════════════════════════════════════════════════════════════════
# Phase 3: 非报表注释章节
# ════════════════════════════════════════════════════════════════════

def phase3_consol(word_tables: list[dict], json_data: list[dict], std: str, dry_run: bool, verbose: bool) -> int:
    """Phase 3: 为非报表注释章节的表创建 JSON 条目。"""
    note_ch = note_chapter_for_std(std)
    existing_sids = {e["section_id"] for e in json_data}
    added = 0
    max_seq = max((e.get("seq", 0) for e in json_data), default=0)

    for wt in word_tables:
        p = parse_tag(wt["tag"])
        if not p:
            continue
        ch = p.get("chapter", "")
        if ch == note_ch:
            continue  # Phase 1/2 已处理

        # 非报表注释章节：构建 section_id
        sec = p.get("section")
        sec_name = p.get("section_name", "")
        tidx = p.get("table_idx", 0)

        if sec is not None:
            sid = f"{ch}-{sec}-{tidx + 1}"
        elif sec_name:
            # 中文名称章节：用名称简写
            safe_name = re.sub(r"[^\w]", "", sec_name)[:20]
            sid = f"{ch}-{safe_name}-{tidx + 1}"
        else:
            sid = f"{ch}-{tidx + 1}"

        if sid in existing_sids:
            continue

        max_seq += 1
        mh = normalize_mh(wt["multi_header"]) if wt.get("multi_header") else None
        headers = list(mh[0]) if mh else wt["leaf_headers"]

        new_entry = {
            "id": str(uuid.uuid4()),
            "standard": "listed" if std == "listed" else "soe",
            "section_id": sid,
            "parent_section": sec_name or f"第{ch}章",
            "parent_seq": 0,  # 非报表注释章节无 parent_seq
            "title": wt.get("title_text") or sec_name or f"第{ch}章",
            "seq": max_seq,
            "headers": headers,
            "rows": wt["data_rows"],
            "multi_header": mh if mh and len(mh) >= 2 else None,
        }

        if new_entry["multi_header"]:
            cg = multi_header_to_column_groups(new_entry["multi_header"])
            if cg:
                new_entry["_column_groups"] = cg

        if verbose:
            print(f"    P3 +{sid}: ch={ch}, {wt['cols']}col, mh={'Y' if mh else 'N'}")

        if not dry_run:
            json_data.append(new_entry)
            existing_sids.add(sid)

        added += 1

    return added


# ════════════════════════════════════════════════════════════════════
# Phase 4: 单体模板 columns.group 补齐
# ════════════════════════════════════════════════════════════════════

def group_from_multi_header(mh: list[list[str]], col_idx: int) -> str | None:
    """从 multi_header 反推第 col_idx 列的 group 值。

    查找 mh[0] 中覆盖该列的非空单元格作为 group 名。
    """
    if not mh or col_idx < 0 or col_idx >= len(mh[0]):
        return None
    # 从 col_idx 向左找覆盖它的非空单元格
    for c in range(col_idx, -1, -1):
        text = (mh[0][c] or "").strip()
        if text:
            return text
    return None


def phase4_standalone(word_tables: list[dict], json_data: dict, std: str, dry_run: bool, verbose: bool) -> int:
    """Phase 4: 单体模板 columns.group 补齐。"""
    note_ch = note_chapter_for_std(std)
    sections = json_data.get("sections", [])
    updated = 0

    # 建立 Word 索引
    word_by_key: dict[tuple[int, int], dict] = {}
    for wt in word_tables:
        p = parse_tag(wt["tag"])
        if not p or p.get("chapter") != note_ch or p.get("section") is None:
            continue
        word_by_key[(p["section"], p["table_idx"])] = wt

    for s in sections:
        sn = s.get("section_number", "")
        m = re.match(rf"^{note_ch}、(\d+)", sn)
        if not m:
            continue
        parent_seq = int(m.group(1))

        for ti, t in enumerate(s.get("tables", [])):
            cols = t.get("columns", [])
            if not cols:
                continue

            has_group = any(c.get("group") for c in cols if isinstance(c, dict))
            has_flat = any(c.get("flat") for c in cols if isinstance(c, dict))

            if has_group or has_flat:
                continue  # 已有

            # 查找对应 Word 表
            wt = word_by_key.get((parent_seq, ti))
            if not wt:
                continue

            if wt["has_multi_header"] and wt["multi_header"]:
                mh = normalize_mh(wt["multi_header"])
                if len(mh) < 2:
                    continue

                # 反推 group
                col_idx = 0
                changed = False
                for c in cols:
                    if not isinstance(c, dict):
                        col_idx += 1
                        continue
                    if c.get("is_label"):
                        col_idx += 1
                        continue
                    grp = group_from_multi_header(mh, col_idx)
                    if grp:
                        if not dry_run:
                            c["group"] = grp
                        changed = True
                    col_idx += 1

                if changed:
                    updated += 1
                    if verbose:
                        print(f"    P4-group {sn} t[{ti}]: 补齐 group")
            else:
                # 无多级表头 → 补标 flat
                if not dry_run:
                    # 标在 is_label 列上
                    for c in cols:
                        if isinstance(c, dict) and c.get("is_label"):
                            c["flat"] = True
                            break
                    else:
                        if cols and isinstance(cols[0], dict):
                            cols[0]["flat"] = True
                updated += 1
                if verbose:
                    print(f"    P4-flat  {sn} t[{ti}]: 补标 flat")

    return updated


# ════════════════════════════════════════════════════════════════════
# 写入 & 排序
# ════════════════════════════════════════════════════════════════════

def sort_consol_json(data: list[dict]) -> list[dict]:
    """按 section_id 排序合并模板。"""
    def sort_key(e):
        sid = e.get("section_id", "")
        # "五-4-1" → (0, "五", 4, 1)
        m = re.match(r"^([一二三四五六七八九十]+)-(\d+)-(\d+)$", sid)
        if m:
            return (0, m.group(1), int(m.group(2)), int(m.group(3)))
        # "五-N-M" 带中文节名
        m2 = re.match(r"^([一二三四五六七八九十]+)-(.+)-(\d+)$", sid)
        if m2:
            return (1, m2.group(1), 0, int(m2.group(3)))
        return (2, sid, 0, 0)
    return sorted(data, key=sort_key)


def write_json(path: Path, data, dry_run: bool):
    """幂等写入 JSON。"""
    new_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        old_text = path.read_text(encoding="utf-8")
        if old_text == new_text:
            return False
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return True


# ════════════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="从 Word 同步附注模板 JSON")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true", help="只比对不写入，有差异 exit 2（CI 门禁用）")
    parser.add_argument("--phase", type=str, default="all", help="1/2/3/4/all")
    parser.add_argument("--std", type=str, default="all", help="soe/listed/all")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    # --check 等价于 --dry-run 但会在有差异时 exit 2
    if args.check:
        args.dry_run = True

    phases = [1, 2, 3, 4] if args.phase == "all" else [int(args.phase)]
    stds = ["soe", "listed"] if args.std == "all" else [args.std]

    print(f"模式: {'CHECK' if args.check else 'DRY-RUN' if args.dry_run else 'WRITE'}, phases={phases}, stds={stds}")

    total_drift = 0  # --check 模式计数漂移文件数

    for std in stds:
        print(f"\n{'='*60}")
        print(f"  {std}")
        print(f"{'='*60}")

        # 加载 Word
        consol_docx = DOCX_DIR / f"{std}_consolidated.docx"
        standalone_docx = DOCX_DIR / f"{std}_standalone.docx"

        if 1 in phases or 2 in phases or 3 in phases:
            print(f"  解析 {consol_docx.name}...")
            consol_word = extract_all_word_tables(consol_docx)
            print(f"  Word 表格: {len(consol_word)}")

            consol_json_path = DATA_DIR / f"consol_note_sections_{std}.json"
            consol_data = json.loads(consol_json_path.read_text("utf-8"))
            print(f"  JSON 表格: {len(consol_data)}")

            if 1 in phases:
                n = phase1_consol(consol_word, consol_data, std, args.dry_run, args.verbose)
                print(f"  Phase 1 (列修复+mh): {n} 更新")

            if 2 in phases:
                n = phase2_consol(consol_word, consol_data, std, args.dry_run, args.verbose)
                print(f"  Phase 2 (缺失表): {n} 新增")

            if 3 in phases:
                n = phase3_consol(consol_word, consol_data, std, args.dry_run, args.verbose)
                print(f"  Phase 3 (非注释章): {n} 新增")

            # 确保一致性：有 mh 的必有 cg，无 mh 的无 cg
            for e in consol_data:
                if e.get("multi_header"):
                    cg = multi_header_to_column_groups(e["multi_header"])
                    if cg:
                        e["_column_groups"] = cg
                    elif "_column_groups" in e:
                        del e["_column_groups"]
                elif "_column_groups" in e:
                    del e["_column_groups"]

            # 排序并写入
            consol_data = sort_consol_json(consol_data)
            changed = write_json(consol_json_path, consol_data, args.dry_run)
            if changed:
                total_drift += 1
                print(f"  ✅ {consol_json_path.name} {'(would write)' if args.dry_run else 'written'}")
            else:
                print(f"  (无变化) {consol_json_path.name}")

        if 4 in phases:
            print(f"  解析 {standalone_docx.name}...")
            standalone_word = extract_all_word_tables(standalone_docx)
            print(f"  Word 表格: {len(standalone_word)}")

            standalone_json_path = DATA_DIR / f"note_template_{std}.json"
            standalone_data = json.loads(standalone_json_path.read_text("utf-8"))
            n_sections = len(standalone_data.get("sections", []))
            n_tables = sum(len(s.get("tables", [])) for s in standalone_data.get("sections", []))
            print(f"  JSON sections: {n_sections}, tables: {n_tables}")

            n = phase4_standalone(standalone_word, standalone_data, std, args.dry_run, args.verbose)
            print(f"  Phase 4 (group补齐): {n} 更新")

            changed = write_json(standalone_json_path, standalone_data, args.dry_run)
            if changed:
                total_drift += 1
                print(f"  ✅ {standalone_json_path.name} {'(would write)' if args.dry_run else 'written'}")
            else:
                print(f"  (无变化) {standalone_json_path.name}")

    if args.check and total_drift:
        print(f"\n🔴 --check 失败：{total_drift} 个文件与 Word 不同步，请重跑 sync 工具")
        sys.exit(2)
    elif args.check:
        print(f"\n✅ --check 通过：所有模板 JSON 与 Word 同步")


if __name__ == "__main__":
    main()
