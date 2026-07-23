<template>
  <div class="k1-tab-adjustment">
    <details class="compile-hint" open>
      <summary>📋 编制提示（对齐 Excel 其他应收款调整分录汇总表 K1-4）</summary>
      <div class="hint-content">
        <p>1. 列结构：调整事项说明 / 类别 / 报表项目 / 科目名称 / 附注项目 / 借方 / 贷方 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE），仅影响列报；「其他」按账项处理。</p>
        <p>3. 仅列示与其他应收款（1221）及坏账准备（1231）相关的审计调整；完整分录通常需多行且整表借贷平衡。</p>
        <p>4. 索引应交叉引用来源底稿（K1-2 明细、K1-8 坏账测算、K1-12 凭证检查等）。</p>
        <p>5. 可「从调整分录模块同步 / 推送至调整分录模块」；「保存并回写 K1-1」将自动分摊 1221/1231 净额至 K1-1 组合行。</p>
        <p class="excel-tip">提示：本底稿适用于调整分录较多、较复杂的项目，且仅列示与本报表项目相关的审计调整。项目组可根据实际情况选择是否使用。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：汇总其他应收款相关账项调整（AJE）与报表重分类（RJE），确保借贷平衡、依据充分，同步至调整分录模块并回写 K1-1 审定。"
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
      v-else-if="state.receivableAjeNet.value !== 0 || state.badDebtAjeNet.value !== 0"
      type="success"
      :closable="false"
      class="balance-alert"
    >
      1221 账项净额 {{ fmtAmt(state.receivableAjeNet.value) }}；1231 账项净额 {{ fmtAmt(state.badDebtAjeNet.value) }}；
      报表调整净额 {{ fmtAmt(state.receivableRjeNet.value) }}
    </el-alert>

    <div class="adj-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="state.addRow()">
          + 新增调整分录
        </el-button>
        <el-dropdown size="small" @command="handleIECommand">
          <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
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
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          :disabled="state.rows.value.length === 0"
          :loading="saving"
          @click="handleSaveAndSync"
        >
          保存并回写 K1-1
        </el-button>
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info" effect="plain">共 {{ state.rows.value.length }} 行</el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:K1-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:K1-1" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
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
      max-height="520"
      empty-text="暂无调整分录。可「新增」或「从调整分录模块同步」。"
      @selection-change="onSelectionChange"
      :row-class-name="rowClassName"
    >
      <el-table-column type="selection" width="40" :selectable="() => !isReadonly" />
      <el-table-column type="index" label="序" width="44" align="center" />

      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <div class="desc-cell">
            <el-tag v-if="row.sourceGroupId" size="small" type="info" class="src-tag">模块</el-tag>
            <el-tag v-else-if="row.sourceKind" size="small" type="warning" class="src-tag">来源</el-tag>
            <el-input
              v-if="!isReadonly"
              :model-value="row.description"
              size="small"
              placeholder="如：补记关联方其他应收 / 坏账准备调整"
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

      <el-table-column label="附注项目" width="110">
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
            :min="0"
            class="amt-input"
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
            :min="0"
            class="amt-input"
            @change="(v: number | undefined) => state.updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="88">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            placeholder="K1-12"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'indexRef', v)"
          />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
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
      <span>1221账项净额 {{ fmtAmt(state.receivableAjeNet.value) }}</span>
      <span>1231账项净额 {{ fmtAmt(state.badDebtAjeNet.value) }}</span>
    </div>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="概述调整分录编制依据、账项/报表调整事项及其对其他应收款审定数的影响；交叉索引来源检查表及与调整分录模块勾稽情况。"
        @change="saveAuditNote"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabAdjustment.vue — K1-4 其他应收款调整分录汇总表
 * 对齐 Excel 列结构 + 调整分录模块双向联动 + A13 / K1-1
 */
