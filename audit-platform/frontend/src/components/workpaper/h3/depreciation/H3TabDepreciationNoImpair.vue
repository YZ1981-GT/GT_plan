<template>
  <div class="h3-tab-depreciation-no-impair">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：复核投资性房地产（成本模式）折旧计提的准确性，按直线法独立测算本期折旧及累计折旧，并与账面核对。"
    />

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-7" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">不含减值 · 共 {{ rows.length }} 行</el-tag>
      <el-tag v-if="significantDiffRows.length" size="small" type="danger">差异行 {{ significantDiffRows.length }}</el-tag>
      <el-tag size="small" :type="h31DepReconcile.matched ? 'success' : 'warning'">
        {{ h31DepReconcile.matched ? 'H3-1累计折旧已勾稽' : 'H3-1累计折旧待勾稽' }}
      </el-tag>
    </div>

    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表适用于成本模式、<strong>无减值</strong>的投资性房地产；公允价值模式不计提折旧。</p>
        <p>2. 测算月折旧＝原值×(1−残值率)÷使用月限；当期折旧＝测算月折旧×本期折旧月份；累计测算＝测算月折旧×期末已提月份。</p>
        <p>3. 投入使用<strong>次月</strong>起提折旧；关注月折旧差异、累计折旧差异（红色&gt;0.01）。</p>
        <p>4. 若资产存在减值准备，请切换至「含减值」版本，并与 H3-10 勾稽。</p>
      </div>
    </details>

    <div class="period-bar">
      <span>期初日</span>
      <el-date-picker v-model="localPeriodBegin" type="date" value-format="YYYY-MM-DD" size="small" :disabled="isReadonly" @change="onPeriodChange" />
      <span>截止日</span>
      <el-date-picker v-model="localPeriodEnd" type="date" value-format="YYYY-MM-DD" size="small" :disabled="isReadonly" @change="onPeriodChange" />
      <el-button size="small" :disabled="isReadonly" @click="recalcAll">重新测算</el-button>
    </div>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow()">+ 新增资产行</el-button>
      <el-button size="small" :disabled="isReadonly" @click="handleImportH32">从 H3-2 带入</el-button>
      <el-dropdown size="small" class="export-dropdown" @command="handleExportCmd">
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
    </div>

    <el-table :data="rows" border size="small" class="audit-table" max-height="520" :row-class-name="getRowClass" show-summary :summary-method="getSummary">
      <el-table-column type="index" width="40" fixed />
      <el-table-column prop="assetNo" label="编号" width="80" fixed>
        <template #default="{ row, $index }">
          <el-input v-model="row.assetNo" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column prop="category" label="类别" width="90">
        <template #default="{ row, $index }">
          <el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column prop="assetName" label="名称" min-width="110" fixed show-overflow-tooltip>
        <template #default="{ row, $index }">
          <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column prop="department" label="管理部门" width="90">
        <template #default="{ row, $index }">
          <el-input v-model="row.department" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column prop="originalCost" label="原值" width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.originalCost" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column prop="bookAccDepEnd" label="账面累计折旧" width="110" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.bookAccDepEnd" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column prop="startDate" label="开始使用日期" width="120">
        <template #default="{ row, $index }">
          <el-date-picker v-model="row.startDate" type="date" value-format="YYYY-MM-DD" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column prop="usefulLife" label="使用年限" width="70" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.usefulLife" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column prop="salvageRate" label="残值率" width="70" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.salvageRate" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column prop="bookMonthly" label="账面月折旧" width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.bookMonthly" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column label="使用月限" width="70" align="right" class-name="formula-col">
        <template #default="{ row }"><span class="formula-value">{{ row.usefulLifeMonths || '-' }}</span></template>
      </el-table-column>
      <el-table-column label="测算到期日" width="100" class-name="formula-col">
        <template #default="{ row }"><span class="formula-value">{{ row.fullDepDate || '-' }}</span></template>
      </el-table-column>
      <el-table-column label="已提月份" width="70" align="right" class-name="formula-col">
        <template #default="{ row }"><span class="formula-value" title="期末已提折旧月份">{{ row.monthsAtEnd }}</span></template>
      </el-table-column>
      <el-table-column label="本期月数" width="70" align="right" class-name="formula-col">
        <template #default="{ row }"><span class="formula-value">{{ row.periodMonths }}</span></template>
      </el-table-column>
      <el-table-column label="测算月折旧" width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="原值×(1-残值率)÷使用月限">{{ fmtNum(row.calcMonthly) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="当期折旧费用" width="110" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="测算月折旧×本期月数">{{ fmtNum(row.periodDep) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="月折旧差异" width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'text-danger': Math.abs(row.monthlyDiff) > 0.01 }">{{ fmtNum(row.monthlyDiff) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="测算累计折旧" width="110" align="right" class-name="formula-col">
        <template #default="{ row }"><span class="formula-value">{{ fmtNum(row.calcAccDep) }}</span></template>
      </el-table-column>
      <el-table-column label="累计差异" width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'text-danger': Math.abs(row.accDepDiff) > 0.01 }">{{ fmtNum(row.accDepDiff) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="bookDepreciation" label="账面本期折旧" width="110" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.bookDepreciation" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column label="本期差异" width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'text-danger': Math.abs(row.difference) > 0.01 }">{{ fmtNum(row.difference) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="90">
        <template #default="{ row, $index }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" @click="removeRow($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary-row">
      <span>测算本期合计：<b>{{ fmtNum(totalPeriodDep) }}</b></span>
      <span>账面本期合计：<b>{{ fmtNum(totalBookDep) }}</b></span>
      <span>本期差异：<b :class="{ 'text-danger': Math.abs(totalDifference) > 0.01 }">{{ fmtNum(totalDifference) }}</b></span>
      <span>累计差异：<b :class="{ 'text-danger': Math.abs(totalAccDepDiff) > 0.01 }">{{ fmtNum(totalAccDepDiff) }}</b></span>
    </div>

    <div class="summary-row">
      <span>H3-1累计折旧审定数：<b>{{ fmtNum(h31DepReconcile.h31AuditedDepTotal) }}</b></span>
      <span>H3-7账面累计折旧：<b>{{ fmtNum(h31DepReconcile.h37BookAccTotal) }}</b></span>
      <span>账面勾稽差异：<b :class="{ 'text-danger': Math.abs(h31DepReconcile.bookDiff) > 0.01 }">{{ fmtNum(h31DepReconcile.bookDiff) }}</b></span>
      <span>测算勾稽差异：<b :class="{ 'text-danger': Math.abs(h31DepReconcile.calcDiff) > 0.01 }">{{ fmtNum(h31DepReconcile.calcDiff) }}</b></span>
    </div>

    <el-card shadow="never" class="recalc-card">
      <template #header>
        <div class="card-header">
          <span>折旧合理性整体重算（实质性分析程序）</span>
          <el-tag
            size="small"
            :type="depreciationRecalc.flagged ? 'danger' : depreciationRecalc.hasBasis ? 'success' : 'info'"
          >
            {{ depreciationRecalc.hasBasis ? `差异率 ${depreciationRecalc.diffRatePct.toFixed(1)}%${depreciationRecalc.flagged ? ' · 超阈值' : ''}` : '待录入资产参数' }}
          </el-tag>
        </div>
      </template>
      <p class="recalc-hint">
        独立预期：原值合计 × 综合年折旧率（默认按各资产「原值×(1−残值率)÷年限」加权推导，可手工覆盖），与账面本期折旧比较；差异率 &gt;10% 触发关注。此为高层分析，与上表逐行测算互补。
      </p>
      <div class="recalc-grid">
        <div class="rc-item"><label>原值合计</label><span class="amount-cell">{{ fmtNum(depreciationRecalc.grossTotal) }}</span></div>
        <div class="rc-item">
          <label>综合年折旧率(%)</label>
          <div class="rc-rate">
            <el-input-number
              :model-value="depRecalcRateOverride ?? Number(depreciationRecalc.ratePct.toFixed(4))"
              :controls="false" :precision="4" size="small" :disabled="isReadonly" style="width:120px"
              @change="(v: number | undefined) => setDepRecalcRate(v ?? null)"
            />
            <el-tag size="small" :type="depreciationRecalc.isManualRate ? 'warning' : 'info'">{{ depreciationRecalc.isManualRate ? '手工' : '理论推导' }}</el-tag>
            <el-button v-if="depreciationRecalc.isManualRate && !isReadonly" size="small" link @click="setDepRecalcRate(null)">恢复推导</el-button>
          </div>
        </div>
        <div class="rc-item"><label>预期本期折旧</label><span class="amount-cell" title="原值合计×综合年折旧率">{{ fmtNum(depreciationRecalc.expected) }}</span></div>
        <div class="rc-item"><label>账面本期折旧</label><span class="amount-cell">{{ fmtNum(depreciationRecalc.booked) }}</span></div>
        <div class="rc-item"><label>差异</label><span class="amount-cell" :class="{ 'text-danger': depreciationRecalc.flagged }">{{ fmtNum(depreciationRecalc.diff) }}</span></div>
        <div class="rc-item"><label>差异率</label><span :class="{ 'text-danger': depreciationRecalc.flagged }">{{ depreciationRecalc.hasBasis ? depreciationRecalc.diffRatePct.toFixed(2) + '%' : '-' }}</span></div>
      </div>
      <el-alert v-if="depreciationRecalc.flagged" type="warning" :closable="false" show-icon style="margin-top:10px"
        title="预期折旧与账面本期折旧差异率超过 10%，请核查折旧参数/计提是否恰当，并在下方说明差异原因。" />
      <div class="recalc-note">
        <label>差异原因说明</label>
        <el-input :model-value="depRecalcExplanation" type="textarea" :autosize="{ minRows: 2 }"
          placeholder="说明预期折旧与账面差异的原因（如资产结构、年限/残值率差异、当期新增或处置影响等）。"
          :disabled="isReadonly" @change="setDepRecalcExplanation" />
      </div>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-7-no-impair')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-7-no-impair')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 4 }" placeholder="说明折旧参数合理性、测算与账面差异原因、与 H3-2/H3-1 勾稽情况。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>四、审计结论</span></div></template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="A、折旧测算准确，与账面无重大差异。B、除下列差异外未见异常。C、存在重大未调整差异，不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDepreciationNoImpair.vue — H3-7(A) 折旧不含减值
 * 对齐 Excel「折旧测算表（成本模式不含减值）H3-7」28列结构
 */
