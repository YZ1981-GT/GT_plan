# Design Document — ACNR Consumer Wiring

## Overview

本设计将 4 个优先级消费者（CrossSheetResolver、EventBus失效链、LinkageGraphBuilder、StalePropagationEngine）+ 3 个新增服务（stale_impact 端点、Bulk Export 服务、CustomQueryFieldPicker 组件）接入 ACNR 统一解析体系。核心设计原则：**strangler-fig 模式**（旧路径保留为 fallback，新路径优先），**addr_id 作为唯一节点标识**，**容错不中断**（ACNR 异常时降级到旧逻辑）。

## Architecture

### 数据流全景图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          EVENT-DRIVEN FLOW                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  WORKPAPER_SAVED ──▶ acnr/events.invalidate() ──┬──▶ L3 Runtime clear   │
│                                                  ├──▶ L2 Overlay clear   │
│                                                  ├──▶ ReverseIndex clear │
│                                                  └──▶ Legacy V1 delegate │
│                                                                          │
│  LinkageGraphBuilder.build() ──▶ _normalize_wp_uri_to_addr_id() ─┐      │
│                                                                   ▼      │
│  unified_dependency_graph.json (addr_id keyed WP nodes)                  │
│         │                                                                │
│         ▼                                                                │
│  StalePropagationEngine.reload_graph() ──▶ addr_id index rebuilt         │
│         │                                                                │
│         ▼                                                                │
│  on_change(source) ──▶ detect_format() ──▶ normalize ──▶ BFS ──▶ mark   │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                         REQUEST-DRIVEN FLOW                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  CrossSheetResolver.resolve(formula)                                     │
│      │                                                                   │
│      ├──▶ full_resolve(formula_ref=..., project_id=...) ──┬─ found=true  │
│      │                                                     │  → use      │
│      │                                                     │    addr_id  │
│      │                                                     │             │
│      │                                                     └─ found=false│
│      │                                                        → snapshot │
│      │                                                          fallback │
│      └──▶ exception → log warning → snapshot fallback                    │
│                                                                          │
│  GET /api/linkage-bus/impact-by-addr?addr_id=D2/D2-2/E100               │
│      │                                                                   │
│      └──▶ StalePropagationEngine.on_change(addr_id) ──▶ BFS response    │
│                                                                          │
│  Bulk Export: manifest.list_import_export(cycle)                         │
│      │                                                                   │
│      └──▶ topo_sort(depends_on_sheets) ──▶ ordered sheet list            │
│              │                                                           │
│              └──▶ for each: GET {api_prefix}/{wp_id}/{item_id}           │
│                                                                          │
│  CustomQueryFieldPicker                                                  │
│      │                                                                   │
│      └──▶ useAcnr().buildAddressTree(cycle) ──▶ tree nodes              │
│              │                                                           │
│              └──▶ useAcnr().loadCellNodes(entry) ──▶ cell children       │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 层次关系

```
┌─────────────────────────────────────────┐
│  Frontend (Vue)                          │
│  ┌───────────────────────────────────┐  │
│  │ CustomQueryFieldPicker            │  │
│  │   └── useAcnr composable         │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │ useStaleImpact (已有)             │  │
│  │   └── /api/linkage-bus/impact-by-addr │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Backend API Layer                       │
│  ┌───────────────────────────────────┐  │
│  │ linkage_bus.py                    │  │
│  │   ├── POST /impact (已有)         │  │
│  │   └── GET /impact-by-addr (新增)  │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │ wp_bulk_tab_export.py (新增)      │  │
│  │   └── manifest.list_import_export │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Service Layer                           │
│  ┌─────────────────┐  ┌──────────────┐  │
│  │ CrossSheetResolver│  │ StalePropEng │  │
│  │   → full_resolve │  │   → addr_id  │  │
│  │   → fallback     │  │     indexing │  │
│  └─────────────────┘  └──────────────┘  │
│  ┌─────────────────┐  ┌──────────────┐  │
│  │ LinkageGraphBld  │  │ acnr/events │  │
│  │   → normalize    │  │   → invalid. │  │
│  │   → addr_id keys │  │   → rev_idx  │  │
│  └─────────────────┘  └──────────────┘  │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  ACNR Core (已完成)                      │
│  ├── resolver.py (full_resolve)         │
│  ├── catalog.py (L1 静态目录)           │
│  ├── overlay.py (L2 项目覆盖)           │
│  ├── runtime.py (L3 运行时条目)         │
│  └── manifest.py (I/E 清单)             │
└─────────────────────────────────────────┘
```

## Components and Interfaces

### 1. CrossSheetResolver Enhancement

**文件**: `backend/app/services/custom_query/cross_sheet_resolver.py`

修改现有 `CrossSheetResolver.resolve()` 方法，在 BFS 循环内对每个跨 sheet 引用先调 `full_resolve`，命中则使用 `addr_id` 作为 node URI，未命中则 fallback 到现有 snapshot 提取。

```python
from app.services.acnr.resolver import full_resolve, ResolveResult

class CrossSheetResolver:
    def __init__(self, project_id: str | None = None):
        self._project_id = project_id

    def resolve(
        self,
        parsed_data: dict | None,
        sheet_name: str,
        cell_ref: str,
        max_depth: int = 3,
    ) -> RefChainResponse:
        max_depth = min(max_depth, 3)
        queue: deque[tuple[str, str, int]] = deque()
        queue.append((sheet_name, cell_ref.upper(), 0))
        visited: set[str] = set()
        chain: list[RefChainNode] = []
        has_cycle = False
        truncated_at_depth: int | None = None

        while queue:
            cur_sheet, cur_cell, depth = queue.popleft()

            # ── ACNR full_resolve 尝试 ──────────────────────────
            acnr_result: ResolveResult | None = None
            try:
                acnr_result = _sync_resolve(
                    formula_ref=f"WP('{cur_sheet}','{cur_cell}')",
                    project_id=self._project_id,
                )
            except Exception as exc:
                logger.warning(
                    "ACNR full_resolve failed for %s!%s: %s",
                    cur_sheet, cur_cell, exc,
                )

            # 确定 node URI
            if acnr_result and acnr_result.found and acnr_result.addr_id:
                uri = acnr_result.addr_id
                resolve_missed = False
            else:
                uri = f"{cur_sheet}!{cur_cell}"
                resolve_missed = True

            # 环检测、snapshot 提取、BFS 继续...（保持现有逻辑）
            if uri in visited:
                chain.append(RefChainNode(depth=depth, uri=uri, cycle=True))
                has_cycle = True
                continue
            visited.add(uri)

            value, formula = _extract_cell_from_snapshot(parsed_data, cur_sheet, cur_cell)
            missing = self._is_missing(parsed_data, cur_sheet, cur_cell)

            node = RefChainNode(
                depth=depth, uri=uri, value=value, formula=formula,
                missing=missing, resolve_missed=resolve_missed,
            )
            chain.append(node)

            if depth >= max_depth:
                node.truncated = True
                if truncated_at_depth is None:
                    truncated_at_depth = depth
                continue

            refs = parse_cross_sheet_refs(formula)
            for ref_sheet, ref_cell in refs:
                queue.append((ref_sheet, ref_cell, depth + 1))

        return RefChainResponse(
            chain=chain, has_cycle=has_cycle, truncated_at_depth=truncated_at_depth,
        )
```

**关键设计决策**:
- **sync→async 桥接（风险修复）**：`full_resolve` 是 async，`CrossSheetResolver.resolve` 是同步 BFS，且在 FastAPI 请求线程内**已有运行中的 event loop** —— 此时 `asyncio.run()` / `loop.run_until_complete()` 会抛 `RuntimeError: This event loop is already running`。`_sync_resolve` 的实现策略（择一，按可行性排序）：
  1. **首选：把 `resolve()` 本身改为 `async def`**，BFS 内直接 `await full_resolve(...)`，所有调用方（同步）改为 `await` 或经现有 async 端点调用。这是最干净、无线程风险的方案。
  2. 若调用方无法改 async：`_sync_resolve` 用 `concurrent.futures` + `asyncio.run_coroutine_threadsafe(coro, loop)` 投递到**另一线程的 loop**，或在无 loop 上下文用 `asyncio.run()`。需 `try: loop=asyncio.get_running_loop()` 探测当前是否有 loop 决定分支。
  3. **兜底：不阻塞 BFS 的降级** —— 若桥接失败（如探测到 running loop 且无旁路 loop），直接走 snapshot fallback + `resolve_missed=True`，不得抛异常中断 BFS（容错第一）。
