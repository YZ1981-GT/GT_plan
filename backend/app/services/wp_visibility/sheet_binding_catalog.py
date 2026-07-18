"""服务端 sheet binding catalog（Task 4 / 组件 C4）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 4.4：``sheet_name`` 只能在已确定的 project+wp_index+version 联合上下文内解释。
  - 4.5：禁止 ``sheet_name`` 全局唯一推断（本 catalog 只在单一 wp_index 内解析，天然满足）。
  - 5.8：Row_Assignee/Operation_Reviewer 仅凭程序行身份时，Page_Visibility_Set 限定为对应
    ProcedureRowTask 映射的 Sheet_Key 集合。
  - 5.9：仅凭程序行身份请求某 wp_index 的 **未映射** Sheet_Key → External_Not_Found（本 catalog
    以 ``unmapped`` 拒绝，供 gate 转 404）。
  - 5.10/5.11：Workpaper_Lead 整张底稿；多身份并集（页面集由 catalog 提供成员判定）。
  - 8.3：gate 判定页面级资源时校验服务端解析的 wp_index 与 Sheet_Key 属于允许范围。
  - 8.4：客户端提供的页面绑定与服务端解析不一致 → 拒绝（catalog 提供权威 sheet_key 集合）。
Design: 组件 C4（server-side sheet binding catalog）/ Property 4 / Property 7。

**权威来源**：某 project+wp_index 的稳定 sheet_key 集合与 ``sheet_name→sheet_key`` 映射
取自 **该 wp_index 下 active ProcedureRowTask** 的 ``(sheet_key, sheet_name)`` 快照
（materialization 时写入，见 ``procedure_task_materialization_service``）。行任务是"先委派后生成
底稿"的项目级真源，其 sheet_key/sheet_name 恰好落在"已确定 project+wp_index+version"上下文内，
因此不做任何全局推断。

**version 说明**：当前数据模型中 ProcedureRowTask 的 sheet_key/sheet_name 不随底稿文件版本
（``working_paper.file_version``）变化——程序行的稳定 sheet 身份跨版本不变。catalog 记录 version
以满足"在确定 version 内解析"的语义契约；sheet_key 成员集本身与 version 无关。
（GAP 提示：若未来引入按版本裁剪的 sheet，需在 build() 内追加版本过滤。）

**row-only 不可映射即拒绝**：checklist item / render sheet / row task 无法在本 wp_index 内唯一
映射到 sheet_key 时一律 ``unmapped``/``ambiguous`` 拒绝，**绝不** 退化为整稿授权（Req 5.9）。

约定：build() 纯读；解析方法为纯函数（无 IO）。asyncpg 用等值/小集合查询。
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureRowTask

# 从 checklist item_id / 任意字符串头部提取 sheet 级编码 token（如 D2A / D2-7 / G1A / K10-6）。
_CODE_TOKEN_RE = re.compile(r"^([A-Za-z]+\d+(?:-\d+)?[A-Za-z]?)")
# sheet 级编码 → 底稿基码（D2A→D2 / D2-7A→D2-7），与 materialization 的 _base_wp_code 对齐。
_BASE_CODE_RE = re.compile(r"^([A-Za-z]+\d+(?:-\d+)?)")


def _norm_sheet_name(name: str | None) -> str:
    """sheet_name 归一：去除所有空白（含全角空格/tab），大小写保留。

    与 render-config sheet 名过滤"忽略空白"匹配一致（前端注册表 label 与 xlsx 真实 sheet 名
    常差一个空格，如「…程序表J1A」vs「…程序表 J1A」）。
    """
    if not name:
        return ""
    return re.sub(r"[\s\u3000]+", "", name).strip()


def _norm_code(code: str | None) -> str:
    """sheet_key / 编码 token 归一：去空白后大写。"""
    if not code:
        return ""
    return re.sub(r"[\s\u3000]+", "", code).strip().upper()


def _base_of(code: str) -> str:
    """编码 → 基码（去尾字母 / 保留 -N 段），无法解析原样返回归一值。"""
    norm = _norm_code(code)
    m = _BASE_CODE_RE.match(norm)
    return m.group(1) if m else norm


class SheetResolveReason(str, enum.Enum):
    """sheet 解析拒绝原因（对外统一 External_Not_Found；内部 sheet_unmapped 家族）。"""

    empty = "empty"          # 输入为空
    unmapped = "unmapped"    # 本 wp_index 内 0 候选（Req 5.9 sheet_unmapped）
    ambiguous = "ambiguous"  # 本 wp_index 内 >1 候选（不可唯一映射 → 拒绝，不退化整稿）


@dataclass(frozen=True)
class SheetResolution:
    """sheet_name / sheet_key / checklist item → 稳定 sheet_key 的解析结果（不可变）。"""

    ok: bool
    sheet_key: str | None
    reason: SheetResolveReason | None = None


@dataclass(frozen=True)
class SheetBindingCatalog:
    """某 project+wp_index+version 内的权威 sheet 绑定目录（不可变）。

    - ``sheet_keys``：本 wp_index 的稳定 sheet_key 集合（canonical，原样保留大小写）。
    - ``_norm_key_to_canonical``：归一 sheet_key → canonical sheet_key。
    - ``_norm_name_to_keys``：归一 sheet_name → canonical sheet_key 集合（可能多对一/一对多）。
    - ``_base_to_keys``：sheet_key 基码 → canonical sheet_key 集合（供 checklist item 基码匹配）。
    """

    project_id: UUID
    wp_index_id: UUID
    version: str | None
    sheet_keys: frozenset[str]
    _norm_key_to_canonical: Mapping[str, str]
    _norm_name_to_keys: Mapping[str, frozenset[str]]
    _base_to_keys: Mapping[str, frozenset[str]]

    # ------------------------------------------------------------------
    # 构建（纯读；权威来源 = 该 wp_index 下 active ProcedureRowTask 的 (sheet_key, sheet_name)）
    # ------------------------------------------------------------------
    @classmethod
    async def build(
        cls,
        db: AsyncSession,
        project_id: UUID,
        wp_index_id: UUID,
        version: str | None = None,
    ) -> "SheetBindingCatalog":
        rows = (
            await db.execute(
                sa.select(
                    sa.distinct(ProcedureRowTask.sheet_key),
                    ProcedureRowTask.sheet_name,
                ).where(
                    ProcedureRowTask.project_id == project_id,
                    ProcedureRowTask.wp_index_id == wp_index_id,
                    ProcedureRowTask.is_deleted == sa.false(),
                )
            )
        ).all()

        sheet_keys: set[str] = set()
        norm_key_to_canonical: dict[str, str] = {}
        norm_name_to_keys: dict[str, set[str]] = {}
        base_to_keys: dict[str, set[str]] = {}

        for sheet_key, sheet_name in rows:
            if not sheet_key:
                continue
            canonical = sheet_key.strip()
            sheet_keys.add(canonical)
            norm_key_to_canonical.setdefault(_norm_code(canonical), canonical)
            base_to_keys.setdefault(_base_of(canonical), set()).add(canonical)
            nname = _norm_sheet_name(sheet_name)
            if nname:
                norm_name_to_keys.setdefault(nname, set()).add(canonical)

        return cls(
            project_id=project_id,
            wp_index_id=wp_index_id,
            version=version,
            sheet_keys=frozenset(sheet_keys),
            _norm_key_to_canonical=MappingProxyType(dict(norm_key_to_canonical)),
            _norm_name_to_keys=MappingProxyType(
                {k: frozenset(v) for k, v in norm_name_to_keys.items()}
            ),
            _base_to_keys=MappingProxyType(
                {k: frozenset(v) for k, v in base_to_keys.items()}
            ),
        )

    # ------------------------------------------------------------------
    # 纯函数解析
    # ------------------------------------------------------------------
    def is_empty(self) -> bool:
        return not self.sheet_keys

    def contains(self, sheet_key: str | None) -> bool:
        """sheet_key 是否属于本 wp_index 的权威集合（归一比较）。"""
        return _norm_code(sheet_key) in self._norm_key_to_canonical

    def resolve_sheet_key(self, sheet_key: str | None) -> SheetResolution:
        """校验 sheet_key 属于本 wp_index（成员校验，Req 8.3/8.4）。"""
        norm = _norm_code(sheet_key)
        if not norm:
            return SheetResolution(False, None, SheetResolveReason.empty)
        canonical = self._norm_key_to_canonical.get(norm)
        if canonical is None:
            return SheetResolution(False, None, SheetResolveReason.unmapped)
        return SheetResolution(True, canonical, None)

    def resolve_sheet_name(self, sheet_name: str | None) -> SheetResolution:
        """sheet_name → 稳定 sheet_key（仅在本 wp_index 内，Req 4.4/4.5）。

        0 候选 → ``unmapped``；>1 候选 → ``ambiguous``（不可唯一映射，拒绝，不退化整稿）。
        """
        nname = _norm_sheet_name(sheet_name)
        if not nname:
            return SheetResolution(False, None, SheetResolveReason.empty)
        keys = self._norm_name_to_keys.get(nname)
        if not keys:
            return SheetResolution(False, None, SheetResolveReason.unmapped)
        if len(keys) > 1:
            return SheetResolution(False, None, SheetResolveReason.ambiguous)
        return SheetResolution(True, next(iter(keys)), None)

    def resolve_checklist_item(self, item_id: str | None) -> SheetResolution:
        """checklist item_id → 稳定 sheet_key（仅在本 wp_index 内）。

        策略（确定性、fail-closed）：
          1. 从 item_id 头部提取编码 token（如 ``D2-7-voucher-check`` → ``D2-7``）。
          2. token 归一后若直接命中某 sheet_key → 唯一解析。
          3. 否则按基码匹配：token 基码 == 某 sheet_key 基码，唯一命中 → 解析；0/多 → 拒绝。
        无法唯一映射 → ``unmapped``/``ambiguous``，绝不退化整稿授权（Req 5.9）。
        """
        raw = (item_id or "").strip()
        if not raw:
            return SheetResolution(False, None, SheetResolveReason.empty)
        m = _CODE_TOKEN_RE.match(raw)
        if not m:
            return SheetResolution(False, None, SheetResolveReason.unmapped)
        token = m.group(1)
        # ② 直接命中 sheet_key
        canonical = self._norm_key_to_canonical.get(_norm_code(token))
        if canonical is not None:
            return SheetResolution(True, canonical, None)
        # ③ 基码唯一匹配
        keys = self._base_to_keys.get(_base_of(token))
        if not keys:
            return SheetResolution(False, None, SheetResolveReason.unmapped)
        if len(keys) > 1:
            return SheetResolution(False, None, SheetResolveReason.ambiguous)
        return SheetResolution(True, next(iter(keys)), None)

    def resolve_row_task(self, task: ProcedureRowTask) -> SheetResolution:
        """ProcedureRowTask → 稳定 sheet_key（直取 task.sheet_key 并校验属于本 wp_index）。

        row-only 入口经此解析；task.sheet_key 不在本 wp_index 权威集合内即拒绝
        （防止跨 wp_index 的 task 误落到本 catalog）。
        """
        if task is None or getattr(task, "sheet_key", None) is None:
            return SheetResolution(False, None, SheetResolveReason.empty)
        return self.resolve_sheet_key(task.sheet_key)
