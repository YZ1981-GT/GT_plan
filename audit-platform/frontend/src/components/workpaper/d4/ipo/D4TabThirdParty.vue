<script setup lang="ts">
/**
 * D4TabThirdParty — D4-24 第三方回款检查
 *
 * 动态行检查表：每行一笔第三方回款记录
 * 13列对齐源模板：序号/客户/销售额/应收余额/回款金额/回款方/原因/与客户关系/与被审计单位关系/代付协议/函证/合理性分析/索引
 * 双模式 + AI辅助 + 导入导出
 */
import { ref, computed, inject, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'

// ─── Props ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── Types ───────────────────────────────────────────────────────────
interface ThirdPartyRow {
  id: string
  customerName: string
  salesAmount: number | string
  arBalance: number | string
  thirdPartyAmount: number | string
  thirdPartyName: string
  reason: string
  relationToCustomer: string
  relationToAuditee: string
  hasAgreement: string  // 是/否
  hasConfirmation: string  // 是/否
  analysis: string
  indexRef: string
}

// ─── State ───────────────────────────────────────────────────────────
const rows = ref<ThirdPartyRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function createRow(): ThirdPartyRow {
  return {
    id: `tp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    customerName: '', salesAmount: '', arBalance: '', thirdPartyAmount: '',
    thirdPartyName: '', reason: '', relationToCustomer: '', relationToAuditee: '',
    hasAgreement: '', hasConfirmation: '', analysis: '', indexRef: '',
  }
}

// ─── Load ────────────────────────────────────────────────────────────
function loadData() {
  const resp = props.allResponses.get('D4-24-rows')
  if (resp?.remark) {
    try { const p = JSON.parse(resp.remark); if (Array.isArray(p)) { rows.value = p; return } } catch {}
  }
  rows.value = []
}
function loadNote() {
  auditNote.value = props.allResponses.get('D4-24-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D4-24-conclusion')?.remark || ''
}
watch(() => props.allResponses.get('D4-24-rows')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-24-note')?.remark, loadNote, { immediate: true })

// ─── CRUD ────────────────────────────────────────────────────────────
async function handleAddRow() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入客户名称', '添加第三方回款记录', {
      confirmButtonText: '确认', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '客户名称不能为空',
    })
    if (value?.trim()) {
      const row = createRow()
      row.customerName = value.trim()
      rows.value.push(row)
      persistAll()
    }
  } catch {}
}
function removeRow(id: string) {
  if (props.isReadonly) return
  rows.value = rows.value.filter(r => r.id !== id)
  persistAll()
}
function updateCell(id: string, field: keyof ThirdPartyRow, value: any) {
  if (props.isReadonly) return
  const row = rows.value.find(r => r.id === id)
  if (row) { (row as any)[field] = value; persistAll() }
}

// ─── Persistence ─────────────────────────────────────────────────────
function persistAll() {
  props.allResponses.set('D4-24-rows', { item_id: 'D4-24-rows', conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set('D4-24-note', { item_id: 'D4-24-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-24-conclusion', { item_id: 'D4-24-conclusion', conclusion: null, remark: auditConclusion.value })
  debounceSave()
}
function debounceSave() { if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000) }
function flushSave() {
  const keys = ['D4-24-rows', 'D4-24-note', 'D4-24-conclusion']
  const items = keys.map(k => props.allResponses.get(k)).filter(Boolean)
  window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

// ─── Mode / AI ───────────────────────────────────────────────────────
const editorMode = ref<string>('表格视图')
const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); const s = r.data?.data?.status ?? r.data?.status; aiAvailable.value = s === 'healthy' || s === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)
async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value || '', relatedContext: { task: '基于第三方回款检查(D4-24)结果生成审计说明', rowCount: rows.value.length, totalAmount: rows.value.reduce((s, r) => s + (parseFloat(String(r.thirdPartyAmount)) || 0), 0) } }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditNote(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiNoteLoading.value = false }
}
async function genConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiConclusionLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value || '', relatedContext: { task: '基于第三方回款检查结果生成审计结论', noteText: auditNote.value || '', rowCount: rows.value.length } }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiConclusionLoading.value = false }
}

// ─── Import/Export ───────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function handleExportTemplate() { exportTemplate('D4-24') }
function handleExportData() { exportData('D4-24') }
async function handleImportFile(uploadFile: any) { await importData('D4-24', uploadFile.raw || uploadFile) }

// ─── Stats ───────────────────────────────────────────────────────────
const totalThirdPartyAmount = computed(() => rows.value.reduce((s, r) => s + (parseFloat(String(r.thirdPartyAmount)) || 0), 0))
const noAgreementCount = computed(() => rows.value.filter(r => r.hasAgreement === '否').length)

function fmtAmount(v: number): string { return v ? v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—' }
</script>

<template>
  <div class="d4-third-party">
    <!-- 工具条 -->
    <div class="toolbar">
      <div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div>
      <div class="toolbar-right">
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown><el-dropdown-menu>
            <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
            <el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly || importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item>
          </el-dropdown-menu></template>
        </el-dropdown>
        <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:D2-7" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-24-thirdparty')">💬 复核</el-button>
      </div>
    </div>

    <!-- 仪表板 -->
    <div class="stats-dashboard">
      <div class="stat-card stat-primary"><div class="stat-value">{{ rows.length }}<span class="stat-unit">笔</span></div><div class="stat-label">第三方回款</div></div>
      <div class="stat-card stat-amount"><div class="stat-value">{{ fmtAmount(totalThirdPartyAmount) }}</div><div class="stat-label">回款总额</div></div>
      <div class="stat-card" :class="noAgreementCount > 0 ? 'stat-warn' : 'stat-ok'"><div class="stat-value">{{ noAgreementCount }}<span class="stat-unit">笔</span></div><div class="stat-label">无代付协议</div></div>
    </div>

    <template v-if="editorMode !== '在线编辑'">
      <!-- 引导条 -->
      <div class="guide-strip">
        <span class="guide-strip-label">编制流程：</span>
        <el-tooltip content="了解第三方回款原因，获取代付协议" placement="bottom" :show-after="300"><span class="guide-chip">①获取协议</span></el-tooltip><span class="guide-arrow">→</span>
        <el-tooltip content="向第三方回款单位函证确认" placement="bottom" :show-after="300"><span class="guide-chip">②函证确认</span></el-tooltip><span class="guide-arrow">→</span>
        <el-tooltip content="关注资金流、实物流与合同约定是否一致" placement="bottom" :show-after="300"><span class="guide-chip">③核查一致性</span></el-tooltip><span class="guide-arrow">→</span>
        <el-tooltip content="核查是否存在关联关系或利益安排" placement="bottom" :show-after="300"><span class="guide-chip">④关联方核查</span></el-tooltip><span class="guide-arrow">→</span>
        <el-tooltip content="对异常回款追查期后资金流向" placement="bottom" :show-after="300"><span class="guide-chip">⑤追查资金流</span></el-tooltip>
      </div>

      <!-- 主表格 -->
      <el-table :data="rows" border stripe class="tp-table">
        <el-table-column label="序号" width="55" align="center" fixed><template #default="{ $index }">{{ $index + 1 }}</template></el-table-column>
        <el-table-column label="客户名称" min-width="120"><template #default="{ row }"><el-input v-model="row.customerName" size="small" :disabled="isReadonly" @change="updateCell(row.id, 'customerName', row.customerName)" /></template></el-table-column>
        <el-table-column label="本年度销售金额" min-width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.salesAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id, 'salesAmount', row.salesAmount)" /></template></el-table-column>
        <el-table-column label="期末应收余额" min-width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.arBalance" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id, 'arBalance', row.arBalance)" /></template></el-table-column>
        <el-table-column label="第三方回款金额" min-width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.thirdPartyAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id, 'thirdPartyAmount', row.thirdPartyAmount)" /></template></el-table-column>
        <el-table-column label="回款方名称" min-width="120"><template #default="{ row }"><el-input v-model="row.thirdPartyName" size="small" :disabled="isReadonly" @change="updateCell(row.id, 'thirdPartyName', row.thirdPartyName)" /></template></el-table-column>
        <el-table-column label="回款原因" min-width="110"><template #default="{ row }"><el-input v-model="row.reason" size="small" :disabled="isReadonly" @change="updateCell(row.id, 'reason', row.reason)" /></template></el-table-column>
        <el-table-column label="与客户关系" min-width="100"><template #default="{ row }"><el-input v-model="row.relationToCustomer" size="small" :disabled="isReadonly" @change="updateCell(row.id, 'relationToCustomer', row.relationToCustomer)" /></template></el-table-column>
        <el-table-column label="与被审计单位关系" min-width="110"><template #default="{ row }"><el-input v-model="row.relationToAuditee" size="small" :disabled="isReadonly" @change="updateCell(row.id, 'relationToAuditee', row.relationToAuditee)" /></template></el-table-column>
        <el-table-column label="代付协议" width="80" align="center"><template #default="{ row }"><el-select v-model="row.hasAgreement" size="small" :disabled="isReadonly" placeholder="—" @change="updateCell(row.id, 'hasAgreement', row.hasAgreement)"><el-option label="是" value="是" /><el-option label="否" value="否" /></el-select></template></el-table-column>
        <el-table-column label="函证" width="70" align="center"><template #default="{ row }"><el-select v-model="row.hasConfirmation" size="small" :disabled="isReadonly" placeholder="—" @change="updateCell(row.id, 'hasConfirmation', row.hasConfirmation)"><el-option label="是" value="是" /><el-option label="否" value="否" /></el-select></template></el-table-column>
        <el-table-column label="合理性分析" min-width="140"><template #default="{ row }"><el-input v-model="row.analysis" size="small" :disabled="isReadonly" placeholder="分析回款合理性" @change="updateCell(row.id, 'analysis', row.analysis)" /></template></el-table-column>
        <el-table-column label="索引" width="80"><template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateCell(row.id, 'indexRef', row.indexRef)" /></template></el-table-column>
        <el-table-column label="操作" width="60" fixed="right" align="center"><template #default="{ row }"><el-popconfirm title="确认删除？" @confirm="removeRow(row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template></el-popconfirm></template></el-table-column>
      </el-table>

      <div class="add-row-bar"><el-button :disabled="isReadonly" @click="handleAddRow"><el-icon :size="14"><Plus /></el-icon> 添加记录</el-button></div>

      <!-- 审计意见区 -->
      <el-card class="audit-opinion-card" shadow="never">
        <template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-chips"><GtIndexChip value="wp:E1-31" :context-project-id="projectId" /><GtIndexChip value="wp:D2-7" :context-project-id="projectId" /></div><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly || !aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly || !aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template>
        <div class="opinion-body">
          <div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" :model-value="auditNote" :disabled="isReadonly" placeholder="说明第三方回款检查结果，包括回款原因合理性、代付协议完备性、函证结果、关联关系核查情况等" @input="(v: string) => updateAuditNote(v)" /></div>
          <div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断第三方回款是否具有合理商业实质，是否存在资金回流或虚假销售的迹象" @input="(v: string) => updateAuditConclusion(v)" /></div>
        </div>
      </el-card>

      <details class="tips-collapse"><summary class="tips-summary">📋 编制提示</summary><ol class="tips-list">
        <li>向管理层了解第三方回款原因，获取代付协议。</li>
        <li>向第三方回款单位函证（参见E1-31银行流水双向核对表）。</li>
        <li>关注资金流、实物流与合同约定及商业实质是否一致。</li>
        <li>核查被审计单位及其实控人/董监高与第三方回款方是否存在关联关系。</li>
        <li>对异常的第三方回款追查期后资金流向。</li>
      </ol></details>
    </template>

    <template v-if="editorMode === '在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="第三方回款检查D4-24" :readonly="isReadonly" /></div></template>
  </div>
</template>

<style scoped>
.d4-third-party { padding: 16px 20px; font-size: 13px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.stats-dashboard { display: flex; gap: 12px; margin-bottom: 20px; padding: 14px 18px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed; }
.stat-card { padding: 10px 16px; min-width: 110px; border-radius: 8px; background: #fff; border: 1px solid #ebeef5; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.stat-card.stat-primary { border-left: 3px solid #409eff; }
.stat-card.stat-amount { border-left: 3px solid #e6a23c; }
.stat-card.stat-warn { border-left: 3px solid #f56c6c; }
.stat-card.stat-ok { border-left: 3px solid #67c23a; }
.stat-value { font-size: 18px; font-weight: 700; color: #303133; font-variant-numeric: tabular-nums; }
.stat-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }
.guide-strip { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; padding: 10px 14px; background: #f0f9eb; border-radius: 6px; border: 1px solid #e1f3d8; }
.guide-strip-label { font-weight: 600; color: #67c23a; font-size: 12px; }
.guide-chip { background: #fff; border: 1px solid #c2e7b0; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: #529b2e; cursor: help; }
.guide-chip:hover { background: #f0f9eb; }
.guide-arrow { color: #a8abb2; font-size: 12px; }
.tp-table { font-size: 13px; }
.tp-table :deep(.el-table__cell) { padding: 5px 4px; }
.add-row-bar { margin: 12px 0 24px; text-align: center; }
.audit-opinion-card { margin-bottom: 20px; }
.opinion-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-actions { margin-left: auto; display: flex; gap: 8px; }
.opinion-body { display: flex; flex-direction: column; gap: 14px; }
.opinion-field label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; font-weight: 500; }
.tips-collapse { margin-bottom: 16px; border-radius: 6px; border: 1px solid #fde2e2; border-left: 3px solid #f56c6c; }
.tips-summary { cursor: pointer; padding: 8px 14px; font-size: 13px; font-weight: 500; color: #f56c6c; }
.tips-list { margin: 8px 14px 12px; padding-left: 18px; font-size: 12px; color: #606266; line-height: 2; }
.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }
</style>
