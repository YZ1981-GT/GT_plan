<template>
  <el-popover
    :visible="visible"
    placement="bottom-start"
    :width="420"
    trigger="manual"
    popper-class="cross-sheet-trace-popover"
  >
    <template #reference>
      <slot />
    </template>

    <div class="trace-content">
      <div v-if="loading" class="trace-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载引用链...</span>
      </div>

      <div v-else-if="error" class="trace-error">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ error }}</span>
      </div>

      <div v-else-if="traceData" class="trace-chain">
        <div class="trace-header">
          <span class="trace-title">跨 sheet 引用链</span>
          <el-tag v-if="traceData.has_cycle" type="danger" size="small">
            ⚠ 循环引用
          </el-tag>
          <el-tag v-if="traceData.truncated_at_depth !== null" type="warning" size="small">
            截断于第 {{ traceData.truncated_at_depth }} 层
          </el-tag>
        </div>

        <div class="trace-nodes">
          <div
            v-for="(node, idx) in traceData.chain"
            :key="idx"
            class="trace-node"
            :class="{
              'is-cycle': node.cycle,
              'is-missing': node.missing,
              'is-truncated': node.truncated,
            }"
            :style="{ paddingLeft: `${node.depth * 16 + 8}px` }"
          >
            <span class="node-depth">L{{ node.depth }}</span>
            <span class="node-uri" :title="node.uri">{{ node.uri }}</span>

            <span v-if="node.cycle" class="node-badge cycle">⚠ 循环</span>
            <span v-else-if="node.missing" class="node-badge missing">⚠ 缺失</span>
            <span v-else-if="node.truncated" class="node-badge truncated">…更多</span>
            <span v-else class="node-value" :title="String(node.value ?? '')">
              {{ formatValue(node.value) }}
            </span>

            <span v-if="node.formula" class="node-formula" :title="node.formula">
              ƒ {{ node.formula }}
            </span>
          </div>
        </div>
      </div>

      <div v-else class="trace-empty">
        无跨 sheet 引用
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import request from '@/utils/request'

interface RefChainNode {
  depth: number
  uri: string
  value: any
  formula?: string
  truncated?: boolean
  cycle?: boolean
  missing?: boolean
}

interface RefChainResponse {
  chain: RefChainNode[]
  has_cycle: boolean
  truncated_at_depth: number | null
}

const props = defineProps<{
  wpCode: string
  sheetName: string
  cellRef: string
  projectId: string
  formula?: string
  hoverActive?: boolean
}>()

const visible = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const traceData = ref<RefChainResponse | null>(null)

let showTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

// 300ms delay before showing
watch(
  () => props.hoverActive,
  (active) => {
    if (active) {
      if (hideTimer) {
        clearTimeout(hideTimer)
        hideTimer = null
      }
      showTimer = setTimeout(() => {
        visible.value = true
        fetchTrace()
      }, 300)
    } else {
      if (showTimer) {
        clearTimeout(showTimer)
        showTimer = null
      }
      // 200ms delay before hiding (avoid flicker)
      hideTimer = setTimeout(() => {
        visible.value = false
      }, 200)
    }
  }
)

async function fetchTrace() {
  if (!props.wpCode || !props.sheetName || !props.cellRef) return

  loading.value = true
  error.value = null
  traceData.value = null

  try {
    const params = new URLSearchParams({
      wp_code: props.wpCode,
      sheet_name: props.sheetName,
      cell_ref: props.cellRef,
      project_id: props.projectId,
      max_depth: '3',
    })
    const res = await request.get(`/api/custom-query/cross-sheet-trace?${params}`)
    traceData.value = res.data ?? res
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载超时'
  } finally {
    loading.value = false
  }
}

function formatValue(value: any): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return String(value)
  const str = String(value)
  return str.length > 30 ? str.slice(0, 30) + '…' : str
}

onBeforeUnmount(() => {
  if (showTimer) clearTimeout(showTimer)
  if (hideTimer) clearTimeout(hideTimer)
})
</script>

<style scoped>
.trace-content {
  max-height: 320px;
  overflow-y: auto;
}

.trace-loading,
.trace-error,
.trace-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.trace-error {
  color: var(--el-color-danger);
}

.trace-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.trace-title {
  font-weight: 600;
  font-size: 13px;
}

.trace-nodes {
  padding: 8px 0;
}

.trace-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 12px;
  line-height: 1.6;
  border-left: 2px solid transparent;
}

.trace-node.is-cycle {
  border-left-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.trace-node.is-missing {
  border-left-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

.trace-node.is-truncated {
  border-left-color: var(--el-color-info);
  opacity: 0.7;
}

.node-depth {
  flex-shrink: 0;
  width: 24px;
  font-size: 10px;
  color: var(--el-text-color-placeholder);
  font-weight: 600;
}

.node-uri {
  flex-shrink: 0;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: monospace;
  color: var(--el-color-primary);
}

.node-badge {
  flex-shrink: 0;
  font-size: 11px;
  padding: 0 4px;
  border-radius: 3px;
}

.node-badge.cycle {
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.node-badge.missing {
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

.node-badge.truncated {
  color: var(--el-text-color-secondary);
}

.node-value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-text-color-regular);
}

.node-formula {
  flex-shrink: 0;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-style: italic;
  color: #e67e22;
  font-size: 11px;
}
</style>