- **WP() 参数形态（风险修复）**：grammar_v1 期望 `WP(parent, sheet, cell)`（3 参），而 CrossSheetResolver 上下文只有 `sheet_name + cell`，通常**无 parent wp_code**。构造 `WP('sheet','cell')`（2 参）会 miss。策略：
  1. 若 `self._parent_wp_code` 已知（构造函数可选传入），构造 3 参 `WP('{parent}','{sheet}','{cell}')`；
  2. 否则优先用 **URI 形态** `wp://{sheet}/{cell}` 或 addr_id 形态交给 `full_resolve(uri=...)`，让 resolver 的 sheet-alias/custom_flat 分支去匹配；
  3. 仍 miss → `resolve_missed=True` + snapshot fallback（不影响链路完整性）。构造函数因此新增可选 `parent_wp_code: str | None = None`。
- `RefChainNode` 新增 `resolve_missed: bool = False` 字段（向后兼容，默认 False）。
- 异常只 log warning，不中断 BFS（容错第一）。
- **性能**：BFS 每节点一次 resolve，`max_depth ≤ 3` 且 `full_resolve` 命中走 L1 内存 catalog（无 DB），开销可接受；若传 `project_id` 但不传 `db`，则跳过 wp_id attach（node URI 只需 addr_id，无需 wp_id）。

### 2. Events.py Invalidation Chain Enhancement

**文件**: `backend/app/services/acnr/events.py`

在现有 `invalidate()` 函数中，L2 overlay clear 之后、legacy delegate 之前，插入 `invalidate_reverse_index()` 调用。

```python
async def invalidate(
    project_id: str, *,
    wp_id: str | None = None,
    addr_id: str | None = None,
    trigger: str | None = None,
    extra_sheets: list[str] | None = None,
) -> None:
    # Step 1: L3 RuntimeIndex clear
    try:
        from app.services.acnr.runtime import clear_runtime_entries
        clear_runtime_entries(project_id)
    except Exception as exc:
        logger.warning("acnr.invalidate L3 clear failed: %s", exc)

    # Step 2: L2 overlay clear
    try:
        from app.services.acnr.overlay import clear_project_overlays
        clear_project_overlays(project_id)
    except Exception as exc:
        logger.warning("acnr.invalidate L2 overlay clear failed: %s", exc)

    # Step 3: FormulaReverseIndex clear (NEW)
    try:
        from app.services.formula_reverse_index import invalidate_reverse_index
        invalidate_reverse_index()
    except Exception as exc:
        logger.warning("acnr.invalidate reverse_index clear failed: %s", exc)

    # Step 4: Legacy address_registry delegate
    try:
        from app.services.address_registry import address_registry
        await address_registry.invalidate_async(str(project_id), domain="wp")
    except Exception as exc:
        logger.warning("acnr.invalidate address_registry delegate failed: %s", exc)
```

**执行顺序**:  L3 → L2 → ReverseIndex → Legacy V1（每步独立 try/except，互不影响）。

### 3. LinkageGraphBuilder addr_id Normalization

**文件**: `backend/app/services/linkage_graph_builder.py`

新增 `_normalize_wp_uri_to_addr_id()` 纯函数，在所有 `_from_*` 方法中对 WP 域 URI 调用此函数做归一化。

```python
import re

# WP URI 格式: WP:{wp_code}:{sheet_display_name}:{cell_ref}
_WP_URI_PATTERN = re.compile(r"^WP:([^:]+):([^:]+):(.+)$")

# Sheet display name → sheet_code 映射（剥离中文前缀）
# 例: "明细表D2-2" → "D2-2", "审定表D2-1" → "D2-1"
_SHEET_CODE_PATTERN = re.compile(r"([A-Z]\d+(?:-\d+)?[A-Z]?)")


def _normalize_wp_uri_to_addr_id(uri: str) -> str:
    """将 WP:{wp_code}:{sheet_display}:{cell} 归一化为 addr_id。

    - WP 域: "WP:D2:明细表D2-2:E100" → "D2/D2-2/E100"
    - 非 WP 域: 原样返回（REPORT:*, TB:*, NOTE:*, etc.）

    sheet_code 提取策略:
    1. 从 sheet_display 中提取 [A-Z]\\d+(-\\d+)?[A-Z]? 模式
    2. 如无法提取则使用原始 sheet_display（保留可调试性）
    """
    m = _WP_URI_PATTERN.match(uri)
    if not m:
        return uri  # 非 WP 域，原样返回

    wp_code, sheet_display, cell = m.groups()

    # 提取 sheet_code
    code_match = _SHEET_CODE_PATTERN.search(sheet_display)
    sheet_code = code_match.group(1) if code_match else sheet_display

    return f"{wp_code}/{sheet_code}/{cell}"
```

在 `_from_prefill_mapping`、`_from_cross_wp_references`、`_from_l3_dependencies`、`_from_docx_placeholders` 中，所有 `target_uri` / `source_uri` 经 `_normalize_wp_uri_to_addr_id()` 处理后再入图。非 WP 域（REPORT、TB、NOTE、MAPPING）保留原 URI。

### 4. StalePropagationEngine addr_id Compatibility

**文件**: `backend/app/services/stale_propagation_engine.py`

改造 `on_change()` 和 `_load_graph()` 以支持 addr_id 格式。

```python
_LEGACY_WP_URI = re.compile(r"^WP:[^:]+:[^:]+:")  # 检测 WP:xx:xx: 前缀


def _detect_and_normalize(source_uri: str) -> str:
    """格式检测 + 归一化。

    - 含 'WP:' 前缀 + 多 ':' → legacy → 调 _normalize_wp_uri_to_addr_id
    - 含 '/' 无 ':' 前缀 → addr_id → 直接使用
    - 其他（REPORT:、TB: 等非 WP 域）→ 原样
    """
    if _LEGACY_WP_URI.match(source_uri):
        from app.services.linkage_graph_builder import _normalize_wp_uri_to_addr_id
        return _normalize_wp_uri_to_addr_id(source_uri)
    return source_uri


class StalePropagationEngine:
    def __init__(self) -> None:
        self._graph: dict[str, list[str]] = {}
        self._reverse_graph: dict[str, list[str]] = {}
        self._addr_id_index: dict[str, str] = {}  # addr_id → graph_key 映射
        self._degraded: bool = False
        self._loaded: bool = False
        self._load_graph()

    def _load_graph(self) -> None:
        # ... 现有加载逻辑 ...
        # 加载后构建 addr_id index
        self._build_addr_id_index()

    def _build_addr_id_index(self) -> None:
        """构建 addr_id → graph_key 的 O(1) 查找索引。"""
        self._addr_id_index.clear()
        for key in self._graph:
            self._addr_id_index[key] = key
            # 如果 key 是 addr_id 格式，也建立反向映射
            # 以便新旧两种格式都能匹配

    def reload_graph(self) -> None:
        self._graph.clear()
        self._reverse_graph.clear()
        self._addr_id_index.clear()
        self._loaded = False
        self._load_graph()

    async def on_change(self, source_uri: str, ...) -> dict[str, Any]:
        # 格式检测 + 归一化
        normalized = _detect_and_normalize(source_uri)
        # BFS 使用归一化后的 URI
        affected_uris = self._bfs(normalized, max_depth=5)
        # ... 后续逻辑不变 ...
```

### 5. stale_impact(addr_id) API Endpoint

**文件**: `backend/app/routers/linkage_bus.py`

新增 `GET /api/linkage-bus/impact-by-addr` 端点。

```python
@router.get("/impact-by-addr")
async def stale_impact_by_addr(
    addr_id: str = Query("", description="ACNR addr_id，如 D2/D2-2/E100"),
    max_depth: int = Query(3, ge=1, le=10, description="最大 BFS 深度"),
    project_id: str = Query(..., description="项目 ID"),
    year: int = Query(0, description="年度（可选）"),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """按 ACNR addr_id 查询下游影响（BFS 传播分析）。"""
    if not addr_id or not addr_id.strip():
        raise HTTPException(status_code=400, detail="addr_id is required")

    if stale_engine.is_degraded:
        raise HTTPException(
            status_code=503,
            detail="Stale propagation engine is in degraded mode",
        )

    result = await stale_engine.on_change(
        source_uri=addr_id,  # addr_id 格式直通
        project_id=project_id,
        year=year,
    )

    # 格式化响应
    affected_list = []
    for i, uri in enumerate(result.get("affected", [])):
        affected_list.append({
            "addr_id": uri,
            "depth": min(i + 1, max_depth),  # 近似深度
            "via_ref": None,
            "match_type": "graph_edge",
        })

    return {
        "addr_id": addr_id,
        "total_affected": result.get("total", 0),
        "affected": affected_list,
    }
```

### 6. Bulk Export Service (wp_bulk_tab_export.py)

**文件**: `backend/app/services/wp_bulk_tab_export.py`（新建）

从 ACNR `manifest.list_import_export` 获取 sheet 清单，topo sort 后按 `api_prefix` + `item_id` 逐 sheet 导出/导入。

