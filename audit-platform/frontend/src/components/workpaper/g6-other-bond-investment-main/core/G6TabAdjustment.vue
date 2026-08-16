<template>
  <div class="g6-tab-adjustment">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认针对其他债权投资的审计调整依据充分、借贷平衡，并正确汇总回写至 G6-1 审定表。列结构对齐模板：调整事项说明 / 类别（报表调整·账项调整·其他）/ 报表项目 / 科目 / 附注项目 / 借贷金额。"
      style="margin-bottom: 12px"
    />
    <div class="section-head">
      <h3 class="sheet-title">G6-4 调整分录汇总</h3>
      <div class="head-actions">
        <el-button size="small" type="success" :disabled="isReadonly" @click="handleSaveWriteback">
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

    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom:8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmt(totalDebits) }} ≠ 贷方合计 {{ fmt(totalCredits) }}，差额
      <span class="balance-diff">{{ fmt(Math.abs(balanceDiff)) }}</span>
    </el-alert>

    <div class="g6-adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">
        + 新增分录
      </el-button>
      <span class="row-count">共 {{ entries.length }} 行</span>
    </div>

    <input ref="fileInputRef" type="file" accept=".xlsx" style="display:none" @change="onFileSelected" />

    <el-table
      :data="entries"
      border
      size="small"
      style="width:100%;font-size:13px"
      max-height="520"
      :row-class-name="tableRowClassName"
    >
      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            @change="(v: string) => updateCell(row.id, 'description', v)"
          />
          <span v-else>{{ row.description || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="类别" width="130">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            @change="(v: string) => updateCell(row.id, 'category', v)"
          >
            <el-option v-for="c in categoryOptions" :key="c" :value="c" :label="c" />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reportItem"
            size="small"
            @change="(v: string) => updateCell(row.id, 'reportItem', v)"
          />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="160">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.accountCode"
            size="small"
            filterable
            @change="(v: string) => updateCell(row.id, 'accountCode', v)"
          >
            <el-option
              v-for="opt in accountOptions"
              :key="opt.code"
              :value="opt.code"
              :label="`${opt.code} ${opt.name}`"
            />
          </el-select>
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注项目" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            @change="(v: string) => updateCell(row.id, 'noteItem', v)"
          />
          <span v-else>{{ row.noteItem || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方调整金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            style="width:100%"
            @change="(v: number | undefined) => updateCell(row.id, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            style="width:100%"
            @change="(v: number | undefined) => updateCell(row.id, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" min-width="110">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            @change="(v: string) => updateCell(row.id, 'indexRef', v)"
          />
          <span v-else-if="!row.indexRef">-</span>
          <div v-if="row.indexRef" class="row-index-chip">
            <GtIndexChip :value="row.indexRef" :context-project-id="projectId" />
          </div>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => updateCell(row.id, 'remark', v)"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="handleRemoveEntry(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="g6-adj-footer" :class="{ 'balance-fail': !isBalanced }">
      <span class="footer-label">合计</span>
      <span class="footer-debit">借方：{{ fmt(totalDebits) }}</span>
      <span class="footer-credit">贷方：{{ fmt(totalCredits) }}</span>
      <span v-if="isBalanced" class="footer-status ok">✓ 平衡</span>
      <span v-else class="footer-status err">
        ✗ 不平衡 | 差额：{{ fmt(Math.abs(balanceDiff)) }}
      </span>
    </div>

    <G6AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="adjustment-note"
      conclusion-ai-section="adjustment-conclusion"
      :related-context="{
        分录数: entries.length,
        借方合计: totalDebits,
        贷方合计: totalCredits,
        是否平衡: isBalanced,
        成本回写: writebackNets.costNet,
        利息回写: writebackNets.interestNet,
        减值回写: writebackNets.impairmentNet,
      }"
      note-placeholder="填写审计说明：调整分录的依据、借贷平衡与回写情况，拟调整/未调整事项及其影响。"
      note-hint="覆盖账项调整依据与回写审定表情况。"
      conclusion-placeholder="填写审计结论：A、未见异常。B、除上述调整事项予以调整外，其余未见异常。C、存在重大未调整事项，不可确认。"
      conclusion-hint="按 A/B/C 口径评价调整分录充分性。"
    />

    <details class="g6-guide-details">
      <summary>📋 编制提示</summary>
      <div class="g6-guide-content">
        <p>1. 列结构对齐 Excel：调整事项说明、类别（账项调整/报表调整/其他）、报表项目、科目名称、附注项目、借贷金额、索引、备注。</p>
        <p>2. 「账项调整」按科目分流回写 G6-1（150301/150303→成本，150302→利息，150305→减值，150304→公允价值）；「报表调整」不计入审定。</p>
        <p>3. 借贷须平衡后方可保存回写；科目选择后自动带出名称。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G6TabAdjustment.vue — G6-4 调整分录汇总（对齐 Excel 列 + useG6MainAdjustment）
 */
import { ref, computed, inject, onMounted, watch, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import G6AuditTextCards from '../G6AuditTextCards.vue'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import { useG6MainAdjustment } from '../../composables/useG6MainAdjustment'
import { useG6MainImportExport } from '../../composables/useG6MainImportExport'
import type { G6MainImportableSheet } from '../../composables/useG6MainImportExport'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import { dispatchG6SaveItems } from '../../composables/g6CrossHelpers'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses?: Map<string, ChecklistResponse>
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
watch(
  () => props.allResponses,
  (source) => {
    if (!source) return
    allResponses.value = source
  },
  { immediate: true, deep: true },
)

const NOTE_KEY = 'G6-4-adjustment-audit-note'
const CONCLUSION_KEY = 'G6-4-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function readSaved(key: string): string {
  const fromMap = allResponses.value.get(key)
  if (fromMap?.remark) return fromMap.remark
  const cr = props.htmlData?.checklist_responses
  if (cr && typeof cr === 'object' && (cr as Record<string, any>)[key]) {
    const v = (cr as Record<string, any>)[key]
    return typeof v === 'object' ? (v.remark ?? '') : String(v ?? '')
  }
  const resp = props.htmlData?.responses
  if (Array.isArray(resp)) {
    const found = resp.find((r: any) => r?.item_id === key)
    if (found?.remark) return found.remark
  }
  return ''
}

function dispatchSave(itemId: string, val: string): void {
  if (props.isReadonly) return
  const item: ChecklistResponse = { item_id: itemId, conclusion: null, remark: val }
  allResponses.value.set(itemId, item)
  try {
    dispatchG6SaveItems(props.wpId, [item])
  } catch { /* silent */ }
}

watch(auditNote, (val) => { dispatchSave(NOTE_KEY, val) })
watch(auditConclusion, (val) => { dispatchSave(CONCLUSION_KEY, val) })

const isReadonlyRef = toRef(props, 'isReadonly')
const {
  entries,
  totalDebits,
  totalCredits,
  balanceDiff,
  isBalanced,
  writebackNets,
  addEntry,
  removeEntry,
  updateCell,
  saveAndWriteback,
  loadEntries,
  accountOptions,
  categoryOptions,
} = useG6MainAdjustment({
  wpId: computed(() => props.wpId),
  allResponses,
  isReadonly: isReadonlyRef,
})

const isReadonly = computed(() => props.isReadonly)
const wpId = computed(() => props.wpId)
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: centralYear,
  wpId,
  wpCode: 'G6',
  itemId: 'G6-4-rows',
  buildLineItems: () => entries.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: entries.value.find((r) => r.description)?.description || 'G6 其他债权投资调整',
    adjustmentType: entries.value.length > 0 && entries.value.every((r) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

const ie = useG6MainImportExport({
  wpId: computed(() => props.wpId),
  onImported: () => { emit('imported') },
})

onMounted(() => {
  loadEntries()
  auditNote.value = readSaved(NOTE_KEY)
  auditConclusion.value = readSaved(CONCLUSION_KEY)
})

async function handleAddEntry(): Promise<void> {
  try {
    const { value: summary } = await ElMessageBox.prompt(
      '请输入调整事项说明：',
      '新增调整分录',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPlaceholder: '如：调整其他债权投资减值损失',
        inputValidator: (v) => (!v?.trim() ? '说明不能为空' : true),
      },
    )
    addEntry(summary.trim())
  } catch {
    /* 取消 */
  }
}

async function handleRemoveEntry(id: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该调整分录行？', '删除确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
    removeEntry(id)
  } catch {
    /* 取消 */
  }
}

function handleSaveWriteback(): void {
  saveAndWriteback()
}

function handleIECommand(cmd: string): void {
  const sheet: G6MainImportableSheet = 'G6-4'
  if (cmd === 'template') ie.exportTemplate(sheet)
  else if (cmd === 'export') ie.exportData(sheet)
  else if (cmd === 'import') fileInputRef.value?.click()
}

async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const result = await ie.importData('G6-4', file)
  if (result) emit('imported')
  input.value = ''
}

function openReview(): void {
  openReviewDialog('G6-4-adjustment')
}

function fmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function tableRowClassName({ row }: { row: { category?: string; entryType?: string } }): string {
  if (row.category === '报表调整' || row.entryType === 'RJE') return 'rje-row'
  return ''
}
</script>

<style scoped>
.g6-tab-adjustment {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
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

.g6-adj-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.row-count {
  color: #909399;
  font-size: 12px;
}

.g6-adj-footer {
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

.g6-adj-footer.balance-fail {
  background: #fef0f0;
  border: 1px solid #f56c6c;
}

.footer-label {
  color: #606266;
}

.footer-debit,
.footer-credit {
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

.balance-diff {
  color: #f56c6c;
  font-weight: 700;
}

:deep(.rje-row) {
  background-color: #fdf6ec !important;
}

.row-index-chip {
  margin-top: 4px;
}

.g6-guide-details {
  margin-top: 16px;
}

.g6-guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.g6-guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.g6-guide-content p {
  margin: 0;
}
</style>
