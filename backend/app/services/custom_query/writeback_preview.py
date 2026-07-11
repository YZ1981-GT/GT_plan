"""WritebackPreview — 回写预览生成（高级查询模块）

Task 15.1（advanced-query-module）：在回写型查询执行**之前**，生成一份「将被修改
的目标 cell 列表」供用户确认。

设计要点（design.md §Components 11 WritebackPreview + SnapshotWriter）：

- **预览**（R14.1）：5s 内返回 ``WritebackPreview{items[≤10000]{addr_id, old_value,
  new_value}}``。每个 item 通过 ``AddressingService``（封装 ACNR ``full_resolve``）
  将目标解析为 canonical ``addr_id``，并捕获目标格**当前旧值** + **拟写入新值**。
- **空预览**（R14.6）：无任何 cell 将被修改 → 返回「无可回写内容」提示，且**不进入
  确认流程**（``enter_confirmation=False``）。
- **上限**：item 数量硬上限 10,000（``MAX_PREVIEW_ITEMS``）；超出则截断并置
  ``truncated=True``。

Task 15.2（确认窗口 + 乐观锁 stale 校验门）在同一模块中以 ``WritebackConfirmationGate``
实现：在**实际回写之前**做一道校验门 —— 校验预览未过期（默认 600s 确认窗口，R14.2）
且目标 cell 当前旧值与预览时捕获的旧值一致（乐观锁 stale 检测，R14.7）；任一不满足 →
``WritebackConfirmationConflict``（error_code ``WRITEBACK_CONFLICT`` → HTTP 409），数据不
变、提示重新预览。该门与 ``snapshot_writer.WritebackConflict``（opened_at vs updated_at
乐观锁）对齐同一 ``WRITEBACK_CONFLICT`` 契约。

实际回写事务（Task 15.3）不在本任务范围内 —— 本门只做「能否进入回写」的准入判定。

寻址与取值分离
--------------
- **身份（addr_id）**：由 ``AddressingService.resolve_target`` 统一解析（消费 ACNR
  出口，不重写 ACNR 核心）。目标携带的 ``raw`` 优先（通常即用户在 ACNR 选字段树选中
  的 addr_id / URI，Req 2/4）；缺省时以 ``{wp_code}/{sheet_name}/{cell_ref}`` 兜底构造。
- **旧值（old_value）**：目标已显式携带 ``old_value`` 时直接采用；否则对 workpaper
  模块从 ``working_paper.parsed_data['univer_snapshot']`` 只读定位捕获（与
  ``snapshot_writer`` 的定位逻辑一致，但**只读、不写**）。非 workpaper 模块由上层
  orchestrator 提供 ``old_value``（实际回写路径见 Task 15.3）。

Requirements: 14.1, 14.6
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.custom_query.addressing_service import (
    AddressingService,
    addressing_service,
)
from app.services.custom_query.snapshot_writer import _parse_cell_ref

logger = logging.getLogger(__name__)

# ─── 常量 ────────────────────────────────────────────────────────────────────

# 预览 item 硬上限（R14.1「不超过 10,000 条」）
MAX_PREVIEW_ITEMS = 10_000

# 预览时间预算（R14.1「5s 内返回」）
DEFAULT_PREVIEW_TIMEOUT_S = 5.0

# 空预览提示（R14.6）
EMPTY_PREVIEW_NOTICE = "无可回写内容：没有任何单元格需要修改。"

# 确认有效窗口默认值（R14.2「默认 600 秒」）
DEFAULT_CONFIRMATION_WINDOW_S = 600.0

# 确认时 stale 复核的时间预算（复用预览的 5s 解析/取值预算量级）
DEFAULT_CONFIRM_TIMEOUT_S = 5.0

# 归集层错误码（供 router 转 HTTP 状态；与 design.md Error Handling 表对齐）
ERR_CODE_PREVIEW_TIMEOUT = "RESOLVE_UNAVAILABLE"  # 预览超时视为解析服务不可用（R14.1 / R1.5）

# 回写冲突错误码（乐观锁 stale / 预览过期）；与 snapshot_writer.WritebackConflict 同契约
# （design.md Error Handling 表：`WRITEBACK_CONFLICT` → HTTP 409，数据不变、提示重新预览，R14.7）
ERR_CODE_WRITEBACK_CONFLICT = "WRITEBACK_CONFLICT"

# 重新预览提示（R14.7：预览过期或旧值不一致时提示重新预览）
RE_PREVIEW_NOTICE = "回写预览已失效（已过期或目标单元格旧值已变化），请重新预览后再确认。"

# ``old_value`` 未提供的哨兵（区分「显式 None」与「未提供需读取」）
_UNSET: Any = object()


# ─── 异常 ────────────────────────────────────────────────────────────────────


class WritebackPreviewError(Exception):
    """预览生成失败（如 5s 内未能完成解析/取值）。

    携带 ``error_code`` 供 router 层转为统一错误契约。
    """

    def __init__(self, message: str, *, error_code: str = ERR_CODE_PREVIEW_TIMEOUT) -> None:
        self.error_code = error_code
        self.message = message
        super().__init__(message)


class WritebackConfirmationConflict(Exception):
    """确认阶段回写冲突（Task 15.2）。

    触发条件（R14.7）：
      - ``reason="expired"``：确认时预览已超出确认有效窗口（默认 600s，R14.2）。
      - ``reason="stale"``：目标 cell 当前旧值与预览时捕获的旧值不一致（外部改动）。
      - ``reason="empty"``：预览为空/不应进入确认流程（R14.6，不允许确认）。

    统一携带 ``error_code = "WRITEBACK_CONFLICT"``，供 router 转 HTTP 409；与
    ``snapshot_writer.WritebackConflict`` 对齐同一错误契约。语义为「数据不变、提示重新
    预览」，本异常发生时**不得**发生任何数据写入。
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        stale_items: "list[WritebackPreviewItem] | None" = None,
        error_code: str = ERR_CODE_WRITEBACK_CONFLICT,
    ) -> None:
        self.error_code = error_code
        self.reason = reason
        self.message = message
        # 触发 stale 的具体条目（供前端高亮 / 审计记录），过期场景为空
        self.stale_items = stale_items or []
        super().__init__(message)


