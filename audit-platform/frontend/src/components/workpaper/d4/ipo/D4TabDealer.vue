<script setup lang="ts">
/**
 * D4TabDealer — D4-25 经销商检查
 *
 * 列规格驱动渲染 13 列，复用 ipoChecklistSchema 单一真源。
 * 双模式（表格视图 ↔ 在线编辑）+ 表内计算（占比派生列）+ AI 辅助 + 导入导出
 *
 * 🔴 本组件零公式字面量，只引用 ipoChecklistSchema + ipoChecklistFormulaEngine
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
  getAddRowPromptTitle,
  getAddRowInputLabel,
  createEmptyRow,
  type RowRecord,
} from './ipoChecklistSchema'
import {
  recalcAllDerived,
  setManualOverride,
  type ManualOverrides,
} from './ipoChecklistFormulaEngine'

const SHEET_CODE = 'D4-25' as const
const spec = SHEET_SPECS[SHEET_CODE]
const derivedKeys = getDerivedColumns(SHEET_CODE)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── 数据 ──────────────────────────────────────────────────────
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
    try {
      const p = JSON.parse(r.remark)
      if (Array.isArray(p)) { rows.value = p; doRecalc(); return }
    } catch { /* ignore */ }
  }
  rows.value = []
}
function loadNote() {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
}
watch(() => props.allResponses.get(ROWS_KEY)?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get(NOTE_KEY)?.remark, loadNote, { immediate: true })

// ─── 表内计算 ──────────────────────────────────────────────────
function doRecalc() {
  const errors = recalcAllDerived(SHEET_CODE, rows.value, manualOverrides.value)
  if (errors.length > 0) {
    console.warn('[D4-25] 公式求值错误:', errors)
  }
}

// ─── 行操作 ──────────────────────────────────────────────────
async function handleAddRow() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt(
      getAddRowInputLabel(SHEET_CODE),
      getAddRowPromptTitle(SHEET_CODE),
      { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' }
    )
    if (value?.trim()) {
      rows.value.push(createEmptyRow(SHEET_CODE, value.trim()))
      doRecalc()
      persistAll()
    }
  } catch { /* cancel */ }
}

function removeRow(rowId: string) {
  if (props.isReadonly) return
  rows.value = rows.value.filter(r => r.rowId !== rowId)
  doRecalc()
  persistAll()
}

function updateCell(rowId: string, key: string, value: unknown) {
  if (props.isReadonly) return
  const row = rows.value.find(r => r.rowId === rowId)
  if (!row) return

  // 派生列手填 → 锁定为手填值，不再重算
  if (derivedKeys.has(key)) {
    const numVal = value === '' || value === null || value === undefined ? null : Number(value)
    if (numVal !== null && !Number.isFinite(numVal)) return
    setManualOverride(manualOverrides.value, SHEET_CODE, key, rowId, numVal)
    row[key] = numVal
    ElMessage.info('该列为计算列，已锁定为手填值')
  } else {
    row[key] = value
    doRecalc()
  }
  persistAll()
}

// ─── 持久化 ──────────────────────────────────────────────────
function persistAll() {
  props.allResponses.set(ROWS_KEY, { item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value })
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    const keys = [ROWS_KEY, NOTE_KEY, CONCLUSION_KEY]
    window.dispatchEvent(new CustomEvent('d4:save-items', {
      detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) }
    }))
  }, 2000)
}

function flushPendingSave() {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
    const keys = [ROWS_KEY, NOTE_KEY, CONCLUSION_KEY]
    window.dispatchEvent(new CustomEvent('d4:save-items', {
      detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) }
    }))
  }
}

function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }

onBeforeUnmount(() => { flushPendingSave() })

// ─── 双模式切换 ──────────────────────────────────────────────
const editorMode = ref<string>('表格视图')
const modeOptions = ['表格视图', '在线编辑']
const syncState = ref<{ ok: boolean; message: string } | null>(null)

watch(editorMode, async (newMode, oldMode) => {
  if (newMode === oldMode) return
  syncState.value = null

  if (newMode === '在线编辑') {
    // 切到 OO：先 flush debounce 再投影
    flushPendingSave()
    // 投影 rows → OO 由 OO 打开后自动从 DB 读取，无需手动推
  } else if (newMode === '表格视图') {
    // 切回表格：OO 数据通过 DB 已同步，reload rows
    await nextTick()
    loadData()
  }
})

