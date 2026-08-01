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
    python ... --apply --confirm                                                # 🔴 破坏性写库
    python ... --apply --confirm --include-positional                           # 🔴 连 positional 一起迁
    python ... --apply --confirm --no-require-columns                           # 🔴 关掉列头安全闸
    python ... --rollback --confirm                                             # 🔴 从备份回滚

## 写入路径的三道安全闸（Task 8）

1. **`--confirm` 二次确认**：只给 `--apply` / `--rollback` 不给 `--confirm` → 拒绝执行并 exit 2。
2. **`--require-columns`（默认开）**：只迁「每张计划表在模板里都有 `columns`」的章节。
   实测 847 张计划表里 382 张模板也没有 `columns`，迁过去投影会降级成
   `_needs_columns`（只有行名、数据值恒空）→ **比 legacy 快照更糟**（legacy 至少有
   `headers`）。开着这道闸，每条被迁的记录都是严格改善。`--no-require-columns` 可关。
3. **`positional` 需显式 opt-in**：默认只迁 `by_name` + `single_row`；`positional`
   靠按序对齐，表名重名/非业务名时可能把行数据搬到错误的表下 → 须 `--include-positional`。

## 写入内容

- `sub_table_data = {模板表名: [行]}`（`header_label` 假数据行已删）
- `_sub_table_columns = {模板表名: 模板 columns}`
- `_source = "workpaper"` —— **必须**，`project_sub_tables()` 只对 workpaper 来源投影，
  漏了这行会让整章渲染为空（比迁移前更糟）
- `_template_lineage._legacy_backup`：原 `rows` / `_tables` 全量备份（回滚依据 + 幂等探针）
- 删除顶层 `rows` / `_tables`；**其余顶层键（`_note_texts` / `_last_sync_*` …）原样保留**

备份放 `table_data._template_lineage` 而非 `template_lineage` DB 列：后者存在类型冲突
（`group_note_baseline_service` 写 list、`note_auto_trim` 写 dict）。Task 6 的
`apply_reflow_section` 也用 `table_data._template_lineage._reflow_history`，此处一致。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 正常（dry-run / `--check` 无残留 / apply·rollback 全部成功） |
| 1 | `--check` 模式下仍有 legacy 残留 |
| 2 | 拒绝执行（`--apply` / `--rollback` 缺 `--confirm`） |
| 3 | apply / rollback 过程中有章节失败（其余章节已提交） |

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R3 / Task 3（dry-run）、Task 8（apply）
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import io
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
# 纯函数：迁移 / 回滚的 table_data 变换（Task 8.1 / 8.3 / rollback）
# ════════════════════════════════════════════════════════════════════

LINEAGE_KEY = "_template_lineage"
BACKUP_KEY = "_legacy_backup"
MIGRATED_SOURCE = "workpaper"
"""`project_sub_tables()` 只对 `_source in ("workpaper","workpaper_html")` 投影。"""


def _already_migrated(table_data: Any) -> bool:
    """幂等探针：`table_data._template_lineage._legacy_backup` 是否已存在。"""
    if not isinstance(table_data, dict):
        return False
    lineage = table_data.get(LINEAGE_KEY)
    return isinstance(lineage, dict) and BACKUP_KEY in lineage


