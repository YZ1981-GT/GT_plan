<!--
  CustomQueryFieldPicker.vue — 高级查询「选字段」ACNR 地址树

  spec advanced-query-module Task 18.1（满足 acnr-consumer-wiring Req 8）

  职责：
  - 复用 useAcnr 的 buildAddressTree / loadCellNodes / listSheets 构建选字段树
    （不自建下拉，与公式选址同一棵树）
  - sheet 层懒加载 cell 子节点（loadCellNodes）
  - 选中 cell 节点 → 记录 node.addrId 作为查询字段标识（R2.4）+ emit addrId + formulaRef（acnr Req 8.4）
  - 域内登记数为 0 → 不渲染分组节点 + 空态提示（R1.7 / R1.8）
  - list_sheets / list_cells 失败或 10s 无响应（AbortController）→
    加载失败提示 + 保留已选字段 + 重新加载入口（R2.7）
  - cycle prop 过滤 + showCycleFilter 循环下拉（acnr Req 8.5）
  - 监听 template-applied 事件 → clearCache + reload（acnr Req 8.6）

  Requirements（advanced-query-module）: 2.1, 2.2, 2.3, 2.4, 1.7, 1.8, 2.7
  Requirements（acnr-consumer-wiring Task 7.1）: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8
-->
<template>
  <div class="gt-cqfp">
    <div class="gt-cqfp-header">
      <span class="gt-cqfp-title">选字段（ACNR 地址树）</span>
      <span class="gt-cqfp-hint">与公式选址同一棵树 · 选中格记录 addr_id</span>
    </div>

    <!-- 循环过滤下拉（acnr Req 8.5，默认隐藏，showCycleFilter 开启后显示） -->
    <div v-if="showCycleFilter" class="gt-cqfp-cycle-filter">
      <el-select
        v-model="selectedCycle"
        placeholder="全部循环"
        clearable
        size="small"
        class="gt-cqfp-cycle-select"
        @change="onCycleChange"
      >
        <el-option v-for="c in cycleOptions" :key="c" :label="`${c} 循环`" :value="c" />
      </el-select>
    </div>

    <div class="gt-cqfp-body">
      <!-- 加载失败：保留已选 + 重载入口（R2.7） -->
      <div v-if="loadState === 'error'" class="gt-cqfp-state gt-cqfp-state--error">
        <el-icon class="gt-cqfp-state-icon"><WarnTriangleFilled /></el-icon>
        <div class="gt-cqfp-state-text">地址树加载失败或超时（10 秒无响应）</div>
        <el-button size="small" type="primary" plain @click="reload">
          <el-icon style="margin-right: 4px"><Refresh /></el-icon>
          重新加载
        </el-button>
      </div>

      <!-- 空态：该域暂无已登记内容（R1.7 / R1.8） -->
      <div v-else-if="loadState === 'empty'" class="gt-cqfp-state">
        <el-empty :image-size="60" description="该域暂无已登记内容，暂不可查询" />
        <el-button size="small" text @click="reload">刷新</el-button>
      </div>

      <!-- 地址树 -->
      <div v-else v-loading="loadState === 'loading'" class="gt-cqfp-tree-wrap">
        <el-tree
          :key="treeKey"
          ref="treeRef"
          class="gt-cqfp-tree"
          node-key="value"
          lazy
          :load="loadNode"
          :props="treeProps"
          :expand-on-click-node="true"
          highlight-current
          @node-click="onNodeClick"
        >
          <!-- 不解构 slot 作用域：el-tree（含未解析/懒加载占位）可能以 undefined 作用域
               调用 #default，解构 { data } 会抛错。改用整体 scope + 可选链守卫防崩。 -->
          <template #default="scope">
            <span
              v-if="scope && scope.data"
              class="gt-cqfp-node"
              :class="{
                'gt-cqfp-node--cell': scope.data.nodeType === 'cell',
                'gt-cqfp-node--selected': scope.data.nodeType === 'cell' && isSelected(scope.data.addrId),
              }"
            >
              <el-icon v-if="scope.data.nodeType === 'cell' && isSelected(scope.data.addrId)" class="gt-cqfp-node-check">
                <Select />
              </el-icon>
              {{ scope.data.label }}
              <span v-if="scope.data.nodeType === 'cell'" class="gt-cqfp-node-addr">{{ scope.data.addrId }}</span>
            </span>
          </template>
        </el-tree>
      </div>
    </div>

    <!-- 已选字段（独立于树，reload 后保留不变 R2.7） -->
    <div class="gt-cqfp-selected">
      <div class="gt-cqfp-selected-header">
        已选字段（{{ modelValue.length }}）
        <el-button
          v-if="modelValue.length"
          size="small"
          link
          type="danger"
          @click="clearAll"
        >清空</el-button>
      </div>
      <div v-if="!modelValue.length" class="gt-cqfp-selected-empty">
        在上方树中点击单元格节点以选为查询字段
      </div>
      <div v-else class="gt-cqfp-tags">
        <el-tag
          v-for="addrId in modelValue"
          :key="addrId"
          size="small"
          closable
          type="info"
          effect="plain"
          @close="removeField(addrId)"
        >
          {{ labelOf(addrId) }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { WarnTriangleFilled, Refresh, Select } from '@element-plus/icons-vue'
import { useAcnr, type AcnrSheetEntry, type AcnrCellEntry } from '@/services/acnr/useAcnr'
import { eventBus } from '@/utils/eventBus'

const props = withDefaults(
  defineProps<{
    /** v-model：已选字段的 addr_id 列表 */
    modelValue?: string[]
    /** 循环码过滤（如 'D'），不传返回所有循环 */
    cycle?: string
    /** 是否显示内置循环过滤下拉（acnr Req 8.5） */
    showCycleFilter?: boolean
  }>(),
  { modelValue: () => [], cycle: undefined, showCycleFilter: false },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void
  (
    e: 'select',
    node: { addrId: string; formulaRef: string | null; label: string; meta?: AcnrCellEntry },
  ): void
}>()

const { buildAddressTree, loadCellNodes, clearCache } = useAcnr()

// ─── 循环过滤（acnr Req 8.5） ────────────────────────────────────────────────
const cycleOptions = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'S']
const selectedCycle = ref<string>(props.cycle || '')

