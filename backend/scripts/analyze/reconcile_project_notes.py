"""附注数值全量核对（只读；spec disclosure-note-template-word-realignment Task 34 / US-11）。

对一个项目一个年度的附注逐表核对三层，列出全部不符：

- A 取数格：公式推送规则声明的每个附注格，按 dry-run 重算的公式值对现值 —— 一致 / 待推送 / 人工保留 / 推送不到（带原因）。
- B 报表：能按名称对上资产负债表、利润表行的章节，报表数（本期 ↔ 期末、上期 ↔ 期初）须出现在该章节某张表的汇总行
  （或与章节同名的行）里；对不上的列出该章节全部汇总格、报表公式与试算表来源科目余额，供判断根因。
- C 表内勾稽：只有一个汇总行的表，合计 = 上方明细之和（「减：」行取负，「其中：」行与比例 / 文字列不计）；明细全空、
  合计有数记「只有合计」（取数只到合计，明细没有来源）。

看的是用户看到的表（底稿子表读时投影后），与编辑器 / Word 导出同口径。只读：推送 dry-run 在事务里跑完即回滚，不写库、
不发事件。用法::

    python backend/scripts/analyze/reconcile_project_notes.py --project <id> [--year 2025] --out <目录>

退出码：0 = 没有不符；2 = 有不符（报告里逐条列出）；1 = 运行失败。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

TOL = 0.01
_WS = re.compile(r"[\s\u3000]+")
_ENUM = re.compile(r"^(?:[一二三四五六七八九十]+、|\d+[、.．]|[（(]\d+[)）]|[①②③④⑤⑥⑦⑧⑨⑩])")
_PREFIXES = ("减：", "减:", "加：", "加:", "其中：", "其中:")
_TAIL_PAREN = re.compile(r"[（(][^（()）]*[)）]$")
#: 不参与求和的列：比例 / 比率 / 文字说明
_SKIP_HEADER = re.compile(r"比例|比率|%|％|率|账龄|原因|说明|名称|性质|类型|方式|是否|期限|款项")
_TOTAL_LABELS = {"合计", "总计", "小计"}


def num(value: Any) -> float | None:
    """单元格数值；空 / 文字 / 布尔 ⇒ None（0 是数）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("，", "")
    if not text or text in {"-", "—", "－"}:
        return None
    try:
        return float(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def norm_name(text: Any) -> str:
    """名称比较口径：去空白、序号（一、/ 1、/（1））、减 / 加 / 其中 前缀、末尾括注。"""
    s = _WS.sub("", str(text or ""))
    for _ in range(3):
        before = s
        s = _ENUM.sub("", s)
        for prefix in _PREFIXES:
            if s.startswith(prefix):
                s = s[len(prefix):]
        s = _TAIL_PAREN.sub("", s)
        if s == before:
            break
    return s


def is_total_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    label = _WS.sub("", str(row.get("label") or ""))
    return bool(row.get("is_total")) or row.get("row_type") in ("total", "subtotal") or label in _TOTAL_LABELS


def tables_of(table_data: Any) -> list[dict]:
    if not isinstance(table_data, dict):
        return []
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        return [t for t in tables if isinstance(t, dict)]
    return [table_data] if isinstance(table_data.get("rows"), list) else []


def _cell(row: dict, j: int) -> Any:
    values = row.get("values")
    return values[j] if isinstance(values, list) and j < len(values) else None


def _finding(layer: str, status: str, code: str, table: str, **extra: Any) -> dict:
    return {"layer": layer, "status": status, "section": code, "table": table, **extra}


# ── C 表内勾稽 ────────────────────────────────────────────────────────────────


def check_table_arithmetic(code: str, table: dict) -> list[dict]:
    """只有一个汇总行的表：每个金额列 合计 = 上方明细之和（「减：」取负、「其中：」不计）。返回逐列结果（含一致）。"""
    rows = [r for r in (table.get("rows") or []) if isinstance(r, dict)]
    name = str(table.get("name") or "")
    totals = [i for i, r in enumerate(rows) if is_total_row(r)]
    if len(totals) != 1:
        has_value = any(num(v) not in (None, 0.0) for r in rows for v in (r.get("values") or []))
        if len(totals) > 1 and has_value:
            return [_finding("C", "未核", code, name, reason=f"{len(totals)} 个汇总行（分段口径未声明），表内勾稽不核")]
        return []
    ti = totals[0]
    headers = table.get("headers") or []
    width = max((len(r.get("values") or []) for r in rows), default=0)
    out: list[dict] = []
    for j in range(width):
        header = str(headers[j + 1]) if j + 1 < len(headers) else f"第{j + 1}列"
        if _SKIP_HEADER.search(_WS.sub("", header)):
            continue
        total = num(_cell(rows[ti], j))
        details: list[float] = []
        for r in rows[:ti]:
            label = _WS.sub("", str(r.get("label") or ""))
            if label.startswith(("其中：", "其中:")) or r.get("is_memo"):
                continue
            v = num(_cell(r, j))
            if v is not None:
                details.append(-v if label.startswith(("减：", "减:")) else v)
        where = {"row": str(rows[ti].get("label") or ""), "column": header}
        if not details:
            if total not in (None, 0.0):
                out.append(_finding("C", "只有合计", code, name, actual=total, **where,
                                    reason="明细行全空、只有合计有数（取数只到合计，明细没有来源）"))
            continue
        expected = round(sum(details), 2)
        if total is not None and abs(expected - total) <= TOL:
            out.append(_finding("C", "一致", code, name, expected=expected, actual=total, **where))
        else:
            out.append(_finding("C", "不符", code, name, expected=expected, actual=total, **where,
                                reason="合计 ≠ 上方明细之和" if total is not None else "明细有数、合计为空"))
    return out


# ── B 报表 ────────────────────────────────────────────────────────────────────


def report_index(report_rows: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for r in report_rows:
        index.setdefault(norm_name(r["row_name"]), []).append(r)
    return index


def match_report(name: str, index: dict[str, list[dict]]) -> list[tuple[str, dict | None, str | None]]:
    """章节名 → [(名称, 报表行 | None, 对不上的原因)]。整名对不上时按「、」「和」「与」拆开逐项对（营业收入和营业成本）。"""
    whole = norm_name(name)
    parts = [whole] if whole in index else [p for p in re.split(r"[、和与及]", whole) if p] or [whole]
    out = []
    for part in parts:
        cands = index.get(part) or []
        amounts = {(c["current"], c["prior"]) for c in cands}
        if not cands:
            out.append((part, None, None))
        elif len(amounts) > 1:
            out.append((part, None, f"报表有 {len(cands)} 行「{part}」且金额不同（{[c['row_code'] for c in cands]}），不比"))
        else:
            out.append((part, cands[0], None))
    return out


def summary_cells(tables: list[dict], part: str) -> list[dict]:
    """章节内可对报表的格：各表汇总行与「与章节同名」的行的全部数值格。"""
    cells = []
    for t in tables:
        headers = t.get("headers") or []
        for r in t.get("rows") or []:
            if not isinstance(r, dict) or not (is_total_row(r) or norm_name(r.get("label")) == part):
                continue
            for j, v in enumerate(r.get("values") or []):
                value = num(v)
                if value is not None:
                    cells.append({"table": str(t.get("name") or ""), "row": str(r.get("label") or ""),
                                  "column": str(headers[j + 1]) if j + 1 < len(headers) else f"第{j + 1}列",
                                  "value": value})
    return cells


_CUR_WORDS = ("期末", "本期", "本年", "年末")
_PRIOR_WORDS = ("期初", "上期", "上年", "年初")


def _column_period(header: str) -> str | None:
    h = _WS.sub("", header)
    cur, prior = any(w in h for w in _CUR_WORDS), any(w in h for w in _PRIOR_WORDS)
    return "current" if cur and not prior else "prior" if prior and not cur else None


def _hint(cells: list[dict], rrow: dict, tb: dict[str, dict[str, float]], key: str) -> str:
    if not cells:
        return "附注章节没有汇总格有数（该节无取数，或推送跳过）"
    col = "audited" if key == "current" else "opening"
    singles = [c for c in (rrow.get("source_accounts") or [])
               if abs((tb.get(c) or {}).get(col) or 0.0) > TOL
               and any(abs(cell["value"] - tb[c][col]) <= TOL for cell in cells)]
    if singles:
        return (f"附注汇总格等于科目 {'/'.join(singles)} 的余额，报表公式 {rrow.get('formula')} 还加减了其他科目"
                "（口径不同：原值 / 净额，或报表少扣备抵）")
    return "附注汇总格与报表数都对不上，需人工核对"


def check_report(code: str, name: str, tables: list[dict], index: dict[str, list[dict]],
                 tb: dict[str, dict[str, float]]) -> list[dict]:
    """章节对报表：报表数须出现在该章节的汇总格（列期间认得出时只认同一期间的列）。"""
    out: list[dict] = []
    for part, rrow, why in match_report(name, index):
        if rrow is None:
            if why:
                out.append(_finding("B", "未核", code, "", item=part, reason=why))
            continue
        cells = summary_cells(tables, part)
        for period, key in (("期末 / 本期", "current"), ("期初 / 上期", "prior")):
            target = rrow[key]
            if target is None:
                continue
            base = {"item": part, "report_row": f"{rrow['row_code']} {rrow['row_name']}", "period": period,
                    "expected": target, "formula": rrow.get("formula")}
            usable = [c for c in cells if _column_period(c["column"]) in (None, key)]
            if abs(target) <= TOL:
                nonzero = [c for c in usable if abs(c["value"]) > TOL]
                status = "不符" if nonzero else "一致"
                out.append(_finding("B", status, code, "", **base, cells=nonzero[:12],
                                    reason="报表为 0，附注汇总格有数" if nonzero else None))
                continue
            hits = [c for c in usable if abs(c["value"] - target) <= TOL]
            if hits:
                out.append(_finding("B", "一致", code, hits[0]["table"], **base, actual=hits[0]["value"],
                                    at=f"{hits[0]['row']} / {hits[0]['column']}"))
            else:
                out.append(_finding("B", "不符", code, "", **base, reason=_hint(usable, rrow, tb, key),
                                    cells=usable[:12]))
    return out


# ── A 取数格（公式推送 dry-run）────────────────────────────────────────────────

_A_STATUS = {"unchanged": "一致", "write": "不符", "skipped": "推送不到", "conflict": "推送不到",
             "fallback_to_total": "只有合计"}


def split_addr(addr: str) -> tuple[str, str, str, str]:
    """``note://节/表/行.end`` → (节, 表, 行, 期间)；缺的段为空串。"""
    body = addr[len("note://"):] if addr.startswith("note://") else addr
    parts = body.split("/", 2)
    section = parts[0] if parts else ""
    table = parts[1] if len(parts) > 1 else ""
    row, period = "", ""
    if len(parts) > 2:
        row, _, period = parts[2].rpartition(".")
        if not row:
            row, period = period, ""
    return section, table, row, {"end": "期末 / 本期", "prior": "期初 / 上期"}.get(period, period)


def check_push_items(items: list[Any]) -> list[dict]:
    out: list[dict] = []
    for it in items:
        if getattr(it, "domain", None) != "note":
            continue
        section, table, row, period = split_addr(str(it.addr_id or ""))
        action = str(it.action)
        status = "人工保留" if action.startswith("keep_") else _A_STATUS.get(action, action)
        formula, current = num(it.formula), num(it.current)
        if status == "人工保留" and formula is not None and current is not None and abs(formula - current) <= TOL:
            status = "一致"
        reason = it.reason or ("附注现值 ≠ 公式值（推送待执行）" if action == "write" else None)
        out.append(_finding("A", status, section, table, row=row, period=period, rule=it.rule_id,
                            expected=formula, actual=current, reason=reason))
    return out


# ── 取数与汇总 ────────────────────────────────────────────────────────────────


async def _load(db: Any, project_id: uuid.UUID, year: int) -> tuple[list, list[dict], dict[str, dict[str, float]]]:
    import sqlalchemy as sa

    notes = (await db.execute(sa.text(
        "SELECT note_section, section_title, account_name, table_data FROM disclosure_notes "
        "WHERE project_id = :p AND year = :y AND NOT is_deleted ORDER BY sort_order NULLS LAST, note_section"),
        {"p": project_id, "y": year})).all()
    report = [{"row_code": r[0], "row_name": r[1], "current": num(r[2]), "prior": num(r[3]), "formula": r[4],
               "source_accounts": list(r[5] or [])} for r in (await db.execute(sa.text(
                   "SELECT row_code, row_name, current_period_amount, prior_period_amount, formula_used, source_accounts "
                   "FROM financial_report WHERE project_id = :p AND year = :y AND NOT is_deleted "
                   "AND report_type::text IN ('balance_sheet', 'income_statement') ORDER BY report_type, row_code"),
                   {"p": project_id, "y": year})).all()]
    tb: dict[str, dict[str, float]] = {}
    for code, audited, opening in (await db.execute(sa.text(
            "SELECT standard_account_code, audited_amount, opening_balance FROM trial_balance "
            "WHERE project_id = :p AND year = :y AND NOT is_deleted"), {"p": project_id, "y": year})).all():
        bucket = tb.setdefault(code, {"audited": 0.0, "opening": 0.0})
        bucket["audited"] += num(audited) or 0.0
        bucket["opening"] += num(opening) or 0.0
    return notes, report, tb


async def reconcile(db: Any, project_id: uuid.UUID, year: int) -> dict:
    """三层核对；推送 dry-run 后回滚会话（只读）。"""
    from app.services.formula_push.engine import MANUAL, run
    from app.services.note_content_utils import effective_table_data

    notes, report, tb = await _load(db, project_id, year)
    await db.rollback()
    push = await run(db, project_id=project_id, year=year, trigger=MANUAL, dry_run=True)
    await db.rollback()
    findings = check_push_items(list(push.items))
    index = report_index(report)
    for code, title, account, table_data in notes:
        tables = tables_of(effective_table_data(table_data))
        if not tables:
            continue
        findings.extend(check_report(code, account or title, tables, index, tb))
        for t in tables:
            findings.extend(check_table_arithmetic(code, t))
    summary = Counter(f"{f['layer']}:{f['status']}" for f in findings)
    return {"project_id": str(project_id), "year": year, "push_status": push.status,
            "summary": dict(sorted(summary.items())), "findings": findings}


_LAYER = {"A": "取数格（公式推送）", "B": "报表", "C": "表内勾稽"}


def _md_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def to_markdown(rep: dict, title: str) -> str:
    lines = [f"# 附注数值全量核对：{title} {rep['year']}", "",
             f"- 项目 `{rep['project_id']}`；推送 dry-run 状态 {rep['push_status']}", "", "| 层 | 状态 | 项数 |",
             "|---|---|---|"]
    lines += [f"| {_LAYER[k.split(':')[0]]} | {k.split(':')[1]} | {v} |" for k, v in rep["summary"].items()]
    for layer in ("A", "B", "C"):
        rows = [f for f in rep["findings"] if f["layer"] == layer and f["status"] != "一致"]
        if not rows:
            continue
        lines += ["", f"## {layer} {_LAYER[layer]}（非一致 {len(rows)} 项）", "",
                  "| 状态 | 章节 | 表 | 行 / 列 / 期间 | 应为 | 现值 | 说明 |", "|---|---|---|---|---|---|---|"]
        for f in sorted(rows, key=lambda x: (x["status"], x["section"], x["table"])):
            where = " / ".join(str(x) for x in (f.get("row") or f.get("item"), f.get("column"), f.get("period")) if x)
            note = f.get("reason") or ""
            if f.get("report_row"):
                note = f"{f['report_row']}（{f.get('formula')}）；{note}"
            if f.get("cells"):
                note += "；附注汇总格：" + "，".join(f"{c['table']}/{c['row']}/{c['column']}={c['value']:,.2f}"
                                               for c in f["cells"][:6])
            if f.get("rule"):
                note = f"{f['rule']}：{note}"
            lines.append(f"| {f['status']} | {_md_cell(f['section'])} | {_md_cell(f['table'])} | {_md_cell(where)} | "
                         f"{_md_cell(f.get('expected'))} | {_md_cell(f.get('actual'))} | {_md_cell(note)} |")
    return "\n".join(lines) + "\n"


async def _main(args: argparse.Namespace) -> int:
    import sqlalchemy as sa

    from app.core.database import async_session

    project_id = uuid.UUID(args.project)
    async with async_session() as db:
        row = (await db.execute(sa.text(
            "SELECT name, EXTRACT(YEAR FROM audit_period_end)::int FROM projects WHERE id = :p AND NOT is_deleted"),
            {"p": project_id})).first()
        if row is None:
            print(f"项目 {project_id} 不存在或已删除")
            return 1
        year = args.year or row[1]
        rep = await reconcile(db, project_id, year)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"note_reconcile_{args.project[:8]}_{year}"
    stem.with_suffix(".json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    stem.with_suffix(".md").write_text(to_markdown(rep, row[0]), encoding="utf-8")
    print(json.dumps(rep["summary"], ensure_ascii=False))
    print(f"报告：{stem.with_suffix('.md')}")
    return 2 if any(k.endswith(":不符") for k in rep["summary"]) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="附注数值全量核对（只读）")
    parser.add_argument("--project", required=True, help="项目 id")
    parser.add_argument("--year", type=int, help="年度（默认项目审计年度）")
    parser.add_argument("--out", default=".", help="报告目录（写 JSON + Markdown）")
    return asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
