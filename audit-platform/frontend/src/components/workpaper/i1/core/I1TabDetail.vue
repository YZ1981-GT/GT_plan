<template>
  <div class="i1-tab-detail">
    <!-- 方法论上下文（琥珀色左边线） -->
    <div class="methodology-context">
      <p><strong>I1-2 明细表编制逻辑（对齐 Excel 56 列）：</strong></p>
      <p>横向三区块：原值 | 累计摊销 | 减值准备；每块「未审数 → 期初/账项调整 → 审定数」。</p>
      <p>右侧：期初/期末净值（未审+审定）+ 权属证明 + 抵押受限。区段 Tab 拆分仅为可读性，行数据一体。</p>
      <p>公式：期末=期初+增加−减少；净值=原值−摊销−减值；审定=未审+调整。</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实明细账与总账、报表及上年底稿是否相符，确认期初、期末余额的准确性。"
    />

    <details class="guidance-details">
      <summary>编制说明</summary>
      <div class="guidance-content">
        <p>1、本科目核算企业持有的无形资产成本，包括专利权、非专利技术、商标权、著作权、土地使用权等。</p>
        <p>2、对于使用寿命不确定的无形资产，每年进行减值测试。</p>
        <p>3、对于尚未达到可使用状态的无形资产，由于其价值通常具有较大的不确定性，也应当每年进行减值测试。</p>
        <p>4、增加方式（购置/内部研发/企业合并/其他）联动 I1-5；减少方式（处置/失效终止/其他）联动 I1-6。</p>
        <p>5、无形资产减值损失一经确认不得转回；减值「减少」一般为处置结转。</p>
      </div>
    </details>

    <div v-if="crossValidation.hasAnyWarning" class="cross-validation-warning">
      <el-icon class="warning-icon"><WarningFilled /></el-icon>
      <span>明细审定合计与 I1 审定表小计不一致：</span>
      <span v-if="crossValidation.hasCostWarning" class="warning-item">
        原值差异 {{ fmtAmount(crossValidation.costDiff) }}
      </span>
      <span v-if="crossValidation.hasAmortWarning" class="warning-item">
        摊销差异 {{ fmtAmount(crossValidation.amortDiff) }}
      </span>
      <span v-if="crossValidation.hasImpairWarning" class="warning-item">
        减值差异 {{ fmtAmount(crossValidation.impairDiff) }}
      </span>
    </div>

    <div class="tab-toolbar">
      <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddRow">+ 新增</el-button>
      <el-dropdown
        v-if="!isReadonly"
        size="small"
        :disabled="ieBusy"
        @command="handleIeCommand"
      >
        <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
      <span class="chip-wrap"><GtIndexChip value="wp:I1-2" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      <el-tag v-if="needAnnualImpairmentCount" size="small" type="warning">
        须年测减值 {{ needAnnualImpairmentCount }}
      </el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I1-1')">→ 审定表</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I1-5')">I1-5</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I1-6')">I1-6</el-tag>
      <span class="row-count">未审净值 {{ fmtAmount(summaryRow.netValue) }} / 审定净值 {{ fmtAmount(summaryRow.auditedNetEnd) }}</span>
    </div>

    <!-- 5区段Tab切换（Excel 56列可读性拆分，行数据一体） -->
    <el-tabs v-model="activeTab" type="border-card" class="segment-tabs" @tab-change="onTabChange">
      <el-tab-pane
        v-for="tab in tabs"
        :key="tab.key"
        :label="tab.label"
        :name="tab.key"
      >
        <el-table
          :data="rows"
          border
          size="small"
          highlight-current-row
          :current-row-key="activeRowKey"
          row-key="rowId"
          class="detail-table"
          :row-class-name="getRowClassName"
          @current-change="onCurrentRowChange"
        >
          <el-table-column type="index" label="#" width="50" align="center" />

          <el-table-column
            v-for="col in tab.columns"
            :key="col.key"
            :prop="col.key"
            :label="col.label"
            :min-width="col.width"
            :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
          >
            <template v-if="col.type === 'formula'" #header>
              <el-tooltip :content="col.tooltip" placement="top">
                <span class="formula-col-header">{{ col.label }}</span>
              </el-tooltip>
            </template>

            <template #default="{ row, $index }">
              <span v-if="col.type === 'formula'" class="formula-value">
                <el-tooltip :content="col.tooltip" placement="top">
                  <span>{{ fmtAmount((row as any)[col.key]) }}</span>
                </el-tooltip>
              </span>

              <el-input-number
                v-else-if="col.type === 'number' && col.editable && !isReadonly"
                :model-value="(row as any)[col.key]"
                size="small"
                :controls="false"
                :precision="2"
                class="cell-input-number"
                @change="(val: number | undefined) => handleCellChange($index, col.key, val ?? 0)"
              />

              <el-input
                v-else-if="col.type === 'text' && col.editable && !isReadonly"
                :model-value="(row as any)[col.key]"
                size="small"
                class="cell-input-text"
                @change="(val: string) => handleCellChange($index, col.key, val)"
              />

              <el-date-picker
                v-else-if="col.type === 'date' && col.editable && !isReadonly"
                :model-value="(row as any)[col.key]"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                class="cell-date-picker"
                @change="(val: string) => handleCellChange($index, col.key, val ?? '')"
              />

              <el-select
                v-else-if="col.type === 'select' && col.editable && !isReadonly"
                :model-value="(row as any)[col.key]"
                size="small"
                class="cell-select"
                clearable
                @change="(val: string) => handleCellChange($index, col.key, val ?? '')"
              >
                <el-option
                  v-for="opt in col.options"
                  :key="String(opt)"
                  :label="ynLabel(opt)"
                  :value="opt"
                />
              </el-select>

              <span v-else class="cell-readonly">
                {{ displayCell(row, col) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column v-if="!isReadonly" label="操作" width="80" align="center" fixed="right">
            <template #default="{ $index }">
              <el-button size="small" type="danger" text @click="handleRemoveRow($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="summary-section">
          <el-table :data="[summaryDisplayRow(tab.key)]" border size="small" class="summary-table">
            <el-table-column label="#" width="50" align="center">
              <template #default>
                <span class="summary-label">合计</span>
              </template>
            </el-table-column>
            <el-table-column
              v-for="col in tab.columns"
              :key="'sum-' + col.key"
              :prop="col.key"
              :label="col.label"
              :min-width="col.width"
              :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
            >
              <template #default="{ row }">
                <span class="summary-value">{{ getSummaryValue(row, col) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="" width="80" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 按分类汇总（对齐 Excel 分类小计行） -->
    <el-card v-if="categorySummary.length" shadow="never" class="category-card">
      <template #header>
        <div class="card-header"><span>按资产分类汇总</span></div>
      </template>
      <el-table :data="categorySummary" border size="small" class="category-table">
        <el-table-column prop="category" label="分类" min-width="120" />
        <el-table-column prop="count" label="项数" width="70" align="center" />
        <el-table-column prop="costEnd" label="未审原值期末" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.costEnd) }}</template>
        </el-table-column>
        <el-table-column prop="accAmortEnd" label="未审摊销期末" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.accAmortEnd) }}</template>
        </el-table-column>
        <el-table-column prop="impairmentEnd" label="未审减值期末" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.impairmentEnd) }}</template>
        </el-table-column>
        <el-table-column prop="netValue" label="未审净值" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.netValue) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="填写审计说明：明细取数与登记、与总账/报表/上年底稿核对、增减方式抽查、与审定表勾稽等。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button v-if="!isReadonly" size="small" @click="fillDraft">填入结论模板</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除下列事项应予调整外，其余未见异常。C、存在重大未调整事项，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { inject, ref, computed, toRef, onMounted, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import { useI1Detail, type I1DetailTab, type I1DetailRow } from '../../composables/useI1Detail'