// ─── AI ──────────────────────────────────────────────────────
const aiAvailable = ref(false)
async function checkAiHealth() {
  try {
    const r = await http.get('/api/ai/health', { _silent: true } as any)
    aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' ||
      (r.data?.data?.status ?? r.data?.status) === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)

async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'analysis-note', existingContent: auditNote.value,
      relatedContext: { task: '基于经销商检查(D4-25)结果生成审计说明', rowCount: rows.value.length },
    }, { _silent: true } as any)
    const t = res.data?.data?.content ?? res.data?.content ?? ''
    if (!t) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateAuditNote(t)
  } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiNoteLoading.value = false }
}

async function genConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiConclusionLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'adj-conclusion', existingContent: auditConclusion.value,
      relatedContext: { task: '基于经销商检查结果生成审计结论', noteText: auditNote.value, rowCount: rows.value.length },
    }, { _silent: true } as any)
    const t = res.data?.data?.content ?? res.data?.content ?? ''
    if (!t) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateAuditConclusion(t)
  } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiConclusionLoading.value = false }
}

// ─── 导入导出 ────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
function handleExportTemplate() { exportTemplate(SHEET_CODE) }
function handleExportData() { exportData(SHEET_CODE) }
async function handleImportFile(f: any) {
  await importData(SHEET_CODE, f.raw || f)
  // 导入后 reload + 切回表格视图
  editorMode.value = '表格视图'
  await nextTick()
  loadData()
}

// ─── 格式化 ──────────────────────────────────────────────────
function fmtAmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return displayPrefs.fmtAmount(n)
}

function fmtPercent(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return (n * 100).toFixed(2) + '%'
}
</script>

