"""附注 legacy 快照 → `sub_table_data` 迁移（**默认只读 dry-run**）。

## 背景

`disclosure_notes.table_data` 的权威形态是 `sub_table_data`（`{表名: [业务键行]}`）
+ `_sub_table_columns`（`{表名: [ColumnDef]}`），由 `note_sub_table_projector` 读时投影。
但历史数据把结构直接持久化在 `table_data` 顶层的 `rows` / `_tables` 里；`sub_table_data`
为空时消费方会回退到这些旧快照 → 界面显示的是过期结构（含已从模板删除的
`header_label` 假数据行）。

## 实测（2026-07-29 全库）

| 指标 | 数量 |
|------|------|
| legacy 章节（`sub_table_data` 空 且 有 `rows`/`_tables`） | **572** |
| 其中同时有 `rows` + `_tables` | 460 |
| 其中只有 `rows`（无 `_tables`） | 112 |
| `_tables` 总表数 | 1036 |
| **`_tables` 完全没有 `columns` 的章节** | **456 / 460（99%）** |
| `_tables` 存在**重名**表的章节 | 58 |
| 表名等于表头首格（如「项  目」）的章节 | 79 |

→ **直接按 `_tables[].name` 建键不可行**：99% 缺列头（投影会降级成只显示行名）、
58 个会因重名互相覆盖丢表、79 个表名根本不是业务表名。列头与表名都必须靠模板补。

## 分类（本脚本的核心产出）

| 类别 | 判定 | 迁移策略 |
|------|------|----------|
| `by_name` | `_tables[].name` 与模板表名可一一匹配 | 按名迁移 + 从模板补 columns |
| `positional` | 表名无意义/重名，但**表数与模板相等** | 按序对齐（⚠️ 需人工抽样确认） |
| `single_row` | 只有顶层 `rows`，模板恰好 1 张表 | 用模板表名 |
| `manual` | 表数与模板不等 / 模板章节缺失 / 形态异常 | 必须人工，脚本跳过 |

## 用法

    python backend/scripts/fix/migrate_legacy_note_snapshots.py                 # dry-run 摘要
    python ... --out report.txt                                                 # 落盘明细
    python ... --check                                                          # CI：残留数 >0 则 exit 1
    python ... --project <uuid>                                                 # 限定项目
    python ... --apply --confirm                                                # 🔴 破坏性，Task 8 才用

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R3 / Task 3（dry-run）、Task 8（apply）
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

HEADER_LABEL_ROW_TYPE = "header_label"


# ════════════════════════════════════════════════════════════════════
# 纯函数：分类与转换计划
# ════════════════════════════════════════════════════════════════════


@dataclass
class TablePlan:
    """一张表的迁移计划。"""

    target_name: str
    source_index: int | None
    """来自 `_tables[i]`；`None` 表示来自顶层 `rows`"""
    row_count: int
    dropped_header_label_rows: int
    columns_from_template: bool


@dataclass
class NotePlan:
    note_id: str
    project: str
    note_section: str
    section_title: str
    kind: str
    """by_name / positional / single_row / manual"""
    reason: str = ""
    tables: list[TablePlan] = field(default_factory=list)
    legacy_table_count: int = 0
    legacy_row_total: int = 0

    @property
    def planned_row_total(self) -> int:
        return sum(t.row_count for t in self.tables)

    @property
    def is_actionable(self) -> bool:
        return self.kind != "manual" and bool(self.tables)


def _rows_of(obj: Any) -> list[dict[str, Any]]:
    r = obj.get("rows") if isinstance(obj, dict) else None
    return [x for x in r if isinstance(x, dict)] if isinstance(r, list) else []


def _strip_header_labels(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    kept = [r for r in rows if str(r.get("row_type") or "") != HEADER_LABEL_ROW_TYPE]
    return kept, len(rows) - len(kept)


def _name_is_meaningful(name: str, headers: Any) -> bool:
    """表名是否像业务表名（排除「项  目」这类表头首格被当成表名的情况）。"""
    n = str(name or "").strip()
    if not n:
        return False
    h0 = ""
    if isinstance(headers, list) and headers:
        h0 = str(headers[0] or "").strip()
    if h0 and n == h0:
        return False
    # 「项 目」「项  目」这类：去空格后 <= 2 字且是常见表头词
    compact = n.replace(" ", "").replace("\u3000", "")
    if compact in {"项目", "序号", "名称", "类别", "组合", "存货种类"}:
        return False
    return True


def build_note_plan(
    *,
    note_id: str,
    project: str,
    note_section: str,
    section_title: str,
    table_data: dict[str, Any],
    template_tables: list[dict[str, Any]] | None,
) -> NotePlan:
    """纯函数：为单个 legacy 章节生成迁移计划（不写库）。"""
    tpl = [t for t in (template_tables or []) if isinstance(t, dict) and t.get("name")]
    tpl_names = [str(t["name"]) for t in tpl]
    tpl_by_name = {str(t["name"]): t for t in tpl}

    legacy_tables = table_data.get("_tables")
    legacy_tables = [t for t in legacy_tables if isinstance(t, dict)] if isinstance(legacy_tables, list) else []
    top_rows = _rows_of(table_data)

    plan = NotePlan(
        note_id=note_id,
        project=project,
        note_section=note_section,
        section_title=section_title,
        kind="manual",
        legacy_table_count=len(legacy_tables),
        legacy_row_total=sum(len(_rows_of(t)) for t in legacy_tables) or len(top_rows),
    )

    if not tpl:
        plan.reason = "模板中无此章节或该章节无表（可能是自定义章节）"
        return plan

    # ── 只有顶层 rows（无 _tables）─────────────────────────────────
    if not legacy_tables:
        if not top_rows:
            plan.reason = "既无 _tables 也无非空 rows"
            return plan
        if len(tpl) != 1:
            plan.kind = "manual"
            plan.reason = f"只有单表 rows，但模板有 {len(tpl)} 张表 → 无法确定归属"
            return plan
        kept, dropped = _strip_header_labels(top_rows)
        plan.kind = "single_row"
        plan.tables = [
            TablePlan(tpl_names[0], None, len(kept), dropped, bool(tpl_by_name[tpl_names[0]].get("columns")))
        ]
        return plan

    # ── 有 _tables：先试按名匹配 ───────────────────────────────────
    names = [str(t.get("name") or "") for t in legacy_tables]
    meaningful = [
        _name_is_meaningful(n, legacy_tables[i].get("headers")) for i, n in enumerate(names)
    ]
    has_dup = len(set(names)) != len(names)

    if all(meaningful) and not has_dup and all(n in tpl_by_name for n in names):
        plan.kind = "by_name"
        for i, n in enumerate(names):
            kept, dropped = _strip_header_labels(_rows_of(legacy_tables[i]))
            plan.tables.append(
                TablePlan(n, i, len(kept), dropped, bool(tpl_by_name[n].get("columns")))
            )
        return plan

    # ── 退化为按序对齐（要求表数相等）──────────────────────────────
    if len(legacy_tables) == len(tpl):
        plan.kind = "positional"
        bad = []
        if has_dup:
            bad.append("重名")
        if not all(meaningful):
            bad.append("表名非业务名")
        unmatched = [n for n in names if n not in tpl_by_name]
        if unmatched:
            bad.append(f"{len(unmatched)} 个名字不在模板中")
        plan.reason = "按序对齐（" + "、".join(bad) + "）⚠️ 需人工抽样确认"
        for i, tname in enumerate(tpl_names):
            kept, dropped = _strip_header_labels(_rows_of(legacy_tables[i]))
            plan.tables.append(
                TablePlan(tname, i, len(kept), dropped, bool(tpl_by_name[tname].get("columns")))
            )
        return plan

    plan.kind = "manual"
    plan.reason = f"legacy {len(legacy_tables)} 张表 ≠ 模板 {len(tpl)} 张表，无法安全对齐"
    return plan


# ════════════════════════════════════════════════════════════════════
# DB 扫描与报告
# ════════════════════════════════════════════════════════════════════

_LEGACY_WHERE = (
    "dn.is_deleted = false "
    "AND (dn.table_data->'sub_table_data' IS NULL "
    "     OR jsonb_typeof(dn.table_data->'sub_table_data') <> 'object' "
    "     OR dn.table_data->'sub_table_data' = '{}'::jsonb) "
    "AND (dn.table_data ? 'rows' OR dn.table_data ? '_tables')"
)


async def _scan(db: Any, args: argparse.Namespace) -> list[NotePlan]:
    import sqlalchemy as sa

    from app.services.note_template_reflow_service import (
        _load_template_sections,
        _pick_template_section,
    )

    where = [_LEGACY_WHERE]
    params: dict[str, Any] = {}
    if args.project:
        where.append("dn.project_id = :pid")
        params["pid"] = args.project
    if args.year:
        where.append("dn.year = :year")
        params["year"] = args.year
    if args.section:
        where.append("dn.note_section = :sec")
        params["sec"] = args.section

    rows = (
        await db.execute(
            sa.text(
                "SELECT dn.id, dn.project_id, dn.note_section, dn.section_title, "
                "       dn.table_data, p.name AS project "
                "FROM disclosure_notes dn JOIN projects p ON p.id = dn.project_id "
                f"WHERE {' AND '.join(where)} "
                "ORDER BY p.name, dn.sort_index, dn.note_section "
                f"LIMIT {int(args.limit)}"
            ),
            params,
        )
    ).mappings().all()

    # 模板按项目缓存（同项目多章节复用，避免重复读文件与 DB）
    tpl_cache: dict[str, list[dict[str, Any]]] = {}
    plans: list[NotePlan] = []

    for r in rows:
        pid = str(r["project_id"])
        if pid not in tpl_cache:
            try:
                sections, _tt = await _load_template_sections(db, r["project_id"])
            except Exception:  # noqa: BLE001 — 模板不可用则该项目全部转 manual
                sections = []
            tpl_cache[pid] = sections
        sec = _pick_template_section(
            tpl_cache[pid], str(r["note_section"] or ""), str(r["section_title"] or ""),
        )
        td = r["table_data"] if isinstance(r["table_data"], dict) else {}
        plans.append(
            build_note_plan(
                note_id=str(r["id"]),
                project=str(r["project"]),
                note_section=str(r["note_section"] or ""),
                section_title=str(r["section_title"] or ""),
                table_data=td,
                template_tables=(sec or {}).get("tables") if sec else None,
            )
        )
    return plans


def _render_report(plans: list[NotePlan], *, verbose: bool) -> tuple[str, Counter[str]]:
    c: Counter[str] = Counter()
    lines: list[str] = [f"legacy 章节 {len(plans)} 个\n"]

    for p in plans:
        c[p.kind] += 1
        c["tables_planned"] += len(p.tables)
        c["rows_planned"] += p.planned_row_total
        c["header_label_dropped"] += sum(t.dropped_header_label_rows for t in p.tables)
        c["tables_without_template_columns"] += sum(
            1 for t in p.tables if not t.columns_from_template
        )
        if p.legacy_row_total != p.planned_row_total and p.is_actionable:
            c["row_count_changed"] += 1

    if verbose:
        for kind in ("manual", "positional", "by_name", "single_row"):
            group = [p for p in plans if p.kind == kind]
            if not group:
                continue
            lines.append(f"\n{'=' * 60}\n[{kind}] {len(group)} 个")
            for p in group:
                lines.append(f"\n  {p.project} / {p.note_section} {p.section_title}")
                if p.reason:
                    lines.append(f"    原因: {p.reason}")
                lines.append(
                    f"    legacy: {p.legacy_table_count} 表 / {p.legacy_row_total} 行"
                    f"  →  计划: {len(p.tables)} 表 / {p.planned_row_total} 行"
                )
                for t in p.tables:
                    src = "rows" if t.source_index is None else f"_tables[{t.source_index}]"
                    flags = []
                    if t.dropped_header_label_rows:
                        flags.append(f"删 header_label {t.dropped_header_label_rows} 行")
                    if not t.columns_from_template:
                        flags.append("⚠️ 模板无 columns")
                    tail = f"  ({', '.join(flags)})" if flags else ""
                    lines.append(f"      {src} → 「{t.target_name}」 {t.row_count} 行{tail}")

    lines.append(f"\n{'=' * 60}\n汇总：")
    for k in (
        "by_name", "positional", "single_row", "manual",
        "tables_planned", "rows_planned", "header_label_dropped",
        "tables_without_template_columns", "row_count_changed",
    ):
        lines.append(f"  {k:<32}{c[k]}")
    actionable = c["by_name"] + c["positional"] + c["single_row"]
    lines.append(f"  {'可迁移合计':<32}{actionable}")
    lines.append(f"  {'须人工合计':<32}{c['manual']}")
    if c["positional"]:
        lines.append(
            f"\n⚠️ {c['positional']} 个章节只能按序对齐（表名重名/非业务名），"
            "迁移前必须人工抽样核对，否则会把行数据搬到错误的表下。"
        )
    if c["tables_without_template_columns"]:
        lines.append(
            f"⚠️ {c['tables_without_template_columns']} 张表在模板里也没有 columns，"
            "迁移后投影会降级为「只显示行名」，需先补模板列头。"
        )
    return "\n".join(lines), c


async def _run(args: argparse.Namespace) -> int:
    from app.core.database import async_session

    async with async_session() as db:
        plans = await _scan(db, args)

    text, c = _render_report(plans, verbose=not args.quiet)

    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"written -> {args.out}")
        print(text.rsplit("=" * 60, 1)[-1])
    else:
        print(text)

    if args.check:
        if plans:
            print(f"\n[FAIL] 仍有 {len(plans)} 个 legacy 快照章节未迁移")
            return 1
        print("\n[OK] 无 legacy 残留")
        return 0

    if args.apply:
        # Task 8 才实现写入；此处显式拒绝，避免误以为已迁移
        print(
            "\n[BLOCKED] --apply 尚未实现（属 Task 8，破坏性操作）。\n"
            "  前置条件：① 本报告经人工核对；② positional 类抽样确认；\n"
            "  ③ 模板缺 columns 的表先补齐；④ 用户显式确认。"
        )
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="附注 legacy 快照迁移（默认 dry-run 只读）")
    ap.add_argument("--project", help="项目 UUID")
    ap.add_argument("--year", type=int)
    ap.add_argument("--section", help="章节号，如 五、9")
    ap.add_argument("--limit", type=int, default=4000)
    ap.add_argument("--out", help="报告输出文件（UTF-8）")
    ap.add_argument("--quiet", action="store_true", help="只输出汇总，不列明细")
    ap.add_argument("--check", action="store_true", help="CI 模式：有 legacy 残留则 exit 1")
    ap.add_argument("--apply", action="store_true", help="🔴 写库（Task 8 才实现）")
    ap.add_argument("--confirm", action="store_true", help="配合 --apply 的二次确认")
    args = ap.parse_args()
    os.environ.setdefault("DB_DISABLE_SSL", "True")
    # Windows 控制台默认 GBK，报告里的 ⚠️ 等字符会 UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — 不支持 reconfigure 时忽略
        pass
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
