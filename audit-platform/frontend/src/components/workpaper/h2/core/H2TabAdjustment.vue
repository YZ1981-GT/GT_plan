<template>
  <div class="h2-tab-adjustment">
    <!-- 编制提示（对齐 Excel H2-3） -->
    <details class="compile-hint" open>
      <summary>📋 编制提示（对齐 Excel 在建工程调整分录汇总表 H2-3）</summary>
      <div class="hint-content">
        <p>1. 本表对齐 Excel「在建工程调整分录汇总表」：调整事项说明 / 类别 / 报表项目 / 科目 / 附注项目 / 借贷 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE），仅影响列报；「其他」按账项调整处理。</p>
        <p>3. 仅列示与在建工程相关的审计调整；一笔完整分录通常需多行（1604 + 对方科目）且整表借贷平衡。</p>
        <p>4. 索引应交叉引用来源底稿（如 H2-5 转固时点、H2-8 增加、H2-9 减少、H2-15 减值）；亦可从上述底稿一键推送草稿。</p>
        <p>5. 可「从调整分录模块同步 / 推送至调整分录模块」与集中台账双向联动（含 1604 的完整分录组）；「推送 A13」将账项调整送入未更正错报汇总（报表调整默认不推）。</p>
        <p>6. 科目 1604 账项净额可回写 H2-1 审定表期末「账项调整」列；借贷须平衡后方可推送中央模块。</p>
        <p class="excel-tip">提示：本底稿适用于调整分录较多、较复杂的项目，且仅列示与本报表项目相关的审计调整。项目组可根据实际情况选择是否使用。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：复核在建工程相关账项调整（AJE）与报表重分类（RJE）依据充分、借贷平衡，同步至调整分录模块与 H2-1 审定，并可推送 A13 错报汇总。"
    />

    <el-alert
      v-if="!state.isBalanced.value && state.rows.value.length > 0"
      type="error"
      :closable="false"
      class="balance-alert"
    >
      借贷不平衡：借方 {{ fmtAmt(state.debitTotal.value) }} ≠ 贷方 {{ fmtAmt(state.creditTotal.value) }}，差额
      {{ fmtAmt(Math.abs(state.balanceDiff.value)) }}
    </el-alert>
    <el-alert
      v-else-if="state.cipAjeNet.value !== 0"
      type="success"
      :closable="false"
      class="balance-alert"
    >
      1604 账项净额 {{ fmtAmt(state.cipAjeNet.value) }}（可回写 H2-1 期末账项调整）；报表调整净额
      {{ fmtAmt(state.cipRjeNet.value) }}
    </el-alert>

    <!-- 工具栏 -->
    <div class="adj-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="state.addRow">
          + 新增调整分录
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          :loading="state.syncing.value"
          :disabled="!projectId"
          @click="onSyncFromModule"
        >
          从调整分录模块同步
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          plain
          :disabled="!state.isBalanced.value || !projectId || state.rows.value.length === 0"
          @click="onPushToModule"
        >
          推送至调整分录模块
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly || selectedRowIds.length === 0"
          @click="handlePushSelected"
        >
          推送至A13（{{ selectedRowIds.length }}条）
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly || state.rows.value.length === 0"
          @click="handlePushAll"
        >
          推送账项调整→A13
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="!state.isBalanced.value || state.rows.value.length === 0"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
          @click="syncToCentral"
        >
          同步到集中登记
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info" effect="plain">共 {{ state.rows.value.length }} 行</el-tag>
        <el-tag v-if="state.cipAjeNet.value !== 0" type="success" size="small" effect="plain">
          1604账项净额 {{ fmtAmt(state.cipAjeNet.value) }}
        </el-tag>
        <el-tag v-if="state.cipRjeNet.value !== 0" type="warning" size="small" effect="plain">
          1604报表净额 {{ fmtAmt(state.cipRjeNet.value) }}
        </el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-1" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
        <el-button size="small" circle @click="openReview('H2-3')">💬</el-button>
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

    <div v-if="state.lastSyncMsg.value || state.lastPushMsg.value" class="push-msg">
      {{ state.lastSyncMsg.value || state.lastPushMsg.value }}
    </div>

    <!-- 主表（Excel 列序） -->
    <el-table
      :data="state.rows.value"
      border
      stripe
      size="small"
      class="adj-table"
      empty-text="暂无调整分录。可「新增」、从 H2-9/H2-15 推送草稿，或「从调整分录模块同步」。"
      @selection-change="onSelectionChange"
      :row-class-name="rowClassName"
    >
      <el-table-column type="selection" width="40" :selectable="() => !isReadonly" />
      <el-table-column type="index" label="序" width="44" align="center" />

      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <div class="desc-cell">
            <el-tag v-if="isAutoDraft(row)" size="small" type="warning" class="src-tag">{{ autoDraftLabel(row) }}</el-tag>
            <el-tag v-else-if="row.sourceGroupId" size="small" type="info" class="src-tag">模块</el-tag>
            <el-input
              v-if="!isReadonly"
              :model-value="row.description"
              size="small"
              placeholder="如：补提减值 / 暂估转固决算调整"
              @update:model-value="(v: string) => state.updateCell(row.rowId, 'description', v)"
            />
            <span v-else>{{ row.description || '—' }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="类别" width="118">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            @change="(v: string) => state.updateCell(row.rowId, 'category', v)"
          >
            <el-option
              v-for="opt in state.categoryOptions"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <el-table-column label="报表项目" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reportItem"
            size="small"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'reportItem', v)"
          />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目" width="168">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.accountCode"
            size="small"
            filterable
            allow-create
            default-first-option
            placeholder="科目"
            @change="(v: string) => state.updateRow(row.rowId, { accountCode: v })"
          >
            <el-option
              v-for="opt in state.accountOptions"
              :key="opt.code"
              :label="`${opt.code} ${opt.name}`"
              :value="opt.code"
            />
          </el-select>
          <span v-else>{{ row.accountCode }} {{ row.accountName }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'noteItem', v)"
          />
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方调整金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            style="width:100%"
            @update:model-value="(v: number | undefined) => state.updateCell(row.rowId, 'debitAmount', v ?? 0)"
          />
          <span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            style="width:100%"
            @update:model-value="(v: number | undefined) => state.updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="88">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            placeholder="H2-9"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'indexRef', v)"
          />
          <span v-else>{{ row.indexRef || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'remark', v)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="state.removeRow(row.rowId)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷平衡 -->
    <div
      class="balance-bar"
      :class="{ 'balance-ok': state.isBalanced.value, 'balance-err': !state.isBalanced.value }"
    >
      <span>借方合计：{{ fmtAmt(state.debitTotal.value) }}</span>
      <span>贷方合计：{{ fmtAmt(state.creditTotal.value) }}</span>
      <el-tag :type="state.isBalanced.value ? 'success' : 'danger'" size="small">
        {{ state.isBalanced.value ? '借贷平衡' : `差额 ${fmtAmt(Math.abs(state.balanceDiff.value))}` }}
      </el-tag>
      <span class="sep">|</span>
      <span>1604账项净额 {{ fmtAmt(state.cipAjeNet.value) }}</span>
    </div>

    <p class="sheet-note">
      【注：本底稿适用于调整分录较多、较复杂的项目，且仅列示与在建工程相关的审计调整。项目组可根据项目实际情况选择是否使用该底稿。】
    </p>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="概述调整分录编制依据、账项/报表调整事项及其对在建工程审定数的影响；交叉索引来源检查表及与调整分录模块勾稽情况。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input
        v-model="auditConclusionText"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="A、调整分录借贷平衡且依据充分，已正确回写 H2-1 / 同步调整分录模块。B、除上述调整事项外未见异常。C、存在重大未调整事项或范围受限，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H2TabAdjustment.vue — H2-3 在建工程调整分录汇总表
 * 对齐 Excel 列结构 + 调整分录模块双向联动 + A13 / H2-1
 */
import { ref, computed, toRef, inject, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useH2Adjustment } from '../../composables/useH2Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import GtIndexChip from '../../GtIndexChip.vue'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number | null
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const runtime = inject(WorkpaperRuntimeContextKey, null)

const allResponsesRef = computed(() => props.allResponses)
const auditYear = computed(() => {
  if (props.year != null && Number.isFinite(Number(props.year)) && Number(props.year) >= 1900) {
    return Math.trunc(Number(props.year))
  }
  const raw = runtime?.year?.value ?? null
  if (raw == null || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) && n >= 1900 ? Math.trunc(n) : null
})

const state = useH2Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  isReadonly: toRef(props, 'isReadonly'),
  auditYear,
  onSave: (itemId: string, value: any) => {
    const existing = props.allResponses.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const remark = typeof value === 'string' ? value : JSON.stringify(value)
    props.allResponses.set(itemId, { ...existing, item_id: itemId, remark })
    saveResponse(itemId, value)
  },
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: toRef(props, 'projectId') as Ref<string>,
  year: centralYear,
  wpId: toRef(props, 'wpId') as Ref<string>,
  wpCode: 'H2',
  itemId: 'H2-3-rows',
  buildLineItems: () => state.rows.value.map((e: any) => ({
    standard_account_code: e.accountCode || undefined,
    account_name: e.accountName,
    debit_amount: e.debitAmount,
    credit_amount: e.creditAmount,
  })),
  buildMeta: () => ({
    description: state.rows.value.find((e: any) => e.description)?.description || 'H2 在建工程调整',
    adjustmentType: state.rows.value.length > 0 && state.rows.value.every((e: any) => e.category === '报表调整') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

const NOTE_KEY = 'H2-3-audit-note'
const CONCLUSION_KEY = 'H2-3-audit-conclusion'
const auditNote = ref('')
const auditConclusionText = ref('')
const selectedRowIds = ref<string[]>([])

onMounted(() => {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark ?? state.auditNote.value ?? ''
  const c = props.allResponses.get(CONCLUSION_KEY)
  auditConclusionText.value = String(c?.remark ?? c?.conclusion ?? '')
})

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  state.saveNote(val)
}

function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusionText.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  saveResponse(CONCLUSION_KEY, val)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '—'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onSelectionChange(sel: Array<{ rowId: string }>) {
  selectedRowIds.value = sel.map((r) => r.rowId)
}

function handlePushSelected() {
  state.pushToA13(selectedRowIds.value)
  ElMessage.success(state.lastPushMsg.value || '已推送')
}

function handlePushAll() {
  state.pushToA13()
  ElMessage.success(state.lastPushMsg.value || '已推送账项调整')
}

async function onSyncFromModule() {
  const n = await state.syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(`已从调整分录模块同步 ${n} 行`)
  else ElMessage.info(state.lastSyncMsg.value || '无相关分录')
}

async function onPushToModule() {
  if (!state.isBalanced.value) {
    ElMessage.error('借贷不平衡，无法推送')
    return
  }
  const { pushed } = await state.confirmAndPush()
  if (pushed > 0) ElMessage.success(`已推送 ${pushed} 笔至调整分录模块，并通知 H2-1`)
  else ElMessage.info(state.lastSyncMsg.value || '无可推送分录（可能已同步或分组不平衡）')
}

function isAutoDraft(row: { remark?: string; indexRef?: string }): boolean {
  const r = String(row.remark || '')
  return r.includes('H2-9-aje-auto') || r.includes('H2-15-aje-auto') || r.includes('aje-auto')
}

function autoDraftLabel(row: { remark?: string; indexRef?: string }): string {
  const r = String(row.remark || '')
  if (r.includes('H2-15') || String(row.indexRef || '').includes('H2-15')) return 'H2-15'
  if (r.includes('H2-9') || String(row.indexRef || '').includes('H2-9')) return 'H2-9'
  return '草稿'
}

function rowClassName({ row }: { row: { remark?: string; sourceGroupId?: string } }): string {
  if (isAutoDraft(row)) return 'row-auto-draft'
  if (row.sourceGroupId) return 'row-from-module'
  return ''
}

function openReview(id: string) {
  openReviewDialog(id)
}
</script>

<style scoped>
.h2-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.compile-hint {
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 12px;
  background: var(--el-fill-color-blank);
}
.compile-hint summary { cursor: pointer; font-weight: 600; color: var(--el-text-color-primary); }
.hint-content { margin-top: 8px; line-height: 1.6; }
.hint-content p { margin: 4px 0; }
.excel-tip { color: var(--el-color-warning-dark-2); margin-top: 8px !important; }
.objective-alert, .balance-alert { margin-bottom: 12px; }
.adj-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  gap: 8px;
  flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.push-msg { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.adj-table { font-size: var(--wp-font-size, 13px); }
.desc-cell { display: flex; flex-direction: column; gap: 4px; }
.src-tag { align-self: flex-start; }
.amount-cell { font-variant-numeric: tabular-nums; }
.balance-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 0;
  margin-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  font-size: 13px;
}
.balance-ok .sep, .balance-err .sep { color: var(--el-text-color-placeholder); }
.balance-err { color: var(--el-color-danger); }
.sheet-note {
  margin: 12px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.note-card { margin-bottom: 12px; }
:deep(.row-auto-draft) { background: var(--el-color-warning-light-9) !important; }
:deep(.row-from-module) { background: var(--el-color-info-light-9) !important; }
</style>