import { ref, computed, inject, toRef, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH3Depreciation } from '../../composables/useH3Depreciation'
import { useH3FormData } from '../../composables/useH3FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import { generateH3AI, h3AiLoading } from '../useH3AiGenerate'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  periodEnd?: string
  auditYear?: number
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})
const branch = ref<'noImpair' | 'withImpair'>('noImpair')

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost') as any,
})

const {
  rows, periodBegin, periodEnd, addRow, removeRow, updateRow, recalcAll,
  totalPeriodDep, totalBookDep, totalDifference, totalAccDepDiff, significantDiffRows, h31DepReconcile,
  setPeriodDates,
  importFromH32, exportData, importData,
  depreciationRecalc, depRecalcRateOverride, depRecalcExplanation, setDepRecalcRate, setDepRecalcExplanation,
} = useH3Depreciation({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  branch,
  periodEnd: computed(() => props.periodEnd),
  auditYear: computed(() => props.auditYear),
  getValue, setValue, saveImmediate,
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

const NOTE_KEY = 'H3-7-noimpair-audit-note'
const CONCLUSION_KEY = 'H3-7-noimpair-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function onCellChange(index: number) { updateRow(index) }
function handleImportH32() {
  const result = importFromH32(true)
  ElMessage[result.imported ? 'success' : 'info'](result.message)
}
async function handleExportCmd(cmd: string) {
  if (cmd === 'export-template') await exportData('template')
  else if (cmd === 'export-data') await exportData('data')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}
async function onFileSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  const result = await importData(file, true)
  ElMessage.success(`已导入 ${result.imported} 行`)
  ElMessageBox.alert('导入完成。若勾稽结果未即时刷新，请切换分支或底稿后返回查看。', '提示')
}
function getRowClass({ row }: { row: any }): string {
  if (Math.abs(row.difference) > 0.01 || Math.abs(row.accDepDiff) > 0.01) return 'row-warn'
  return ''
}
function getSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '合计'
    if (idx === 17) return fmtNum(totalPeriodDep.value)
    if (idx === 19) return fmtNum(totalAccDepDiff.value)
    return ''
  })
}
function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
const _h3AiLoading = h3AiLoading
async function generateAI(section: string) {
  await generateH3AI(props.wpId, section)
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-depreciation-no-impair { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }
.period-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.export-dropdown { margin-left: 0; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.audit-table :deep(.row-warn) { background-color: #fef9e7 !important; }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); }
.summary-row { display: flex; align-items: center; gap: 16px; margin: 12px 0; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; flex-wrap: wrap; }
.action-btns { display: flex; gap: 4px; }
.recalc-card { margin-top: 16px; }
.recalc-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.recalc-hint { margin: 0 0 12px; font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.6; }
.recalc-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px 20px; }
.rc-item { display: flex; flex-direction: column; gap: 4px; }
.rc-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.rc-rate { display: flex; align-items: center; gap: 6px; }
.amount-cell { font-variant-numeric: tabular-nums; font-weight: 600; }
.recalc-note { margin-top: 12px; display: flex; flex-direction: column; gap: 6px; }
.recalc-note label { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
