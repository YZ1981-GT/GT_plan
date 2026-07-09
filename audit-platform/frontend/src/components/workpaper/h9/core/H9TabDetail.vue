<template>
  <div class="h9-tab-detail">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第26条：租赁负债按实际利率法后续计量，期末=期初-偿还(借方)+利息(贷方)。22列按3区段Tab展示，与H8使用权资产合同一一对应。</p>
    </div>

    <!-- 区段切换 + 工具栏 -->
    <div class="segment-bar">
      <el-segmented v-model="activeTab" :options="tabOptions" size="default" />
      <div class="bar-actions">
        <el-dropdown v-if="!isReadonly" trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRow">+ 新增合同</el-button>
        <el-button size="small" type="primary" plain @click="$emit('open-ai', 'detail')">AI 辅助</el-button>
        <el-button size="small" @click="$emit('open-review', 'detail')">复核</el-button>
      </div>
    </div>

    <!-- 区段1: 基础+变动 (A~E列 + O~R) -->
    <el-table
      v-if="activeTab === '负债变动'"
      :data="rows"
      border
      size="small"
      class="detail-table"
      show-summary
      :summary-method="getSummaryMovement"
    >
      <el-table-column prop="lessor" label="出租方" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.lessor" size="small" @change="onCell(row.rowId, 'lessor', row.lessor)" />
          <span v-else>{{ row.lessor }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="contractNo" label="合同号" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.contractNo" size="small" @change="onCell(row.rowId, 'contractNo', row.contractNo)" />
          <span v-else>{{ row.contractNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="H8" width="60" align="center">
        <template #default="{ row }">
          <GtIndexChip v-if="row.contractNo" value="H8-2" :context-project-id="props.projectId"
            context="H8使用权资产对应合同" @click="emit('navigate-sheet', 'H8-2')" :prevent-navigate="true" />
        </template>
      </el-table-column>
      <el-table-column prop="assetDesc" label="承租资产" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.assetDesc" size="small" @change="onCell(row.rowId, 'assetDesc', row.assetDesc)" />
          <span v-else>{{ row.assetDesc }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="ibrRate" label="IBR利率(%)" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.ibrRate" :controls="false" :precision="2" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'ibrRate', v)" />
          <span v-else>{{ row.ibrRate ? row.ibrRate.toFixed(2) + '%' : '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="leaseTerm" label="租赁期(月)" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.leaseTerm" :controls="false" :min="0" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'leaseTerm', v)" />
          <span v-else>{{ row.leaseTerm || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="beginBalance" label="B:期初余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'beginBalance', v)" />
          <span v-else>{{ fmtAmt(row.beginBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="repayment" label="C:本期偿还(借)" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.repayment" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'repayment', v)" />
          <span v-else>{{ fmtAmt(row.repayment) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="interestAccrued" label="D:本期利息(贷)" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.interestAccrued" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'interestAccrued', v)" />
          <span v-else>{{ fmtAmt(row.interestAccrued) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="E:期末余额" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：E=B-C+D（负债贷方：期初-偿还+利息）">{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="handleDelete(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 区段2: 审定调整 (F~N列) -->
    <el-table
      v-if="activeTab === '审定调整'"
      :data="rows"
      border
      size="small"
      class="detail-table"
      show-summary
      :summary-method="getSummaryAdjustment"
    >
      <el-table-column prop="lessor" label="出租方" width="120" />
      <el-table-column prop="contractNo" label="合同号" width="110" />
      <el-table-column prop="beginAje" label="F:期初AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.beginAje" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'beginAje', v)" />
          <span v-else>{{ fmtAmt(row.beginAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="repayAje" label="G:偿还AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.repayAje" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'repayAje', v)" />
          <span v-else>{{ fmtAmt(row.repayAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="interestAje" label="H:利息AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.interestAje" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'interestAje', v)" />
          <span v-else>{{ fmtAmt(row.interestAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="I:审定期初" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：I=B+F">{{ fmtAmt(row.auditedBegin) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="J:审定偿还" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：J=C+G">{{ fmtAmt(row.auditedRepay) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="K:审定利息" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：K=D+H">{{ fmtAmt(row.auditedInterest) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="L:审定期末" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：L=I-J+K">{{ fmtAmt(row.auditedEnd) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="reclassification" label="M:重分类" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.reclassification" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'reclassification', v)" />
          <span v-else>{{ fmtAmt(row.reclassification) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="N:最终审定" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：N=L-M">{{ fmtAmt(row.finalAudited) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 区段3: 到期分析+关联方+发函+期后 -->
    <el-table
      v-if="activeTab === '到期与关联'"
      :data="rows"
      border
      size="small"
      class="detail-table"
    >
      <el-table-column prop="lessor" label="出租方" width="120" />
      <el-table-column prop="contractNo" label="合同号" width="110" />
      <el-table-column label="N:最终审定" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmt(row.finalAudited) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="isRelatedParty" label="S:关联方" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="!isReadonly" :type="row.isRelatedParty === '是' ? 'danger' : 'info'" size="small"
            style="cursor: pointer" @click="toggleRelated(row)">
            {{ row.isRelatedParty }}
          </el-tag>
          <el-tag v-else :type="row.isRelatedParty === '是' ? 'danger' : 'info'" size="small">
            {{ row.isRelatedParty }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="isConfirmed" label="T:发函" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="!isReadonly" :type="row.isConfirmed === '是' ? 'success' : 'info'" size="small"
            style="cursor: pointer" @click="toggleConfirmed(row)">
            {{ row.isConfirmed }}
          </el-tag>
          <el-tag v-else :type="row.isConfirmed === '是' ? 'success' : 'info'" size="small">
            {{ row.isConfirmed }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计统计栏 -->
    <div class="stat-bar">
      <span>合同总数：{{ rows.length }}</span>
      <span>期初合计：{{ fmtAmt(totalRow.beginBalance) }}元</span>
      <span>审定期末合计：{{ fmtAmt(totalRow.auditedEnd) }}元</span>
      <span>最终审定合计：{{ fmtAmt(totalRow.finalAudited) }}元</span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="note-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" plain @click="$emit('open-ai', 'detail-note')">AI 辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="对租赁负债明细的审计说明..."
        :readonly="isReadonly"
        @change="onSaveNote('H9-2-audit-note', auditNote)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="note-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" plain @click="$emit('open-ai', 'detail-conclusion')">AI 辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="对租赁负债明细表的审计结论..."
        :readonly="isReadonly"
        @change="onSaveNote('H9-2-audit-conclusion', auditConclusion)"
      />
    </el-card>

    <!-- 隐藏文件上传(导入) -->
    <input ref="importFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileImport" />
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabDetail.vue — H9-2 租赁负债明细表（22列 3区段Tab）
 *
 * 按合同列示租赁负债变动（负债贷方科目：期末=期初-偿还+利息）
 * 3区段Tab切换行同步：①负债变动(基础+B~E) ②审定调整(F~N) ③到期与关联(S/T)
 *
 * Spec: .kiro/specs/h9-lease-liabilities/ Task 4.3
 * Requirements: 3.1-3.6
 */
import { ref, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH9Detail, type H9DetailRow } from '../../composables/useH9Detail'
import { useH9ImportExport } from '../../composables/useH9ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── 区段Tab ─────────────────────────────────────────────────────────────────
const tabOptions = ['负债变动', '审定调整', '到期与关联']
const activeTab = ref('负债变动')

// ─── Composable ──────────────────────────────────────────────────────────────
const {
  rows, totalRow,
  addRow, deleteRow, updateCell,
} = useH9Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const {
  exportTemplate, exportData, importData,
} = useH9ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'H9-2',
  onImported: () => { /* parent will reload */ },
})

// ─── 审计说明/结论 ───────────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')

// 从 allResponses 加载文本
function loadNotes() {
  const noteItem = props.allResponses.get('H9-2-audit-note')
  auditNote.value = noteItem?.remark ?? noteItem?.conclusion ?? ''
  const conclusionItem = props.allResponses.get('H9-2-audit-conclusion')
  auditConclusion.value = conclusionItem?.remark ?? conclusionItem?.conclusion ?? ''
}
loadNotes()

function onSaveNote(itemId: string, value: string) {
  emit('save', itemId, value)
}

// ─── Actions ─────────────────────────────────────────────────────────────────
function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onCell(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入出租方名称', '新增明细行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：XX房地产开发有限公司',
  })
  if (value) addRow(value)
}

function handleDelete(rowId: string) {
  deleteRow(rowId)
}

function toggleRelated(row: H9DetailRow) {
  const newVal = row.isRelatedParty === '是' ? '否' : '是'
  updateCell(row.rowId, 'isRelatedParty', newVal)
}

function toggleConfirmed(row: H9DetailRow) {
  const newVal = row.isConfirmed === '是' ? '否' : '是'
  updateCell(row.rowId, 'isConfirmed', newVal)
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────
const importFileRef = ref<HTMLInputElement | null>(null)

function handleImportExport(command: string) {
  switch (command) {
    case 'export-template': exportTemplate(['H9-2']); break
    case 'export-data': exportData(['H9-2']); break
    case 'import-data': importFileRef.value?.click(); break
  }
}

async function handleFileImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  await importData(file)
  // Reset input
  if (importFileRef.value) importFileRef.value.value = ''
}

// ─── Summary methods ─────────────────────────────────────────────────────────
function getSummaryMovement({ columns }: any) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return `合计（${rows.value.length}笔）`
    if (idx === 6) return fmtAmt(totalRow.value.beginBalance)
    if (idx === 7) return fmtAmt(totalRow.value.repayment)
    if (idx === 8) return fmtAmt(totalRow.value.interestAccrued)
    if (idx === 9) return fmtAmt(totalRow.value.endBalance)
    return ''
  })
}

function getSummaryAdjustment({ columns }: any) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 5) return fmtAmt(totalRow.value.auditedBegin)
    if (idx === 6) return fmtAmt(totalRow.value.auditedRepay)
    if (idx === 7) return fmtAmt(totalRow.value.auditedInterest)
    if (idx === 8) return fmtAmt(totalRow.value.auditedEnd)
    if (idx === 10) return fmtAmt(totalRow.value.finalAudited)
    return ''
  })
}
</script>

<style scoped>
.h9-tab-detail { padding: 16px; font-size: 13px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.segment-bar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.bar-actions { display: flex; gap: 6px; align-items: center; }

.detail-table { font-size: 13px; margin-bottom: 12px; }
.detail-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; }

.stat-bar {
  display: flex; gap: 24px; padding: 10px 0; font-size: 12px;
  color: var(--el-text-color-secondary); border-top: 1px solid var(--el-border-color-lighter);
  margin-bottom: 16px;
}

.audit-note-card { margin-bottom: 12px; }
.note-header { display: flex; align-items: center; justify-content: space-between; }
</style>
