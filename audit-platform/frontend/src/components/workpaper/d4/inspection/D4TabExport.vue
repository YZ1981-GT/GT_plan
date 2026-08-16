<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * D4TabExport — D4-16 出口收入电子口岸系统核对
 *
 * 三分组交叉核对：账面出口收入 × 电子口岸系统 × 免抵退税申报数据
 * 双模式：表格视图 / 在线编辑
 * 支持自动差异计算、AI辅助审计意见
 *
 * 源模板结构：
 * - 账面出口收入金额（期间/结关金额/差异/原因/金额/期间）
 * - 电子口岸系统（申报外营收入/差异/原因/索引）
 * - 免抵退税申报数据（申报外营收入/差异/原因/索引）
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
interface ExportCheckRow {
  id: string
  bookAmount: number        // 账面出口收入金额
  portsAmount: number       // 电子口岸结关金额
  portsDiff: number         // 差异(账面-口岸)
  portsReason: string       // 差异原因
  portsAmount2: number      // 口岸金额(第二列)
  portsPeriod: string       // 期间
  taxReportAmount: number   // 免抵退税申报外营收入
  taxDiff: number           // 差异(账面-申报)
  taxReason: string         // 差异原因
  taxIndex: string          // 索引
}

// ─── State ───────────────────────────────────────────────────────────
const rows = ref<ExportCheckRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// ─── OCR ─────────────────────────────────────────────────────────────
const ocrTargetId = ref('')

async function handleOcrUpload(rowId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData, { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any)
    const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (fields.amount) {
      const row = rows.value.find(r => r.id === rowId)
      if (row) { row.bookAmount = Number(fields.amount) || 0; onCellChange(row) }
      ElMessage.success('OCR金额已填入')
    } else {
      ElMessage.info('OCR完成，未识别到金额字段')
    }
  } catch { ElMessage.warning('OCR识别失败') }
}

// ─── Load ────────────────────────────────────────────────────────────
function loadData() {
  const resp = props.allResponses.get('D4-16-rows')
  if (resp?.remark) {
    try {
      const parsed = JSON.parse(resp.remark)
      if (Array.isArray(parsed) && parsed.length) { rows.value = parsed; return }
    } catch { /* fallback */ }
  }
  rows.value = []
}
function loadNoteConclusion() {
  auditNote.value = props.allResponses.get('D4-16-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D4-16-conclusion')?.remark || ''
}

watch(() => props.allResponses.get('D4-16-rows')?.remark, () => loadData(), { immediate: true })
watch(() => props.allResponses.get('D4-16-note')?.remark, () => loadNoteConclusion(), { immediate: true })

