<template>
  <div class="h3-tab-adjudication-cost">
    <!-- 一、投资性房地产 — 原值 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>一、投资性房地产 — 原值</span>
          <span v-if="!isTriangleBalanced" class="triangle-warn">⚠ 勾稽不平</span>
        </div>
      </template>
      <el-table :data="originalRows" border size="small" class="audit-table" show-summary :summary-method="getOriginalSummary">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column prop="beginBalance" label="期初" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'beginBalance')" />
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="增加" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.increase" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'increase')" />
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="减少" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'decrease')" />
          </template>
        </el-table-column>
        <el-table-column prop="transfer" label="转换" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transfer" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'transfer')" />
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+增加-减少±转换">{{ fmtNum(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.unadjusted" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'unadjusted')" />
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.aje" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'aje')" />
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.rje" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'rje')" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 二、累计折旧 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span>二、累计折旧</span>
      </template>
      <el-table :data="depRows" border size="small" class="audit-table" show-summary :summary-method="getDepSummary">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column prop="beginBalance" label="期初" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'beginBalance')" />
          </template>
        </el-table-column>
        <el-table-column prop="provision" label="计提" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.provision" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'provision')" />
          </template>
        </el-table-column>
        <el-table-column prop="reversal" label="转回" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.reversal" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'reversal')" />
          </template>
        </el-table-column>
        <el-table-column prop="transferDep" label="转换折旧" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transferDep" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'transferDep')" />
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+计提-转回±转换">{{ fmtNum(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.unadjusted" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'unadjusted')" />
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.aje" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'aje')" />
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.rje" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'rje')" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 净值合计 -->
    <el-card shadow="never" class="net-value-card">
      <div class="net-value-row">
        <span class="net-label">净值合计（原值期末 - 折旧期末）</span>
        <span class="net-amount">{{ fmtNum(netValueTotal) }}</span>
      </div>
    </el-card>

    <!-- 审计说明 / 结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-1-cost')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-1-cost')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明/结论..." :disabled="isReadonly" />
      <div class="chip-row">
        <span class="chip-label">跳转：</span>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-6 互转审核')">H3-6 互转审核</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabAdjudicationCost.vue — H3-1 审定表（成本模式）
 * 双区块(原值+折旧)+三角勾稽+TB回写+AI+💬复核+GtIndexChip→H3-6
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH3AdjudicationCost } from '../../composables/useH3AdjudicationCost'
import type { H3CostOriginalRow, H3CostDepRow } from '../../composables/useH3AdjudicationCost'
import { useH3FormData } from '../../composables/useH3FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost'),
})

const {
  originalRows, depRows, originalTotal, depTotal, netValueTotal,
  isTriangleBalanced, updateOriginalCell, updateDepCell,
} = useH3AdjudicationCost({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

const conclusion = ref(getValue('H3-1-cost-conclusion') ?? '')

function onOrigCellChange(row: H3CostOriginalRow, field: keyof H3CostOriginalRow) {
  updateOriginalCell(row.rowId, field, (row as any)[field])
}
function onDepCellChange(row: H3CostDepRow, field: keyof H3CostDepRow) {
  updateDepCell(row.rowId, field, (row as any)[field])
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getOriginalSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '小计'
    const key = ['', 'beginBalance', 'increase', 'decrease', 'transfer', 'endBalance', 'unadjusted', 'aje', 'rje', 'audited'][idx]
    return key ? fmtNum((originalTotal.value as any)[key] ?? 0) : ''
  })
}
function getDepSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '小计'
    const key = ['', 'beginBalance', 'provision', 'reversal', 'transferDep', 'endBalance', 'unadjusted', 'aje', 'rje', 'audited'][idx]
    return key ? fmtNum((depTotal.value as any)[key] ?? 0) : ''
  })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-adjudication-cost { padding: 16px; font-size: 13px; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.triangle-warn { color: var(--el-color-danger); font-size: 12px; font-weight: 600; }
.audit-table { font-size: 13px; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.net-value-card { margin-bottom: 16px; }
.net-value-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; }
.net-label { font-weight: 600; }
.net-amount { font-size: 16px; font-weight: 700; color: var(--el-color-primary); }
.conclusion-card { margin-bottom: 16px; }
.action-btns { display: flex; gap: 4px; }
.chip-row { margin-top: 12px; display: flex; align-items: center; gap: 8px; }
.chip-label { font-size: 12px; color: var(--el-text-color-secondary); }
.nav-chip { cursor: pointer; }
</style>