```python
"""底稿批量 Tab 导入导出服务 — 基于 ACNR manifest"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def list_export_sheets(
    db: AsyncSession,
    project_id: str,
    cycle: str,
) -> list[dict[str, Any]]:
    """获取指定循环的可导出 sheet 列表（已拓扑排序）。

    从 manifest.list_import_export 获取清单，
    按 depends_on_sheets 拓扑排序，
    跳过 wp_id=None 的未解析实例。
    """
    from app.services.acnr.manifest import list_import_export

    entries = await list_import_export(db, project_id, cycle)

    # 过滤掉未解析实例
    valid_entries = []
    for entry in entries:
        if entry.get("wp_id") is None:
            logger.warning(
                "Bulk export: skipping sheet_code=%s (wp_id=None, resolve_instance miss)",
                entry.get("sheet_code"),
            )
            continue
        valid_entries.append(entry)

    # 拓扑排序
    sorted_entries = _topological_sort(valid_entries)
    return sorted_entries


def _topological_sort(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 depends_on_sheets 拓扑排序。

    - 无依赖的 entry 排前
    - 循环依赖时 fallback 到 import_order 排序
    - 同级无依赖关系时以 import_order 为 tiebreaker
    """
    # 构建 sheet_code → entry 映射
    by_code: dict[str, dict] = {}
    for e in entries:
        by_code[e["sheet_code"]] = e

    # 构建邻接表（依赖 → 被依赖）
    in_degree: dict[str, int] = {e["sheet_code"]: 0 for e in entries}
    graph: dict[str, list[str]] = {e["sheet_code"]: [] for e in entries}

    for e in entries:
        deps = e.get("depends_on_sheets") or []
        for dep in deps:
            if dep in graph:
                graph[dep].append(e["sheet_code"])
                in_degree[e["sheet_code"]] += 1

    # Kahn's algorithm
    queue: deque[str] = deque()
    for code, deg in in_degree.items():
        if deg == 0:
            queue.append(code)

    # 按 import_order 排序初始队列（tiebreaker）
    queue = deque(sorted(queue, key=lambda c: by_code[c].get("import_order", 999)))

    result: list[dict] = []
    while queue:
        # 取 import_order 最小的
        current = queue.popleft()
        result.append(by_code[current])
        for neighbor in graph.get(current, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                # 插入时保持 import_order 排序
                inserted = False
                for i, q_item in enumerate(queue):
                    if by_code[neighbor].get("import_order", 999) < by_code[q_item].get("import_order", 999):
                        queue.insert(i, neighbor)
                        inserted = True
                        break
                if not inserted:
                    queue.append(neighbor)

    # 检测环（结果数 < 输入数 → 有环）
    if len(result) < len(entries):
        logger.error(
            "Circular dependency detected in depends_on_sheets, falling back to import_order sort"
        )
        return sorted(entries, key=lambda e: e.get("import_order", 999))

    return result
```

### 7. CustomQueryFieldPicker Component

**文件**: `audit-platform/frontend/src/components/custom-query/CustomQueryFieldPicker.vue`（新建）

使用 `useAcnr` composable 构建公式选址树。

```vue
<template>
  <div class="custom-query-field-picker">
    <!-- 循环过滤 -->
    <el-select
      v-if="showCycleFilter"
      v-model="selectedCycle"
      placeholder="选择循环"
      clearable
      size="small"
      class="cycle-filter"
      @change="onCycleChange"
    >
      <el-option
        v-for="c in cycleOptions"
        :key="c"
        :label="c"
        :value="c"
      />
    </el-select>

    <!-- 地址树 -->
    <el-tree
      v-if="!loading && treeData.length > 0"
      :data="treeData"
      :props="{ label: 'label', children: 'children' }"
      :load="loadNode"
      lazy
      node-key="addrId"
      highlight-current
      @node-click="onNodeClick"
    />

    <!-- 加载状态 -->
    <div v-else-if="loading" class="loading-area">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>加载地址树…</span>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-area">
      <el-empty description="当前循环无可选字段" :image-size="64" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useAcnr, type AcnrTreeNode, type AcnrSheetEntry } from '@/services/acnr/useAcnr'
import { useEventBus } from '@/utils/eventBus'

const props = defineProps<{
  cycle?: string
  showCycleFilter?: boolean
}>()

const emit = defineEmits<{
  select: [payload: { addrId: string; formulaRef: string | null }]
}>()

const { buildAddressTree, loadCellNodes, loading, clearCache } = useAcnr()
const eventBus = useEventBus()

const treeData = ref<AcnrTreeNode[]>([])
const selectedCycle = ref(props.cycle || '')
const cycleOptions = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','S']

async function loadTree() {
  treeData.value = await buildAddressTree(selectedCycle.value || undefined)
}

async function loadNode(node: any, resolve: (data: AcnrTreeNode[]) => void) {
  if (node.data?.type === 'sheet' && node.data?.meta) {
    const cells = await loadCellNodes(node.data.meta as AcnrSheetEntry)
    resolve(cells)
  } else {
    resolve([])
  }
}

function onNodeClick(data: AcnrTreeNode) {
  if (data.type === 'cell') {
    const meta = data.meta as any
    emit('select', {
      addrId: data.addrId,
      formulaRef: meta?.formula_ref ?? null,
    })
  }
}

function onCycleChange() {
  loadTree()
}

// 监听 template-applied 事件刷新
eventBus.on('template-applied', () => {
  clearCache()
  loadTree()
})

// 监听 cycle prop 变化
watch(() => props.cycle, (val) => {
  if (val) {
    selectedCycle.value = val
    loadTree()
  }
})

onMounted(() => {
  loadTree()
})
</script>
```

## Detailed Interfaces

### CrossSheetResolver (修改)

```python
@dataclass
class RefChainNode:
    depth: int
    uri: str                      # 新：addr_id 格式（命中时）或 sheet!cell 格式（fallback）
    value: Any = None
    formula: str | None = None
    missing: bool = False
    cycle: bool = False
    truncated: bool = False
    resolve_missed: bool = False  # 新增：ACNR 未命中标记

@dataclass
class RefChainResponse:
    chain: list[RefChainNode]
    has_cycle: bool
    truncated_at_depth: int | None

class CrossSheetResolver:
    def __init__(self, project_id: str | None = None): ...
    def resolve(self, parsed_data, sheet_name, cell_ref, max_depth=3) -> RefChainResponse: ...
```

### LinkageGraphBuilder (修改)

```python
class LinkageGraphBuilder:
    # 新增纯函数（module-level，可独立测试）
    @staticmethod
    def _normalize_wp_uri_to_addr_id(uri: str) -> str: ...

    # 现有方法签名不变
    async def build(self) -> dict[str, Any]: ...
```

### StalePropagationEngine (修改)

```python
class StalePropagationEngine:
    # 新增
    _addr_id_index: dict[str, str]

    def _build_addr_id_index(self) -> None: ...

    # 修改：on_change 接受 addr_id 和 legacy URI
    async def on_change(self, source_uri: str, project_id, year) -> dict: ...
```

### Linkage Bus API (新增端点)

```
GET /api/linkage-bus/impact-by-addr
  Query Parameters:
    - addr_id: str (required) — ACNR addr_id，如 "D2/D2-2/E100"
    - max_depth: int (optional, default=3) — BFS 深度
    - project_id: str (required) — 项目 UUID
    - year: int (optional, default=0) — 年度

  Response 200:
    {
      "addr_id": "D2/D2-2/E100",
      "total_affected": 5,
      "affected": [
        {"addr_id": "D2/D2-1/审定数", "depth": 1, "via_ref": null, "match_type": "graph_edge"},
        ...
      ]
    }

  Response 400: { "detail": "addr_id is required" }
  Response 503: { "detail": "Stale propagation engine is in degraded mode" }
```

### Bulk Export Service API

```python
async def list_export_sheets(db, project_id, cycle) -> list[dict]:
    """已拓扑排序的可导出 sheet 列表。"""
    ...

def _topological_sort(entries: list[dict]) -> list[dict]:
    """Kahn's algorithm + import_order tiebreaker。"""
    ...
```

### CustomQueryFieldPicker Component API

```typescript
// Props
interface Props {
  cycle?: string           // 过滤循环
  showCycleFilter?: boolean // 是否显示循环下拉
}

// Emits
interface Emits {
  select: [payload: { addrId: string; formulaRef: string | null }]
}
```

## Data Models

### RefChainNode 扩展

| 字段 | 类型 | 说明 |
|------|------|------|
| `resolve_missed` | `bool` | ACNR full_resolve 未命中标记（默认 False，向后兼容） |

### unified_dependency_graph.json 节点格式变更

**Before** (legacy):
```json
{"id": "WP:D2:明细表D2-2:E100", "module": "WP", "code": "D2"}
```

**After** (addr_id):
```json
{"id": "D2/D2-2/E100", "module": "WP", "code": "D2"}
```

