<script setup lang="ts">
/**
 * D4TabCustomerChecklist — D4-28 客户信息核查清单
 *
 * 15 列（10 主列 + 5 二级列），两级表头。
 * 父组「核查方式（√）」跨 5 列 checkbox。三个占比列表内计算。
 * 🔴 不得压扁；守卫断言 DOM 父组跨列数 = 5。
 * 🔴 本组件零公式字面量，只引用 ipoChecklistSchema + ipoChecklistFormulaEngine。
 */
import { ref, computed, inject, watch, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { DisplayPrefs_Key } from '@/stores/displayPrefs'
import {
  SHEET_SPECS, getDerivedColumns, getAddRowPromptTitle, getAddRowInputLabel,
  createEmptyRow, type RowRecord,
} from './ipoChecklistSchema'
import { recalcAllDerived, setManualOverride, type ManualOverrides } from './ipoChecklistFormulaEngine'

const SHEET_CODE = 'D4-28' as const
const spec = SHEET_SPECS[SHEET_CODE]
const derivedKeys = getDerivedColumns(SHEET_CODE)

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const rows = ref<RowRecord[]>([])
const auditNote = ref(''); const auditConclusion = ref('')
const manualOverrides = ref<ManualOverrides>(new Map())
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const ROWS_KEY = `${SHEET_CODE}-rows`
const NOTE_KEY = `${SHEET_CODE}-note`
const CONCLUSION_KEY = `${SHEET_CODE}-conclusion`

function loadData() { const r = props.allResponses.get(ROWS_KEY); if (r?.remark) { try { const p = JSON.parse(r.remark); if (Array.isArray(p)) { rows.value = p; doRecalc(); return } } catch {} }; rows.value = [] }
function loadNote() { auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''; auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || '' }
watch(() => props.allResponses.get(ROWS_KEY)?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get(NOTE_KEY)?.remark, loadNote, { immediate: true })

function doRecalc() { const errors = recalcAllDerived(SHEET_CODE, rows.value, manualOverrides.value); if (errors.length > 0) console.warn('[D4-28] 公式求值错误:', errors) }

async function handleAddRow() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt(getAddRowInputLabel(SHEET_CODE), getAddRowPromptTitle(SHEET_CODE), { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' })
    if (value?.trim()) { rows.value.push(createEmptyRow(SHEET_CODE, value.trim())); doRecalc(); persistAll() }
  } catch {}
}
function removeRow(rowId: string) { if (props.isReadonly) return; rows.value = rows.value.filter(r => r.rowId !== rowId); doRecalc(); persistAll() }

function updateCell(rowId: string, key: string, value: unknown) {
  if (props.isReadonly) return
  const row = rows.value.find(r => r.rowId === rowId)
  if (!row) return
  if (derivedKeys.has(key)) {
    const numVal = value === '' || value === null || value === undefined ? null : Number(value)
    if (numVal !== null && !Number.isFinite(numVal)) return
    setManualOverride(manualOverrides.value, SHEET_CODE, key, rowId, numVal)
    row[key] = numVal
    ElMessage.info('该列为计算列，已锁定为手填值')
  } else { row[key] = value; doRecalc() }
  persistAll()
}

function toggleCheckbox(rowId: string, key: string, val: boolean) {
  if (props.isReadonly) return
  const row = rows.value.find(r => r.rowId === rowId)
  if (!row) return; row[key] = val; persistAll()
}

function persistAll() {
  props.allResponses.set(ROWS_KEY, { item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value })
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { debounceTimer = null; const keys = [ROWS_KEY, NOTE_KEY, CONCLUSION_KEY]; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function flushPendingSave() { if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; const keys = [ROWS_KEY, NOTE_KEY, CONCLUSION_KEY]; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } }
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { flushPendingSave() })

const editorMode = ref<string>('表格视图'); const modeOptions = ['表格视图', '在线编辑']
const syncState = ref<{ ok: boolean; message: string } | null>(null)
watch(editorMode, async (newMode, oldMode) => { if (newMode === oldMode) return; syncState.value = null; if (newMode === '在线编辑') { flushPendingSave() } else if (newMode === '表格视图') { await nextTick(); loadData() } })

// AI
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于客户信息核查清单(D4-28)结果生成审计说明', rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于客户核查清单结果生成审计结论', noteText: auditNote.value, rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function handleExportTemplate() { exportTemplate(SHEET_CODE) }
function handleExportData() { exportData(SHEET_CODE) }
async function handleImportFile(f: any) { await importData(SHEET_CODE, f.raw || f); editorMode.value = '表格视图'; await nextTick(); loadData() }

function fmtPercent(v: unknown): string { if (v === null || v === undefined || v === '') return ''; const n = Number(v); if (!Number.isFinite(n)) return ''; return (n * 100).toFixed(2) + '%' }
function fmtAmt(v: unknown): string { if (v === null || v === undefined || v === '') return ''; const n = Number(v); if (!Number.isFinite(n)) return String(v); return displayPrefs.fmtAmount(n) }

const checkedCount = computed(() => rows.value.filter(r => r.checkBiz || r.checkInternet || r.checkConfirm || r.checkCall || r.checkVisit).length)
</script>

<template>
<div class="d4-customer-checklist">
  <div class="toolbar">
    <div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div>
    <div class="toolbar-right">
      <el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item><el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown>
      <GtIndexChip value="wp:D4-29" :context-project-id="projectId" />
      <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-28-checklist')">💬 复核</el-button>
    </div>
  </div>
  <div v-if="syncState" :class="['sync-banner', syncState.ok ? 'sync-ok' : 'sync-fail']">{{ syncState.message }}</div>

  <!-- 仪表板 -->
  <div class="stats-dashboard">
    <div class="stat-card stat-primary"><div class="stat-value">{{ rows.length }}<span class="stat-unit">家</span></div><div class="stat-label">抽取客户</div></div>
    <div class="stat-card stat-ok"><div class="stat-value">{{ checkedCount }}<span class="stat-unit">家</span></div><div class="stat-label">已执行核查</div></div>
  </div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 编制说明 -->
    <div class="methodology-strip">
      <div class="methodology-content">
        <p>核查主要客户及交易真实性，包括调查交易对手背景和商业目的等。</p>
        <p>对比历年主要客户清单，关注报告期新增的主要客户、原有主要客户交易额大幅减少或合作关系取消的情况。</p>
        <p>根据客户集中度和风险情况抽取客户/项目，考虑实施查询工商资料、互联网查询、电话访谈关键经办人员、实地走访客户等程序。</p>
      </div>
    </div>

    <!-- 主表格 — 两级表头 -->
    <el-table :data="rows" border stripe class="checklist-table" :highlight-current-row="true">
      <el-table-column label="序号" width="50" align="center" fixed>
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="客户名称" min-width="110">
        <template #default="{ row }"><el-input v-model="row.customerName" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'customerName', row.customerName)" /></template>
      </el-table-column>
      <el-table-column label="选取原因" min-width="100">
        <template #default="{ row }"><el-input v-model="row.reason" size="small" :disabled="isReadonly" placeholder="如：新增主要客户" @change="updateCell(row.rowId, 'reason', row.reason)" /></template>
      </el-table-column>
      <el-table-column label="销售金额" min-width="100" align="right">
        <template #default="{ row }"><WpAmountInput v-model="row.salesAmount" size="small" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'salesAmount', row.salesAmount)" /></template>
      </el-table-column>
      <el-table-column label="占总交易比重" min-width="80" align="right">
        <template #default="{ row }"><span class="derived-value">{{ fmtPercent(row.salesRatio) }}</span></template>
      </el-table-column>
      <el-table-column label="应收账款期末余额" min-width="110" align="right">
        <template #default="{ row }"><WpAmountInput v-model="row.arBalance" size="small" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'arBalance', row.arBalance)" /></template>
      </el-table-column>
      <el-table-column label="占期末余额比重" min-width="80" align="right">
        <template #default="{ row }"><span class="derived-value">{{ fmtPercent(row.arRatio) }}</span></template>
      </el-table-column>
      <el-table-column label="合同负债期末余额" min-width="110" align="right">
        <template #default="{ row }"><WpAmountInput v-model="row.contractLiability" size="small" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'contractLiability', row.contractLiability)" /></template>
      </el-table-column>
      <el-table-column label="占期末余额比重" min-width="80" align="right">
        <template #default="{ row }"><span class="derived-value">{{ fmtPercent(row.clRatio) }}</span></template>
      </el-table-column>
      <!-- 🔴 两级表头：父组「核查方式（√）」跨 5 列 checkbox -->
      <el-table-column label="核查方式（√）" align="center" class-name="col-check-group">
        <el-table-column label="工商资料查询" width="55" align="center">
          <template #default="{ row }"><el-checkbox :model-value="!!row.checkBiz" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'checkBiz', v)" /></template>
        </el-table-column>
        <el-table-column label="互联网信息查询" width="60" align="center">
          <template #default="{ row }"><el-checkbox :model-value="!!row.checkInternet" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'checkInternet', v)" /></template>
        </el-table-column>
        <el-table-column label="函证" width="45" align="center">
          <template #default="{ row }"><el-checkbox :model-value="!!row.checkConfirm" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'checkConfirm', v)" /></template>
        </el-table-column>
        <el-table-column label="视频电话访谈" width="60" align="center">
          <template #default="{ row }"><el-checkbox :model-value="!!row.checkCall" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'checkCall', v)" /></template>
        </el-table-column>
        <el-table-column label="实地走访" width="55" align="center">
          <template #default="{ row }"><el-checkbox :model-value="!!row.checkVisit" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'checkVisit', v)" /></template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="索引号" width="70">
        <template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'indexRef', row.indexRef)" /></template>
      </el-table-column>
      <el-table-column label="操作" width="55" fixed="right" align="center">
        <template #default="{ row }">
          <el-popconfirm title="确认删除?" @confirm="removeRow(row.rowId)">
            <template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="handleAddRow"><el-icon :size="14"><Plus /></el-icon> 添加客户</el-button></div>

    <el-card class="audit-opinion-card" shadow="never">
      <template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template>
      <div class="opinion-body">
        <div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录核查发现的异常情况" @input="(v:string)=>updateAuditNote(v)" /></div>
        <div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断客户交易真实性" @input="(v:string)=>updateAuditConclusion(v)" /></div>
      </div>
    </el-card>
  </template>
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" :sheet-name="spec.sheetName" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-customer-checklist { padding: 16px 20px; font-size: var(--wp-font-size, 13px) }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px }
.toolbar-left { display: flex; align-items: center }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap }
.sync-banner { padding: 6px 12px; border-radius: 4px; font-size: 12px; margin-bottom: 12px }
.sync-ok { background: #f0f9eb; color: #67c23a; border: 1px solid #e1f3d8 }
.sync-fail { background: #fef0f0; color: #f56c6c; border: 1px solid #fde2e2 }
.stats-dashboard { display: flex; gap: 12px; margin-bottom: 20px; padding: 14px 18px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed }
.stat-card { padding: 10px 16px; min-width: 100px; border-radius: 8px; background: #fff; border: 1px solid #ebeef5; box-shadow: 0 1px 3px rgba(0,0,0,.04) }
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08) }
.stat-card.stat-primary { border-left: 3px solid #409eff }
.stat-card.stat-ok { border-left: 3px solid #67c23a }
.stat-value { font-size: 18px; font-weight: 700; color: #303133; font-variant-numeric: tabular-nums }
.stat-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 2px }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px }
.methodology-strip { margin-bottom: 16px; padding: 10px 14px; background: #fffbf0; border-radius: 6px; border: 1px solid #faecd8; border-left: 3px solid #e6a23c }
.methodology-strip .methodology-content { font-size: 12px; color: #606266; line-height: 1.8 }
.methodology-strip .methodology-content p { margin: 2px 0 }
.checklist-table { font-size: var(--wp-font-size, 13px) }
.checklist-table :deep(.el-table__cell) { padding: 5px 3px }
.checklist-table :deep(.col-check-group .el-table__cell) { background-color: #f0f9eb !important }
.derived-value { color: #409eff; font-variant-numeric: tabular-nums }
.add-row-bar { margin: 12px 0 24px; text-align: center }
.audit-opinion-card { margin-bottom: 20px }
.opinion-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133 }
.opinion-actions { margin-left: auto; display: flex; gap: 8px }
.opinion-body { display: flex; flex-direction: column; gap: 14px }
.opinion-field label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; font-weight: 500 }
.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden }
</style>