// ─── 树节点类型 ──────────────────────────────────────────────────────────────
type PickerNodeType = 'group' | 'sheet' | 'cell'
interface PickerNode {
  label: string
  value: string
  addrId: string
  nodeType: PickerNodeType
  isLeaf?: boolean
  meta?: AcnrSheetEntry | AcnrCellEntry
}

const treeProps = { label: 'label', children: 'children', isLeaf: 'isLeaf' } as const

const treeRef = ref()
const treeKey = ref(0)
const loadState = ref<'loading' | 'loaded' | 'empty' | 'error'>('loading')

// 已加载的分组 → sheet 子节点缓存（供分组懒加载复用 buildAddressTree 结果）
const groupChildren = new Map<string, PickerNode[]>()

// 已选字段 addr_id → 可读标签（用于 tag 展示，reload 后保留）
const labelMap = ref<Record<string, string>>({})

const TIMEOUT_MS = 10_000
let activeController: AbortController | null = null

/** 10s 超时竞速（AbortController）：超时视为加载失败（R2.7） */
function raceWithTimeout<T>(p: Promise<T>): Promise<T> {
  const controller = new AbortController()
  activeController = controller
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      controller.abort()
      reject(new Error('acnr_field_tree_timeout'))
    }, TIMEOUT_MS)
    p.then(
      (v) => {
        clearTimeout(timer)
        resolve(v)
      },
      (e) => {
        clearTimeout(timer)
        reject(e)
      },
    )
  })
}

// ─── 懒加载 ─────────────────────────────────────────────────────────────────
async function loadNode(node: any, resolve: (data: PickerNode[]) => void) {
  // root（level 0）→ 分组节点（buildAddressTree）
  if (node.level === 0) {
    await loadRoot(resolve)
    return
  }
  const data = node.data as PickerNode
  // 分组节点 → 该分组下的 sheet 子节点（复用 buildAddressTree 结果）
  if (data.nodeType === 'group') {
    resolve(groupChildren.get(data.value) || [])
    return
  }
  // sheet 节点 → 懒加载 cell 子节点（loadCellNodes / list_cells，R2.2）
  if (data.nodeType === 'sheet') {
    await loadCells(data, resolve)
    return
  }
  resolve([])
}

/** 加载根：buildAddressTree（list_sheets，R2.1）；空 → 空态；失败/超时 → error（R2.7） */
async function loadRoot(resolve: (data: PickerNode[]) => void) {
  loadState.value = 'loading'
  try {
    const tree = await raceWithTimeout(buildAddressTree(selectedCycle.value || undefined))
    if (!Array.isArray(tree) || tree.length === 0) {
      // 域内登记数为 0 → 隐藏分组节点 + 空态提示（R1.7 / R1.8）
      loadState.value = 'empty'
      resolve([])
      return
    }
    groupChildren.clear()
    const groups: PickerNode[] = tree.map((g) => {
      const children: PickerNode[] = (g.children || []).map((s) => ({
        label: s.label,
        value: s.addrId,
        addrId: s.addrId,
        nodeType: 'sheet',
        isLeaf: false,
        meta: s.meta as AcnrSheetEntry,
      }))
      groupChildren.set(g.value, children)
      return {
        label: g.label,
        value: g.value,
        addrId: g.addrId,
        nodeType: 'group',
        isLeaf: false,
      }
    })
    loadState.value = 'loaded'
    resolve(groups)
  } catch (e) {
    // list_sheets 失败或 10s 无响应（R2.7）：保留已选、提供重载入口
    loadState.value = 'error'
    resolve([])
  }
}

