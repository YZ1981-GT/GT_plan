<template>
<div class="f1-confirmation-procedure">
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-tag type="info" size="small">有余额户 {{ coverage.totalAccounts }}</el-tag>
      <el-tag type="success" size="small">已发函 {{ coverage.confirmedAccounts }}</el-tag>
      <el-tag :type="coverageTagType" size="small">
        金额覆盖率 {{ coverageLabel }}
      </el-tag>
    </div>
    <div class="toolbar-right">
      <el-button size="small" link type="primary" @click="guideVisible = true">使用手册</el-button>
      <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
      <GtIndexChip value="wp:F0-1" :context-project-id="projectId" />
      <GtIndexChip value="wp:F0-5" :context-project-id="projectId" />
    </div>
  </div>

  <el-alert type="info" :closable="false" show-icon class="guide-alert">
    <template #title>
      从 F1-2 筛选拟发函对象 → 勾选后「标记已发函(Y)」写回明细 → 在 F0-1 维护发函/回函；未回函对象在 F0-5 执行替代程序。
    </template>
  </el-alert>

  <div class="action-bar">
    <el-input
      v-model="searchQuery"
      size="small"
      clearable
      placeholder="搜索供应商名称"
      style="max-width: 220px"
    />
    <el-button
      size="small"
      type="primary"
      :disabled="isReadonly || selectedRowIds.length === 0"
      @click="markSelectedConfirmed"
    >
      标记已发函 (Y)
    </el-button>
    <el-button size="small" :disabled="isReadonly" @click="selectUnconfirmed">选中未发函</el-button>
  </div>

  <el-table
    ref="tableRef"
    :data="filteredCandidates"
    size="small"
    border
    stripe
    max-height="520"
    row-key="rowId"
    @selection-change="onSelectionChange"
  >
    <el-table-column v-if="!isReadonly" type="selection" width="42" reserve-selection />
    <el-table-column label="序号" type="index" width="52" />
    <el-table-column prop="customerName" label="供应商名称" min-width="160" show-overflow-tooltip />
    <el-table-column label="期末审定余额" width="130" align="right">
      <template #default="{ row }">
        <span class="amt">{{ fmtAmount(row.endAudited) }}</span>
      </template>
    </el-table-column>
    <el-table-column prop="relationType" label="关联方" width="90" />
    <el-table-column label="发函(Y)" width="90" align="center">
      <template #default="{ row }">
        <el-tag v-if="isConfirmedMarked(row.isConfirmed)" type="success" size="small">Y</el-tag>
        <span v-else class="muted">—</span>
      </template>
    </el-table-column>
  </el-table>

  <el-empty v-if="candidates.length === 0" description="F1-2 暂无有余额的预付对象，请先编制明细表" />

  <F1ConfirmationUsageGuide v-model="guideVisible" />
</div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { ChecklistResponse } from '../composables/useF1FormData'
import {
  F1_DETAIL_ROWS_ITEM_ID,
  parseConfirmationCandidates,
  computeConfirmationCoverage,
  markRowsConfirmedInJson,
  isConfirmedMarked,
  type F1ConfirmationCandidate,
} from '../composables/useF1ConfirmationProcedure'
// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import F1ConfirmationUsageGuide from './F1ConfirmationUsageGuide.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
}>()

const allResponsesRef = toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>
const guideVisible = ref(false)
const searchQuery = ref('')
const selectedRowIds = ref<string[]>([])
const tableRef = ref<{ clearSelection?: () => void } | null>(null)

const detailJson = computed(() => allResponsesRef.value.get(F1_DETAIL_ROWS_ITEM_ID)?.remark)

const candidates = computed(() => parseConfirmationCandidates(detailJson.value))

const filteredCandidates = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return candidates.value
  return candidates.value.filter(r => r.customerName.toLowerCase().includes(q))
})

const coverage = computed(() => computeConfirmationCoverage(candidates.value))

const coverageLabel = computed(() => {
  if (coverage.value.coverageRatio == null) return '—'
  return `${coverage.value.coverageRatio.toFixed(1)}%`
})

const coverageTagType = computed(() => {
  const ratio = coverage.value.coverageRatio
  if (ratio == null) return 'info'
  if (ratio >= 70) return 'success'
  if (ratio >= 50) return 'warning'
  return 'danger'
})

watch(detailJson, () => {
  selectedRowIds.value = []
  tableRef.value?.clearSelection?.()
})

function onSelectionChange(rows: Array<{ rowId: string }>) {
  selectedRowIds.value = rows.map(r => r.rowId)
}

function selectUnconfirmed() {
  const table = tableRef.value as {
    clearSelection?: () => void
    toggleRowSelection?: (row: F1ConfirmationCandidate, selected?: boolean) => void
  } | null
  table?.clearSelection?.()
  for (const row of filteredCandidates.value) {
    if (!isConfirmedMarked(row.isConfirmed)) {
      table?.toggleRowSelection?.(row, true)
    }
  }
}

async function markSelectedConfirmed() {
  if (props.isReadonly || selectedRowIds.value.length === 0) return
  const { json, changed } = markRowsConfirmedInJson(detailJson.value, selectedRowIds.value)
  if (changed <= 0) {
    ElMessage.info('所选对象均已标记发函')
    return
  }
  await props.saveImmediate(F1_DETAIL_ROWS_ITEM_ID, { remark: json })
  ElMessage.success(`已标记 ${changed} 户发函(Y)，请继续在 F0-1 维护函证汇总`)
  selectedRowIds.value = []
  tableRef.value?.clearSelection?.()
}

function fmtAmount(val: number): string {
  if (!val) return '-'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.f1-confirmation-procedure { padding: 16px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.guide-alert { margin-bottom: 12px; }
.action-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.amt { font-variant-numeric: tabular-nums; }
.muted { color: #909399; }
</style>
