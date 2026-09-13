<script setup lang="ts">
/**
 * D4TabOverseas — D4-26 境外销售收入检查
 *
 * 19 列（14 主列 + 5 二级列），两级表头。
 * 父组「核查程序执行情况」跨 5 列 checkbox。
 * 🔴 不得压扁成平铺列；守卫断言 DOM 父组跨列数 = 5。
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

const SHEET_CODE = 'D4-26' as const
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

function doRecalc() { const errors = recalcAllDerived(SHEET_CODE, rows.value, manualOverrides.value); if (errors.length > 0) console.warn('[D4-26] 公式求值错误:', errors) }

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
  } else {
    row[key] = value; doRecalc()
  }
  persistAll()
}

function toggleCheckbox(rowId: string, key: string, val: boolean) {
  if (props.isReadonly) return
  const row = rows.value.find(r => r.rowId === rowId)
  if (!row) return
  row[key] = val; persistAll()
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
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于境外销售收入检查(D4-26)结果生成审计说明', rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于境外销售检查结果生成审计结论', noteText: auditNote.value, rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function handleExportTemplate() { exportTemplate(SHEET_CODE) }
function handleExportData() { exportData(SHEET_CODE) }
async function handleImportFile(f: any) { await importData(SHEET_CODE, f.raw || f); editorMode.value = '表格视图'; await nextTick(); loadData() }

function fmtPercent(v: unknown): string { if (v === null || v === undefined || v === '') return ''; const n = Number(v); if (!Number.isFinite(n)) return ''; return (n * 100).toFixed(2) + '%' }
function fmtAmt(v: unknown): string { if (v === null || v === undefined || v === '') return ''; const n = Number(v); if (!Number.isFinite(n)) return String(v); return displayPrefs.fmtAmount(n) }
</script>

<template>
<div class="d4-overseas">
  <div class="toolbar">
    <div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div>
    <div class="toolbar-right">
      <el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item><el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown>
      <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
      <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-26-overseas')">💬 复核</el-button>
    </div>
  </div>
  <div v-if="syncState" :class="['sync-banner', syncState.ok ? 'sync-ok' : 'sync-fail']">{{ syncState.message }}</div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 编制说明 -->
    <div class="methodology-strip">
      <div class="methodology-content">
        <p>了解被审计单位的境外销售情况，包括销售对象、目的国、产品种类、业务模式、贸易模式和结算方式等。</p>
        <p>关注是否存在第三方回款情况及其原因，评估收入确认的合规性。</p>
        <p>针对主要境外客户执行核查程序：实地走访、交易函证、海关函证、核对报关单、电子口岸数据查询。</p>
        <p>比较核查程序确认的销售金额与账面金额，分析差异原因。</p>
      </div>
    </div>

    <!-- 主表格 — 两级表头 -->
    <el-table :data="rows" border stripe class="overseas-table" :highlight-current-row="true">
      <el-table-column label="客户名称" min-width="110" fixed>
        <template #default="{ row }"><el-input v-model="row.customerName" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'customerName', row.customerName)" /></template>
      </el-table-column>
      <el-table-column label="所在国家/地区" min-width="100">
        <template #default="{ row }"><el-input v-model="row.country" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'country', row.country)" /></template>
      </el-table-column>
      <el-table-column label="产品种类" min-width="100">
        <template #default="{ row }"><el-input v-model="row.productType" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'productType', row.productType)" /></template>
      </el-table-column>
      <el-table-column label="业务模式" min-width="90">
        <template #default="{ row }">
          <el-select v-model="row.bizModel" size="small" :disabled="isReadonly" placeholder="--" @change="updateCell(row.rowId, 'bizModel', row.bizModel)">
            <el-option label="直销客户" value="直销客户" /><el-option label="经销商" value="经销商" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="本期销售金额" min-width="120" align="right">
        <template #default="{ row }"><WpAmountInput v-model="row.salesAmount" size="small" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'salesAmount', row.salesAmount)" /></template>
      </el-table-column>
      <el-table-column label="占同类交易比例" min-width="100" align="right">
        <template #default="{ row }"><span class="derived-value">{{ fmtPercent(row.salesRatio) }}</span></template>
      </el-table-column>
      <el-table-column label="贸易模式" min-width="80">
        <template #default="{ row }">
          <el-select v-model="row.tradeMode" size="small" :disabled="isReadonly" placeholder="--" @change="updateCell(row.rowId, 'tradeMode', row.tradeMode)">
            <el-option label="EXW" value="EXW" /><el-option label="FOB" value="FOB" /><el-option label="CIF" value="CIF" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="主要贸易条款" min-width="110">
        <template #default="{ row }"><el-input v-model="row.tradeTerms" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'tradeTerms', row.tradeTerms)" /></template>
      </el-table-column>
      <el-table-column label="出口结算模式" min-width="100">
        <template #default="{ row }">
          <el-select v-model="row.settlementMode" size="small" :disabled="isReadonly" placeholder="--" @change="updateCell(row.rowId, 'settlementMode', row.settlementMode)">
            <el-option label="汇款" value="汇款" /><el-option label="托收" value="托收" /><el-option label="信用证" value="信用证" /><el-option label="银行保函" value="银行保函" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="是否存在第三方回款" min-width="100">
        <template #default="{ row }">
          <el-select v-model="row.hasThirdParty" size="small" :disabled="isReadonly" placeholder="--" @change="updateCell(row.rowId, 'hasThirdParty', row.hasThirdParty)">
            <el-option label="是" value="是" /><el-option label="否" value="否" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="第三方回款原因" min-width="110">
        <template #default="{ row }"><el-input v-model="row.thirdPartyReason" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'thirdPartyReason', row.thirdPartyReason)" /></template>
      </el-table-column>
      <el-table-column label="核查程序确认的销售金额" min-width="130" align="right">
        <template #default="{ row }"><WpAmountInput v-model="row.verifiedAmount" size="small" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'verifiedAmount', row.verifiedAmount)" /></template>
      </el-table-column>
      <el-table-column label="差异" min-width="100" align="right">
        <template #default="{ row }"><span class="derived-value">{{ fmtAmt(row.diff) }}</span></template>
      </el-table-column>
      <el-table-column label="差异原因分析" min-width="110">
        <template #default="{ row }"><el-input v-model="row.diffReason" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'diffReason', row.diffReason)" /></template>
      </el-table-column>
      <!-- 🔴 两级表头：父组「核查程序执行情况」跨 5 列 checkbox -->
      <el-table-column label="核查程序执行情况" align="center" class-name="col-check-group">
        <el-table-column label="实地走访" width="60" align="center">
          <template #default="{ row }"><el-checkbox :model-value="!!row.fieldVisit" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'fieldVisit', v)" /></template>
        </el-table-column>
        <el-table-column label="交易函证" width="60" align="center">
          <template #default="{ row }"><el-checkbox :model-value="!!row.tradeConfirm" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'tradeConfirm', v)" /></template>
        </el-table-column>
        <el-table-column label="海关函证" width="60" align="center">
          <template #default="{ row }"><el-checkbox :model-value="!!row.customsConfirm" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'customsConfirm', v)" /></template>
        </el-table-column>
        <el-table-column label="核对报关单" width="70" align="center">
          <template #default="{ row }"><el-checkbox :model-value="!!row.checkDeclaration" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'checkDeclaration', v)" /></template>
        </el-table-column>
        <el-table-column label="电子口岸数据查询" width="80" align="center">
          <template #default="{ row }"><el-checkbox :model-value="!!row.eportQuery" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'eportQuery', v)" /></template>
        </el-table-column>
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
        <div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录发现的差异或异常交易安排" @input="(v:string)=>updateAuditNote(v)" /></div>
        <div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断境外销售收入的真实性" @input="(v:string)=>updateAuditConclusion(v)" /></div>
      </div>
    </el-card>
  </template>
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" :sheet-name="spec.sheetName" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-overseas { padding: 16px 20px; font-size: var(--wp-font-size, 13px) }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px }
.toolbar-left { display: flex; align-items: center }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap }
.sync-banner { padding: 6px 12px; border-radius: 4px; font-size: 12px; margin-bottom: 12px }
.sync-ok { background: #f0f9eb; color: #67c23a; border: 1px solid #e1f3d8 }
.sync-fail { background: #fef0f0; color: #f56c6c; border: 1px solid #fde2e2 }
.methodology-strip { margin-bottom: 16px; padding: 10px 14px; background: #fffbf0; border-radius: 6px; border: 1px solid #faecd8; border-left: 3px solid #e6a23c }
.methodology-strip .methodology-content { font-size: 12px; color: #606266; line-height: 1.8 }
.methodology-strip .methodology-content p { margin: 2px 0 }
.overseas-table { font-size: var(--wp-font-size, 13px) }
.overseas-table :deep(.el-table__cell) { padding: 5px 3px }
.overseas-table :deep(.col-check-group .el-table__cell) { background-color: #f0f9eb !important }
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
