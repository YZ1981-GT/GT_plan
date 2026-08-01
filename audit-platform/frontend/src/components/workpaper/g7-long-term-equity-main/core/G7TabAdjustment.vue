<template>
  <div class="g7-tab-adjustment">
    <!-- Section标题栏 + 复核按钮右对齐 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-3 调整分录汇总</h3>
      <div class="head-actions">
        <el-button size="small" type="success" :disabled="isReadonly || !isBalanced" @click="handleSaveWriteback">
          保存&amp;回写
        </el-button>
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
        <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">🤖AI辅助</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !isBalanced || entries.length === 0"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
          @click="syncToCentral"
        >
          同步到集中登记
        </el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || a13PushableCount === 0"
          :title="a13PushableCount === 0 ? '无可推送的调整分录（需已填金额且非建议草稿）' : `推送 ${a13PushableCount} 笔至 A13 未更正错报汇总`"
          @click="pushToA13"
        >
          推送错报至 A13 ({{ a13PushableCount }})
        </el-button>
        <el-tag
          v-if="centralStatus?.review_status"
          size="small"
          :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
          :title="centralStatus.rejection_reason || ''"
        >
          集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}
        </el-tag>
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
    </div>

    <details class="g7-guide-details">
      <summary>📋 编制提示</summary>
      <div class="g7-guide-content">
        <p>1. 本表按源 Excel G7-3 编制：调整事项说明、类别、报表项目、科目名称、附注项目、借贷调整金额、索引及备注。</p>
        <p>2. 「账项调整」作为 AJE 影响账面余额；「报表调整」作为 RJE 影响列报；「其他」按 AJE 处理。</p>
        <p>3. 每一调整事项应形成完整借贷分录，整表借贷平衡后才能确认；确认后同步集中调整分录模块并回写 G7-1。</p>
        <p>4. 1511 长期股权投资按借方减贷方回写；1512 减值准备按贷方减借方回写。</p>
        <p>5. 可从集中调整分录模块拉取涉及 1511/1512 的完整分录组，避免只取单边导致底稿失衡。</p>
        <p>6. G7-14/G7-13 推入的建议草稿标黄；请「采纳」后再保存推集中模块，「清除」则丢弃。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：汇总长期股权投资相关账项调整与报表调整，验证借贷平衡及依据充分，并与集中调整分录模块、G7-1 审定表保持一致。
    </el-alert>

    <!-- 借贷差额实时显示 -->
    <div class="balance-indicator" :class="{ balanced: isBalanced, unbalanced: !isBalanced }">
      <span v-if="isBalanced">借贷差额: ¥0.00 ✅</span>
      <span v-else>借贷差额: ¥{{ fmtAbs(balanceDiff) }} ❌</span>
    </div>

    <!-- 借贷不平衡警告 -->
    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom:8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmt(totalDebits) }} ≠ 贷方合计 {{ fmt(totalCredits) }}，差额
      <span class="balance-diff-text">{{ fmt(Math.abs(balanceDiff)) }}</span>
    </el-alert>

    <!-- 工具栏 -->
    <div class="g7-adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">
        + 新增调整分录
      </el-button>
      <el-button
        size="small"
        :loading="syncing"
        :disabled="isReadonly || !projectId"
        @click="handleSyncFromModule"
      >
        从调整分录模块同步
      </el-button>
      <el-button
        size="small"
        type="success"
        plain
        :disabled="isReadonly || suggestedDraftCount === 0"
        @click="adoptAllSuggested"
      >
        采纳全部建议 ({{ suggestedDraftCount }})
      </el-button>
      <el-button
        size="small"
        type="warning"
        plain
        :disabled="isReadonly || suggestedDraftCount === 0"
        @click="clearSuggestedDrafts"
      >
        清除建议草稿 ({{ suggestedDraftCount }})
      </el-button>
      <span class="row-count">共 {{ entries.length }} 行</span>
      <span v-if="lastSyncMsg" class="sync-msg">{{ lastSyncMsg }}</span>
    </div>

    <!-- 隐藏的文件上传 -->
    <input ref="fileInputRef" type="file" accept=".xlsx" style="display:none" @change="onFileSelected" />

    <!-- 源 Excel G7-3 列结构 -->
    <el-table
      :data="entries"
      border
      size="small"
      style="width:100%;font-size:13px"
      max-height="520"
      :row-class-name="tableRowClassName"
    >
      <el-table-column label="调整事项说明" min-width="180">
        <template #default="{ row }">
          <div class="desc-cell">
            <el-tag v-if="isSuggestedDraft(row)" size="small" type="warning" class="draft-tag">
              {{ sourceKindLabel(row.sourceKind) || '建议' }}
            </el-tag>
            <el-input
              v-if="!isReadonly"
              v-model="row.description"
              size="small"
              placeholder="说明调整原因及依据"
              @change="handleRowChanged(row)"
            />
            <span v-else>{{ row.description || '-' }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="类别" width="120">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            v-model="row.category"
            size="small"
            @change="handleRowChanged(row)"
          >
            <el-option v-for="opt in categoryOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <el-table-column label="报表项目" width="130">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.reportItem"
            size="small"
            @change="handleRowChanged(row)"
          />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="170">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            v-model="row.accountCode"
            size="small"
            filterable
            allow-create
            default-first-option
            @change="handleAccountChanged(row)"
          >
            <el-option
              v-for="opt in accountOptions"
              :key="opt.code"
              :value="opt.code"
              :label="`${opt.code} ${opt.name}`"
            />
          </el-select>
          <span v-else>{{ row.accountName || row.accountCode || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注项目" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.noteItem"
            size="small"
            @change="handleRowChanged(row)"
          />
          <span v-else>{{ row.noteItem || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方调整金额" width="125" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && !isSuggestedDraft(row)"
            v-model="row.debitAmount"
            size="small"
            :controls="false"
            :precision="2"
            :min="0"
            style="width:100%"
            @change="handleRowChanged(row)"
          />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方调整金额" width="125" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && !isSuggestedDraft(row)"
            v-model="row.creditAmount"
            size="small"
            :controls="false"
            :precision="2"
            :min="0"
            style="width:100%"
            @change="handleRowChanged(row)"
          />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="90">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.indexRef"
            size="small"
            @change="handleRowChanged(row)"
          />
          <span v-else>{{ row.indexRef || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.remark"
            size="small"
            @change="handleRowChanged(row)"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button
            v-if="isSuggestedDraft(row)"
            link
            size="small"
            type="success"
            @click="adoptSuggestedRow(row.id)"
          >
            采纳
          </el-button>
          <el-button link size="small" type="danger" @click="handleRemoveEntry(row.id)">
            🗑️
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 + 借贷差额汇总（借贷不平衡时红色高亮） -->
    <div class="g7-adj-footer" :class="{ 'balance-fail': !isBalanced }">
      <span class="footer-label">合计</span>
      <span class="footer-debit">借方：{{ fmt(totalDebits) }}</span>
      <span class="footer-credit">贷方：{{ fmt(totalCredits) }}</span>
      <span class="footer-diff">差额：{{ fmt(Math.abs(balanceDiff)) }}</span>
      <span v-if="isBalanced" class="footer-status ok">✅ 平衡</span>
      <span v-else class="footer-status err">❌ 不平衡</span>
    </div>

    <!-- 审计说明 -->
    <el-card class="note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiNote">🤖AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea"
        :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写调整分录的审计说明：调整事项依据、错报性质、AJE/RJE 判断过程等。"
        @change="saveNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">🤖AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea"
        :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论：调整分录经复核借贷平衡、依据充分，已回写 G7-1 审定表。"
        @change="saveConclusion" />
    </el-card>

  </div>
</template>

<script setup lang="ts">
/**
 * G7TabAdjustment.vue — G7-3 调整分录汇总（源模板22行×10列，HTML动态行）
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/ Task 6.1
 * Requirements: 6.1, 6.4
 *
 * 功能：
 * - 对齐源 Excel 列（调整事项说明|类别|报表项目|科目名称|附注项目|借方|贷方|索引|备注）
 * - 借贷平衡实时校验 (isDebitCreditBalanced) + 差额≠0红色❌ / 差额=0绿色✅
 * - 动态行增删 (ElMessageBox.prompt 输入摘要确认)
 * - 导入导出 (sheet='G7-3', useG7ImportExport)
 * - 与集中调整分录模块双向同步，保存时按 1511/1512 分流回写 G7-1
 */
import {
  ref,
  computed,
  inject,
  onMounted,
  onBeforeUnmount,
  watch,
  type ComputedRef,
} from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  G7_ADJUSTMENT_ACCOUNT_OPTIONS,
  g7AccountCode,
  g7ImpairmentAccountCode,
} from '../../composables/g7AccountScope'
import type { TbSourceCodes } from '../../composables/shared/tbSourceCodes'
import { isDebitCreditBalanced, parseNum } from '../../composables/useG7FormulaEngine'
import { useG7ImportExport } from '../../composables/useG7ImportExport'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import { useWorkpaperAuditYear } from '../../composables/workpaperAuditYear'
import type { G7MainImportableSheet } from '../../composables/useG7ImportExport'
import { api } from '@/services/apiProxy'
import { adjustments as adjustmentPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'
import {
  G7_ADJUSTMENT_PUSHED_EVENT,
  adoptAllSuggestedDrafts,
  adoptSuggestedDraft,
  aggregateAccount as aggregateAccountPure,
  aggregateByInvestee,
  applyInvesteeWritebackToGroups,
  isPushableToModule,
  isSuggestedDraft,
  normalizeG73Entry,
  sourceKindLabel,
} from './g7AdjustmentModel'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ═══ 数据模型 ═══
interface G7AdjustmentEntry {
  id: string
  seq: number
  description: string
  category: '账项调整' | '报表调整' | '其他'
  reportItem: string
  noteItem: string
  indexRef: string
  sourceGroupId?: string
  /** 建议草稿来源：g7-14-suggested / g7-13-bargain-suggested */
  sourceKind?: string
  /** 被投资单位（建议分录 / 按单位回写） */
  investeeName?: string
  /** 兼容历史存量和导入导出契约 */
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

// ═══ 状态 ═══
const entries = ref<G7AdjustmentEntry[]>([])
const isDirty = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const syncing = ref(false)
const lastSyncMsg = ref('')
const auditYear = useWorkpaperAuditYear()

/** 科目码单一真源（宿主 provide 的四表溯源 → 解析结果；常量只作兜底）*/
const tbSourceCodes = inject<ComputedRef<TbSourceCodes | null>>(
  'g7TbSourceCodes',
  computed(() => null),
)
const accountGross = computed(() => g7AccountCode(tbSourceCodes.value))
const accountImpairment = computed(() => g7ImpairmentAccountCode(tbSourceCodes.value))
const ROWS_KEY = 'G7-3-rows'
const categoryOptions = ['账项调整', '报表调整', '其他'] as const
// 前四条（长投原值 / 减值准备 / 投资收益 / 资产减值损失）取共享声明，
// 与 g7AdjustmentModel 的归一化清单同源；此处只补本 Tab 额外提供的对方科目。
const accountOptions = [
  ...G7_ADJUSTMENT_ACCOUNT_OPTIONS,
  { code: '1012', name: '银行存款' },
  { code: '1122', name: '应收账款' },
  { code: '2241', name: '其他应付款' },
] as const

// ═══ 审计说明/结论 持久化（checklist_responses）══════════════════════════════
const NOTE_KEY = 'G7-3-adjustment-audit-note'
const CONCLUSION_KEY = 'G7-3-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function persistAudit(itemId: string, val: string): void {
  if (props.isReadonly || !props.wpId) return
  api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
    project_id: props.projectId || undefined,
    items: [{ item_id: itemId, conclusion: null, remark: val }],
  }, { _silent: true } as any).catch(() => {})
}

function saveNote(): void { persistAudit(NOTE_KEY, auditNote.value) }
function saveConclusion(): void { persistAudit(CONCLUSION_KEY, auditConclusion.value) }

async function loadAuditResponses(): Promise<void> {
  if (!props.wpId) return
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items = extractChecklistItems(res)
    for (const it of items) {
      if (it.item_id === NOTE_KEY && it.remark) auditNote.value = it.remark
      else if (it.item_id === CONCLUSION_KEY && it.remark) auditConclusion.value = it.remark
    }
  } catch { /* silent */ }
}

// ═══ 导入导出 ═══
const ie = useG7ImportExport({
  wpId: computed(() => props.wpId),
})

// ═══ 计算属性 ═══
const totalDebits = computed(() =>
  entries.value.reduce((sum, e) => sum + parseNum(e.debitAmount), 0),
)
const totalCredits = computed(() =>
  entries.value.reduce((sum, e) => sum + parseNum(e.creditAmount), 0),
)
const balanceDiff = computed(() => totalDebits.value - totalCredits.value)
const isBalanced = computed(() =>
  isDebitCreditBalanced(
    entries.value.map((e) => e.debitAmount),
    entries.value.map((e) => e.creditAmount),
  ),
)
const suggestedDraftCount = computed(() =>
  entries.value.filter((e) => isSuggestedDraft(e)).length,
)

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'G7',
  itemId: 'G7-3-rows',
  buildLineItems: () => entries.value.map((e) => ({
    standard_account_code: e.accountCode || undefined,
    account_name: e.accountName,
    report_line_code: e.reportItem || undefined,
    debit_amount: e.debitAmount,
    credit_amount: e.creditAmount,
  })),
  buildMeta: () => ({
    description: entries.value.find((e) => e.description)?.description || 'G7 长期股权投资调整',
    adjustmentType: entries.value.length > 0 && entries.value.every((e) => e.category === '报表调整') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

// ═══ 初始化 ═══
function generateId(): string {
  return `g7adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createEntry(description = ''): G7AdjustmentEntry {
  return {
    id: generateId(),
    seq: entries.value.length + 1,
    description,
    category: '账项调整',
    reportItem: '长期股权投资',
    noteItem: '',
    indexRef: 'G7-3',
    sourceKind: undefined,
    investeeName: undefined,
    entryType: 'AJE',
    date: '',
    summary: description,
    accountCode: accountGross.value,
    accountName: '长期股权投资',
    debitAmount: 0,
    creditAmount: 0,
    preparedBy: '',
    remark: '',
  }
}

function normalizeEntry(raw: any, index: number): G7AdjustmentEntry {
  return normalizeG73Entry(raw, index, { generateId }) as G7AdjustmentEntry
}

function extractChecklistItems(response: unknown): any[] {
  if (Array.isArray(response)) return response
  const res = response as { data?: unknown; items?: unknown }
  if (Array.isArray(res?.data)) return res.data
  if (Array.isArray(res?.items)) return res.items
  const nested = res?.data as { items?: unknown } | undefined
  if (Array.isArray(nested?.items)) return nested.items
  return []
}

function parseStoredEntries(raw: unknown): G7AdjustmentEntry[] {
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    const list = Array.isArray(parsed)
      ? parsed
      : Array.isArray((parsed as any)?.entries) ? (parsed as any).entries : []
    return list.map(normalizeEntry)
  } catch {
    return []
  }
}

async function loadEntries(): Promise<void> {
  let saved: G7AdjustmentEntry[] = []
  if (props.wpId) {
    try {
      const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
      const items = extractChecklistItems(res)
      const rowItem = items.find((item: any) => item.item_id === ROWS_KEY)
      const fromConclusion = parseStoredEntries(rowItem?.conclusion)
      const fromRemark = parseStoredEntries(rowItem?.remark)
      saved = fromConclusion.length >= fromRemark.length ? fromConclusion : fromRemark
    } catch { /* fallback to html data */ }
  }
  if (!saved.length) {
    saved = parseStoredEntries(
      props.htmlData?.adjustment?.entries
      ?? (props.htmlData as { entries?: unknown })?.entries,
    )
  }
  entries.value = saved.length ? saved : [createEntry()]
}

async function persistEntries(): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  const json = JSON.stringify(entries.value)
  await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
    project_id: props.projectId || undefined,
    items: [{ item_id: ROWS_KEY, conclusion: json, remark: json }],
  }, { _silent: true } as any)
}

onMounted(async () => {
  await Promise.all([loadEntries(), loadAuditResponses()])
  eventBus.on('adjustment:updated', handleModuleUpdated)
  eventBus.on('adjustment:saved', handleModuleUpdated)
  window.addEventListener(G7_ADJUSTMENT_PUSHED_EVENT, onAdjustmentPushed as EventListener)
})

watch(() => props.wpId, (id, prev) => {
  if (id && id !== prev) void loadEntries()
})

onBeforeUnmount(() => {
  eventBus.off('adjustment:updated', handleModuleUpdated)
  eventBus.off('adjustment:saved', handleModuleUpdated)
  window.removeEventListener(G7_ADJUSTMENT_PUSHED_EVENT, onAdjustmentPushed as EventListener)
  if (isDirty.value) void persistEntries().catch(() => {})
})

// ═══ 操作方法 ═══
function markDirty(): void {
  isDirty.value = true
}

function handleRowChanged(row: G7AdjustmentEntry): void {
  row.entryType = row.category === '报表调整' ? 'RJE' : 'AJE'
  row.summary = row.description
  markDirty()
}

function handleAccountChanged(row: G7AdjustmentEntry): void {
  const matched = accountOptions.find((item) => item.code === row.accountCode)
  if (matched) row.accountName = matched.name
  handleRowChanged(row)
}

function reSequence(): void {
  entries.value.forEach((e, i) => { e.seq = i + 1 })
}

/** 新增行 - 弹出ElMessageBox.prompt输入摘要 */
async function handleAddEntry(): Promise<void> {
  try {
    const { value: summary } = await ElMessageBox.prompt(
      '请输入新分录摘要：',
      '新增调整分录',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPlaceholder: '如：调整长期股权投资权益法确认',
        inputValidator: (v) => (!v?.trim() ? '摘要不能为空' : true),
      },
    )
    const newEntry = createEntry(summary.trim())
    entries.value.push(newEntry)
    markDirty()
  } catch {
    // 用户取消
  }
}

/** 删除行 - 二次确认 */
async function handleRemoveEntry(id: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该调整分录行？', '删除确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
    entries.value = entries.value.filter((e) => e.id !== id)
    reSequence()
    markDirty()
  } catch {
    // 用户取消
  }
}

function aggregateAccount(codePrefix: string): { ajeTotal: number; rjeTotal: number } {
  return aggregateAccountPure(entries.value, codePrefix, tbSourceCodes.value)
}

function dispatchWriteback(accountCode: string, totals: { ajeTotal: number; rjeTotal: number }): void {
  window.dispatchEvent(new CustomEvent('g7:adjustment-writeback', {
    detail: {
      accountCode,
      ...totals,
      totalAdjustment: totals.ajeTotal + totals.rjeTotal,
      byInvestee: aggregateByInvestee(entries.value, accountCode),
      entries: entries.value,
    },
  }))
}

function applyTotalsToGroup(group: any, totals: { ajeTotal: number; rjeTotal: number }): void {
  if (!Array.isArray(group?.rows) || group.rows.length === 0) return
  for (const row of group.rows) {
    row.closingAJE = 0
    row.closingRJE = 0
    row.closingAdjusted = parseNum(row.closingUnadjusted)
  }
  const target = group.rows[0]
  target.closingAJE = totals.ajeTotal
  target.closingRJE = totals.rjeTotal
  target.closingAdjusted = parseNum(target.closingUnadjusted) + totals.ajeTotal + totals.rjeTotal
}

/** 直接落库 G7-1，避免审定表未挂载时 CustomEvent 丢失 */
async function persistAdjudicationWriteback(
  gross: { ajeTotal: number; rjeTotal: number },
  impairment: { ajeTotal: number; rjeTotal: number },
): Promise<void> {
  if (!props.wpId || props.isReadonly) return
  const response: any = await api.get(
    `/api/workpapers/${props.wpId}/checklist-responses`,
    { _silent: true } as any,
  )
  const items = Array.isArray(response) ? response : response?.data || []
  const stored = items.find((item: any) => item.item_id === 'G7-1-adjudication-data')
  let data: any
  try {
    data = JSON.parse(stored?.remark || '')
  } catch {
    data = structuredClone(props.htmlData?.adjudication || { groups: [] })
  }
  const byInvesteeGross = aggregateByInvestee(entries.value, accountGross.value, tbSourceCodes.value)
  const byInvesteeImpair = aggregateByInvestee(entries.value, accountImpairment.value, tbSourceCodes.value)
  const saveItems: any[] = [{
    item_id: 'G7-1-adjustment-writeback',
    conclusion: null,
    remark: JSON.stringify({
      gross,
      impairment,
      byInvesteeGross,
      byInvesteeImpair,
      updatedAt: new Date().toISOString(),
    }),
  }]
  if (Array.isArray(data?.groups) && data.groups.length > 0) {
    const appliedGross = applyInvesteeWritebackToGroups(data.groups, byInvesteeGross, accountGross.value, tbSourceCodes.value)
    const appliedImpair = applyInvesteeWritebackToGroups(data.groups, byInvesteeImpair, accountImpairment.value, tbSourceCodes.value)
    if (!appliedGross) {
      const investmentGroup = data.groups.find((group: any) =>
        !['impairment', 'total'].includes(group.id || group.groupType),
      )
      applyTotalsToGroup(investmentGroup, gross)
    }
    if (!appliedImpair) {
      const impairmentGroup = data.groups.find((group: any) =>
        group.id === 'impairment' || group.groupType === 'impairment',
      )
      applyTotalsToGroup(impairmentGroup, impairment)
    }
    saveItems.push({
      item_id: 'G7-1-adjudication-data',
      conclusion: null,
      remark: JSON.stringify(data),
    })
  }
  await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
    project_id: props.projectId || undefined,
    items: saveItems,
  }, { _silent: true } as any)
}

/**
 * 可推送至 A13 的分录：已填金额且非「建议草稿」（未采纳的建议不构成错报）。
 */
const a13PushableEntries = computed(() =>
  entries.value.filter(
    (e) =>
      !isSuggestedDraft(e)
      && Math.max(Math.abs(parseNum(e.debitAmount)), Math.abs(parseNum(e.creditAmount))) > 0,
  ),
)
const a13PushableCount = computed(() => a13PushableEntries.value.length)

/**
 * 推送未更正错报至 A13 汇总。
 *
 * 走平台唯一消费者 `useA13MisstatementBridge`（挂在 WorkpaperEditor，形态 B：
 * `{ wpCode, accountCode, entries: [...] }`），由桥负责去重与落库；本表只负责
 * 组装载荷，不直接写 misstatements。
 */
function pushToA13(): void {
  if (props.isReadonly) return
  const rows = a13PushableEntries.value
  if (rows.length === 0) {
    ElMessage.warning('无可推送的调整分录（需已填金额且非建议草稿）')
    return
  }
  eventBus.emit('a13:push-misstatement', {
    wpCode: 'G7-3',
    accountCode: accountGross.value,
    accountName: '长期股权投资',
    projectId: props.projectId,
    source: 'G7-3 调整分录汇总',
    entries: rows.map((e) => ({
      description: e.description || e.summary || 'G7 长期股权投资调整',
      accountCode: e.accountCode || accountGross.value,
      accountName: e.accountName || '长期股权投资',
      debitAmount: parseNum(e.debitAmount),
      creditAmount: parseNum(e.creditAmount),
      indexRef: e.indexRef || 'G7-3',
    })),
    timestamp: Date.now(),
  })
  ElMessage.success(`已推送 ${rows.length} 笔至 A13 未更正错报汇总`)
}

function publishCreatedEvents(): void {
  for (const entry of entries.value) {
    if (!entry.debitAmount && !entry.creditAmount) continue
    eventBus.emit('adjustment:created', {
      wpCode: 'G7-3',
      entryType: entry.category === '报表调整' ? 'RJE' : 'AJE',
      amount: Math.max(entry.debitAmount, entry.creditAmount),
      accountCode: entry.accountCode,
      accountName: entry.accountName,
      description: entry.description,
      debitAmount: entry.debitAmount,
      creditAmount: entry.creditAmount,
      timestamp: Date.now(),
    })
  }
}

/** 将未同步的完整分录组单向写入集中 adjustments 表 */
async function pushToAdjustmentModule(): Promise<number> {
  if (!props.projectId || props.isReadonly) return 0
  const year = Number(auditYear.value)
  if (!Number.isFinite(year) || year < 1900) return 0
  const pending = entries.value.filter((entry) => isPushableToModule(entry))
  const groups = new Map<string, G7AdjustmentEntry[]>()
  for (const entry of pending) {
    const key = `${entry.category}||${entry.description || entry.id}`
    groups.set(key, [...(groups.get(key) || []), entry])
  }

  let pushed = 0
  for (const lines of groups.values()) {
    const debit = lines.reduce((sum, line) => sum + parseNum(line.debitAmount), 0)
    const credit = lines.reduce((sum, line) => sum + parseNum(line.creditAmount), 0)
    if (Math.abs(debit - credit) >= 0.01) continue
    try {
      const res: any = await api.post(adjustmentPaths.create(props.projectId), {
        adjustment_type: lines[0].category === '报表调整' ? 'rje' : 'aje',
        year,
        company_code: 'default',
        description: `[G7] ${lines[0].description || '长期股权投资调整'}`,
        line_items: lines.map((line) => ({
          standard_account_code: line.accountCode,
          account_name: line.accountName || undefined,
          debit_amount: line.debitAmount,
          credit_amount: line.creditAmount,
        })),
      }, { _silent: true } as any)
      const groupId = res?.entry_group_id ?? res?.data?.entry_group_id ?? res?.id
      if (!groupId) continue
      const id = String(groupId)
      entries.value = entries.value.map((entry) =>
        lines.some((line) => line.id === entry.id) ? { ...entry, sourceGroupId: id } : entry,
      )
      pushed++
    } catch {
      lastSyncMsg.value = '底稿已保存，但部分分录未能同步至集中模块'
    }
  }
  if (pushed > 0) {
    await persistEntries()
    eventBus.emit('adjustment:updated')
  }
  return pushed
}

/** 保存、同步集中模块并回写 G7-1 */
async function handleSaveWriteback(): Promise<void> {
  if (!isBalanced.value) {
    ElMessage.error('借贷不平衡，无法保存')
    return
  }
  try {
    await persistEntries()
    const gross = aggregateAccount(accountGross.value)
    const impairment = aggregateAccount(accountImpairment.value)
    await persistAdjudicationWriteback(gross, impairment)
    dispatchWriteback(accountGross.value, gross)
    dispatchWriteback(accountImpairment.value, impairment)
    publishCreatedEvents()
    const pushed = await pushToAdjustmentModule()
    isDirty.value = false
    ElMessage.success(
      `已保存并回写 G7-1；1511 AJE ${fmt(gross.ajeTotal)} / RJE ${fmt(gross.rjeTotal)}`
      + (pushed ? `，同步集中模块 ${pushed} 笔` : ''),
    )
  } catch {
    ElMessage.error('保存失败，请稍后重试')
  }
}

function categoryFromType(value: unknown): '账项调整' | '报表调整' | '其他' {
  const text = String(value || '').toLowerCase()
  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return '报表调整'
  if (text.includes('其他')) return '其他'
  return '账项调整'
}

function isG7Account(code: unknown): boolean {
  return /^151[12]/.test(String(code || ''))
}

/** 从集中模块拉取：命中 1511/1512 的分录组按完整借贷行导入 */
async function syncFromAdjustmentModule(): Promise<number> {
  if (!props.projectId || props.isReadonly) return 0
  syncing.value = true
  lastSyncMsg.value = ''
  try {
    const year = Number(auditYear.value) || new Date().getFullYear()
    const res: any = await api.get(adjustmentPaths.list(props.projectId), {
      params: { year, page: 1, page_size: 200 },
      _silent: true,
    } as any)
    const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
    if (!Array.isArray(items)) {
      lastSyncMsg.value = '未获取到调整分录'
      return 0
    }

    const imported: G7AdjustmentEntry[] = []
    for (const item of items) {
      const lines = item.line_items || item.lines || []
      if (!lines.some((line: any) => isG7Account(line.standard_account_code || line.account_code))) continue
      const groupId = String(item.entry_group_id || item.id || '')
      for (const line of lines) {
        const accountCode = String(line.standard_account_code || line.account_code || '')
        imported.push(normalizeEntry({
          id: `${groupId}-${imported.length}`,
          description: item.description || item.adjustment_no || '调整分录模块同步',
          category: categoryFromType(item.adjustment_type || item.type),
          reportItem: isG7Account(accountCode) ? '长期股权投资' : '',
          accountCode,
          accountName: line.account_name || accountCode,
          noteItem: '',
          debitAmount: line.debit_amount,
          creditAmount: line.credit_amount,
          indexRef: item.adjustment_no || 'G7-3',
          remark: '来自调整分录模块',
          sourceGroupId: groupId,
        }, imported.length))
      }
    }
    const manual = entries.value.filter((entry) => !entry.sourceGroupId)
    entries.value = [...manual, ...imported].map((entry, index) => ({ ...entry, seq: index + 1 }))
    await persistEntries()
    lastSyncMsg.value = imported.length ? `已同步 ${imported.length} 行` : '集中模块中无 1511/1512 相关分录'
    return imported.length
  } catch {
    lastSyncMsg.value = '同步失败，请稍后重试'
    return 0
  } finally {
    syncing.value = false
  }
}

async function handleSyncFromModule(): Promise<void> {
  const count = await syncFromAdjustmentModule()
  if (count > 0) ElMessage.success(`已从调整分录模块同步 ${count} 行`)
  else ElMessage.info(lastSyncMsg.value || '无相关分录')
}

function handleModuleUpdated(payload?: unknown): void {
  // 建议推送只发 g7:adjustment-pushed；若误带 source=suggested 则忽略，防止覆盖草稿
  const src = String((payload as any)?.source || (payload as any)?.detail?.source || '')
  if (src.includes('suggested') || src.includes('G7-14') || src.includes('G7-13')) return
  if (!props.isReadonly && props.projectId) void syncFromAdjustmentModule()
}

async function onAdjustmentPushed(ev: Event): Promise<void> {
  const detail = (ev as CustomEvent).detail || {}
  if (detail.mainWpId && detail.mainWpId !== props.wpId) return
  // 推送结果以 checklist 为准；丢弃本地 dirty，避免卸载时盖写
  isDirty.value = false
  await loadEntries()
  ElMessage.success(
    detail.count
      ? `已接收上游建议分录 ${detail.count} 行`
      : '已刷新 G7-3（上游建议分录已写入）',
  )
}

async function adoptSuggestedRow(rowId: string): Promise<void> {
  const row = entries.value.find((e) => e.id === rowId)
  if (!row || !isSuggestedDraft(row)) return
  const next = adoptSuggestedDraft(row)
  Object.assign(row, next)
  markDirty()
  await persistEntries()
  isDirty.value = false
  ElMessage.success('已采纳为手工分录')
}

async function adoptAllSuggested(): Promise<void> {
  if (props.isReadonly || suggestedDraftCount.value === 0) return
  try {
    await ElMessageBox.confirm(
      `将采纳 ${suggestedDraftCount.value} 行建议草稿（清除来源标记，可随后推入集中模块）。是否继续？`,
      '采纳全部建议',
      { confirmButtonText: '采纳', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  entries.value = adoptAllSuggestedDrafts(entries.value).map((e, i) => ({ ...e, seq: i + 1 }))
  markDirty()
  await persistEntries()
  isDirty.value = false
  ElMessage.success('已全部采纳')
}

async function clearSuggestedDrafts(): Promise<void> {
  if (props.isReadonly || suggestedDraftCount.value === 0) return
  try {
    await ElMessageBox.confirm(
      `将清除 ${suggestedDraftCount.value} 行建议草稿（保留手工分录与模块同步行）。是否继续？`,
      '清除建议草稿',
      { confirmButtonText: '清除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  entries.value = entries.value
    .filter((e) => !isSuggestedDraft(e))
    .map((e, i) => ({ ...e, seq: i + 1 }))
  if (!entries.value.length) entries.value = [createEntry()]
  markDirty()
  await persistEntries()
  isDirty.value = false
  ElMessage.success('已清除建议草稿')
}

async function handleAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  try {
    const res: any = await api.post(
      `/api/workpapers/${props.wpId}/g7-main/ai/adjustment-conclusion`,
      {
        existingContent: auditConclusion.value,
        relatedContext: {
          entries: entries.value,
          balanced: isBalanced.value,
          totalDebits: totalDebits.value,
          totalCredits: totalCredits.value,
        },
      },
    )
    const aiText = res?.data?.content ?? res?.content ?? ''
    if (aiText) {
      auditConclusion.value = auditConclusion.value
        ? `${auditConclusion.value}\n${aiText}`
        : aiText
      saveConclusion()
      ElMessage.success('AI结论已生成')
    } else {
      generateLocalConclusion()
    }
  } catch {
    generateLocalConclusion()
  }
}

async function handleAiNote(): Promise<void> {
  if (props.isReadonly) return
  try {
    const res: any = await api.post(
      `/api/workpapers/${props.wpId}/g7-main/ai/adjustment-note`,
      {
        existingContent: auditNote.value,
        relatedContext: {
          entries: entries.value,
          suggestedDraftCount: suggestedDraftCount.value,
        },
      },
    )
    const aiText = res?.data?.content ?? res?.content ?? ''
    if (aiText) {
      auditNote.value = auditNote.value ? `${auditNote.value}\n${aiText}` : aiText
      saveNote()
      ElMessage.success('AI说明已生成')
    } else {
      generateLocalNote()
    }
  } catch {
    generateLocalNote()
  }
}

function generateLocalConclusion(): void {
  const draft =
    `经复核，本期 G7-3 共 ${entries.value.length} 行调整分录，` +
    (isBalanced.value ? '借贷平衡。' : `借贷不平衡（差额 ${fmt(Math.abs(balanceDiff.value))}），待补齐。`) +
    (suggestedDraftCount.value
      ? `其中建议草稿 ${suggestedDraftCount.value} 行，需确认采纳或清除。`
      : '') +
    ` 1511 净影响 AJE ${fmt(aggregateAccount(accountGross.value).ajeTotal)} / RJE ${fmt(aggregateAccount(accountGross.value).rjeTotal)}。`
  auditConclusion.value = auditConclusion.value
    ? `${auditConclusion.value}\n${draft}`
    : draft
  saveConclusion()
  ElMessage.success('已生成本地结论')
}

function generateLocalNote(): void {
  const draft =
    `已执行调整分录完整性与借贷平衡复核；` +
    `建议草稿 ${suggestedDraftCount.value} 行、手工/模块同步 ${entries.value.length - suggestedDraftCount.value} 行。`
  auditNote.value = auditNote.value ? `${auditNote.value}\n${draft}` : draft
  saveNote()
  ElMessage.success('已生成本地说明')
}

/** 导入导出命令处理 */
function handleIECommand(cmd: string): void {
  const sheet: G7MainImportableSheet = 'G7-3'
  if (cmd === 'template') ie.exportTemplate(sheet)
  else if (cmd === 'export') ie.exportData(sheet)
  else if (cmd === 'import') fileInputRef.value?.click()
}

/** 文件选择后导入 */
async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const result = await ie.importData('G7-3', file)
  if (result) {
    await loadEntries()
    ElMessage.success(`数据已导入，共 ${result.rowCount ?? 0} 行`)
  }
  input.value = '' // 重置file input
}

/** 复核对话 */
function openReview(): void {
  openReviewDialog('G7-3-adjustment')
}

/** 格式化金额 */
function fmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

/** 格式化差额绝对值 */
function fmtAbs(v: number): string {
  return Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 表格行class（RJE / 建议草稿区分） */
function tableRowClassName({ row }: { row: G7AdjustmentEntry }): string {
  if (isSuggestedDraft(row)) return 'suggested-row'
  if (row.entryType === 'RJE') return 'rje-row'
  return ''
}
</script>

<style scoped>
.g7-tab-adjustment {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.audit-objective {
  margin-bottom: 12px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 借贷差额实时指示器 */
.balance-indicator {
  margin-bottom: 8px;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.balance-indicator.balanced {
  background: #f0f9eb;
  color: #67c23a;
  border: 1px solid #e1f3d8;
}

.balance-indicator.unbalanced {
  background: #fef0f0;
  color: #f56c6c;
  border: 1px solid #fde2e2;
}

.g7-adj-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.row-count {
  color: #909399;
  font-size: 12px;
}

.sync-msg {
  color: #909399;
  font-size: 12px;
}

/* 合计行 */
.g7-adj-footer {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
  padding: 10px 16px;
  background: #f0f9eb;
  border-radius: 4px;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
}

.g7-adj-footer.balance-fail {
  background: #fef0f0;
  border: 1px solid #f56c6c;
}

.footer-label {
  color: #606266;
}

.footer-debit,
.footer-credit,
.footer-diff {
  color: #303133;
}

.footer-status.ok {
  color: #67c23a;
  margin-left: auto;
}

.footer-status.err {
  color: #f56c6c;
  margin-left: auto;
  font-weight: 700;
}

.balance-diff-text {
  color: #f56c6c;
  font-weight: 700;
}

/* 审计说明/结论卡片 */
.note-card { margin-top: 12px; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-weight: 500; }
.desc-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.draft-tag {
  align-self: flex-start;
}

/* RJE行浅色区分 */
:deep(.rje-row) {
  background-color: #fdf6ec !important;
}
:deep(.suggested-row) {
  background-color: #f0f9eb !important;
}

/* 编制提示 */
.g7-guide-details {
  margin-top: 16px;
}

.g7-guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.g7-guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.g7-guide-content p {
  margin: 0;
}
</style>
