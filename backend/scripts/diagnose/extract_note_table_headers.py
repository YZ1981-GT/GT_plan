"""从附注**源 docx** 抽「章节 → 表 → 标题 + 两级表头」事实（只读）。

spec: note-template-columns-and-legacy-snapshot-closure（Task 7）

判据真源
--------
``docs/模版/`` 两份附注模板 docx —— 这是 ``backend/data/note_template_{listed,soe}.json``
的重建源头（那两份 JSON 是 md 重建产物，会压扁两级表头、把表头首格当表名）。

🔴 三条踩坑（本脚本已规避）
-----------------------------
1. **章号是 Word 自动编号，段落文本不含「十六、」** → 必须按 ``paragraph.style.name``
   是否为 ``Heading N`` 定位章节，用章号正则会 0 命中。
2. **两版 Heading 层级完全不同**：listed 是 ``Heading 1``=章 / ``Heading 2``=节；
   **soe 是 ``Heading 1``=章 / ``Heading 3``=节 / ``Heading 4``=子节**（第四章会计政策、
   第八章项目注释都跳过 Heading 2）→ 按 ``Heading 2`` 抽节在 soe 上会漏掉全部科目节。
3. **平台自带的 ``data/audit_report_templates/disclosure_notes/*.docx`` 只对
   ``五、N`` 科目章节埋了 ``##STYLE_REF:table:CODE:N##`` 标记**，`三、`/`十四、` 等
   非科目章节没有标记 → 那条路对本 spec 的 ③ 类不可用，必须回到源 docx。

用法
----
    python backend/scripts/diagnose/extract_note_table_headers.py
    python backend/scripts/diagnose/extract_note_table_headers.py --out backend/data/note_table_headers_source_facts.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[2]
REPO_ROOT = _HERE.parents[3]

DOCX_PATHS = {
    "listed": REPO_ROOT
    / "docs"
    / "模版"
    / "1.上市公司年审报表及附注-2026.01"
    / "1.上市公司年审报表及附注-2026.01"
    / "3.2025年度上市公司财务报表附注模板-2026.01.15.docx",
    "soe": REPO_ROOT
    / "docs"
    / "模版"
    / "1、2025年度财务决算审计报告-2026.01.06"
    / "1、2025年度财务决算审计报告-国企"
    / "1.1-2025国企财务报表附注20260119.docx",
}

DEFAULT_OUT = BACKEND_ROOT / "data" / "note_table_headers_source_facts.json"

_HEADING_RE = re.compile(r"^Heading\s+(\d+)$", re.I)
# 中文标题里的「（N）」「N．」「N、」前缀
_NUM_PREFIX_RE = re.compile(
    r"^\s*(?:[（(]\s*[0-9０-９一二三四五六七八九十]+\s*[)）]|[0-9]+\s*[.、．]|"
    r"[①②③④⑤⑥⑦⑧⑨⑩]|[A-Za-z]\s*[.、．])\s*"
)
# 明显不是表标题的段落
_NOT_TITLE_PREFIX = ("【", "注：", "提示", "说明：")

# 🔴 R3.2 允许的 guidance 三种来源里，②「准则/财会文号条款」的识别正则。
# 附注模板里的条款引用形态实测有：`15号文第二十六条` / `（15号文第四条，…` /
# `财会〔2018〕15号` / `企业会计准则第X号` / `国资委` 等。
_CLAUSE_RE = re.compile(
    r"(\d+\s*号文|财会\s*[〔\[]|企业会计准则第|准则第\s*\d+\s*号|"
    r"信息披露编报规则|国资委|证监会|第[一二三四五六七八九十百]+条)"
)


@dataclass
class TableFact:
    index: int
    title_candidate: str
    title_source: str
    header_rows: int
    level1: list[str] = field(default_factory=list)
    level2: list[str] = field(default_factory=list)
    grid_cols: int = 0
    merges: list[dict[str, Any]] = field(default_factory=list)
    body_first_col: list[str] = field(default_factory=list)
    # 🔴 Task 12（guidance 补齐）新增：**逐表**指引段候选
    # 判据方向：附注模板 docx 里表前段落分两类 —— ①表标题（短、常带 `（N）` 编号）
    # ②编制指引（蓝字，多在「（括号）」内 / 以「注：」「提示」开头 / 引 15 号文条款）。
    # 原实现用 `_NOT_TITLE_PREFIX` 把 ② 当噪声**丢弃**；而它正是 R3.2 允许的
    # guidance 来源之一，且**必须逐表取**——按「同章有指引段」的章级判据会把
    # A 表的指引贴到 B 表上（实测 listed `三、无形资产` 两张表会共用同一段）。
    guidance_candidates: list[dict[str, str]] = field(default_factory=list)


def _open(path: Path):
    try:
        from docx import Document  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(f"[ERR] 缺少 python-docx：{exc}") from exc
    if not path.exists():
        raise SystemExit(f"[ERR] 源 docx 不存在：{path}")
    return Document(str(path))


def _cell_text(cell) -> str:
    return re.sub(r"\s+", " ", (cell.text or "")).strip()


def _row_cells(table, row_idx: int) -> list[str]:
    try:
        row = table.rows[row_idx]
    except IndexError:
        return []
    return [_cell_text(c) for c in row.cells]


def _detect_header_rows(table) -> tuple[int, list[str], list[str], list[dict[str, Any]]]:
    """判两级表头：第 0 行有横向合并（同一 tc 重复出现）即视为两级。

    python-docx 的 ``row.cells`` 对 ``gridSpan`` 会重复返回同一个 ``_Cell``，
    对 ``vMerge`` 亦然 —— 故「相邻同值且底层 tc 相同」即为合并。
    """
    r0 = _row_cells(table, 0)
    if not r0:
        return 0, [], [], []
    try:
        tcs0 = [c._tc for c in table.rows[0].cells]  # noqa: SLF001
    except IndexError:
        tcs0 = []
    merges: list[dict[str, Any]] = []
    i = 0
    horizontal_span = False
    while i < len(tcs0):
        j = i
        while j + 1 < len(tcs0) and tcs0[j + 1] is tcs0[i]:
            j += 1
        if j > i:
            horizontal_span = True
            merges.append({"row": 0, "start": i, "span": j - i + 1, "text": r0[i]})
        i = j + 1

    if not horizontal_span or len(table.rows) < 2:
        return 1, r0, [], merges

    r1 = _row_cells(table, 1)
    # 两级：第 0 行是父表头，第 1 行是叶子；纵向合并的列在 r1 里与 r0 同值
    return 2, r0, r1, merges


def scan_docx(variant: str) -> dict[str, Any]:
    from docx.oxml.ns import qn  # noqa: PLC0415
    from docx.table import Table  # noqa: PLC0415
    from docx.text.paragraph import Paragraph  # noqa: PLC0415

    doc = _open(DOCX_PATHS[variant])
    body = doc.element.body

    heading_stack: dict[int, str] = {}
    current_key = "(preamble)"
    per_section: dict[str, list[TableFact]] = {}
    section_meta: dict[str, dict[str, Any]] = {}
    recent_paras: list[str] = []

    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            para = Paragraph(child, doc)
            text = re.sub(r"\s+", " ", (para.text or "")).strip()
            style = (para.style.name if para.style is not None else "") or ""
            m = _HEADING_RE.match(style.strip())
            if m and text:
                lvl = int(m.group(1))
                heading_stack[lvl] = text
                for deeper in [k for k in heading_stack if k > lvl]:
                    heading_stack.pop(deeper, None)
                current_key = " / ".join(
                    heading_stack[k] for k in sorted(heading_stack)
                )
                section_meta.setdefault(
                    current_key,
                    {
                        "heading_level": lvl,
                        "heading_text": text,
                        "path": [heading_stack[k] for k in sorted(heading_stack)],
                    },
                )
                recent_paras = []
                continue
            if text:
                recent_paras.append(text)
                if len(recent_paras) > 6:
                    recent_paras.pop(0)
        elif child.tag == qn("w:tbl"):
            table = Table(child, doc)
            facts = per_section.setdefault(current_key, [])
            title, src = _pick_title(recent_paras)
            hrows, l1, l2, merges = _detect_header_rows(table)
            facts.append(
                TableFact(
                    index=len(facts),
                    title_candidate=title,
                    title_source=src,
                    header_rows=hrows,
                    level1=l1,
                    level2=l2,
                    grid_cols=len(l1),
                    merges=merges,
                    body_first_col=[
                        _row_cells(table, r)[0] if _row_cells(table, r) else ""
                        for r in range(hrows, min(len(table.rows), hrows + 40))
                    ],
                    guidance_candidates=_pick_guidance(recent_paras, title),
                )
            )
            recent_paras = []

    return {
        "docx": str(DOCX_PATHS[variant].relative_to(REPO_ROOT)).replace("\\", "/"),
        "sections": {
            key: {
                **section_meta.get(key, {}),
                "tables": [t.__dict__ for t in facts],
            }
            for key, facts in per_section.items()
        },
    }


def _pick_guidance(recent: list[str], picked_title: str) -> list[str]:
    """从表前最近的段落里抽**指引段**候选（Task 12 的 guidance 真源）。

    🔴 为什么必须逐表抽、不能按章抽
    ------------------------------------------------------------------
    首轮探针按「同章有没有指引段」判可用性，得 listed 160/175、soe 43/59；
    但那是**章级**判据 —— 一个章节有 9 张表（如 `三、现金流量表项目注释`）时，
    按章取会把第 1 张表的指引贴到第 9 张表上 = 自造披露口径（违反 R3.2）。
    表前 6 段的缓冲区（``recent_paras``）天然就是「紧邻本表」的范围。

    判据（R3.2 只许三种来源，故只收这三类，其余一律丢弃）
    ------------------------------------------------------------------
    * **括注型指引**：整段被 ``（）`` 包裹，或以 ``（``/``注：``/``【`` 起头
      —— 附注模板用蓝字括注写编制指引，这是最主要的一类；
    * **条款引用**：含 ``15号文`` / ``第N条`` / ``准则`` / ``财会`` 等字样；
    * **提示型**：以 ``提示`` / ``说明`` 起头。

    刻意**不收**普通陈述段（如 `本公司无形资产包括【土地使用权…】等。`）——
    那是正文披露内容不是编制指引，写进 guidance 等于把示例当口径。

    Returns:
        去重后的候选列表（保序）；找不到返回 ``[]``（**不猜**，由 R3.3 处置）。
    """
    out: list[str] = []
    for text in recent:
        if not text or text == picked_title:
            continue
        if len(text) < 6:
            continue
        wrapped = text.startswith(("（", "(")) and text.rstrip().endswith(("）", ")"))
        is_bracket = wrapped or text.startswith(("（", "(", "【", "注：", "注:"))
        is_clause = bool(_CLAUSE_RE.search(text))
        is_hint = text.lstrip("【（(").startswith(("提示", "说明"))
        if is_bracket or is_clause or is_hint:
            if text not in out:
                out.append(text)
    return out


def _pick_title(recent: list[str]) -> tuple[str, str]:
    """从表前最近的段落里挑标题候选。

    优先「带 `（N）`/`N.` 编号且 ≤40 字」的段落（附注模板的表标题范式），
    否则取最后一个不像指引的短段落；都没有则空串（**不猜**）。
    """
    for text in reversed(recent):
        if text.startswith(_NOT_TITLE_PREFIX):
            continue
        if _NUM_PREFIX_RE.match(text):
            stripped = _NUM_PREFIX_RE.sub("", text).strip().rstrip("：:")
            if 2 <= len(stripped) <= 40:
                return stripped, "numbered_paragraph"
    for text in reversed(recent):
        if text.startswith(_NOT_TITLE_PREFIX):
            continue
        t = text.strip().rstrip("：:")
        if 2 <= len(t) <= 40 and "。" not in t:
            return t, "nearest_short_paragraph"
    return "", "none"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__ or "")
    ap.add_argument("--out", default=None)
    ap.add_argument("--variant", choices=["listed", "soe", "both"], default="both")
    args = ap.parse_args(argv)

    variants = ("listed", "soe") if args.variant == "both" else (args.variant,)
    payload: dict[str, Any] = {"generated_at": datetime.now(timezone.utc).isoformat()}
    for v in variants:
        data = scan_docx(v)
        payload[v] = data
        n_sec = len(data["sections"])
        n_tbl = sum(len(s["tables"]) for s in data["sections"].values())
        two_lvl = sum(
            1
            for s in data["sections"].values()
            for t in s["tables"]
            if t["header_rows"] == 2
        )
        titled = sum(
            1
            for s in data["sections"].values()
            for t in s["tables"]
            if t["title_candidate"]
        )
        print(
            f"[OK] {v}: sections={n_sec} tables={n_tbl} "
            f"two_level_header={two_lvl} title_found={titled}"
        )

    out = Path(args.out) if args.out else DEFAULT_OUT
    if not out.is_absolute():
        out = REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"[OK] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
