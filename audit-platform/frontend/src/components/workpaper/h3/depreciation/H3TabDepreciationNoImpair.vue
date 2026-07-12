<template>
  <div class="h3-tab-depreciation-no-impair">
    <!-- 成本模式限定提示 -->
    <el-alert title="折旧测算 — 不含减值（直线法）" type="info" :closable="false" show-icon class="mode-alert">
      本表仅适用于成本模式，计算月折旧=原值×(1-残值率)/使用年限/12
    </el-alert>

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增资产行</el-button>
      <el-dropdown size="small" class="export-dropdown">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item>导出模板</el-dropdown-item>
            <el-dropdown-item>导出数据</el-dropdown-item>
            <el-dropdown-item>导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 28列折旧测算表（不含减值） -->
    <el-table :data="rows" border size="small" class="audit-table" :row-class-name="getRowClass" show-summary :summary-method="getSummary">
      <el-table-column prop="assetName" label="资产名称" min-width="120" fixed />
      <el-table-column prop="originalCost" label="原值" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.originalCost" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="salvageRate" label="残值率" width="80" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.salvageRate" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="usefulLife" label="年限(年)" width="80" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.usefulLife" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="elapsedYears" label="已用(年)" width="80" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.elapsedYears" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column label="月折旧" min-width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="原值×(1-残值率)/年限/12">{{ fmtNum(row.monthlyDep) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="年折旧" min-width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="月折旧×12">{{ fmtNum(row.annualDep) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="测算累计" min-width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="月折旧×已用月数">{{ fmtNum(row.accDepCalc) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accDepBook" label="账面累计" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.accDepBook" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column label="差异" min-width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'text-danger': Math.abs(row.difference) > 0.01 }">
            {{ fmtNum(row.difference) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计验证 -->
    <div class="summary-row">
      <span>测算累计合计：<b>{{ fmtNum(totalAccDepCalc) }}</b></span>
      <span>账面累计合计：<b>{{ fmtNum(totalAccDepBook) }}</b></span>
      <span>差异合计：<b :class="{ 'text-danger': Math.abs(totalDifference) > 0.01 }">{{ fmtNum(totalDifference) }}</b></span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-7-no-impair')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-7-no-impair')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明..." :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDepreciationNoImpair.vue — H3-7(A) 折旧不含减值
 * 28列42公式+差异高亮（仅成本模式）
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH3Depreciation } from '../../composables/useH3Depreciation'
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
  measurementModel: ref('cost') as any,
})

const {
  rows, addRow, updateRow, totalAccDepCalc, totalAccDepBook, totalDifference,
} = useH3Depreciation({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

const auditConclusion = ref(getValue('H3-7-noimpair-conclusion') ?? '')

function onCellChange(index: number, row: any) { updateRow(index, row) }

function getRowClass({ row }: { row: any }): string {
  if (Math.abs(row.difference) > 0.01) return 'row-warn'
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '合计'
    if (idx === 7) return fmtNum(totalAccDepCalc.value)
    if (idx === 8) return fmtNum(totalAccDepBook.value)
    if (idx === 9) return fmtNum(totalDifference.value)
    return ''
  })
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-depreciation-no-impair { padding: 16px; font-size: var(--wp-font-size, 13px); }
.mode-alert { margin-bottom: 16px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.audit-table :deep(.row-warn) { background-color: #fef9e7 !important; }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); }
.summary-row { display: flex; align-items: center; gap: 16px; margin: 12px 0; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.conclusion-card { margin-top: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.export-dropdown { margin-left: auto; }
</style>