非 WP 域不变:
```json
{"id": "TB:1122::期末余额", "module": "TB", "code": "1122"}
{"id": "REPORT:balance_sheet:ROW_001", "module": "REPORT", "code": "balance_sheet"}
```

### StalePropagationEngine 内部状态扩展

| 字段 | 类型 | 说明 |
|------|------|------|
| `_addr_id_index` | `dict[str, str]` | addr_id → graph adjacency key 的 O(1) 查找索引 |

## Error Handling

| 场景 | 处理策略 |
|------|----------|
| `full_resolve` 异常 | `logger.warning` → fallback snapshot 提取（BFS 不中断） |
| `full_resolve` 返回 `found=False` | 使用 snapshot fallback，标记 `resolve_missed=True` |
| `invalidate_reverse_index` 异常 | `logger.warning` → 继续执行后续 step（不 re-raise） |
| `manifest.list_import_export` 返回 `wp_id=None` | skip + `logger.warning`（该 sheet 不进 ZIP） |
| 拓扑排序检测循环依赖 | `logger.error` → fallback `import_order` 数值排序 |
| `stale_impact_by_addr` 缺少 addr_id | HTTP 400 `"addr_id is required"` |
| `stale_engine.is_degraded` | HTTP 503 `"Stale propagation engine is in degraded mode"` |
| `useAcnr` 网络请求失败 | `console.warn` → 返回空数组/miss 结果 |
| `buildAddressTree` 空结果 | 显示 `<el-empty>` 占位 |

## Testing Strategy

### Unit Tests (Example-based)
- CrossSheetResolver: 验证 project_id 正确传递给 full_resolve（Req 1.4）
- Events invalidation: 验证执行顺序、异常隔离（Req 2.1–2.4）
- stale_impact endpoint: 验证 400/503 边界条件（Req 5.5, 5.6）
- Bulk export: 验证 wp_id=None 跳过行为（Req 6.3）
- CustomQueryFieldPicker: 验证 template-applied 事件清缓存、加载态展示（Req 8.6–8.8）

### Property-Based Tests (Hypothesis, min 100 iterations)
- P1–P3: CrossSheetResolver 容错性 — 生成随机 ResolveResult 组合
- P4–P5: `_normalize_wp_uri_to_addr_id` — 生成随机 WP URI 和非 WP URI
- P6: `_detect_and_normalize` — 生成两种格式的 URI 混合
- P7–P9: `_topological_sort` — 生成随机 DAG/有环图/平级 entry
- P10: `LinkageGraphBuilder.build()` — mock 数据源，验证输出图格式
- P11: stale_impact endpoint — 生成随机 addr_id 验证响应 schema
- P12: Bulk export tab naming — 生成随机 manifest entries
- P13: CustomQueryFieldPicker — 生成随机 AcnrTreeNode 验证渲染
- P14: Invalidation chain — 注入随机异常组合，验证全 step 执行

### Integration Tests
- End-to-end: WORKPAPER_SAVED → invalidation → rebuild graph → stale_impact query
- Bulk export: manifest → topo sort → ZIP 生成验证

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: ACNR Resolve Fallback Preserves Response Contract

*For any* cross-sheet reference input (sheet_name, cell_ref), regardless of whether ACNR `full_resolve` returns found=true, found=false, or raises an exception, the `CrossSheetResolver.resolve()` method SHALL always return a valid `RefChainResponse` with the same field schema.

**Validates: Requirements 1.5, 1.6**

### Property 2: addr_id Used on ACNR Hit

*For any* cross-sheet reference where ACNR `full_resolve` returns `found=true` with a non-empty `addr_id`, the corresponding `RefChainNode.uri` in the chain SHALL equal that `addr_id`, and `resolve_missed` SHALL be `False`.

**Validates: Requirements 1.2**

### Property 3: Snapshot Fallback on ACNR Miss

*For any* cross-sheet reference where ACNR `full_resolve` returns `found=false` or raises an exception, the corresponding `RefChainNode` SHALL have `resolve_missed=True` and the BFS traversal SHALL continue without interruption.

**Validates: Requirements 1.3, 1.6**

### Property 4: WP URI Normalization Round-Trip Consistency

*For any* valid WP-domain URI in format `WP:{wp_code}:{sheet_display}:{cell}` where `sheet_display` contains a recognizable sheet code pattern, `_normalize_wp_uri_to_addr_id(uri)` SHALL produce an addr_id in format `{wp_code}/{sheet_code}/{cell}` that contains all three components separated by `/`.

**Validates: Requirements 3.1, 3.10**

### Property 5: Non-WP Domain URI Passthrough

*For any* URI that does NOT start with `WP:` (including REPORT:, TB:, NOTE:, ADJ:, MAPPING:), `_normalize_wp_uri_to_addr_id(uri)` SHALL return the input unchanged.

**Validates: Requirements 3.5, 3.6, 3.8, 3.9**

### Property 6: Format Detection Correctness

*For any* string, `_detect_and_normalize()` SHALL classify inputs with `WP:` prefix and colons as legacy format (applying normalization), and inputs with `/` separators and no `WP:` prefix as addr_id format (passing through unchanged).

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 7: Topological Sort Respects Dependencies

*For any* list of manifest entries with a valid DAG of `depends_on_sheets`, `_topological_sort()` SHALL produce an ordering where every entry appears AFTER all entries it depends on.

**Validates: Requirements 7.1, 7.2**

### Property 8: Topological Sort Stability via import_order

*For any* two entries that have no dependency relationship between them (neither depends on the other directly or transitively), the entry with the lower `import_order` SHALL appear first in the sorted output.

**Validates: Requirements 7.4**

### Property 9: Circular Dependency Fallback

*For any* list of manifest entries containing a circular dependency in `depends_on_sheets`, `_topological_sort()` SHALL return entries sorted by `import_order` (numeric fallback).

**Validates: Requirements 7.3**

### Property 10: Graph Build Invariant — WP Nodes Use addr_id

*For any* unified dependency graph produced by `LinkageGraphBuilder.build()`, all nodes with `module == "WP"` SHALL have their `id` field in addr_id format (containing `/` separators, not `WP:` prefix).

**Validates: Requirements 3.11**

### Property 11: stale_impact Response Schema Completeness

*For any* valid `addr_id` input to the `/impact-by-addr` endpoint, the response SHALL contain `addr_id` (string), `total_affected` (int ≥ 0), and `affected` (list where each entry has `addr_id`, `depth`, `via_ref`, and `match_type` fields).

**Validates: Requirements 5.4**

### Property 12: Bulk Export Tab Names Match sheet_code

*For any* manifest entry that is included in bulk export (i.e., `wp_id` is not None), the generated ZIP tab name SHALL exactly equal the entry's `sheet_code`.

**Validates: Requirements 6.4**

### Property 13: CustomQueryFieldPicker Tree Node Contract

*For any* `AcnrTreeNode` rendered by `CustomQueryFieldPicker`, the displayed label SHALL equal `AcnrTreeNode.label`, and when a cell node is selected, the emitted event SHALL contain the node's `addrId` field.

**Validates: Requirements 8.3, 8.4**

### Property 14: Invalidation Chain Completeness

*For any* call to `acnr.events.invalidate()`, the function SHALL invoke all four steps (L3 clear, L2 clear, ReverseIndex clear, Legacy delegate) regardless of whether any individual step raises an exception.

**Validates: Requirements 2.1, 2.2, 2.3**

---

## Components and Interfaces (Retrospective Expansion — P5–P8)

> 复盘补充的 4 组消费者接入设计。均沿用 strangler-fig + fail-open-on-infra / fail-closed-on-miss 原则。

### 7. Formula Validation → ACNR full_resolve (Req 9)

**文件**: `wp_formula_service.py`、`routers/report_config.py`、`routers/wp_user_formulas.py`；新增共享 helper（建议 `backend/app/services/acnr/formula_validation.py`）。

三处 `address_registry.validate_formula_refs` 收敛到一个 ACNR-backed helper：

```python
# backend/app/services/acnr/formula_validation.py
async def validate_refs_via_acnr(
    db, project_id: str, year: int, expression: str, template_type: str,
) -> list[dict]:
    """返回 issues 列表（空=通过）。ACNR full_resolve 判定 WP 域引用；
    非 WP 域 + 基础设施异常 → 委托 legacy validate_formula_refs（fail-open）。"""
    from app.services.acnr.resolver import full_resolve
    from app.services.address_registry import address_registry
    issues: list[dict] = []
    wp_refs, other_refs = _split_refs(expression)  # 拆 WP() vs TB()/ROW()/NOTE()
    # WP 域走 ACNR
    for ref in wp_refs:
        try:
            r = await full_resolve(formula_ref=ref, project_id=project_id, db=db)
        except Exception as exc:
            logger.warning("ACNR validate fallback for %s: %s", ref, exc)
            return await address_registry.validate_formula_refs(
                db, project_id, year, expression, template_type)  # fail-open
        if not r.found:
            issues.append({"ref": ref, "reason": "not_found"})
    # 非 WP 域仍走 legacy（catalog 覆盖确认前）
    if other_refs:
        legacy = await address_registry.validate_formula_refs(
            db, project_id, year, _join_refs(other_refs), template_type)
        issues.extend(legacy)
    return issues
```