def build_migrated_table_data(
    table_data: dict[str, Any],
    plan: NotePlan,
    template_tables: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """纯函数：由 legacy `table_data` + 迁移计划产出**新的** `table_data`。

    - `sub_table_data`：`{目标表名: 保留行}`（`header_label` 假数据行已剔除）
    - `_sub_table_columns`：从同名模板表的 `columns` 补齐（模板无 columns 则不写该键）
    - `_source`：置 `workpaper`，否则投影器返回 `None`、整章渲染为空
    - `_template_lineage._legacy_backup`：原 `rows` / `_tables` 备份，**已存在则不覆盖**
    - 顶层 `rows` / `_tables` 删除；**其余顶层键原样保留**

    不修改入参（内部 deepcopy）、无 IO。
    """
    td: dict[str, Any] = copy.deepcopy(table_data) if isinstance(table_data, dict) else {}

    tpl_by_name = {
        str(t["name"]): t
        for t in (template_tables or [])
        if isinstance(t, dict) and t.get("name")
    }

    legacy_tables = td.get("_tables")
    legacy_tables = (
        [t for t in legacy_tables if isinstance(t, dict)]
        if isinstance(legacy_tables, list)
        else []
    )
    top_rows = _rows_of(td)

    sub: dict[str, Any] = {}
    cols: dict[str, Any] = {}
    for tp in plan.tables:
        if tp.source_index is None:
            src_rows = top_rows
        elif 0 <= tp.source_index < len(legacy_tables):
            src_rows = _rows_of(legacy_tables[tp.source_index])
        else:  # 计划与快照不一致（并发改动）→ 空表，宁缺勿造
            src_rows = []
        kept, _dropped = _strip_header_labels(src_rows)
        sub[tp.target_name] = kept

        tpl_cols = (tpl_by_name.get(tp.target_name) or {}).get("columns")
        if isinstance(tpl_cols, list) and tpl_cols:
            cols[tp.target_name] = copy.deepcopy(tpl_cols)

    # ── 备份（幂等：已有 _legacy_backup 时保留最早那份原始数据）────────
    lineage = dict(td.get(LINEAGE_KEY)) if isinstance(td.get(LINEAGE_KEY), dict) else {}
    if BACKUP_KEY not in lineage:
        lineage[BACKUP_KEY] = {
            "at": datetime.now(timezone.utc).isoformat(),
            "kind": plan.kind,
            "rows": td.get("rows"),
            "_tables": td.get("_tables"),
        }
    td[LINEAGE_KEY] = lineage

    td["sub_table_data"] = sub
    existing_cols = td.get("_sub_table_columns")
    if cols or isinstance(existing_cols, dict):
        merged = dict(existing_cols) if isinstance(existing_cols, dict) else {}
        merged.update(cols)
        td["_sub_table_columns"] = merged
    td["_source"] = MIGRATED_SOURCE

    # Task 8.3：只删这两个顶层键，其余（_note_texts / _last_sync_* …）保留
    td.pop("rows", None)
    td.pop("_tables", None)
    return td


def build_rollback_table_data(table_data: Any) -> dict[str, Any] | None:
    """纯函数：从 `_legacy_backup` 还原迁移前的 `table_data`。

    Returns:
        `None` —— 无备份（未迁移 / 备份形态损坏），调用方 SHALL 跳过该章节。
        否则为还原后的新 dict（不修改入参）。

    还原动作与 `build_migrated_table_data` 严格互逆：放回 `rows` / `_tables`（备份里为
    `None` 的键表示迁移前本就不存在 → 删掉而非写 null），移除
    `sub_table_data` / `_sub_table_columns` / `_source`，弹出 `_legacy_backup`
    （`_template_lineage` 变空则整键删除）。
    """
    if not isinstance(table_data, dict):
        return None
    lineage_raw = table_data.get(LINEAGE_KEY)
    if not isinstance(lineage_raw, dict) or not isinstance(lineage_raw.get(BACKUP_KEY), dict):
        return None

    td = copy.deepcopy(table_data)
    lineage = dict(td.get(LINEAGE_KEY) or {})
    backup = lineage.pop(BACKUP_KEY, None) or {}
    if lineage:
        td[LINEAGE_KEY] = lineage
    else:
        td.pop(LINEAGE_KEY, None)

    for key in ("rows", "_tables"):
        val = backup.get(key)
        if val is None:
            td.pop(key, None)
        else:
            td[key] = val

    td.pop("sub_table_data", None)
    td.pop("_sub_table_columns", None)
    td.pop("_source", None)
    return td


# ════════════════════════════════════════════════════════════════════
# 纯函数：可迁移集合筛选（三道安全闸中的第 2、3 道）
# ════════════════════════════════════════════════════════════════════

ALWAYS_MIGRATABLE_KINDS = ("by_name", "single_row")
"""默认放行的类别。`positional` 须 `--include-positional` 显式 opt-in。"""


def allowed_kinds(*, include_positional: bool) -> tuple[str, ...]:
    return (*ALWAYS_MIGRATABLE_KINDS, "positional") if include_positional else ALWAYS_MIGRATABLE_KINDS


def select_migratable(
    plans: list[NotePlan],
    *,
    kinds: tuple[str, ...],
    require_columns: bool,
) -> tuple[list[NotePlan], Counter[str]]:
    """纯函数：按 `is_actionable` + 类别白名单 + 列头闸筛出可迁移章节。"""
    picked: list[NotePlan] = []
    c: Counter[str] = Counter()
    for p in plans:
        if not p.is_actionable:
            c["skipped_manual"] += 1
            continue
        if p.kind not in kinds:
            c["skipped_kind"] += 1
            continue
        if require_columns and not all(t.columns_from_template for t in p.tables):
            c["skipped_no_columns"] += 1
            continue
        picked.append(p)
    c["selected"] = len(picked)
    return picked, c


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


# ════════════════════════════════════════════════════════════════════
# 🔴 写库：迁移（Task 8.2）与回滚
# ════════════════════════════════════════════════════════════════════

_UPDATE_SQL = (
    "UPDATE disclosure_notes SET table_data = CAST(:td AS jsonb), updated_at = :now "
    "WHERE id = :id"
)
"""🔴 JSONB 绑定必须走 `CAST(:td AS jsonb)` + `json.dumps` 字符串。

`sa.type_coerce(td, sa.JSON)` 配 `sa.text()` 在 **asyncpg** 下会抛
`Neither 'TypeCoerce' object nor 'Comparator' object has an attribute 'encode'`
（type_coerce 是 SQL 表达式构造器，不是可绑定的值；asyncpg 直接拿它当参数去 encode）。
实测 38/38 章节全失败、0 行写入。`note_template_reflow_service.apply_reflow_section`
曾有同款缺陷（同批修复）。
"""


def _json_param(td: dict[str, Any]) -> str:
    """JSONB 绑定值：`ensure_ascii=False` 保中文原样（库里是 jsonb，不影响存储）。"""
    import json

    return json.dumps(td, ensure_ascii=False, default=str)

_REFUSE_MSG = (
    "\n[REFUSED] 破坏性写库必须同时给 --confirm。\n"
    "  前置条件：① dry-run 报告经人工核对；② positional 类抽样确认（并加 --include-positional）；\n"
    "  ③ 模板缺 columns 的表先补齐（否则被 --require-columns 拦下）；④ 用户显式确认。\n"
    "  确认后重跑：... --apply --confirm"
)


def _fmt_failures(failures: list[tuple[str, str, str]]) -> list[str]:
    if not failures:
        return []
    lines = [f"\n失败明细（{len(failures)} 个，已跳过、其余章节照常提交）："]
    lines += [f"  {note_id}  {label}\n    {err}" for note_id, label, err in failures]
    return lines


async def _apply(db: Any, plans: list[NotePlan], args: argparse.Namespace) -> dict[str, Any]:
    """🔴 写库：把筛选后的 legacy 章节迁移为 `sub_table_data` 形态。

    - **每个章节一个 savepoint**（`begin_nested`）：单章节失败只回滚该章节，不牵连其余
    - 全部处理完在最外层 `commit()` 一次
    - `_already_migrated()` 为真则跳过（幂等重跑安全）
    """
    import sqlalchemy as sa

    from app.services.note_template_reflow_service import (
        _load_template_sections,
        _pick_template_section,
    )

    picked, counters = select_migratable(
        plans,
        kinds=allowed_kinds(include_positional=bool(args.include_positional)),
        require_columns=bool(args.require_columns),
    )

    tpl_cache: dict[str, list[dict[str, Any]]] = {}
    failures: list[tuple[str, str, str]] = []
    migrated = 0
    skipped_already = 0
    skipped_missing = 0

    for p in picked:
        label = f"{p.project} / {p.note_section} {p.section_title} [{p.kind}]"
        try:
            row = (
                await db.execute(
                    sa.text(
                        "SELECT id, project_id, table_data FROM disclosure_notes "
                        "WHERE id = :id AND is_deleted = false"
                    ),
                    {"id": p.note_id},
                )
            ).mappings().first()
            if not row:
                skipped_missing += 1
                continue

            td = dict(row["table_data"]) if isinstance(row["table_data"], dict) else {}
            if _already_migrated(td):
                skipped_already += 1
                continue

            pid = str(row["project_id"])
            if pid not in tpl_cache:
                sections, _tt = await _load_template_sections(db, row["project_id"])
                tpl_cache[pid] = sections
            sec = _pick_template_section(tpl_cache[pid], p.note_section, p.section_title)
            tpl_tables = (sec or {}).get("tables") if sec else None

            new_td = build_migrated_table_data(td, p, tpl_tables)

            async with db.begin_nested():  # savepoint：失败只回滚本章节
                await db.execute(
                    sa.text(_UPDATE_SQL),
                    {
                        "id": p.note_id,
                        "td": _json_param(new_td),
                        "now": datetime.now(timezone.utc),
                    },
                )
            migrated += 1
        except Exception as exc:  # noqa: BLE001 — 单章节失败不终止整批
            failures.append((p.note_id, label, f"{type(exc).__name__}: {exc}"))

    await db.commit()

    return {
        "mode": "迁移",
        "scanned": len(plans),
        "selected": counters["selected"],
        "migrated": migrated,
        "skipped_already": skipped_already,
        "skipped_no_columns": counters["skipped_no_columns"],
        "skipped_kind": counters["skipped_kind"],
        "skipped_manual": counters["skipped_manual"],
        "skipped_missing": skipped_missing,
        "failed": len(failures),
        "failures": failures,
    }


_BACKUP_WHERE = (
    "dn.is_deleted = false "
    "AND jsonb_typeof(dn.table_data->'_template_lineage') = 'object' "
    "AND dn.table_data->'_template_lineage' ? '_legacy_backup'"
)


async def _rollback(db: Any, args: argparse.Namespace) -> dict[str, Any]:
    """🔴 写库：从 `_template_lineage._legacy_backup` 还原迁移前形态。

    同样是**每章节一个 savepoint**，最外层一次 commit。
    """
    import sqlalchemy as sa

    where = [_BACKUP_WHERE]
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
                "SELECT dn.id, dn.note_section, dn.section_title, dn.table_data, "
                "       p.name AS project "
                "FROM disclosure_notes dn JOIN projects p ON p.id = dn.project_id "
                f"WHERE {' AND '.join(where)} "
                "ORDER BY p.name, dn.sort_index, dn.note_section "
                f"LIMIT {int(args.limit)}"
            ),
            params,
        )
    ).mappings().all()

    failures: list[tuple[str, str, str]] = []
    restored = 0
    skipped_no_backup = 0

    for r in rows:
        note_id = str(r["id"])
        label = f"{r['project']} / {r['note_section']} {r['section_title']}"
        try:
            td = r["table_data"] if isinstance(r["table_data"], dict) else {}
            new_td = build_rollback_table_data(td)
            if new_td is None:
                skipped_no_backup += 1
                continue
            async with db.begin_nested():
                await db.execute(
                    sa.text(_UPDATE_SQL),
                    {
                        "id": note_id,
                        "td": _json_param(new_td),
                        "now": datetime.now(timezone.utc),
                    },
                )
            restored += 1
        except Exception as exc:  # noqa: BLE001
            failures.append((note_id, label, f"{type(exc).__name__}: {exc}"))

    await db.commit()

    return {
        "mode": "回滚",
        "scanned": len(rows),
        "restored": restored,
        "skipped_no_backup": skipped_no_backup,
        "failed": len(failures),
        "failures": failures,
    }