# ─── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class WritebackTarget:
    """单个回写目标 — 预览生成的输入单元。

    Fields:
      new_value:  拟写入的新值。
      raw:        寻址输入（addr_id / URI / 公式引用），用于解析 canonical addr_id；
                  通常即用户在 ACNR 选字段树选中的 ``node.addrId``（Req 2/4）。
                  为空时以 ``{wp_code}/{sheet_name}/{cell_ref}`` 兜底构造。
      module:     回写落点模块（workpaper / report / note / adj / tb），默认 workpaper。
      wp_id:      物理记录 ID（workpaper 模块为 working_paper.id），用于只读捕获旧值。
      wp_code:    底稿编码（兜底构造 raw 用）。
      sheet_name: sheet 名称（定位 cell 用）。
      cell_ref:   cell 引用（如 ``E100``）。
      old_value:  目标当前旧值；未提供（``_UNSET``）时由服务只读捕获。
    """

    new_value: Any
    raw: str | None = None
    module: str = "workpaper"
    wp_id: str | None = None
    wp_code: str | None = None
    sheet_name: str | None = None
    cell_ref: str | None = None
    old_value: Any = field(default=_UNSET)


@dataclass
class WritebackPreviewItem:
    """预览条目 — ``{addr_id, old_value, new_value}`` 及解析元信息。

    Fields:
      addr_id:    canonical ``{wp_code}/{sheet_code}/{coordinate_key}``；解析失败为 None。
      old_value:  目标格当前旧值（捕获或调用方提供）。
      new_value:  拟写入新值。
      raw:        原始寻址输入（回溯用）。
      found:      是否成功解析为有效 addr_id。
      error:      解析失败原因（found=False 时）。
      changed:    新旧值是否不同（True 表示该格会被修改）。
    """

    addr_id: str | None
    old_value: Any
    new_value: Any
    raw: str | None = None
    found: bool = True
    error: str | None = None
    changed: bool = True
    # 源目标回引（Task 15.2 确认门用于只读复核当前旧值 stale 检测）。
    # 不参与 to_dict 序列化（保持 R14.1 预览条目形态稳定）。
    source: "WritebackTarget | None" = field(default=None, repr=False, compare=False)


