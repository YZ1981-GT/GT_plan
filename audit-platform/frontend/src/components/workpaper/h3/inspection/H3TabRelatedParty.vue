<template>
  <div class="h3-tab-related-party">
    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增关联交易</el-button>
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

    <!-- 11列关联交易表 -->
    <el-table :data="rows" border size="small" class="audit-table" :row-class-name="getRowClass" show-summary :summary-method="getSummary">
      <el-table-column prop="seq" label="序号" width="50" align="center" />
      <el-table-column prop="relatedParty" label="关联方" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-model="row.relatedParty" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="relationship" label="关联关系" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.relationship" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="transType" label="交易类型" width="100">
        <template #default="{ row, $index }">
          <el-select v-model="row.transType" size="small" :disabled="isReadonly" @change="onCellChange($index, row)">
            <el-option label="出租" value="出租" />
            <el-option label="购入" value="购入" />
            <el-option label="处置" value="处置" />
            <el-option label="转换" value="转换" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.amount" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="pricingMethod" label="定价方式" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.pricingMethod" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="marketRef" label="市场价参考" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.marketRef" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column label="差异率" width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span
            class="formula-value"
            :class="{ 'text-danger': Math.abs(calcDiffRate(row)) > 10 }"
            title="(金额-市场价)/市场价×100%"
          >
            {{ row.marketRef ? calcDiffRate(row).toFixed(1) + '%' : '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="approvalDoc" label="审批文件" width="70" align="center">
        <template #default="{ row, $index }">
          <el-checkbox v-model="row.approvalDoc" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="审计结论" min-width="100">
        <template #default="{ row, $index }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="onCellChange($index, row)">
            <el-option label="无异常" value="无异常" />
            <el-option label="需关注" value="需关注" />
            <el-option label="不合理" value="不合理" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-13')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-13')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明..." :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabRelatedParty.vue — H3-13 关联交易
 * el-table 11列+差异率>10%红色+合计行
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH3RelatedParty } from '../../composables/useH3RelatedParty'
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
  rows, addRow, updateRow, totalAmount,
} = useH3RelatedParty({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

const auditConclusion = ref(getValue('H3-13-conclusion') ?? '')

function onCellChange(index: number, row: any) { updateRow(index, row) }

function calcDiffRate(row: any): number {
  if (!row.marketRef || row.marketRef === 0) return 0
  return ((row.amount - row.marketRef) / row.marketRef) * 100
}

function getRowClass({ row }: { row: any }): string {
  if (Math.abs(calcDiffRate(row)) > 10) return 'row-danger'
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    if (idx === 4) return fmtNum(totalAmount.value)
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
.h3-tab-related-party { padding: 16px; font-size: 13px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: 13px; }
.audit-table :deep(.row-danger) { background-color: #fef0f0 !important; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); }
.conclusion-card { margin-top: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.export-dropdown { margin-left: auto; }
</style>
