"""NoteConversionService — 国企版与上市版互转

Requirements: 47.1, 47.2, 47.3, 47.4, 47.5, 47.6, 47.7
Sprint A.5: D14 国企↔上市丝滑切换

基于 `审计报告模板/纯报表科目注释/` 对照模板执行行次映射：
- 报表行次映射：国企版 row_code → 上市版 row_code（保留金额）
- 附注章节映射：保留已填充数据
- 公式适配：更新 row_code 引用
- 转换前影响预览（新增/删除/保留数量）
- 转换操作支持撤销（保留快照 30 天）
- 转换完成后自动执行全链路刷新

V2 (Sprint A.5):
- section_id 匹配（不依赖 section_number 字符串）
- manual cells 保留：用 merge_table_data_preserving_cell_modes 合并
- SOE 独有 → archive 到 template_lineage.archived_sections
- Listed 独有 → 创建空 DisclosureNote
- format_diff → 调 adapt_table_data
"""
from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 章节映射的原因码与常量
# spec: soe-listed-note-conversion-correctness / Requirements 2.6, 2.8, 4.2, 4.3
# ---------------------------------------------------------------------------

#: 目标侧已有同 sid 的未删除记录 ⇒ 不改写（防 Requirement 2.6 的重复行）
SKIP_REASON_TARGET_SID_OCCUPIED = "target_sid_occupied"
#: 目标章节号已被本 (project, year) 的**任一**记录占用（含软删）⇒ 不改写。
#:
#: 🔴 判据来自 DB 硬约束（2026-08-07 实测 ``pg_indexes``，spec 未登记）：
#: ``uq_disclosure_notes_project_year_section`` 是 ``(project_id, year, note_section)``
#: 上的 **UNIQUE 索引且不带 ``is_deleted`` 过滤** ⇒ 软删记录同样占位。撞它会在
#: flush 时抛 IntegrityError；那是**可预期条件**不是错误，故前置检查后进
#: ``skipped``，而不是让它掉进 ``failed``（避免把正常业务状态报成故障）。
SKIP_REASON_TARGET_NUMBER_OCCUPIED = "target_note_section_occupied"
#: ``section_id`` 为 NULL 且按 (note_section, section_title) 回填不出（Requirement 2.8）
SKIP_REASON_SID_UNRESOLVED = "sid_unresolved"
#: 回填候选多于一个（模板内同 (number,title) 或同 title 撞车）⇒ 宁缺勿造
SKIP_REASON_SID_AMBIGUOUS = "sid_ambiguous"
#: sid 已是目标侧取值 ⇒ 本章节已转换过（幂等重跑）
SKIP_REASON_ALREADY_TARGET = "already_target_side"
#: sid 既不在共有清单也不在源独有清单（模板漂移 / 手工建的章节）
SKIP_REASON_UNKNOWN_SECTION = "unknown_section"
#: 目标模板查不到该 sid 的 ``section_number``（结构性异常，模板 sid 应唯一且必带编号）
SKIP_REASON_TARGET_NUMBER_MISSING = "target_number_missing"

# --- 目标侧独有章节的新建（Requirement 2.4）三条不建原因 -------------------

#: 目标独有章节的 sid 在本 (project, year) 已有未删除记录 ⇒ 不重复建（幂等重跑）
SKIP_REASON_CREATE_ALREADY_EXISTS = "create_target_already_exists"
#: 目标独有章节的章节号已被占用（**含软删记录** —— 见
#: :data:`SKIP_REASON_TARGET_NUMBER_OCCUPIED` 的索引说明）。
#:
#: 🔴 这条路径**可达且必然发生**：归档走软删而 ``uq_disclosure_notes_project_year_section``
#: 不排除软删行 ⇒ 被归档章节的章节号仍占位。实测两份模板的「源独有章节号」与
#: 「目标独有章节号」交集恰为 ``七`` / ``五`` / ``十三`` 三个（两个方向都是这三个）
#: ⇒ 这三个新建空章节会撞上刚归档的同号行。撞号是**可预期业务状态**（进
#: ``skipped`` 供审计核对），**不是错误**（掉进 ``failed`` 会把正常状态报成故障）。
SKIP_REASON_CREATE_NUMBER_OCCUPIED = "create_target_number_occupied"
#: 目标模板无该 sid 的 ``section_number`` ⇒ 建不出（实测当前为 0 条，属结构性防御）
SKIP_REASON_CREATE_NUMBER_MISSING = "create_target_number_missing"

# --- 回滚（Requirement 9.3）-------------------------------------------------

#: ``snapshot_before`` 的格式版本。
#:
#: * ``1``（隐含，无该键）= 旧格式，只有 ``template_type`` / ``year`` /
#:   ``converted_at`` ⇒ **结构上无法**回退 ``section_id`` / ``note_section`` /
#:   归档状态；回滚必须 fail-closed 如实报告，禁静默假成功。
#: * ``2`` = 本 spec Task 16 起的格式，额外带 ``notes[]``（逐章节的
#:   ``section_id`` / ``note_section`` / ``is_deleted`` / ``template_lineage``）
#:   与 ``target_type`` / ``direction``。
SNAPSHOT_FORMAT_VERSION = 2

#: 旧格式快照 ⇒ 章节字段无法回退（``status='partial'`` 的原因码）
ROLLBACK_REASON_LEGACY_SNAPSHOT = "legacy_snapshot_without_section_state"
#: 转换新建的空章节在转换后被录入了内容 ⇒ 不删（删就是删审计师的数据）
ROLLBACK_SKIP_CREATED_HAS_CONTENT = "created_section_has_user_content"
#: 章节号目标值被**本次回滚无权移动**的记录占用 ⇒ 该章节整体不回退
ROLLBACK_FAIL_NUMBER_BLOCKED = "note_section_restore_blocked"
#: 快照里的章节在库中已不存在（被别的流程物理删除）⇒ 无从回退
ROLLBACK_SKIP_NOTE_MISSING = "snapshot_note_no_longer_exists"

#: 回滚**不尝试**还原的字段（如实上报给调用方，禁静默假成功）。
#:
#: 🔴 ``table_data`` 只回退 ``binding_id`` 章节号前缀，**不整体还原**。两条理由：
#:
#: 1. **整体还原会销毁用户数据** —— 快照最长保留 30 天，期间审计师可能在附注里
#:    正常录入；拿 30 天前的 ``table_data`` 覆盖回去，等于把这段时间的编辑全部
#:    抹掉（比「没回退干净」严重得多）。
#: 2. **验收判据只要求 binding_id 一致**（spec Task 17：往返后
#:    ``section_id`` / ``note_section`` / ``is_deleted`` / ``template_lineage`` /
#:    ``binding_id`` 回到初始），而 ``binding_id`` 前缀改写是**可逆变换**
#:    （正向 ``(td, old, new)``，逆向 ``(td, new, old)``），无需快照。
#:
#: 由此有一项**确实不可逆**：正向的格式适配（``adapt_table_data_with_report``
#: 改列结构 / 搬单元格）。当前 ``field_mapping`` 实测 39/39 全 null ⇒
#: ``format_adapted`` 结构性恒 0，故实践中无损；但一旦非 0，回滚结果里会带
#: ``format_adapted_not_reversible`` 并把 ``status`` 降级为 ``partial``。
ROLLBACK_UNRESTORED_FIELDS: tuple[str, ...] = (
    "table_data（仅回退 binding_id 章节号前缀；正向格式适配不可逆）",
)

#: 归档原因（写入 ``template_lineage.archived_sections[].reason``）。
#: 取值形态沿用历史实现（已于 spec Task 10 删除的 v2 章节转换方法），
#: 避免同一字段出现两套约定。
def archive_reason(current_type: str, target_type: str) -> str:
    """``template_lineage.archived_sections[].reason`` 的取值。"""
    return f"template_conversion_{current_type}_to_{target_type}"


#: 本步**不统计**的返回键 —— 取值为 ``None`` 表示「未测量」，与 ``0``（已测量为零）
#: 严格区分（平台三态纪律）。
#:
#: spec Task 9 已填充 ``archived`` / ``created`` / ``user_edits_preserved``
#: 三项，故本元组**清空**：这三个键现在是真实计数，``0`` 表示「已测量为零」。
#: 保留常量本身是为了 ``pending_keys`` 返回键的语义连续性（空列表 = 无未测量项），
#: 将来若再有未测量项按同一纪律登记进来。
MAP_NOTES_PENDING_KEYS: tuple[str, ...] = ()


def _conversion_side(template_type: str) -> str:
    """``template_type`` → 匹配器/模板侧标识（``soe`` / ``listed``）。"""
    return "soe" if str(template_type) == "soe" else "listed"


def _rewrite_binding_id_prefix(node: Any, old_prefix: str, new_prefix: str) -> int:
    """就地改写 ``table_data`` 内所有 ``binding_id`` 的章节号前缀。

    spec: soe-listed-note-conversion-correctness / Requirement 2.7（Property 35）

    ``binding_id`` 形态是「**章节号**.行标签.列键」（实测 1030 个未软删章节中
    446 条带 binding，如 ``八、26.其中：土地.closing_balance``）。改写
    ``note_section`` 而不改前缀会让这批绑定**静默失联** —— 公式取数变成空值而
    不是报错，属最难发现的一类缺陷。

    binding_id 分布在多个层级（实测容器键含 ``rows`` / ``_tables[].rows`` /
    ``sub_table_data`` 等），故按**递归遍历**处理而不是只扫某个固定路径。

    Args:
        node: 已**深拷贝**的 table_data 片段（禁传 ORM 持有的原对象 —— JSONB 就地
            改嵌套不标脏，且改完再赋值会因新旧相等而不发 UPDATE）
        old_prefix: 旧章节号
        new_prefix: 新章节号

    Returns:
        改写条数。
    """
    if not old_prefix or not new_prefix or old_prefix == new_prefix:
        return 0
    old_head = f"{old_prefix}."
    new_head = f"{new_prefix}."
    count = 0
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "binding_id" and isinstance(value, str) and value.startswith(old_head):
                node[key] = new_head + value[len(old_head):]
                count += 1
            else:
                count += _rewrite_binding_id_prefix(value, old_prefix, new_prefix)
    elif isinstance(node, list):
        for item in node:
            count += _rewrite_binding_id_prefix(item, old_prefix, new_prefix)
    return count


def count_manual_cells(node: Any) -> int:
    """统计 ``table_data`` 内 ``_cell_modes`` 取值为 ``manual`` 的单元格数。

    spec: soe-listed-note-conversion-correctness / Requirement 2.5（Property 9）

    ------------------------------------------------------------------
    为什么按**值**判定而不按键形态
    ------------------------------------------------------------------

    ``_cell_modes`` 有两种建键形态并存：**按列索引**（``{"0": "manual"}``，真实库
    实测 47390/47390 个键全是数字）与**按列 id**（列重映射路径产生，见
    ``note_template_diff._ROW_COLUMN_KEYED_BUCKETS``）。按 ``manual`` **值**计数
    对两种形态都成立，无需分支。

    ------------------------------------------------------------------
    为什么递归 + 镜像跳过
    ------------------------------------------------------------------

    ``_cell_modes`` 实测分布在三处容器：``rows[]``（370 个章节）/
    ``_tables[].rows[]``（256）/ ``sub_table_data.*[]``（87），只扫某个固定路径会漏
    （同 :func:`_rewrite_binding_id_prefix` 的成因）。

    🔴 但**顶层 ``rows`` 是 ``_tables[0].rows`` 的冗余副本** —— 真实库实测两者同时
    存在的 392 个章节里 **392/392 逐字节相同**（legacy 单表表示，
    ``note_total_recalc`` 亦明写「末尾把首张表的 rows 镜像到顶层」）⇒ 朴素递归会把
    这批 manual 单元格**计两次**，让上报数虚增一倍。故仅当两者**实测相等**时才跳过
    顶层 ``rows``（数据驱动，不假设镜像一定成立；万一不相等则两处都算，宁多算不漏）。

    Args:
        node: ``table_data`` 或其片段。非 dict/list 一律返回 0。

    Returns:
        manual 单元格数。
    """
    if isinstance(node, dict):
        total = 0
        modes = node.get("_cell_modes")
        if isinstance(modes, dict):
            total += sum(1 for v in modes.values() if v == "manual")
        rows = node.get("rows")
        tables = node.get("_tables")
        mirrored = (
            isinstance(rows, list)
            and isinstance(tables, list)
            and bool(tables)
            and isinstance(tables[0], dict)
            and tables[0].get("rows") == rows
        )
        for key, value in node.items():
            if key == "_cell_modes":
                continue
            if key == "rows" and mirrored:
                continue
            total += count_manual_cells(value)
        return total
    if isinstance(node, list):
        return sum(count_manual_cells(item) for item in node)
    return 0