**决策**：只有 WP 域 `found=false` 才判 invalid（Req 9.4）；基础设施异常时整体回退 legacy（Req 9.3 fail-open），绝不因 resolver 挂掉而阻断保存。`WpFormulaService.save` 的 `(None, issues)` 契约不变（Req 9.1）。

### 8. Invalidation Path Unification (Req 2.5–2.6, Req 10, Req 11)

**问题根因**：`acnr/events.invalidate`（Req 1.3 增强 reverse_index 清理处）只被 `on_workpaper_saved`（WORKPAPER_SAVED 事件）调用；但 `touch_wp_registry` 是**另一条热路径**，直接 `address_registry.invalidate_async(domain="wp")`，绕过 events.invalidate → task 1.3 在此路径上是死代码。

**设计**：确立单一 canonical 失效入口，两条路径都汇入它。

```python
# backend/app/services/acnr/events.py — 已有 invalidate() 即 canonical 入口
# 新增薄封装供 domain 化调用（Req 11）
async def invalidate_domain(project_id: str, *, domain: str,
                            wp_id: str | None = None) -> None:
    if domain == "wp":
        await invalidate(project_id, wp_id=wp_id, trigger="touch_wp_registry")
    else:
        # 非 WP 域：单一 seam，当前 behavior parity 委托 legacy
        try:
            from app.services.address_registry import address_registry
            await address_registry.invalidate_async(str(project_id), domain=domain)
        except Exception as exc:
            logger.warning("acnr.invalidate_domain %s failed: %s", domain, exc)
```

改造点：
- `wp_parsed_data_service.touch_wp_registry` → 调 `acnr.events.invalidate(project_id, trigger="touch_wp_registry")`（Req 10.1）。不 re-publish 事件（Req 10.4，避免 handler 重复 fan-out），直接 in-process 调用。异常仅 warning（Req 10.3）。
- `event_handlers._invalidate_addr_tb/report/note` → 改调 `acnr.events.invalidate_domain(pid, domain="tb"|"report"|"note")`（Req 11.1）。行为与现状一致（最终仍委托 legacy，Req 11.2），但提供未来按域清 L2/L3 overlay 的统一缝。
- **无回归保证**：canonical `invalidate()` 最后一步仍 `address_registry.invalidate_async(domain="wp")`（Req 10.2 / 现 Req 2.3），是当前直接调用的超集。

**幂等/重入注意**：WORKPAPER_SAVED handler 与 touch_wp_registry 可能在同一保存事务前后都触发 invalidate → invalidate 必须幂等（清缓存本就幂等）；避免在 invalidate 内再 publish 事件形成环。

### 9. Custom WP Cell Index → ACNR L3 Runtime (Req 12)

**文件**: `address_registry.py`（`extract_custom_cells` / `_build_custom_wp_cell_entries` 产出点）；ACNR `runtime.py`（`register_custom` / runtime entries）。

`_build_custom_wp_cell_entries` 在产出 legacy `AddressEntry` 的同时，追加注册到 L3 runtime：

```python
# 在遍历 extract_custom_cells(parsed_data) 生成 AddressEntry 后追加：
from app.services.acnr.runtime import register_custom  # project-scoped
addr_id = f"{wp_code}/{wp_code}/{rec.cell}"   # custom_flat: parent==sheet==wp_code
register_custom(
    project_id=project_id,
    addr_id=addr_id,
    cell_address=rec.cell,
    semantic_label=rec.row_label or None,
    formula_ref=f"WP('{wp_code}','{wp_code}','{rec.cell}')",  # grammar_v1 custom_flat 对齐
    wp_code=wp_code,
)
```

**决策**：
- addr_id 用 custom_flat profile `{wp_code}/{wp_code}/{cell}`（parent==sheet==wp_code），与 `resolveUri.ts` 的 `RE_CUSTOM_FLAT` / grammar_v1 一致（Req 12.1/12.2）。
- runtime 是 project-scoped，随 canonical invalidate 清理（Req 12.3）——正好复用 §8 统一失效链（L3 RuntimeIndex clear 是 invalidate 第 1 步）。
- 单 wp 注册失败仅 warning + continue（Req 12.4，复用现有 per-wp try/except）。
- **保留 legacy AddressEntry 产出**（strangler-fig）：runtime 注册是**追加**，不删旧路径，直到 `full_resolve` 对自定义 cell 的命中率经验证达标。

### 10. Frontend Index Navigation → ACNR resolveIndex (Req 13)

**文件**: `frontend/composables/useWorkpaperNavigation.ts`；`frontend/utils/parseIndexRef.ts`（收敛）；`frontend/services/acnr/resolveUri.ts`（权威语法）。

`navigateToWorkpaper` 增加 ACNR 前置解析，失败回退现有 registry 路径：

```typescript
const { resolveInstance, resolveIndex } = useAcnr()
async function navigateToWorkpaper(wpCode, projectId, year?) {
  if (A16_VIRTUAL_RE.test(wpCode)) { /* 现有虚拟码逻辑不变 (Req 13.4) */ }
  await registry.load()
  const entry = registry.lookup(wpCode)
  // ── ACNR 前置：优先拿 wp_id + jump_route ──
  try {
    const idx = await resolveIndex(`wp:${wpCode}`)
    if (idx.found && idx.jump_route) { router.push(idx.jump_route); return }
  } catch { /* 静默回退 */ }
  // ── 回退：现有 index-resolve API + resolveRoute（Req 13.2 无回归）──
  ...
}
```

`parseIndexRef.ts` 收敛（Req 13.3）：二选一——(a) 内部委托 `services/acnr/resolveUri.ts` 的 `parseIndexRef`；(b) 保留但加**契约测试**断言与 ACNR 解析器在 11 命名空间上逐一等价。推荐 (b) 先加契约测试锁定行为，再择机物理合并，降低回归风险。

## Data Models (Expansion)

### CrossSheetResolver 构造签名扩展

| 字段 | 类型 | 说明 |
|------|------|------|
| `_parent_wp_code` | `str \| None` | 可选父底稿码，用于构造 3 参 `WP(parent,sheet,cell)`；缺省时退化为 URI 形态解析 |

### L3 Runtime 自定义 cell 条目

| 字段 | 类型 | 说明 |
|------|------|------|
| `addr_id` | `str` | custom_flat `{wp_code}/{wp_code}/{cell}` |
| `formula_ref` | `str` | `WP('{wp_code}','{wp_code}','{cell}')` |
| `project_id` | `str` | project-scoped，随 invalidate 清理 |

## Error Handling (Expansion)

| 场景 | 处理策略 |
|------|----------|
| `full_resolve` 校验时异常/不可用（Req 9.3） | `logger.warning` → 回退 legacy `validate_formula_refs`（fail-open，不阻断保存） |
| 非 WP 域引用（Req 9.4） | 保持 legacy 校验，不由 ACNR 判 invalid |
| `sync→async` 桥接失败（design §1） | 降级 snapshot fallback + `resolve_missed=True`，不抛异常 |
| WP() 无 parent wp_code（design §1） | 退化为 `full_resolve(uri="wp://{sheet}/{cell}")`；仍 miss → resolve_missed=True |
| `touch_wp_registry` 调 canonical invalidate 抛异常（Req 10.3） | `logger.warning`，不 raise（不阻断主流程） |
| L3 runtime 注册单 wp 失败（Req 12.4） | `logger.warning` + continue 下一 wp |
| ACNR `resolveIndex` 前端失败（Req 13.2） | 静默回退 registry + index-resolve API |

## Correctness Properties (Expansion — P15–P18)

### Property 15: Formula Validation Fail-Open on Infra Error

*For any* formula expression, WHEN ACNR `full_resolve` raises an exception during validation, `validate_refs_via_acnr` SHALL return the same result as the legacy `validate_formula_refs` for that expression (fail-open), never returning a spurious `not_found` issue caused solely by resolver infrastructure failure.

**Validates: Requirements 9.3**

### Property 16: Invalidation Path Convergence

*For any* WP-domain invalidation trigger (WORKPAPER_SAVED event OR `touch_wp_registry`), the set of cache layers cleared SHALL be identical and SHALL always include the FormulaReverseIndex clear (i.e. both paths converge on the canonical `acnr.events.invalidate`), and neither path SHALL re-publish a WORKPAPER_SAVED event (no duplicate fan-out).

