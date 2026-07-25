<template>
  <div class="k2-tab-adjustment">
    <!-- Section标题栏 + 复核按钮右对齐 -->
    <div class="section-head">
      <h3 class="sheet-title">K2-3 调整分录汇总</h3>
      <div class="head-actions">
        <el-button size="small" type="success" :disabled="isReadonly || !isBalanced" @click="handleSaveWriteback">
          保存&amp;回写
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !isBalanced || entries.length === 0"
          @click="syncToCentral"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
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
        <el-dropdown trigger="click" size="small" @command="handleIECommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
    </div>

    <!-- 借贷不平衡警告 -->
    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom:8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmtAmt(totalDebits) }} ≠ 贷方合计 {{ fmtAmt(totalCredits) }}，差额 {{ fmtAmt(Math.abs(balanceDiff)) }}
    </el-alert>

    <!-- 工具栏 -->
    <div class="k2-adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">+ 新增</el-button>
      <span class="entry-count">共 {{ entries.length }} 条分录</span>
    </div>

    <!-- 调整分录表格 -->
    <el-table
      :data="entries"
      border
      size="small"
      style="width:100%;font-size:13px"
      max-height="520"
      :row-class-name="tableRowClassName"
    >
      <el-table-column prop="seq" label="序号" width="56" align="center" />

      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small" @change="(v: string) => updateCell(row.id, 'entryType', v)">
            <el-option value="AJE" label="AJE" />
            <el-option value="RJE" label="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摘要" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" placeholder="分录摘要" @change="(v: string) => updateCell(row.id, 'summary', v)" />
          <span v-else>{{ row.summary || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方科目" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.debitAccount" size="small" placeholder="科目名称" @change="(v: string) => updateCell(row.id, 'debitAccount', v)" />
          <span v-else>{{ row.debitAccount || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" :precision="2" :min="0" style="width:100%" @change="(v: number | undefined) => updateCell(row.id, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方科目" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.creditAccount" size="small" placeholder="科目名称" @change="(v: string) => updateCell(row.id, 'creditAccount', v)" />
          <span v-else>{{ row.creditAccount || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" :precision="2" :min="0" style="width:100%" @change="(v: number | undefined) => updateCell(row.id, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="编制人" width="80">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.preparedBy" size="small" @change="(v: string) => updateCell(row.id, 'preparedBy', v)" />
          <span v-else>{{ row.preparedBy || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="handleRemoveEntry(row.id)">🗑️</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="k2-adj-footer" :class="{ 'balance-fail': !isBalanced }">
      <span class="footer-label">合计</span>
      <span class="footer-debit">借方：{{ fmtAmt(totalDebits) }}</span>
      <span class="footer-credit">贷方：{{ fmtAmt(totalCredits) }}</span>
      <span v-if="isBalanced" class="footer-status ok">✓ 平衡</span>
      <span v-else class="footer-status err">✗ 不平衡 | 差额：{{ fmtAmt(Math.abs(balanceDiff)) }}</span>
    </div>

    <!-- 索引跳转 -->
    <div style="display:flex;gap:8px;margin:12px 0;align-items:center">
      <span style="font-size:12px;color:#909399">关联底稿：</span>
      <el-tag size="small" type="primary" effect="plain" style="cursor:pointer" @click="emit('navigate-sheet', 'K2-1')">→ K2-1 审定表</el-tag>
      <el-tag size="small" type="warning" effect="plain" style="cursor:pointer" @click="emit('navigate-sheet', 'A13')">→ A13 错报汇总</el-tag>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" style="margin-bottom:12px">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span style="font-weight:600">审计说明</span>
        </div>
      </template>
      <el-input v-model="adjAuditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="概述调整分录编制原因、重大调整事项说明..." @blur="persistAdjNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" style="margin-bottom:12px">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span style="font-weight:600">审计结论</span>
          <el-button size="small" type="default" link @click="openReview">💬 复核</el-button>
        </div>
      </template>
      <el-input v-model="adjAuditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="isReadonly" placeholder="调整分录综合结论..." @blur="persistAdjConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="k2-guide-details">
      <summary>📋 编制提示</summary>
      <div class="k2-guide-content">
        <p>1. 调整分录(AJE)用于更正被审计单位财务报表中的错报；重分类分录(RJE)用于分析性归类调整。</p>
        <p>2. 借贷必须平衡后方可保存回写。点击"保存&amp;回写"将汇总AJE/RJE数据回写K2-1审定表。</p>
        <p>3. 保存后自动发布 adjustment:created 事件联动 A13 错报汇总底稿。</p>
        <p>4. 其他流动资产科目代码 1231，资产类借方，期末=期初+借-贷。</p>
        <p>5. K2-5摊销测算差异超重要性水平时会推送建议AJE，本表自动接收。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabAdjustment.vue — K2-3 调整分录汇总
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 4.6
 * Requirements: 7.1-7.2
 *
 * 功能：
 * - AJE/RJE 分录列表: 序号/类型/摘要/借方科目/借方金额/贷方科目/贷方金额/编制人
 * - 借贷平衡校验（Σ借方 === Σ贷方），不平衡红色警告
 * - 双向同步K2-1审定表 (update allResponses AJE/RJE fields)
 * - EventBus publish 'adjustment:created' → A13
 * - 动态行新增(ElMessageBox.prompt) + 导入导出
 */
import { ref, computed, inject, onMounted, onBeforeUnmount } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'

const K2_ACCOUNT_CODE = '1231'
const ITEM_PREFIX = 'K2-3-adj'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ═══ 数据模型 ═══
interface AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  summary: string
  debitAccount: string
  debitAmount: number
  creditAccount: string
  creditAmount: number
  preparedBy: string
}

const entries = ref<AdjustmentEntry[]>([])
let nextId = 1

// ═══ 计算属性：借贷平衡 ═══
const totalDebits = computed(() => entries.value.reduce((sum, e) => sum + (e.debitAmount || 0), 0))
const totalCredits = computed(() => entries.value.reduce((sum, e) => sum + (e.creditAmount || 0), 0))
const balanceDiff = computed(() => totalDebits.value - totalCredits.value)
const isBalanced = computed(() => Math.abs(balanceDiff.value) < 0.005)

// ═══ 同步到集中调整登记（workpaper-adjustment-centralization） ═══
const { year: auditYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: auditYear,
  wpId: () => props.wpId,
  wpCode: 'K2',
  itemId: `${ITEM_PREFIX}-entries`,
  buildLineItems: () => entries.value.flatMap(e => {
    const items: any[] = []
    if (e.debitAccount || (e.debitAmount || 0) !== 0) items.push({ account_name: e.debitAccount, debit_amount: e.debitAmount || 0, credit_amount: 0 })
    if (e.creditAccount || (e.creditAmount || 0) !== 0) items.push({ account_name: e.creditAccount, debit_amount: 0, credit_amount: e.creditAmount || 0 })
    return items
  }),
  buildMeta: () => ({
    description: entries.value.find(e => e.summary)?.summary || 'K2 其他流动资产调整',
    adjustmentType: entries.value.length > 0 && entries.value.every(e => e.entryType === 'RJE') ? 'rje' : 'aje',
  }),
})

// ═══ 初始化加载 ═══
onMounted(() => {
  loadFromResponses()
  loadAuditNoteConclusion()
  refreshStatus()
  // 订阅K2-5/K2-6推送的建议AJE
  eventBus.on('adjustment:created', handleSuggestedAjeFromUpstream)
})

onBeforeUnmount(() => {
  eventBus.off('adjustment:created', handleSuggestedAjeFromUpstream)
})

/** 接收上游(K2-5/K2-6)推送的建议AJE */
function handleSuggestedAjeFromUpstream(payload: any): void {
  if (!payload || payload.wpCode !== 'K2' || !payload.suggestedEntries) return
  if (payload.source === 'K2-5-amort-variance' || payload.source === 'K2-6-abnormal') {
    const suggested = payload.suggestedEntries as any[]
    let added = 0
    for (const item of suggested) {
      // 按摘要去重
      const exists = entries.value.some(e => e.summary === item.summary)
      if (!exists) {
        entries.value.push({
          id: `entry-${++nextId}`,
          seq: entries.value.length + 1,
          entryType: 'AJE',
          summary: item.summary || `${payload.source}建议调整`,
          debitAccount: item.debitAccount || '其他流动资产',
          debitAmount: Math.abs(item.debitAmount || item.variance || 0),
          creditAccount: item.creditAccount || '销售费用',
          creditAmount: Math.abs(item.creditAmount || item.variance || 0),
          preparedBy: '',
        })
        added++
      }
    }
    if (added > 0) {
      reSequence()
      persistEntries()
      ElMessage.info(`已自动接收 ${added} 笔来自${payload.source === 'K2-5-amort-variance' ? 'K2-5摊销差异' : 'K2-6异常凭证'}的建议AJE`)
    }
  }
}

// ═══ 审计说明/结论 ═══
const adjAuditNote = ref('')
const adjAuditConclusion = ref('')

function loadAuditNoteConclusion(): void {
  const noteItem = props.allResponses.get('K2-3-audit-note')
  adjAuditNote.value = noteItem?.remark ?? ''
  const conclItem = props.allResponses.get('K2-3-audit-conclusion')
  adjAuditConclusion.value = conclItem?.remark ?? ''
}

function persistAdjNote(): void {
  emit('save', 'K2-3-audit-note', { remark: adjAuditNote.value })
}
function persistAdjConclusion(): void {
  emit('save', 'K2-3-audit-conclusion', { remark: adjAuditConclusion.value })
}

function loadFromResponses(): void {
  const saved = props.allResponses.get(`${ITEM_PREFIX}-entries`)
  if (!saved) return
  const raw = saved.remark ?? saved.value ?? (typeof saved === 'string' ? saved : null)
  if (!raw) return
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed)) {
      entries.value = parsed.map((e: any, idx: number) => ({
        id: e.id || `entry-${++nextId}`,
        seq: idx + 1,
        entryType: e.entryType || 'AJE',
        summary: e.summary || '',
        debitAccount: e.debitAccount || '',
        debitAmount: e.debitAmount || 0,
        creditAccount: e.creditAccount || '',
        creditAmount: e.creditAmount || 0,
        preparedBy: e.preparedBy || '',
      }))
      nextId = entries.value.length + 1
    }
  } catch { /* ignore parse error */ }
}

// ═══ 行操作 ═══
async function handleAddEntry(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入分录摘要', '新增调整分录', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：调整其他流动资产-合同取得成本摊销',
    })
    if (value?.trim()) {
      const entry: AdjustmentEntry = {
        id: `entry-${++nextId}`,
        seq: entries.value.length + 1,
        entryType: 'AJE',
        summary: value.trim(),
        debitAccount: '其他流动资产',
        debitAmount: 0,
        creditAccount: '',
        creditAmount: 0,
        preparedBy: '',
      }
      entries.value.push(entry)
      persistEntries()
    }
  } catch { /* cancelled */ }
}

async function handleRemoveEntry(id: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该调整分录行？', '删除确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
    entries.value = entries.value.filter(e => e.id !== id)
    reSequence()
    persistEntries()
  } catch { /* cancelled */ }
}

function updateCell(id: string, field: keyof AdjustmentEntry, value: any): void {
  const entry = entries.value.find(e => e.id === id)
  if (entry) {
    ;(entry as any)[field] = value
    persistEntries()
  }
}

function reSequence(): void {
  entries.value.forEach((e, i) => { e.seq = i + 1 })
}

// ═══ 持久化 ═══
function persistEntries(): void {
  emit('save', `${ITEM_PREFIX}-entries`, { remark: JSON.stringify(entries.value) })
}

// ═══ 保存回写K2-1 + EventBus ═══
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法回写')
    return
  }

  // 汇总AJE/RJE金额 → 回写allResponses
  const ajeTotal = entries.value
    .filter(e => e.entryType === 'AJE')
    .reduce((sum, e) => sum + (e.debitAmount - e.creditAmount), 0)
  const rjeTotal = entries.value
    .filter(e => e.entryType === 'RJE')
    .reduce((sum, e) => sum + (e.debitAmount - e.creditAmount), 0)

  // 同步到allResponses供K2-1审定表读取
  props.allResponses.set('K2-1-aje-total', { item_id: 'K2-1-aje-total', value: ajeTotal })
  props.allResponses.set('K2-1-rje-total', { item_id: 'K2-1-rje-total', value: rjeTotal })

  // 持久化
  emit('save', 'K2-1-aje-total', { remark: String(ajeTotal) })
  emit('save', 'K2-1-rje-total', { remark: String(rjeTotal) })
  persistEntries()

  // EventBus publish adjustment:created → A13
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K2',
      accountCode: K2_ACCOUNT_CODE,
      projectId: props.projectId,
      ajeTotal,
      rjeTotal,
      entryCount: entries.value.length,
    })
  } catch { /* silent */ }

  ElMessage.success('已保存并回写K2-1审定表，已通知A13')
}

