<template>
  <div class="i1-tab-amort-no-impair">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><b>CAS6剩余年限法（不含减值）：</b>月摊销 = (原值 - 残值 - 累计摊销) ÷ 剩余月数。逐资产逐月计算1~28月摊销额横向矩阵，与账面核对差异。适用于不存在减值情况的无形资产。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>I1-10 摊销测算表（不含减值）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSyncFromDetail">
              同步I1-2参数
            </el-button>
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" link @click="handleReview">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="currentRows"
        border
        stripe
        size="small"
        max-height="520"
        class="amort-matrix-table"
        show-summary
        :summary-method="getSummaryRow"
      >
        <el-table-column type="index" label="#" width="35" fixed />
        <el-table-column prop="name" label="资产名称" width="120" fixed show-overflow-tooltip />
        <el-table-column label="原值" width="100" align="right" fixed>
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.cost"
              :controls="false"
              size="small"
              :min="0"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'cost', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="残值" width="90" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.salvage"
              :controls="false"
              size="small"
              :min="0"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'salvage', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.salvage) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计摊销" width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.accAmortBegin"
              :controls="false"
              size="small"
              :min="0"
              :precision="2"
              class="cell-input"
              @change="handleFieldChange($index, 'accAmortBegin', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.accAmortBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="剩余月数" width="75" align="center">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.remainingMonths"
              :controls="false"
              size="small"
              :min="0"
              :max="600"
              class="cell-input"
              @change="handleRemainingChange($index, $event)"
            />
            <span v-else>{{ row.remainingMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column label="月摊销额" width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              title="月摊销=(原值-残值-累计摊销)÷剩余月数"
            >{{ fmtAmt(row.monthlyAmortAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 28个月列 -->
        <el-table-column
          v-for="m in MATRIX_COLUMNS"
          :key="m"
          :label="`第${m}月`"
          width="78"
          align="right"
        >
          <template #default="{ row }">
            <span
              class="formula-cell"
              :title="`第${m}月摊销额`"
            >{{ fmtAmt(row.monthlyAmort[m - 1]) }}</span>
          </template>
        </el-table-column>

        <!-- 本期合计 -->
        <el-table-column label="本期合计" width="110" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              title="本期合计=SUM(第1月~第28月)"
            >{{ fmtAmt(row.periodAmortization) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行独立展示 -->
      <div class="totals-bar">
        <span>摊销合计: <b class="amount-cell">{{ fmtAmt(summaryRow.periodTotal) }}</b></span>
        <span>资产数: <b>{{ currentRows.length }}</b> 项</span>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>摊销测算审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明摊销测算差异原因及审计结论..."
        @blur="handleSaveNote"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>剩余年限法：月摊销 = (原值 - 残值 - 累计摊销) ÷ 剩余月数</li>
        <li>28列对应审计期间内每月的摊销额（通常恒定）</li>
        <li>若资产已摊销完毕（剩余月数≤0），该行摊销额显示为0</li>
        <li>点击"同步I1-2参数"可从明细表自动导入资产信息</li>
        <li>如有减值情况请切换到"含减值（I1-11）"分支</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, inject, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI1Amortization, type I1AmortizationRow, type I1AssetParams } from '../../composables/useI1Amortization'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  currentRows,
  currentItemId,
  summaryRow,
  MATRIX_COLUMNS,
  recalcAll,
  recalcRow,
  syncFromDetail,
  updateRowField,
} = useI1Amortization(toRef(props, 'wpId'), allResponsesRef as any, {
  onSave: (itemId, value) => emit('save', itemId, value),
})

// ─── State ───────────────────────────────────────────────────────────────────

const auditNote = ref('')

// Load note from allResponses
watch(() => props.allResponses, (responses) => {
  const item = responses.get('I1-10-note')
  if (item) {
    auditNote.value = (item as any).remark ?? (item as any).conclusion ?? ''
  }
}, { immediate: true })

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleFieldChange(rowIndex: number, field: keyof I1AmortizationRow, value: number | null) {
  updateRowField(rowIndex, field, value ?? 0)
}

function handleRemainingChange(rowIndex: number, value: number | null) {
  const rows = currentRows.value
  const row = rows[rowIndex]
  if (!row) return
  row.remainingMonths = value ?? 0
  row.usefulLifeMonths = row.usedMonths + (value ?? 0)
  recalcRow(rowIndex)
}

async function handleSyncFromDetail() {
  try {
    await ElMessageBox.confirm(
      '将从I1-2明细表同步资产参数（名称/原值/残值/使用寿命），现有手工调整将被覆盖。是否继续？',
      '同步I1-2参数',
      { confirmButtonText: '确定同步', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  // Extract asset params from allResponses I1-2 detail data
  const detailData = props.allResponses.get('I1-2-rows')
  const raw = (detailData as any)?.remark ?? (detailData as any)?.conclusion
  if (!raw) {
    ElMessageBox.alert('未找到I1-2明细表数据，请先完善明细表。', '提示')
    return
  }

  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      ElMessageBox.alert('I1-2明细表暂无资产数据。', '提示')
      return
    }
    const assetParams: I1AssetParams[] = parsed.map((item: any) => ({
      rowId: item.rowId ?? '',
      name: item.name ?? item.assetName ?? '',
      cost: Number(item.cost ?? item.originalCost ?? 0),
      salvageRate: Number(item.salvageRate ?? 0),
      usefulLifeMonths: Number(item.usefulLifeMonths ?? item.usefulLife ?? 0),
      accAmortBegin: Number(item.accAmortBegin ?? item.accumulatedAmort ?? 0),
      impairmentEnd: 0,
    }))
    syncFromDetail(assetParams)
  } catch {
    ElMessageBox.alert('I1-2明细表数据解析失败。', '错误')
  }
}

function handleAiGenerate() {
  console.log('AI generate: I1-10 amortization summary')
}

function handleReview() {
  openReviewDialog('I1-10')
}

function handleSaveNote() {
  emit('save', 'I1-10-note', auditNote.value)
}

// ─── Summary method for el-table ─────────────────────────────────────────────

function getSummaryRow({ columns, data }: { columns: any[]; data: I1AmortizationRow[] }) {
  const sums: string[] = []
  columns.forEach((col: any, index: number) => {
    if (index === 0) {
      sums[index] = '合计'
      return
    }
    if (index === 1) {
      sums[index] = ''
      return
    }
    // cost column (index 2)
    if (index === 2) {
      sums[index] = fmtAmt(data.reduce((s, r) => s + (r.cost ?? 0), 0))
      return
    }
    // salvage column (index 3)
    if (index === 3) {
      sums[index] = fmtAmt(data.reduce((s, r) => s + (r.salvage ?? 0), 0))
      return
    }
    // accAmortBegin (index 4)
    if (index === 4) {
      sums[index] = fmtAmt(data.reduce((s, r) => s + (r.accAmortBegin ?? 0), 0))
      return
    }
    // remainingMonths (index 5) — no sum
    if (index === 5) {
      sums[index] = '-'
      return
    }
    // monthlyAmortAmount (index 6)
    if (index === 6) {
      sums[index] = fmtAmt(data.reduce((s, r) => s + (r.monthlyAmortAmount ?? 0), 0))
      return
    }
    // month columns (index 7 to 7+27=34)
    const monthIdx = index - 7
    if (monthIdx >= 0 && monthIdx < 28) {
      sums[index] = fmtAmt(summaryRow.value.monthlyTotals[monthIdx] ?? 0)
      return
    }
    // periodAmortization (last column, index 35)
    if (index === 35) {
      sums[index] = fmtAmt(summaryRow.value.periodTotal)
      return
    }
    sums[index] = ''
  })
  return sums
}

// ─── Util ────────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-amort-no-impair {
  padding: 16px;
  font-size: 13px;
}

.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.title-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.amort-matrix-table {
  font-size: 12px;
}

.amort-matrix-table :deep(.el-table__footer) {
  font-weight: 600;
  background: var(--el-fill-color-light);
}

.cell-input {
  width: 100%;
}

.cell-input :deep(.el-input__inner) {
  text-align: right;
  font-size: 12px;
}

.amount-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

.totals-bar {
  display: flex;
  gap: 24px;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 13px;
}

.note-card {
  margin-top: 12px;
}

.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}

.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