**Validates: Requirements 2.5, 2.6, 10.1, 10.2, 10.4**

### Property 17: Custom Cell addr_id custom_flat Round-Trip

*For any* custom WP cell record `(wp_code, cell)` registered into L3 runtime, the produced `addr_id` SHALL equal `{wp_code}/{wp_code}/{cell}` and its `formula_ref` SHALL be parseable back to the same `addr_id` by the grammar_v1 custom_flat profile (round-trip consistency), and the legacy AddressEntry output SHALL still be produced (additive registration).

**Validates: Requirements 12.1, 12.2**

### Property 18: Frontend Index Parser Parity

*For any* index reference string among the 11 registered namespaces, `utils/parseIndexRef.ts` and `services/acnr/resolveUri.ts::parseIndexRef` SHALL classify the namespace identically (parity), OR the local parser SHALL delegate to the ACNR parser so a single grammar governs classification.

**Validates: Requirements 13.3**

---

## Components and Interfaces (Retrospective Expansion — P9–P11)

### 11. Formula Pickers → ACNR (Req 14)

**文件**: `frontend/components/formula/FormulaRefPicker.vue`、`FormulaEditDialog.vue`、`CellSelector.vue`、`utils/wpFormulaPicker.ts`。

现状：`FormulaRefPicker` 从 legacy Pinia `useAddressRegistry`（`reportAddresses/tbAddresses/noteAddresses`）取数，**无 WP tab**；`FormulaEditDialog` 经 `mapRegistryToPickerRows` 从 legacy 注册表 WP 条目取数。

设计（依赖 §13 store 收敛，见下）：
- 三处 picker 的取数改走 ACNR-backed store（§13）或直接 `useAcnr`。因 §13 保持 store 公共契约不变，`FormulaRefPicker` 的 `addrStore.reportAddresses` 等 **无需改调用点**——底层数据源换成 ACNR 即可（strangler 最优路径）。
- **新增 WP tab**：`FormulaRefPicker` 增加第 4 个 tab，数据源 `useAcnr().listSheets(cycle)` → 展开 `loadCellNodes`，选中 cell → `WP('{parent}','{sheet}','{cell}')`（Req 14.2/14.5）。
- `wpFormulaPicker.mapRegistryToPickerRows` 增加一个 ACNR 变体 `mapAcnrCellsToPickerRows(cells: AcnrCellEntry[])`，`_ref = cell.formula_ref`，`pickerRowsSubsetOfRegistry` 语义变为 subset-of-ACNR（Req 14.3）。
- 空结果回退 legacy（Req 14.4）。

### 12. NoteFormulaDialog Load/Edit/Persist Fix (Req 15)

**文件**: `frontend/components/formula/NoteFormulaDialog.vue`；后端 `routers/disclosure_notes.py` + 新增 service。

**问题根因**（实证）：`formulas = ref([])` 从不加载；`addFormula` 推硬编码 `SUM(上方明细行)`；编辑只改本地 row，`onApply` 调 `apply-formulas`（`execute_note_formulas` 从 check_presets 重生成）**丢弃用户编辑**；后端仅 `apply-formulas`/`clear-formulas`，**无 list/save**。

设计：
- **后端新增**（Req 15.6）：`GET /{pid}/{year}/{note_section}/formulas`（列出当前公式：已保存优先，否则返回 generator 预览）+ `PUT /{pid}/{year}/{note_section}/formulas`（upsert 用户编辑集）。新增 `NoteFormulaService`（`list_by_section` / `save_many`），`service 只 flush 不 commit`，router 统一 commit。存储可复用现有 note 公式表或新增轻量表（迁移 V1xx）。
- **前端**：`NoteFormulaDialog` onOpen（watch visible）调 `GET .../formulas` 填充 `formulas`（Req 15.1）；行 `完成` 时调 `PUT` 持久化（Req 15.2）；`addFormula` 推空可编辑行（Req 15.3）；`onApply` 执行**持久化集**而非无条件重生成，另设「重新生成」显式按钮（Req 15.4）；保存前经 §7 ACNR 校验（Req 15.5/Req 9），悬空引用 `ElMessage` 提示不入库。
- **无回归**：`apply-formulas`/`clear-formulas` 端点保留，语义不变（重生成变显式动作）。

### 13. addressRegistry Store ACNR Convergence (Req 16)

**文件**: `frontend/stores/addressRegistry.ts`。

设计（facade over ACNR，保持公共契约）：
- `resolve(uri)` → 先 `http.get('/api/acnr/resolve', {params:{uri}})`；miss/error 回退 legacy `/api/address-registry/resolve`（Req 16.1）。
- `validate(formula)` → ACNR-backed 校验（与后端 Req 9 parity），infra 失败回退 legacy（Req 16.2 fail-open）。
- `search(kw, domain)` → wp 域走 `useAcnr().listSheets/listCells` 映射为 `AddressEntry[]`；tb/report/note/aux 保留 legacy（Req 16.3）。
- 公共 return 面（`addresses`/`*Addresses`/`refresh/search/resolve/validate/jump/invalidate`）**不变**（Req 16.4）——消费者零改动。
- `template-applied`/`formula-changed` 复用现有 debounced refresh，额外 `clearCache` ACNR 派生缓存（Req 16.5）。

### 14. Note Tree Position → ACNR NOTE Index (Req 17)

**文件**: `frontend/views/composables/useNoteTree.ts`（`TreeNode`）；节点渲染处（DisclosureEditor）。

设计：
- `TreeNode` 增加可选字段 `indexRef?: string`（值 `note:{note_section}`）——additive，不改结构/分组/拖拽（Req 17.3）。
- 节点上的索引 chip（若有）或跳转经 `useAcnr().resolveIndex('note:'+section)` 取 `jump_route`；unresolved 回退现有 note 导航（Req 17.2）。
- NOTE 域走 ACNR full_resolve V1 delegation，无需预登记 L1 catalog（Req 17.4）——与 core ACNR `_delegate_v1` 的 note 分支一致。

## Data Models (Expansion 2)

### NoteFormula 持久化（新增，Req 15.6）

| 字段 | 类型 | 说明 |
|------|------|------|
| `project_id` / `year` / `note_section` | — | 定位维度 |
| `target_cell` | `str` | 目标单元格/合计行标识 |
| `expression` | `str` | 公式表达式 |
| `category` | `str` | auto_calc / logic_check / reasonability |
| `description` | `str \| null` | 说明 |

### TreeNode 扩展（Req 17.1）

| 字段 | 类型 | 说明 |
|------|------|------|
| `indexRef` | `string?` | `note:{note_section}`，ACNR NOTE 域可解析索引 |

## Error Handling (Expansion 2)

| 场景 | 处理策略 |
|------|----------|
| FormulaRefPicker WP tab `listSheets` 空/失败 | 回退 legacy `wpAddresses`；tab 内 `el-empty` 占位 |
| NoteFormulaDialog `GET formulas` 失败（Req 15.1） | `ElMessage.warning` + 空列表（不阻断弹窗），不静默丢已存数据 |
| NoteFormula 保存悬空引用（Req 15.5） | ACNR 校验 `not_found` → `ElMessage` 提示 + 不入库 |
| addressRegistry `resolve` ACNR miss（Req 16.1） | 回退 legacy resolve；仍 miss → `{found:false}` |
| note `resolveIndex` 未命中（Req 17.2） | 回退现有 note 导航（无回归） |

## Correctness Properties (Expansion 2 — P19–P22)

### Property 19: WP Picker Emits grammar_v1 Formula

*For any* WP cell selected in the FormulaRefPicker WP tab or FormulaEditDialog WP browse, the emitted `formula_ref` SHALL be a grammar_v1-valid `WP(...)` reference (3-arg standard, or `WP('wp_code','wp_code','cell')` for custom_flat) that `full_resolve`/`parseUri` can round-trip to the cell's `addr_id`.

**Validates: Requirements 14.2, 14.3, 14.5**

### Property 20: Formula Dialog Edit Persistence Round-Trip

*For any* sequence of formula edits saved in NoteFormulaDialog, reopening the dialog for the same note section SHALL display exactly the persisted set (no loss, no silent regeneration), i.e. save→reload is an identity on the formula set.

**Validates: Requirements 15.1, 15.2, 15.4**

### Property 21: Store Facade Contract Invariance

*For any* consumer call to `useAddressRegistry` public methods, the response shape SHALL be identical whether served by ACNR or by the legacy fallback (facade preserves the `AddressEntry`/`ResolveResult`/`ValidateResult` contracts), so no consumer branches on the backing source.

**Validates: Requirements 16.1, 16.2, 16.4**

### Property 22: Note Index Additive Non-Regression

*For any* note tree built by useNoteTree, adding `indexRef` SHALL NOT change node `id`/`label`/`children`/ordering/grouping (the tree with and without index metadata is structurally identical except for the additive `indexRef` field).

