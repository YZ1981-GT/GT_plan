<template>
  <div class="i1-tab-adjustment">
    <details class="compile-hint" open>
      <summary>📋 编制提示（对齐 Excel 无形资产调整分录汇总表 I1-3）</summary>
      <div class="hint-content">
        <p>1. 列：调整事项说明 / 类别 / 报表项目 / 科目 / 附注项目 / 借方调整金额 / 贷方调整金额 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE）；「其他」按账项调整。</p>
        <p>3. 仅列示与无形资产相关的审计调整；完整分录通常多行（1701/1702/1703 + 对方科目）且整表借贷平衡。</p>
        <p>4. 可「从调整分录模块同步 / 推送至调整分录模块」与集中台账双向联动；「推送 A13」将账项调整送入未更正错报汇总。</p>
        <p>5. 1701/1702/1703 账项净额可回写 I1 审定表 AJE/RJE；借贷须平衡后方可推送中央模块。</p>
        <p class="excel-tip">提示：本底稿适用于调整分录较多、较复杂的项目，且仅列示与本报表项目相关的审计调整。项目组可根据实际情况选择是否使用。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：复核无形资产相关账项调整（AJE）与报表重分类（RJE）依据充分、借贷平衡，同步至调整分录模块与 I1 审定，并可推送 A13 错报汇总。"
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
      1701账项净额 {{ fmtAmt(state.costAjeNet.value) }}；1702账项净额 {{ fmtAmt(state.amortAjeNet.value) }}；1703账项净额 {{ fmtAmt(state.impairAjeNet.value) }}
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
          保存并回写 I1
        </el-button>
        <el-dropdown
          v-if="!isReadonly"
          size="small"
          :disabled="ieBusy"
          @command="handleExportCommand"
        >
          <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info" effect="plain">审计年度 {{ auditYearDisplay }}</el-tag>
        <el-tag size="small" type="info" effect="plain">共 {{ state.rows.value.length }} 行</el-tag>
        <el-tag :type="state.isBalanced.value ? 'success' : 'danger'" size="small">
          {{ state.isBalanced.value ? '✓ 借贷平衡' : '✗ 借贷不平' }}
        </el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:I1-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:I1" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
        <el-button size="small" type="default" link @click="openReview('I1-3')">💬 复核</el-button>
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
              placeholder="如：补记无形资产 / 摊销差异 / 减值补提"
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
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            :controls="false"
            :min="0"
            style="width:100%"
            @update:model-value="(v: number | undefined) => state.updateCell(row.rowId, 'debitAmount', v ?? 0)"
          />
          <span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            :controls="false"
            :min="0"
            style="width:100%"
            @update:model-value="(v: number | undefined) => state.updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            placeholder="I1-5"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'indexRef', v)"
          />
          <GtIndexChip
            v-else-if="row.indexRef"
            :value="row.indexRef"
            @click="emit('navigate-sheet', row.indexRef)"
          />
          <span v-else>—</span>
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

      <el-table-column v-if="!isReadonly" label="" width="52" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
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
        placeholder="记录调整依据、与管理层沟通、与 I1-5/I1-6/I1-10 勾稽等情况…"
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
 * I1TabAdjustment.vue — I1-3 调整分录汇总
 * 对齐源 xlsx + H8-3 范式：中央调整模块双向联动 + EventBus + A13
 */
import { computed, inject, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI1Adjustment, resolveI1AuditYear } from '../../composables/useI1Adjustment'
import { useI1ImportExport } from '../../composables/useI1ImportExport'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
  (e: 'save', itemId: string, value: any): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const runtime = inject(WorkpaperRuntimeContextKey, null)

const allResponsesRef = computed(() => props.allResponses)

/** props.year → scaffold → 摊销期间截止日年份 → 日历年 */
const auditYear = computed(() =>
  resolveI1AuditYear({
    propYear: props.year,
    runtimeYear: runtime?.year?.value,
    allResponses: props.allResponses,
  }),
)
const auditYearDisplay = computed(() => auditYear.value)

const state = useI1Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  isReadonly: toRef(props, 'isReadonly'),
  auditYear,
  onSave: (itemId, value) => emit('save', itemId, value),
})

const { importing, exporting, exportTemplate, exportData, importData } = useI1ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => state.load(),
})
const ieBusy = computed(() => importing.value || exporting.value)
const fileInputRef = ref<HTMLInputElement | null>(null)

async function handleExportCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('I1-3')
  else if (cmd === 'export-data') await exportData('I1-3')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) await importData('I1-3', file)
  ;(e.target as HTMLInputElement).value = ''
}

const selectedRowIds = ref<string[]>([])

const hasAnyNet = computed(() =>
  Math.abs(state.costAjeNet.value) > 0.01
  || Math.abs(state.amortAjeNet.value) > 0.01
  || Math.abs(state.impairAjeNet.value) > 0.01
  || Math.abs(state.costRjeNet.value) > 0.01,
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
  if (!state.isBalanced.value) {
    ElMessage.error('借贷不平衡，无法推送')
    return
  }
  try {
    await ElMessageBox.confirm(
      '将本表未同步分录按「调整事项」分组推送至中央调整分录模块，确认？',
      '推送至调整分录模块',
      { type: 'warning', confirmButtonText: '确认推送', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const n = await state.pushToAdjustmentModule()
  if (n > 0) ElMessage.success(`已推送 ${n} 笔至调整分录模块`)
  else if (state.lastSyncMsg.value) ElMessage.warning(state.lastSyncMsg.value)
}

function handlePushSelected() {
  state.pushToA13(selectedRowIds.value)
  ElMessage.success(state.lastPushMsg.value || '已推送')
}

function handlePushAll() {
  state.pushToA13()
  ElMessage.success(state.lastPushMsg.value || '已推送')
}

function handleSaveAndSync() {
  state.saveAndPublish()
  ElMessage.success('已保存并发布至审定表联动')
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-adjustment {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

.compile-hint {
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.hint-content { padding: 8px 4px 0; line-height: 1.7; }
.excel-tip { color: var(--el-color-primary); }

.objective-alert, .balance-alert { margin-bottom: 10px; }

.adj-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }

.push-msg {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--el-color-primary);
}

.adj-table { font-size: 12px; }
.adj-table :deep(.rje-row) { background: #fdf6ec; }
.adj-table :deep(.el-table__footer) { font-weight: 600; }

.desc-cell { display: flex; align-items: center; gap: 4px; }
.src-tag { flex-shrink: 0; }
.amount-cell { font-variant-numeric: tabular-nums; }

.note-card { margin-top: 12px; }
</style>