import { ref, computed, toRef, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { useK1Adjustment } from '../../composables/useK1Adjustment'
import { applyK14NetsToK11 } from '../../composables/k1AdjK11Writeback'
import { useK1ImportExport } from '../../composables/useK1ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number | null
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const runtime = inject(WorkpaperRuntimeContextKey, null)

const allResponsesRef = computed(() => props.allResponses)
const isReadonly = computed(() => props.isReadonly)
const projectId = computed(() => props.projectId)
const saving = ref(false)
const selectedRowIds = ref<string[]>([])

const auditYear = computed(() => {
  if (props.year != null && Number.isFinite(Number(props.year)) && Number(props.year) >= 1900) {
    return Math.trunc(Number(props.year))
  }
  const raw = runtime?.year?.value ?? null
  if (raw == null || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) && n >= 1900 ? Math.trunc(n) : null
})

const state = useK1Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  isReadonly: toRef(props, 'isReadonly'),
  auditYear,
  onSave: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
  onSyncToK11: () =>
    applyK14NetsToK11(props.allResponses, (itemId, value) => emit('save', itemId, value)),
})

const auditNote = computed({
  get: () => state.auditNote.value,
  set: (v: string) => { state.auditNote.value = v },
})

const wpIdRef = toRef(props, 'wpId')
const { isExporting, isImporting, exportTemplate, exportData, importData } = useK1ImportExport({
  wpId: wpIdRef,
})
const ieBusy = computed(() => isExporting.value || isImporting.value)
const fileInputRef = ref<HTMLInputElement | null>(null)
const SHEET = 'K1-4' as const

async function handleIECommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate(SHEET)
  else if (cmd === 'export-data') await exportData(SHEET)
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await importData(SHEET, file)
  if (result) state.load()
}

function onSelectionChange(rows: { rowId: string }[]) {
  selectedRowIds.value = rows.map((r) => r.rowId)
}

function handlePushSelected() {
  state.pushToA13(selectedRowIds.value)
  ElMessage.success(state.lastPushMsg.value || '已推送')
}

async function onSyncFromModule() {
  const n = await state.syncFromAdjustmentModule()
  ElMessage[n ? 'success' : 'info'](state.lastSyncMsg.value)
}

async function onPushToModule() {
  const n = await state.pushToAdjustmentModule()
  ElMessage[n ? 'success' : 'warning'](state.lastSyncMsg.value)
}

async function handleSaveAndSync() {
  if (!state.isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法回写')
    return
  }
  saving.value = true
  try {
    const k11 = state.publishAndSync()
    if (k11?.applied) {
      ElMessage.success(`${k11.message}（已自动回写 K1-1）`)
    } else {
      ElMessage.success('已保存净额键并通知 A13；K1-4 暂无 1221/1231 净额可回写 K1-1')
    }
  } finally {
    saving.value = false
  }
}

function saveAuditNote() {
  state.saveNote(auditNote.value)
}

function openReview() {
  openReviewDialog('K1-4-adjustment')
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: { row: { category?: string; entryType?: string } }): string {
  if (row.category === '报表调整' || row.entryType === 'RJE') return 'rje-row'
  return ''
}
</script>

<style scoped>
.k1-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.compile-hint { margin-bottom: 10px; }
.hint-content { padding: 8px 12px; background: #fffbeb; border-left: 3px solid #f59e0b; font-size: 12px; line-height: 1.8; }
.hint-content p { margin: 0 0 4px; }
.excel-tip { color: #2563eb; font-style: italic; }
.objective-alert { margin-bottom: 8px; }
.balance-alert { margin-bottom: 8px; }
.adj-toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; }
.push-msg { font-size: 12px; color: #409eff; margin-bottom: 6px; }
.desc-cell { display: flex; align-items: center; gap: 4px; }
.src-tag { flex-shrink: 0; }
.amt-input { width: 100%; }
.balance-bar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-top: 8px; padding: 10px 14px; border-radius: 4px; background: #f0f9eb; font-size: 13px; font-weight: 600; }
.balance-bar.balance-err { background: #fef0f0; border: 1px solid #f56c6c; }
.sep { color: #c0c4cc; }
.note-card { margin-top: 12px; }
:deep(.rje-row) { background-color: #fdf6ec !important; }
</style>