// ─── CRUD ────────────────────────────────────────────────────────────
function addRow() {
  if (props.isReadonly) return
  rows.value.push({
    id: `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    bookAmount: 0, portsAmount: 0, portsDiff: 0, portsReason: '',
    portsAmount2: 0, portsPeriod: '', taxReportAmount: 0, taxDiff: 0, taxReason: '', taxIndex: '',
  })
  persistAll()
}

function removeRow(id: string) {
  if (props.isReadonly) return
  rows.value = rows.value.filter(r => r.id !== id)
  persistAll()
}

function onCellChange(row: ExportCheckRow) {
  // Auto-calc differences
  row.portsDiff = row.bookAmount - row.portsAmount
  row.taxDiff = row.bookAmount - row.taxReportAmount
  persistAll()
}

// ─── Stats ───────────────────────────────────────────────────────────
const totalBook = computed(() => rows.value.reduce((s, r) => s + r.bookAmount, 0))
const totalPortsDiff = computed(() => rows.value.reduce((s, r) => s + r.portsDiff, 0))
const totalTaxDiff = computed(() => rows.value.reduce((s, r) => s + r.taxDiff, 0))
const hasDiff = computed(() => rows.value.some(r => r.portsDiff !== 0 || r.taxDiff !== 0))

// ─── Persistence ─────────────────────────────────────────────────────
function persistAll() {
  props.allResponses.set('D4-16-rows', { item_id: 'D4-16-rows', conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set('D4-16-note', { item_id: 'D4-16-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-16-conclusion', { item_id: 'D4-16-conclusion', conclusion: null, remark: auditConclusion.value })
  debounceSave()
}
function debounceSave() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
}
function flushSave() {
  const keys = ['D4-16-rows', 'D4-16-note', 'D4-16-conclusion']
  const items = keys.map(k => props.allResponses.get(k)).filter(Boolean)
  window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
}
function updateAuditNote(val: string) { if (props.isReadonly) return; auditNote.value = val; persistAll() }
function updateAuditConclusion(val: string) { if (props.isReadonly) return; auditConclusion.value = val; persistAll() }

onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

// ─── Mode / AI / Import-Export ───────────────────────────────────────
const editorMode = ref<string>('表格视图')
const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() {
  try { const res = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (res.data?.data?.status ?? res.data?.status) === 'healthy' }
  catch { aiAvailable.value = false }
}
checkAiHealth()

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: computed(() => props.wpId), projectId: computed(() => props.projectId),
})
function handleExportTemplate() { exportTemplate('D4-16') }
function handleExportData() { exportData('D4-16') }
async function handleImportFile(uploadFile: any) { await importData('D4-16', uploadFile.raw || uploadFile) }

const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)
async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-note', existingContent: auditNote.value, relatedContext: { task: '基于出口收入与电子口岸/免抵退税核对差异，生成审计说明', totalBook: totalBook.value, totalPortsDiff: totalPortsDiff.value, totalTaxDiff: totalTaxDiff.value, rowCount: rows.value.length } }, { _silent: true } as any)
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
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于出口核对结果生成审计结论', noteText: auditNote.value, hasDiff: hasDiff.value, totalPortsDiff: totalPortsDiff.value, totalTaxDiff: totalTaxDiff.value } }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiConclusionLoading.value = false }
}
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

function fmtAmount(v: number): string {
  if (!v) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="d4-export">
    <!-- 工具条 -->
    <div class="toolbar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <div class="toolbar-right">
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly || importing" @change="handleImportFile"><span>导入数据</span></el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-14" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-16-export')">💬 复核</el-button>
      </div>
    </div>

    <!-- 统计 -->
    <div class="stats-dashboard">
      <div class="stat-card stat-primary">
        <div class="stat-value">{{ fmtAmount(totalBook) }}</div>
        <div class="stat-label">账面出口收入合计</div>
      </div>
      <div class="stat-card" :class="{ 'stat-warn': totalPortsDiff !== 0 }">
        <div class="stat-value">{{ fmtAmount(totalPortsDiff) }}</div>
        <div class="stat-label">口岸系统差异合计</div>
      </div>
      <div class="stat-card" :class="{ 'stat-warn': totalTaxDiff !== 0 }">
        <div class="stat-value">{{ fmtAmount(totalTaxDiff) }}</div>
        <div class="stat-label">免抵退税差异合计</div>
      </div>
    </div>

    <template v-if="editorMode !== '在线编辑'">
      <!-- 方法论折叠 -->
      <details class="methodology-collapse">
        <summary class="methodology-summary">📖 审计目标与出口核对过程（点击展开）</summary>
        <div class="methodology-body">
          <p><strong>审计目标：</strong>核实出口收入的真实性和完整性——账面记录与海关电子口岸数据、免抵退税申报数据一致。</p>
          <p><strong>核对过程：</strong>将账面出口收入金额逐期与电子口岸系统结关金额、免抵退税申报的外营收入金额进行比对，分析差异原因。</p>
        </div>
      </details>

      <!-- 引导条 -->
      <div class="guide-strip">
        <span class="guide-strip-label">编制流程：</span>
        <el-tooltip content="按月/季度填入账面出口收入金额" placement="bottom" :show-after="300"><span class="guide-chip">①录入账面金额</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="从电子口岸系统获取对应期间结关金额并填入" placement="bottom" :show-after="300"><span class="guide-chip">②填入口岸数据</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="从免抵退税申报表获取外营收入金额并填入" placement="bottom" :show-after="300"><span class="guide-chip">③填入申报数据</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="系统自动计算差异，对差异项填写原因说明" placement="bottom" :show-after="300"><span class="guide-chip">④核对差异</span></el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="填写审计说明与结论" placement="bottom" :show-after="300"><span class="guide-chip">⑤填审计意见</span></el-tooltip>
      </div>

      <!-- 主表格 -->
      <el-table :data="rows" border stripe class="export-table">
        <el-table-column label="序号" width="55" align="center" fixed>
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>

        <!-- 账面出口收入 -->
        <el-table-column label="账面出口收入金额" align="center" class-name="col-book">
          <el-table-column label="金额" min-width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput v-model="row.bookAmount" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)" />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 电子口岸系统 -->
        <el-table-column label="电子口岸系统" align="center" class-name="col-ports">
          <el-table-column label="期间" min-width="90">
            <template #default="{ row }">
              <el-input v-model="row.portsPeriod" size="small" :disabled="isReadonly" placeholder="如：2025-01" @change="persistAll()" />
            </template>
          </el-table-column>
          <el-table-column label="结关金额" min-width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput v-model="row.portsAmount" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="差异" min-width="110" align="right">
            <template #default="{ row }">
              <span :class="{ 'diff-warn': row.portsDiff !== 0 }">{{ fmtAmount(row.portsDiff) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="原因" min-width="140">
            <template #default="{ row }">
              <el-input v-model="row.portsReason" size="small" :disabled="isReadonly" placeholder="差异原因" @change="persistAll()" />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 免抵退税申报数据 -->
        <el-table-column label="免抵退税申报数据" align="center" class-name="col-tax">
          <el-table-column label="申报外营收入" min-width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput v-model="row.taxReportAmount" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="差异" min-width="110" align="right">
            <template #default="{ row }">
              <span :class="{ 'diff-warn': row.taxDiff !== 0 }">{{ fmtAmount(row.taxDiff) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="原因" min-width="140">
            <template #default="{ row }">
              <el-input v-model="row.taxReason" size="small" :disabled="isReadonly" placeholder="差异原因" @change="persistAll()" />
            </template>
          </el-table-column>
          <el-table-column label="索引" min-width="80">
            <template #default="{ row }">
              <el-input v-model="row.taxIndex" size="small" :disabled="isReadonly" @change="persistAll()" />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 操作 -->
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="{ row }">
            <el-upload :show-file-list="false" :auto-upload="false" :disabled="isReadonly"
              @change="(f: any) => handleOcrUpload(row.id, f.raw || f)" style="display:inline-block;">
              <el-button link size="small" :disabled="isReadonly" title="OCR识别附件">📎</el-button>
            </el-upload>
            <el-popconfirm title="确认删除？" @confirm="removeRow(row.id)">
              <template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div class="add-row-bar">
        <el-button :disabled="isReadonly" @click="addRow"><el-icon :size="16" style="margin-right:4px;"><Plus /></el-icon>添加行</el-button>
      </div>

      <!-- 审计意见区 -->
      <el-card class="audit-opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">审计意见区</span>
            <div class="opinion-actions">
              <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly || !aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip>
              <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly || !aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip>
            </div>
          </div>
        </template>
        <div class="opinion-body">
          <div class="opinion-field"><label>审计说明</label><el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" :model-value="auditNote" :disabled="isReadonly" placeholder="记录核对范围、差异情况、差异原因分析及处理结果" @input="(v: string) => updateAuditNote(v)" /></div>
          <div class="opinion-field"><label>审计结论</label><el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :model-value="auditConclusion" :disabled="isReadonly" placeholder="基于出口核对结果，判断出口收入记录是否完整、准确" @input="(v: string) => updateAuditConclusion(v)" /></div>
        </div>
      </el-card>

      <!-- 编制提示 -->
      <details class="tips-collapse">
        <summary class="tips-summary">📋 编制提示</summary>
        <ol class="tips-list">
          <li>出口收入应与电子口岸海关出口报关单数据逐期核对。</li>
          <li>免抵退税申报数据从税务申报系统获取（外营收入=FOB出口额）。</li>
          <li>常见差异原因：汇率差异、退运冲减、跨期报关、样品/无偿出口等。</li>
          <li>差异超过重要性水平时应追查具体交易并评估影响。</li>
          <li>适用性：仅出口型企业需填此表，内销企业标注"不适用"。</li>
        </ol>
      </details>
    </template>

    <!-- OnlyOffice -->
    <template v-if="editorMode === '在线编辑'">
      <div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="出口收入电子口岸系统核对D4-16" :readonly="isReadonly" /></div>
    </template>
  </div>
</template>

<style scoped>
.d4-export { padding: 16px 20px; font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.stats-dashboard { display: flex; gap: 12px; margin-bottom: 20px; padding: 14px 18px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed; }
.stat-card { padding: 10px 16px; min-width: 140px; border-radius: 8px; background: #fff; border: 1px solid #ebeef5; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.stat-card.stat-primary { border-left: 3px solid #409eff; }
.stat-card.stat-warn { border-left: 3px solid #f56c6c; }
.stat-value { font-size: 18px; font-weight: 700; color: #303133; font-variant-numeric: tabular-nums; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }
.methodology-collapse { margin-bottom: 14px; border-radius: 6px; border: 1px solid #faecd8; border-left: 3px solid #e6a23c; background: #fffbf0; }
.methodology-summary { cursor: pointer; padding: 8px 14px; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #b88230; }
.methodology-body { padding: 8px 14px 12px; font-size: 12px; color: #606266; line-height: 1.8; }
.methodology-body p { margin: 0 0 6px; }
.guide-strip { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; padding: 10px 14px; background: #f0f9eb; border-radius: 6px; border: 1px solid #e1f3d8; }
.guide-strip-label { font-weight: 600; color: #67c23a; font-size: 12px; }
.guide-chip { background: #fff; border: 1px solid #c2e7b0; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: #529b2e; cursor: help; }
.guide-chip:hover { background: #f0f9eb; }
.guide-arrow { color: #a8abb2; font-size: 12px; }
.export-table { font-size: var(--wp-font-size, 13px); }
.export-table :deep(.el-table__cell) { padding: 6px 0; }
.export-table :deep(.col-book .el-table__cell) { background-color: #fafff5 !important; }
.export-table :deep(.col-ports .el-table__cell) { background-color: #f0f5ff !important; }
.export-table :deep(.col-tax .el-table__cell) { background-color: #fff8f0 !important; }
.diff-warn { color: #f56c6c; font-weight: 600; }
.add-row-bar { margin: 12px 0 20px; text-align: center; }
.audit-opinion-card { margin-bottom: 20px; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 8px; }
.opinion-body { display: flex; flex-direction: column; gap: 14px; }
.opinion-field label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.tips-collapse { margin-bottom: 16px; border-radius: 6px; border: 1px solid #fde2e2; border-left: 3px solid #f56c6c; }
.tips-summary { cursor: pointer; padding: 8px 14px; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #f56c6c; }
.tips-list { margin: 8px 14px 12px; padding-left: 18px; font-size: 12px; color: #606266; line-height: 2; }
.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }
</style>