def _append_unique(container: dict[str, Any], key: str, value: Any) -> bool:
    """往 lineage 的 list 字段追加（去重）。返回是否真的改了。

    去重是必要的：同值重复追加会让新旧 dict 相等 ⇒ 工作单元判「无净变更」⇒
    不发 UPDATE，看起来「写了」其实没写。
    """
    existing = container.get(key)
    items = list(existing) if isinstance(existing, list) else []
    if value in items:
        return False
    items.append(value)
    container[key] = items
    return True


def snapshot_note_state(note: Any) -> dict[str, Any]:
    """把一个 ``DisclosureNote`` 的**可回退字段**投影成快照条目（纯函数）。

    spec: soe-listed-note-conversion-correctness / Requirement 9.3（Property 32）

    只取 :func:`_map_disclosure_notes` 会改写的四个列 —— 快照要能证明「往返后逐
    字段回到初始」，多存无用字段只会让 30 天前的旧值有机会覆盖新数据
    （见 :data:`ROLLBACK_UNRESTORED_FIELDS` 的第 1 条理由）。

    ``table_data`` **有意不入快照**：正向对它的唯一改动是 ``binding_id`` 章节号
    前缀，而那是可逆变换（逆向即 ``_rewrite_binding_id_prefix(td, new, old)``）。

    Returns:
        JSON 可序列化的 dict（``snapshot_before`` 是 JSONB 列，值必须能过
        ``json`` 编码 —— 故 ``note_id`` 存 ``str``、lineage 深拷贝）。
    """
    lineage = note.template_lineage
    return {
        "note_id": str(note.id),
        "section_id": note.section_id,
        "note_section": note.note_section,
        "is_deleted": bool(note.is_deleted),
        "template_lineage": deepcopy(lineage) if isinstance(lineage, dict) else None,
    }


# ---------------------------------------------------------------------------
# Row name mapping (SOE → Listed) loaded from soe_listed_mapping_preset.json
# ---------------------------------------------------------------------------

_MAPPING_DATA: dict[str, dict[str, str]] | None = None


def _load_mapping_data() -> dict[str, dict[str, str]]:
    """Load SOE→Listed row name mapping from preset JSON."""
    global _MAPPING_DATA
    if _MAPPING_DATA is not None:
        return _MAPPING_DATA

    import pathlib
    preset_path = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "soe_listed_mapping_preset.json"
    if preset_path.exists():
        with open(preset_path, "r", encoding="utf-8") as f:
            _MAPPING_DATA = json.load(f)
    else:
        logger.warning("soe_listed_mapping_preset.json not found at %s", preset_path)
        _MAPPING_DATA = {}
    return _MAPPING_DATA