def _render_write_summary(stats: dict[str, Any]) -> str:
    lines = [f"\n{'=' * 60}\n{stats['mode']}结果："]
    for k, v in stats.items():
        if k in ("mode", "failures"):
            continue
        lines.append(f"  {k:<24}{v}")
    lines += _fmt_failures(stats.get("failures") or [])
    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> int:
    from app.core.database import async_session

    # ── 回滚：不走 legacy 扫描（已迁移记录不再匹配 _LEGACY_WHERE）─────
    if args.rollback:
        if not args.confirm:
            print(_REFUSE_MSG.replace("--apply --confirm", "--rollback --confirm"))
            return 2
        async with async_session() as db:
            stats = await _rollback(db, args)
        print(_render_write_summary(stats))
        return 3 if stats["failed"] else 0

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
            if not args.confirm:
                print(_REFUSE_MSG)
                return 2
            print(
                f"\n[APPLY] 安全闸：require_columns={bool(args.require_columns)} "
                f"include_positional={bool(args.include_positional)}"
            )
            stats = await _apply(db, plans, args)
            print(_render_write_summary(stats))
            return 3 if stats["failed"] else 0
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
    ap.add_argument("--apply", action="store_true", help="🔴 写库：迁移为 sub_table_data 形态")
    ap.add_argument(
        "--rollback",
        action="store_true",
        help="🔴 写库：从 _template_lineage._legacy_backup 回滚到迁移前形态",
    )
    ap.add_argument(
        "--confirm", action="store_true", help="配合 --apply / --rollback 的二次确认（缺则拒绝执行）"
    )
    ap.add_argument(
        "--no-require-columns",
        dest="require_columns",
        action="store_false",
        help="关闭列头安全闸：允许迁移「模板也没有 columns」的表（投影会降级为只显示行名，"
             "比 legacy 快照更糟，仅在明知后果时使用）",
    )
    ap.set_defaults(require_columns=True)
    ap.add_argument(
        "--include-positional",
        action="store_true",
        help="把 positional（按序对齐）类也纳入迁移；未加则只迁 by_name + single_row。"
             "按序对齐可能把行数据搬到错误的表下，务必先人工抽样确认",
    )
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
