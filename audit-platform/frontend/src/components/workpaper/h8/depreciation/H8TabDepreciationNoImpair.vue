<template>
  <div class="h8-tab-depreciation-no-impair">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实未发生减值的使用权资产折旧计提准确性；按直线法独立测算本期及累计折旧，确认折旧期=min(租赁期,使用寿命)（CAS21第21条），并与账面及 H8-1 累计折旧本期计提勾稽。"
    />

    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-8" :context-project-id="projectId" />
      <el-tag size="small" type="info">不含减值 · 共 {{ depRows.length }} 行</el-tag>
      <el-tag v-if="significantDiffRows.length" size="small" type="danger">差异行 {{ significantDiffRows.length }}</el-tag>
      <el-tag size="small" :type="h81DepReconcile.matched ? 'success' : 'warning'">
        {{ h81DepReconcile.matched ? 'H8-1本期计提已勾稽' : 'H8-1本期计提待勾稽' }}
      </el-tag>
      <el-tag
        v-if="h85LeaseTermMismatches.length"
        size="small"
        type="warning"
        class="nav-chip"
        @click="emit('navigate-sheet', 'H8-5')"
      >
        与 H8-5 租期不一致 {{ h85LeaseTermMismatches.length }}
      </el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-5')">← H8-5</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-6')">H8-6</el-tag>
    </div>

    <el-alert
      v-if="h85LeaseTermMismatches.length"
      type="warning"
      :closable="false"
      show-icon
      class="mismatch-alert"
      :title="`有 ${h85LeaseTermMismatches.length} 行租赁期与 H8-5 不一致（例：${h85LeaseTermMismatches[0].contractNo} ${h85LeaseTermMismatches[0].h88Months}≠${h85LeaseTermMismatches[0].h85Months}月）`"
    >
      <template #default>
        <el-button size="small" type="warning" :disabled="isReadonly" @click="handleSyncH85">按 H8-5 覆盖</el-button>
      </template>
    </el-alert>

    <details class="guidance-details" open>
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表适用于<strong>未计提减值</strong>的使用权资产；若已计提减值准备，请切换「含减值」分支并与 H8-10 勾稽。</p>
        <p>2. 测算月折旧＝原值×(1−残值率)÷使用月限；当期折旧＝测算月折旧×本期折旧月份；累计测算＝测算月折旧×期末已提月份。</p>
        <p>3. 折旧期＝min(租赁期, 使用寿命)；能合理确定租赁期满取得所有权时，折旧期取使用寿命。残值率实务常为 0。</p>
        <p>4. 优先「从 H8-2 带入」；若 H8-5 已定租期，带入时自动匹配合同号写入租赁期，也可点「从 H8-5 同步租赁期」。</p>
      </div>
    </details>

    <div class="period-bar">
      <span>折旧期初日</span>
      <el-date-picker
        v-model="localPeriodBegin"
        type="date"
        value-format="YYYY-MM-DD"
        size="small"
        :disabled="isReadonly"
        @change="onPeriodChange"
      />
      <span>截止日</span>
      <el-date-picker
        v-model="localPeriodEnd"
        type="date"
        value-format="YYYY-MM-DD"
        size="small"
        :disabled="isReadonly"
        @change="onPeriodChange"
      />
      <el-button size="small" :disabled="isReadonly" @click="recalcAll">重新测算</el-button>
    </div>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增行</el-button>
      <el-button size="small" :disabled="isReadonly" @click="handleImportH82">从 H8-2 带入</el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSyncH85">从 H8-5 同步租赁期</el-button>
      <el-dropdown size="small" @command="handleExportCmd">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
      <span class="spacer" />
      <el-button size="small" type="primary" plain @click="$emit('open-ai', 'dep-no-impair')">AI 辅助</el-button>
      <el-button size="small" @click="$emit('open-review', 'dep-no-impair')">复核</el-button>
    </div>

    <el-table
      :data="depRows"
      border
      size="small"
      class="formula-table"
      max-height="520"
      :row-class-name="getRowClass"
      show-summary
      :summary-method="getDepSummary"
    >
      <el-table-column type="index" width="40" fixed />
      <el-table-column prop="contractNo" label="合同号" min-width="100" fixed>
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.contractNo" size="small" @change="updateRow($index)" />
          <span v-else>{{ row.contractNo }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="assetCategory" label="类别" width="120">
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            v-model="row.assetCategory"
            size="small"
            filterable
            allow-create
            clearable
            @change="updateRow($index)"
          >
            <el-option v-for="c in assetCategories" :key="c" :label="c" :value="c" />
          </el-select>
          <span v-else>{{ row.assetCategory || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="assetName" label="名称" min-width="110" show-overflow-tooltip>
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="updateRow($index)" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="originalCost" label="原值" width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model.number="row.originalCost" size="small" @change="updateRow($index)" />
          <span v-else>{{ fmtAmt(row.originalCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="bookAccDepEnd" label="账面累计折旧" width="110" align="right">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model.number="row.bookAccDepEnd" size="small" @change="updateRow($index)" />
          <span v-else>{{ fmtAmt(row.bookAccDepEnd) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="startDate" label="开始使用日期" width="120">
        <template #default="{ row, $index }">
          <el-date-picker
            v-if="!isReadonly"
            v-model="row.startDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width:100%"
            @change="updateRow($index)"
          />
          <span v-else>{{ row.startDate || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="usefulLife" label="使用年限" width="80" align="right">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model.number="row.usefulLife" size="small" @change="updateRow($index)" />
          <span v-else>{{ row.usefulLife }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="leaseTermMonths" label="租赁期(月)" width="90" align="right">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model.number="row.leaseTermMonths" size="small" @change="updateRow($index)" />
          <span v-else>{{ row.leaseTermMonths }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="salvageRate" label="残值率" width="70" align="right">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model.number="row.salvageRate" size="small" @change="updateRow($index)" />
          <span v-else>{{ row.salvageRate }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="bookMonthly" label="账面月折旧" width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model.number="row.bookMonthly" size="small" @change="updateRow($index)" />
          <span v-else>{{ fmtAmt(row.bookMonthly || 0) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="折旧期(月)" width="80" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="min(租赁期, 使用寿命月数)">{{ row.depPeriodMonths }}</span>
        </template>
      </el-table-column>
      <el-table-column label="测算到期日" width="100" class-name="formula-col">
        <template #default="{ row }"><span class="formula-value">{{ row.fullDepDate || '—' }}</span></template>
      </el-table-column>
      <el-table-column label="已提月份" width="70" align="right" class-name="formula-col">
        <template #default="{ row }"><span class="formula-value">{{ row.monthsAtEnd }}</span></template>
      </el-table-column>
      <el-table-column label="本期月数" width="70" align="right" class-name="formula-col">
        <template #default="{ row }"><span class="formula-value">{{ row.periodMonths }}</span></template>
      </el-table-column>
      <el-table-column label="测算月折旧" width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="原值×(1−残值率)÷使用月限">{{ fmtAmt(row.calcMonthly) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="当期折旧费用" width="110" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="测算月折旧×本期月数">{{ fmtAmt(row.periodDep) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="月折旧差异" width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'text-danger': Math.abs(row.monthlyDiff) > 0.01 }">{{ fmtAmt(row.monthlyDiff) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="测算累计折旧" width="110" align="right" class-name="formula-col">
        <template #default="{ row }"><span class="formula-value">{{ fmtAmt(row.calcAccDep) }}</span></template>
      </el-table-column>
      <el-table-column label="累计差异" width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'text-danger': Math.abs(row.accDepDiff) > 0.01 }">{{ fmtAmt(row.accDepDiff) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="bookDepreciation" label="账面本期折旧" width="110" align="right">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model.number="row.bookDepreciation" size="small" @change="updateRow($index)" />
          <span v-else>{{ fmtAmt(row.bookDepreciation || 0) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期差异" width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'text-danger': Math.abs(row.difference) > 0.01 }">{{ fmtAmt(row.difference) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="deleteDepRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary-row">
      <span>测算本期合计：<b>{{ fmtAmt(depTotal) }}</b></span>
      <span>账面本期合计：<b>{{ fmtAmt(totalBookDep) }}</b></span>
      <span>本期差异：<b :class="{ 'text-danger': Math.abs(totalDifference) > 0.01 }">{{ fmtAmt(totalDifference) }}</b></span>
      <span>累计差异：<b :class="{ 'text-danger': Math.abs(totalAccDepDiff) > 0.01 }">{{ fmtAmt(totalAccDepDiff) }}</b></span>
    </div>

    <div v-if="categorySubtotals.length" class="category-subtotals">
      <div v-for="c in categorySubtotals" :key="c.category" class="cat-line">
        <span>{{ c.category }}</span>
        <span>本期 {{ fmtAmt(c.periodDep) }}</span>
        <span>测算累计 {{ fmtAmt(c.calcAccDep) }}</span>
      </div>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="说明折旧参数合理性、测算与账面差异原因、与 H8-2/H8-1/H8-9 勾稽情况。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="A、折旧测算准确，与账面无重大差异。B、除下列差异外未见异常。C、存在重大未调整差异，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDepreciationNoImpair.vue — H8-8(A) 折旧测算表（不含减值）
 * 对齐 Excel「折旧测算表（不含减值）H8-8」列结构与测算逻辑
 */
import { ref, toRef, watch, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH8Depreciation, H8_DEP_ASSET_CATEGORIES } from '../../composables/useH8Depreciation'
import GtIndexChip from '../../GtIndexChip.vue'

const assetCategories = [...H8_DEP_ASSET_CATEGORIES]

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /** 父入口分支，强制「不含减值」 */
  branch?: string
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const externalBranch = computed(() => '不含减值' as const)

const AUDIT_NOTE_KEY = 'H8-dep-no-impair-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-dep-no-impair-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function _hydrateAudit() {
  const n = props.allResponses.get(AUDIT_NOTE_KEY)
  if (n?.remark != null) auditNote.value = n.remark
  const c = props.allResponses.get(AUDIT_CONCLUSION_KEY)
  if (c?.remark != null) auditConclusion.value = c.remark
}
_hydrateAudit()
watch(() => props.allResponses, _hydrateAudit)
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', AUDIT_NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', AUDIT_CONCLUSION_KEY, val)
}

const {
  depRows, depTotal, totalBookDep, totalDifference, totalAccDepDiff,
  significantDiffRows, h85LeaseTermMismatches, h81DepReconcile, categorySubtotals,
  periodBegin, periodEnd,
  addDepRow, deleteDepRow, updateRow, recalcAll,
  setPeriodDates, importFromH82, syncLeaseTermFromH85, exportData, importData,
} = useH8Depreciation({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
  externalBranch,
})

const localPeriodBegin = ref('')
const localPeriodEnd = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
watch([periodBegin, periodEnd], () => {
  localPeriodBegin.value = periodBegin.value
  localPeriodEnd.value = periodEnd.value
}, { immediate: true })

function onPeriodChange() {
  if (localPeriodBegin.value && localPeriodEnd.value) {
    setPeriodDates(localPeriodBegin.value, localPeriodEnd.value)
  }
}

function fmtAmt(v: number): string {
  if (v == null || Number.isNaN(v)) return '-'
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入合同号（可留空）', '新增折旧行', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    inputPlaceholder: '如：LEASE-2024-001',
  }).catch(() => ({ value: null }))
  if (value !== null) addDepRow(value || '')
}

function handleImportH82() {
  const r = importFromH82(true)
  ElMessage.success(r.message)
}

function handleSyncH85() {
  const r = syncLeaseTermFromH85()
  if (!r.ok && r.updated === 0) {
    ElMessage.warning(r.reason || '同步失败')
    return
  }
  if (r.updated > 0) {
    ElMessage.success(`已从 H8-5 同步 ${r.updated} 行租赁期并重算折旧`)
  } else {
    ElMessage.info(r.reason || '已一致')
  }
  if (r.unmatchedContracts.length) {
    ElMessage.warning(`H8-5 有租期但本表无合同：${r.unmatchedContracts.join('、')}`)
  }
}

async function handleExportCmd(cmd: string) {
  if (cmd === 'export-template') await exportData('template')
  else if (cmd === 'export-data') await exportData('data')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const r = await importData(file, true)
  ElMessage.success(`已导入 ${r.imported} 行`)
  input.value = ''
}

function getRowClass({ row }: { row: any }) {
  if (Math.abs(row.difference) > 0.01 || Math.abs(row.accDepDiff) > 0.01) return 'diff-row'
  return ''
}

function getDepSummary({ columns }: { columns: any[] }) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const p = col.property
    if (p === 'originalCost') return fmtAmt(depRows.value.reduce((s, r) => s + (r.originalCost || 0), 0))
    if (p === 'bookAccDepEnd') return fmtAmt(depRows.value.reduce((s, r) => s + (r.bookAccDepEnd || 0), 0))
    if (col.label === '当期折旧费用') return fmtAmt(depTotal.value)
    if (col.label === '测算累计折旧') {
      return fmtAmt(depRows.value.reduce((s, r) => s + (r.calcAccDep || 0), 0))
    }
    return ''
  })
}
</script>

<style scoped>
.h8-tab-depreciation-no-impair { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.nav-chip { cursor: pointer; }
.nav-chip:hover { opacity: 0.85; }
.mismatch-alert { margin-bottom: 12px; }

.guidance-details {
  margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary);
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 600; color: #334155; }
.guidance-content { margin-top: 8px; line-height: 1.6; }
.guidance-content p { margin: 4px 0; }

.period-bar, .toolbar {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
}
.spacer { flex: 1; }

.formula-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.formula-table :deep(.formula-col) { background: #f0f9ff; }
.formula-table :deep(.diff-row) { background: #fff7ed; }
.formula-value { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; }
.text-danger { color: #dc2626; font-weight: 600; }

.summary-row {
  display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 12px;
  font-size: 12px; color: #475569;
}
.category-subtotals {
  display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px;
  font-size: 12px; color: #64748b;
}
.cat-line { display: flex; gap: 16px; }

.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }
</style>