@dataclass
class WritebackPreview:
    """回写预览结果。

    Fields:
      items:              将被修改的目标 cell 列表（≤ MAX_PREVIEW_ITEMS）。
      item_count:         ``len(items)``。
      is_empty:           无任何 cell 将被修改（R14.6）。
      enter_confirmation: 是否进入确认流程（空预览为 False，R14.6）。
      truncated:          目标数超过硬上限被截断。
      notice:             空预览时的提示文案。
    """

    items: list[WritebackPreviewItem] = field(default_factory=list)
    is_empty: bool = True
    enter_confirmation: bool = False
    truncated: bool = False
    notice: str | None = None
    # 预览生成时刻（UTC）——确认门据此判定是否超出确认有效窗口（R14.2/R14.7）。
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # 确认有效窗口（秒），默认 600（R14.2）。
    confirmation_window_s: float = DEFAULT_CONFIRMATION_WINDOW_S

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def expires_at(self) -> datetime:
        """确认有效窗口的截止时刻（``created_at + confirmation_window_s``）。"""
        return self.created_at + timedelta(seconds=self.confirmation_window_s)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """判断预览是否已超出确认有效窗口（R14.2/R14.7）。

        ``now >= expires_at`` 视为过期。``now`` 缺省取当前 UTC 时间。
        """
        current = now or datetime.now(timezone.utc)
        # 归一 tz：预览 created_at 为 aware UTC；对 naive now 补 UTC 以稳健比较
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return current >= expires

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API 响应形态。"""
        return {
            "items": [
                {
                    "addr_id": it.addr_id,
                    "old_value": it.old_value,
                    "new_value": it.new_value,
                    "raw": it.raw,
                    "found": it.found,
                    "error": it.error,
                    "changed": it.changed,
                }
                for it in self.items
            ],
            "item_count": self.item_count,
            "is_empty": self.is_empty,
            "enter_confirmation": self.enter_confirmation,
            "truncated": self.truncated,
            "notice": self.notice,
            "created_at": self.created_at.isoformat(),
            "confirmation_window_s": self.confirmation_window_s,
            "expires_at": self.expires_at.isoformat(),
        }


# ─── 值比较 ──────────────────────────────────────────────────────────────────


def _values_equal(old: Any, new: Any) -> bool:
    """判断新旧值是否相等（用于「是否会被修改」判定）。

    - 数值型（int/float 与其数字字符串表示）按数值比较，规避 ``100 == "100"`` 的类型差异。
    - ``None`` 与空字符串视为等价（空 cell 的两种表示）。
    - 其余按字符串规范化后比较。
    """
    if old is new:
        return True

    # None / "" 归一为「空」
    old_empty = old is None or old == ""
    new_empty = new is None or new == ""
    if old_empty or new_empty:
        return old_empty and new_empty

    # 数值比较（含数字字符串）
    old_num = _to_number(old)
    new_num = _to_number(new)
    if old_num is not None and new_num is not None:
        return old_num == new_num

    return str(old) == str(new)


def _to_number(v: Any) -> float | None:
    """尽力转数值；不可转返回 None。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except (ValueError, AttributeError):
            return None
    return None


# ─── WritebackPreviewService ─────────────────────────────────────────────────