import { useI1ImportExport } from '../../composables/useI1ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// 🔴 金额展示走 displayPrefs 单一真源（千分符 / 2 位小数 / 单位「元」/ showZero 偏好）。
//    必须 setup **顶层** inject —— 写进函数体会静默失效（平台铁律）。
//    DisplayPrefs_Key 只能从 composables/displayPrefsKey 引入，
//    从 @/stores/displayPrefs 连带引会让整页崩（该 store 没有这个导出）。
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  adjCostSubtotal?: number
  adjAmortSubtotal?: number
  adjImpairSubtotal?: number
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const { importing, exporting, exportTemplate, exportData, importData } = useI1ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})
const ieBusy = computed(() => importing.value || exporting.value)

async function handleIeCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('I1-2')
  else if (cmd === 'export-data') await exportData('I1-2')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (file) await importData('I1-2', file)
}

const NOTE_KEY = 'I1-2-audit-note'
const CONCLUSION_KEY = 'I1-2-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', CONCLUSION_KEY, val)
}

function loadAuditText(): void {
  const n = props.allResponses.get(NOTE_KEY)
  if (n) auditNote.value = (n.remark ?? n.conclusion ?? '') as string
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c) auditConclusion.value = (c.remark ?? c.conclusion ?? '') as string
}

onMounted(loadAuditText)
watch(() => props.allResponses, loadAuditText, { deep: true })

