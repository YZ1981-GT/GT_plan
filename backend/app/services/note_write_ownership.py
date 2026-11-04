"""附注「章节 × 字段」唯一自动写方判定（spec formula-writer-ownership-and-stale R1b / ADR-WOS-04，design §13）。

D1（2026-11-04 用户拍板）：已接「从底稿拉取 / 离屏同步」的章节由后端取数链路唯一写入，其余章节暂留前端同步。
治理域 = ``note_workpaper_sync_registry.json`` 按准则登记的章节（运行时取自登记表，不取自矩阵文件）；矩阵
``backend/data/note_write_ownership_matrix.json`` 由 ``backend/scripts/gen/gen_note_write_ownership_matrix.py`` 生成。

判定顺序见 ``WriteGate.check``。被拒的字段不写、其他字段照写；所有权类拒绝记结构化日志 ``note_write_blocked`` 并回报
``blocked_writes``；locked / manual 的保留沿用现有口径，不进回报。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

MATRIX_PATH = Path(__file__).resolve().parents[2] / "data" / "note_write_ownership_matrix.json"

TEMPLATE_TYPES: tuple[str, ...] = ("listed", "soe")
FIELD_SUB_TABLE = "table.sub_table_data"
FIELD_ROWS = "table.rows.values"
CELL_PREFIX = "table.cell:"
ANY_TABLE = "*"

PUSH_WRITER = "formula_push"
SYNC_WRITER = "workpaper_sync"
BINDING_WRITER = "binding_refill"
MANUAL_OWNER = "manual_editor"

SCOPE_CELLS = "cells"
SCOPE_PUSHED = "pushed_cells"
#: manual 策略拒绝接管时给用户的处理建议（前端 ``utils/noteWriteOwnership.ts`` 的 ``MANUAL_TAKEOVER_ADVICE`` 同一句）
MANUAL_TAKEOVER_ADVICE = "如需改用底稿数据，先在附注编辑器里把人工填写的格恢复为自动"

#: 同一来源的不同入口（design §13.2）；矩阵文件里同样登记，守卫要求两处一致
IDENTITY: dict[str, str] = {
    "workpaper_html_sync": SYNC_WRITER,
    "update_note_values": BINDING_WRITER,
    "generate_notes": BINDING_WRITER,
}

_WORKPAPER_SOURCES = ("workpaper", "workpaper_html")
#: 不进 ``blocked_writes`` 的拒绝（现有「保留人工 / 锁定」口径）
_SILENT_CODES = frozenset({"locked", "manual"})


def normalize_template_type(value: Any) -> str | None:
    """``listed`` / ``soe`` / 枚举 / ``listed_standalone`` 一类准则串 → ``listed`` / ``soe``；其余 None。"""
    text = str(getattr(value, "value", value) or "").strip().lower()
    for tt in TEMPLATE_TYPES:
        if text == tt or text.startswith(f"{tt}_"):
            return tt
    return None


def never_synced_manual_block(synced_before: bool, manual_values: int) -> bool:
    """底稿披露容器接管的 manual 策略：从未由底稿同步、模板表格已有人工 / 锁定且有值的格 ⇒ 不覆盖。

    与前端离屏同步 ``manualSkipMessage`` 同一判据、同一组输入（``_mark_synced_sections`` 算出的
    ``synced_before`` / ``manual_values``）；前后端对拍用例由生成器按本函数算出。
    """
    return not synced_before and int(manual_values or 0) > 0


@dataclass(frozen=True)
class MatrixEntry:
    owner: str
    scope: str = SCOPE_CELLS
    provisional: str | None = None
    rules: tuple[str, ...] = ()


@dataclass(frozen=True)
class OwnershipMatrix:
    chapters: Mapping[tuple[str, str], Mapping[tuple[str, str], MatrixEntry]]
    identity: Mapping[str, str]


def parse_matrix(raw: Mapping[str, Any]) -> OwnershipMatrix:
    chapters: dict[tuple[str, str], dict[tuple[str, str], MatrixEntry]] = {}
    for chapter in raw.get("chapters") or []:
        key = (str(chapter["template_type"]), str(chapter["note_section"]))
        entries = chapters.setdefault(key, {})
        for e in chapter.get("entries") or []:
            entries[(str(e["table_key"]), str(e["field_key"]))] = MatrixEntry(
                owner=str(e["owner"]), scope=str(e.get("scope") or SCOPE_CELLS),
                provisional=e.get("provisional"), rules=tuple(e.get("rules") or ()),
            )
    return OwnershipMatrix(chapters=chapters, identity=dict(raw.get("identity") or {}))


@lru_cache(maxsize=4)
def _load(path: str, mtime_ns: int) -> OwnershipMatrix:
    return parse_matrix(json.loads(Path(path).read_text(encoding="utf-8")))


def load_matrix(path: Path | None = None) -> OwnershipMatrix:
    """读矩阵（按文件修改时间缓存）。读不到 ⇒ 空矩阵：治理域内的自动写入全部按未登记拒绝（fail-closed）。"""
    target = path or MATRIX_PATH
    try:
        return _load(str(target), target.stat().st_mtime_ns)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.error("附注写入归属矩阵读取失败（治理域内自动写入一律拒绝）：%s", exc)
        return OwnershipMatrix(chapters={}, identity=dict(IDENTITY))


@lru_cache(maxsize=1)
def governed_chapters() -> frozenset[tuple[str, str]]:
    """治理域 ``{(准则, 章节)}`` = 登记表按准则的章节（主章节 + ``{准则}_sections``）。"""
    from app.services.note_readiness_service import _load_registry_entries, registry_sections

    return frozenset(
        (tt, sec) for entry in _load_registry_entries() for tt in TEMPLATE_TYPES
        for sec in registry_sections(entry, tt)
    )


def active_container(table_data: Any) -> str:
    """章节当前生效的容器：底稿披露容器投影非空 ⇒ ``sub_table_data``，否则模板容器（与读时投影同判据）。"""
    if isinstance(table_data, dict) and table_data.get("_source") in _WORKPAPER_SOURCES:
        from app.services.note_sub_table_projector import project_sub_tables

        if project_sub_tables(table_data):
            return FIELD_SUB_TABLE
    return FIELD_ROWS


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    code: str = "allowed"
    owner_id: str | None = None

    @property
    def reportable(self) -> bool:
        return not self.allowed and self.code not in _SILENT_CODES


ALLOWED = Verdict(True)


def _writer_label(writer_id: str | None) -> str:
    from app.services.note_writers import writer_by_id

    spec = writer_by_id(writer_id or "")
    return spec.trigger if spec is not None else (writer_id or "人工填写")


def reason_text(verdict: Verdict, writer_id: str) -> str:
    code = verdict.code
    if code == "unknown_entry":
        return "写入归属矩阵没有这一格，按未登记拒写（公式推送只写矩阵声明的审定主表格）"
    if code == "inactive_container":
        return "本章节已由底稿披露表同步，模板表格被投影覆盖，不再写入"
    if code == "pushed_cell":
        return "这一格由公式推送按试算表审定数写定，其他自动写入不改"
    if code == "manual_values_never_synced":  # 处理建议与前端 utils/noteWriteOwnership.ts 同一句（对拍守卫）
        return f"章节从未由底稿同步、模板表格已有人工填写，底稿披露同步不覆盖（{MANUAL_TAKEOVER_ADVICE}）"
    return f"这一格归「{_writer_label(verdict.owner_id)}」写入，「{_writer_label(writer_id)}」不改写"


class WriteGate:
    """一次写入（一个写方、一个章节）的归属判定；``blocked_writes`` 收集本次被拒的格。"""

    def __init__(
        self, writer_id: str, template_type: Any, section: Any, table_data: Any = None, *,
        matrix: OwnershipMatrix | None = None, domain: Iterable[tuple[str, str]] | None = None,
    ) -> None:
        self.writer_id = writer_id
        self.template_type = normalize_template_type(template_type)
        self.section = str(section or "").strip()
        m = matrix if matrix is not None else load_matrix()
        self.identity = m.identity.get(writer_id) or IDENTITY.get(writer_id, writer_id)
        self._entries = m.chapters.get((self.template_type or "", self.section)) or {}
        chapters = governed_chapters() if domain is None else frozenset(domain)
        self.governed = (self.template_type, self.section) in chapters
        self.container = active_container(table_data)
        self.blocked_writes: list[dict[str, Any]] = []

    def entry(self, table: str, field: str) -> MatrixEntry | None:
        return self._entries.get((table, field))

    def check(
        self, *, table: str, field: str, column: str | None = None, pushed: bool = False,
        cell_mode: Any = None, section_locked: bool = False, legacy_manual: bool = False,
    ) -> Verdict:
        """判定顺序（design §13.3）：locked → manual → 推送只写声明格 → 域外放行 → 容器 → 推送写定格 → 基础条目。"""
        if section_locked or cell_mode == "locked":
            return Verdict(False, "locked")
        if cell_mode == "manual" and not legacy_manual:
            return Verdict(False, "manual")
        push_entry = self.entry(table, CELL_PREFIX + column) if column else None
        if push_entry is not None and push_entry.owner != PUSH_WRITER:
            push_entry = None
        if self.identity == PUSH_WRITER:
            return ALLOWED if push_entry is not None else Verdict(False, "unknown_entry")
        if not self.governed:
            return ALLOWED
        if field == FIELD_ROWS and self.container == FIELD_SUB_TABLE:
            return Verdict(False, "inactive_container", SYNC_WRITER)
        if pushed and push_entry is not None:
            return Verdict(False, "pushed_cell", PUSH_WRITER)
        base = self.entry(ANY_TABLE, field)
        if base is None:
            return Verdict(False, "unknown_entry")
        return ALLOWED if base.owner == self.identity else Verdict(False, "owner_mismatch", base.owner)

    def protects_pushed(self, table: str, column: str) -> bool:
        """推送写定的这一格是否归推送：域外沿用 ADR-3 交接（恒归推送）；域内要矩阵声明了推送条目。"""
        if not self.governed:
            return True
        entry = self.entry(table, CELL_PREFIX + column)
        return entry is not None and entry.owner == PUSH_WRITER

    def check_takeover(self, table_data: Any) -> Verdict:
        """底稿披露同步整节接管前的 manual 策略（design §13.3），只在治理域内、只对底稿披露同步。"""
        if not self.governed or self.identity != SYNC_WRITER or not isinstance(table_data, dict):
            return ALLOWED
        from app.services.note_workpaper_pull_service import manual_value_count

        if never_synced_manual_block(bool(table_data.get("_last_sync_wp_id")), manual_value_count(table_data)):
            return Verdict(False, "manual_values_never_synced", MANUAL_OWNER)
        return ALLOWED

    def record(
        self, verdict: Verdict, *, table: str, field: str, row: str | None = None, **extra: Any,
    ) -> dict[str, Any] | None:
        """被拒写入的结构化回报（并记日志）；locked / manual 不回报，返回 None。"""
        if not verdict.reportable:
            return None
        item: dict[str, Any] = {
            "section": self.section, "table": table, "field": field, "row": row,
            "writer_id": self.writer_id, "owner_id": verdict.owner_id,
            "reason_code": verdict.code, "reason": reason_text(verdict, self.writer_id),
            "template_type": self.template_type,
        }
        item.update({k: v for k, v in extra.items() if v is not None})
        self.blocked_writes.append(item)
        logger.info(
            "note_write_blocked %s", json.dumps(item, ensure_ascii=False, default=str),
            extra={"event": "note_write_blocked", "blocked_write": item},
        )
        return item


_HOLD_KEY = "_gt_push_hold"


def merge_holding_pushed_cells(old_td: Any, new_td: Any, owned: Mapping[tuple[int, int, int], Any],
                               gate: WriteGate) -> dict[str, Any]:
    """模板绑定的三态合并（生成 / 报表更新），推送写定格按 locked 语义保留旧值；被拒的格回报进 ``gate.blocked_writes``。

    ``owned`` = ``note_formula_push_guard.push_owned_cell_details(旧表)``。做法：旧表副本里把这些格临时标 locked 再合并
    （行列对齐完全复用合并本身），合并后还原原模式；另做一次不加标的合并，同位置比值，得出被拒的格。
    """
    from copy import deepcopy

    from app.services.formula_push.policy import values_equal
    from app.services.note_cell_merge import merge_table_data_preserving_cell_modes as merge
    from app.services.note_formula_tables import iter_note_tables

    holds = {key: cell for key, cell in owned.items()
             if not gate.check(table=cell.table, field=FIELD_ROWS, column=cell.field, pushed=True).allowed}
    if not holds or not isinstance(old_td, dict):
        return merge(old_td, new_td)
    marked = deepcopy(old_td)
    tables = dict(iter_note_tables(marked))
    for (t, r, c), cell in holds.items():
        rows = (tables.get(t) or {}).get("rows")
        targets = [rows[r]] if isinstance(rows, list) and r < len(rows) and isinstance(rows[r], dict) else []
        mirror = marked.get("rows") if t == 0 and marked.get("_tables") else None
        if targets and isinstance(mirror, list) and r < len(mirror) and isinstance(mirror[r], dict) \
                and mirror[r].get("label") == targets[0].get("label"):
            targets.append(mirror[r])  # 多表章节顶层 rows 是首表镜像：新模板只有单表时合并读的是它
        for row in targets:
            modes = row.get("_cell_modes") if isinstance(row.get("_cell_modes"), dict) else {}
            row.setdefault(_HOLD_KEY, {})[str(c)] = {"mode": modes.get(str(c)), "table": cell.table,
                                                     "field": cell.field, "label": cell.label}
            row["_cell_modes"] = {**modes, str(c): "locked"}
    plain, held = merge(old_td, new_td), merge(marked, new_td)
    plain_tables = dict(iter_note_tables(plain))
    for t, table in iter_note_tables(held):
        plain_rows = (plain_tables.get(t) or {}).get("rows") or []
        for i, row in enumerate(table.get("rows") or []):
            hold = row.pop(_HOLD_KEY, None) if isinstance(row, dict) else None
            if not hold:
                continue
            modes = dict(row.get("_cell_modes") or {})
            values = row.get("values") if isinstance(row.get("values"), list) else []
            plain_row = plain_rows[i] if i < len(plain_rows) and isinstance(plain_rows[i], dict) else {}
            plain_values = plain_row.get("values") if isinstance(plain_row.get("values"), list) else []
            for col, info in hold.items():
                if info["mode"] is None:
                    modes.pop(col, None)
                else:
                    modes[col] = info["mode"]
                c = int(col)
                kept = values[c] if c < len(values) else None
                incoming = plain_values[c] if c < len(plain_values) else None
                if not values_equal(incoming, kept):
                    gate.record(Verdict(False, "pushed_cell", PUSH_WRITER), table=info["table"],
                                field=f"{CELL_PREFIX}{info['field']}", row=info["label"], incoming=incoming, kept=kept)
            row["_cell_modes"] = modes
    first = held.get("_tables")[0] if isinstance(held.get("_tables"), list) and held["_tables"] else None
    if isinstance(first, dict) and isinstance(held.get("rows"), list):
        # 多表：合并把顶层 rows 重建为首表行的深拷贝（带着临时标记）⇒ 按清理后的首表重建一次，与合并本身同口径
        held["rows"] = deepcopy(first.get("rows") or [])
    return held


def takeover_skip_result(gate: WriteGate, verdict: Verdict, section_id: str, synced_at: str,
                         tables: Iterable[str]) -> dict[str, Any]:
    """底稿披露同步整节接管被 manual 策略拒绝时的返回：与口径跳过同形（``skipped`` + ``reason``），一行不写。

    前端离屏同步按 ``reason`` 显示中文，批量严格模式按 ``skipped`` 整批回滚，路由按 ``skipped`` 不发保存事件。
    """
    for table in sorted({str(t) for t in tables if not str(t).startswith("_")}) or [ANY_TABLE]:
        gate.record(verdict, table=table, field=FIELD_SUB_TABLE)
    return {
        "success": True, "section_id": section_id, "synced_at": synced_at, "rows_synced": 0, "created": False,
        "revived": False, "texts_synced": 0, "blocked_by_manual_override": False, "skipped": True,
        "reason": verdict.code, "blocked_writes": list(gate.blocked_writes),
    }


def note_template_type(note: Any) -> str | None:
    """单条附注记录下的准则（``_current_standard`` 前缀优先，``source_template`` 兜底；与行级合并同一口径，不查库）。"""
    from app.services.note_shared_table_segments import resolve_template_variant

    td = getattr(note, "table_data", None)
    standard = td.get("_current_standard") if isinstance(td, dict) else None
    return resolve_template_variant(standard, getattr(note, "source_template", None))


__all__ = [
    "ALLOWED", "ANY_TABLE", "BINDING_WRITER", "CELL_PREFIX", "FIELD_ROWS", "FIELD_SUB_TABLE", "IDENTITY",
    "MANUAL_TAKEOVER_ADVICE", "MATRIX_PATH", "MatrixEntry", "OwnershipMatrix", "PUSH_WRITER", "SCOPE_CELLS", "SCOPE_PUSHED",
    "SYNC_WRITER", "TEMPLATE_TYPES", "Verdict", "WriteGate", "active_container", "governed_chapters",
    "load_matrix", "merge_holding_pushed_cells", "never_synced_manual_block", "normalize_template_type",
    "note_template_type", "parse_matrix", "reason_text", "takeover_skip_result",
]
