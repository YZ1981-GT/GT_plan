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
- `full_resolve` 是异步的，但 CrossSheetResolver 是同步 BFS → 使用 `_sync_resolve` 包装器（`asyncio.run_coroutine_threadsafe` 或在已有 event loop 中 `loop.run_until_complete`）。若性能敏感可改为 batch resolve。
- `RefChainNode` 新增 `resolve_missed: bool = False` 字段（向后兼容，默认 False）。
- 异常只 log warning，不中断 BFS（容错第一）。

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