const {
  rows,
  activeTab,
  activeRowIndex,
  summaryRow,
  crossValidation,
  categorySummary,
  needAnnualImpairmentCount,
  tabs,
  switchTab,
  setActiveRow,
  updateCell,
  addRow,
  removeRow,
  fillConclusionDraft,
} = useI1Detail(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'allResponses') as Ref<Map<string, any>>,
  {
    adjCostSubtotal: toRef(props, 'adjCostSubtotal') as Ref<number>,
    adjAmortSubtotal: toRef(props, 'adjAmortSubtotal') as Ref<number>,
    adjImpairSubtotal: toRef(props, 'adjImpairSubtotal') as Ref<number>,
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

const activeRowKey = computed(() => {
  if (activeRowIndex.value < 0 || activeRowIndex.value >= rows.value.length) return ''
  return rows.value[activeRowIndex.value]?.rowId ?? ''
})

function onTabChange(tabKey: string | number): void {
  switchTab(tabKey as I1DetailTab)
}

function onCurrentRowChange(row: I1DetailRow | null): void {
  if (!row) return
  const idx = rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) setActiveRow(idx)
}

function handleCellChange(rowIndex: number, field: string, value: string | number): void {
  updateCell(rowIndex, field as keyof I1DetailRow, value)
}

async function handleAddRow(): Promise<void> {
  await addRow()
}

function handleRemoveRow(index: number): void {
  removeRow(index)
}

function fillDraft(): void {
  const draft = fillConclusionDraft()
  auditConclusion.value = draft
  emit('save', CONCLUSION_KEY, draft)
  ElMessage.success('已填入结论模板')
}

function getRowClassName({ rowIndex }: { row: I1DetailRow; rowIndex: number }): string {
  return rowIndex === activeRowIndex.value ? 'active-synced-row' : ''
}

function ynLabel(opt: string): string {
  if (opt === 'Y') return '是(Y)'
  if (opt === 'N') return '否(N)'
  if (opt === '') return '—'
  return opt
}

function displayCell(row: I1DetailRow, col: { key: string; type: string }): string {
  const val = (row as any)[col.key]
  if (col.type === 'number') return fmtAmount(val)
  if (col.key === 'hasTitleEvidence' || col.key === 'mortgageRestricted'
    || col.key === 'indefiniteLife' || col.key === 'notReadyForUse') {
    return ynLabel(String(val ?? ''))
  }
  return val ? String(val) : '-'
}

function summaryDisplayRow(tabKey: I1DetailTab): Record<string, any> {
  const s = summaryRow.value
  switch (tabKey) {
    case 'basic':
      return { category: '—', name: `合计(${rows.value.length})` }
    case 'cost':
      return {
        name: '合计',
        costBegin: s.costBegin,
        costIncrease: s.costIncrease,
        costDecrease: s.costDecrease,
        costEnd: s.costEnd,
        auditedCostBegin: s.auditedCostBegin,
        auditedCostIncrease: s.auditedCostIncrease,
        auditedCostDecrease: s.auditedCostDecrease,
        auditedCostEnd: s.auditedCostEnd,
      }
    case 'amort':
      return {
        name: '合计',
        accAmortBegin: s.accAmortBegin,
        amortProvision: s.amortProvision,
        amortOtherIncrease: s.amortOtherIncrease,
        amortDisposal: s.amortDisposal,
        amortOtherDecrease: s.amortOtherDecrease,
        accAmortEnd: s.accAmortEnd,
        auditedAccAmortBegin: s.auditedAccAmortBegin,
        auditedAmortIncrease: s.auditedAmortIncrease,
        auditedAmortDecrease: s.auditedAmortDecrease,
        auditedAccAmortEnd: s.auditedAccAmortEnd,
      }
    case 'impairment':
      return {
        name: '合计',
        impairmentBegin: s.impairmentBegin,
        impairmentProvision: s.impairmentProvision,
        impairOtherIncrease: s.impairOtherIncrease,
        impairDisposal: s.impairDisposal,
        impairOtherDecrease: s.impairOtherDecrease,
        impairmentEnd: s.impairmentEnd,
        auditedImpairmentBegin: s.auditedImpairmentBegin,
        auditedImpairIncrease: s.auditedImpairIncrease,
        auditedImpairDecrease: s.auditedImpairDecrease,
        auditedImpairmentEnd: s.auditedImpairmentEnd,
      }
    case 'net':
      return {
        name: '合计',
        netBegin: s.netBegin,
        netValue: s.netValue,
        auditedNetBegin: s.auditedNetBegin,
        auditedNetEnd: s.auditedNetEnd,
      }
    default:
      return { name: '合计' }
  }
}

