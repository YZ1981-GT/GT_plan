"""C 类底稿 → disclosure_notes 模块单向同步服务

按 design §12.1 推荐选项 A：底稿是编辑入口，disclosure_notes 模块仅作展示+独立编辑（向后兼容）。
当用户在 C 类附注底稿 sheet 保存数据时，自动 push 到 disclosure_notes 表对应 section。

Validates: Requirements 3.11.5 §4.2（附注双源问题）+ design §12.1
Validates: Requirements US-3（C 类底稿 → 附注自动同步）
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Mapping
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, User
from app.models.report_models import (
    ContentType,
    DisclosureNote,
    NoteStatus,
    SourceTemplate,
)
from app.services.conflict_resolution_service import (
    _check_manual_override_before_propagate,
)
from app.services.note_shared_table_segments import (
    SEG_KEY,
    find_segment,
    find_stamped_window,
    has_discontiguous_stamp,
    resolve_template_variant,
    stamp_baseline_rows,
    template_rows,
)
from app.services.note_sub_table_projector import normalize_sub_table_data
from app.services.standard_unification_service import (
    StandardUnificationService,
    derive_applicable_standards,
    detect_standard_conflict,
)

logger = logging.getLogger(__name__)


# ─── Conflict Error ──────────────────────────────────────────────────────────


class StandardMismatchError(ValueError):
    """``current_standard`` 与项目 ``entity_type`` 冲突（跨主体类型同步）。

    继承 ``ValueError``：即便某个调用方未显式捕获本类型，既有的
    ``except ValueError -> 422`` 兜底仍会拦住写入，不会退化成 500 或静默写错章节。

    Spec: applicable-standards-runtime-and-sync-guard R4.1
    """

    code = "STANDARD_MISMATCH"

    def __init__(self, conflict: dict[str, Any]):
        self.conflict = conflict
        self.project_standard = str(conflict.get("project_standard") or "")
        self.requested_standard = str(conflict.get("requested_standard") or "")
        self.allowed = list(conflict.get("allowed") or [])
        super().__init__(
            f"项目适用准则为 {self.project_standard}，"
            f"不能以 {self.requested_standard} 同步披露数据"
        )


class ConflictError(Exception):
    """附注侧有更新的手动编辑，与底稿同步冲突。"""

    def __init__(self, note_id: UUID, note_updated: datetime, last_sync_at: datetime | None = None):
        self.note_id = note_id
        self.note_updated = note_updated
        self.last_sync_at = last_sync_at
        super().__init__(
            f"Conflict: note {note_id} updated at {note_updated}, "
            f"last sync at {last_sync_at}"
        )

def _detect_manual_override(table_data: dict[str, Any] | None) -> bool:
    """读取 disclosure_note.table_data 中的 ``_manual_override`` 标记。

    约定字段位置（任一为 True 即视为 manual_override）：
      1. ``table_data['_manual_override']``           顶层标记
      2. ``table_data['sub_table_data']['_manual_override']``  子表标记

    无字段或不为 True 时返回 False（默认 allow，不影响既有写入路径）。
    """
    if not isinstance(table_data, dict):
        return False
    if table_data.get("_manual_override") is True:
        return True
    sub = table_data.get("sub_table_data")
    if isinstance(sub, dict) and sub.get("_manual_override") is True:
        return True
    return False


def _count_rows_synced(sub_table_data: dict[str, list[dict]] | None) -> int:
    """统计 sub_table_data 中所有子表行数总和（跳过 _ 元数据键）。"""
    if not sub_table_data:
        return 0
    total = 0
    for key, rows in sub_table_data.items():
        if str(key).startswith("_"):
            continue
        if isinstance(rows, list):
            total += len(rows)
    return total


def _extract_note_texts(
    sub_table_data: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """分离表格数据与叙述正文 ``_note_texts``。"""
    data = dict(sub_table_data or {})
    raw = data.pop("_note_texts", None)
    texts: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                texts.append(item)
    return data, texts


def _extract_removed_table_keys(
    sub_table_data: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """分离表格数据与「待删除表名」元数据键 ``_removed_table_keys``。

    底稿改版重命名子表后，附注侧浅合并不会删除旧键 → 附注永久残留空表。
    底稿据此显式上报旧表名，由 ``sync_from_workpaper`` 删除（Requirement 8）。
    """
    data = dict(sub_table_data or {})
    raw = data.pop("_removed_table_keys", None)
    keys: list[str] = []
    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            name = str(item).strip()
            # 元数据键不可删除（`_note_texts` 等由各自路径管理）
            if name and not name.startswith("_") and name not in keys:
                keys.append(name)
    return data, keys


def _drop_removed_tables(
    merged_sub: dict[str, Any],
    merged_cols: dict[str, Any],
    removed_keys: list[str],
    pushed_keys: set[str],
) -> list[str]:
    """从合并结果中删除 ``removed_keys``，跳过本次推送的表名（Property 7）。

    返回实际删除的表名（供审计日志/返回值）。原地修改传入的 dict（均为调用方新建的副本）。
    """
    dropped: list[str] = []
    for key in removed_keys:
        if key in pushed_keys:
            continue  # 本次刚推送 → 推送优先，绝不删
        removed_any = merged_sub.pop(key, None) is not None
        merged_cols.pop(key, None)
        if removed_any:
            dropped.append(key)
    return dropped


#: 行级合并的元数据键（随 ``sub_table_data`` 走，不改 request schema）
ROW_SCOPE_KEY = "_row_scope"


@dataclass(frozen=True)
class RowScope:
    """载荷声明的「本次只负责这张表的这一段」。

    ``owner_row_code`` 是模板段首行的 ``report_row_code``（如货币资金段 = ``BS-002``）。
    """

    table_name: str
    owner_row_code: str


def _extract_row_scope(
    sub_table_data: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, RowScope]]:
    """分离表格数据与行级合并声明 ``_row_scope``（对称 :func:`_extract_removed_table_keys`）。

    形态::

        {"_row_scope": {"外币货币性项目": {"owner_row_code": "BS-002"}}}

    非法形态（整体非 dict / 单条非 dict / 缺 ``owner_row_code`` / 表名以 ``_`` 开头）
    一律**丢弃该条声明 + warning** → 该表退回既有的表级覆盖语义（声明无效 ≠ 共享表，
    退回原语义是既有行为，不引入新风险）。

    spec: disclosure-note-row-level-merge Requirements 1.1 / 1.4
    """
    data = dict(sub_table_data or {})
    raw = data.pop(ROW_SCOPE_KEY, None)
    scopes: dict[str, RowScope] = {}
    if raw is None:
        return data, scopes
    if not isinstance(raw, dict):
        logger.warning(
            "wp_disclosure_sync: %s 形态非法（期望对象，实为 %s）→ 忽略",
            ROW_SCOPE_KEY, type(raw).__name__,
        )
        return data, scopes
    for table_name, spec in raw.items():
        name = str(table_name or "").strip()
        if not name or name.startswith("_"):
            logger.warning("wp_disclosure_sync: %s 表名非法 %r → 忽略", ROW_SCOPE_KEY, table_name)
            continue
        owner = ""
        if isinstance(spec, Mapping):
            owner = str(spec.get("owner_row_code") or "").strip()
        if not owner:
            logger.warning(
                "wp_disclosure_sync: %s['%s'] 缺 owner_row_code → 忽略（退回表级覆盖）",
                ROW_SCOPE_KEY, name,
            )
            continue
        scopes[name] = RowScope(table_name=name, owner_row_code=owner)
    return data, scopes


def _merge_rows_by_scope(
    existing_rows: list[Any] | None,
    incoming_rows: list[Any],
    *,
    scope: RowScope,
    variant: str | None,
    section_number: str,
) -> tuple[list[Any], str | None]:
    """段内整段替换、**段外原样保留**。

    Returns:
        ``(merged_rows, error)``。``error`` 非空表示段边界解析失败 → 调用方
        **跳过该表写入**（fail closed，Requirement 2.2），绝不回退整表覆盖
        —— 回退会静默清掉他循环已录的段。

    基线选择（Requirement 4）：
      - ``existing_rows`` 非空 → 用它（不回退模板，否则抹掉他人已录数据）
      - 为空 → 用模板骨架（``stamp_baseline_rows``），使他段在附注里仍有标签可见

    段窗口定位：
      - 基线里有 ``_seg == owner_row_code`` 的连续段 → 用它（Requirement 3.4）
      - 否则（首次 / 历史数据无戳）→ 用模板下标并按基线长度裁剪（Requirement 4.3）

    ``incoming_rows`` 为空 → 段恢复模板骨架（Requirement 3.6），**不是删段**。
    """
    owner = scope.owner_row_code
    baseline: list[Any] = [
        dict(r) if isinstance(r, Mapping) else r for r in (existing_rows or [])
    ]

    if not variant:
        return baseline, "variant_unresolved"
    tpl = template_rows(variant, section_number, scope.table_name)
    if tpl is None:
        return baseline, "template_table_not_found"
    tpl_seg = find_segment(tpl, owner)
    if tpl_seg is None:
        return baseline, "owner_row_code_not_in_template"

    baseline_source = "existing"
    if not baseline:
        baseline = stamp_baseline_rows(tpl)
        baseline_source = "template"

    stamped = find_stamped_window(baseline, owner)
    if stamped is not None:
        start, end = stamped
        window_source = "stamp"
        if has_discontiguous_stamp(baseline, owner):
            logger.warning(
                "wp_disclosure_sync: 段 %s 在 section=%s table=%s 的落库行里不连续 → "
                "只替换首个连续区间 [%d,%d)（脏数据，另需 data-hygiene）",
                owner, section_number, scope.table_name, start, end,
            )
    else:
        # 🔴 用 `data_end` 而非 `end`：段尾的表级汇总行（合计/小计）**不属于本段**，
        # 否则 owner 一推数据就把合计行删掉（实测 13 个段的尾部挂着这类行）。
        start = min(tpl_seg.start, len(baseline))
        end = max(start, min(tpl_seg.data_end, len(baseline)))
        window_source = "template_index"

    if incoming_rows:
        seg_rows: list[Any] = [
            {**dict(r), SEG_KEY: owner} for r in incoming_rows if isinstance(r, Mapping)
        ]
    else:
        # 空推送 → 段恢复模板骨架（标签留、数值空），段不消失；同样只到 data_end
        seg_rows = stamp_baseline_rows(tpl)[tpl_seg.start:tpl_seg.data_end]

    merged = list(baseline[:start]) + seg_rows + list(baseline[end:])
    logger.info(
        "wp_disclosure_sync: row-level merge section=%s table=%s owner=%s "
        "window=[%d,%d) window_source=%s baseline=%s rows_in=%d rows_out=%d total=%d",
        section_number, scope.table_name, owner, start, end, window_source,
        baseline_source, len(incoming_rows or []), len(seg_rows), len(merged),
    )
    return merged, None


def _apply_row_scoped_merge(
    merged_sub: dict[str, Any],
    clean_sub_table_data: dict[str, Any],
    row_scopes: dict[str, RowScope],
    *,
    variant: str | None,
    section_number: str,
    baselines: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """把行级合并套进表级合并结果（原地修改 ``merged_sub``）。

    未声明 ``_row_scope`` 的表**一行都不改**（Property 1 零回归的支点）。

    Args:
        merged_sub: 表级合并结果（scoped 表的值会被本函数改写）。
        clean_sub_table_data: 本次推送（提供 incoming 行）。
        baselines: **落库既有**子表（提供 baseline 行）。🔴 不能用 ``merged_sub``
            当基线 —— 调用方已把 incoming 写进去了，那样基线就是 incoming 本身。

    Returns:
        ``(row_scoped_tables, row_scope_unresolved)``
    """
    scoped: list[str] = []
    unresolved: list[str] = []
    for key, scope in row_scopes.items():
        if key not in clean_sub_table_data:
            continue  # 孤立声明已在调用方剔除；双保险
        incoming = clean_sub_table_data.get(key)
        prev = baselines.get(key)
        merged_rows, err = _merge_rows_by_scope(
            prev if isinstance(prev, list) else None,
            incoming if isinstance(incoming, list) else [],
            scope=scope,
            variant=variant,
            section_number=section_number,
        )
        if err:
            unresolved.append(key)
            logger.warning(
                "wp_disclosure_sync: 行级合并失败 section=%s table=%s owner=%s reason=%s "
                "→ 跳过该表写入（fail closed）",
                section_number, key, scope.owner_row_code, err,
            )
            # fail closed：既有数据原样保留；本来没有该表就不要凭空创建
            if isinstance(prev, list):
                merged_sub[key] = prev
            else:
                merged_sub.pop(key, None)
            continue
        merged_sub[key] = merged_rows
        scoped.append(key)
    return scoped, unresolved


#: 显式删除叙述段的元数据键（对称 ``_removed_table_keys``）
REMOVED_TEXT_SECTIONS_KEY = "_removed_text_sections"


def _extract_removed_text_sections(
    sub_table_data: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """分离表格数据与「待删除叙述段」``_removed_text_sections``。

    `_note_texts` 改为按 ``section`` 浅合并后，底稿删掉某段说明不再自动消失
    → 需要与 ``_removed_table_keys`` 同款的显式删除语义。
    """
    data = dict(sub_table_data or {})
    raw = data.pop(REMOVED_TEXT_SECTIONS_KEY, None)
    keys: list[str] = []
    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            # 只认字符串：`str(None)` == "None" 会造出一个假 section 名
            if not isinstance(item, str):
                continue
            name = item.strip()
            if name and name not in keys:
                keys.append(name)
    return data, keys


def _note_text_key(item: Any) -> str:
    """叙述段的合并键：``section`` 优先，退 ``title``。两者皆空 → ``""``。"""
    if not isinstance(item, Mapping):
        return ""
    return str(item.get("section") or item.get("title") or "").strip()


#: 无 `section`/`title` 段的位置化占位键前缀（不可能与真实 section 名冲突）
_ANON_TEXT_KEY = "\x00anon"


def _note_text_merge_keys(items: list[Any]) -> list[str]:
    """逐条算合并键；无键段退化为「第 n 条无键段」的**位置化**占位键。

    位置化是必须的：存量有循环推 ``[{"text": "…"}]``（无 section 也无 title，F4 范式）。
    若把无键段一律「原样保留 + 追加」，每次同步都会多攒一条 → 附注正文无限膨胀。
    """
    out: list[str] = []
    anon = 0
    for item in items:
        key = _note_text_key(item)
        if not key:
            key = f"{_ANON_TEXT_KEY}{anon}"
            anon += 1
        out.append(key)
    return out


def _merge_note_texts(
    existing: list[Any] | None,
    incoming: list[Any] | None,
    removed_sections: Any = (),
) -> list[dict[str, Any]]:
    """按 ``section`` 键浅合并叙述段（Requirement 5.1 / 5.3 / 5.5）。

    - 同 ``section`` → incoming 覆盖
    - 未推送的 ``section`` → **保留**（多循环共章节时不再被他人整体覆盖）
    - ``removed_sections`` 里的 ``section`` → 删除；**推送优先**（本次推了就不删）
    - 段序稳定：既有顺序在前、新 section 追加在后（``text_content`` 重排不跳动）

    🔴 零回归论证：单 owner 场景下既有键集 ⊆ 推送键集 → 合并结果 ≡ 整替换。
    """
    inc = [i for i in (incoming or []) if isinstance(i, Mapping)]
    exist = [e for e in (existing or []) if isinstance(e, Mapping)]
    inc_keys = _note_text_merge_keys(inc)
    exist_keys = _note_text_merge_keys(exist)
    pushed_keys = set(inc_keys)
    removed = {
        str(s).strip()
        for s in (removed_sections or ())
        if str(s).strip() and str(s).strip() not in pushed_keys
    }
    inc_by_key: dict[str, Any] = {}
    for key, item in zip(inc_keys, inc):
        inc_by_key[key] = item  # 同键重复 → 取最后一条

    out: list[dict[str, Any]] = []
    used: set[str] = set()
    # ① 既有顺序在前（被推送的**原位**替换、被删的丢弃、其余原样保留）
    for key, item in zip(exist_keys, exist):
        if not key.startswith(_ANON_TEXT_KEY) and key in removed:
            continue
        if key in inc_by_key:
            if key in used:
                continue  # 既有重复键只保留首个位置
            out.append(dict(inc_by_key[key]))
            used.add(key)
            continue
        out.append(dict(item))
    # ② 新 section 追加在后（保持载荷内顺序）
    for key, item in zip(inc_keys, inc):
        if key not in used:
            out.append(dict(item))
            used.add(key)
    return out


def _format_note_texts(note_texts: list[dict[str, Any]]) -> str:
    """将 _note_texts 列表格式化为附注 text_content。"""
    parts: list[str] = []
    for item in note_texts:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        title = str(item.get("title") or item.get("section") or "").strip()
        parts.append(f"【{title}】\n{text}" if title else text)
    return "\n\n".join(parts)


def _derive_section_title(section_id: str) -> str:
    """从 section_id 派生默认标题（**纯字符串兜底**，模板查不到时才用）。

    Examples:
        "五-1-1 应收账款" → "应收账款"
        "五-1-1" → "五-1-1"
    """
    if not section_id:
        return ""
    parts = section_id.strip().split(maxsplit=1)
    if len(parts) == 2:
        return parts[1]
    return section_id


_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@lru_cache(maxsize=4)
def _template_section_meta(variant: str) -> dict[str, tuple[str, str]]:
    """``section_number`` → ``(section_title, account_name)``（附注模板权威源）。

    variant ∈ {"listed", "soe"}；文件缺失/损坏 → 返回空 dict（fail-open）。
    """
    path = _DATA_DIR / f"note_template_{variant}.json"
    out: dict[str, tuple[str, str]] = {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:  # pragma: no cover - 环境异常
        logger.warning("wp_disclosure_sync: load note_template_%s failed: %s", variant, err)
        return out
    for sec in doc.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        num = sec.get("section_number")
        if not isinstance(num, str) or not num.strip():
            continue
        title = str(sec.get("section_title") or "").strip()
        account = str(sec.get("account_name") or "").strip() or title
        if title:
            out[num.strip()] = (title, account)
    return out


def _resolve_section_meta(
    section_id: str, source_template: SourceTemplate | None
) -> tuple[str, str | None]:
    """新建附注时的标题/科目名：**优先查附注模板**（按变体），否则字符串兜底。

    旧实现直接用 ``section_id`` 当 ``section_title``（如 "五、36"），附注树/
    Word 导出显示的是章节号而非中文标题。这里按 ``source_template`` 先查对应
    变体模板，未命中再查另一变体（同一章节号两变体标题通常一致），最后兜底。
    """
    if not section_id:
        return "", None
    key = section_id.strip()
    order = ("listed", "soe")
    if source_template == SourceTemplate.soe:
        order = ("soe", "listed")
    for variant in order:
        hit = _template_section_meta(variant).get(key)
        if hit:
            return hit[0], (hit[1] or None)
    return _derive_section_title(section_id), None


def _derive_year(payload_year: int | None) -> int:
    """纯兜底：优先使用 payload 中的 year，否则取当前自然年。

    注意：**不要**在同步路径直接用它推导目标年度——服务器当前自然年
    与项目审计年度通常不同（如 2026 年做 2025 年报审计），会把底稿推送
    写到错误年度的附注记录上，审计师在附注模块（按审计年度渲染）永远看不到。
    同步路径统一走 :func:`_resolve_target_year`（以 ``projects.audit_year`` 为权威）。
    """
    if payload_year and isinstance(payload_year, int):
        return payload_year
    return datetime.now(timezone.utc).year


async def _resolve_project_audit_year(
    db: AsyncSession, project_id: UUID
) -> int | None:
    """读项目审计年度（权威源 ``projects.audit_year``）；取不到返回 None（fail-open）。"""
    try:
        result = await db.execute(
            sa.select(Project.audit_year).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        year = result.scalar_one_or_none()
        if isinstance(year, int) and year > 0:
            return year
    except Exception as err:  # pragma: no cover - 查询异常时安全降级
        logger.warning(
            "resolve audit_year failed for project %s: %s; falling back",
            project_id, err,
        )
    return None


async def _resolve_project_sync_context(
    db: AsyncSession, project_id: UUID
) -> tuple[int | None, dict | None]:
    """一次查询取回 ``(审计年度, 结构化准则)``；任何异常 → ``(None, None)`` fail-open。

    合并了原先只为 ``audit_year`` 而做的那次查询（R4.7：守卫不引入额外 DB 往返）。
    准则优先读 v2 权威源，缺失时用旧列 ``template_type`` / ``report_scope`` 兜底；
    两者皆空返回 ``None``（表示"不可判"，守卫据此放行，而不是被
    ``_normalize_standard`` 补成默认的 soe 从而误杀上市项目）。
    """
    try:
        row = (
            await db.execute(
                sa.select(
                    Project.audit_year,
                    Project.applicable_standard_v2,
                    Project.template_type,
                    Project.report_scope,
                ).where(
                    Project.id == project_id,
                    Project.is_deleted == sa.false(),
                )
            )
        ).first()
        if row is None:
            return None, None
        audit_year, v2, template_type, report_scope = row
        year = audit_year if isinstance(audit_year, int) and audit_year > 0 else None
        standard: dict | None = None
        if isinstance(v2, dict) and v2:
            standard = StandardUnificationService._normalize_standard(v2)
        elif template_type or report_scope:
            standard = StandardUnificationService._normalize_standard(
                {"entity_type": template_type, "scope": report_scope}
            )
        return year, standard
    except Exception as err:  # pragma: no cover - 查询异常时安全降级
        logger.warning(
            "resolve project sync context failed for project %s: %s; falling back",
            project_id, err,
        )
        return None, None


def _guard_standard_matches_project(
    project_id: UUID,
    project_standard: dict | None,
    requested_standard: str,
    section_id: str,
) -> None:
    """跨主体类型（listed vs soe）的披露同步守卫。冲突则抛 :class:`StandardMismatchError`。

    必须在**任何写入语句之前**调用（Property 6：拒绝时零写入）。
    """
    conflict = detect_standard_conflict(project_standard, requested_standard)
    if conflict is not None:
        logger.warning(
            "wp_disclosure_sync: REJECTED cross-entity sync project=%s section=%s "
            "project_standard=%s requested=%s",
            project_id, section_id,
            conflict.get("project_standard"), conflict.get("requested_standard"),
        )
        raise StandardMismatchError(conflict)
    requested = str(requested_standard or "").strip().lower()
    if requested and isinstance(project_standard, dict) and project_standard:
        allowed = derive_applicable_standards(project_standard)
        if requested not in allowed:
            # R4.3：entity 一致、仅 scope 维度不同（合并 vs 个别报表口径）→ 放行留痕
            logger.warning(
                "wp_disclosure_sync: scope mismatch (allowed) project=%s section=%s "
                "requested=%s allowed=%s",
                project_id, section_id, requested, allowed,
            )


async def _resolve_target_year(
    db: AsyncSession, project_id: UUID, payload_year: int | None
) -> int:
    """派生同步目标年度：payload 显式年度 > 项目审计年度 > 当前自然年（兜底）。

    前端各披露组件历史上普遍不传 ``year``，此前会 fallback 到服务器当前自然年，
    导致同步落到错误年度的附注（附注模块看不到）。此处以 ``projects.audit_year``
    为权威，一处修复覆盖全部披露组件；前端显式传 year 仍优先。
    """
    if payload_year and isinstance(payload_year, int):
        return payload_year
    audit_year = await _resolve_project_audit_year(db, project_id)
    if audit_year is not None:
        return audit_year
    return _derive_year(None)


async def sync_from_workpaper(
    db: AsyncSession,
    project_id: UUID,
    *,
    wp_id: UUID,
    sheet_name: str,
    section_id: str,
    sub_table_data: dict[str, list[dict]],
    current_standard: str,
    user: User,
    year: int | None = None,
    sub_table_columns: dict[str, list[dict]] | None = None,
    propagation_origin: Literal["user_edit", "system_recompute"] = "user_edit",
    commit: bool = True,
) -> dict[str, Any]:
    """C 类底稿 sheet 保存时，将 sub_table_data 同步到 disclosure_notes 模块对应 section。

    行为：
    - 查 disclosure_notes WHERE (project_id, year, note_section=section_id, is_deleted=false)
    - 已存在：更新 table_data（merge sub_table_data）+ 同步标记
    - 不存在：新建一条记录（status=draft，content_type=table|mixed）+ 同步标记
    - ``sub_table_data['_note_texts']`` 写入 ``text_content``，并从子表字典中剥离

    manual_override 守卫（Req 7 AC 1/2/6/7）：
    - 如果目标 disclosure_note 当前 table_data 带有 ``_manual_override=True`` 标记，
      调用 ``_check_manual_override_before_propagate`` hook：
        * propagation_origin='user_edit'   → 入队 cross_module_conflict 并跳过 table_data 更新
        * propagation_origin='system_recompute' → auto_resolve 留痕并继续写入
    - 如果目标无 manual_override，正常写入（保持既有行为，不影响兼容性）

    Args:
        commit: 是否立即 commit。批量同步时应传 False，由调用方统一提交。

    Returns:
        {
            "success": True,
            "section_id": str,
            "synced_at": ISO timestamp,
            "rows_synced": int,
            "created": bool,             # 本次是否新建（True=create，False=update）
            "blocked_by_manual_override": bool,  # 是否被 manual_override 拦截（True=table_data 未更新）
            "texts_synced": int,
        }
    """
    if not section_id or not section_id.strip():
        raise ValueError("section_id 不能为空")
    section_id = section_id.strip()

    # 一次查询同时拿到审计年度与项目准则（R4.7）
    audit_year, project_standard = await _resolve_project_sync_context(db, project_id)
    # 🔴 守卫必须在任何写入之前：定位键不含 current_standard，跨主体类型的推送
    # 会静默写进错误章节（国企项目的「五、xx」是另一套压缩编号）。
    _guard_standard_matches_project(
        project_id, project_standard, current_standard, section_id
    )

    if year and isinstance(year, int):
        target_year = year
    elif audit_year is not None:
        target_year = audit_year
    else:
        target_year = _derive_year(None)
    now = datetime.now(timezone.utc)
    clean_sub_table_data, note_texts = _extract_note_texts(sub_table_data)
    clean_sub_table_data, removed_table_keys = _extract_removed_table_keys(clean_sub_table_data)
    clean_sub_table_data, removed_text_sections = _extract_removed_text_sections(
        clean_sub_table_data
    )
    # 行级合并声明（多段共享表）：不声明就一行不改，走原表级覆盖路径
    clean_sub_table_data, row_scopes = _extract_row_scope(clean_sub_table_data)
    for _orphan in [k for k in row_scopes if k not in clean_sub_table_data]:
        logger.warning(
            "wp_disclosure_sync: %s['%s'] 声明的表不在本次推送里 → 忽略该条声明",
            ROW_SCOPE_KEY, _orphan,
        )
        row_scopes.pop(_orphan, None)
    # 入库前归一为 {key: list[dict]} 规范形态：拒绝表对象包装 / 位置化 values 行
    # 落库（否则投影器读时取不出业务键 → 附注整表丢失）。
    clean_sub_table_data = normalize_sub_table_data(clean_sub_table_data, sub_table_columns)
    rows_synced = _count_rows_synced(clean_sub_table_data)

    # ─── 查现有记录 ───────────────────────────────────────────────────
    stmt = sa.select(DisclosureNote).where(
        DisclosureNote.project_id == project_id,
        DisclosureNote.year == target_year,
        DisclosureNote.note_section == section_id,
        DisclosureNote.is_deleted == sa.false(),
    )
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()

    # 软删行复活：唯一索引 uq_disclosure_notes_project_year_section 建在
    # (project_id, year, note_section) 上且**不含 is_deleted** → 被软删的章节
    # 仍占用唯一键。若此处只查 active 行就走 INSERT，会撞唯一键 500
    # （实测：审计师删除某章节后底稿再同步 → 附注同步失败 UniqueViolationError）。
    # 故命中软删行时改为复活复用该行（视同"更新"，保留其 id 与既有 table_data）。
    revived = False
    if note is None:
        deleted_stmt = sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == target_year,
            DisclosureNote.note_section == section_id,
            DisclosureNote.is_deleted == sa.true(),
        )
        deleted_result = await db.execute(deleted_stmt)
        note = deleted_result.scalar_one_or_none()
        if note is not None:
            note.is_deleted = False
            revived = True
            logger.info(
                "wp_disclosure_sync: revived soft-deleted disclosure_note "
                "project=%s year=%s section=%s",
                project_id, target_year, section_id,
            )

    # 构建合并后的 table_data
    # 约定：按子表 key 浅合并 sub_table_data（同名 key 覆盖，未推送的 key 保留），
    #     便于 H4 仅推送「工程物资」子表而不清空 H2 已同步的在建工程明细。
    #     并保留 _source / _current_standard / _last_sync_wp / _last_sync_sheet 元数据
    new_table_data: dict[str, Any] = dict(note.table_data) if note and note.table_data else {}
    existing_sub = new_table_data.get("sub_table_data")
    existing_sub = existing_sub if isinstance(existing_sub, dict) else {}
    # 段边界必须按变体查模板：🔴 禁止按章节号推导（20 个章节号两份模板都有、13 个标题不同）
    row_scope_variant = (
        resolve_template_variant(
            current_standard, note.source_template if note is not None else None
        )
        if row_scopes
        else None
    )
    row_scoped_tables: list[str] = []
    row_scope_unresolved: list[str] = []
    if clean_sub_table_data:
        # 浅合并：保留未推送的既有子表，同名 key 覆盖。
        # 显式推送 ``{table_key: []}`` 表示该表"空行"有效状态（区别于删除），照常覆盖。
        merged_sub = dict(existing_sub)
        for key, rows in clean_sub_table_data.items():
            merged_sub[key] = rows
        # ★ 行级合并（多段共享表）：只对声明了 `_row_scope` 的表生效
        if row_scopes:
            row_scoped_tables, row_scope_unresolved = _apply_row_scoped_merge(
                merged_sub,
                clean_sub_table_data,
                row_scopes,
                variant=row_scope_variant,
                section_number=section_id,
                baselines=existing_sub,
            )
        new_table_data["sub_table_data"] = merged_sub
    else:
        # 空载荷 no-op：绝不清空既有子表（表格丢失主因修复）。
        # 改版底稿仅同步叙述、item_id/字段漂移读不出表格、或传入空 {} 时，
        # 保留附注已有全部表格，仅更新叙述/元数据。若需删除表格须显式经删除语义
        # （当前契约不支持删除，避免误删）。
        new_table_data["sub_table_data"] = existing_sub

    # ── 列头元数据 _sub_table_columns：与 sub_table_data 同款浅合并 + 空 no-op ──
    #   （spec disclosure-table-sync-convergence Req2/D3/Property13）
    #   投影器据此把 sub_table_data 渲染成源模板表样；空载荷不清空既有列头。
    clean_columns = sub_table_columns if isinstance(sub_table_columns, dict) else {}
    existing_cols = new_table_data.get("_sub_table_columns")
    existing_cols = existing_cols if isinstance(existing_cols, dict) else {}
    if clean_columns:
        merged_cols = dict(existing_cols)
        for key, defs in clean_columns.items():
            merged_cols[key] = defs
        new_table_data["_sub_table_columns"] = merged_cols
    elif existing_cols:
        new_table_data["_sub_table_columns"] = existing_cols

    # ── 旧表名清理（Requirement 8）：改版重命名后删除附注残留空表 ──
    if removed_table_keys:
        sub_after = dict(new_table_data.get("sub_table_data") or {})
        cols_after = dict(new_table_data.get("_sub_table_columns") or {})
        dropped = _drop_removed_tables(
            sub_after, cols_after, removed_table_keys, set(clean_sub_table_data or {}),
        )
        new_table_data["sub_table_data"] = sub_after
        if cols_after or "_sub_table_columns" in new_table_data:
            new_table_data["_sub_table_columns"] = cols_after
        if dropped:
            logger.info(
                "wp_disclosure_sync: dropped obsolete sub-tables %s section=%s",
                dropped, section_id,
            )

    new_table_data["_source"] = "workpaper"
    new_table_data["_current_standard"] = current_standard
    new_table_data["_last_sync_wp_id"] = str(wp_id)
    new_table_data["_last_sync_sheet"] = sheet_name
    new_table_data["_last_sync_at"] = now.isoformat()

    # ── 叙述段按 `section` 浅合并（原实现是整列表替换）──────────────────────
    #   多循环共用同一附注章节时（G2/G3/K1 共用 五、8/八、9），整替换会让
    #   K1 录的 10 段说明被 G2 的一段整体覆盖。删除走显式 `_removed_text_sections`。
    existing_note_texts = new_table_data.get("_note_texts")
    merged_note_texts = _merge_note_texts(
        existing_note_texts if isinstance(existing_note_texts, list) else [],
        note_texts,
        removed_text_sections,
    )
    if merged_note_texts:
        new_table_data["_note_texts"] = merged_note_texts
    else:
        new_table_data.pop("_note_texts", None)
    formatted_texts = _format_note_texts(merged_note_texts)

    content_type = ContentType.table
    if formatted_texts or (note and note.content_type == ContentType.mixed):
        content_type = ContentType.mixed
    if note and note.content_type == ContentType.text and formatted_texts:
        content_type = ContentType.mixed

    created = False
    blocked_by_manual_override = False

    if note is None:
        # ─── 新建 ─────────────────────────────────────────────────────
        # 从 current_standard（如 "soe_standalone" / "listed_standalone"）派生 source_template
        source_template_value: SourceTemplate | None = None
        if current_standard:
            cs = current_standard.lower()
            if cs.startswith("listed"):
                source_template_value = SourceTemplate.listed
            elif cs.startswith("soe"):
                source_template_value = SourceTemplate.soe
        derived_title, derived_account = _resolve_section_meta(
            section_id, source_template_value
        )
        note = DisclosureNote(
            project_id=project_id,
            year=target_year,
            note_section=section_id,
            section_title=derived_title,
            account_name=derived_account,
            content_type=content_type,
            table_data=new_table_data,
            text_content=formatted_texts or None,
            source_template=source_template_value,
            status=NoteStatus.draft,
            last_sync_source="workpaper",
            last_sync_wp_id=wp_id,
            last_sync_at=now,
            last_sync_user_id=user.id,
            updated_by=user.id,
        )
        db.add(note)
        created = True
        logger.info(
            "wp_disclosure_sync: created new disclosure_note "
            "project=%s section=%s wp_id=%s rows=%d texts=%d",
            project_id, section_id, wp_id, rows_synced, len(note_texts),
        )
    else:
        # ─── 更新 ─────────────────────────────────────────────────────
        # manual_override 守卫：写入前先看目标是否有 _manual_override 标记
        is_manual_override = _detect_manual_override(note.table_data)
        if is_manual_override:
            decision = await _check_manual_override_before_propagate(
                db=db,
                project_id=project_id,
                source_module="workpaper",
                source_id=wp_id,
                target_module="disclosure",
                target_id=note.id,
                target_field=f"sub_table_data.{section_id}",
                new_value=sheet_name,  # 上游标识（具体值由 sub_table_data 表达，过长不入审计 details）
                current_value=None,
                is_manual_override=True,
                user_id=user.id,
                propagation_origin=propagation_origin,
            )
            if decision == "block_enqueued":
                # 拦截：跳过 table_data 更新，仅记录 last_sync_at（说明同步已被尝试但被守卫拦下）
                blocked_by_manual_override = True
                note.last_sync_source = "workpaper"
                note.last_sync_wp_id = wp_id
                note.last_sync_at = now
                note.last_sync_user_id = user.id
                logger.info(
                    "wp_disclosure_sync: BLOCKED by manual_override "
                    "id=%s section=%s wp_id=%s",
                    note.id, section_id, wp_id,
                )
                if commit:
                    await db.commit()
                return {
                    "success": True,
                    "section_id": section_id,
                    "synced_at": now.isoformat(),
                    "rows_synced": 0,
                    "created": False,
                    "blocked_by_manual_override": True,
                    "texts_synced": 0,
                    # 被守卫拦下 → 一行都没写，行级合并同样未发生
                    "row_scoped_tables": [],
                    "row_scope_unresolved": [],
                }
            # decision in ('auto_resolved', 'allow') → 继续走更新分支
        note.table_data = new_table_data
        note.content_type = content_type
        if formatted_texts:
            note.text_content = formatted_texts
        elif note_texts or removed_text_sections:
            # 本次**确实**推了叙述（或显式删段）而合并后为空（全被删 / 文本全空）
            # → 如实清空，保持 text_content 由底稿联动驱动
            note.text_content = None
        else:
            # 🔴 本次未推送叙述 → **保留既有**（Requirement 5.2）。
            #   原实现无条件置 None：多循环共章节时会清掉他循环刚推的说明，
            #   也会清掉审计师在附注模块 AI 填充/手工编辑的正文。
            pass
        note.last_sync_source = "workpaper"
        note.last_sync_wp_id = wp_id
        note.last_sync_at = now
        note.last_sync_user_id = user.id
        note.updated_by = user.id
        note.updated_at = now
        logger.info(
            "wp_disclosure_sync: updated disclosure_note "
            "id=%s section=%s wp_id=%s rows=%d texts=%d",
            note.id, section_id, wp_id, rows_synced, len(note_texts),
        )

    if commit:
        await db.commit()

    return {
        "success": True,
        "section_id": section_id,
        "synced_at": now.isoformat(),
        "rows_synced": rows_synced,
        "created": created,
        # additive：本次是否复活了被软删的同键章节（唯一键含软删行，见上方复活逻辑）
        "revived": revived,
        "blocked_by_manual_override": blocked_by_manual_override,
        "texts_synced": len(note_texts),
        # additive（行级合并）：本次走行级合并的表 / 段边界解析失败被跳过的表。
        # `row_scope_unresolved` 必须进返回值而非只进日志 —— fail closed 是静默跳过，
        # 前端据此提示审计师「这张表没同步成功」，否则又是一个 dead path。
        "row_scoped_tables": row_scoped_tables,
        "row_scope_unresolved": row_scope_unresolved,
    }


async def sync_batch_from_workpaper(
    db: AsyncSession,
    project_id: UUID,
    *,
    wp_id: UUID,
    current_standard: str,
    items: list[dict[str, Any]],
    user: User,
    year: int | None = None,
    propagation_origin: Literal["user_edit", "system_recompute"] = "user_edit",
) -> dict[str, Any]:
    """多章节一次事务同步：任一失败则整批回滚。"""
    if not items:
        raise ValueError("items 不能为空")

    results: list[dict[str, Any]] = []
    try:
        for item in items:
            section_id = str(item.get("section_id") or "").strip()
            sheet_name = str(item.get("sheet_name") or "").strip()
            if not section_id or not sheet_name:
                raise ValueError("每个 item 必须包含 section_id 与 sheet_name")
            sub_table_data = item.get("sub_table_data") or {}
            if not isinstance(sub_table_data, dict):
                raise ValueError(f"section {section_id} 的 sub_table_data 必须为对象")
            sub_table_columns = item.get("columns")
            if sub_table_columns is not None and not isinstance(sub_table_columns, dict):
                raise ValueError(f"section {section_id} 的 columns 必须为对象")
            result = await sync_from_workpaper(
                db,
                project_id,
                wp_id=wp_id,
                sheet_name=sheet_name,
                section_id=section_id,
                sub_table_data=sub_table_data,
                current_standard=current_standard,
                user=user,
                year=year,
                sub_table_columns=sub_table_columns,
                propagation_origin=propagation_origin,
                commit=False,
            )
            results.append(result)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {
        "success": True,
        "sections_synced": len(results),
        "rows_synced": sum(int(item.get("rows_synced") or 0) for item in results),
        "texts_synced": sum(int(item.get("texts_synced") or 0) for item in results),
        "results": results,
        "synced_at": results[-1]["synced_at"] if results else datetime.now(timezone.utc).isoformat(),
    }


# ─── US-3: HTML 路径同步服务类 ────────────────────────────────────────────────


class WpDisclosureSyncService:
    """C 类底稿 → disclosure_notes 同步服务（HTML 渲染器路径）。

    Validates: Requirements US-3（C 类底稿 → 附注自动同步）
    """

    async def sync_from_html(
        self,
        db: AsyncSession,
        wp_id: UUID,
        sheet_name: str,
        sub_table_data: dict,
        *,
        project_id: UUID,
        user: User,
        sub_table_columns: dict | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """从 HTML 渲染器的 C 类底稿同步到 disclosure_notes。

        Steps:
        1. 查 wp_code → 映射到 disclosure_notes.section_id
        2. 读 disclosure_notes 当前值
        3. 冲突检测（除非 force=True）
        4. 写入 table_data + is_stale=False
        5. 审计日志
        6. SSE 通知

        Args:
            db: async DB session
            wp_id: 底稿 ID
            sheet_name: C 类附注 sheet 名
            sub_table_data: 子表数据
            project_id: 项目 ID
            user: 当前用户
            force: 强制覆盖（跳过冲突检测）

        Returns:
            同步结果 dict

        Raises:
            ConflictError: 附注侧有更新的手动编辑
        """
        now = datetime.now(timezone.utc)
        # 先剥离元数据键（`_removed_table_keys` / `_row_scope`），保证新建/更新两条分支入库形态一致
        incoming_raw, html_removed_keys = _extract_removed_table_keys(sub_table_data)
        incoming_raw, html_row_scopes = _extract_row_scope(incoming_raw)
        for _orphan in [k for k in html_row_scopes if k not in incoming_raw]:
            logger.warning(
                "sync_from_html: %s['%s'] 声明的表不在本次推送里 → 忽略该条声明",
                ROW_SCOPE_KEY, _orphan,
            )
            html_row_scopes.pop(_orphan, None)

        # 1. 查映射：通过 sheet_name 推导 section_id
        mapping = await self._get_section_mapping(db, wp_id, sheet_name)
        if not mapping:
            logger.debug(
                "sync_from_html: no mapping for wp_id=%s sheet=%s, skip",
                wp_id, sheet_name,
            )
            return {
                "success": True,
                "synced": False,
                "reason": "no_mapping",
            }

        section_id = mapping["section_id"]
        last_sync_at = mapping.get("last_sync_at")

        # 2. 读 disclosure_notes 当前值（按项目审计年度定位，避免跨年度串记录）
        target_year = await _resolve_target_year(db, project_id, None)
        note = await self._get_note(db, project_id, section_id, year=target_year)

        if note is None:
            # 软删行复活（唯一键 (project_id, year, note_section) 不含 is_deleted，
            # 直接 INSERT 会撞键 500）；命中则复用该行走更新分支
            revived_stmt = sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == target_year,
                DisclosureNote.note_section == section_id,
                DisclosureNote.is_deleted == sa.true(),
            )
            revived_result = await db.execute(revived_stmt)
            note = revived_result.scalar_one_or_none()
            if note is not None:
                note.is_deleted = False

        if note is None:
            # 无现有记录 → 新建（标题/科目名优先查附注模板，避免用章节号当标题）
            if html_row_scopes:
                # 新建分支拿不到变体（无 `_current_standard` / 无 `source_template`）→
                # 无法定位段窗口。此时附注里**没有任何他人数据**，表级写入不会污染谁，
                # 故按现状整表写入，仅记 warning：他段骨架本次不会预置
                # （下一次同步走更新分支即会补齐）。行级合并的实际消费者
                # （E1 等）走 `sync_from_workpaper`，不经本分支。
                logger.warning(
                    "sync_from_html: 新建章节 %s 声明了 %s 但无变体可解析 → "
                    "本次按整表写入，他段骨架不预置：%s",
                    section_id, ROW_SCOPE_KEY, sorted(html_row_scopes),
                )
            html_title, html_account = _resolve_section_meta(section_id, None)
            note = DisclosureNote(
                project_id=project_id,
                year=target_year,
                note_section=section_id,
                section_title=html_title,
                account_name=html_account,
                content_type=ContentType.table,
                table_data=(
                    {
                        "sub_table_data": normalize_sub_table_data(
                            incoming_raw, sub_table_columns,
                        ),
                        "_sub_table_columns": sub_table_columns,
                    }
                    if isinstance(sub_table_columns, dict) and sub_table_columns
                    else {
                        "sub_table_data": normalize_sub_table_data(incoming_raw),
                    }
                ),
                status=NoteStatus.draft,
                is_stale=False,
                last_sync_source="workpaper_html",
                last_sync_wp_id=wp_id,
                last_sync_at=now,
                last_sync_user_id=user.id,
                updated_by=user.id,
            )
            db.add(note)
            await db.flush()
            try:
                await self._write_audit_log(db, "disclosure_sync_create", wp_id, section_id, user)
            except Exception as exc:
                logger.warning("Audit log write failed (non-blocking): %s", exc)
            self._broadcast_synced(project_id, section_id)
            await db.commit()
            return {
                "success": True,
                "synced": True,
                "section_id": section_id,
                "synced_at": now.isoformat(),
                "created": True,
            }

        # 3. 冲突检测
        if not force and last_sync_at and note.updated_at:
            if note.updated_at > last_sync_at:
                raise ConflictError(
                    note_id=note.id,
                    note_updated=note.updated_at,
                    last_sync_at=last_sync_at,
                )

        # 4. 写入（原子操作）
        existing_table_data = dict(note.table_data) if note.table_data else {}
        # 该入口的 sub_table_data 未做逐值类型约束（dict），归一后再落库
        incoming_sub = normalize_sub_table_data(incoming_raw, sub_table_columns)
        html_row_scoped: list[str] = []
        html_row_scope_unresolved: list[str] = []
        if incoming_sub:
            merged_html_sub = dict(incoming_sub)
            if html_row_scopes:
                prev_sub_for_scope = existing_table_data.get("sub_table_data")
                prev_sub_for_scope = (
                    prev_sub_for_scope if isinstance(prev_sub_for_scope, dict) else {}
                )
                # 该入口无 `current_standard` 形参 → 变体取落库元数据，再退 source_template
                html_variant = resolve_template_variant(
                    existing_table_data.get("_current_standard"), note.source_template
                )
                html_row_scoped, html_row_scope_unresolved = _apply_row_scoped_merge(
                    merged_html_sub,
                    incoming_sub,
                    html_row_scopes,
                    variant=html_variant,
                    section_number=section_id,
                    baselines=prev_sub_for_scope,
                )
            existing_table_data["sub_table_data"] = merged_html_sub
        else:
            # 空载荷 no-op：绝不清空既有子表（与 sync_from_workpaper 同款防护）。
            prev_sub = existing_table_data.get("sub_table_data")
            existing_table_data["sub_table_data"] = prev_sub if isinstance(prev_sub, dict) else {}
        # 列头元数据同款浅合并 + 空 no-op
        incoming_cols = sub_table_columns if isinstance(sub_table_columns, dict) else {}
        prev_cols = existing_table_data.get("_sub_table_columns")
        prev_cols = prev_cols if isinstance(prev_cols, dict) else {}
        if incoming_cols:
            merged_cols = dict(prev_cols)
            merged_cols.update(incoming_cols)
            existing_table_data["_sub_table_columns"] = merged_cols
        elif prev_cols:
            existing_table_data["_sub_table_columns"] = prev_cols
        if html_removed_keys:
            sub_after = dict(existing_table_data.get("sub_table_data") or {})
            cols_after = dict(existing_table_data.get("_sub_table_columns") or {})
            _drop_removed_tables(sub_after, cols_after, html_removed_keys, set(incoming_sub or {}))
            existing_table_data["sub_table_data"] = sub_after
            if cols_after or "_sub_table_columns" in existing_table_data:
                existing_table_data["_sub_table_columns"] = cols_after
        existing_table_data["_source"] = "workpaper_html"
        existing_table_data["_last_sync_wp_id"] = str(wp_id)
        existing_table_data["_last_sync_sheet"] = sheet_name
        existing_table_data["_last_sync_at"] = now.isoformat()

        note.table_data = existing_table_data
        note.is_stale = False
        note.last_sync_source = "workpaper_html"
        note.last_sync_wp_id = wp_id
        note.last_sync_at = now
        note.last_sync_user_id = user.id
        note.updated_by = user.id
        note.updated_at = now

        # 5. 审计日志（失败不阻断主流程）
        try:
            await self._write_audit_log(db, "disclosure_sync_update", wp_id, section_id, user)
        except Exception as exc:
            logger.warning("Audit log write failed (non-blocking): %s", exc)

        # 6. SSE 通知
        self._broadcast_synced(project_id, section_id)

        await db.commit()

        return {
            "success": True,
            "synced": True,
            "section_id": section_id,
            "synced_at": now.isoformat(),
            "created": False,
            # additive（行级合并）：与 `sync_from_workpaper` 同名同义
            "row_scoped_tables": html_row_scoped,
            "row_scope_unresolved": html_row_scope_unresolved,
        }

    async def _get_section_mapping(
        self, db: AsyncSession, wp_id: UUID, sheet_name: str
    ) -> dict[str, Any] | None:
        """查 wp_id + sheet_name → section_id 映射。

        策略：查 disclosure_notes 中 last_sync_wp_id = wp_id 且
        table_data._last_sync_sheet = sheet_name 的记录。
        如果找不到，尝试从 sheet_name 推导 section_id（C 类 sheet 命名约定）。
        """
        # 方式 1：查已有同步记录
        stmt = sa.select(DisclosureNote).where(
            DisclosureNote.last_sync_wp_id == wp_id,
            DisclosureNote.is_deleted == sa.false(),
        )
        result = await db.execute(stmt)
        notes = result.scalars().all()

        for n in notes:
            td = n.table_data or {}
            if td.get("_last_sync_sheet") == sheet_name:
                return {
                    "section_id": n.note_section,
                    "last_sync_at": n.last_sync_at,
                }

        # 方式 2：从 sheet_name 推导（C 类 sheet 命名约定：如 "应收账款附注C" → "五-1-1 应收账款"）
        # 简化：用 sheet_name 作为 section_id 查找
        stmt2 = sa.select(DisclosureNote).where(
            DisclosureNote.note_section.ilike(f"%{sheet_name.replace('附注C', '').replace('附注', '')}%"),
            DisclosureNote.is_deleted == sa.false(),
        ).limit(1)
        result2 = await db.execute(stmt2)
        note2 = result2.scalar_one_or_none()
        if note2:
            return {
                "section_id": note2.note_section,
                "last_sync_at": note2.last_sync_at,
            }

        return None

    async def _get_note(
        self,
        db: AsyncSession,
        project_id: UUID,
        section_id: str,
        *,
        year: int | None = None,
    ) -> DisclosureNote | None:
        """读 disclosure_notes 当前值。

        传 ``year`` 时按年度精确定位（同一 section 跨年度并存时避免
        ``scalar_one_or_none`` 抛 MultipleResultsFound）；不传保持原行为。
        """
        stmt = sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.note_section == section_id,
            DisclosureNote.is_deleted == sa.false(),
        )
        if year is not None:
            stmt = stmt.where(DisclosureNote.year == year)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _write_audit_log(
        self, db: AsyncSession, action: str, wp_id: UUID, section_id: str, user: User
    ) -> None:
        """写入审计日志。"""
        try:
            from app.models.audit_log_models import AuditLogEntry

            log_entry = AuditLogEntry(
                user_id=user.id,
                action_type=action,
                object_type="disclosure_note",
                object_id=None,
                payload={
                    "wp_id": str(wp_id),
                    "section_id": section_id,
                    "source": "workpaper_html",
                },
            )
            db.add(log_entry)
        except Exception as exc:
            # 审计日志写入失败不阻断主流程
            logger.warning("Failed to write audit log: %s", exc)

    def _broadcast_synced(self, project_id: UUID, section_id: str) -> None:
        """发布 note.synced SSE 事件（非阻塞）。"""
        try:
            from app.services.event_bus import event_bus

            event_bus.broadcast_raw(
                event_type="note.synced",
                extra={
                    "project_id": str(project_id),
                    "section_id": section_id,
                },
            )
        except Exception as exc:
            logger.warning("Failed to broadcast note.synced SSE: %s", exc)


# ─── Module-level singleton ──────────────────────────────────────────────────

wp_disclosure_sync_service = WpDisclosureSyncService()
