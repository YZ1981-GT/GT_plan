<template>
  <div class="i2-tab-adjustment">
    <details class="compile-hint" open>
      <summary>📋 编制提示（对齐 Excel 开发支出调整分录汇总表 I2-3）</summary>
      <div class="hint-content">
        <p>1. 列：调整事项说明 / 类别 / 报表项目 / 科目 / 附注项目 / 借方调整金额 / 贷方调整金额 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE）；「其他」按账项调整。</p>
        <p>3. 仅列示与开发支出相关的审计调整；完整分录通常多行（1717 + 对方科目，如费用化转出、转无形资产）且整表借贷平衡。</p>
        <p>4. 可「从调整分录模块同步 / 推送至调整分录模块」与集中台账双向联动；「推送 A13」将账项调整送入未更正错报汇总。</p>
        <p>5. 1717 账项/报表净额可回写 I2 审定表 AJE/RJE；借贷须平衡后方可推送中央模块。</p>
        <p class="excel-tip">提示：本底稿适用于调整分录较多、较复杂的项目，且仅列示与本报表项目相关的审计调整。项目组可根据实际情况选择是否使用。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：复核开发支出相关账项调整（AJE）与报表重分类（RJE）依据充分、借贷平衡，同步至调整分录模块与 I2 审定，并可推送 A13 错报汇总。"
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
      v-else-if="state.groupBalanceIssues.value.length"
      type="warning"
      :closable="false"
      class="balance-alert"
    >
      整表借贷平衡，但有 {{ state.groupBalanceIssues.value.length }} 组「调整事项」组内不平（推送时将跳过）：
      <span v-for="(g, i) in state.groupBalanceIssues.value.slice(0, 3)" :key="g.key">
        {{ i ? '；' : '' }}{{ g.entryType }}「{{ g.description }}」差额 {{ fmtAmt(g.diff) }}
      </span>
      <span v-if="state.groupBalanceIssues.value.length > 3">…</span>
    </el-alert>
    <el-alert
      v-else-if="hasAnyNet"
      type="success"
      :closable="false"
      class="balance-alert"
    >
      1717 账项净额 {{ fmtAmt(state.ajeNet.value) }}；报表净额 {{ fmtAmt(state.rjeNet.value) }}
    </el-alert>

    <div class="adj-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="state.addRow()">
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
          :disabled="state.rows.value.length === 0"
          @click="handleSaveAndSync"
        >
          保存并回写 I2
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
        <el-button size="small" @click="emit('navigate-sheet', 'I2-1')">← 审定表</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-2')">明细表 →</el-button>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info" effect="plain">审计年度 {{ auditYearDisplay }}</el-tag>
        <el-tag size="small" type="info" effect="plain">共 {{ state.rows.value.length }} 行</el-tag>
        <el-tag :type="state.isBalanced.value ? 'success' : 'danger'" size="small">
          {{ state.isBalanced.value ? '✓ 借贷平衡' : '✗ 借贷不平' }}
        </el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:I2-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:I2" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
        <el-button size="small" type="default" link @click="openReview('I2-3')">💬 复核</el-button>
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

    <el-table
      :data="state.rows.value"
      border
      stripe
      size="small"
      class="adj-table"
      empty-text="暂无调整分录。可「新增」或「从调整分录模块同步」。"
      @selection-change="onSelectionChange"
      :row-class-name="rowClassName"
      show-summary
      :summary-method="getSummary"
    >
      <el-table-column type="selection" width="40" :selectable="() => !isReadonly" />
      <el-table-column type="index" label="序" width="44" align="center" />

      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <div class="desc-cell">
            <el-tag v-if="row.sourceGroupId" size="small" type="info" class="src-tag">模块</el-tag>
            <el-input
              v-if="!isReadonly"
              :model-value="row.description"
              size="small"
              placeholder="如：费用化转出 / 资本化补记 / 转无形资产差异"
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
            <el-option v-for="opt in state.categoryOptions" :key="opt" :label="opt" :value="opt" />
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

      <el-table-column label="科目" width="200">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.accountCode"
            size="small"
            filterable
            allow-create
            default-first-option
            style="width:100%"
            @change="(v: string) => state.updateCell(row.rowId, 'accountCode', v)"
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
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            :controls="false"
            :precision="2"
            style="width:100%"
            @change="(v: number | undefined) => state.updateCell(row.rowId, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            :controls="false"
            :precision="2"
            style="width:100%"
            @change="(v: number | undefined) => state.updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="90">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'indexRef', v)"
          />
          <span v-else>{{ row.indexRef || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="90">
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

      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" text @click="state.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input
        v-model="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="记录调整依据、与管理层沟通、与 I2-1/I2-6/I2-7 勾稽等情况…"
        @blur="state.saveNote(state.auditNote.value)"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>四、审计结论</span></template>
      <el-input
        v-model="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="A、调整恰当且已同步审定/模块。B、除下列事项外未见异常。C、存在未解决调整差异。"
        @blur="state.saveConclusion(state.auditConclusion.value)"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * I2TabAdjustment.vue — I2-3 开发支出调整分录汇总
 * 对齐源 xlsx + I1-3 范式：中央调整模块双向联动 + EventBus + A13
 */
import { computed, inject, ref, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI2Adjustment, resolveI2AuditYear } from '../../composables/useI2Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{
  sheetName?: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
  year?: number
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
  (e: 'save'): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const runtime = inject(WorkpaperRuntimeContextKey, null)

const allResponsesRef = computed(() => props.allResponses)
const isReadonly = computed(() => !!props.isReadonly)

const auditYear = computed(() =>
  resolveI2AuditYear({
    propYear: props.year,
    runtimeYear: runtime?.year?.value,
    allResponses: props.allResponses,
  }),
)
const auditYearDisplay = computed(() => auditYear.value)

const state = useI2Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  isReadonly,
  auditYear,
  onSave: (itemId, value) => {
    void props.saveResponse('I2-3', { [itemId]: value })
  },
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: toRef(props, 'projectId'),
  year: auditYear,
  wpId: toRef(props, 'wpId'),
  wpCode: 'I2',
  itemId: 'I2-3-rows',
  buildLineItems: () => state.rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: state.rows.value.find((r) => r.description)?.description || 'I2 开发支出调整',
    adjustmentType: state.rows.value.length > 0 && state.rows.value.every((r) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

const selectedRowIds = ref<string[]>([])

const hasAnyNet = computed(() =>
  Math.abs(state.ajeNet.value) > 0.01 || Math.abs(state.rjeNet.value) > 0.01,
)

function openReview(id: string) {
  openReviewDialog(id)
}

function onSelectionChange(sel: Array<{ rowId: string }>) {
  selectedRowIds.value = sel.map((r) => r.rowId)
}

function rowClassName({ row }: { row: { category?: string } }) {
  return row.category === '报表调整' ? 'rje-row' : ''
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((col: any, idx: number) => {
    if (idx <= 1) return idx === 1 ? '合计' : ''
    if (col.label === '借方调整金额') return fmtAmt(state.debitTotal.value)
    if (col.label === '贷方调整金额') return fmtAmt(state.creditTotal.value)
    return ''
  })
}

async function onSyncFromModule() {
  const n = await state.syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(`已从调整分录模块同步 ${n} 行`)
  else if (state.lastSyncMsg.value) ElMessage.info(state.lastSyncMsg.value)
}

async function onPushToModule() {
  await ElMessageBox.confirm(
    '将本表未同步分录按「调整事项」分组推送至中央调整分录模块，确认？',
    '推送至调整分录模块',
    { type: 'warning' },
  )
  const n = await state.pushToAdjustmentModule()
  if (n > 0) {
    ElMessage.success(`已推送 ${n} 笔至调整分录模块`)
    emit('save')
  } else if (state.lastSyncMsg.value) {
    ElMessage.warning(state.lastSyncMsg.value)
  }
}

function handlePushSelected() {
  state.pushToA13(selectedRowIds.value)
  if (state.lastPushMsg.value) ElMessage.success(state.lastPushMsg.value)
}

function handlePushAll() {
  state.pushToA13()
  if (state.lastPushMsg.value) ElMessage.success(state.lastPushMsg.value)
}

function handleSaveAndSync() {
  state.saveAndPublish()
  emit('save')
  ElMessage.success('已保存并回写 I2（1717 AJE/RJE 净额）')
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i2-tab-adjustment { font-size: var(--wp-font-size, 13px); padding: 16px; }
.compile-hint {
  margin-bottom: 12px; font-size: 12px; color: #4b5563; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 14px; line-height: 1.7;
}
.compile-hint summary { cursor: pointer; font-weight: 600; color: #374151; }
.hint-content { margin-top: 8px; }
.hint-content p { margin: 0 0 4px; }
.excel-tip { color: #6b7280; }
.objective-alert, .balance-alert { margin-bottom: 10px; }
.adj-toolbar {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 12px; margin-bottom: 10px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.push-msg { font-size: 12px; color: #6b7280; margin-bottom: 8px; }
.adj-table { width: 100%; margin-bottom: 14px; }
.desc-cell { display: flex; align-items: center; gap: 4px; }
.src-tag { flex-shrink: 0; }
.note-card { margin-top: 12px; }
:deep(.rje-row) { background-color: #f0f9ff !important; }
</style>