function getSummaryValue(row: Record<string, any>, col: { key: string; type: string }): string {
  const val = row[col.key]
  if (val == null || val === '') return '-'
  if (col.type === 'number' || col.type === 'formula') return fmtAmount(val as number)
  return String(val)
}

function fmtAmount(value: number | null | undefined): string {
  return displayPrefs.fmtAmount(value)
}
</script>

<style scoped>
.i1-tab-detail {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}

/* 方法论上下文（琥珀色） */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p {
  margin: 0;
}
.methodology-context strong {
  color: #78350f;
}

/* 审计目标 alert */
.objective-alert { margin-bottom: 12px; }

/* 编制提示 details */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }

/* 索引 chip */
.chip-wrap { display: inline-flex; align-items: center; }

/* 审计说明/结论卡片 */
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }

/* 交叉验证警告（黄色） */
.cross-validation-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 10px 14px;
  background: #fefce8;
  border: 1px solid #fde047;
  border-radius: 6px;
  font-size: 12px;
  color: #854d0e;
}
.warning-icon {
  color: #eab308;
  font-size: 16px;
}
.warning-item {
  padding: 2px 8px;
  background: #fef9c3;
  border-radius: 4px;
  font-weight: 500;
  margin-left: 4px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.import-export-dropdown {
  margin-left: auto;
}
.row-count {
  margin-left: auto;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.nav-chip {
  cursor: pointer;
}
.nav-chip:hover {
  opacity: 0.85;
}
.category-card {
  margin-top: 16px;
}
.category-table {
  font-size: var(--wp-font-size, 13px);
}

/* 5区段Tab */
.segment-tabs {
  border-radius: 8px;
}
.segment-tabs :deep(.el-tabs__header) {
  background: #f8fafc;
}
.segment-tabs :deep(.el-tabs__item) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}

/* 明细表格 */
.detail-table {
  font-size: var(--wp-font-size, 13px);
}
.detail-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  background: #f8fafc;
}
.detail-table :deep(.active-synced-row) {
  background: #eff6ff !important;
}
.detail-table :deep(.el-table__body tr:hover > td) {
  background: #f0f9ff;
}

/* 公式列表头：虚线下划线 + cursor:help */
.formula-col-header {
  border-bottom: 1px dashed #6b7280;
  cursor: help;
  padding-bottom: 1px;
}

/* 公式值：虚线下划线 + cursor:help + tooltip来源 */
.formula-value {
  border-bottom: 1px dashed #9ca3af;
  cursor: help;
  color: #374151;
  font-weight: 500;
}

/* 输入控件 */
.cell-input-number {
  width: 100%;
}
.cell-input-number :deep(.el-input__inner) {
  text-align: right;
}
.cell-input-text {
  width: 100%;
}
.cell-date-picker {
  width: 100%;
}
.cell-select {
  width: 100%;
}
.cell-readonly {
  color: var(--el-text-color-regular);
}

/* 合计行区域 */
.summary-section {
  margin-top: 8px;
}
.summary-table {
  font-size: var(--wp-font-size, 13px);
}
.summary-table :deep(.el-table__header) {
  display: none;
}
.summary-table :deep(tr td) {
  background: #f0fdf4 !important;
  font-weight: 600;
}
.summary-label {
  font-weight: 700;
  color: #166534;
}
.summary-value {
  font-weight: 600;
  color: #166534;
}
</style>
