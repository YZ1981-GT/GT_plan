<template>
  <div class="h1-tab-operating-lease">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>审计目标：核实以经营租赁方式租出的固定资产租赁条款合理、租金收益率正常，市场租金偏离超阈值项目已获合理解释。</template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar" style="display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
      <GtIndexChip value="wp:H1-19" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ operatingRows.length }} 项</el-tag>
    </div>

    <div class="methodology-context">
      <p>检查以经营租赁方式租出的固定资产：租赁条款合理性、租金收益率、市场租金对比。净收益=年租金-折旧分摊-维护费；收益率=净收益÷原值。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-19 经营租出检查 <el-tag size="small" type="info">共 {{ operatingRows.length }} 项</el-tag></span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-19')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="operatingRows" border stripe size="small" max-height="450" class="lease-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="110" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="onCell(row, 'assetName')" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="lessee" label="承租方" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lessee" size="small" @change="onCell(row, 'lessee')" />
            <span v-else>{{ row.lessee }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseStart" label="起始日" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.leaseStart" type="date" value-format="YYYY-MM-DD" size="small" style="width:110px" @change="onCell(row, 'leaseStart')" />
            <span v-else>{{ row.leaseStart }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseEnd" label="终止日" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.leaseEnd" type="date" value-format="YYYY-MM-DD" size="small" style="width:110px" @change="onCell(row, 'leaseEnd')" />
            <span v-else>{{ row.leaseEnd }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="annualRent" label="年租金" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.annualRent" :controls="false" size="small" @change="onCell(row, 'annualRent')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.annualRent) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="月租金" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="月租金=年租金÷12">{{ fmtAmt(row.monthlyRent) }}</span></template>
        </el-table-column>
        <el-table-column prop="originalCost" label="资产原值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false" size="small" @change="onCell(row, 'originalCost')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="depAlloc" label="折旧分摊" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.depAlloc" :controls="false" size="small" @change="onCell(row, 'depAlloc')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.depAlloc) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="maintenanceCost" label="维护费" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.maintenanceCost" :controls="false" size="small" @change="onCell(row, 'maintenanceCost')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.maintenanceCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净收益" width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" title="净收益=年租金-折旧分摊-维护费">{{ fmtAmt(row.netIncome) }}</span></template>
        </el-table-column>
        <el-table-column label="收益率%" width="80" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="收益率=净收益÷原值×100%">{{ row.returnRate != null ? row.returnRate.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="marketRent" label="市场年租" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.marketRent" :controls="false" size="small" @change="onCell(row, 'marketRent')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.marketRent) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="偏离%" width="80" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(deviation(row) ?? 0) > 20 }]" title="偏离=(年租金-市场年租)÷市场年租×100%">
              {{ deviation(row) != null ? deviation(row)!.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('19', row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>年租金合计: <b class="amount-cell">{{ fmtAmt(operatingSummary.totalRent) }}</b></span>
        <span>净收益合计: <b class="amount-cell">{{ fmtAmt(operatingSummary.totalNetIncome) }}</b></span>
        <span>平均收益率: <b>{{ operatingSummary.avgReturnRate.toFixed(1) }}%</b></span>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input v-model="auditNoteText" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：租赁条款合理性、租金收益率与市场租金对比、偏离项解释。" @change="saveAuditNote" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写经营租出检查审计结论..." @change="saveAuditConclusion" />
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
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1LeaseCheck, type OperatingLeaseRow } from '../../composables/useH1LeaseCheck'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const auditNoteText = ref('')
const NOTE_KEY = 'H1-19-audit-note'
const CONCLUSION_KEY = 'H1-19-audit-conclusion'
function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) conclusion.value = c.remark
})
const { operatingRows, operatingSummary, addOperatingRow, removeRow, updateOperatingCell } = useH1LeaseCheck(
  toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any,
)

function deviation(row: OperatingLeaseRow): number | null {
  return row.marketRent > 0 ? ((row.annualRent - row.marketRent) / row.marketRent * 100) : null
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('资产名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name != null) {
    addOperatingRow()
    const last = operatingRows.value[operatingRows.value.length - 1]
    if (last) updateOperatingCell(last.rowId, 'assetName', name)
  }
}
function onCell(row: OperatingLeaseRow, field: keyof OperatingLeaseRow) { updateOperatingCell(row.rowId, field, (row as any)[field]) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-operating-lease { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.lease-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
