"""跨 sheet 公式追溯 — CrossSheetResolver

BFS 遍历 `=Sheet!Cell` 引用链，最深 3 层，支持环检测和缺失标记。

Algorithm (design.md 6.3):
  CrossSheetResolver.resolve(wp_id, sheet, cell_ref, max_depth=3):
    queue = deque([(sheet, cell_ref, 0)])
    visited = set()
    chain = []

    while queue:
      cur_sheet, cur_cell, depth = queue.popleft()
      uri = f"{cur_sheet}!{cur_cell}"
      if uri in visited → chain.append(RefChainNode(cycle=True)); continue
      visited.add(uri)

      value, formula = extract_cell(wp_id, cur_sheet, cur_cell)
      chain.append(RefChainNode(depth, uri, value, formula))

      if depth >= max_depth → chain[-1].truncated = True; continue

      refs = parse_cross_sheet_refs(formula)
      for ref_sheet, ref_cell in refs:
        queue.append((ref_sheet, ref_cell, depth + 1))

    return chain
"""

import asyncio
import logging
import re
from collections import deque
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.services.acnr.resolver import ResolveResult

logger = logging.getLogger(__name__)


# ─── Models ──────────────────────────────────────────────────────────────────


class RefChainNode(BaseModel):
    """引用链中的单个节点"""

    depth: int  # 0..3
    uri: str  # 命中时为 ACNR addr_id（如 "D2/D2-1/A2"），否则 "审定表D2-1!A2"
    value: Any = None
    formula: str | None = None
    truncated: bool = False  # 第 3 层后截断
    cycle: bool = False  # 检测到循环
    missing: bool = False  # 引用目标缺失
    resolve_missed: bool = False  # ACNR full_resolve 未命中（走 snapshot fallback）


class RefChainResponse(BaseModel):
    """跨 sheet 追溯响应"""

    chain: list[RefChainNode]  # depth 0..3
    has_cycle: bool
    truncated_at_depth: int | None


# ─── Formula Parser ──────────────────────────────────────────────────────────

# Matches cross-sheet references in formulas:
#   'Sheet Name'!A1  (quoted sheet name with spaces/Chinese)
#   SheetName!A1     (unquoted sheet name)
# Handles multiple refs in one formula. Avoids matching function names like SUM(.
# Group 1 = quoted name, Group 2 = unquoted name, Group 3 = cell ref
_CROSS_SHEET_REF_PATTERN = re.compile(
    r"(?:'([^']+)'|([A-Za-z\u4e00-\u9fff][\w\u4e00-\u9fff]*))!([A-Z]{1,3}\d{1,7})",
    re.IGNORECASE,
)


def parse_cross_sheet_refs(formula: str | None) -> list[tuple[str, str]]:
    """从公式字符串中提取所有跨 sheet 引用 (sheet_name, cell_ref) 对。

    Examples:
        "=审定表D2-1!A2" → [("审定表D2-1", "A2")]
        "='Sheet Name'!B3+Sheet2!C4" → [("Sheet Name", "B3"), ("Sheet2", "C4")]
        "=Left!A1+Right!A1" → [("Left", "A1"), ("Right", "A1")]
        "=A1+B2" → []
        None → []
        "" → []
    """
    if not formula:
        return []
    matches = _CROSS_SHEET_REF_PATTERN.findall(formula)
    # Each match is (quoted_name, unquoted_name, cell_ref)
    return [(m[0] or m[1], m[2].upper()) for m in matches]


# ─── Cell Extraction ─────────────────────────────────────────────────────────