<template>
<div class="d4-dealer">
  <!-- 工具栏 -->
  <div class="toolbar">
    <div class="toolbar-left">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
    </div>
    <div class="toolbar-right">
      <el-dropdown trigger="click" size="small">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false"
                :disabled="isReadonly || importing" @change="handleImportFile">
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
      <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-25-dealer')">
        💬 复核
      </el-button>
    </div>
  </div>

  <!-- 同步状态 -->
  <div v-if="syncState" :class="['sync-banner', syncState.ok ? 'sync-ok' : 'sync-fail']">
    {{ syncState.message }}
  </div>

  <!-- 表格视图 -->
  <template v-if="editorMode !== '在线编辑'">
    <!-- 编制说明（源模板红字方法论） -->
    <div class="methodology-strip">
      <div class="methodology-content">
        <p>选取经销商收入占比较大的客户，取得经销商的基本资料，关注经销商基本情况是否与销售规模匹配。</p>
        <p>了解客户是否同时向经销商和终端客户销售，如是，关注直销客户和经销商客户的毛利差异，分析差异原因的合理性。</p>
        <p>关注经销商是否存在关联方关系、是否属于非法人实体、销售费用承担方式、有无补贴或返利等政策。</p>
        <p>抽查经销商销售至终端客户的销售金额，对比期末存货量，分析经销商库存的合理性。</p>
      </div>
    </div>

    <!-- 主表格 — 列规格驱动 -->
    <el-table :data="rows" border stripe class="dealer-table" :highlight-current-row="true">
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="客户名称" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.customerName" size="small" :disabled="isReadonly"
            @change="updateCell(row.rowId, 'customerName', row.customerName)" />
        </template>
      </el-table-column>
      <el-table-column label="经销商" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.dealer" size="small" :disabled="isReadonly"
            @change="updateCell(row.rowId, 'dealer', row.dealer)" />
        </template>
      </el-table-column>
      <el-table-column label="本期销售数量" min-width="100" align="right">
        <template #default="{ row }">
          <el-input v-model="row.salesQty" size="small" :disabled="isReadonly" style="width:100%"
            @change="updateCell(row.rowId, 'salesQty', row.salesQty)" />
        </template>
      </el-table-column>
      <el-table-column label="本期销售金额" min-width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput v-model="row.salesAmount" size="small" :disabled="isReadonly" style="width:100%"
            @change="updateCell(row.rowId, 'salesAmount', row.salesAmount)" />
        </template>
      </el-table-column>
      <el-table-column label="占同类交易比例" min-width="100" align="right">
        <template #default="{ row }">
          <span class="derived-value">{{ fmtPercent(row.salesRatio) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末应收账款余额" min-width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput v-model="row.arBalance" size="small" :disabled="isReadonly" style="width:100%"
            @change="updateCell(row.rowId, 'arBalance', row.arBalance)" />
        </template>
      </el-table-column>
      <el-table-column label="是否关联方" width="85" align="center">
        <template #default="{ row }">
          <el-select v-model="row.isRelated" size="small" :disabled="isReadonly" placeholder="--"
            @change="updateCell(row.rowId, 'isRelated', row.isRelated)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="个人/企业" width="85" align="center">
        <template #default="{ row }">
          <el-select v-model="row.entityType" size="small" :disabled="isReadonly" placeholder="--"
            @change="updateCell(row.rowId, 'entityType', row.entityType)">
            <el-option label="个人" value="个人" />
            <el-option label="企业" value="企业" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="销售费用承担方式" min-width="110">
        <template #default="{ row }">
          <el-input v-model="row.expenseBearer" size="small" :disabled="isReadonly"
            @change="updateCell(row.rowId, 'expenseBearer', row.expenseBearer)" />
        </template>
      </el-table-column>
      <el-table-column label="补贴或返利" width="85" align="center">
        <template #default="{ row }">
          <el-select v-model="row.subsidy" size="small" :disabled="isReadonly" placeholder="--"
            @change="updateCell(row.rowId, 'subsidy', row.subsidy)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="终端销售金额" min-width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput v-model="row.terminalSalesAmount" size="small" :disabled="isReadonly" style="width:100%"
            @change="updateCell(row.rowId, 'terminalSalesAmount', row.terminalSalesAmount)" />
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly"
            @change="updateCell(row.rowId, 'remark', row.remark)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right" align="center">
        <template #default="{ row }">
          <el-popconfirm title="确认删除?" @confirm="removeRow(row.rowId)">
            <template #reference>
              <el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="add-row-bar">
      <el-button :disabled="isReadonly" @click="handleAddRow">
        <el-icon :size="14"><Plus /></el-icon> 添加经销商
      </el-button>
    </div>

    <!-- 审计意见区 -->
    <el-card class="audit-opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计意见区</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiNoteLoading"
                :disabled="isReadonly || !aiAvailable" @click="genNote">
                🤖 AI辅助说明
              </el-button>
            </el-tooltip>
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiConclusionLoading"
                :disabled="isReadonly || !aiAvailable" @click="genConclusion">
                🤖 AI辅助结论
              </el-button>
            </el-tooltip>
          </div>
        </div>
      </template>
      <div class="opinion-body">
        <div class="opinion-field">
          <label>三、审计说明</label>
          <el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" :model-value="auditNote"
            :disabled="isReadonly" placeholder="记录经销商销售检查中发现的异常情况"
            @input="(v: string) => updateAuditNote(v)" />
        </div>
        <div class="opinion-field">
          <label>四、审计结论</label>
          <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :model-value="auditConclusion"
            :disabled="isReadonly" placeholder="综合判断经销商销售收入的真实性"
            @input="(v: string) => updateAuditConclusion(v)" />
        </div>
      </div>
    </el-card>
  </template>

  <!-- 在线编辑 -->
  <template v-if="editorMode === '在线编辑'">
    <div class="oo-container">
      <GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId"
        :sheet-name="spec.sheetName" :readonly="isReadonly" />
    </div>
  </template>
</div>
</template>

<style scoped>
.d4-dealer { padding: 16px 20px; font-size: var(--wp-font-size, 13px) }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px }
.toolbar-left { display: flex; align-items: center }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap }
.sync-banner { padding: 6px 12px; border-radius: 4px; font-size: 12px; margin-bottom: 12px }
.sync-ok { background: #f0f9eb; color: #67c23a; border: 1px solid #e1f3d8 }
.sync-fail { background: #fef0f0; color: #f56c6c; border: 1px solid #fde2e2 }
.methodology-strip { margin-bottom: 16px; padding: 10px 14px; background: #fffbf0; border-radius: 6px; border: 1px solid #faecd8; border-left: 3px solid #e6a23c }
.methodology-strip .methodology-content { font-size: 12px; color: #606266; line-height: 1.8 }
.methodology-strip .methodology-content p { margin: 2px 0 }
.dealer-table { font-size: var(--wp-font-size, 13px) }
.dealer-table :deep(.el-table__cell) { padding: 5px 4px }
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
