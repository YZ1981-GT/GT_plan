<template>
  <div class="h5-tab-finance-lease">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：检查油气资产融资租出的净投资、内含利率与本期利息确认，核实所有权风险报酬转移与终止确认。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-19" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.financeRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-19 融资租出（本金合计 {{ fmtAmt(state.totalFinancePrincipal.value) }}，本期利息 {{ fmtAmt(state.totalCurrentInterest.value) }}）</span>
          <div class="title-actions">
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
      <el-input type="textarea" :model-value="auditNoteText" :autosize="{ minRows: 5, maxRows: 8 }" placeholder="填写融资租出审计说明..." :disabled="isReadonly" @change="savePolishNote" /></el-card>
    <el-card shadow="never" class="note-card"><template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusionText" :autosize="{ minRows: 3, maxRows: 6 }" placeholder="填写融资租出审计结论..." :disabled="isReadonly" @change="savePolishConclusion" /></el-card>
    <details class="compile-hint"><summary>编制提示</summary><ul>
      <li>净投资=本金(应收融资租赁款)-未确认融资收益</li><li>本期利息=期初净投资×内含利率</li><li>融资租出转移所有权风险报酬，终止确认油气资产</li></ul></details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5Lease } from '../../composables/useH5Lease'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const state = useH5Lease({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: (itemId: string, value: any) => formData.setResponse(itemId, value) })

// 审计说明/结论（component-local H5-19，独立于 H5-18 键，conclusion:null）
const NOTE_KEY = 'H5-19-audit-note'
const CONCLUSION_KEY = 'H5-19-audit-conclusion'
const auditNoteText = ref('')
const auditConclusionText = ref('')
function savePolishNote(val: string): void {
  if (props.isReadonly) return
  auditNoteText.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void formData.saveResponse(NOTE_KEY, val)
}
function savePolishConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusionText.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void formData.saveResponse(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
})

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '新增融资租出', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addFinanceRow(value)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-finance-lease { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; } .section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; } .lease-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.action-bar { margin: 12px 0; } .note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; } .compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
