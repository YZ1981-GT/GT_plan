<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * J1TabAdjustment — J1-3 调整分录汇总表
 *
 * 参照 D4TabAdjustment 完整功能：
 * - 可编辑表格 8列 + 新增/删除行
 * - 分类下拉（账项调整/报表调整/其他）
 * - 借贷平衡指示器
 * - 推送至A13 + 确认调整
 * - 导入导出三级
 * - 审计说明/结论 + AI辅助（opinion-card）
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useJ1ImportExport } from '@/composables/workpaper/j1/useJ1ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, any>
  isReadonly?: boolean
}>()

const isReadonly = computed(() => props.isReadonly ?? false)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 行模型 ───────────────────────────────────────────────────────────
interface AdjRow {
  rowId: string
  description: string
  category: string
  reportItem: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}

const rows = ref<AdjRow[]>([])
const STORAGE_KEY = 'J1-3-adjustment-rows'

// ─── Load/Save ────────────────────────────────────────────────────────
function loadRows() {
  const raw = props.allResponses?.get(STORAGE_KEY)?.remark
  if (!raw) { rows.value = []; return }
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map((r: any, i: number) => ({
        rowId: r.rowId || genId(i),
        description: r.description || '',
        category: r.category || '账项调整',
        reportItem: r.reportItem || '',
        accountName: r.accountName || '',
        noteItem: r.noteItem || '',
        debitAmount: Number(r.debitAmount) || 0,
        creditAmount: Number(r.creditAmount) || 0,
        indexRef: r.indexRef || '',
        remark: r.remark || '',
      }))
    }
  } catch { rows.value = [] }
}
loadRows()

function genId(idx?: number): string {
  return `j1adj-${Date.now()}-${idx ?? Math.random().toString(36).slice(2, 6)}`
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(persistRows, 1500)
}

function persistRows() {
  const data = rows.value.map(r => ({
    rowId: r.rowId, description: r.description, category: r.category,
    reportItem: r.reportItem, accountName: r.accountName, noteItem: r.noteItem,
    debitAmount: r.debitAmount, creditAmount: r.creditAmount,
    indexRef: r.indexRef, remark: r.remark,
  }))
  const serialized = JSON.stringify(data)
  props.allResponses?.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: serialized })
  // PUT to backend
  http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
    items: [{ item_id: STORAGE_KEY, conclusion: null, remark: serialized }],
  }).catch(() => {})
}

// ─── CRUD ─────────────────────────────────────────────────────────────
function addRow() {
  if (isReadonly.value) return
  rows.value.push({
    rowId: genId(), description: '', category: '账项调整',
    reportItem: '', accountName: '', noteItem: '',
    debitAmount: 0, creditAmount: 0, indexRef: '', remark: '',
  })
  scheduleSave()
}

function removeRow(rowId: string) {
  if (isReadonly.value) return
  rows.value = rows.value.filter(r => r.rowId !== rowId)
  scheduleSave()
}

function updateCell(rowId: string, field: keyof AdjRow, value: string | number) {
  if (isReadonly.value) return
  const idx = rows.value.findIndex(r => r.rowId === rowId)
  if (idx === -1) return
  const row = { ...rows.value[idx] }
  if (field === 'debitAmount' || field === 'creditAmount') {
    ;(row as any)[field] = Number(value) || 0
  } else {
    ;(row as any)[field] = String(value)
  }
  rows.value[idx] = row
  scheduleSave()
}

// ─── 借贷平衡 ─────────────────────────────────────────────────────────
const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
const isBalanced = computed(() => Math.abs(balanceDiff.value) < 0.005)

