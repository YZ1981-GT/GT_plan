"""AddressingService — 统一寻址层（替换 per-URI-prefix 解析逻辑）

高级查询模块的唯一寻址入口。所有查询目标、回写目标、结果列下钻都经此层，
统一消费 ACNR 的单一 resolve 出口 `full_resolve`（async、kw-only，返回
`ResolveResult`），不重写 ACNR 核心、不自建命名/坐标表。

设计定位（design.md §Components 1）：
  - `resolve_target(raw, *, project_id, db, timeout_s=5.0)`：
      归一输入 → `asyncio.wait_for(full_resolve(...), timeout=5.0)`；
      `found=True` 采用 `ResolveResult.addr_id` 作 canonical 身份并附 `wp_id`；
      超时 / resolve 不可用 → `error="resolve_unavailable"`。
  - `resolve_many(raws, *, project_id, db)`：`asyncio.gather` 并发解析；
      封装 ACNR 出口不重写；上层按 R1.4 归集 `found=False` 清单、整体不执行。

输入语法（归一顺序，语法糖在入口即收敛为 ACNR 输入形态，单点解析）：
  - 含 `://` → 五域 URI（wp/tb/report/note/aux）
  - `report:` / `note:` / `adj:` / `tb:` 用户输入语法糖（历史 `{module}:{qualifier}|{cell_range}`
    形态，替换 `custom_query.py` 各前缀分支与 `module_cell_resolver.resolve`）→ 归一为
    ACNR URI（report/note/tb）或索引 ns 引用（adj，非 V1 URI 域）
  - `FUNC(...)` 形态 → 公式引用（WP()/TB()/ROW()/NOTE()/AUX()/...）
  - `ns:target` 形态（单冒号、ns 为标识符）→ 索引命名空间引用
  - 其余（形如 `{wp_code}/{sheet_code}/{coordinate_key}`）→ 裸 addr_id

不可解析归集（R1.4「全有或全无」）：`resolve_all` / `resolve_all_or_raise` 在任一目标
`found=False` 时逐项归集无法解析清单、整体不执行、不返回部分结果
（`TARGET_UNRESOLVABLE`，含 `unresolved: [...]`）。

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.5, 4.2, 4.4
属性: P1, P4
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.acnr.resolver import full_resolve

logger = logging.getLogger(__name__)

# resolve 默认超时（秒）——R1.5 / R3.5：resolve 不可用或无响应即中止
DEFAULT_RESOLVE_TIMEOUT_S = 5.0

# ─── 错误码常量（与 design.md Error Handling / ResolvedTarget.error 对齐）─────
ERR_UNRESOLVABLE = "unresolvable"          # 目标无法被解析为有效 addr_id（R1.4/R3.4）
ERR_RESOLVE_UNAVAILABLE = "resolve_unavailable"  # resolve 不可用/超时（R1.5/R3.5）
ERR_AMBIGUOUS = "ambiguous"                # 同 sheet 多候选（R5.5，透传自 full_resolve）

# 归集层 error_code（design.md Error Handling 表；供 router 转 HTTP 状态）
#   TARGET_UNRESOLVABLE → HTTP 400（含 unresolved: [...]），R1.4
#   RESOLVE_UNAVAILABLE → HTTP 503（resolve 服务不可用），R1.5
ERR_CODE_TARGET_UNRESOLVABLE = "TARGET_UNRESOLVABLE"
ERR_CODE_RESOLVE_UNAVAILABLE = "RESOLVE_UNAVAILABLE"


@dataclass
class ResolvedTarget:
    """统一寻址结果 — 查询/回写/下钻的 canonical 身份载体。

    Fields per design.md §Components 1:
      raw:        用户原始输入（report:/note:/tb:/addr_id/uri/formula_ref）
      found:      是否成功解析为有效 addr_id
      addr_id:    canonical {wp_code}/{sheet_code}/{coordinate_key}
      wp_id:      带 project_id 且命中时附加（resolve_instance 出口）
      jump_route: 前端跳转出口（GtIndexChip 下钻用）
      entry_type: sheet/cell/runtime_cell/tb/report/note/aux
      error:      unresolvable / resolve_unavailable / ambiguous
    """

    raw: str
    found: bool
    addr_id: Optional[str] = None
    wp_id: Optional[str] = None
    jump_route: Optional[str] = None
    entry_type: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ResolveManyOutcome:
    """`resolve_all` 的「全有或全无」归集结果（R1.4）。

    Fields:
      ok:         是否全部目标成功解析（无任一 found=False）
      resolved:   全部解析成功的目标（`ok=False` 时为空——不返回部分结果）
      unresolved: 无法解析清单，逐项 {raw, error}
      error_code: 归集层错误码（TARGET_UNRESOLVABLE / RESOLVE_UNAVAILABLE），
                  ok=True 时为 None
    """

    ok: bool
    resolved: list[ResolvedTarget]
    unresolved: list[dict]
    error_code: Optional[str] = None


class TargetUnresolvableError(Exception):
    """任一查询目标无法解析时抛出（R1.4「全有或全无」）。

    携带 `error_code`（TARGET_UNRESOLVABLE / RESOLVE_UNAVAILABLE）与逐项
    `unresolved` 清单，供 router 层转为统一错误契约
    （`detail={error_code, message, unresolved}`，HTTP 400 / 503）。
    """

    def __init__(
        self,
        unresolved: list[dict],
        *,
        error_code: str = ERR_CODE_TARGET_UNRESOLVABLE,
        message: Optional[str] = None,
    ) -> None:
        self.error_code = error_code
        self.unresolved = unresolved
        raws = ", ".join(str(u.get("raw")) for u in unresolved) or "(none)"
        self.message = message or f"以下查询目标无法解析：{raws}"
        super().__init__(self.message)


# ─── 输入归类 ────────────────────────────────────────────────────────────────

# 公式引用：以 大写/下划线 标识符 + '(' 开头，如 WP( / TB( / SUM_ROW( / NOTE(
_FORMULA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\(")
# 索引命名空间：ns 为标识符 + ':'（单冒号，非 '://'），如 cell:D2-2!E100 / tb:1001
_INDEX_NS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:")

# ─── report:/note:/adj:/tb: 用户输入语法糖归一（R1.6 单点收敛）─────────────────
# 历史 custom_query 语法糖形态：{module}:{qualifier}|{cell_range}
#   report:balance_sheet|C5:C10 / note:五-1-1|C3:D8 / adj:aje|B2:E10 / tb:detail|C1:C50
# 归一目标：report/note/tb 三域走 ACNR V1 URI（{domain}://{source}#{cell}），
#           adj 非 V1 URI 域 → 归一为索引 ns 引用（ACNR full_resolve 内部委托处理）。
_SUGAR_PREFIXES = ("report:", "note:", "adj:", "tb:")
# 属于 ACNR V1 URI 五域的语法糖模块（可直接构 URI）；adj 不在其中
_SUGAR_URI_DOMAINS = {"report", "note", "tb"}


def _normalize_sugar(s: str) -> Optional[dict[str, str]]:
    """将 `report:/note:/adj:/tb:` 用户输入语法糖归一为 ACNR 输入形态。

    这是替换 `module_cell_resolver.resolve` 与 `custom_query.py` 各前缀分支的
    入口归一逻辑：语法糖在此单点收敛为 `full_resolve` 的单键 kwarg，后续解析
    完全由 ACNR full_resolve 承担（消费 ACNR 出口，不重写 ACNR 核心）。

    形态：`{module}:{qualifier}[|{cell_range}]`
      - report/note/tb（V1 URI 域）→ {"uri": "{module}://{qualifier}[#{cell_range}]"}
      - adj（非 V1 URI 域）        → {"index_ref": "adj:{qualifier}"}

    Returns:
        full_resolve 单键 kwarg 字典；若非语法糖或 qualifier 为空 → None
        （None 时由 `_classify_input` 继续后续归类，最终归为 unresolvable）。
    """
    for prefix in _SUGAR_PREFIXES:
        if not s.startswith(prefix):
            continue
        module = prefix[:-1]  # 去掉尾部 ':'
        tail = s[len(prefix):]
        # 剥离历史语法糖的 |cell_range 段，保留至 URI 的 #cell 片段供下游取用
        qualifier, _sep, cell_range = tail.partition("|")
        qualifier = qualifier.strip()
        cell_range = cell_range.strip()
        if not qualifier:
            # 空 qualifier → 非法语法糖，退回通用归类（最终 unresolvable）
            return None
        if module in _SUGAR_URI_DOMAINS:
            uri = f"{module}://{qualifier}"
            if cell_range:
                uri += f"#{cell_range}"
            return {"uri": uri}
        # adj：归一为索引 ns 引用（cell_range 不入 ACNR 索引语法，丢弃于寻址层）
        return {"index_ref": f"{module}:{qualifier}"}
    return None


def _classify_input(raw: str) -> dict[str, str]:
    """将原始输入归类为 full_resolve 的单一 kwarg。

    返回形如 {"uri": ...} / {"formula_ref": ...} / {"index_ref": ...} /
    {"addr_id": ...} 的单键字典，直接作为 full_resolve 的关键字参数展开。

    归一顺序（语法糖在通用索引 ns 归类之前收敛，确保单点解析）：
      URI → 语法糖 → 公式 → 索引 ns → 裸 addr_id
    """
    s = raw.strip()

    # 1) 五域 URI（含 scheme 分隔 '://'）
    if "://" in s:
        return {"uri": s}

    # 2) report:/note:/adj:/tb: 语法糖归一（R1.6 单点收敛，先于通用索引 ns）
    sugar = _normalize_sugar(s)
    if sugar is not None:
        return sugar

    # 3) 公式引用（FUNC(...) 形态）
    if _FORMULA_RE.match(s):
        return {"formula_ref": s}

    # 4) 索引命名空间引用（ns:target，单冒号且非 URI）
    #    注意：canonical addr_id 用 '/' 分段、不含前导 'ns:'，故先判索引再退化 addr_id
    if _INDEX_NS_RE.match(s):
        return {"index_ref": s}

    # 5) 退化为裸 addr_id
    return {"addr_id": s}


class AddressingService:
    """统一寻址服务 — 唯一寻址入口，封装 ACNR full_resolve 出口。"""

    async def resolve_target(
        self,
        raw: str,
        *,
        project_id: str | None = None,
        db: AsyncSession | None = None,
        timeout_s: float = DEFAULT_RESOLVE_TIMEOUT_S,
    ) -> ResolvedTarget:
        """解析单个目标为 canonical addr_id 身份。

        - 归一输入 → `asyncio.wait_for(full_resolve(...), timeout=timeout_s)`。
        - `found=True` → 采用 `ResolveResult.addr_id` 作 canonical 身份，
          带 project_id 时 full_resolve 已附 `wp_id`（`_attach_wp_id`）。
        - 超时 / resolve 抛错 → `error="resolve_unavailable"`（R1.5/R3.5）。
        - `found=False` → `error` 透传（ambiguous）或归为 `unresolvable`（R1.4/R3.4）。
        """
        kwargs = _classify_input(raw)

        try:
            result = await asyncio.wait_for(
                full_resolve(project_id=project_id, db=db, **kwargs),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning("resolve_target timeout: raw=%s timeout=%ss", raw, timeout_s)
            return ResolvedTarget(
                raw=raw, found=False, error=ERR_RESOLVE_UNAVAILABLE
            )
        except Exception as exc:  # resolve 依赖故障 → 视为不可用，中止（不返回部分结果）
            logger.warning("resolve_target failed: raw=%s error=%s", raw, exc)
            return ResolvedTarget(
                raw=raw, found=False, error=ERR_RESOLVE_UNAVAILABLE
            )

        if not result.found:
            return ResolvedTarget(
                raw=raw,
                found=False,
                entry_type=result.entry_type,
                error=result.error or ERR_UNRESOLVABLE,
            )

        return ResolvedTarget(
            raw=raw,
            found=True,
            addr_id=result.addr_id,
            wp_id=result.wp_id,
            jump_route=result.jump_route,
            entry_type=result.entry_type,
            error=None,
        )

    async def resolve_many(
        self,
        raws: list[str],
        *,
        project_id: str | None = None,
        db: AsyncSession | None = None,
        timeout_s: float = DEFAULT_RESOLVE_TIMEOUT_S,
    ) -> list[ResolvedTarget]:
        """并发解析多个目标，返回与输入同序的结果列表。

        用 `asyncio.gather` 并发解析（封装 ACNR 出口，不重写）；结果顺序与
        `raws` 一致。上层按 R1.4「全有或全无」：任一 `found=False` 时归集
        无法解析清单、整体不执行、不返回部分结果。
        """
        if not raws:
            return []

        return list(
            await asyncio.gather(
                *(
                    self.resolve_target(
                        raw, project_id=project_id, db=db, timeout_s=timeout_s
                    )
                    for raw in raws
                )
            )
        )

    async def resolve_all(
        self,
        raws: list[str],
        *,
        project_id: str | None = None,
        db: AsyncSession | None = None,
        timeout_s: float = DEFAULT_RESOLVE_TIMEOUT_S,
    ) -> ResolveManyOutcome:
        """「全有或全无」归集解析（R1.4）。

        并发解析全部目标；只要存在至少一个 `found=False`，即：
          - 逐项归集无法解析清单（保留原始输入 + 各自 error）
          - 整体不执行、不返回部分结果（`resolved` 置空）
          - 归集 error_code：任一目标为 resolve 不可用/超时 → `RESOLVE_UNAVAILABLE`
            （R1.5，服务不可用更需明示）；否则 → `TARGET_UNRESOLVABLE`（R1.4）

        全部成功时返回 `ok=True` + 与输入同序的 `resolved`。
        """
        results = await self.resolve_many(
            raws, project_id=project_id, db=db, timeout_s=timeout_s
        )

        unresolved = [
            {"raw": r.raw, "error": r.error or ERR_UNRESOLVABLE}
            for r in results
            if not r.found
        ]

        if unresolved:
            error_code = (
                ERR_CODE_RESOLVE_UNAVAILABLE
                if any(u["error"] == ERR_RESOLVE_UNAVAILABLE for u in unresolved)
                else ERR_CODE_TARGET_UNRESOLVABLE
            )
            # all-or-nothing：不返回任何部分 resolved
            return ResolveManyOutcome(
                ok=False,
                resolved=[],
                unresolved=unresolved,
                error_code=error_code,
            )

        return ResolveManyOutcome(
            ok=True, resolved=results, unresolved=[], error_code=None
        )

    async def resolve_all_or_raise(
        self,
        raws: list[str],
        *,
        project_id: str | None = None,
        db: AsyncSession | None = None,
        timeout_s: float = DEFAULT_RESOLVE_TIMEOUT_S,
    ) -> list[ResolvedTarget]:
        """`resolve_all` 的抛出型封装：任一不可解析即 `TargetUnresolvableError`。

        供 router / orchestrator 层直接 await 并将异常转为统一错误契约
        （`TARGET_UNRESOLVABLE` / `RESOLVE_UNAVAILABLE`）。成功时返回全部
        解析结果（与输入同序）。
        """
        outcome = await self.resolve_all(
            raws, project_id=project_id, db=db, timeout_s=timeout_s
        )
        if not outcome.ok:
            raise TargetUnresolvableError(
                outcome.unresolved, error_code=outcome.error_code or ERR_CODE_TARGET_UNRESOLVABLE
            )
        return outcome.resolved


# 模块级单例（与 module_cell_resolver 一致的使用范式）
addressing_service = AddressingService()
