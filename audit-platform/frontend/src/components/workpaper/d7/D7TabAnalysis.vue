<template>
<div class="d7-analysis">
    <div class="toolbar">
      <el-button size="small" @click="exportTemplate">导出模板</el-button>
      <el-button size="small" @click="exportData">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
        <el-button size="small" :loading="importing">导入数据</el-button>
      </el-upload>
    </div>
    <!-- (一) 借方发生额分析 -->
    <div class="analysis-card">
      <h4 class="card-title">(一) 借方发生额分析</h4>
      <el-table :data="debitRows" size="small" border>
        <el-table-column label="对方科目/项目" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.item" size="small" @change="(v: string) => updateDebitCell(row.rowId, 'item', v)" />
            <span v-else>{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDebitCell(row.rowId, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数据来源" width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.dataSource" size="small" @change="(v: string) => updateDebitCell(row.rowId, 'dataSource', v)" />
            <span v-else>{{ row.dataSource }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="removeDebitRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="card-footer">
        <el-button v-if="!isReadonly" size="small" @click="addDebitRow">添加行</el-button>
        <div class="diff-line">
          <span>TB借方合计：{{ fmtAmt(debitTotal) }}</span>
          <span :class="{ 'diff-red': debitDiff !== 0 }">差异：{{ fmtAmt(debitDiff) }}{{ debitDiff === 0 ? ' ✓' : ' ✗' }}</span>
        </div>
      </div>
    </div>

    <!-- (三) 贷方发生额分析 -->
    <div class="analysis-card">
      <h4 class="card-title">(三) 贷方发生额分析</h4>
      <el-table :data="creditRows" size="small" border>
        <el-table-column label="对方科目/项目" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.item" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'item', v)" />
            <span v-else>{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCreditCell(row.rowId, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数据来源" width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.dataSource" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'dataSource', v)" />
            <span v-else>{{ row.dataSource }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="removeCreditRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="card-footer">
        <el-button v-if="!isReadonly" size="small" @click="addCreditRow">添加行</el-button>
        <div class="diff-line">
          <span>TB贷方合计：{{ fmtAmt(creditTotal) }}</span>
          <span :class="{ 'diff-red': creditDiff !== 0 }">差异：{{ fmtAmt(creditDiff) }}{{ creditDiff === 0 ? ' ✓' : ' ✗' }}</span>
        </div>
      </div>
    </div>

    <!-- (四) Top10 债务人 -->
    <div class="analysis-card">
      <h4 class="card-title">(四) 期末Top10债务人</h4>
      <el-alert
        v-if="isHighConcentration"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom:8px"
      >
        前十大客户集中度较高（{{ (top10Concentration * 100).toFixed(1) }}%），请关注客户集中度风险
      </el-alert>
      <el-table :data="top10Rows" size="small" border>
        <el-table-column label="债务人名称" min-width="160">
          <template #default="{ row }">
            <span>{{ row.customerName }}</span>
            <GtIndexChip wp-code="D7-2" :label="`→D7-2`" style="margin-left:4px" />
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }"><span>{{ fmtAmt(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="期初余额" width="120" align="right">
          <template #default="{ row }"><span>{{ fmtAmt(row.priorBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="变动金额" width="120" align="right">
          <template #default="{ row }"><span :class="{ 'diff-red': row.changeAmount !== 0 }">{{ fmtAmt(row.changeAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="变动比例" width="90" align="center">
          <template #default="{ row }"><span :class="{ 'rate-exceed': isRateExceed(row.changeRate) }">{{ fmtPercent(row.changeRate) }}</span></template>
        </el-table-column>
        <el-table-column label="账龄" width="120">
          <template #default="{ row }"><span>{{ row.aging }}</span></template>
        </el-table-column>
        <el-table-column label="期后结转" width="110" align="right">
          <template #default="{ row }"><span>{{ fmtAmt(row.postTransfer) }}</span></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 审计说明/结论 -->
    <div class="audit-notes-section">
      <h4>审计说明</h4>
      <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="对借贷方发生额构成及Top10客户的分析..." />
      <div class="note-actions">
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genAnalysisNote">🤖AI</el-button>
      </div>
    </div>
    <div class="audit-notes-section">
      <h4>审计结论</h4>
      <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="分析程序结论..." />
      <div class="note-actions">
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genAnalysisConclusion">🤖AI</el-button>
      </div>
    </div>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabAnalysis.vue — 分析表 D7-4 (~350行)
 * 4区块卡片：借方+贷方+Top10+审计说明
 * Task: 19.1
 * Requirements: 9.1-9.10, 19.2, 20.1
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD7Analysis } from '../composables/useD7Analysis'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import { useD7AiGenerate } from '../composables/useD7AiGenerate'
import { isChangeRateExceeding } from '../composables/useD7FormulaEngine'
import type { ChecklistResponse } from '../composables/useD7FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: any
}>()

const {
  debitRows, debitTotal, debitDiff,
  creditRows, creditTotal, creditDiff,
  top10Rows, top10Concentration, isHighConcentration,
  auditNotes,
  addDebitRow, addCreditRow,
  removeDebitRow, removeCreditRow,
  updateDebitCell, updateCreditCell,
} = useD7Analysis({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD7ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D7-4',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
  return false
}

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD7AiGenerate(toRef(props, 'wpId'))

async function genAnalysisNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('analysis-note', auditNotes.value.explanation, {
    task: '合同负债分析性复核说明',
    debitTotal: debitTotal.value,
    creditTotal: creditTotal.value,
    debitDiff: debitDiff.value,
    creditDiff: creditDiff.value,
    top10Concentration: top10Concentration.value,
    isHighConcentration: isHighConcentration.value,
  }, 'AI · 分析性复核说明')
  if (text) auditNotes.value.explanation = text
}

async function genAnalysisConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('analysis-note', auditNotes.value.conclusion, {
    task: '合同负债分析程序结论',
    debitDiff: debitDiff.value,
    creditDiff: creditDiff.value,
    top10Concentration: top10Concentration.value,
  }, 'AI · 分析程序结论')
  if (text) auditNotes.value.conclusion = text
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return String(rate)
  return `${(rate * 100).toFixed(1)}%`
}

function isRateExceed(rate: number | '' | 'N/A'): boolean {
  return isChangeRateExceeding(rate, 0.3)
}
</script>

<style scoped>
.d7-analysis { padding: 16px; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }

.analysis-card { margin-bottom: 20px; padding: 16px; border: 1px solid #ebeef5; border-radius: 8px; }
.card-title { font-size: 14px; font-weight: 600; margin: 0 0 12px; color: #303133; }
.card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.diff-line { display: flex; gap: 16px; font-size: 13px; }
.diff-red { color: #f56c6c; font-weight: 600; }
.rate-exceed { color: #f56c6c; font-weight: 600; }

.audit-notes-section { margin-top: 16px; }
.audit-notes-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.note-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