/** 加载 cell 子节点：loadCellNodes（list_cells）；失败/超时 → 提示 + 保留已选（R2.7） */
async function loadCells(sheetNode: PickerNode, resolve: (data: PickerNode[]) => void) {
  try {
    const meta = sheetNode.meta as AcnrSheetEntry
    const cells = await raceWithTimeout(loadCellNodes(meta))
    const cellNodes: PickerNode[] = (cells || []).map((c) => ({
      label: c.label,
      value: c.addrId,
      addrId: c.addrId,
      nodeType: 'cell',
      isLeaf: true,
      meta: c.meta as AcnrCellEntry,
    }))
    resolve(cellNodes)
  } catch (e) {
    ElMessage.error(`单元格加载失败或超时：${sheetNode.label}，请重新展开重试`)
    resolve([])
  }
}

// ─── 选择 ───────────────────────────────────────────────────────────────────
function isSelected(addrId: string): boolean {
  return props.modelValue.includes(addrId)
}

function onNodeClick(data: PickerNode) {
  // 仅 cell 节点可选为查询字段（R2.4）
  if (data.nodeType !== 'cell') return
  toggleField(data)
}

function toggleField(data: PickerNode) {
  const next = [...props.modelValue]
  const idx = next.indexOf(data.addrId)
  if (idx >= 0) {
    next.splice(idx, 1)
  } else {
    next.push(data.addrId)
    // 记录 addr_id → 可读标签
    labelMap.value = { ...labelMap.value, [data.addrId]: data.label }
    // acnr Req 8.4：emit addr_id + formula_ref（供父级查询表单构造引用）
    const cellMeta = data.meta as AcnrCellEntry | undefined
    emit('select', {
      addrId: data.addrId,
      formulaRef: cellMeta?.formula_ref ?? null,
      label: data.label,
      meta: cellMeta,
    })
  }
  emit('update:modelValue', next)
}

function removeField(addrId: string) {
  emit('update:modelValue', props.modelValue.filter((a) => a !== addrId))
}

function clearAll() {
  emit('update:modelValue', [])
}

function labelOf(addrId: string): string {
  return labelMap.value[addrId] || addrId
}

// ─── 重载（R2.7 保留已选字段不变） ──────────────────────────────────────────
function reload() {
  // 已选字段存于 modelValue + labelMap，独立于树 DOM，重挂树不影响已选
  groupChildren.clear()
  loadState.value = 'loading'
  treeKey.value += 1 // 强制 el-tree 重挂 → 重新触发 loadRoot
}

// 循环下拉切换（acnr Req 8.5）→ 重载树
function onCycleChange() {
  reload()
}

// 外部 cycle prop 变化 → 同步内部选择并重载（acnr Req 8.5）
watch(
  () => props.cycle,
  (val) => {
    if (val !== undefined && val !== selectedCycle.value) {
      selectedCycle.value = val || ''
      reload()
    }
  },
)

// ACNR catalog 更新（template-applied）→ 清缓存 + 重载（acnr Req 8.6）
function onTemplateApplied() {
  clearCache()
  reload()
}

onMounted(() => {
  eventBus.on('template-applied', onTemplateApplied)
})

onBeforeUnmount(() => {
  activeController?.abort()
  eventBus.off('template-applied', onTemplateApplied)
})

defineExpose({ reload })
</script>

<style scoped>
.gt-cqfp {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
.gt-cqfp-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.gt-cqfp-title {
  font-size: var(--gt-font-size-sm, 13px);
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}
.gt-cqfp-hint {
  font-size: 11px;
  color: var(--gt-color-info, #909399);
}
.gt-cqfp-cycle-filter {
  display: flex;
  align-items: center;
}
.gt-cqfp-cycle-select {
  width: 160px;
}
.gt-cqfp-body {
  border: 1px solid var(--gt-color-border-lighter, #ebeef5);
  border-radius: 6px;
  min-height: 180px;
  max-height: 320px;
  overflow: auto;
}
.gt-cqfp-tree-wrap {
  min-height: 176px;
  padding: 4px;
}
.gt-cqfp-tree {
  font-size: 13px;
}
.gt-cqfp-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px 12px;
  text-align: center;
}
.gt-cqfp-state--error {
  color: var(--gt-color-coral, #e6684b);
}
.gt-cqfp-state-icon {
  font-size: 28px;
}
.gt-cqfp-state-text {
  font-size: 12px;
}
.gt-cqfp-node {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.gt-cqfp-node--cell {
  color: var(--gt-color-text-regular, #606266);
}
.gt-cqfp-node--selected {
  color: var(--gt-color-primary, #5b3aa8);
  font-weight: 600;
}
.gt-cqfp-node-check {
  color: var(--gt-color-primary, #5b3aa8);
}
.gt-cqfp-node-addr {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 10px;
  color: var(--gt-color-info, #909399);
  margin-left: 6px;
}
.gt-cqfp-selected {
  border: 1px dashed var(--gt-color-border-lighter, #ebeef5);
  border-radius: 6px;
  padding: 8px;
}
.gt-cqfp-selected-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
  margin-bottom: 6px;
}
.gt-cqfp-selected-empty {
  font-size: 11px;
  color: var(--gt-color-info, #909399);
}
.gt-cqfp-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
