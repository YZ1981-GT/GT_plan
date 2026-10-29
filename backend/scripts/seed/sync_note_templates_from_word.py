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

合并模板按表标记位置对条目前先核对身份（Word 节标题 ↔ 种子父章节、行名），对不上的不写、逐条报出（R7.6）。
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

# 导入 multi_header_to_column_groups；表头行数判定用平台的 app.services.note_word_table
sys.path.insert(0, str(ROOT / "scripts" / "seed"))
sys.path.insert(0, str(ROOT))
from seed_consol_note_sections import fill_label_header, multi_header_to_column_groups
from app.services.note_word_table import seed_table_structure, sync_logical_columns  # noqa: E402  与平台同一构建（R7.6）


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


def word_header(table) -> tuple[int, list[list[str]] | None]:
    """表头行数与多级表头（None = 单行表头）：与平台同一套（``note_word_table.seed_multi_header``，标题行库 /
    上年附注导入 / Word 目录核对共用）。

    原先这里另有一套只看纵向合并的判定：两级表头「账龄」列下格留白判成一行，数据行里两格一并的空白取数格、
    通栏分类行又被算进表头（合并种子 12 张表数据行升进表头）；Word 表头里没合并的空白格也照搬，
    种子格式把它读成「并进左边」（R6.3）。
    """
    from app.services.note_word_table import seed_multi_header

    n_hdr, mh = seed_multi_header(table._tbl)
    return (n_hdr, mh) if n_hdr >= 2 else (max(n_hdr, 1), None)


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
    """从 Word 文件提取所有表格元信息（含表格后段落文字）。"""
    doc = Document(str(docx_path))
    body = doc.element.body
    results = []
    table_idx = 0
    current_tag = ""
    last_para_text = ""  # 表格前最近的非空段落（用作 title）
    # 所在 ##SECTION:…## 节与节标题（节标记后第一段正文）：写种子前核对身份用（R7.6）
    section, heading, want_heading = "", "", False
    # ── text_after 收集 ──
    collecting_after = False  # 是否正在收集上一张表后的段落
    after_paras: list[str] = []

    def _flush_after():
        """把已收集的段落文字写入上一张表的 text_after_raw。"""
        nonlocal collecting_after, after_paras
        if collecting_after and results:
            results[-1]["text_after_raw"] = "\n".join(after_paras)
        after_paras = []
        collecting_after = False

    for elem in body:
        if elem.tag == qn("w:p"):
            runs = elem.findall(f".//{qn('w:t')}")
            text = "".join(r.text or "" for r in runs).strip()
            sec_m = re.match(r"^##SECTION:(.+?)##$", text)
            if sec_m:  # 节边界：其后的节标题 / 小标题属于下一节，不再算上一张表的表后文字（R7.6）
                _flush_after()
                section, heading, want_heading = sec_m.group(1), "", True
            elif want_heading and text and not text.startswith(("##", "{{")):
                heading, want_heading = text, False
            tag_m = re.search(r"\{\{table:([^}]+)\}\}", text)
            if tag_m:
                _flush_after()
                current_tag = tag_m.group(1)
                # tag 所在段落文本（去掉标签本身）可作为标题
                clean = re.sub(r"\{\{table:[^}]+\}\}", "", text).strip()
                clean = re.sub(r"##STYLE_REF[^#]*##", "", clean).strip()
                if clean:
                    last_para_text = clean
            elif text and not text.startswith("##"):
                if collecting_after:
                    after_paras.append(text)
                last_para_text = text
        elif elem.tag == qn("w:tbl"):
            _flush_after()
            table = doc.tables[table_idx]
            grid, nc, nr = get_merge_grid(table)
            has_merge = any(
                grid.get((r, c), {}).get("colspan", 1) > 1 or grid.get((r, c), {}).get("rowspan", 1) > 1
                for r in range(min(4, nr)) for c in range(nc)
                if grid.get((r, c)) and not grid.get((r, c), {}).get("is_merged")
            )
            n_hdr, mh = word_header(table) if has_merge else (1, None)
            assert mh is None or len(mh[0]) == nc, f"Word 表 #{table_idx} 网格列数 {nc} 与表头列数 {len(mh[0])} 不同"
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
            elif mh and leaf_headers:
                # 标签列表头多为纵向合并（末行是延续格）：取它的文字，phase5 的「首列表头一致」校验才不会因空串被跳过
                leaf_headers[0] = next((row[0] for row in mh if row[0]), leaf_headers[0])

            data_rows = extract_word_data_rows(grid, n_hdr, nr, nc)

            results.append({
                "idx": table_idx,
                "tag": current_tag,
                "section": section,
                "section_heading": heading,
                "el": table._tbl,
                "title_text": last_para_text,  # Word 中表格前的段落文本
                "text_after_raw": "",           # 表格后段落文字（后续 _flush_after 填充）
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
            collecting_after = True  # 开始收集下一段文字
            table_idx += 1

    _flush_after()  # 最后一张表
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


#: Word 模板节标记已知缺陷（口径, Word 节号）：按标记与种子身份对不上，不写、--check 不计；对上了报「登记失效」（R7.6）
KNOWN_SECTION_GAPS = {
    ("listed", n): "上市合并 Word 缺 五、71~78 节标记（公允价值变动收益…现金流量表项目注释的表都落在 五、70 下），"
                   "其后 五、79/81/82 被标成 五、71/73/74；种子章节号与单体模板一致，不按 Word 改号"
    for n in (71, 73, 74)
}
#: 第 1 张 Word 表下半截另起表头内嵌第二张表、种子（与单体一致）拆成两条的节（口径, 节号）：
#: 种子第 2 条没有 Word 标记，``:k``（k ≥ 1）对 五-N-(k+2)（R7.8；原按 k+1 对，表名 / 表头 / 表后文字逐张错后一张）
EMBEDDED_SPLITS = {("listed", 11): "持有待售资产表下半截是持有待售负债表（单体也拆成两张）"}
#: 表头占位列已按单体模板实例化的合并表（口径, 条目号）→ (单体章节号, 单体表名)：Word 表头是「……」「可无限量添加列」
#: 这类按需增加的列（编辑器只能增行不能增列；表体「可无限量添加行」是动态行，照 Word 留着），种子取单体模板（底稿披露表
#: 写进的那张表）的列，合并才收得下单体的数；Phase 1 不按 Word 改回，种子里没有该条目报「登记失效」（R7.7）
STANDALONE_INSTANTIATED = {
    ("listed", "五-22-2"): ("五、22", "固定资产情况"), ("listed", "五-24-1"): ("五、24", "（1）以成本计量"),
    ("listed", "五-24-2"): ("五、24", "（2）以公允价值计量"), ("listed", "五-25-1"): ("五、25", "使用权资产"),
    ("listed", "五-28-1"): ("五、28", "商誉账面原值"), ("listed", "五-28-2"): ("五、28", "商誉减值准备"),
}
#: Word 一格横跨两个网格列、数据行也拆成两格的合并表（口径, 条目号）：种子按逻辑列存，与单体模板 / Word 逻辑列一致
#: （用户 2026-10-23 拍板；原按网格存，两列同键认不出），Phase 1 按逻辑列比对 / 重建（R8.2）
LOGICAL_COLUMNS = {("listed", "五-10-1"), ("listed", "五-11-1")}
IDENTITY_MISMATCHES: list[str] = []
KNOWN_GAP_HITS: set[tuple[str, int]] = set()


def entry_sid(std: str, p: dict) -> str:
    """Word 表标记 → 合并种子条目号：报表注释章 五-N-(k+1)（拆表节 k ≥ 1 再 +1），其余章 章-节号或节名-(k+1)。"""
    ch, sec, k = p.get("chapter", ""), p.get("section"), p.get("table_idx", 0) + 1
    if ch == note_chapter_for_std(std) and sec is not None:
        return f"五-{sec}-{k + (k > 1 and (std, sec) in EMBEDDED_SPLITS)}"
    if p.get("section_name"):
        return f"{ch}-{re.sub(r'[^\w]', '', p['section_name'])[:20]}-{k}"
    return f"{ch}-{sec}-{k}" if sec is not None else f"{ch}-{k}"


def identity_mismatch(entry: dict, wt: dict, std: str, sid: str, *, rows: bool = True) -> bool:
    """按标记对到的 Word 表与种子条目不是同一张（节标题 ≠ 父章节，或双方实质行名无交集）⇒ 不写并记录（R7.6）。

    原来只按位置对（``八、N:k`` → ``五-N-(k+1)``）：种子假章节 五-10 让其后每节错一节，Phase 1 用错表覆盖表名 / 表头，
    Phase 2 按错的父章节补表。
    """
    from app.services.note_word_table import heading_key, rows_disjoint

    reason = None
    if heading_key(wt.get("section_heading")) != heading_key(entry.get("parent_section")):
        reason = f"Word 节「{(wt.get('section_heading') or '')[:20]}」≠ 种子父章节「{(entry.get('parent_section') or '')[:20]}」"
    elif rows and rows_disjoint(entry.get("rows"), wt.get("data_rows")):
        reason = "行名没有交集"
    if reason is None:
        return False
    section = (parse_tag(wt["tag"]) or {}).get("section")
    if (std, section) in KNOWN_SECTION_GAPS:
        KNOWN_GAP_HITS.add((std, section))
    elif (msg := f"[{std}] {sid} ← Word {wt['tag']}：{reason}") not in IDENTITY_MISMATCHES:
        IDENTITY_MISMATCHES.append(msg)
    return True


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

def phase1_consol(word_tables: list[dict], json_data: list[dict], std: str, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """Phase 1: 合并模板列不一致修复 + multi_header 写入 + title 同步。

    返回 ``(struct_updated, title_updated)``。
    """
    note_ch = note_chapter_for_std(std)
    by_sid = {e["section_id"]: e for e in json_data}
    struct_updated = 0
    title_updated = 0

    for wt in word_tables:
        p = parse_tag(wt["tag"])
        if not p or p.get("chapter") != note_ch or p.get("section") is None:
            continue

        sid = entry_sid(std, p)
        entry = by_sid.get(sid)
        if not entry:
            continue  # Phase 2 处理
        if identity_mismatch(entry, wt, std, sid):
            continue

        # ── title 同步：以 Word 表格前段落文本为准 ──
        w_title = (wt.get("title_text") or "").strip()
        j_title = (entry.get("title") or "").strip()
        if w_title and w_title != j_title:
            if not dry_run:
                entry["title"] = w_title
            title_updated += 1
            if verbose:
                print(f"    P1-T {sid}: title '{j_title[:30]}' → '{w_title[:30]}'")
        if (std, sid) in STANDALONE_INSTANTIATED:
            continue  # 占位列已按单体模板实例化，不按 Word 改回
        if (std, sid) in LOGICAL_COLUMNS:
            struct_updated += sync_logical_columns(entry, wt["el"], apply=not dry_run)  # 按逻辑列比对 / 重建
            continue

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
                    struct_updated += 1
                    if verbose:
                        print(f"    P1-A {sid}: 写入 mh ({len(mh)} 行)")
            continue

        # 情况 B: 列数不一致
        if not wt["has_multi_header"]:
            continue  # 单级表头列数不一致

        mh = normalize_mh(wt["multi_header"]) if wt["multi_header"] else None
        if not mh or len(mh) < 2:
            continue

        # 策略：以 Word 列数为准，扩展或收缩 JSON
        if verbose:
            print(f"    P1-B {sid}: W={w_cols}col J={j_cols}col → 以 Word 为准")

        if not dry_run:
            built = seed_table_structure(wt["el"])  # 平表头取展示全路径（R6.3 口径，原来写多级表头首行）
            entry["headers"] = built["headers"]
            entry["rows"] = [align_row_columns(row, j_cols, w_cols) for row in entry.get("rows", [])]
            entry["multi_header"] = built["multi_header"]
            entry.pop("_column_groups", None)
            if built.get("_column_groups"):
                entry["_column_groups"] = built["_column_groups"]
            fill_label_header(entry, std)  # 标签列 Word 留白 ⇒ 单体同名表的表头（R6）

        struct_updated += 1

    return struct_updated, title_updated


# ════════════════════════════════════════════════════════════════════
# Phase 2: 合并模板 - 缺失表新增
# ════════════════════════════════════════════════════════════════════

def phase2_consol(word_tables: list[dict], json_data: list[dict], std: str, dry_run: bool, verbose: bool) -> int:
    """Phase 2: 从 Word 新增 JSON 中缺失的报表注释表。返回新增数。"""
    note_ch = note_chapter_for_std(std)
    existing_sids = {e["section_id"] for e in json_data}

    added = 0
    max_seq = max((e.get("seq", 0) for e in json_data), default=0)

    for wt in word_tables:
        p = parse_tag(wt["tag"])
        if not p or p.get("chapter") != note_ch or p.get("section") is None:
            continue

        sid = entry_sid(std, p)
        if sid in existing_sids:
            continue

        # 构建新条目：父章节取 Word 节标题（原来沿用同号旧条目或「科目N」，种子错节时一并错）；同节已有条目须对得上节标题
        ps = p["section"]
        same = next((e for e in json_data if e.get("parent_seq") == ps and str(e.get("section_id", "")).startswith("五-")), None)
        if same is not None and identity_mismatch(same, wt, std, sid, rows=False):
            continue
        parent = same["parent_section"] if same is not None else (
            clean_parent_section(wt.get("section_heading") or "") or f"科目{ps}")
        pi = {"parent_section": parent, "parent_seq": ps}
        max_seq += 1
        built = seed_table_structure(wt["el"])

        new_entry = {
            "id": str(uuid.uuid4()),
            "standard": "listed" if std == "listed" else "soe",
            "section_id": sid,
            "parent_section": pi["parent_section"],
            "parent_seq": pi["parent_seq"],
            "title": wt.get("title_text") or pi["parent_section"] or "",
            "seq": max_seq,
            "headers": built["headers"],
            "rows": built["rows"],
            "multi_header": built["multi_header"],
        }
        if built.get("_column_groups"):
            new_entry["_column_groups"] = built["_column_groups"]
        fill_label_header(new_entry, std)  # 标签列 Word 留白 ⇒ 单体同名表的表头（R6）

        if verbose:
            print(f"    P2 +{sid}: {wt['cols']}col, mh={'Y' if built['multi_header'] else 'N'}, rows={len(built['rows'])}")

        if not dry_run:
            json_data.append(new_entry)
            existing_sids.add(sid)

        added += 1

    return added


# ════════════════════════════════════════════════════════════════════
# Phase 3: 非报表注释章节
# ════════════════════════════════════════════════════════════════════

def phase3_consol(word_tables: list[dict], json_data: list[dict], std: str, dry_run: bool, verbose: bool) -> tuple[int, int]:
    """Phase 3: 为非报表注释章节的表创建 JSON 条目 + title 同步。

    返回 ``(added, title_updated)``。
    """
    note_ch = note_chapter_for_std(std)
    existing_sids = {e["section_id"] for e in json_data}
    by_sid = {e["section_id"]: e for e in json_data}
    added = 0
    title_updated = 0
    max_seq = max((e.get("seq", 0) for e in json_data), default=0)

    for wt in word_tables:
        p = parse_tag(wt["tag"])
        if not p:
            continue
        ch = p.get("chapter", "")
        if ch == note_ch:
            continue  # Phase 1/2 已处理

        # 非报表注释章节：构建 section_id（中文名称章节用名称简写）
        sec_name = p.get("section_name", "")
        sid = entry_sid(std, p)

        if sid in existing_sids:
            # ── title 同步（与 Phase 1 同逻辑） ──
            w_title = (wt.get("title_text") or "").strip()
            if w_title:
                entry_p3 = by_sid.get(sid)
                if entry_p3 and (entry_p3.get("title") or "").strip() != w_title:
                    if not dry_run:
                        entry_p3["title"] = w_title
                    title_updated += 1
                    if verbose:
                        print(f"    P3-T {sid}: title → '{w_title[:40]}'")
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
        fill_label_header(new_entry, std)  # 标签列 Word 留白 ⇒ 单体同名表的表头（R6）

        if verbose:
            print(f"    P3 +{sid}: ch={ch}, {wt['cols']}col, mh={'Y' if mh else 'N'}")

        if not dry_run:
            json_data.append(new_entry)
            existing_sids.add(sid)

        added += 1

    return added, title_updated


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
# Phase 5: 单体模板 - title 同步
# ════════════════════════════════════════════════════════════════════

def phase5_standalone_title(
    word_tables: list[dict], json_data: dict, std: str, dry_run: bool, verbose: bool,
) -> int:
    """已退役：单体表名不再按 ``(section_num, table_idx)`` 位置覆盖。

    单体模板中存在按底稿披露表拆出的期初续表，而 Word 可能只写一张表或仅写“续：”。
    位置覆盖会从第一张续表起把后续标题整体错后一张。标题、表序与结构现由
    ``note_word_tree``（Word）和 ``note_template_workpaper_alignment``（底稿）共同门禁；
    本长期工具只保留参数兼容，不再写模板。
    """
    del word_tables, json_data, std, dry_run
    if verbose:
        print("    P5 已退役：标题/表序改由 Word 树与底稿披露表对齐门禁管理")
    return 0


# ════════════════════════════════════════════════════════════════════
# text_after 清理 + parent_section 规范化
# ════════════════════════════════════════════════════════════════════

_TAG_RE = re.compile(r"\{\{[^}]+\}\}")
_HINT_BRACKET_RE = re.compile(r"【[^】]*】")
_SECTION_MARKER_RE = re.compile(r"^##\s*")
_PUNCT_ONLY_RE = re.compile(r"^[\s\n\r。，、；：？！…—·\u201c\u201d\u2018\u2019（）【】《》〈〉「」『』\[\]()]+$")
_PARENT_HINT_RE = re.compile(r"[（(][^）)]*(?:删除|修改|调整|提示|不适用|根据企业|选择|酌情)[^）)]*[）)]")
# 纯提示性（注：...）段落：整段以「（注：」开头且不含具体金额/公司名
_NOTE_HINT_RE = re.compile(r"^（注[：:]")


def _is_pure_hint_note(line: str) -> bool:
    """判断以（注：开头的段落是否为纯提示性内容（不含具体金额/公司名则视为提示）。"""
    if not _NOTE_HINT_RE.match(line):
        return False
    # 含具体金额（数字+万/元/%）或公司名（XX公司）的不是纯提示
    if re.search(r"\d+[万元%]", line):
        return False
    return True


def clean_text_after(raw: str) -> str:
    """清理 Word 表格后段落文字为种子 text_after_table。

    规则：
    1. 去掉 ``{{...}}`` 标记（seq/section/table 控制符）
    2. 去掉 ``【提示性内容】``
    3. 去掉 ``##`` 样式标记行
    4. 去掉纯提示性 ``（注：...）`` 段落（不含具体金额/公司名的注释）
    5. 逐行 strip，去掉空行
    6. 结果如果只剩标点符号则视为空
    """
    lines = raw.split("\n")
    cleaned: list[str] = []
    for line in lines:
        s = _TAG_RE.sub("", line)
        s = _HINT_BRACKET_RE.sub("", s)
        s = _SECTION_MARKER_RE.sub("", s)
        s = s.strip()
        if not s:
            continue
        if _PUNCT_ONLY_RE.match(s):
            continue
        if _is_pure_hint_note(s):
            continue
        cleaned.append(s)
    return "\n".join(cleaned)


def clean_parent_section(name: str) -> str:
    """去掉 parent_section 中括号内的提示性文字。

    例：``应收账款（以下不适用的，请删除；账龄可根据企业的分组进行修改）`` → ``应收账款``
    仅处理含「删除/修改/调整/提示/不适用」等关键词的括号，避免误删正常括号内容。
    """
    return _PARENT_HINT_RE.sub("", name).strip()


def _dedup_sibling_titles(text: str, sibling_titles: set[str]) -> str:
    """去掉 text_after 中等于同章节兄弟表 title 的行。

    Word 中表格后段落常混入下一张（或后续几张）表的标题——因为标题段落紧贴在
    ``{{table:...}}`` 标记之前，被收集到了上一张表的 text_after 中。
    渲染时会与兄弟表的标签/标题重复。

    策略：逐行检查，如果该行精确等于任意一个兄弟表的 title，则去掉。
    """
    if not text or not sibling_titles:
        return text
    lines = text.split("\n")
    filtered = [line for line in lines if line.strip() not in sibling_titles]
    return "\n".join(filtered)


# ════════════════════════════════════════════════════════════════════
# Phase 6: text_after_table 同步 + parent_section 清理
# ════════════════════════════════════════════════════════════════════

def phase6_text_after_and_parent(
    word_tables: list[dict],
    json_data: list[dict] | dict,
    std: str,
    kind: str,  # "consol" | "standalone"
    dry_run: bool,
    verbose: bool,
) -> tuple[int, int]:
    """Phase 6: 从 Word 同步 text_after_table + 清理 parent_section。

    返回 ``(text_updated, parent_cleaned)``。
    """
    note_ch = note_chapter_for_std(std)
    text_updated = 0
    parent_cleaned = 0

    if kind == "consol":
        # ── 合并附注：按 section_id 匹配 ──
        by_sid = {e["section_id"]: e for e in json_data}

        # 构建同章节兄弟表 title 集合（按 parent_seq 分组），用于去重
        from collections import defaultdict
        _consol_groups: dict[int, list[dict]] = defaultdict(list)
        for e in json_data:
            _consol_groups[e.get("parent_seq", 0)].append(e)
        # 建立 section_id → 同组所有兄弟 title 的映射（排除自身）
        _sibling_titles: dict[str, set[str]] = {}
        for group in _consol_groups.values():
            all_titles = {e.get("title", "").strip() for e in group if e.get("title")}
            for e in group:
                own = e.get("title", "").strip()
                _sibling_titles[e["section_id"]] = all_titles - {own} if own else all_titles

        for wt in word_tables:
            p = parse_tag(wt["tag"])
            if not p:
                continue
            ch, sec = p.get("chapter", ""), p.get("section")
            sid = entry_sid(std, p)
            entry = by_sid.get(sid)
            if not entry or (ch == note_ch and sec is not None and identity_mismatch(entry, wt, std, sid)):
                continue
            # text_after_table
            raw = wt.get("text_after_raw", "")
            cleaned = clean_text_after(raw) if raw else ""
            # 去掉与同章节兄弟表 title 重复的行
            cleaned = _dedup_sibling_titles(cleaned, _sibling_titles.get(sid, set()))
            existing = (entry.get("text_after_table") or "").strip()
            if cleaned != existing:
                if not dry_run:
                    if cleaned:
                        entry["text_after_table"] = cleaned
                    elif "text_after_table" in entry:
                        del entry["text_after_table"]
                text_updated += 1
                if verbose:
                    preview = cleaned[:50].replace("\n", "\\n") if cleaned else "(空)"
                    print(f"    P6-T {sid}: text_after → {preview}")

        # parent_section 清理
        for entry in json_data:
            ps = entry.get("parent_section", "")
            cleaned_ps = clean_parent_section(ps)
            if cleaned_ps != ps:
                if not dry_run:
                    entry["parent_section"] = cleaned_ps
                parent_cleaned += 1
                if verbose:
                    print(f"    P6-P {entry['section_id']}: parent '{ps[:40]}' → '{cleaned_ps[:40]}'")

    elif kind == "standalone":
        # ── 单体附注：按 (section_num, table_idx) 匹配 ──
        sections = json_data.get("sections", []) if isinstance(json_data, dict) else []
        word_by_key: dict[tuple[int, int], dict] = {}
        for wt in word_tables:
            p = parse_tag(wt["tag"])
            if not p or p.get("chapter") != note_ch or p.get("section") is None:
                continue
            word_by_key[(p["section"], p["table_idx"])] = wt

        for s in sections:
            sn = s.get("section_number", "")
            m = re.match(rf"^{re.escape(note_ch)}、(\d+)", sn)
            if not m:
                continue
            parent_seq = int(m.group(1))
            word_idx = 0
            tables_list = s.get("tables", [])
            # 同 section 所有非续表 name 集合（用于去重）
            all_names = {
                t2.get("name", "").strip()
                for t2 in tables_list
                if t2.get("continuation_of_index") is None and t2.get("name")
            }
            for ti, t in enumerate(tables_list):
                if t.get("continuation_of_index") is not None:
                    continue
                wt = word_by_key.get((parent_seq, word_idx))
                word_idx += 1
                if not wt:
                    continue
                raw = wt.get("text_after_raw", "")
                cleaned = clean_text_after(raw) if raw else ""
                # 去掉与同 section 兄弟表 name 重复的行（排除自身）
                own_name = (t.get("name") or "").strip()
                siblings = all_names - {own_name} if own_name else all_names
                cleaned = _dedup_sibling_titles(cleaned, siblings)
                existing = (t.get("text_after_table") or "").strip()
                if cleaned != existing:
                    if not dry_run:
                        if cleaned:
                            t["text_after_table"] = cleaned
                        elif "text_after_table" in t:
                            del t["text_after_table"]
                    text_updated += 1
                    if verbose:
                        preview = cleaned[:50].replace("\n", "\\n") if cleaned else "(空)"
                        print(f"    P6-T {sn} t[{ti}]: text_after → {preview}")

    return text_updated, parent_cleaned


# ════════════════════════════════════════════════════════════════════
# Title 漂移检测（--check 门禁）
# ════════════════════════════════════════════════════════════════════

def check_title_drift(
    word_tables: list[dict],
    json_data: list[dict] | dict,
    std: str,
    kind: str,  # "consol" | "standalone"
    verbose: bool = False,
) -> list[str]:
    """比对 Word 与 JSON 的 title，返回不一致条目列表（空 = 无漂移）。

    合并附注：``json_data`` 是 ``list[dict]``，按 section_id 匹配。
    单体附注：``json_data`` 是 ``dict``（顶层带 sections），按 (section_num, table_idx) 匹配。
    """
    note_ch = note_chapter_for_std(std)
    drifts: list[str] = []

    if kind == "consol":
        by_sid = {e["section_id"]: e for e in json_data}
        # 正向：Word 有但 JSON title 不同
        word_sids: set[str] = set()
        for wt in word_tables:
            p = parse_tag(wt["tag"])
            if not p or p.get("section") is None:
                continue
            ch, sec = p.get("chapter", ""), p.get("section")
            sid = entry_sid(std, p)
            word_sids.add(sid)
            entry = by_sid.get(sid)
            if not entry or (ch == note_ch and sec is not None and identity_mismatch(entry, wt, std, sid)):
                continue
            w_title = (wt.get("title_text") or "").strip()
            j_title = (entry.get("title") or "").strip()
            if w_title and w_title != j_title:
                msg = f"  {sid}: W→J '{w_title[:50]}' vs '{j_title[:50]}'"
                drifts.append(msg)
                if verbose:
                    print(msg)
        # 反向：JSON 有 title 但 Word 中无对应 tag（仅报信息，不算 drift 错误）
        if verbose:
            for entry in json_data:
                sid = entry.get("section_id", "")
                if sid not in word_sids and entry.get("title"):
                    print(f"  [info] {sid}: JSON 有但 Word 无对应 tag（可能来自 Markdown 种子）")

    elif kind == "standalone":
        # 单体存在“底稿按期间拆表、Word 只写续表提示”等有意差异，位置式比较会从第一处拆表起整体错位。
        # 权威校验是 ``check_note_template_word_tree.py --check``；这里不再产生重复且错误的漂移结论。
        return []

    return drifts


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
    parser.add_argument("--phase", type=str, default="all", help="1/2/3/4/5/6/all")
    parser.add_argument("--std", type=str, default="all", help="soe/listed/all")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    # --check 等价于 --dry-run 但会在有差异时 exit 2
    if args.check:
        args.dry_run = True

    phases = [1, 2, 3, 4, 5, 6] if args.phase == "all" else [int(args.phase)]
    stds = ["soe", "listed"] if args.std == "all" else [args.std]

    print(f"模式: {'CHECK' if args.check else 'DRY-RUN' if args.dry_run else 'WRITE'}, phases={phases}, stds={stds}")

    total_drift = 0  # --check 模式计数漂移文件数
    total_title_drift: list[str] = []  # title 漂移明细

    for std in stds:
        print(f"\n{'='*60}")
        print(f"  {std}")
        print(f"{'='*60}")

        # 加载 Word
        consol_docx = DOCX_DIR / f"{std}_consolidated.docx"
        standalone_docx = DOCX_DIR / f"{std}_standalone.docx"

        consol_word: list[dict] = []
        consol_data: list[dict] = []
        consol_json_path = DATA_DIR / f"consol_note_sections_{std}.json"

        if 1 in phases or 2 in phases or 3 in phases or 6 in phases:
            print(f"  解析 {consol_docx.name}...")
            consol_word = extract_all_word_tables(consol_docx)
            print(f"  Word 表格: {len(consol_word)}")

            consol_data = json.loads(consol_json_path.read_text("utf-8"))
            print(f"  JSON 表格: {len(consol_data)}")
            sids = {e.get("section_id") for e in consol_data}
            for key in (k for k in (*STANDALONE_INSTANTIATED, *LOGICAL_COLUMNS) if k[0] == std and k[1] not in sids):
                IDENTITY_MISMATCHES.append(f"[{std}] {key[1]} 登记为占位列按单体实例化 / 按逻辑列存，但种子里没有该条目，请核对登记")

            if 1 in phases:
                struct_n, title_n = phase1_consol(consol_word, consol_data, std, args.dry_run, args.verbose)
                parts = []
                if struct_n:
                    parts.append(f"{struct_n} 结构更新")
                if title_n:
                    parts.append(f"{title_n} title同步")
                print(f"  Phase 1 (列修复+mh+title): {', '.join(parts) if parts else '0 更新'}")

            if 2 in phases:
                n = phase2_consol(consol_word, consol_data, std, args.dry_run, args.verbose)
                print(f"  Phase 2 (缺失表): {n} 新增")

            if 3 in phases:
                added_n, title_n = phase3_consol(consol_word, consol_data, std, args.dry_run, args.verbose)
                parts = []
                if added_n:
                    parts.append(f"{added_n} 新增")
                if title_n:
                    parts.append(f"{title_n} title同步")
                print(f"  Phase 3 (非注释章): {', '.join(parts) if parts else '0'}")

            if 6 in phases:
                txt_n, ps_n = phase6_text_after_and_parent(consol_word, consol_data, std, "consol", args.dry_run, args.verbose)
                parts = []
                if txt_n:
                    parts.append(f"{txt_n} text_after")
                if ps_n:
                    parts.append(f"{ps_n} parent清理")
                print(f"  Phase 6 (text+parent): {', '.join(parts) if parts else '0'}")

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

        standalone_word: list[dict] = []
        standalone_data: dict = {}
        standalone_json_path = DATA_DIR / f"note_template_{std}.json"

        if 4 in phases or 5 in phases or 6 in phases:
            print(f"  解析 {standalone_docx.name}...")
            standalone_word = extract_all_word_tables(standalone_docx)
            print(f"  Word 表格: {len(standalone_word)}")

            standalone_data = json.loads(standalone_json_path.read_text("utf-8"))
            n_sections = len(standalone_data.get("sections", []))
            n_tables = sum(len(s.get("tables", [])) for s in standalone_data.get("sections", []))
            print(f"  JSON sections: {n_sections}, tables: {n_tables}")

            if 4 in phases:
                n = phase4_standalone(standalone_word, standalone_data, std, args.dry_run, args.verbose)
                print(f"  Phase 4 (group补齐): {n} 更新")

            if 5 in phases:
                n = phase5_standalone_title(standalone_word, standalone_data, std, args.dry_run, args.verbose)
                print(f"  Phase 5 (单体title，已退役): {n} 更新")

            if 6 in phases:
                txt_n, _ = phase6_text_after_and_parent(standalone_word, standalone_data, std, "standalone", args.dry_run, args.verbose)
                print(f"  Phase 6 (单体text_after): {txt_n} 更新")

            changed = write_json(standalone_json_path, standalone_data, args.dry_run)
            if changed:
                total_drift += 1
                print(f"  ✅ {standalone_json_path.name} {'(would write)' if args.dry_run else 'written'}")
            else:
                print(f"  (无变化) {standalone_json_path.name}")

        # ── --check 模式：title 漂移检测 ──
        if args.check:
            if consol_word and consol_data:
                drifts = check_title_drift(consol_word, consol_data, std, "consol", args.verbose)
                if drifts:
                    total_title_drift.extend([f"[{std} consol] {d}" for d in drifts])
            if standalone_word and standalone_data:
                drifts = check_title_drift(standalone_word, standalone_data, std, "standalone", args.verbose)
                if drifts:
                    total_title_drift.extend([f"[{std} standalone] {d}" for d in drifts])

    # ── 身份校验（R7.6）：对不上的不写；已知标记缺陷单列，登记了却对上了 = 登记失效 ──
    if IDENTITY_MISMATCHES:
        print(f"\n🔴 Word 表与种子身份对不上 {len(IDENTITY_MISMATCHES)} 处（未写入）:")
        print("\n".join(f"  {m}" for m in IDENTITY_MISMATCHES))
    for key, reason in KNOWN_SECTION_GAPS.items():
        if key[0] in stds and (1 in phases or 6 in phases) and key not in KNOWN_GAP_HITS:
            IDENTITY_MISMATCHES.append(f"[{key[0]}] Word 节 {key[1]} 登记为已知标记缺陷但已对得上，请删除该登记")
            print(f"🔴 {IDENTITY_MISMATCHES[-1]}")
    if args.check and IDENTITY_MISMATCHES:
        total_drift += 1

    # ── 最终结果 ──
    if args.check:
        if total_title_drift:
            print(f"\n🔴 title 漂移 {len(total_title_drift)} 处:")
            for d in total_title_drift:
                print(d)
            total_drift += 1  # 计入漂移
        if total_drift:
            print(f"\n🔴 --check 失败：{total_drift} 个问题，请重跑 sync 工具")
            sys.exit(2)
        else:
            print("\n✅ --check 通过：模板结构同步无漂移；单体标题/表序由 check_note_template_word_tree.py --check 管理")
    elif total_drift:
        print(f"\n完成：{total_drift} 个文件已更新")


if __name__ == "__main__":
    main()
