<template>
  <div class="h3-tab-adjudication-fair">
    <!-- 单区块：投资性房地产（公允价值） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>投资性房地产 — 公允价值模式</span>
        </div>
      </template>
      <el-table :data="fairRows" border size="small" class="audit-table" show-summary :summary-method="getFairSummary">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column prop="beginFair" label="期初公允" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginFair" size="small" :disabled="isReadonly" @change="onCellChange(row, 'beginFair')" />
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.increase" size="small" :disabled="isReadonly" @change="onCellChange(row, 'increase')" />
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" @change="onCellChange(row, 'decrease')" />
          </template>
        </el-table-column>
        <el-table-column prop="transfer" label="转换" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transfer" size="small" :disabled="isReadonly" @change="onCellChange(row, 'transfer')" />
          </template>
        </el-table-column>
        <el-table-column prop="fairValueChange" label="公允价值变动" min-width="120" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.fairValueChange" size="small" :disabled="isReadonly" @change="onCellChange(row, 'fairValueChange')" />
          </template>
        </el-table-column>
        <el-table-column label="期末公允" min-width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+增加-减少±转换+公允变动">{{ fmtNum(row.endFair) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.unadjusted" size="small" :disabled="isReadonly" @change="onCellChange(row, 'unadjusted')" />
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.aje" size="small" :disabled="isReadonly" @change="onCellChange(row, 'aje')" />
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.rje" size="small" :disabled="isReadonly" @change="onCellChange(row, 'rje')" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 公允价值变动损益汇总 -->
    <el-card shadow="never" class="summary-card">
      <div class="summary-row">
        <span>公允价值变动损益合计</span>
        <span class="summary-amount">{{ fmtNum(totalFairValueChange) }}</span>
      </div>
    </el-card>

    <!-- 审计说明 / 结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-1-fair')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-1-fair')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明/结论..." :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabAdjudicationFair.vue — H3-1 审定表（公允价值模式）
 * 单区块公允+公允变动+TB回写+AI+💬复核
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH3AdjudicationFair } from '../../composables/useH3AdjudicationFair'
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
  measurementModel: ref('fair_value'),
})

const {
  fairRows, fairTotal, totalFairValueChange, updateFairCell,
} = useH3AdjudicationFair({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

const conclusion = ref(getValue('H3-1-fair-conclusion') ?? '')

function onCellChange(row: any, field: string) {
  updateFairCell(row.rowId, field, row[field])
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getFairSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '小计'
    const key = ['', 'beginFair', 'increase', 'decrease', 'transfer', 'fairValueChange', 'endFair', 'unadjusted', 'aje', 'rje', 'audited'][idx]
    return key ? fmtNum((fairTotal.value as any)[key] ?? 0) : ''
  })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-adjudication-fair { padding: 16px; font-size: 13px; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.audit-table { font-size: 13px; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.summary-card { margin-bottom: 16px; }
.summary-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; font-weight: 600; }
.summary-amount { font-size: 16px; color: var(--el-color-warning); }
.conclusion-card { margin-bottom: 16px; }
.action-btns { display: flex; gap: 4px; }
</style>