def _build_reverse_mapping(mapping: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Build Listed→SOE reverse mapping."""
    reverse: dict[str, dict[str, str]] = {}
    for report_type, rows in mapping.items():
        reverse[report_type] = {v: k for k, v in rows.items()}
    return reverse


# ---------------------------------------------------------------------------
# Impact Preview
# ---------------------------------------------------------------------------


class ConversionPreview:
    """Impact preview result for a conversion."""

    def __init__(
        self,
        added: int = 0,
        removed: int = 0,
        preserved: int = 0,
        added_items: list[str] | None = None,
        removed_items: list[str] | None = None,
    ):
        self.added = added
        self.removed = removed
        self.preserved = preserved
        self.added_items = added_items or []
        self.removed_items = removed_items or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "removed": self.removed,
            "preserved": self.preserved,
            "added_items": self.added_items[:20],  # Limit for response size
            "removed_items": self.removed_items[:20],
        }


# ---------------------------------------------------------------------------
# NoteConversionService
# ---------------------------------------------------------------------------


class NoteConversionService:
    """Service for converting between SOE and Listed report standards."""

    SNAPSHOT_RETENTION_DAYS = 30

    def __init__(self, db: AsyncSession):
        self.db = db

    async def preview_conversion(
        self,
        project_id: UUID,
        year: int,
        target_type: str,
    ) -> ConversionPreview:
        """Preview the impact of converting to target_type.

        Returns counts of added/removed/preserved row names.

        Requirements: 47.4
        """
        if target_type not in ("soe", "listed"):
            raise ValueError("target_type must be 'soe' or 'listed'")

        # Get current project template_type
        project = await self._get_project(project_id)
        current_type = project.template_type or "soe"

        if current_type == target_type:
            return ConversionPreview(added=0, removed=0, preserved=0)

        mapping_data = _load_mapping_data()

        added_items: list[str] = []
        removed_items: list[str] = []
        preserved = 0

        for report_type, row_mapping in mapping_data.items():
            if current_type == "soe" and target_type == "listed":
                # SOE → Listed: SOE keys are source, Listed values are target
                source_names = set(row_mapping.keys())
                target_names = set(row_mapping.values())
            else:
                # Listed → SOE: reverse
                source_names = set(row_mapping.values())
                target_names = set(row_mapping.keys())

            # Items in source that map to target = preserved
            # Items in target not in source mapping = added (new rows in target)
            # Items in source not mapping to target = removed
            for src_name in source_names:
                if current_type == "soe":
                    mapped_target = row_mapping.get(src_name)
                else:
                    # Reverse lookup
                    reverse = _build_reverse_mapping({report_type: row_mapping})
                    mapped_target = reverse.get(report_type, {}).get(src_name)

                if mapped_target:
                    preserved += 1
                else:
                    removed_items.append(f"[{report_type}] {src_name}")

            # Count target-only items (those not reachable from source)
            if current_type == "soe":
                mapped_targets = set(row_mapping.values())
                # All target names are mapped from source in this preset
                # "Added" = target names that don't have a source mapping
                # In our preset, every listed name has a soe source, so added=0
                # But some SOE-specific rows (△/▲) map to generic listed rows
                pass
            else:
                mapped_targets = set(row_mapping.keys())

        # Simplified: count unique source rows that have a mapping vs those that don't
        # The preset maps every SOE row to a Listed row, so:
        # SOE→Listed: all SOE rows map, preserved = len(all mapped), removed = SOE-only (△/▲ rows)
        # Listed→SOE: all Listed rows have a reverse mapping

        # Recalculate with simpler logic
        added_items = []
        removed_items = []
        preserved = 0

        for report_type, row_mapping in mapping_data.items():
            if not row_mapping:
                continue
            if current_type == "soe" and target_type == "listed":
                # Every SOE row maps to a Listed row
                preserved += len(row_mapping)
                # SOE-specific rows (△/▲) that map to different Listed rows
                # are "preserved with rename", not removed
            else:
                # Listed → SOE: reverse mapping
                reverse_map = {v: k for k, v in row_mapping.items()}
                preserved += len(reverse_map)

        return ConversionPreview(
            added=len(added_items),
            removed=len(removed_items),
            preserved=preserved,
            added_items=added_items,
            removed_items=removed_items,
        )

    async def preview_note_conversion(
        self,
        project_id: UUID,
        year: int,
        target_type: str,
    ) -> dict[str, Any]:
        """附注章节转换预览 —— 与真实执行**同一条路径**，写入全部回滚。

        spec: soe-listed-note-conversion-correctness / Requirements 9.1, 9.2

        ------------------------------------------------------------------
        为什么走 savepoint + 显式 rollback，而不另写一份「只读版映射逻辑」
        ------------------------------------------------------------------

        另写只读版必然造**第二份真源**：章节配对判据（别名桥接 / 禁止对 /
        sid 回填 / 章节号占用 / 目标 sid 占用）共 8 个分支，只读版与写入版
        任何一处漂移都表现为「预览说会改 N 个、实际改了 M 个」，而两边各自
        的单测都是绿的。故预览**直接调** :meth:`_map_disclosure_notes`，真实
        产生写入后由 savepoint 整体回滚 ⇒ 预览计数与真实执行计数由**构造**
        保证相等（Property 31 的判据即此）。

        🔴 ``begin_nested()`` 的 savepoint 在 ``__aexit__`` 时若未回滚会
        **RELEASE**（= 写入生效）⇒ 必须显式 ``await sp.rollback()``。异常路径
        由 ``__aexit__`` 自行回滚，两条路径都不会留下写入。

        Requirement 9.2「预览不产生任何写入」由三层保证：
        1. savepoint 显式回滚（DB 层）——``db.add()`` 的新建对象与全部 UPDATE 一并撤销；
        2. 回滚后 SQLAlchemy 会把脏对象置为 expired、把新增对象逐出 session
           ⇒ 后续 flush 不会把内存里的改动再写回去；
        3. 本方法**不 commit**，并在回滚后核验 session 无残留待写对象，有残留即
           记 ERROR 并整体回滚（防将来有人在映射函数里绕过 savepoint 写库）。

        本方法**不碰** ``project.template_type`` / ``report_scope`` /
        ``applicable_standard_v2``（Requirement 10.6）—— 改它们会触发
        ``execute_full_chain(force=True)`` 全链重算，属破坏性操作。

        Returns:
            ``{"status", "from_type", "to_type", "mapped", "archived", "created",
               "user_edits_preserved", "forbidden_hits": list[str],
               "details": {...}}``
        """
        if target_type not in ("soe", "listed"):
            raise ValueError("target_type must be 'soe' or 'listed'")

        project = await self._get_project(project_id)
        current_type = project.template_type or "soe"

        if current_type == target_type:
            # 同类型 = 无变更。**仍走同一个映射函数**（它对同类型在任何 DB 访问之前
            # 就 early-return 零值结果）⇒ 无需 savepoint，也不必在此另抄一份零值
            # 键集（抄一份就是第二份真源，映射函数加键时必漂移）。
            return self._build_note_preview_payload(
                current_type,
                target_type,
                await self._map_disclosure_notes(project_id, year, current_type, target_type),
                status="no_change",
            )

        async with self.db.begin_nested() as sp:
            detail = await self._map_disclosure_notes(
                project_id, year, current_type, target_type
            )
            # 🔴 显式回滚（不可省）—— 见上方 docstring
            await sp.rollback()

        # 第 3 层零写入核验：savepoint 回滚后 session 不该再有待写对象
        leftover = len(self.db.new) + len(self.db.dirty) + len(self.db.deleted)
        if leftover:
            logger.error(
                "note_conversion preview: savepoint 回滚后仍有 %d 个待写对象"
                "（project=%s year=%s %s→%s）—— 违反 Requirement 9.2，已整体回滚",
                leftover, project_id, year, current_type, target_type,
            )
            await self.db.rollback()

        return self._build_note_preview_payload(current_type, target_type, detail)

    @staticmethod
    def _format_forbidden_hit(hit: dict[str, Any]) -> str:
        """禁止匹配对的一行人类可读展示（供预览响应的 ``forbidden_hits``）。"""
        return (
            f"[故意不配对] {hit.get('source_side')}「{hit.get('source_title')}」"
            f"({hit.get('source_section_id')}) 与 "
            f"{hit.get('target_side')}「{hit.get('target_title')}」"
            f"({hit.get('target_section_id')})"
        )

    @classmethod
    def _build_note_preview_payload(
        cls,
        current_type: str,
        target_type: str,
        detail: dict[str, Any],
        *,
        status: str = "preview",
    ) -> dict[str, Any]:
        """把 `_map_disclosure_notes` 的返回结构投影成预览响应（Requirement 9.1）。

        六个顶层键按 design 的端点契约；``details`` 承载可追溯明细
        （``skipped`` / ``failed`` / ``skipped_reasons`` / 别名桥接 / 禁止对结构化条目），
        让审计师能逐条核对「为什么这一章没被改写」。
        """
        skipped = detail.get("skipped") or []
        failed = detail.get("failed") or []
        forbidden = detail.get("forbidden_hits") or []
        return {
            "status": status,
            "from_type": current_type,
            "to_type": target_type,
            # ---- design 端点契约的六个键 ----
            "mapped": int(detail.get("mapped") or 0),
            "archived": int(detail.get("archived") or 0),
            "created": int(detail.get("created") or 0),
            "user_edits_preserved": int(detail.get("user_edits_preserved") or 0),
            "forbidden_hits": [cls._format_forbidden_hit(h) for h in forbidden],
            "details": {
                "format_adapted": int(detail.get("format_adapted") or 0),
                "binding_ids_rewritten": int(detail.get("binding_ids_rewritten") or 0),
                "sid_backfilled": int(detail.get("sid_backfilled") or 0),
                "sid_backfill_conflicts": int(detail.get("sid_backfill_conflicts") or 0),
                # 三态纪律：user_edits_dropped 非 0 即平台红线被破坏（manual 单元格丢失）
                "user_edits_dropped": int(detail.get("user_edits_dropped") or 0),
                "skipped_count": len(skipped),
                "skipped_reasons": detail.get("skipped_reasons") or {},
                "skipped": skipped,
                "failed_count": len(failed),
                "failed": failed,
                "bridged_by_alias": detail.get("bridged_by_alias") or [],
                "forbidden_pairs": forbidden,
                "pending_keys": detail.get("pending_keys") or [],
            },
        }

    async def execute_conversion(
        self,
        project_id: UUID,
        year: int,
        target_type: str,
    ) -> dict[str, Any]:
        """Execute the conversion from current type to target_type.

        Steps:
        1. Snapshot current state
        2. Update project.template_type
        3. Map report_line_mappings row_codes
        4. Map disclosure_notes section_codes
        5. Update formula references
        6. Trigger full chain refresh

        Requirements: 47.2, 47.3, 47.5, 47.6
        """
        if target_type not in ("soe", "listed"):
            raise ValueError("target_type must be 'soe' or 'listed'")

        project = await self._get_project(project_id)
        current_type = project.template_type or "soe"

        if current_type == target_type:
            return {"status": "no_change", "message": "Already using target type"}

        # Step 1: Snapshot current state（含逐章节可回退字段，Requirement 9.3）
        snapshot = await self._create_snapshot(
            project_id, year, current_type, target_type
        )

        try:
            # Step 2: Update project.template_type
            await self.db.execute(
                sa.update(Project)
                .where(Project.id == project_id)
                .values(template_type=target_type)
            )

            # Step 3: Map report_line_mappings row_codes (via row_name matching)
            mapped_rows = await self._map_report_rows(
                project_id, year, current_type, target_type
            )

            # Step 4: 章节映射 —— 真实改写 section_id + note_section（Requirements 2.1/4.1）
            notes_detail = await self._map_disclosure_notes(
                project_id, year, current_type, target_type
            )
            mapped_notes = notes_detail["mapped"]

            # Step 5: Update formula references
            updated_formulas, formula_reason = await self._update_formula_references(
                project_id, year, current_type, target_type
            )

            # 正向结果摘要写回快照行的 ``steps``（既有 JSONB 列，无迁移）。
            # 回滚据 ``format_adapted`` 判断「本次转换有没有做过不可逆的格式适配」
            # 并如实降级 status —— 快照本身在 Step 1 就落盘了，那时还不知道这些数。
            await self._record_forward_summary(
                snapshot.get("snapshot_id"), current_type, target_type, notes_detail
            )

            await self.db.flush()

            # Step 6: Trigger full chain refresh
            refresh_result = await self._trigger_chain_refresh(project_id, year)

            await self.db.commit()
        except Exception as exc:
            # Requirement 9.4 的姊妹面：自动触发路径失败时必须留下可追溯线索。
            # 🔴 如实说明快照的处境 —— 此处尚未 commit，故**连快照行本身**都会随
            # 事务回滚一起消失；「没有快照可回滚」在这里恰恰等价于「DB 未被改动」，
            # 不是遗漏。把 snapshot_id 挂到异常上供上层（事件 handler）一并记日志。
            logger.error(
                "note_conversion: 转换失败 project=%s year=%s %s→%s "
                "snapshot_id=%s（尚未提交 ⇒ 事务回滚后快照行不保留，DB 保持转换前状态）: %s",
                project_id, year, current_type, target_type,
                snapshot.get("snapshot_id"), exc,
            )
            setattr(exc, "conversion_snapshot_id", snapshot.get("snapshot_id"))
            setattr(exc, "conversion_committed", False)
            raise

        # Requirement 4.3：failed 非空时调用方必须收到明确提示
        warnings: list[str] = []
        if notes_detail["failed"]:
            warnings.append(
                f"{len(notes_detail['failed'])} 个附注章节映射失败，其余 {mapped_notes} 个已改写；"
                f"可用快照 {snapshot.get('snapshot_id')} 回退"
            )
        if notes_detail.get("skipped_reasons"):
            warnings.append(f"附注章节跳过分布：{notes_detail['skipped_reasons']}")
        # Requirement 2.5 是平台红线：manual 单元格丢失必须让调用方看到，不能只留日志
        if notes_detail.get("user_edits_dropped"):
            warnings.append(
                f"{notes_detail['user_edits_dropped']} 个人工编辑单元格在章节改写中丢失；"
                f"可用快照 {snapshot.get('snapshot_id')} 回退"
            )

        return {
            "status": "completed",
            "from_type": current_type,
            "to_type": target_type,
            "snapshot_id": snapshot.get("snapshot_id"),
            "snapshot_at": snapshot.get("snapshot_at"),
            "mapped_rows": mapped_rows,
            # Requirement 4.4：mapped_rows == 0 的原因码（no_mapping_needed ≠ not_implemented）
            "mapped_rows_reason": self.report_row_mapping_reason(),
            # Requirement 4.1：实际改写的章节数（改造前是存量 count(*) 冒充）
            "mapped_notes": mapped_notes,
            # Requirement 4.2：mapped / archived / created / skipped / failed 五类齐备，
            # 全部为**实际发生数**（Task 9 收口后不再有 None = 未测量的项）
            "notes_detail": notes_detail,
            "archived_notes": notes_detail["archived"],
            "created_notes": notes_detail["created"],
            "notes_failed": len(notes_detail["failed"]),
            "notes_skipped": len(notes_detail["skipped"]),
            "updated_formulas": updated_formulas,
            # Requirement 4.4：0 值必须可区分「无可改写对象」与「未实现」
            "updated_formulas_reason": formula_reason,
            "refresh_triggered": refresh_result,
            "warnings": warnings,
        }

    async def rollback_conversion(
        self,
        project_id: UUID,
        year: int,
    ) -> dict[str, Any]:
        """撤销最近一次转换 —— ``template_type`` **与章节标识**一并回退。

        Requirements: 47.5；spec soe-listed-note-conversion-correctness /
        Requirement 9.3（Property 32）

        ------------------------------------------------------------------
        改造前只回退 ``template_type`` = 假成功
        ------------------------------------------------------------------

        Step 4 改的是 ``disclosure_notes`` 的 ``section_id`` / ``note_section`` /
        ``is_deleted`` / ``template_lineage`` 以及 ``table_data`` 里的
        ``binding_id`` 前缀，而旧实现只把 ``project.template_type`` 改回去 ⇒
        附注章节标识仍留在目标变体上。两份模板有 20 个章节号重合且 13 个标题不同
        ⇒ 「回滚成功」之后数据仍停在错误的章节位置。

        现在章节字段由 :meth:`_rollback_section_state` 逐项回退，并以
        ``status`` 区分两态：

        * ``rolled_back`` —— 五项字段全部回到快照状态；
        * ``partial`` —— 有章节未能回退（旧格式快照 / 新建空章节已有内容 /
          章节号被占 / 正向做过不可逆的格式适配），``sections`` 与 ``warnings``
          里逐条说明**哪些字段没能回退**。

        绝不返回「成功」而实际没回退干净（fail-closed）。
        """
        # Find the most recent snapshot for this project/year
        from app.models.chain_execution import ChainExecution

        result = await self.db.execute(
            sa.select(ChainExecution)
            .where(
                ChainExecution.project_id == project_id,
                ChainExecution.year == year,
                ChainExecution.trigger_type == "conversion_snapshot",
            )
            .order_by(ChainExecution.created_at.desc())
            .limit(1)
        )
        execution = result.scalar_one_or_none()

        if not execution:
            return {"status": "error", "message": "No conversion snapshot found"}

        # Check retention period
        snapshot_at = execution.started_at
        if snapshot_at and (datetime.now(timezone.utc) - snapshot_at) > timedelta(days=self.SNAPSHOT_RETENTION_DAYS):
            return {"status": "error", "message": "Snapshot expired (>30 days)"}

        snapshot_data = execution.snapshot_before
        if not snapshot_data:
            return {"status": "error", "message": "Snapshot data is empty"}

        # Restore project.template_type
        original_type = snapshot_data.get("template_type")
        if original_type:
            await self.db.execute(
                sa.update(Project)
                .where(Project.id == project_id)
                .values(template_type=original_type)
            )

        # 章节状态回退（Requirement 9.3）—— section_id / note_section /
        # binding_id 前缀 / 归档状态 / template_lineage
        forward = (execution.steps or {}).get("conversion_forward") or {}
        sections = await self._rollback_section_state(
            project_id, year, snapshot_data, forward
        )

        await self.db.flush()

        # Trigger full chain refresh to regenerate with restored type
        refresh_result = await self._trigger_chain_refresh(project_id, year)

        await self.db.commit()

        status = "rolled_back" if sections["complete"] else "partial"
        return {
            "status": status,
            "restored_type": original_type,
            "refresh_triggered": refresh_result,
            "snapshot_id": str(execution.id),
            "snapshot_version": int(snapshot_data.get("snapshot_version") or 1),
            # Requirement 9.3：章节字段的逐项回退结果（禁静默假成功）
            "sections": sections,
            "unrestored_fields": list(ROLLBACK_UNRESTORED_FIELDS),
            "warnings": sections["warnings"],
        }

    # ------------------------------------------------------------------
    # 章节状态回退（spec Task 16 / Requirement 9.3）
    # ------------------------------------------------------------------

    async def _rollback_section_state(
        self,
        project_id: UUID,
        year: int,
        snapshot_data: dict[str, Any],
        forward: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """把 ``disclosure_notes`` 的章节标识逐项回退到快照状态。

        spec: soe-listed-note-conversion-correctness / Requirement 9.3（Property 32）

        ------------------------------------------------------------------
        回退哪五项（判据 = Task 17 的逐字段比对）
        ------------------------------------------------------------------

        ==========================  ============================================
        ``section_id``              取快照原值（含把回填出来的 sid 退回 ``None``）
        ``note_section``            取快照原值（章节号）
        ``is_deleted``              归档章节退回 ``False``
        ``template_lineage``        **整体**取快照原值（含 ``legacy_section_ids`` /
                                    ``legacy_note_sections`` / ``archived_sections`` /
                                    ``conversions`` / ``created_by_conversion`` /
                                    ``section_id_backfilled_from`` / ``alias_source_title``
                                    全部随之消失）
        ``binding_id`` 前缀         逆向调 :func:`_rewrite_binding_id_prefix`
                                    （正向 ``(td, old, new)`` ⇒ 逆向 ``(td, new, old)``）
        ==========================  ============================================

        ``template_lineage`` 走**整体还原**而不是「逐键删掉我们加的那些」：后者无法
        还原 ``conversions`` 这类 list 的原有元素与顺序，也无法表达「本来就是
        ``None``」；整体还原让「回到初始」可被逐字节证明。代价是会覆盖转换后其它
        流程对该列的写入 —— 该列全库实测 **0 条有值**，且回滚本身是显式撤销动作，
        故这个取舍是可接受的（已写入 :data:`ROLLBACK_UNRESTORED_FIELDS` 的邻近说明）。

        ------------------------------------------------------------------
        ``created`` 那批新建空章节怎么回退 —— 裁决 = **物理删除（仅限仍为空时）**
        ------------------------------------------------------------------

        平台惯例是「不删 tracked 数据、一律软删」，但这里**软删不成立**，两条硬理由：

        1. **软删不释放章节号。** DB 实测 ``uq_disclosure_notes_project_year_section``
           是 ``(project_id, year, note_section)`` 上的**非部分** UNIQUE 索引
           （不带 ``is_deleted`` 过滤）⇒ 软删行照样占位。而新建空章节占用的章节号
           可能正是某个被改写章节要退回去的旧章节号（实测两份模板的「源独有章节号」
           与「目标独有章节号」交集 = ``七`` / ``五`` / ``十三``）⇒ 软删会**堵死**
           那些章节的回退。
        2. **这些行不含任何审计数据。** 它们是本次转换自己 ``INSERT`` 出来的
           ``is_empty=True`` / ``status='draft'`` 空骨架，删掉是「撤销自己的插入」，
           不是「删用户数据」。且实测**无任何外键引用 ``disclosure_notes``**，
           物理删除无级联风险。

        ⇒ 判据是**内容**而非来源：仅当该章节仍为空（``is_empty`` 且无
        ``table_data`` 且无 ``text_content``）才物理删除；若转换后审计师已在里面
        录入内容，则**保留不动**并计入 ``skipped``（原因码
        :data:`ROLLBACK_SKIP_CREATED_HAS_CONTENT`），此时「不残留多余章节」这条
        不成立，如实降级 ``status='partial'``。

        ------------------------------------------------------------------
        章节号为什么要「可行槽位迭代」而不是直接赋值
        ------------------------------------------------------------------

        章节号有唯一约束，而回退是一次**置换**：A 要退回 X，X 此刻可能被 B 占着，
        B 又要退回 Y……直接按任意顺序赋值会撞 IntegrityError。故按「反复扫一遍，
        谁的目标槽位现在空着就先给谁」推进（经典的置换原地重排），直到没有进展。

        🔴 **不会死锁**（这是正向路径给的结构性保证）：正向改写本身也是带占用表的
        顺序赋值 —— 若 A 想写的章节号当时被 B 占着，A 会进 ``skipped``
        （:data:`SKIP_REASON_TARGET_NUMBER_OCCUPIED`）而**不会**进 ``mapped``。
        故成功改写的集合里不可能存在互相占位的环，逆向必能逐个化解。真出现剩余
        （模板漂移 / 转换后有人手工改过章节号）就如实进 ``failed``
        （:data:`ROLLBACK_FAIL_NUMBER_BLOCKED`）**并整章不动**，绝不部分回退到
        「``section_id`` 退了、``note_section`` 没退」这种半成品状态。

        ------------------------------------------------------------------
        旧格式快照 = fail-closed
        ------------------------------------------------------------------

        ``snapshot_version`` 缺失/为 1（只有 ``template_type``）⇒ 一行都不改，
        返回 ``complete=False`` + 明确说明「该快照不含章节映射信息，无法回退
        ``section_id`` / ``note_section`` / 归档状态」，由调用方把 ``status``
        降级为 ``partial``。**禁静默假成功**。

        Note:
            替身 session 需支持 ``delete()``（撤销新建空章节）且章节查询要能返回
            **软删记录**（回退归档）—— 生产 ``AsyncSession`` 两者都有，内存替身
            按需扩展。

        Returns:
            ``{"complete": bool, "restored", "unarchived", "created_removed",
               "binding_ids_reverted", "skipped": [...], "failed": [...],
               "warnings": [...], ...}``
        """
        from app.models.report_models import DisclosureNote

        forward = forward or {}
        detail: dict[str, Any] = {
            "complete": True,
            # 逐字段回退成功的章节数（含归档复原）
            "restored": 0,
            # 其中「``is_deleted`` 由 True 退回 False」的条数 = 归档被撤销数
            "unarchived": 0,
            # 物理删除的「本次转换新建空章节」数
            "created_removed": 0,
            # binding_id 前缀被逆向改写的条数
            "binding_ids_reverted": 0,
            # 库中存在但不在快照里、也不是本次转换新建的章节（别的流程建的）⇒ 不动
            "foreign_notes": 0,
            "skipped": [],
            "failed": [],
            "warnings": [],
        }

        version = int(snapshot_data.get("snapshot_version") or 1)
        snap_notes = snapshot_data.get("notes")
        if version < SNAPSHOT_FORMAT_VERSION or not isinstance(snap_notes, list):
            # fail-closed：结构上无法回退，如实报告而不是静默返回成功
            detail["complete"] = False
            detail["reason"] = ROLLBACK_REASON_LEGACY_SNAPSHOT
            detail["warnings"].append(
                "该快照为旧格式（不含章节映射信息），无法回退 section_id / "
                "note_section / 归档状态 / template_lineage；已仅回退 template_type。"
            )
            logger.error(
                "note_conversion rollback: project=%s year=%s 快照为旧格式"
                "（snapshot_version=%s）⇒ 章节字段无法回退",
                project_id, year, version,
            )
            return detail

        snap_by_id: dict[str, dict[str, Any]] = {
            str(s.get("note_id")): s for s in snap_notes if isinstance(s, dict) and s.get("note_id")
        }
        direction = snapshot_data.get("direction")

        # 🔴 不过滤 is_deleted：归档章节要复原，新建空章节要识别
        notes_result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
            )
        )
        notes = list(notes_result.scalars().all())

        # ------------------------------------------------------------------
        # Pass 0：撤销「本次转换新建的空章节」（必须最先，它们占着章节号）
        # ------------------------------------------------------------------
        survivors: list[Any] = []
        for note in notes:
            if str(note.id) in snap_by_id:
                survivors.append(note)
                continue
            lineage = note.template_lineage if isinstance(note.template_lineage, dict) else {}
            created_by = lineage.get("created_by_conversion")
            if not created_by or (direction and created_by != direction):
                # 不是本次转换建的 ⇒ 与本次回滚无关，一律不动
                detail["foreign_notes"] += 1
                survivors.append(note)
                continue
            if not self._created_section_is_untouched(note):
                # 转换后已被录入内容 ⇒ 保留（删它就是删审计师的数据）
                detail["skipped"].append({
                    "note_id": str(note.id),
                    "section_id": note.section_id,
                    "note_section": note.note_section,
                    "reason": ROLLBACK_SKIP_CREATED_HAS_CONTENT,
                    "detail": "转换新建的空章节已有内容，保留不删",
                })
                detail["complete"] = False
                survivors.append(note)
                continue
            try:
                async with self.db.begin_nested():
                    await self.db.delete(note)
                    await self.db.flush()
                detail["created_removed"] += 1
            except Exception as exc:  # noqa: BLE001 — 逐章节隔离
                logger.warning(
                    "note_conversion rollback: 删除新建空章节失败 project=%s note=%s: %s",
                    project_id, note.id, exc,
                )
                detail["failed"].append({
                    "note_id": str(note.id),
                    "section_id": note.section_id,
                    "note_section": note.note_section,
                    "phase": "remove_created_section",
                    "error": str(exc),
                })
                detail["complete"] = False
                survivors.append(note)

        # ------------------------------------------------------------------
        # Pass 1/2：逐章节回退四个列（+ binding_id 前缀）
        # ------------------------------------------------------------------
        # 章节号占用表 —— 同样**不排除软删行**（非部分唯一索引）
        occupied: dict[str, str] = {
            n.note_section: str(n.id) for n in survivors if n.note_section
        }

        pending: list[tuple[Any, dict[str, Any]]] = []
        for note in survivors:
            snap = snap_by_id.get(str(note.id))
            if snap is None:
                continue
            target_number = snap.get("note_section")
            if note.note_section == target_number:
                # 章节号无需变动 ⇒ 直接回退其余字段
                await self._restore_note_from_snapshot(note, snap, detail)
            else:
                pending.append((note, snap))

        # 快照里有、库里已不存在的章节（被别的流程物理删除）⇒ 无从回退，如实登记
        live_ids = {str(n.id) for n in survivors}
        for note_id, snap in snap_by_id.items():
            if note_id not in live_ids:
                detail["skipped"].append({
                    "note_id": note_id,
                    "section_id": snap.get("section_id"),
                    "note_section": snap.get("note_section"),
                    "reason": ROLLBACK_SKIP_NOTE_MISSING,
                    "detail": "快照中的章节在库中已不存在，无法回退",
                })
                detail["complete"] = False

        # 可行槽位迭代：谁的目标章节号此刻空着就先回退谁（化解置换链）
        while pending:
            progressed = False
            remaining: list[tuple[Any, dict[str, Any]]] = []
            for note, snap in pending:
                target_number = snap.get("note_section")
                holder = occupied.get(target_number) if target_number else None
                if target_number and holder is not None and holder != str(note.id):
                    remaining.append((note, snap))
                    continue
                # 回退**前**记下它当前占的章节号 —— 成功后 note.note_section 已是
                # 目标值，届时反查会拿错键
                prev_number = note.note_section
                ok = await self._restore_note_from_snapshot(note, snap, detail)
                if ok:
                    if prev_number and occupied.get(prev_number) == str(note.id):
                        occupied.pop(prev_number, None)
                    if target_number:
                        occupied[target_number] = str(note.id)
                progressed = True
            pending = remaining
            if not progressed:
                break

        # 剩余 = 目标章节号被本次回滚无权移动的记录占着 ⇒ 整章不动，如实报告
        for note, snap in pending:
            target_number = snap.get("note_section")
            detail["failed"].append({
                "note_id": str(note.id),
                "section_id": note.section_id,
                "note_section": note.note_section,
                "phase": "restore_note_section",
                "error": ROLLBACK_FAIL_NUMBER_BLOCKED,
                "detail": (
                    f"目标章节号 {target_number} 被 note "
                    f"{occupied.get(target_number)} 占用且不属本次回滚范围；"
                    "该章节整体未回退（不做半成品回退）"
                ),
            })
            detail["complete"] = False

        # ------------------------------------------------------------------
        # 不可逆项如实上报（正向格式适配改过 table_data 列结构）
        # ------------------------------------------------------------------
        format_adapted = int(forward.get("format_adapted") or 0)
        if format_adapted:
            detail["format_adapted_not_reversible"] = format_adapted
            detail["complete"] = False
            detail["warnings"].append(
                f"正向转换对 {format_adapted} 个章节做过格式适配（改列结构），"
                "该变换不可逆，table_data 的列结构未回退"
            )

        if detail["failed"]:
            detail["complete"] = False
            logger.error(
                "note_conversion rollback: project=%s year=%s 有 %d 个章节回退失败"
                "（成功 %d 个）: %s",
                project_id, year, len(detail["failed"]), detail["restored"],
                [f.get("section_id") for f in detail["failed"][:10]],
            )
        if detail["skipped"]:
            reasons: dict[str, int] = {}
            for item in detail["skipped"]:
                reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
            detail["skipped_reasons"] = reasons
            detail["warnings"].append(f"章节回退跳过分布：{reasons}")
        logger.info(
            "note_conversion rollback: project=%s year=%s 章节回退汇总 —— "
            "复原 %d / 撤销归档 %d / 删除新建空章节 %d / binding_id 逆向改写 %d / "
            "跳过 %d / 失败 %d（complete=%s）",
            project_id, year, detail["restored"], detail["unarchived"],
            detail["created_removed"], detail["binding_ids_reverted"],
            len(detail["skipped"]), len(detail["failed"]), detail["complete"],
        )
        return detail

    @staticmethod
    def _created_section_is_untouched(note: Any) -> bool:
        """「转换新建的空章节」是否**仍然为空**（可安全物理删除的判据）。

        判据取**内容**而非来源：三项都为空才算未被触碰。``is_empty`` 单独不够 ——
        它是新建时写死的标记，审计师录入后未必有人把它翻成 ``False``。
        """
        table_data = note.table_data
        if isinstance(table_data, dict) and table_data:
            return False
        if isinstance(table_data, list) and table_data:
            return False
        if (note.text_content or "").strip():
            return False
        return True

    async def _restore_note_from_snapshot(
        self,
        note: Any,
        snap: dict[str, Any],
        detail: dict[str, Any],
    ) -> bool:
        """把单个章节的四个列 + ``binding_id`` 前缀回退到快照状态。

        spec: soe-listed-note-conversion-correctness / Requirement 9.3

        逐章节 ``begin_nested()`` savepoint —— 一章回退失败不该让整次回滚白做
        （与正向映射同款隔离，Requirement 4.3 的同一纪律）。失败时该章节的改动
        由 savepoint 整体回滚，**不留半成品**。

        Returns:
            是否成功。失败已记入 ``detail["failed"]``。
        """
        target_number = snap.get("note_section")
        target_sid = snap.get("section_id")
        target_deleted = bool(snap.get("is_deleted"))
        target_lineage = snap.get("template_lineage")
        was_deleted = bool(note.is_deleted)
        old_number = note.note_section
        try:
            async with self.db.begin_nested():
                # binding_id 前缀逆向改写（正向 (td, old, new) ⇒ 逆向 (td, new, old)）。
                # 必须深拷贝后整体赋值：JSONB 未声明 MutableDict，就地改嵌套不标脏。
                if (
                    target_number
                    and old_number
                    and target_number != old_number
                    and isinstance(note.table_data, dict)
                ):
                    new_td = deepcopy(note.table_data)
                    reverted = _rewrite_binding_id_prefix(
                        new_td, old_number, target_number
                    )
                    if reverted:
                        note.table_data = new_td
                        detail["binding_ids_reverted"] += reverted

                if target_number:
                    note.note_section = target_number
                note.section_id = target_sid
                note.is_deleted = target_deleted
                # 🔴 整体还原（含 None）—— 逐键删「我们加的那些」无法还原
                # ``conversions`` 这类 list 的原有元素与顺序，也表达不了「本来是 None」
                note.template_lineage = (
                    deepcopy(target_lineage) if isinstance(target_lineage, dict) else None
                )
                await self.db.flush()
            detail["restored"] += 1
            if was_deleted and not target_deleted:
                detail["unarchived"] += 1
            return True
        except Exception as exc:  # noqa: BLE001 — 逐章节隔离，失败不阻断其余
            logger.warning(
                "note_conversion rollback: 章节回退失败 project=%s note=%s "
                "%s→%s: %s",
                note.project_id, note.id, old_number, target_number, exc,
            )
            detail["failed"].append({
                "note_id": str(note.id),
                "section_id": note.section_id,
                "note_section": note.note_section,
                "phase": "restore_note",
                "error": str(exc),
            })
            detail["complete"] = False
            return False

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    async def _get_project(self, project_id: UUID) -> Project:
        """Get project or raise 404."""
        result = await self.db.execute(
            sa.select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        return project

    async def _create_snapshot(
        self,
        project_id: UUID,
        year: int,
        current_type: str,
        target_type: str | None = None,
    ) -> dict[str, Any]:
        """转换前快照 —— 含**逐章节**的可回退字段（Requirement 9.3）。

        spec: soe-listed-note-conversion-correctness / Requirement 9.3（Property 32）

        落 ``chain_executions.snapshot_before``（JSONB，既有列）+
        ``trigger_type='conversion_snapshot'``。**本 spec 无 DB 迁移** ⇒ 扩充的
        内容全部放进这个既有 JSONB 列，不新增列。

        ------------------------------------------------------------------
        为什么必须扩快照（改造前的结构性缺陷）
        ------------------------------------------------------------------

        旧格式只存 ``template_type`` / ``year`` / ``converted_at`` ⇒
        :meth:`rollback_conversion` **结构上不可能**还原 ``section_id`` /
        ``note_section`` / 归档状态（``is_deleted``）/ ``template_lineage``，
        而 Step 4 恰恰改的就是这四个列。所以旧快照下的「回滚成功」是假成功：
        ``template_type`` 退回去了，附注章节标识还留在目标变体上 —— 两份模板有
        20 个章节号重合且 13 个标题不同，等于把数据留在错误的章节位置上。

        ------------------------------------------------------------------
        快照范围
        ------------------------------------------------------------------

        * **不过滤 ``is_deleted``** —— 归档走软删，回滚要把它们 ``is_deleted``
          置回 ``False``；只查未删除行则归档章节在快照里根本不存在。
        * 逐章节只存四个列（见 :func:`snapshot_note_state`），实测最大项目
          327 章节 ≈ 50 KB，远小于连 ``table_data`` 一起存的 1.4 MB，且避免了
          「用 30 天前的 table_data 覆盖掉这期间的正常录入」这一数据销毁风险。

        Args:
            current_type: 转换**前**的 ``template_type``。
            target_type: 转换**后**的 ``template_type``。用于推导
                ``direction``（= ``created_by_conversion`` 的取值），回滚据它
                识别「哪些章节是本次转换新建的」。``None`` 时 ``direction``
                亦为 ``None``，回滚退化为按「不在快照里 + lineage 有
                ``created_by_conversion``」识别（宽一档但仍安全）。

        Returns:
            ``{"snapshot_id", "snapshot_at", "notes_count"}``。
        """
        from app.models.chain_execution import ChainExecution
        from app.models.report_models import DisclosureNote

        # 🔴 不过滤 is_deleted：归档章节必须进快照才能被回滚复原
        notes_result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
            )
        )
        note_states = [snapshot_note_state(n) for n in notes_result.scalars().all()]

        snapshot_data: dict[str, Any] = {
            "snapshot_version": SNAPSHOT_FORMAT_VERSION,
            "template_type": current_type,
            "target_type": target_type,
            "direction": (
                f"{current_type}_to_{target_type}" if target_type else None
            ),
            "year": year,
            "converted_at": datetime.now(timezone.utc).isoformat(),
            "notes_count": len(note_states),
            "notes": note_states,
        }

        execution = ChainExecution(
            project_id=project_id,
            year=year,
            status="completed",
            steps={"conversion_snapshot": {"status": "completed"}},
            trigger_type="conversion_snapshot",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            snapshot_before=snapshot_data,
        )
        self.db.add(execution)
        await self.db.flush()

        return {
            "snapshot_id": str(execution.id),
            "snapshot_at": execution.started_at.isoformat() if execution.started_at else None,
            "notes_count": len(note_states),
        }

    async def _record_forward_summary(
        self,
        snapshot_id: str | None,
        current_type: str,
        target_type: str,
        notes_detail: dict[str, Any],
    ) -> None:
        """把正向章节映射的结果摘要写回快照行的 ``steps``（既有 JSONB 列）。

        spec: soe-listed-note-conversion-correctness / Requirement 9.3

        为什么不写进 ``snapshot_before``：那一列的语义是「转换**前**的状态」，
        往里塞转换后的产出会让「快照」二字含义漂移；``steps`` 本就是记录本次
        执行做了什么的地方。

        回滚只用其中一项做判断 —— ``format_adapted``：它 > 0 意味着正向改过
        ``table_data`` 的列结构（不可逆，见 :data:`ROLLBACK_UNRESTORED_FIELDS`），
        回滚必须把 ``status`` 降级为 ``partial`` 并如实说明。

        全程 fail-open：这是**诊断信息**，写不进去不该让已经成功的转换失败
        （回滚届时读不到该键，按「未知」处理，仍然不会假称完全可逆）。
        """
        if not snapshot_id:
            return
        from app.models.chain_execution import ChainExecution

        try:
            await self.db.execute(
                sa.update(ChainExecution)
                .where(ChainExecution.id == UUID(str(snapshot_id)))
                .values(
                    steps={
                        "conversion_snapshot": {"status": "completed"},
                        "conversion_forward": {
                            "direction": f"{current_type}_to_{target_type}",
                            "mapped": int(notes_detail.get("mapped") or 0),
                            "archived": int(notes_detail.get("archived") or 0),
                            "created": int(notes_detail.get("created") or 0),
                            "format_adapted": int(notes_detail.get("format_adapted") or 0),
                            "binding_ids_rewritten": int(
                                notes_detail.get("binding_ids_rewritten") or 0
                            ),
                            "recorded_at": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                )
            )
        except Exception as exc:  # noqa: BLE001 — 诊断信息，失败不阻断转换
            logger.warning(
                "note_conversion: 正向摘要写回快照 %s 失败（不影响转换）: %s",
                snapshot_id, exc,
            )

    async def _map_report_rows(
        self,
        project_id: UUID,
        year: int,
        current_type: str,
        target_type: str,
    ) -> int:
        """报表行 row_code 映射 —— 实证结论：**无可改写对象**。

        spec: soe-listed-note-conversion-correctness / Requirements 3.4, 4.4

        2026-08-06 ``report_config`` 全表实证（四变体 1222 行）：

        - 该表**无 ``project_id`` 列** —— 它是纯模板表，按 ``applicable_standard``
          分行存储。切换 ``project.template_type`` 后，报表生成自然读另一套
          配置行，不存在「项目级 row_code 需要就地改写」这回事。
        - 报表数值落在 ``financial_report``，由 Step 6 的全链重算按目标准则
          的配置行重新生成。

        故本步返回 0 是**实证结论**（原因码
        :data:`~app.services.note_conversion_row_codes.FORMULA_REWRITE_REASON`），
        不是「未实现」。跨变体 row_code 差异清单见
        ``app/services/note_conversion_row_codes.py``（12 条同义两码），它服务于
        **公式引用改写**（``_update_formula_references``），与本步无关。

        Returns:
            实际改写的报表行数（当前恒 0；原因码由
            :meth:`_update_formula_references` 一并上报，取值
            ``no_mapping_needed``）。
        """
        # 无写入：report_config 是按 applicable_standard 分行的模板表，
        # 切 template_type 即切配置行；数值由 Step 6 全链重算重新生成。
        return 0

    @staticmethod
    def formula_rewrite_reason() -> str:
        """``updated_formulas == 0`` 的原因码（Requirement 4.4）。

        ``no_mapping_needed`` = 已按 12 条同义两码清单扫描过、确认库内无可改写
        对象（实证结论）；与 ``not_implemented``（功能没做）必须可区分。
        实证依据见 :meth:`_update_formula_references` 的 docstring。
        """
        from app.services.note_conversion_row_codes import FORMULA_REWRITE_REASON

        return FORMULA_REWRITE_REASON

    @staticmethod
    def report_row_mapping_reason() -> str:
        """``mapped_rows == 0`` 的原因码（Requirement 4.4）。

        与公式改写共用同一原因码常量：``no_mapping_needed`` 表示「已按实证确认
        无可改写对象」，必须与 ``not_implemented``（未实现）可区分。
        """
        from app.services.note_conversion_row_codes import FORMULA_REWRITE_REASON

        return FORMULA_REWRITE_REASON

    # ------------------------------------------------------------------
    # 章节映射（spec soe-listed-note-conversion-correctness / Wave 3 Task 8）
    # ------------------------------------------------------------------

    def _build_section_mapping_plan(
        self,
        diff_data: dict[str, Any],
        current_type: str,
        target_type: str,
    ) -> dict[str, Any]:
        """构造「源侧 sid → 目标侧 sid」映射计划（纯函数，不碰 DB）。

        spec: Requirements 2.1, 2.2, 5.1, 5.2, 5.3

        三个来源合成：

        1. ``common_sections`` —— 两侧标题精确相同的章节，按
           ``soe_section_id ↔ listed_section_id`` 直接配对；
        2. **别名桥接** —— 措辞差异（「财务报表编制基础」↔「财务报表**的**编制基础」等
           5 对已实证）会让两侧各自落进 ``*_only_sections``，若不桥接则走
           「源侧归档 + 目标侧新建空章」⇒ **丢已录数据**。桥接一律经
           :mod:`app.services.note_section_matcher` 的**穷举配对**（禁相似度：
           实证「财务报表主要项目注释」↔「母公司…」相似度 0.87 高于需要救回的
           「研究开发支出」↔「研发支出」0.80，任何阈值都无法二者兼顾）；
        3. ``format_diff_sections`` —— 与 common 同一批 sid，额外携带目标格式与
           ``field_mapping``，供 :func:`adapt_table_data_with_report` 适配结构。

        Returns:
            ``{"pairs": {src_sid: {"target_sid", "title", "via"}},
               "source_only": set[str], "target_only": {tgt_sid: entry},
               "target_sids": set[str], "format_diff": {src_sid: entry},
               "bridged": list[dict], "forbidden_hits": list[dict]}``

        ``source_only`` 与 ``target_only`` 都是**已扣除别名桥接**后的净值（桥接掉的
        章节已进 ``pairs``）—— 直接拿 diff 数据的 ``*_only_sections`` 去归档/新建会
        把那 5 对措辞差异章节做成「归档 + 新建空章」⇒ 丢已录数据。
        """
        from app.services.note_section_matcher import (
            FORBIDDEN_MATCH_PAIRS,
            match_section,
            normalize_for_match,
            resolve_alias_counterpart,
        )

        src_side = _conversion_side(current_type)
        tgt_side = _conversion_side(target_type)
        src_field = f"{src_side}_section_id"
        tgt_field = f"{tgt_side}_section_id"
        src_only_key = f"{src_side}_only_sections"
        tgt_only_key = f"{tgt_side}_only_sections"

        pairs: dict[str, dict[str, Any]] = {}
        for entry in diff_data.get("common_sections") or []:
            if not isinstance(entry, dict):
                continue
            src_sid = entry.get(src_field)
            tgt_sid = entry.get(tgt_field)
            if not src_sid or not tgt_sid:
                continue
            pairs[src_sid] = {
                "target_sid": tgt_sid,
                "title": entry.get("section_title") or "",
                "via": "common",
            }

        source_only: dict[str, dict[str, Any]] = {}
        for entry in diff_data.get(src_only_key) or []:
            if isinstance(entry, dict) and entry.get("section_id"):
                source_only[entry["section_id"]] = entry

        target_only: dict[str, dict[str, Any]] = {}
        target_only_by_title: dict[str, dict[str, Any]] = {}
        for entry in diff_data.get(tgt_only_key) or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("section_id"):
                target_only[entry["section_id"]] = entry
            key = normalize_for_match(entry.get("title"))
            if key and key not in target_only_by_title:
                target_only_by_title[key] = entry

        # 别名桥接
        bridged: list[dict[str, Any]] = []
        for src_sid, entry in list(source_only.items()):
            src_title = entry.get("title") or ""
            counterpart = resolve_alias_counterpart(src_title, tgt_side)
            if not counterpart:
                continue
            tgt_entry = target_only_by_title.get(normalize_for_match(counterpart))
            if not tgt_entry or not tgt_entry.get("section_id"):
                continue
            # 双重保险：再过一次 match_section（禁止对优先于一切）
            soe_title = src_title if src_side == "soe" else (tgt_entry.get("title") or "")
            listed_title = (tgt_entry.get("title") or "") if src_side == "soe" else src_title
            if not match_section(soe_title, listed_title):
                continue
            pairs[src_sid] = {
                "target_sid": tgt_entry["section_id"],
                "title": src_title,
                "via": "alias",
            }
            bridged.append({
                "source_sid": src_sid,
                "target_sid": tgt_entry["section_id"],
                "source_title": src_title,
                "target_title": tgt_entry.get("title") or "",
            })
            source_only.pop(src_sid, None)
            target_only.pop(tgt_entry["section_id"], None)

        format_diff: dict[str, dict[str, Any]] = {}
        for entry in diff_data.get("format_diff_sections") or []:
            if isinstance(entry, dict) and entry.get(src_field):
                format_diff[entry[src_field]] = entry

        # ------------------------------------------------------------------
        # 禁止匹配对命中（Requirement 5.3 / design Error Handling 表）
        #
        # 判据 = **两侧标题都落在各自的「独有」桶里**（已扣除别名桥接）。这正是
        # 「本该看起来像同一章、但我们故意不配对」的形态：两个章节各自被判独有，
        # 源侧走归档、目标侧走新建空章。预览要把它显式展示出来，否则审计师看到
        # 「归档 1 + 新建 1」会以为是漏配。
        #
        # 🔴 只报「双侧都在」的对，不报单侧命中 —— 实测两份模板 JSON 里
        # 「公司财务报表主要项目注释」（源 docx 无「母」字的写法）**不存在**，
        # 只有带「母」字的 JSON 现值存在 ⇒ 那一条只有单侧命中，报出来是噪声
        # （它的价值在于「改一侧另一侧漏防」的防御，不是当期事实）。
        # ------------------------------------------------------------------
        src_only_by_title = {
            normalize_for_match(e.get("title")): e for e in source_only.values()
        }
        tgt_only_by_title = {
            normalize_for_match(e.get("title")): e for e in target_only.values()
        }
        forbidden_hits: list[dict[str, Any]] = []
        for soe_title, listed_title, reason in FORBIDDEN_MATCH_PAIRS:
            src_title = soe_title if src_side == "soe" else listed_title
            tgt_title = listed_title if src_side == "soe" else soe_title
            src_entry = src_only_by_title.get(normalize_for_match(src_title))
            tgt_entry = tgt_only_by_title.get(normalize_for_match(tgt_title))
            if not src_entry or not tgt_entry:
                continue
            forbidden_hits.append({
                "source_side": src_side,
                "target_side": tgt_side,
                "source_title": src_entry.get("title") or src_title,
                "source_section_id": src_entry.get("section_id"),
                "target_title": tgt_entry.get("title") or tgt_title,
                "target_section_id": tgt_entry.get("section_id"),
                "soe_title": soe_title,
                "listed_title": listed_title,
                "reason": reason,
            })

        return {
            "pairs": pairs,
            "source_only": set(source_only),
            "target_only": target_only,
            "target_sids": {v["target_sid"] for v in pairs.values()},
            "format_diff": format_diff,
            "bridged": bridged,
            "forbidden_hits": forbidden_hits,
        }

    @staticmethod
    def _build_sid_backfill_index(sections: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
        """构造源侧模板的 sid 反查索引（``section_id IS NULL`` 存量行回填用）。

        spec: Requirement 2.8

        🔴 **只按 (section_number, section_title) 与 section_title 两级反查，
        刻意不提供「只按 section_number」的兜底** —— 实测那样会制造错位：
        listed 项目里存在 ``note_section='八'`` 且 ``section_title='财务报表主要项目注释'``
        的存量行（soe 口径章名），按编号反查 listed 模板得到的是 ``八、政府补助``，
        正是本 spec 要消除的「同章节号不同科目」错位。宁缺勿造 → 进 ``skipped``。
        """
        from app.services.note_section_matcher import normalize_for_match

        by_number_title: dict[str, list[str]] = {}
        by_title: dict[str, list[str]] = {}
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            sid = sec.get("section_id")
            if not sid:
                continue
            number = normalize_for_match(sec.get("section_number"))
            title = normalize_for_match(sec.get("section_title"))
            if number and title:
                by_number_title.setdefault(f"{number}\x00{title}", []).append(sid)
            if title:
                by_title.setdefault(title, []).append(sid)
        return {"by_number_title": by_number_title, "by_title": by_title}

    @staticmethod
    def _resolve_missing_sid(
        index: dict[str, dict[str, list[str]]],
        note_section: str | None,
        section_title: str | None,
    ) -> tuple[str | None, str]:
        """按 (note_section, section_title) 回填 sid。

        Returns:
            ``(sid, how)``；``how`` ∈ ``number_title`` / ``title`` /
            :data:`SKIP_REASON_SID_AMBIGUOUS` / :data:`SKIP_REASON_SID_UNRESOLVED`。
        """
        from app.services.note_section_matcher import normalize_for_match

        number = normalize_for_match(note_section)
        title = normalize_for_match(section_title)
        if title:
            hit = index["by_number_title"].get(f"{number}\x00{title}") if number else None
            if hit:
                if len(hit) == 1:
                    return hit[0], "number_title"
                return None, SKIP_REASON_SID_AMBIGUOUS
            hit = index["by_title"].get(title)
            if hit:
                if len(hit) == 1:
                    return hit[0], "title"
                return None, SKIP_REASON_SID_AMBIGUOUS
        return None, SKIP_REASON_SID_UNRESOLVED

    async def _map_disclosure_notes(
        self,
        project_id: UUID,
        year: int,
        current_type: str,
        target_type: str,
    ) -> dict[str, Any]:
        """把 ``disclosure_notes`` 的章节标识真正改写到目标变体。

        spec: soe-listed-note-conversion-correctness
        / Requirements 2.1, 2.2, 2.6, 2.7, 2.8, 4.1, 4.2, 4.3

        ------------------------------------------------------------------
        改造前的行为（本 spec 立项要修的核心缺陷）
        ------------------------------------------------------------------

        原实现只 ``SELECT count(*)`` 返回存量章节数，**一行数据不改**，而该计数
        被当作 ``mapped_notes`` 上报给审计师 ⇒ 界面显示「已映射 N 个章节」而实际
        零映射（假成功反馈）。同时 ``template_type`` 已切换 ⇒ 读取按新模板渲染，
        两份模板有 20 个章节号重合且 13 个标题不同（``八、1`` 在 soe 是货币资金、
        在 listed 是政府补助）⇒ 原「八、1 货币资金」的数据显示在「八、1 政府补助」
        位置。

        ------------------------------------------------------------------
        本步做什么
        ------------------------------------------------------------------

        * **共有章节**（含别名桥接）→ 改写 ``section_id`` + ``note_section``
          （🔴 **不是** ``section_number`` —— 该列不存在），源侧 sid 追加进
          ``template_lineage.legacy_section_ids``（``legacy_aliases`` 列也不存在；
          本 spec 无迁移故落 JSONB）。
        * **``binding_id`` 前缀**（Requirement 2.7）→ 与 ``note_section`` 同步改写，
          旧章节号记入 ``template_lineage.legacy_note_sections`` 供解析回退。
        * **``section_id IS NULL`` 的存量行**（Requirement 2.8，实测 817/1030）
          → 按 (``note_section``, ``section_title``) 回填后参与映射，回填不出则
          进 ``skipped`` 附原因码，**禁静默跳过**。
        * **重复行防护**（Requirement 2.6）→ 改写前检查目标 sid 是否已被本
          (project, year) 的其他未删除记录占用，占用则进 ``skipped``。
        * **格式适配** → 走 :func:`adapt_table_data_with_report`，按
          ``report.changed``（事实判据）计 ``format_adapted``，**不得**改回无条件
          ``+= 1``（那会把 39/39 全 null 的 ``field_mapping`` 空操作上报成「已适配」）。
        * **源侧独有章节归档**（Requirement 2.3）→ ``is_deleted=true`` +
          ``template_lineage.archived_sections`` 追加
          ``{section_id, archived_at, reason}``。``status`` 枚举**没有** ``archived``
          取值（实测仅 ``draft``/``confirmed``）⇒ 归档只能这么表达。
        * **目标侧独有章节新建**（Requirement 2.4）→ ``is_empty=true`` /
          ``status='draft'``，``note_section`` 取**目标模板的真实 ``section_number``**
          （🔴 **不是** sid —— 历史 v2 实现写 ``note_section=sid  # legacy compat``
          是缺陷形态：章节号列会变成一串 slug，而界面与 Word 导出都读它。
          那份实现已于 spec Task 10 删除，此处记录以防回退）。新建**必须先过章节号占用检查**，撞号进
          ``skipped``（见 :data:`SKIP_REASON_CREATE_NUMBER_OCCUPIED`）。
        * **人工编辑保留**（Requirement 2.5）→ 共有章节的 ``_cell_modes == 'manual'``
          单元格数计入 ``user_edits_preserved``。「保留」本身是**不动 ``table_data``
          的自然结果**，但本步会改 ``binding_id`` 前缀、可能跑列重映射 ⇒ 逐章节比对
          改写前后的 manual 计数，少了就记 ``user_edits_dropped`` 并 ERROR
          （平台红线：manual 单元格必须保留）。
        * 逐章节 ``begin_nested()`` savepoint，异常进 ``failed`` 并继续处理其余章节
          （Requirement 4.3：一章失败不该让整次转换白做）。

        ------------------------------------------------------------------
        本步**不**做什么（spec Task 10）
        ------------------------------------------------------------------

        与历史 v2 章节转换方法的收敛已由 spec Task 10 完成：**本方法是唯一真源**，
        ``convert_disclosure_notes_v2`` / ``preview_conversion_v2`` 已删除（生产零
        调用方 + 三缺陷已在本方法修好 + 断言已迁移至
        ``tests/services/test_note_conversion_section_mapping_production.py``）。
        **不要**再造第二份章节转换实现 —— 守卫
        ``tests/test_note_conversion_v2_removal.py`` 会打红。

        Returns:
            ``{"mapped": int, "archived": int, "created": int,
               "format_adapted": int, "user_edits_preserved": int,
               "skipped": list[dict], "failed": list[dict], ...}``
        """
        from app.models.report_models import DisclosureNote
        from app.services.note_template_diff import (
            adapt_table_data_with_report,
            load_diff_data,
            load_template_sections,
        )

        result: dict[str, Any] = {
            "mapped": 0,
            # Requirement 2.3 / 2.4 / 2.5（Task 9）—— 真实计数，``0`` = 已测量为零
            "archived": 0,
            "created": 0,
            "user_edits_preserved": 0,
            # 共有章节改写前后 manual 计数的净减少量。正常恒 0；非 0 即平台红线
            # 「manual 单元格必须保留」被破坏，同时会记 ERROR 日志。
            "user_edits_dropped": 0,
            "format_adapted": 0,
            "skipped": [],
            "failed": [],
            "binding_ids_rewritten": 0,
            # section_id IS NULL 的存量行成功回填出源侧 sid 的条数（Requirement 2.8）
            "sid_backfilled": 0,
            # 其中「本轮不改写但已把回填结果落库」的条数
            "sid_backfill_persisted": 0,
            # 回填出的 sid 已被别的 note 占用 ⇒ 不落库（防重复行，Requirement 2.6）
            "sid_backfill_conflicts": 0,
            "bridged_by_alias": [],
            # 禁止匹配对命中（Requirement 5.3）—— 两侧标题都落在各自「独有」桶里，
            # 源侧因此走归档、目标侧走新建空章。预览端点（Requirement 9.1）据此
            # 向审计师展示「这两个章节故意不配对」，避免被误读成漏配。
            "forbidden_hits": [],
            "pending_keys": list(MAP_NOTES_PENDING_KEYS),
        }
        # 未测量项一律置 None（≠ 0 = 已测量为零）。Task 9 收口后该元组为空，
        # 此循环是**空操作**，保留是为了将来新增未测量项时不必重建这条纪律。
        for key in MAP_NOTES_PENDING_KEYS:
            result[key] = None

        if current_type == target_type:
            return result

        src_side = _conversion_side(current_type)
        tgt_side = _conversion_side(target_type)

        plan = self._build_section_mapping_plan(load_diff_data(), current_type, target_type)
        result["bridged_by_alias"] = plan["bridged"]
        result["forbidden_hits"] = plan["forbidden_hits"]

        # 目标模板 sid → section 全量条目（单一索引，供「改写章节号」与「新建空章节」
        # 两条路径共用；建两个平行索引会变成双真源）
        target_sections: dict[str, dict[str, Any]] = {
            sec["section_id"]: sec
            for sec in load_template_sections(tgt_side)
            if isinstance(sec, dict) and sec.get("section_id")
        }

        def target_number(sid: str) -> str | None:
            return (target_sections.get(sid) or {}).get("section_number")

        backfill_index = self._build_sid_backfill_index(load_template_sections(src_side))

        notes_result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        notes = list(notes_result.scalars().all())

        # 目标 sid 占用集（Requirement 2.6 防重复行）：既有 sid + 本轮已写入的 sid
        occupied: dict[str, UUID] = {n.section_id: n.id for n in notes if n.section_id}

        # 目标章节号占用集 —— **不过滤 is_deleted**，因为 DB 的
        # uq_disclosure_notes_project_year_section 是非部分唯一索引，软删记录同样占位。
        number_rows = await self.db.execute(
            sa.select(DisclosureNote.id, DisclosureNote.note_section).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
            )
        )
        number_owner: dict[str, UUID] = {
            r.note_section: r.id for r in number_rows.all() if r.note_section
        }

        for note in notes:
            async def skip(
                reason: str,
                sid: str | None = None,
                detail: str | None = None,
                *,
                backfilled_from: str | None = None,
            ) -> None:
                """登记一条跳过；若 sid 是本轮回填出来的则顺带落库。

                🔴 **落库必须先过占用检查**：两条 ``section_id IS NULL`` 的存量行
                可能回填到同一个 sid，无脑写会产生重复 ``(project_id, year,
                section_id)`` —— 正是 Requirement 2.6 / Property 10 要禁的形态。
                占用则不写，计入 ``sid_backfill_conflicts`` 供审计核对。

                落库的价值：Task 9 的归档要按 sid 记 ``archived_sections``，
                下一次转换也能直接参与映射（否则每次都要重新回填）。
                """
                if backfilled_from and sid:
                    holder = occupied.get(sid)
                    if holder is None or holder == note.id:
                        note.section_id = sid
                        self._record_lineage(note, backfilled_from=backfilled_from)
                        occupied[sid] = note.id
                        result["sid_backfill_persisted"] += 1
                        await self.db.flush()
                    else:
                        result["sid_backfill_conflicts"] += 1
                item = {
                    "note_id": str(note.id),
                    "section_id": sid,
                    "note_section": note.note_section,
                    "section_title": note.section_title,
                    "reason": reason,
                }
                if detail:
                    item["detail"] = detail
                result["skipped"].append(item)

            try:
                async with self.db.begin_nested():
                    src_sid = note.section_id
                    backfilled_how: str | None = None
                    if not src_sid:
                        src_sid, how = self._resolve_missing_sid(
                            backfill_index, note.note_section, note.section_title
                        )
                        if not src_sid:
                            await skip(how, detail="按 (note_section, section_title) 回填源侧 sid 失败")
                            continue
                        backfilled_how = how
                        # 🔴 唯一计数点，放在**解析成功处**：无论该章节随后是被改写
                        # 还是被 skip，「回填」这件事都已发生。在下游分支里重复 +1
                        # 会让计数超过实际章节数，使 Requirement 2.8 无法据此核对。
                        result["sid_backfilled"] += 1

                    if src_sid in plan["target_sids"] and src_sid not in plan["pairs"]:
                        # 已是目标侧取值 ⇒ 幂等重跑，不再改写
                        await skip(
                            SKIP_REASON_ALREADY_TARGET,
                            sid=src_sid,
                            backfilled_from=backfilled_how,
                        )
                        continue

                    pair = plan["pairs"].get(src_sid)
                    if pair is None:
                        if src_sid not in plan["source_only"]:
                            # sid 既不在共有清单也不在源独有清单（模板漂移 / 手工建的
                            # 章节）⇒ 不归档（归档等于替模板漂移的账做主张），如实登记。
                            await skip(
                                SKIP_REASON_UNKNOWN_SECTION,
                                sid=src_sid,
                                backfilled_from=backfilled_how,
                            )
                            continue

                        # 源侧独有章节 → 归档（Requirement 2.3）
                        #
                        # ``status`` 枚举实测仅 ``draft``/``confirmed``，**没有**
                        # ``archived`` ⇒ 只能靠 ``is_deleted=true`` +
                        # ``template_lineage.archived_sections`` 表达。
                        archive_lineage: dict[str, Any] = {
                            "archived_section_id": src_sid,
                            "archived_reason": archive_reason(current_type, target_type),
                            "converted": f"{current_type}_to_{target_type}",
                        }
                        if backfilled_how:
                            archive_lineage["backfilled_from"] = backfilled_how
                        note.is_deleted = True
                        if note.section_id != src_sid:
                            # 回填出来的 sid 一并落库，使 archived_sections[].section_id
                            # 与该行实际取值一致（供 rollback 与事后追溯）
                            note.section_id = src_sid
                        self._record_lineage(note, **archive_lineage)
                        await self.db.flush()
                        # 软删后不再占用 section_id（Requirement 2.6 只约束未删除行）；
                        # 🔴 但 **note_section 仍占位** —— uq_disclosure_notes_project_year_section
                        # 不排除软删行 ⇒ 绝不能从 number_owner 里 pop，否则新建阶段
                        # 会撞 IntegrityError。
                        occupied.pop(src_sid, None)
                        result["archived"] += 1
                        continue

                    target_sid = pair["target_sid"]
                    holder = occupied.get(target_sid)
                    if holder is not None and holder != note.id:
                        await skip(
                            SKIP_REASON_TARGET_SID_OCCUPIED,
                            sid=src_sid,
                            detail=f"目标 sid {target_sid} 已被 note {holder} 占用",
                            backfilled_from=backfilled_how,
                        )
                        continue

                    new_number = target_number(target_sid)
                    if not new_number:
                        await skip(
                            SKIP_REASON_TARGET_NUMBER_MISSING,
                            sid=src_sid,
                            detail=f"目标模板({tgt_side})无 sid={target_sid} 的 section_number",
                            backfilled_from=backfilled_how,
                        )
                        continue

                    number_holder = number_owner.get(new_number)
                    if number_holder is not None and number_holder != note.id:
                        await skip(
                            SKIP_REASON_TARGET_NUMBER_OCCUPIED,
                            sid=src_sid,
                            detail=(
                                f"目标章节号 {new_number} 已被 note {number_holder} 占用"
                                "（uq_disclosure_notes_project_year_section 不排除软删记录）"
                            ),
                            backfilled_from=backfilled_how,
                        )
                        continue

                    old_number = note.note_section
                    # Requirement 2.5：改写**前**的 manual 计数作为基准。本分支随后会
                    # 改 binding_id 前缀、可能跑列重映射，都不该让 manual 单元格消失。
                    manual_before = count_manual_cells(note.table_data)
                    lineage_kwargs: dict[str, Any] = {
                        "legacy_section_id": src_sid,
                        "converted": f"{current_type}_to_{target_type}",
                    }
                    if backfilled_how:
                        lineage_kwargs["backfilled_from"] = backfilled_how

                    # binding_id 前缀（Requirement 2.7）—— 必须深拷贝后整体赋值：
                    # JSONB 列未声明 MutableDict，就地改嵌套不标脏；且拿 ORM 持有的
                    # 同一 dict 改完再赋值会因新旧相等而不发 UPDATE。
                    if old_number and new_number != old_number and isinstance(note.table_data, dict):
                        new_td = deepcopy(note.table_data)
                        rewritten = _rewrite_binding_id_prefix(new_td, old_number, new_number)
                        if rewritten:
                            note.table_data = new_td
                            result["binding_ids_rewritten"] += rewritten
                            lineage_kwargs["legacy_note_section"] = old_number

                    note.section_id = target_sid
                    note.note_section = new_number
                    if pair["via"] == "alias" and pair.get("title"):
                        lineage_kwargs["alias_source_title"] = note.section_title
                    self._record_lineage(note, **lineage_kwargs)

                    # 格式适配（Requirement 1.5：按事实判据计数，不取自我声明）
                    fd = plan["format_diff"].get(src_sid)
                    if fd and isinstance(note.table_data, dict) and note.table_data:
                        target_format = (
                            fd.get("listed_format") if tgt_side == "listed" else fd.get("soe_format")
                        ) or {}
                        field_mapping = fd.get("field_mapping") or {}
                        if target_format or field_mapping:
                            adapted, report = adapt_table_data_with_report(
                                note.table_data, target_format, field_mapping
                            )
                            if report.changed:
                                note.table_data = adapted
                                result["format_adapted"] += 1

                    await self.db.flush()

                    # Requirement 2.5：改写后的 manual 计数即「保留下来的人工编辑」。
                    # 与基准不等说明本分支的改写弄丢了人工编辑（平台红线），如实上报。
                    manual_after = count_manual_cells(note.table_data)
                    result["user_edits_preserved"] += manual_after
                    if manual_after < manual_before:
                        dropped = manual_before - manual_after
                        result["user_edits_dropped"] += dropped
                        logger.error(
                            "note_conversion: 章节 %s→%s 丢失 %d 个 manual 单元格"
                            "（project=%s note=%s）—— 违反 Requirement 2.5",
                            src_sid, target_sid, dropped, project_id, note.id,
                        )

                    occupied.pop(src_sid, None)
                    occupied[target_sid] = note.id
                    if old_number and number_owner.get(old_number) == note.id:
                        number_owner.pop(old_number, None)
                    number_owner[new_number] = note.id
                    result["mapped"] += 1
            except Exception as exc:  # noqa: BLE001 — 逐章节隔离，失败不阻断其余
                logger.warning(
                    "note_conversion: 章节映射失败 project=%s note=%s sid=%s: %s",
                    project_id, note.id, note.section_id, exc,
                )
                result["failed"].append({
                    "note_id": str(note.id),
                    "section_id": note.section_id,
                    "note_section": note.note_section,
                    "phase": "map_section",
                    "error": str(exc),
                })

        # ------------------------------------------------------------------
        # 目标侧独有章节 → 新建空章节（Requirement 2.4 / Property 8）
        #
        # 🔴 必须**排在归档之后**：归档走软删而章节号唯一索引不排除软删行 ⇒ 只有在
        # 归档与共有章节改写都做完之后，``number_owner`` 才反映真实占用情况。
        # ------------------------------------------------------------------
        def record_create_skip(
            tgt_sid: str,
            entry: dict[str, Any],
            reason: str,
            number: str | None = None,
            detail: str | None = None,
        ) -> None:
            """登记一条「未新建」。``note_id`` 为 None（该章节还不存在）。"""
            item: dict[str, Any] = {
                "note_id": None,
                "section_id": tgt_sid,
                "note_section": number,
                "section_title": entry.get("title") or entry.get("section_title") or "",
                "reason": reason,
            }
            if detail:
                item["detail"] = detail
            result["skipped"].append(item)

        for tgt_sid, entry in plan["target_only"].items():
            new_number = target_number(tgt_sid)
            try:
                async with self.db.begin_nested():
                    if tgt_sid in occupied:
                        # 幂等：本 (project, year) 已有该 sid 的未删除记录
                        record_create_skip(
                            tgt_sid, entry, SKIP_REASON_CREATE_ALREADY_EXISTS, new_number,
                            detail=f"sid 已被 note {occupied[tgt_sid]} 占用",
                        )
                        continue
                    if not new_number:
                        record_create_skip(
                            tgt_sid, entry, SKIP_REASON_CREATE_NUMBER_MISSING,
                            detail=f"目标模板({tgt_side})无 sid={tgt_sid} 的 section_number",
                        )
                        continue
                    number_holder = number_owner.get(new_number)
                    if number_holder is not None:
                        record_create_skip(
                            tgt_sid, entry, SKIP_REASON_CREATE_NUMBER_OCCUPIED, new_number,
                            detail=(
                                f"目标章节号 {new_number} 已被 note {number_holder} 占用"
                                "（uq_disclosure_notes_project_year_section 不排除软删记录，"
                                "刚归档的同号章节仍占位）"
                            ),
                        )
                        continue

                    tpl = target_sections.get(tgt_sid) or {}
                    title = entry.get("title") or entry.get("section_title") or tpl.get(
                        "section_title"
                    ) or new_number
                    content_type = tpl.get("content_type")
                    new_note = DisclosureNote(
                        project_id=project_id,
                        year=year,
                        # 🔴 章节号取目标模板的真实 section_number。
                        # 历史 v2 实现写 ``note_section=sid``（注释「legacy compat」）
                        # 是缺陷形态 —— 该列是展示用章节号，写成 slug 会让界面与
                        # Word 导出显示一串拼音。那份实现已删（spec Task 10）。
                        note_section=new_number,
                        section_title=title,
                        section_id=tgt_sid,
                        # 结构字段取自目标模板（树位置 / 排序），缺失时用安全缺省
                        level=tpl.get("level") if isinstance(tpl.get("level"), int) else 2,
                        parent_section_id=tpl.get("parent_section_id") or None,
                        sort_index=int(tpl.get("sort_index") or 0),
                        sort_order=tpl.get("sort_order") if isinstance(tpl.get("sort_order"), int) else None,
                        account_name=tpl.get("account_name") or None,
                        content_type=content_type if content_type in ("table", "text", "mixed") else None,
                        source_template=tgt_side,
                        auto_numbering=True,
                        lock_number=False,
                        # Requirement 2.4：空章节
                        status="draft",
                        is_empty=True,
                    )
                    self._record_lineage(
                        new_note,
                        created_by_conversion=f"{current_type}_to_{target_type}",
                    )
                    self.db.add(new_note)
                    await self.db.flush()
                    occupied[tgt_sid] = new_note.id
                    number_owner[new_number] = new_note.id
                    result["created"] += 1
            except Exception as exc:  # noqa: BLE001 — 逐章节隔离，失败不阻断其余
                logger.warning(
                    "note_conversion: 章节新建失败 project=%s sid=%s number=%s: %s",
                    project_id, tgt_sid, new_number, exc,
                )
                result["failed"].append({
                    "note_id": None,
                    "section_id": tgt_sid,
                    "note_section": new_number,
                    "phase": "create_section",
                    "error": str(exc),
                })

        if result["failed"]:
            logger.error(
                "note_conversion: %s→%s 章节映射有 %d 个章节失败（其余 %d 个已改写）: %s",
                current_type, target_type, len(result["failed"]), result["mapped"],
                [f["section_id"] for f in result["failed"][:10]],
            )
        if result["user_edits_dropped"]:
            logger.error(
                "note_conversion: %s→%s 共 %d 个 manual 单元格在改写中丢失"
                "（保留 %d 个）—— 违反 Requirement 2.5，请核查 binding_id 改写与格式适配",
                current_type, target_type, result["user_edits_dropped"],
                result["user_edits_preserved"],
            )
        if result["skipped"]:
            reasons: dict[str, int] = {}
            for item in result["skipped"]:
                reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
            result["skipped_reasons"] = reasons
            logger.info(
                "note_conversion: %s→%s 章节映射跳过 %d 个，原因分布 %s",
                current_type, target_type, len(result["skipped"]), reasons,
            )
        logger.info(
            "note_conversion: %s→%s 章节处置汇总 —— 改写 %d / 归档 %d / 新建 %d / "
            "格式适配 %d / 保留人工编辑 %d 个单元格",
            current_type, target_type, result["mapped"], result["archived"],
            result["created"], result["format_adapted"], result["user_edits_preserved"],
        )
        return result

    @staticmethod
    def _record_lineage(
        note: Any,
        *,
        legacy_section_id: str | None = None,
        legacy_note_section: str | None = None,
        converted: str | None = None,
        backfilled_from: str | None = None,
        alias_source_title: str | None = None,
        archived_section_id: str | None = None,
        archived_reason: str | None = None,
        created_by_conversion: str | None = None,
    ) -> bool:
        """把转换痕迹写进 ``template_lineage``（JSONB）。

        spec: Requirements 2.2, 2.3, 2.4, 2.7（Property 6 / Property 7 / Property 35）

        ``disclosure_notes`` **无 ``legacy_aliases`` 列**（实测 39 列），本 spec 也
        无迁移 ⇒ 源侧 sid 落 ``template_lineage.legacy_section_ids``、旧章节号落
        ``template_lineage.legacy_note_sections``。该列全库实测 **0 条有值**，
        等于全新字段。

        承载的字段（Requirement 2.3 的 ``archived_sections`` 亦在此，语义与
        历史 v2 实现的同名字段一致，避免同一字段两套约定）：

        ================================  ==========================================
        ``legacy_section_ids``            共有章节改写前的源侧 sid（去重 list）
        ``legacy_note_sections``          改写前的旧章节号，供 binding_id 解析回退
        ``archived_sections``             ``{section_id, archived_at, reason}`` 列表
        ``created_by_conversion``         本章节由哪次转换新建（目标侧独有）
        ``section_id_backfilled_from``    NULL sid 的回填来源（``number_title``/``title``）
        ``alias_source_title``            别名桥接时的源侧标题
        ``conversions``                   转换方向与时间的历史 list
        ================================  ==========================================

        🔴 必须**深拷贝构造新 dict 再整体赋值**：JSONB 列未声明 ``MutableDict``，
        就地改嵌套不标脏；而拿 ORM 持有的同一个 dict 改完再赋值，新旧值 ``==``
        相等 ⇒ 工作单元判「无净变更」⇒ 不发 UPDATE。

        Returns:
            是否真的产生了变更。
        """
        base = note.template_lineage if isinstance(note.template_lineage, dict) else {}
        lineage = deepcopy(base)
        changed = False
        if legacy_section_id:
            changed |= _append_unique(lineage, "legacy_section_ids", legacy_section_id)
        if legacy_note_section:
            changed |= _append_unique(lineage, "legacy_note_sections", legacy_note_section)
        if backfilled_from and lineage.get("section_id_backfilled_from") != backfilled_from:
            lineage["section_id_backfilled_from"] = backfilled_from
            changed = True
        if alias_source_title and lineage.get("alias_source_title") != alias_source_title:
            lineage["alias_source_title"] = alias_source_title
            changed = True
        if archived_section_id and archived_reason:
            # 🔴 去重按 (section_id, reason) 而不是整条 dict —— 整条含
            # ``archived_at`` 时间戳，同一章节被同一方向重复归档会因时间戳不同而
            # 反复追加，把「归档一次」记成多次。
            history = lineage.get("archived_sections")
            items = [x for x in history if isinstance(x, dict)] if isinstance(history, list) else []
            already = any(
                x.get("section_id") == archived_section_id and x.get("reason") == archived_reason
                for x in items
            )
            if not already:
                items.append({
                    "section_id": archived_section_id,
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                    "reason": archived_reason,
                })
                lineage["archived_sections"] = items
                changed = True
        if created_by_conversion and lineage.get("created_by_conversion") != created_by_conversion:
            lineage["created_by_conversion"] = created_by_conversion
            lineage["created_at"] = datetime.now(timezone.utc).isoformat()
            changed = True
        if converted:
            entry = {"direction": converted, "at": datetime.now(timezone.utc).isoformat()}
            history = lineage.get("conversions")
            items = list(history) if isinstance(history, list) else []
            items.append(entry)
            lineage["conversions"] = items
            changed = True
        if changed:
            note.template_lineage = lineage
        return changed

    async def _update_formula_references(
        self,
        project_id: UUID,
        year: int,
        current_type: str,
        target_type: str,
    ) -> tuple[int, str]:
        """改写公式中的报表行引用 ``ROW('X')``（跨变体 row_code 映射）。

        spec: soe-listed-note-conversion-correctness / Requirements 3.3, 3.4, 4.4

        Returns:
            ``(改写条数, 原因码)``。原因码用于区分「已扫描确无对象」与「未实现」
            （Requirement 4.4）—— 二者都返回 0，但语义完全不同。

        ------------------------------------------------------------------
        实证依据（2026-08-06 全库对账，替代原「两准则 row_code 方案相同」的错误理由）
        ------------------------------------------------------------------

        原实现返回 0 的理由写作「both standards use the same row_code scheme」，
        该判断**不成立**：``report_config`` 四变体实测存在 **12 条同义两码**
        （同一 ``(report_type, row_name)`` 在两侧挂不同 row_code，如
        ``soe IS-055`` ↔ ``listed IS-033``），映射清单见
        :mod:`app.services.note_conversion_row_codes`。

        但返回 0 **当前仍是正确结果**，成因是「没有可改写的对象」而非「不需要改写」：

        - ``report_config`` **无 project_id 列** ⇒ 纯模板表，按
          ``applicable_standard`` 分行；切 ``template_type`` 后自然读另一套配置行，
          不存在「项目级公式需要跟着改」。
        - 全库 ``report_config.formula`` 中引用那 12 个 row_code 的行数 = **0**
          （``ROW()`` 引用集只覆盖 BS-002~BS-128 / CFS / CFSS / EQ / IMP /
          IS-001~IS-030 等主表行，无一条命中）。
        - ``wp_formula`` 表 **0 行**。
        - 附注侧公式的 ``binding_id`` 形如 ``五、11.分公司B.prior_year_value``
          （章节号 + 行标签 + 列键），``note_source_resolvers`` 里的 ``ROW()``
          参数是**单元格坐标**（``R2C1``）而非报表行码 ⇒ 不存在 row_code 级附注公式。

        故原因码为 ``no_mapping_needed``。清单与改写函数已就位，一旦将来出现
        row_code 级项目公式即刻生效（改写时会跳过
        :data:`~app.services.note_conversion_row_codes.ONE_CODE_TWO_MEANINGS_FORBIDDEN`）。

        复算脚本：``backend/scripts/diagnose/diagnose_cross_variant_row_codes.py``。
        """
        from app.services.note_conversion_row_codes import (
            FORMULA_REWRITE_REASON,
            rewrite_row_refs_in_formula,
        )

        # 方向非法/同向 → 改写函数自身即空操作（不在此处猜方向）。
        # 当前项目级公式载体不存在 row_code 级引用（见 docstring 实证），
        # 故没有可迭代的对象；清单与改写函数已就位，一旦出现即在此接入。
        _ = rewrite_row_refs_in_formula  # 接线锚点：符号存在性由守卫钉死
        return 0, FORMULA_REWRITE_REASON

    async def _trigger_chain_refresh(
        self,
        project_id: UUID,
        year: int,
    ) -> bool:
        """Trigger full chain refresh after conversion.

        Requirements: 47.6
        """
        try:
            from app.services.chain_orchestrator import ChainOrchestrator

            orchestrator = ChainOrchestrator(self.db)
            await orchestrator.execute_full_chain(
                project_id=project_id,
                year=year,
                steps=None,  # All steps
                force=True,
            )
            return True
        except Exception as e:
            logger.warning(
                "Chain refresh after conversion failed for project %s: %s",
                project_id, str(e),
            )
            # Don't fail the conversion if refresh fails
            return False

    # ---------------------------------------------------------------------------
    # Sprint A.5.1 / A.5.2 / A.5.3 — D14 section_id 驱动的章节互转 V2
    # ---------------------------------------------------------------------------