**Validates: Requirements 17.1, 17.3**

---

## Components and Interfaces (Retrospective Expansion — P12)

### 15. Bundle Directory Tabs → ACNR Catalog Index (Req 18)

**文件**: `frontend/components/workpaper/d2/D2TabIndex.vue`、`d4/core/D4TabIndex.vue`（试点）；新增 `frontend/components/workpaper/composables/useAcnrCatalogIndex.ts`；契约测试。

**现状（实证）**：每个 bundle 的目录 Tab 硬编码 `indexRows`（`{seq,name,code,group,sheetLabel/tabName,applicable}`），名称如 `D2-2→明细表D2-2`、`D4-14→营业收入发生检查表` 全部字面量；跳转用 `.gt-index-chip` CSS span（非组件）+ `inject('jumpToSection')`。存在 name/code 与 ACNR catalog 漂移风险。

**设计**：
- 新增 `useAcnrCatalogIndex(cycle)`：调 `useAcnr().listSheets(cycle)` 得 `AcnrSheetEntry[]`，产出 `Map<sheet_code, {sheet_name, addr_id, order}>`。
- `TabIndex` 的 `indexRows` 改为：**名称/编码/顺序** 从 catalog map 取（真源），**tabName/applicable/完成检测** 仍来自本地按 `sheet_code` keyed 的 routing config（Req 18.2/18.5）。即「名 = ACNR，路由与项目态 = 本地」。
- 跨底稿跳转行用 `GtIndexChip`（走 resolve_instance）；纯 bundle 内 sheet 切换保留 `jumpToSection`（Req 18.3）。
- **契约测试**（Req 18.4）：`test_tabindex_codes_in_acnr_catalog` —— 收集 D2/D4 TabIndex 的 `sheet_code` 集合，断言全部存在于 ACNR catalog（vitest + catalog fixture 或后端 catalog dump）。
- **降级**（Req 18.7）：catalog 空/失败 → 用现有硬编码 rows 兜底。
- **增量**：D2/D4 试点跑通 helper 后，其余循环 `*TabIndex` 复用同一 helper（Req 18.6）。

**非目标**：不改 `WorkpaperList`（按 wp_id 直跳，Req 13.7 仅可选 chip 化）；不把 catalog 变成 per-project 完成度真源（完成检测仍本地 item_id 逻辑）。

## Error Handling (Expansion 3)

| 场景 | 处理策略 |
|------|----------|
| `useAcnrCatalogIndex` catalog 空/失败（Req 18.7） | 回退硬编码 rows，`console.warn`，目录不空白 |
| TabIndex sheet_code 不在 catalog（Req 18.4） | 契约测试 CI 失败；运行时该行用本地名兜底 |

## Correctness Properties (Expansion 3 — P23)

### Property 23: TabIndex Code ⊆ ACNR Catalog

*For any* migrated bundle `TabIndex`, every `sheet_code` in its directory SHALL exist in the ACNR catalog for that cycle (subset relation), so directory codes never drift from the catalog; catalog-unavailable fallback SHALL still render the full hardcoded row set (no blank directory).

**Validates: Requirements 18.1, 18.4, 18.7**

---

## Components and Interfaces (Retrospective Expansion — P13)

### 16. Consolidation Module Address/Name References → ACNR (Req 19)

**文件**: `frontend/components/consolidation/worksheets/EliminationSheet.vue`（试点）、`ConsolWorksheetTabs.vue` 下其余 worksheet；`frontend/views/composables/useReportCrossCheck.ts`；新增共享 helper `useConsolSubjectSource.ts`；契约测试。

**现状（实证）**：
- `EliminationSheet.subjectTree`：硬编码五级科目树（资产/负债/权益/损益/现金流，叶子=科目中文名），科目坐标名称脱离真源。
- `useReportCrossCheck`：`get(bsMap, 'assets_total','资产总计','资产合计')` 式硬编码 `BS-*/IS-*` + 中文名模糊匹配；`buildMap` 按 row_code+row_name 双键建索引。报表地址靠字符串猜。
- `EliminationSheet` `emit('open-formula'/'goto-sheet')`：公式/跳转未接 ACNR。

**设计**：
- **科目名称源（Req 19.1/19.4）**：新增 `useConsolSubjectSource()`：从 ACNR-backed 地址 store 的 `tbAddresses`（Req 16）或 TB 域取标准科目名，产出与现 `subjectTree` 同构的树（保留 disabled 父节点 + 叶子科目名）。`EliminationSheet` 用它替换硬编码 `subjectTree`；registry 空 → 回退硬编码（Req 19.5）。其余 worksheet 复用同一 helper（增量，Req 19.4）。
- **报表勾稽（Req 19.2）**：`useReportCrossCheck` 取报表值改经 ACNR REPORT 域 / store `reportAddresses` 拿 canonical `row_code→row_name`，用 row_code 精确取值替代中文名模糊匹配；`computeCrossCheckResults` 的 7 条勾稽等式逻辑不变，仅取值来源换真源。
- **公式/跳转（Req 19.3）**：`open-formula` 打开的公式弹窗走 Req 14 的 ACNR picker；`goto-sheet` 跨底稿跳转经 `GtIndexChip`/ACNR resolve。
- **契约测试（Req 19.6）**：`test_crosscheck_codes_in_report_registry` —— 收集 cross-check 用到的 `BS-*/IS-*` 集合，断言存在于 report-config 地址注册表。
- **不变项（Req 19.7）**：`buildAutoEntries`（权益/损益/交叉持股抵消）+ Excel 导入导出逻辑不动，只换坐标名称来源。

## Error Handling (Expansion 4)

| 场景 | 处理策略 |
|------|----------|
| `useConsolSubjectSource` registry 空/失败（Req 19.5） | 回退硬编码 subjectTree，`console.warn`，picker 不空白 |
| 报表勾稽 ACNR REPORT 解析 miss（Req 19.2） | 回退现有 row_name 模糊匹配（无回归） |
| cross-check row_code 不在 report registry（Req 19.6） | 契约测试 CI 失败；运行时该项按 0 处理（现有行为） |

## Correctness Properties (Expansion 4 — P24)

### Property 24: Consolidation Name Source Fidelity + Fallback

*For any* consolidation subject picker or report cross-check, WHEN the ACNR/report registry is available, the coordinate names/codes used SHALL be a subset of the registry (no hardcoded drift); WHEN unavailable, the worksheet SHALL fall back to the full hardcoded set (no blank picker, no lost cross-check rows), and the auto-entry/cross-check computation results SHALL be identical to the pre-migration behavior for the same input data.

**Validates: Requirements 19.1, 19.2, 19.5, 19.7**

---

## Components and Interfaces (Retrospective Expansion — P14)

### 17. Consolidated Report / Notes / Worksheet Address References → ACNR (Req 20)

**文件**: 合并报表视图（consolidation reports view + `consolBreakdown`/`balance-check` 消费处）、合并附注（consolidation notes view + `reaggregate`/`consolBreakdown`）、`ConsolWorksheetTabs.vue` 全部 worksheet 的 `open-formula`/`goto-sheet` seam；复用 §11 formula picker、§14 note index、GtIndexChip、Req 16 store。

**现状（实证，`services/apiPaths/report.ts`）**：
- 合并报表：`reports.consolBreakdown(pid,year,accountCode)` + `balance-check` 用 account_code / 报表行地址（字符串），未接 ACNR。
- 合并附注：`notes.reaggregate` 消费子公司单体附注、`notes.consolBreakdown(sectionId)` 按 note section，未接 ACNR NOTE 域/resolveIndex。
- 合并工作底稿：~15 worksheet 均 `emit('open-formula', key)` + 部分 `emit('goto-sheet', key)`，未接 ACNR；`worksheet.drillTrialBalance` 按 TB account_code。

**设计（复用已有能力，最小新增）**：
- **合并报表（Req 20.1/20.2）**：报表行/account 引用渲染改用 `GtIndexChip`（REPORT/TB 域）或经 Req 16 store `reportAddresses`/`tbAddresses` 取 canonical 地址；`consolBreakdown` drill 的 account_code 经 ACNR TB 域解析取 jump_route。不改报表数值/生成逻辑（Req 20.9）。
- **合并附注（Req 20.3/20.4）**：note section 引用经 `useAcnr().resolveIndex('note:'+sectionId)` 解析/跳转（NOTE 域 V1 delegation，Req 17.4）；reaggregate 溯源以 NOTE addr 标识源单体附注 section（provenance 可追溯），reaggregate 计算不变。
- **合并工作底稿（Req 20.5/20.6）**：`ConsolWorksheetTabs` 统一把子 worksheet 的 `open-formula` 事件接到 Req 14 ACNR formula picker（一处父级接线，惠及全部 worksheet）；`goto-sheet` 经 GtIndexChip/ACNR resolve；drill account_code 作 ACNR TB 地址。
- **降级（Req 20.7）**：registry/catalog 不可用 → 现有行为兜底（报表/附注/worksheet 不空白）。
- **契约（Req 20.8）**：`test_consol_report_codes_in_registry` / `test_consol_note_sections_in_registry` —— 收集合并报表 account_code、合并附注 section 集合，断言在 ACNR REPORT/NOTE 覆盖范围内（V1 动态域豁免）。