// ─── 同步到集中登记 ───────────────────────────────────────────────────
const { year: auditYear } = useAuditContext()
const {
  centralStatus,
  syncing: centralSyncing,
  syncToCentral,
  refreshStatus,
} = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: auditYear,
  wpId: () => props.wpId,
  wpCode: 'J1',
  itemId: 'J1-3-adjustment-rows',
  buildLineItems: () => rows.value.map((r: any) => ({
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: rows.value.find((r: any) => r.description)?.description || 'J1 调整',
    adjustmentType: rows.value.every((r: any) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
void refreshStatus()

// ─── 推送A13 ──────────────────────────────────────────────────────────
const selectedRows = ref<AdjRow[]>([])
function handleSelectionChange(selection: AdjRow[]) { selectedRows.value = selection }

/**
 * 推送错报至 A13 未更正错报汇总。
 * 🔴 历史实现调 `POST /workpapers/{id}/push-to-a13` —— 该端点后端不存在（恒 404，
 *    catch 里只弹「推送失败」）。平台标准是 eventBus `a13:push-misstatement`，
 *    由挂在 WorkpaperEditor 的 useA13MisstatementBridge 唯一消费者写入
 *    unadjusted_misstatements（含 source_wp_code 溯源）。
 */
function pushToA13() {
  if (selectedRows.value.length === 0) return
  eventBus.emit('a13:push-misstatement', {
    wpCode: 'J1-3',
    accountCode: '2211',
    accountName: '应付职工薪酬',
    projectId: props.projectId,
    source: 'J1-3',
    items: selectedRows.value.map(r => ({
      description: `${r.description || '应付职工薪酬调整'}（${r.category}${r.accountName ? '：' + r.accountName : ''}）`,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      indexRef: r.indexRef,
    })),
    timestamp: Date.now(),
  } as any)
}

// ─── 确认调整 ─────────────────────────────────────────────────────────
/**
 * 确认调整：落库 + 发 `adjustment:created` 刷新信号（历史实现只弹一句
 * 「将同步至审定表J1-1」但不发任何事件、也不写 J1-1 → 承诺未兑现）。
 * 审定表侧走「带入调整」从集中登记逐笔分配（避免与本事件双算）。
 */
function publishAdjustment() {
  if (!isBalanced.value || rows.value.length === 0) return
  persistRows()
  const ajeTotal = rows.value
    .filter(r => r.category !== '报表调整')
    .reduce((s, r) => s + r.debitAmount - r.creditAmount, 0)
  const rjeTotal = rows.value
    .filter(r => r.category === '报表调整')
    .reduce((s, r) => s + r.debitAmount - r.creditAmount, 0)
  eventBus.emit('adjustment:created', {
    wpCode: 'J1-3',
    accountCode: '2211',
    projectId: props.projectId,
    entryCount: rows.value.length,
    ajeTotal,
    rjeTotal,
    timestamp: Date.now(),
  } as any)
  ElMessage.success('调整分录已确认（可在审定表 J1-1 用「带入调整」逐笔分配到分类行）')
}

// ─── 导入导出 ─────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData } = useJ1ImportExport(props.wpId)

function triggerImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) importData('adjustment', file)
  }
  input.click()
}

// ─── 分类选项 ─────────────────────────────────────────────────────────
const categoryOptions = [
  { label: '账项调整', value: '账项调整' },
  { label: '报表调整', value: '报表调整' },
  { label: '其他', value: '其他' },
]

// ─── 审计说明/结论 ────────────────────────────────────────────────────
const auditNote = ref(props.allResponses?.get('J1-3-note')?.remark || '')
const auditConclusion = ref(props.allResponses?.get('J1-3-conclusion')?.remark || '')

function saveOpinion() {
  const items = [
    { item_id: 'J1-3-note', conclusion: null, remark: auditNote.value },
    { item_id: 'J1-3-conclusion', conclusion: null, remark: auditConclusion.value },
  ]
  items.forEach(it => props.allResponses?.set(it.item_id, it))
  http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items }).catch(() => {})
}

// ─── AI辅助 ──────────────────────────────────────────────────────────
const aiLoadingKey = ref<string | null>(null)

async function generateNote() {
  if (isReadonly.value) return
  aiLoadingKey.value = 'note'
  try {
    const ctx = rows.value.map(r =>
      `${r.description || '调整'}: ${r.accountName} 借${fmtAmount(r.debitAmount)}/贷${fmtAmount(r.creditAmount)} [${r.category}]`
    ).join('\n') || '（暂无调整分录）'
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'adj-note',
      prompt: '根据应付职工薪酬J1-3调整分录数据，生成审计说明。',
      context: { '调整分录': ctx },
      existingContent: auditNote.value,
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) {
      auditNote.value = text
      saveOpinion()
      ElMessage.success('AI生成审计说明完成')
    }
  } catch { ElMessage.warning('AI生成失败') }
  finally { aiLoadingKey.value = null }
}

async function generateConclusion() {
  if (isReadonly.value) return
  aiLoadingKey.value = 'conclusion'
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'adj-conclusion',
      prompt: '根据应付职工薪酬J1-3调整分录和审计说明，生成审计结论。',
      context: { '审计说明': auditNote.value || '（未填写）', '借贷平衡': isBalanced.value ? '平衡' : `不平衡差异${fmtAmount(balanceDiff.value)}` },
      existingContent: auditConclusion.value,
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) {
      auditConclusion.value = text
      saveOpinion()
      ElMessage.success('AI生成审计结论完成')
    }
  } catch { ElMessage.warning('AI生成失败') }
  finally { aiLoadingKey.value = null }
}

