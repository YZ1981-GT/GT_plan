<template>
  <div class="h1-tab-operating-lease">
    <div class="methodology-context">
      <p>检查以经营租赁方式租出的固定资产：租赁条款合理性、租金收益率、市场租金对比。23公式自动计算租赁净收益与投资收益率。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-19 经营租出检查（{{ state.rows.value.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-19')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" max-height="450" class="lease-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="110" fixed />
        <el-table-column prop="lessee" label="承租方" width="100" />
        <el-table-column prop="leaseStart" label="起始日" width="100" />
        <el-table-column prop="leaseEnd" label="终止日" width="100" />
        <el-table-column prop="monthlyRent" label="月租金" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.monthlyRent) }}</span></template>
        </el-table-column>
        <el-table-column prop="annualRent" label="年租金收入" width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" title="月租×12">{{ fmtAmt(row.annualRent) }}</span></template>
        </el-table-column>
        <el-table-column prop="originalCost" label="资产原值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.originalCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="annualDep" label="年折旧" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.annualDep) }}</span></template>
        </el-table-column>
        <el-table-column prop="maintenanceCost" label="维护费" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.maintenanceCost) }}</span></template>
        </el-table-column>
        <el-table-column label="净收益" width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" title="净收益=租金-折旧-维护">{{ fmtAmt(row.netIncome) }}</span></template>
        </el-table-column>
        <el-table-column label="收益率%" width="80" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="收益率=净收益÷原值×100%">{{ row.returnRate != null ? row.returnRate.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="marketRent" label="市场月租" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.marketRent) }}</span></template>
        </el-table-column>
        <el-table-column label="偏离%" width="80" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.rentDeviation || 0) > 20 }]">
              {{ row.rentDeviation != null ? row.rentDeviation.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100" />
      </el-table>

      <div class="summary-bar">
        <span>年租金合计: <b class="amount-cell">{{ fmtAmt(state.rentTotal.value) }}</b></span>
        <span>净收益合计: <b class="amount-cell">{{ fmtAmt(state.netIncomeTotal.value) }}</b></span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>收益率=净收益÷原值×100%；市场偏离>20%标红</li>
        <li>租出清单联动附注披露(H1-disc)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1LeaseCheck } from '../../composables/useH1LeaseCheck'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const state = useH1LeaseCheck(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any, { variant: 'operatingLease' })

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('资产名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) state.addRow(name)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-operating-lease { padding: 16px; font-size: 13px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.lease-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
