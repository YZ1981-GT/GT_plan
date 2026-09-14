<template>
  <div class="n5-tab-detail">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>所得税费用明细表 N5-2</span>
        <el-tag size="small">当期/递延分项</el-tag>
      </div>
      <div class="section-actions">
        <el-dropdown trigger="click" @command="handleImportExportCmd">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 主数据表格（10列8公式） ═══ -->
    <el-table :data="detailRows" border size="small" show-summary :summary-method="getSummaries" class="detail-table">
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="itemName" label="明细项目" min-width="180">
        <template #default="{ row }">
          <span :class="{ 'subtotal-name': row.isSubtotal }">{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="taxType" label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.taxType === '当期' ? 'warning' : 'success'" size="small">{{ row.taxType }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.isSubtotal" v-model="row.unadjusted" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleRowChange(row)" />
          <span v-else class="cell-value">{{ fmtAmount(row.unadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="aje" label="AJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.isSubtotal" v-model="row.aje" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleRowChange(row)" />
          <span v-else class="cell-value">{{ fmtAmount(row.aje) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="rje" label="RJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.isSubtotal" v-model="row.rje" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleRowChange(row)" />
          <span v-else class="cell-value">{{ fmtAmount(row.rje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定数" min-width="110" align="right">
        <template #header><span class="formula-header" title="审定=未审+AJE+RJE">审定数</span></template>
        <template #default="{ row }">
          <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.audited) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="priorPeriod" label="上期数" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.isSubtotal" v-model="row.priorPeriod" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleRowChange(row)" />
          <span v-else class="cell-value">{{ fmtAmount(row.priorPeriod) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" min-width="100" align="right">
        <template #header><span class="formula-header" title="变动=审定-上期">变动额</span></template>
        <template #default="{ row }">
          <span class="formula-cell" :class="{ negative: row.change < 0 }">{{ fmtAmount(row.change) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly && !row.isSubtotal" v-model="row.remark" size="small" placeholder="备注..." @change="() => handleRowChange(row)" />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 动态行操作 ═══ -->
    <div class="row-actions">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增明细行</el-button>
    </div>

    <!-- ═══ N5-1交叉验证 ═══ -->
    <div class="cross-check">
      <span class="cross-label">N5-2合计 vs N5-1审定表：</span>
      <span :class="['cross-status', crossMatch ? 'cross-ok' : 'cross-err']">
        {{ crossMatch ? '✓ 一致' : '⚠ 差异 ' + fmtAmount(crossDiff) }}
      </span>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header><span class="notes-title">审计说明与结论</span></template>
      <div class="notes-field">
        <label class="field-label">审计说明</label>
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请输入..." :disabled="isReadonly" @change="saveNotes" />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="请输入..." :disabled="isReadonly" @change="saveConclusion" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabDetail — 所得税费用明细表 N5-2
 * 10列8公式+当期/递延分项+合计与N5-1交叉验证+动态行+导入导出
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.3
 * Requirements: 9.1-9.2
 */
import { ref, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { useN5ImportExport } from '../../composables/useN5ImportExport'
import { calcAuditedAmount } from '../../composables/useN5FormulaEngine'
import { useN5CrossSheet } from '../../composables/useN5CrossSheet'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((s: string) => void) | undefined>('openReviewDialog', undefined)
const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>
const allResponsesRef = computed(() => props.allResponses)

const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef })
const importExport = useN5ImportExport({ wpId: wpIdRef, projectId: projectIdRef })
const { adjudicationVsCalc } = useN5CrossSheet(allResponsesRef, { wpId: wpIdRef, projectId: projectIdRef })

// ─── 明细行 ──────────────────────────────────────────────────────────────────

interface DetailRow {
  id: string; seq: number; itemName: string; taxType: '当期' | '递延'
  unadjusted: number; aje: number; rje: number; audited: number
  priorPeriod: number; change: number; remark: string; isSubtotal: boolean
}

const dynamicRows = ref<DetailRow[]>([])
const auditNotes = ref('')
const auditConclusion = ref('')

const defaultRows: Omit<DetailRow, 'audited' | 'change'>[] = [
  { id: 'current-main', seq: 1, itemName: '当期所得税费用', taxType: '当期', unadjusted: 0, aje: 0, rje: 0, priorPeriod: 0, remark: '', isSubtotal: false },
  { id: 'current-sub', seq: 2, itemName: '  其中：企业所得税', taxType: '当期', unadjusted: 0, aje: 0, rje: 0, priorPeriod: 0, remark: '', isSubtotal: false },
  { id: 'deferred-main', seq: 3, itemName: '递延所得税费用', taxType: '递延', unadjusted: 0, aje: 0, rje: 0, priorPeriod: 0, remark: '', isSubtotal: false },
  { id: 'deferred-asset', seq: 4, itemName: '  递延所得税资产减少', taxType: '递延', unadjusted: 0, aje: 0, rje: 0, priorPeriod: 0, remark: '', isSubtotal: false },
  { id: 'deferred-liab', seq: 5, itemName: '  递延所得税负债增加', taxType: '递延', unadjusted: 0, aje: 0, rje: 0, priorPeriod: 0, remark: '', isSubtotal: false },
]

const detailRows = computed<DetailRow[]>(() => {
  const rows = dynamicRows.value.map(r => ({
    ...r,
    audited: calcAuditedAmount(r.unadjusted, r.aje, r.rje),
    change: calcAuditedAmount(r.unadjusted, r.aje, r.rje) - r.priorPeriod,
  }))
  // 合计小计行
  const totalAudited = rows.reduce((s, r) => s + calcAuditedAmount(r.unadjusted, r.aje, r.rje), 0)
  const totalPrior = rows.reduce((s, r) => s + r.priorPeriod, 0)
  rows.push({ id: 'total', seq: rows.length + 1, itemName: '合计', taxType: '当期', unadjusted: 0, aje: 0, rje: 0, audited: totalAudited, priorPeriod: totalPrior, change: totalAudited - totalPrior, remark: '', isSubtotal: true })
  return rows
})

// ─── N5-1交叉验证 ────────────────────────────────────────────────────────────

const detailTotal = computed(() => detailRows.value.find(r => r.isSubtotal)?.audited ?? 0)
const crossDiff = computed(() => detailTotal.value - adjudicationVsCalc.value.total)
const crossMatch = computed(() => Math.abs(crossDiff.value) < 0.01)

// ─── 数据加载 ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  const saved = formData.getField('2', 'detail-rows')
  if (saved && Array.isArray(saved) && saved.length > 0) {
    dynamicRows.value = saved
  } else {
    dynamicRows.value = defaultRows.map(r => ({ ...r, audited: 0, change: 0 }))
  }
  auditNotes.value = formData.getField('2', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('2', 'audit-conclusion') ?? ''
})

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleRowChange(row: DetailRow) {
  row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
  row.change = row.audited - row.priorPeriod
  await formData.setField('2', 'detail-rows', dynamicRows.value.filter(r => !r.isSubtotal))
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入明细项目名称', '新增明细行', { confirmButtonText: '确认', cancelButtonText: '取消' })
    if (!value?.trim()) return
    const newRow: DetailRow = {
      id: `dyn-${Date.now()}`, seq: dynamicRows.value.length + 1,
      itemName: value.trim(), taxType: '当期',
      unadjusted: 0, aje: 0, rje: 0, audited: 0, priorPeriod: 0, change: 0, remark: '', isSubtotal: false,
    }
    dynamicRows.value.push(newRow)
    await formData.setField('2', 'detail-rows', dynamicRows.value)
    ElMessage.success(`已新增: ${value.trim()}`)
  } catch { /* cancelled */ }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

function handleImportExportCmd(cmd: string) {
  if (cmd === 'exportTemplate') importExport.exportTemplate('N5-2')
  else if (cmd === 'exportData') importExport.exportData('N5-2')
  else if (cmd === 'importData') {
    const input = document.createElement('input')
    input.type = 'file'; input.accept = '.xlsx,.xls'
    input.onchange = async (e: any) => {
      const file = e.target.files?.[0]
      if (file) { await importExport.importData(file, 'N5-2'); await formData.loadData() }
    }
    input.click()
  }
}

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function saveNotes() { await formData.setField('2', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('2', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n5-detail',
      prompt: '请基于所得税费用底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog ? openReviewDialog('N5-2-明细表') : ElMessage.info('复核对话未配置') }

function getSummaries({ columns }: { columns: any[] }) {
  return columns.map((_c: any, idx: number) => idx === 0 ? '' : (idx === 1 ? '合计' : ''))
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.n5-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }
.detail-table { margin-bottom: 16px; }
:deep(.detail-table .el-table) { font-size: var(--wp-font-size, 13px); }
.subtotal-name { font-weight: 700; color: #409eff; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.cell-value { font-size: var(--wp-font-size, 13px); color: #606266; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-weight: 500; color: #303133; padding-bottom: 1px; }
.negative { color: #f56c6c !important; }
.row-actions { margin-bottom: 16px; }
.cross-check { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; padding: 10px 16px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 6px; }
.cross-label { font-size: var(--wp-font-size, 13px); color: #606266; }
.cross-status { font-weight: 600; font-size: var(--wp-font-size, 13px); }
.cross-ok { color: #43a047; }
.cross-err { color: #f56c6c; }
.audit-notes-card { margin-bottom: 16px; }
.notes-title { font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #606266; margin-bottom: 6px; }
</style>
