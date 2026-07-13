<template>
  <div class="h9-tab-finance-cost">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实未确认融资费用（负债备抵科目）期末余额及本期实际利率法分摊的准确、完整，验证与 H9-2 明细表及 H9 摊销表利息费用的勾稽一致。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第20条：未确认融资费用为负债备抵科目（借方余额），按实际利率法分期转入利息费用。期末=期初+借方增加-贷方确认。21列按3区段Tab展示，行联动H9-2出租方。</p>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H9-3" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
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
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRow">+ 新增行</el-button>
        <el-button size="small" @click="$emit('open-review', 'finance-cost')">复核</el-button>
      </div>
    </div>

    <!-- 区段1: 基础变动 (A~E列) -->
    <el-table
      v-if="activeTab === '融资费用变动'"
      :data="rows"
      border
      size="small"
      class="detail-table"
      show-summary
      :summary-method="getSummaryMovement"
    >
      <el-table-column prop="lessor" label="A:出租方" min-width="120">
        <template #default="{ row }">
          <span class="readonly-field">{{ row.lessor || '(联动H9-2)' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="contractNo" label="P:合同号" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.contractNo" size="small" @change="onCell(row.rowId, 'contractNo', row.contractNo)" />
          <span v-else>{{ row.contractNo }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="beginBalance" label="B:期初余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'beginBalance', v)" />
          <span v-else>{{ fmtAmt(row.beginBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="debitIncrease" label="C:本期增加(借)" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.debitIncrease" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'debitIncrease', v)" />
          <span v-else>{{ fmtAmt(row.debitIncrease) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="creditDecrease" label="D:本期确认(贷)" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.creditDecrease" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'creditDecrease', v)" />
          <span v-else>{{ fmtAmt(row.creditDecrease) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="E:期末余额" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：E=B+C-D（借方备抵：期初+借-贷）">{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="interestPeriod" label="Q:对应利息期" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.interestPeriod" size="small" placeholder="如：2024年1~12月"
            @change="onCell(row.rowId, 'interestPeriod', row.interestPeriod)" />
          <span v-else>{{ row.interestPeriod || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="handleDelete(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 区段2: 审定调整 (F~O列) -->
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
      <el-table-column prop="confirmAje" label="G:确认AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.confirmAje" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'confirmAje', v)" />
          <span v-else>{{ fmtAmt(row.confirmAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="increaseAje" label="H:增加AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.increaseAje" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'increaseAje', v)" />
          <span v-else>{{ fmtAmt(row.increaseAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="otherAje" label="I:其他AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.otherAje" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'otherAje', v)" />
          <span v-else>{{ fmtAmt(row.otherAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="J:审定期初" width="110" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：J=B">{{ fmtAmt(row.auditedBegin) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="K:审定增加" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：K=C+F+H">{{ fmtAmt(row.auditedIncrease) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="L:审定确认" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：L=D+G+I">{{ fmtAmt(row.auditedDecrease) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="M:审定期末" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：M=J+K-L">{{ fmtAmt(row.auditedEnd) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="reclassification" label="N:重分类" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.reclassification" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'reclassification', v)" />
          <span v-else>{{ fmtAmt(row.reclassification) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="O:最终审定" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：O=M-N">{{ fmtAmt(row.finalAudited) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 区段3: 关联方+备注 -->
    <el-table
      v-if="activeTab === '关联与备注'"
      :data="rows"
      border
      size="small"
      class="detail-table"
    >
      <el-table-column prop="lessor" label="出租方" width="120" />
      <el-table-column prop="contractNo" label="合同号" width="110" />
      <el-table-column label="O:最终审定" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmt(row.finalAudited) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="isRelatedParty" label="T:关联方" width="90" align="center">
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
      <el-table-column prop="remark" label="R:备注" min-width="180">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small" placeholder="备注信息..."
            @change="onCell(row.rowId, 'remark', row.remark)" />
          <span v-else>{{ row.remark || '-' }}</span>
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
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="对未确认融资费用明细的审计说明..."
        :readonly="isReadonly"
        @change="onSaveNote('H9-3-audit-note', auditNote)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="note-header">
          <span>审计结论</span>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="对未确认融资费用明细表的审计结论..."
        :readonly="isReadonly"
        @change="onSaveNote('H9-3-audit-conclusion', auditConclusion)"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <ul>
        <li>未确认融资费用为负债备抵科目（借方余额）：期末 E = 期初 B + 本期增加 C（借）− 本期确认 D（贷）</li>
        <li>本期确认（转入利息费用）按实际利率法计算，应与 H9 摊销表各期利息一致</li>
        <li>出租方名称自 H9-2 明细表联动，保持合同口径一致</li>
        <li>审定期末 M = 审定期初 J + 审定增加 K − 审定确认 L；最终审定 O = M − 重分类 N</li>
        <li>CAS21 下租赁利息费用一般不资本化（租赁期开始日已达预定可使用状态）</li>
      </ul>
    </details>

    <!-- 隐藏文件上传(导入) -->
    <input ref="importFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileImport" />
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabFinanceCost.vue — H9-3 未确认融资费用明细表（21列 3区段Tab）
 *
 * 负债备抵科目（借方余额）：E=B+C-D（期初+借方增加-贷方确认）
 * 行联动H9-2出租方名称（只读）
 * 3区段Tab切换行同步：①融资费用变动(B~E) ②审定调整(F~O) ③关联与备注(T/R)
 *
 * Spec: .kiro/specs/h9-lease-liabilities/ Task 4.3
 * Requirements: 3.4-3.6
 */
import { ref, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH9FinanceCost, type H9FinanceCostRow } from '../../composables/useH9FinanceCost'
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
}>()

// ─── 区段Tab ─────────────────────────────────────────────────────────────────
const tabOptions = ['融资费用变动', '审定调整', '关联与备注']
const activeTab = ref('融资费用变动')

// ─── Composable ──────────────────────────────────────────────────────────────
const {
  rows, totalRow,
  addRow, deleteRow, updateCell,
} = useH9FinanceCost({
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
  sheetCode: 'H9-3',
  onImported: () => { /* parent will reload */ },
})

// ─── 审计说明/结论 ───────────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')

function loadNotes() {
  const noteItem = props.allResponses.get('H9-3-audit-note')
  auditNote.value = noteItem?.remark ?? noteItem?.conclusion ?? ''
  const conclusionItem = props.allResponses.get('H9-3-audit-conclusion')
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
  const { value } = await ElMessageBox.prompt('请输入出租方名称', '新增融资费用行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：XX房地产开发有限公司',
  })
  if (value) addRow(value)
}

function handleDelete(rowId: string) {
  deleteRow(rowId)
}

function toggleRelated(row: H9FinanceCostRow) {
  const newVal = row.isRelatedParty === '是' ? '否' : '是'
  updateCell(row.rowId, 'isRelatedParty', newVal)
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────
const importFileRef = ref<HTMLInputElement | null>(null)

function handleImportExport(command: string) {
  switch (command) {
    case 'export-template': exportTemplate(['H9-3']); break
    case 'export-data': exportData(['H9-3']); break
    case 'import-data': importFileRef.value?.click(); break
  }
}

async function handleFileImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  await importData(file)
  if (importFileRef.value) importFileRef.value.value = ''
}

// ─── Summary methods ─────────────────────────────────────────────────────────
function getSummaryMovement({ columns }: any) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return `合计（${rows.value.length}笔）`
    if (idx === 2) return fmtAmt(totalRow.value.beginBalance)
    if (idx === 3) return fmtAmt(totalRow.value.debitIncrease)
    if (idx === 4) return fmtAmt(totalRow.value.creditDecrease)
    if (idx === 5) return fmtAmt(totalRow.value.endBalance)
    return ''
  })
}

function getSummaryAdjustment({ columns }: any) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 6) return fmtAmt(totalRow.value.auditedBegin)
    if (idx === 7) return fmtAmt(totalRow.value.auditedIncrease)
    if (idx === 8) return fmtAmt(totalRow.value.auditedDecrease)
    if (idx === 9) return fmtAmt(totalRow.value.auditedEnd)
    if (idx === 11) return fmtAmt(totalRow.value.finalAudited)
    return ''
  })
}
</script>

<style scoped>
.h9-tab-finance-cost { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.guidance-details {
  margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-details ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }

.segment-bar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.bar-actions { display: flex; gap: 6px; align-items: center; }

.detail-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.detail-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; }
.readonly-field { color: var(--el-text-color-secondary); font-style: italic; }

.stat-bar {
  display: flex; gap: 24px; padding: 10px 0; font-size: 12px;
  color: var(--el-text-color-secondary); border-top: 1px solid var(--el-border-color-lighter);
  margin-bottom: 16px;
}

.audit-note-card { margin-bottom: 12px; }
.note-header { display: flex; align-items: center; justify-content: space-between; }
</style>