class WritebackPreviewService:
    """回写预览生成服务。

    ``generate`` 在 5s 时间预算内并发解析全部目标的 addr_id 并捕获旧值，产出
    ``WritebackPreview``；空预览（无 cell 将被修改）时 ``enter_confirmation=False``。
    """

    def __init__(self, *, addressing: AddressingService | None = None) -> None:
        # 依赖注入便于测试；默认复用模块级单例（消费 ACNR 出口）
        self._addressing = addressing or addressing_service

    async def generate(
        self,
        db: AsyncSession | None,
        targets: list[WritebackTarget],
        *,
        project_id: str | None = None,
        timeout_s: float = DEFAULT_PREVIEW_TIMEOUT_S,
        confirmation_window_s: float = DEFAULT_CONFIRMATION_WINDOW_S,
    ) -> WritebackPreview:
        """生成回写预览。

        Args:
            db:         数据库会话（只读捕获旧值用；目标已带 old_value 时可为 None）。
            targets:    回写目标列表。
            project_id: 项目上下文（ACNR 解析 project context）。
            timeout_s:  预览时间预算（默认 5s，R14.1）。
            confirmation_window_s: 确认有效窗口秒数（默认 600s，R14.2），写入预览供确认门校验。

        Returns:
            WritebackPreview；空预览 → ``is_empty=True`` + ``enter_confirmation=False``
            + 提示文案（R14.6）。

        Raises:
            WritebackPreviewError: 超出时间预算（视为解析服务不可用）。
        """
        # 无目标 → 直接空预览（R14.6），无需触达解析
        if not targets:
            return self._empty_preview(confirmation_window_s=confirmation_window_s)

        # 硬上限截断（R14.1：item ≤ 10,000）——截断在解析前，限定工作量与时间预算
        truncated = len(targets) > MAX_PREVIEW_ITEMS
        working = targets[:MAX_PREVIEW_ITEMS]

        try:
            built = await asyncio.wait_for(
                asyncio.gather(
                    *(self._build_item(db, t, project_id) for t in working)
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(
                "writeback preview timeout: targets=%d timeout=%ss",
                len(working),
                timeout_s,
            )
            raise WritebackPreviewError(
                f"回写预览未能在 {timeout_s}s 内完成，请稍后重试。",
                error_code=ERR_CODE_PREVIEW_TIMEOUT,
            ) from exc

        # 仅保留「将被修改」的条目：新旧值不同，或解析失败需要向用户暴露
        items = [it for it in built if it.changed or not it.found]

        if not items:
            return self._empty_preview(
                truncated=truncated, confirmation_window_s=confirmation_window_s
            )

        return WritebackPreview(
            items=items,
            is_empty=False,
            enter_confirmation=True,
            truncated=truncated,
            notice=None,
            confirmation_window_s=confirmation_window_s,
        )

    # ─── 内部：单条目构建 ────────────────────────────────────────────────

    async def _build_item(
        self,
        db: AsyncSession | None,
        target: WritebackTarget,
        project_id: str | None,
    ) -> WritebackPreviewItem:
        """解析 addr_id + 捕获旧值，构建单个预览条目。"""
        raw = self._resolve_raw(target)

        # 解析 canonical addr_id（消费 ACNR full_resolve 出口）
        addr_id: str | None = None
        found = False
        error: str | None = None
        if raw:
            resolved = await self._addressing.resolve_target(
                raw, project_id=project_id, db=db
            )
            found = resolved.found
            addr_id = resolved.addr_id
            error = resolved.error
        else:
            error = "missing_target"

        # 捕获旧值：目标已带 old_value 直接用；否则只读读取
        if target.old_value is not _UNSET:
            old_value = target.old_value
        else:
            old_value = await self._read_current_value(db, target)

        changed = not _values_equal(old_value, target.new_value)

        return WritebackPreviewItem(
            addr_id=addr_id,
            old_value=old_value,
            new_value=target.new_value,
            raw=raw,
            found=found,
            error=error,
            changed=changed,
            source=target,
        )

    @staticmethod
    def _resolve_raw(target: WritebackTarget) -> str | None:
        """确定用于解析 addr_id 的原始寻址输入。

        优先目标显式携带的 ``raw``；否则以 ``{wp_code}/{sheet_name}/{cell_ref}``
        兜底构造（裸 addr_id 形态，交由 AddressingService 归类解析）。
        """
        if target.raw:
            return target.raw
        parts = [target.wp_code, target.sheet_name, target.cell_ref]
        if all(parts):
            return "/".join(str(p) for p in parts)
        return None

    async def _read_current_value(
        self, db: AsyncSession | None, target: WritebackTarget
    ) -> Any:
        """只读捕获目标格当前旧值。

        目前完整实现 workpaper 模块（ACNR 身份升级的主回写路径）：从
        ``working_paper.parsed_data['univer_snapshot']`` 定位 cell 取值。非 workpaper
        模块的旧值应由上层 orchestrator 通过 ``target.old_value`` 提供；缺省返回 None。
        """
        if db is None:
            return None
        if target.module != "workpaper":
            # 非 workpaper 模块旧值由上层提供（实际回写路径见 Task 15.3）
            return None
        if not (target.wp_id and target.sheet_name and target.cell_ref):
            return None
        try:
            return await self._read_workpaper_value(
                db, target.wp_id, target.sheet_name, target.cell_ref
            )
        except Exception as exc:  # 只读取值失败不阻塞预览（降级为 None）
            logger.warning(
                "read old value failed (non-fatal): wp_id=%s cell=%s err=%s",
                target.wp_id,
                target.cell_ref,
                exc,
            )
            return None

    @staticmethod
    async def _read_workpaper_value(
        db: AsyncSession, wp_id: str, sheet_name: str, cell_ref: str
    ) -> Any:
        """从 working_paper.parsed_data['univer_snapshot'] 只读定位 cell 取旧值。

        定位逻辑与 ``snapshot_writer`` 保持一致（按 sheet name 匹配 →
        ``cellData[str(row)][str(col)].get('v')``），但**不加行锁、不写回**。
        """
        result = await db.execute(
            text("SELECT parsed_data FROM working_paper WHERE id = :wp_id"),
            {"wp_id": wp_id},
        )
        row = result.first()
        if not row or not row[0]:
            return None

        parsed_data = row[0]
        snapshot = parsed_data.get("univer_snapshot", {}) if isinstance(parsed_data, dict) else {}
        sheets = snapshot.get("sheets", {})

        target_sheet = None
        if isinstance(sheets, dict):
            for sheet_data in sheets.values():
                if isinstance(sheet_data, dict) and sheet_data.get("name") == sheet_name:
                    target_sheet = sheet_data
                    break
        elif isinstance(sheets, list):
            for sheet_data in sheets:
                if isinstance(sheet_data, dict) and sheet_data.get("name") == sheet_name:
                    target_sheet = sheet_data
                    break

        if target_sheet is None:
            return None

        row_idx, col_idx = _parse_cell_ref(cell_ref)
        cell_data = target_sheet.get("cellData", {})
        row_data = cell_data.get(str(row_idx), {}) if isinstance(cell_data, dict) else {}
        cell_obj = row_data.get(str(col_idx), {}) if isinstance(row_data, dict) else {}
        if isinstance(cell_obj, dict):
            return cell_obj.get("v")
        return None

    # ─── 内部：空预览 ────────────────────────────────────────────────────

    @staticmethod
    def _empty_preview(
        *,
        truncated: bool = False,
        confirmation_window_s: float = DEFAULT_CONFIRMATION_WINDOW_S,
    ) -> WritebackPreview:
        """构造空预览（R14.6）：提示无可回写、不进入确认流程。"""
        return WritebackPreview(
            items=[],
            is_empty=True,
            enter_confirmation=False,
            truncated=truncated,
            notice=EMPTY_PREVIEW_NOTICE,
            confirmation_window_s=confirmation_window_s,
        )


# 模块级单例（与 addressing_service / snapshot_writer 一致的使用范式）
writeback_preview_service = WritebackPreviewService()


# ─── 确认门（Task 15.2）：确认窗口 + 乐观锁 stale 校验 ─────────────────────────

# 「无法独立复核当前旧值」的哨兵：非 workpaper 模块或缺定位信息时，无法在确认门内只读
# 复核，交由 Task 15.3 写回事务的 opened_at vs updated_at 乐观锁把关（不误判 stale）。
_UNREADABLE: Any = object()


@dataclass
class ConfirmationCheck:
    """确认门校验结果（通过时返回）。

    Fields:
      ok:              是否通过确认门（本 dataclass 仅在通过时构造，恒为 True）。
      checked_at:      执行校验的 UTC 时刻。
      verified_items:  已成功只读复核旧值一致的条目数。
      deferred_items:  无法独立复核、延后至写回乐观锁把关的条目数。
    """

    ok: bool
    checked_at: datetime
    verified_items: int = 0
    deferred_items: int = 0


class WritebackConfirmationGate:
    """回写确认门（Task 15.2）。

    在**实际回写之前**做一道准入校验（不写数据）：

      1. **确认窗口**（R14.2）：预览必须在确认有效窗口（默认 600s）内确认，否则
         ``WritebackConfirmationConflict(reason="expired")``。
      2. **乐观锁 stale**（R14.7）：对可只读复核的目标（workpaper 模块 + 完整定位），
         重新读取当前旧值并与预览时捕获的旧值比较，任一不一致 →
         ``WritebackConfirmationConflict(reason="stale")``。
      3. **空预览**（R14.6）：``is_empty`` / ``enter_confirmation=False`` 的预览不允许
         进入确认 → ``WritebackConfirmationConflict(reason="empty")``。

    冲突时统一 ``error_code="WRITEBACK_CONFLICT"``（HTTP 409），语义为「数据不变、提示
    重新预览」；本门只做判定，不触发任何写入。非 workpaper / 无定位信息的目标无法在门内
    独立复核，计入 ``deferred_items``，由 Task 15.3 写回事务的乐观锁（opened_at vs
    updated_at）最终把关，避免在此误判 stale。
    """

    def __init__(self, *, preview_service: WritebackPreviewService | None = None) -> None:
        self._preview_service = preview_service or writeback_preview_service

    async def validate(
        self,
        db: AsyncSession | None,
        preview: WritebackPreview,
        *,
        now: datetime | None = None,
        timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
    ) -> ConfirmationCheck:
        """校验确认请求（确认窗口 + stale）。

        Args:
            db:        数据库会话（stale 复核只读读取当前旧值用）。
            preview:   待确认的回写预览（Task 15.1 生成，携带 created_at + 捕获旧值）。
            now:       当前时刻（默认 UTC now；便于测试注入）。
            timeout_s: stale 复核的时间预算。

        Returns:
            ConfirmationCheck(ok=True, ...) 通过。

        Raises:
            WritebackConfirmationConflict: 预览为空 / 已过期 / 目标旧值 stale（R14.6/14.2/14.7）。
        """
        checked_at = now or datetime.now(timezone.utc)

        # (3) 空预览 / 不应进入确认（R14.6）
        if preview.is_empty or not preview.enter_confirmation:
            raise WritebackConfirmationConflict(
                "预览为空或已不可确认，请重新发起预览。",
                reason="empty",
            )

        # (1) 确认窗口（R14.2）：过期 → 拒绝，提示重新预览（R14.7）
        if preview.is_expired(now=checked_at):
            raise WritebackConfirmationConflict(RE_PREVIEW_NOTICE, reason="expired")

        # (2) 乐观锁 stale（R14.7）：只复核「将被写入」且可只读复核的条目
        #     （found=True 的可解析目标；解析失败条目本就不会被写回，交由 15.3 中止）
        verified = 0
        deferred = 0
        stale_items: list[WritebackPreviewItem] = []

        async def _check(item: WritebackPreviewItem) -> None:
            nonlocal verified, deferred
            if not item.found:
                # 解析失败条目非本门 stale 范畴（15.3 写回时以 TARGET_UNRESOLVABLE 中止）
                deferred += 1
                return
            current = await self._reread_current_value(db, item)
            if current is _UNREADABLE:
                deferred += 1
                return
            if _values_equal(current, item.old_value):
                verified += 1
            else:
                stale_items.append(item)

        try:
            await asyncio.wait_for(
                asyncio.gather(*(_check(it) for it in preview.items)),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as exc:
            # 复核超时视为无法确认预览未 stale → 保守拒绝，提示重新预览（数据不变）
            logger.warning(
                "writeback confirmation stale-recheck timeout: items=%d timeout=%ss",
                preview.item_count,
                timeout_s,
            )
            raise WritebackConfirmationConflict(
                RE_PREVIEW_NOTICE, reason="expired"
            ) from exc

        if stale_items:
            logger.info(
                "writeback confirmation rejected (stale): %d/%d cell(s) changed since preview",
                len(stale_items),
                preview.item_count,
            )
            raise WritebackConfirmationConflict(
                RE_PREVIEW_NOTICE, reason="stale", stale_items=stale_items
            )

        return ConfirmationCheck(
            ok=True,
            checked_at=checked_at,
            verified_items=verified,
            deferred_items=deferred,
        )

    async def _reread_current_value(
        self, db: AsyncSession | None, item: WritebackPreviewItem
    ) -> Any:
        """只读复核目标格当前旧值（用于 stale 检测）。

        仅 workpaper 模块 + 完整定位（wp_id/sheet_name/cell_ref）可在门内独立复核；
        其余返回 ``_UNREADABLE`` 表示延后至写回乐观锁把关（不在此误判 stale）。
        """
        src = item.source
        if src is None or db is None:
            return _UNREADABLE
        if src.module != "workpaper":
            return _UNREADABLE
        if not (src.wp_id and src.sheet_name and src.cell_ref):
            return _UNREADABLE
        try:
            return await WritebackPreviewService._read_workpaper_value(
                db, src.wp_id, src.sheet_name, src.cell_ref
            )
        except Exception as exc:  # 只读复核失败 → 延后，不误判
            logger.warning(
                "stale recheck read failed (non-fatal, deferred): wp_id=%s cell=%s err=%s",
                src.wp_id,
                src.cell_ref,
                exc,
            )
            return _UNREADABLE


# 模块级单例（与 writeback_preview_service 一致的使用范式）
writeback_confirmation_gate = WritebackConfirmationGate()