// ─── 格式化 ──────────────────────────────────────────────────────────
function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="j1-tab-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 记录审计过程中发现的需要调整的会计分录，区分账项调整(AJE)与报表调整(RJE)。</p>
        <p>2. 借贷合计必须平衡（借方合计=贷方合计），不平衡时无法确认。</p>
        <p>3. 确认后的调整分录将同步更新J1-1审定表的AJE/RJE列。</p>
        <p>4. 可选中分录推送至A13错报汇总表。</p>
        <p>5. 本表仅列示与应付职工薪酬(2211)相关的审计调整。</p>
        <p>6. 注：本底稿适用于调整分录较多、较复杂的项目，项目组可根据实际情况选择是否使用。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
          + 新增调整分录
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly || selectedRows.length === 0"
          @click="pushToA13"
        >
          推送至A13
        </el-button>
        <GtIndexChip value="wp:J1-1" :context-project-id="projectId" />
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('adjustment')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('adjustment')">导出数据</el-dropdown-item>
              <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button
          size="small"
          type="success"
          :disabled="isReadonly || !isBalanced || rows.length === 0"
          @click="publishAdjustment"
        >
          确认调整
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !isBalanced || rows.length === 0"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
          @click="syncToCentral"
        >
          同步到集中登记
        </el-button>
        <el-tag
          v-if="centralStatus?.review_status"
          size="small"
          :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
          :title="centralStatus.rejection_reason || ''"
        >
          集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}
        </el-tag>
      </div>
    </div>

    <!-- 借贷平衡指示 -->
    <div class="balance-indicator">
      <span class="balance-item">借方合计：<strong>{{ fmtAmount(debitTotal) }}</strong></span>
      <span class="balance-item">贷方合计：<strong>{{ fmtAmount(creditTotal) }}</strong></span>
      <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">不平衡 差异{{ fmtAmount(balanceDiff) }}</el-tag>
    </div>

    <!-- 主表 -->
    <el-table
      :data="rows"
      border
      size="small"
      style="font-size: 13px; margin-bottom: 12px"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column label="调整事项说明" min-width="180">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.description" size="small" placeholder="摘要"
            @change="(v: string) => updateCell(row.rowId, 'description', v)" />
          <span v-else>{{ row.description || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.category" size="small"
            @change="(v: string) => updateCell(row.rowId, 'category', v)">
            <el-option v-for="opt in categoryOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reportItem" size="small" placeholder="报表项目"
            @change="(v: string) => updateCell(row.rowId, 'reportItem', v)" />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" placeholder="如 2211-应付职工薪酬"
            @change="(v: string) => updateCell(row.rowId, 'accountName', v)" />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.noteItem" size="small"
            @change="(v: string) => updateCell(row.rowId, 'noteItem', v)" />
          <span v-else>{{ row.noteItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" :model-value="row.debitAmount" size="small" style="width:105px"
            @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" :model-value="row.creditAmount" size="small" style="width:105px"
            @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="80">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
            @change="(v: string) => updateCell(row.rowId, 'indexRef', v)" />
          <span v-else>{{ row.indexRef || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
            @change="(v: string) => updateCell(row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" type="danger" size="small" link @click="removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态 -->
    <div v-if="rows.length === 0" class="empty-hint">
      暂无调整分录。点击"+ 新增调整分录"添加。
    </div>

    <!-- 审计说明与结论（opinion-card） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:J1-1" :context-project-id="projectId" />
            <GtIndexChip value="wp:A13" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'note'"
              :disabled="isReadonly" @click="generateNote">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReviewDialog?.('J1-3-note')">💬</el-button>
          </div>
        </div>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }"
          placeholder="汇总应付职工薪酬相关调整事项的原因与影响..."
          :disabled="isReadonly" @change="saveOpinion" />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'conclusion'"
              :disabled="isReadonly" @click="generateConclusion">🤖 AI辅助</el-button>
          </div>
        </div>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }"
          placeholder="审计结论..." :disabled="isReadonly" @change="saveOpinion" />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.j1-tab-adjustment { padding: 12px; }
.j1-tab-adjustment :deep(.el-table) { font-size: 13px; }
.j1-tab-adjustment :deep(.el-table th), .j1-tab-adjustment :deep(.el-table td) { font-size: 13px !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; }
.balance-indicator { display: flex; align-items: center; gap: 16px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; margin-bottom: 12px; font-size: 13px; }
.balance-item { color: #606266; }
.balance-item strong { color: #303133; }
.empty-hint { text-align: center; color: #909399; padding: 24px; font-size: 13px; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
