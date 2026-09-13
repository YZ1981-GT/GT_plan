<script setup lang="ts">
/**
 * D4TabUndisclosedRp — D4-27 识别未披露的关联方
 *
 * 18 列，单级表头。10 个身份属性列为 el-checkbox，总计列表内计算 = SUM(10列)。
 * 🔴 源模板示例行（陈XX/李YY）只作展示参考，不作默认种子。
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
  SHEET_SPECS,
  getDerivedColumns,
  getCheckboxColumns,
  getAddRowPromptTitle,
  getAddRowInputLabel,
  createEmptyRow,
  type RowRecord,
} from './ipoChecklistSchema'
import {
  recalcAllDerived,
  type ManualOverrides,
} from './ipoChecklistFormulaEngine'

const SHEET_CODE = 'D4-27' as const
const spec = SHEET_SPECS[SHEET_CODE]
const derivedKeys = getDerivedColumns(SHEET_CODE)
const checkboxKeys = getCheckboxColumns(SHEET_CODE)

const props = defineProps<{
  wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean
}>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const rows = ref<RowRecord[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
const manualOverrides = ref<ManualOverrides>(new Map())
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const ROWS_KEY = `${SHEET_CODE}-rows`
const NOTE_KEY = `${SHEET_CODE}-note`
const CONCLUSION_KEY = `${SHEET_CODE}-conclusion`

function loadData() {
  const r = props.allResponses.get(ROWS_KEY)
  if (r?.remark) {
    try { const p = JSON.parse(r.remark); if (Array.isArray(p)) { rows.value = p; doRecalc(); return } } catch {}
  }
  rows.value = []
}
function loadNote() {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
}
watch(() => props.allResponses.get(ROWS_KEY)?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get(NOTE_KEY)?.remark, loadNote, { immediate: true })

function doRecalc() {
  const errors = recalcAllDerived(SHEET_CODE, rows.value, manualOverrides.value)
  if (errors.length > 0) console.warn('[D4-27] 公式求值错误:', errors)
}

async function handleAddRow() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt(
      getAddRowInputLabel(SHEET_CODE), getAddRowPromptTitle(SHEET_CODE),
      { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' }
    )
    if (value?.trim()) { rows.value.push(createEmptyRow(SHEET_CODE, value.trim())); doRecalc(); persistAll() }
  } catch {}
}
function removeRow(rowId: string) { if (props.isReadonly) return; rows.value = rows.value.filter(r => r.rowId !== rowId); doRecalc(); persistAll() }

function updateCell(rowId: string, key: string, value: unknown) {
  if (props.isReadonly) return
  const row = rows.value.find(r => r.rowId === rowId)
  if (!row) return
  row[key] = value
  doRecalc()
  persistAll()
}

function toggleCheckbox(rowId: string, key: string, val: boolean) {
  if (props.isReadonly) return
  const row = rows.value.find(r => r.rowId === rowId)
  if (!row) return
  row[key] = val
  doRecalc()
  persistAll()
}

function persistAll() {
  props.allResponses.set(ROWS_KEY, { item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value })
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    const keys = [ROWS_KEY, NOTE_KEY, CONCLUSION_KEY]
    window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } }))
  }, 2000)
}
function flushPendingSave() {
  if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; const keys = [ROWS_KEY, NOTE_KEY, CONCLUSION_KEY]; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { flushPendingSave() })

const editorMode = ref<string>('表格视图')
const modeOptions = ['表格视图', '在线编辑']
const syncState = ref<{ ok: boolean; message: string } | null>(null)
watch(editorMode, async (newMode, oldMode) => {
  if (newMode === oldMode) return; syncState.value = null
  if (newMode === '在线编辑') { flushPendingSave() }
  else if (newMode === '表格视图') { await nextTick(); loadData() }
})

// AI
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于识别未披露关联方(D4-27)结果生成审计说明', rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于关联方识别结果生成审计结论', noteText: auditNote.value, rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

// 导入导出
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function handleExportTemplate() { exportTemplate(SHEET_CODE) }
function handleExportData() { exportData(SHEET_CODE) }
async function handleImportFile(f: any) { await importData(SHEET_CODE, f.raw || f); editorMode.value = '表格视图'; await nextTick(); loadData() }

function fmtAmt(v: unknown): string { if (v === null || v === undefined || v === '') return ''; const n = Number(v); if (!Number.isFinite(n)) return String(v); return displayPrefs.fmtAmount(n) }
</script>

<template>
<div class="d4-undisclosed-rp">
  <div class="toolbar">
    <div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div>
    <div class="toolbar-right">
      <el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item><el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown>
      <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
      <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-27-rp')">💬 复核</el-button>
    </div>
  </div>
  <div v-if="syncState" :class="['sync-banner', syncState.ok ? 'sync-ok' : 'sync-fail']">{{ syncState.message }}</div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 编制说明 -->
    <div class="methodology-strip">
      <div class="methodology-content">
        <p>取得公司管理层提供的工商登记信息中登记的股东、董事、监事、高级管理人员名单。</p>
        <p>取得公司客户清单（含自然人客户及法人客户的工商登记信息中股东、法人），核对姓名是否存在重名。</p>
        <p>如存在重名，进一步核实是否为同一人，并判断是否构成关联方关系。</p>
        <p>对于识别出的未披露关联方，应评估其对财务报表的影响及信息披露的充分性。</p>
        <p>将与公司人员重名的客户标记为Y，并记录其身份（公司股东/高管/亲属/员工）。</p>
        <p>审计人员需关注年度销售额较大或交易频繁的重名客户。</p>
      </div>
    </div>

    <el-table :data="rows" border stripe class="rp-table" :highlight-current-row="true">
      <el-table-column label="序号" width="50" align="center" fixed>
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="姓名" min-width="90">
        <template #default="{ row }">
          <el-input v-model="row.personName" size="small" :disabled="isReadonly"
            @change="updateCell(row.rowId, 'personName', row.personName)" />
        </template>
      </el-table-column>
      <!-- 10 个身份属性 checkbox 列 -->
      <el-table-column label="个人客户" width="55" align="center">
        <template #default="{ row }"><el-checkbox :model-value="!!row.personalCustomer" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'personalCustomer', v)" /></template>
      </el-table-column>
      <el-table-column label="客户法人" width="55" align="center">
        <template #default="{ row }"><el-checkbox :model-value="!!row.customerLegalPerson" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'customerLegalPerson', v)" /></template>
      </el-table-column>
      <el-table-column label="合同签订人" width="60" align="center">
        <template #default="{ row }"><el-checkbox :model-value="!!row.contractSignee" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'contractSignee', v)" /></template>
      </el-table-column>
      <el-table-column label="高管亲属" width="55" align="center">
        <template #default="{ row }"><el-checkbox :model-value="!!row.executiveRelative" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'executiveRelative', v)" /></template>
      </el-table-column>
      <el-table-column label="财务部门" width="55" align="center">
        <template #default="{ row }"><el-checkbox :model-value="!!row.financeDept" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'financeDept', v)" /></template>
      </el-table-column>
      <el-table-column label="管理部门" width="55" align="center">
        <template #default="{ row }"><el-checkbox :model-value="!!row.managementDept" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'managementDept', v)" /></template>
      </el-table-column>
      <el-table-column label="技术部门" width="55" align="center">
        <template #default="{ row }"><el-checkbox :model-value="!!row.techDept" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'techDept', v)" /></template>
      </el-table-column>
      <el-table-column label="生产部门" width="55" align="center">
        <template #default="{ row }"><el-checkbox :model-value="!!row.productionDept" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'productionDept', v)" /></template>
      </el-table-column>
      <el-table-column label="营销部门" width="55" align="center">
        <template #default="{ row }"><el-checkbox :model-value="!!row.salesDept" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'salesDept', v)" /></template>
      </el-table-column>
      <el-table-column label="其他" width="45" align="center">
        <template #default="{ row }"><el-checkbox :model-value="!!row.otherDept" :disabled="isReadonly" @change="(v: boolean) => toggleCheckbox(row.rowId, 'otherDept', v)" /></template>
      </el-table-column>
      <!-- 总计（派生列，只读） -->
      <el-table-column label="总计" width="50" align="center">
        <template #default="{ row }"><span class="derived-value">{{ row.total ?? '' }}</span></template>
      </el-table-column>
      <el-table-column label="重名(Y/N)" width="65" align="center">
        <template #default="{ row }">
          <el-select v-model="row.isMatch" size="small" :disabled="isReadonly" placeholder="--"
            @change="updateCell(row.rowId, 'isMatch', row.isMatch)">
            <el-option label="Y" value="Y" /><el-option label="N" value="N" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="公司股东/高管/亲属/员工" min-width="110">
        <template #default="{ row }">
          <el-input v-model="row.identity" size="small" :disabled="isReadonly"
            @change="updateCell(row.rowId, 'identity', row.identity)" />
        </template>
      </el-table-column>
      <el-table-column label="年度销售额" min-width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput v-model="row.annualSales" size="small" :disabled="isReadonly" style="width:100%"
            @change="updateCell(row.rowId, 'annualSales', row.annualSales)" />
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.note" size="small" :disabled="isReadonly"
            @change="updateCell(row.rowId, 'note', row.note)" />
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="70">
        <template #default="{ row }">
          <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
            @change="updateCell(row.rowId, 'indexRef', row.indexRef)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55" fixed="right" align="center">
        <template #default="{ row }">
          <el-popconfirm title="确认删除?" @confirm="removeRow(row.rowId)">
            <template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="handleAddRow"><el-icon :size="14"><Plus /></el-icon> 添加人员</el-button></div>

    <el-card class="audit-opinion-card" shadow="never">
      <template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template>
      <div class="opinion-body">
        <div class="opinion-field"><label>审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录识别未披露关联方的过程和发现" @input="(v:string)=>updateAuditNote(v)" /></div>
        <div class="opinion-field"><label>审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断是否存在未披露的关联方交易" @input="(v:string)=>updateAuditConclusion(v)" /></div>
      </div>
    </el-card>
  </template>
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" :sheet-name="spec.sheetName" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-undisclosed-rp { padding: 16px 20px; font-size: var(--wp-font-size, 13px) }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px }
.toolbar-left { display: flex; align-items: center }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap }
.sync-banner { padding: 6px 12px; border-radius: 4px; font-size: 12px; margin-bottom: 12px }
.sync-ok { background: #f0f9eb; color: #67c23a; border: 1px solid #e1f3d8 }
.sync-fail { background: #fef0f0; color: #f56c6c; border: 1px solid #fde2e2 }
.methodology-strip { margin-bottom: 16px; padding: 10px 14px; background: #fffbf0; border-radius: 6px; border: 1px solid #faecd8; border-left: 3px solid #e6a23c }
.methodology-strip .methodology-content { font-size: 12px; color: #606266; line-height: 1.8 }
.methodology-strip .methodology-content p { margin: 2px 0 }
.rp-table { font-size: var(--wp-font-size, 13px) }
.rp-table :deep(.el-table__cell) { padding: 5px 3px }
.derived-value { color: #409eff; font-weight: 600; font-variant-numeric: tabular-nums }
.add-row-bar { margin: 12px 0 24px; text-align: center }
.audit-opinion-card { margin-bottom: 20px }
.opinion-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133 }
.opinion-actions { margin-left: auto; display: flex; gap: 8px }
.opinion-body { display: flex; flex-direction: column; gap: 14px }
.opinion-field label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; font-weight: 500 }
.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden }
</style>
