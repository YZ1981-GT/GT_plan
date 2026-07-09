<template>
  <div class="h5-tab-finance-lease">
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-19 融资租出（本金合计 {{ fmtAmt(state.totalFinancePrincipal.value) }}，本期利息 {{ fmtAmt(state.totalCurrentInterest.value) }}）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H5-19')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="state.financeRows.value" border stripe size="small" class="lease-table" max-height="500">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="assetName" label="资产名称" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="state.updateFinanceCell(row.rowId, 'assetName', $event)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="lessee" label="承租方" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lessee" size="small" @change="state.updateFinanceCell(row.rowId, 'lessee', $event)" />
            <span v-else>{{ row.lessee }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="principal" label="本金" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.principal" :controls="false" size="small" @change="state.updateFinanceCell(row.rowId, 'principal', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.principal) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unrecognizedFinanceIncome" label="未确认收益" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.unrecognizedFinanceIncome" :controls="false" size="small" @change="state.updateFinanceCell(row.rowId, 'unrecognizedFinanceIncome', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.unrecognizedFinanceIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净投资" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="=本金-未确认收益">{{ fmtAmt(row.netInvestment) }}</span></template>
        </el-table-column>
        <el-table-column prop="interestRate" label="内含利率(%)" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.interestRate" :controls="false" :precision="2" size="small" @change="state.updateFinanceCell(row.rowId, 'interestRate', $event ?? 0)" />
            <span v-else>{{ row.interestRate }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentInterest" label="本期利息" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.currentInterest" :controls="false" size="small" @change="state.updateFinanceCell(row.rowId, 'currentInterest', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.currentInterest) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remainingPrincipal" label="剩余本金" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.remainingPrincipal" :controls="false" size="small" @change="state.updateFinanceCell(row.rowId, 'remainingPrincipal', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.remainingPrincipal) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="state.updateFinanceCell(row.rowId, 'conclusion', $event)" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="state.removeFinanceRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>
    <div class="action-bar" v-if="!isReadonly"><el-button size="small" @click="handleAddRow">+ 新增融资租出</el-button></div>
    <el-card shadow="never" class="note-card"><template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="state.auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion)" /></el-card>
    <details class="compile-hint"><summary>编制提示</summary><ul>
      <li>净投资=本金(应收融资租赁款)-未确认融资收益</li><li>本期利息=期初净投资×内含利率</li><li>融资租出转移所有权风险报酬，终止确认油气资产</li></ul></details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH5Lease } from '../../composables/useH5Lease'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const state = useH5Lease({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: () => {} })

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '新增融资租出', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addFinanceRow(value)
}
function handleAiGenerate() {}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-finance-lease { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; } .section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; } .lease-table { font-size: 13px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.action-bar { margin: 12px 0; } .note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; } .compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