def _extract_cell_from_snapshot(
    parsed_data: dict | None, sheet_name: str, cell_ref: str
) -> tuple[Any, str | None]:
    """从 parsed_data['univer_snapshot'] 提取指定 cell 的 value 和 formula。

    Returns:
        (value, formula) — 若 cell 不存在返回 (None, None)
    """
    if not parsed_data:
        return None, None

    snapshot = parsed_data.get("univer_snapshot")
    if not snapshot:
        return None, None

    sheets = snapshot.get("sheets")
    if not sheets:
        return None, None

    # Find the target sheet by name
    target_sheet = None
    if isinstance(sheets, list):
        for s in sheets:
            if isinstance(s, dict) and s.get("name") == sheet_name:
                target_sheet = s
                break
    elif isinstance(sheets, dict):
        target_sheet = sheets.get(sheet_name)

    if not target_sheet:
        return None, None

    cell_data = target_sheet.get("cellData")
    if not cell_data:
        return None, None

    # Parse cell_ref (e.g. "A2" → row=1, col=0 in 0-indexed)
    row_idx, col_idx = _cell_ref_to_indices(cell_ref)
    if row_idx is None or col_idx is None:
        return None, None

    # cellData uses 0-indexed string keys
    row_data = cell_data.get(str(row_idx))
    if not row_data or not isinstance(row_data, dict):
        return None, None

    cell = row_data.get(str(col_idx))
    if not cell or not isinstance(cell, dict):
        return None, None

    value = cell.get("v")
    formula = cell.get("f")
    # Ensure formula starts with '=' for consistency
    if formula and not formula.startswith("="):
        formula = f"={formula}"

    return value, formula


def _cell_ref_to_indices(cell_ref: str) -> tuple[int | None, int | None]:
    """Convert cell reference like 'A1' to 0-indexed (row, col).

    Examples:
        'A1' → (0, 0)
        'B3' → (2, 1)
        'AA10' → (9, 26)
    """
    match = re.match(r"^([A-Z]+)(\d+)$", cell_ref.upper())
    if not match:
        return None, None

    col_str = match.group(1)
    row_num = int(match.group(2))

    # Convert column letters to 0-indexed number
    col_idx = 0
    for ch in col_str:
        col_idx = col_idx * 26 + (ord(ch) - ord("A") + 1)
    col_idx -= 1  # 0-indexed

    row_idx = row_num - 1  # 0-indexed

    return row_idx, col_idx


# ─── ACNR sync→async bridge (design §1) ──────────────────────────────────────


def _sync_resolve(
    *,
    formula_ref: str | None = None,
    uri: str | None = None,
    project_id: str | None = None,
) -> "ResolveResult | None":
    """同步桥接 ACNR async `full_resolve`，带优雅降级（design §1 风险修复）。

    `full_resolve` 是 async，而 `CrossSheetResolver.resolve` 是同步纯 BFS，且常在
    FastAPI 请求线程 / 异步 orchestrator 内被调用（已有运行中的 event loop）。此时
    `asyncio.run()` / `run_until_complete()` 会抛 `RuntimeError: event loop is
    already running`。策略（design §1）：

      1. 探测当前是否有 running loop：`asyncio.get_running_loop()`。
      2. **有 running loop** → 无法安全内联桥接 → 返回 None（降级 snapshot fallback）。
         这保持了 orchestrator/请求线程内「同步纯 BFS 无 IO」的运行时语义，异步 addr_id
         解析由 orchestrator 的 `AddressingService` 层单独上浮完成。
      3. **无 running loop**（纯同步上下文，如脚本/测试）→ `asyncio.run(full_resolve(...))`。

    容错第一：任何桥接/解析失败一律返回 None，绝不抛异常中断 BFS（Req 1.6）。
    """
    try:
        from app.services.acnr.resolver import full_resolve
    except Exception as exc:  # pragma: no cover - import guard
        logger.warning("ACNR resolver import failed: %s", exc)
        return None

    # Step 1-2: 探测 running loop，有则降级（不阻塞 BFS）
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # 无 running loop → 可安全 asyncio.run
    else:
        # 已有运行中的 loop：内联桥接不安全 → 降级 snapshot fallback
        return None

    # Step 3: 纯同步上下文 → 运行协程
    try:
        return asyncio.run(
            full_resolve(
                formula_ref=formula_ref,
                uri=uri,
                project_id=project_id,
            )
        )
    except Exception as exc:
        logger.warning(
            "ACNR full_resolve bridge failed (formula_ref=%s uri=%s): %s",
            formula_ref,
            uri,
            exc,
        )
        return None


# ─── Resolver ────────────────────────────────────────────────────────────────