// ═══ 导入导出 ═══
function handleIECommand(cmd: string): void {
  if (cmd === 'template') {
    handleExportTemplate()
  } else if (cmd === 'export') {
    handleExportData()
  } else if (cmd === 'import') {
    handleImportFile()
  }
}

async function handleExportTemplate(): Promise<void> {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/k2/export-template?sheet=K2-3`, { responseType: 'blob' } as any)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'K2-3_调整分录模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.warning('导出模板失败（端点可能未就绪）') }
}

async function handleExportData(): Promise<void> {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/k2/export-data?sheet=K2-3`, { responseType: 'blob' } as any)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'K2-3_调整分录数据.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.warning('导出数据失败（端点可能未就绪）') }
}

function handleImportFile(): void {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(`/api/workpapers/${props.wpId}/k2/import-data?sheet=K2-3`, formData)
      const count = res?.data?.data?.rowCount ?? res?.data?.rowCount ?? 0
      if (count > 0) {
        loadFromResponses()
        ElMessage.success(`成功导入 ${count} 条调整分录`)
      } else {
        ElMessage.info('导入完成，无新数据')
      }
    } catch { ElMessage.warning('导入失败（端点可能未就绪）') }
  }
  input.click()
}

// ═══ 复核 ═══
function openReview(): void {
  openReviewDialog('K2-3-adjustment')
}