**关系**：Req 20.5 是 Req 19.3（EliminationSheet formula/nav）的推广——由 `ConsolWorksheetTabs` 父级统一接线覆盖全部 worksheet，避免逐个组件改。

## Error Handling (Expansion 5)

| 场景 | 处理策略 |
|------|----------|
| 合并报表 account_code ACNR REPORT/TB miss（Req 20.1/20.7） | 回退纯文本展示（不可跳转），不空白 |
| 合并附注 note section resolveIndex miss（Req 20.3/20.7） | 回退现有 note 导航 |
| worksheet open-formula picker 不可用（Req 20.5/20.7） | 回退现有公式弹窗行为 |
| consol code 不在 registry（Req 20.8） | 契约测试 CI 失败（catalog 覆盖内）；V1 动态域豁免 |

## Correctness Properties (Expansion 5 — P25)

### Property 25: Consolidation Address Resolution Additive + Numbers Unchanged

*For any* consolidated report line, consolidated note section, or worksheet formula/drill reference, routing address resolution through ACNR SHALL be additive: WHEN resolvable, the reference gains a canonical addr/jump_route; WHEN not resolvable (miss/registry down), it falls back to current behavior; and in all cases the consolidation computation outputs (report figures, reaggregated note values, worksheet recalc/aggregate results) SHALL be identical to pre-migration for the same input data.

**Validates: Requirements 20.1, 20.3, 20.5, 20.7, 20.9**

---

## Coverage Ledger — 全库 ACNR 消费点清单（无死角映射，Req 22.1）

> 第五轮全库穷举扫描结果。每个 ACNR/地址消费点 → 覆盖优先级 或 豁免原因。这是"无死角"的可核查真源。

### 后端 (backend/app)

| 消费点 | 现状 | 覆盖 |
|---|---|---|
| `wp_parsed_data_service.touch_wp_registry` | 直调 `invalidate_async(domain=wp)` | **P6 / Req 10.1** |
| `wp_structure.py:101` invalidate | 直调 `invalidate_async(domain=wp)` | **P6 / Req 2.6** |
| `event_handlers._invalidate_addr_tb/report/note` | 直委托 legacy | **P6 / Req 11** |
| `wp_formula_service.save` validate | `validate_formula_refs` | **P5 / Req 9.1** |
| `routers/report_config.py:115` validate | `validate_formula_refs` | **P5 / Req 9.2** |
| `routers/wp_user_formulas.py:221` validate | `validate_formula_refs` | **P5 / Req 9.2** |
| `address_registry._build_custom_wp_cell_entries` | 产 legacy AddressEntry | **P7 / Req 12** |
| `formula_engine.py:1484` extract_custom_cells 解析 | WP cell 解析走 legacy | **P15 / Req 21.1** |
| `wp_structure_bridge.py` build_uri/AddressEntry 产出 | structure→AddressEntry | **P15 / Req 21.2** |
| `query_builder.py:819` `TB()` ref 语法生成 | 生成 ref 字符串 | **P15 / Req 21.3** |
| `stale_propagation_engine.py` WP:* URI | legacy URI 前缀 | **P2 / Req 4** |
| `linkage_graph_builder.py` 10 数据源 URI | legacy URI | **P2 / Req 3** |
| `acnr/events.py` reverse_index 缺失 | 失效链不全 | **P1 / Req 2** |
| CrossSheetResolver | 未接 full_resolve | **P1 / Req 1** |
| `routers/address_registry.py` V1 API | legacy 端点 | **豁免 Req 21.4**（strangler fallback，不删） |
| `acnr/{events,grammar,resolver}.py` 委托 legacy | 非 wp 域 V1 delegation | **豁免 Req 21.5**（ACNR core 缝，非 gap） |
| `auto_data_resolvers/*` (d4_tb_unadjusted 等) | 数据取数解析器（查 DB） | **豁免**（数据 resolver 非地址消费；ref_index chip 走 GtIndexChip 已 ACNR） |

### 前端 (audit-platform/frontend/src)

| 消费点 | 现状 | 覆盖 |
|---|---|---|
| `GtIndexChip.vue` | ✅ 已迁 ACNR | **标杆（已完成）** |
| `useWorkpaperNavigation.ts` + parseIndexRef.ts | 自解析 | **P8 / Req 13** |
| 导航调用点 ×7（SourceRefChip/WorkpaperTraceView/MyTodoCard/ReviewOpinionList/DocAiChatPanel/WorkpaperHtmlTable/WpPopupDocxEditor） | 走 legacy navigate | **P8 / Req 13.5**（composable 迁移一并修复） |
| `stores/addressRegistry.ts` | legacy V1 store | **P9 / Req 16** |
| `FormulaRefPicker.vue` | legacy store + 无 WP tab | **P9 / Req 14.1-14.2** |
| `FormulaEditDialog.vue` | legacy 注册表 WP 浏览 + 多域 ref 构造 | **P9 / Req 14.3, 14.5-14.7** |
| `FormulaManagerDialog.vue` | 构造 `TB()` from legacy | **P9 / Req 14.6** |
| `FormulaBar.vue` | 构造 TB/ROW/REPORT/NOTE/WP ref | **P9 / Req 14.6** |
| `CellSelector.vue` | legacy store | **P9 / Req 14.4** |
| `NoteFormulaDialog.vue` | 空 ref 不加载/不持久化 | **P10 / Req 15** |
| `useNoteTree.ts` TreeNode | 无 addr_id/NOTE 索引 | **P11 / Req 17** |
| `CustomQueryFieldPicker`（高级查询树） | greenfield useAcnr | **P4 / Req 8** |
| `WorkpaperList.vue` wp_code 列 | wp_id 直跳，展示文本 | **P8 / Req 13.7**（可选 chip 化，非缺陷） |
| `D2TabIndex/D4TabIndex/…每循环目录 Tab` | 硬编码 sheet_code→名称 | **P12 / Req 18** |
| 合并 `EliminationSheet.subjectTree` | 硬编码科目树 | **P13 / Req 19.1** |
| 合并 `useReportCrossCheck` | 硬编码 BS-*/IS-*+模糊匹配 | **P13 / Req 19.2** |
| 合并报表 consolBreakdown/balance-check | account_code 地址 | **P14 / Req 20.1-20.2** |
| 合并附注 reaggregate/consolBreakdown | note section 地址 | **P14 / Req 20.3-20.4** |
| 合并 ~15 worksheet open-formula/goto-sheet | 未接 ACNR | **P14 / Req 20.5-20.6** |

**结论**：全库扫描无未映射消费点。P1–P15 + 标杆(GtIndexChip 已完成) + 豁免项(V1 fallback/ACNR core/数据 resolver) = 完整闭合。新消费点须补入本 Ledger（Req 22.2 CI drift guard）。

## Components and Interfaces (Full-Sweep Closure — P15)

### 18. Backend Producers/Resolvers Alignment (Req 21)

- **formula_engine.py（Req 21.1）**：WP 域引用解析先试 ACNR `full_resolve`/runtime，miss 回退 `extract_custom_cells`；infra 异常 fail-open 回退 legacy。数值计算不变。
- **wp_structure_bridge.py（Req 21.2）**：`build_uri` 产 AddressEntry 时追加 `register_custom` 进 L3 runtime（与 Req 12 同模式），保留 legacy 产出。
- **query_builder.py（Req 21.3）**：生成的 `TB()` 等 ref 加契约测试断言 grammar_v1 可解析。
- **豁免（Req 21.4/21.5）**：legacy router + ACNR core delegation 记入 Ledger 豁免，CI drift guard 白名单。

## Correctness Properties (Full-Sweep Closure — P26)

### Property 26: Formula-Ref Grammar Closure

*For any* `formula_ref` produced by any of the six formula-construction components (frontend) or by `query_builder.py` (backend), the ref SHALL parse under grammar_v1 (`parseUri`/`_formula_ref_to_addr_id` returns non-null) — i.e. no formula-construction site can emit a ref that ACNR cannot resolve.

**Validates: Requirements 14.6, 14.7, 21.3**

### Property 27: Legacy-Consumer Drift Guard

*For any* new backend module introducing a direct `address_registry.` consumer outside the documented exemption list, the CI drift-guard test SHALL fail unless a corresponding Coverage Ledger entry is added.

**Validates: Requirements 22.2**