class CrossSheetResolver:
    """跨 sheet 公式追溯器 — BFS + 环检测 + ACNR addr_id 解析"""

    def __init__(
        self,
        project_id: str | None = None,
        parent_wp_code: str | None = None,
    ) -> None:
        """
        Args:
            project_id: 项目 ID，传递给 ACNR full_resolve 以启用 L2 overlay + wp_id 附加（Req 1.4）
            parent_wp_code: 父底稿码（可选）。已知时构造 grammar_v1 的 3 参
                `WP(parent, sheet, cell)`；未知时退化为 URI 形态交给 resolver 匹配。
        """
        self._project_id = project_id
        self._parent_wp_code = parent_wp_code

    def resolve(
        self,
        parsed_data: dict | None,
        sheet_name: str,
        cell_ref: str,
        max_depth: int = 3,
    ) -> RefChainResponse:
        """BFS 遍历跨 sheet 引用链。

        Args:
            parsed_data: working_paper.parsed_data (含 univer_snapshot)
            sheet_name: 起始 sheet 名
            cell_ref: 起始 cell 引用 (e.g. "A2")
            max_depth: 最大递归深度 (默认 3)

        Returns:
            RefChainResponse with chain nodes, cycle flag, truncation info
        """
        # Clamp max_depth to 3
        max_depth = min(max_depth, 3)

        queue: deque[tuple[str, str, int]] = deque()
        queue.append((sheet_name, cell_ref.upper(), 0))
        visited: set[str] = set()
        chain: list[RefChainNode] = []
        has_cycle = False
        truncated_at_depth: int | None = None

        while queue:
            cur_sheet, cur_cell, depth = queue.popleft()

            # ── ACNR full_resolve 尝试（Req 1.1, 1.2, 1.3, 1.4, 1.6）────────
            # 命中（found=true）→ 使用 addr_id 作为 node URI；未命中/异常 → 降级
            # 到 snapshot fallback（uri=sheet!cell）并标记 resolve_missed=True。
            acnr_result: "ResolveResult | None" = None
            try:
                if self._parent_wp_code:
                    # grammar_v1 3 参形态：WP(parent, sheet, cell)
                    formula_ref = (
                        f"WP('{self._parent_wp_code}','{cur_sheet}','{cur_cell}')"
                    )
                    acnr_result = _sync_resolve(
                        formula_ref=formula_ref,
                        project_id=self._project_id,
                    )
                else:
                    # 无 parent wp_code → 退化 URI 形态，交由 resolver 的
                    # sheet-alias / custom_flat 分支去匹配
                    acnr_result = _sync_resolve(
                        uri=f"wp://{cur_sheet}/{cur_cell}",
                        project_id=self._project_id,
                    )
            except Exception as exc:  # 防御：_sync_resolve 已吞异常，此处再兜底
                logger.warning(
                    "ACNR full_resolve failed for %s!%s: %s",
                    cur_sheet,
                    cur_cell,
                    exc,
                )

            if acnr_result and acnr_result.found and acnr_result.addr_id:
                uri = acnr_result.addr_id
                resolve_missed = False
            else:
                uri = f"{cur_sheet}!{cur_cell}"
                resolve_missed = True

            # Cycle detection
            if uri in visited:
                chain.append(
                    RefChainNode(
                        depth=depth,
                        uri=uri,
                        cycle=True,
                        resolve_missed=resolve_missed,
                    )
                )
                has_cycle = True
                continue

            visited.add(uri)

            # Extract cell value and formula
            value, formula = _extract_cell_from_snapshot(
                parsed_data, cur_sheet, cur_cell
            )

            # Check if target is missing (sheet or cell not found)
            missing = self._is_missing(parsed_data, cur_sheet, cur_cell)

            node = RefChainNode(
                depth=depth,
                uri=uri,
                value=value,
                formula=formula,
                missing=missing,
                resolve_missed=resolve_missed,
            )
            chain.append(node)

            # Depth termination
            if depth >= max_depth:
                node.truncated = True
                if truncated_at_depth is None:
                    truncated_at_depth = depth
                continue

            # Parse cross-sheet references from formula
            refs = parse_cross_sheet_refs(formula)
            for ref_sheet, ref_cell in refs:
                queue.append((ref_sheet, ref_cell, depth + 1))

        return RefChainResponse(
            chain=chain,
            has_cycle=has_cycle,
            truncated_at_depth=truncated_at_depth,
        )

    def _is_missing(
        self, parsed_data: dict | None, sheet_name: str, cell_ref: str
    ) -> bool:
        """Check if the referenced sheet/cell is missing from the snapshot."""
        if not parsed_data:
            return True

        snapshot = parsed_data.get("univer_snapshot")
        if not snapshot:
            return True

        sheets = snapshot.get("sheets")
        if not sheets:
            return True

        # Find the target sheet
        if isinstance(sheets, list):
            for s in sheets:
                if isinstance(s, dict) and s.get("name") == sheet_name:
                    return False  # Sheet exists, cell may be empty but not "missing"
            return True  # Sheet not found
        elif isinstance(sheets, dict):
            return sheet_name not in sheets

        return True

    # ─── Async hot path (Req-8.4) ──────────────────────────────────────────

    async def full_resolve_async(
        self,
        parsed_data: dict | None,
        sheet_name: str,
        cell_ref: str,
        max_depth: int = 3,
    ) -> RefChainResponse:
        """Async 热路径 BFS：在 async 上下文中用 await full_resolve 替代 _sync_resolve() None 降级。

        Req-8.4: CrossSheetResolver._sync_resolve() 在 async 热路径检测到 event loop 时
        SHALL 使用 async orchestrator 预解析。本方法是 async 版 resolve()，在已有
        event loop 的场景下直接 await full_resolve，不降级到 snapshot fallback。

        Parameters
        ----------
        parsed_data : dict | None
            底稿 parsed_data (含 univer_snapshot)
        sheet_name : str
            起始 sheet 名
        cell_ref : str
            起始 cell 引用 (e.g. "A2")
        max_depth : int
            最大递归深度 (默认 3)

        Returns
        -------
        RefChainResponse
            与同步 resolve() 相同结构的响应，但 ACNR 解析不降级。
        """
        max_depth = min(max_depth, 3)

        try:
            from app.services.acnr.resolver import full_resolve
        except Exception as exc:
            logger.warning("ACNR resolver import failed in async path: %s", exc)
            # Fallback to sync resolve (which will itself degrade to snapshot)
            return self.resolve(parsed_data, sheet_name, cell_ref, max_depth)

        queue: deque[tuple[str, str, int]] = deque()
        queue.append((sheet_name, cell_ref.upper(), 0))
        visited: set[str] = set()
        chain: list[RefChainNode] = []
        has_cycle = False
        truncated_at_depth: int | None = None

        while queue:
            cur_sheet, cur_cell, depth = queue.popleft()

            # ── Async ACNR full_resolve (Req-8.4) ────────────────────────
            acnr_result: "ResolveResult | None" = None
            resolve_missed = True
            try:
                if self._parent_wp_code:
                    formula_ref = (
                        f"WP('{self._parent_wp_code}','{cur_sheet}','{cur_cell}')"
                    )
                    acnr_result = await full_resolve(
                        formula_ref=formula_ref,
                        project_id=self._project_id,
                    )
                else:
                    acnr_result = await full_resolve(
                        uri=f"wp://{cur_sheet}/{cur_cell}",
                        project_id=self._project_id,
                    )
            except Exception as exc:
                logger.warning(
                    "Async ACNR full_resolve failed for %s!%s: %s",
                    cur_sheet,
                    cur_cell,
                    exc,
                )

            if acnr_result and acnr_result.found and acnr_result.addr_id:
                uri = acnr_result.addr_id
                resolve_missed = False
            else:
                uri = f"{cur_sheet}!{cur_cell}"

            # Cycle detection
            if uri in visited:
                chain.append(
                    RefChainNode(
                        depth=depth,
                        uri=uri,
                        cycle=True,
                        resolve_missed=resolve_missed,
                    )
                )
                has_cycle = True
                continue

            visited.add(uri)

            # Extract cell value and formula
            value, formula = _extract_cell_from_snapshot(
                parsed_data, cur_sheet, cur_cell
            )

            # Check if target is missing
            missing = self._is_missing(parsed_data, cur_sheet, cur_cell)

            node = RefChainNode(
                depth=depth,
                uri=uri,
                value=value,
                formula=formula,
                missing=missing,
                resolve_missed=resolve_missed,
            )
            chain.append(node)

            # Depth termination
            if depth >= max_depth:
                node.truncated = True
                if truncated_at_depth is None:
                    truncated_at_depth = depth
                continue

            # Parse cross-sheet references from formula
            refs = parse_cross_sheet_refs(formula)
            for ref_sheet, ref_cell in refs:
                queue.append((ref_sheet, ref_cell, depth + 1))

        return RefChainResponse(
            chain=chain,
            has_cycle=has_cycle,
            truncated_at_depth=truncated_at_depth,
        )


# Module-level singleton
cross_sheet_resolver = CrossSheetResolver()