// ═══ 格式化 ═══
function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function tableRowClassName({ row }: { row: AdjustmentEntry }): string {
  if (row.entryType === 'RJE') return 'rje-row'
  return ''
}
</script>

<style scoped>
.k2-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.k2-adj-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.entry-count { font-size: 12px; color: #909399; }

/* 合计行 */
.k2-adj-footer { display: flex; align-items: center; gap: 16px; margin-top: 8px; padding: 10px 16px; background: #f0f9eb; border-radius: 4px; font-weight: 600; font-size: var(--wp-font-size, 13px); }
.k2-adj-footer.balance-fail { background: #fef0f0; border: 1px solid #f56c6c; }
.footer-label { color: #606266; }
.footer-debit, .footer-credit { color: #303133; }
.footer-status.ok { color: #67c23a; margin-left: auto; }
.footer-status.err { color: #f56c6c; margin-left: auto; font-weight: 700; }

/* RJE行浅色区分 */
:deep(.rje-row) { background-color: #fdf6ec !important; }

/* 编制提示 */
.k2-guide-details { margin-top: 16px; }
.k2-guide-content { padding: 8px 12px; background: #fffbeb; border-left: 3px solid #f59e0b; margin-top: 6px; font-size: 12px; line-height: 1.8; }
.k2-guide-content p { margin: 0; }
</style>
