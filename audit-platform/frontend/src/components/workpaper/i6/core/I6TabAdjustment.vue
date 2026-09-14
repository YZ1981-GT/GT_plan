<template>
  <div class="i6-tab-adjustment">
    <details class="compile-hint" open>
      <summary>编制提示（对齐 Excel 研发费用调整分录汇总表 I6-3）</summary>
      <div class="hint-content">
        <p>1. 列：调整事项说明 / 类别 / 报表项目 / 科目 / 附注项目 / 借方调整金额 / 贷方调整金额 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE）；「其他」按账项调整处理。</p>
        <p>3. 仅列示与研发费用（6602）相关的审计调整；完整分录通常多行且整表及同「调整事项」组内借贷平衡。</p>
        <p>4. 「附注项目」请与 I6-2 费用类别一致，以便 I6-1 精确匹配 AJE/RJE（未匹配则按未审占比近似分摊）。</p>
        <p>5. 保存后回写 I6-1；账项调整可推送 A13；可与中央调整分录模块双向同步。</p>
        <p class="excel-tip">【注】本底稿适用于调整分录较多、较复杂的项目，且仅列示与本报表项目相关的审计调整。项目组可根据实际情况选择是否使用。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确认研发费用相关账项调整（AJE）与报表重分类（RJE）依据充分、借贷平衡、科目正确；同步至 I6-1 审定与调整分录模块。"
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
      6602 账项净额 {{ fmtAmt(state.ajeNet.value) }}；报表净额 {{ fmtAmt(state.rjeNet.value) }}
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
          保存并回写 I6-1
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
        <el-dropdown v-if="!isReadonly" size="small" trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="emit('navigate-sheet', 'I6-1')">← 审定表</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I6-2')">明细表 →</el-button>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info" effect="plain">审计年度 {{ auditYearDisplay }}</el-tag>
        <el-tag size="small" type="info" effect="plain">共 {{ state.rows.value.length }} 行</el-tag>
        <el-tag :type="state.isBalanced.value ? 'success' : 'danger'" size="small">
          {{ state.isBalanced.value ? '✓ 借贷平衡' : '✗ 借贷不平' }}
        </el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:I6-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="A13" @click="emit('navigate-sheet', 'A13')" /></span>
        <el-button size="small" type="default" link @click="openReview('I6-3')">复核</el-button>
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
      show-summary
      :summary-method="getSummary"
      :row-class-name="rowClassName"
      @selection-change="onSelectionChange"
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
              placeholder="如：跨期调整 / 费用化补记 / 资本化转出差异"
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
            <el-option v-for="opt in state.I6_CATEGORY_OPTIONS" :key="opt" :label="opt" :value="opt" />
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

      <el-table-column label="科目名称" width="200">
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
              v-for="opt in state.I6_ADJ_ACCOUNT_OPTIONS"
              :key="opt.code"
              :label="`${opt.code} ${opt.name}`"
              :value="opt.code"
            />
          </el-select>
          <span v-else>{{ row.accountCode }} {{ row.accountName }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注项目" width="130">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            filterable
            allow-create
            clearable
            placeholder="费用类别"
            style="width:100%"
            @change="(v: string) => state.updateCell(row.rowId, 'noteItem', v)"
          >
            <el-option v-for="opt in noteItemOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
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
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" @click="emit('navigate-sheet', row.indexRef)" />
          <span v-else>—</span>
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
        placeholder="记录调整依据、与管理层沟通、与 I6-1/I6-2/I6-5/I6-6 勾稽等情况…"
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
        :placeholder="state.suggestConclusionTemplate()"
        @blur="state.saveConclusion(state.auditConclusion.value)"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * I6TabAdjustment.vue — I6-3 研发费用调整分录汇总
 * 对齐致同 Excel + 中央调整分录模块双向联动 + I6-1 回写 + A13
 */
import { computed, inject, ref, toRef, onMounted } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { useI6Adjustment, resolveI6AuditYear } from '../../composables/useI6Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { I6_DETAIL_DEFAULT_CATEGORIES } from '../../composables/useI6Detail'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  save: [itemId: string, value: any]
}>()

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const isReadonly = computed(() => props.isReadonly)

const auditYear = computed(() =>
  resolveI6AuditYear({ propYear: props.year, allResponses: props.allResponses }),
)
const auditYearDisplay = computed(() => auditYear.value)

const state = useI6Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  isReadonly,
  auditYear,
  onSave: (itemId, value) => emit('save', itemId, value),
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: toRef(props, 'projectId'),
  year: auditYear,
  wpId: toRef(props, 'wpId'),
  wpCode: 'I6',
  itemId: 'I6-3-rows',
  buildLineItems: () => state.rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: state.rows.value.find((r) => r.description)?.description || 'I6 研发费用调整',
    adjustmentType: state.rows.value.length > 0 && state.rows.value.every((r) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

const selectedRowIds = ref<string[]>([])

const noteItemOptions = [
  ...I6_DETAIL_DEFAULT_CATEGORIES,
  '人员人工费用',
  '直接投入费用',
  '折旧费用与长期待摊费用',
  '无形资产摊销费用',
  '设计费用',
  '装备调试费用与试验费用',
  '委托外部研究开发费用',
  '其他费用',
]

const hasAnyNet = computed(() =>
  Math.abs(state.ajeNet.value) > 0.01 || Math.abs(state.rjeNet.value) > 0.01,
)

function openReview(id: string) { openReviewDialog(id) }

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
  if (n > 0) ElMessage.success(`已推送 ${n} 笔至调整分录模块`)
  else if (state.lastSyncMsg.value) ElMessage.warning(state.lastSyncMsg.value)
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
  if (!state.isBalanced.value && state.rows.value.length > 0) {
    ElMessage.warning('借贷不平衡，请先修正')
    return
  }
  state.saveAndPublish()
  ElMessage.success('已保存并回写 I6-1（6602 AJE/RJE 净额）')
}

async function handleImportExport(cmd: string): Promise<void> {
  if (cmd === 'export-template' || cmd === 'export-data') {
    try {
      const ep = cmd === 'export-template' ? 'export-template' : 'export-data'
      const res = await http.get(`/api/workpapers/${props.wpId}/i6/${ep}`, {
        params: { sheet: 'I6-3' },
        responseType: 'blob',
      })
      const blob = res.data instanceof Blob ? res.data : new Blob([res.data])
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `I6-3_调整分录${cmd === 'export-template' ? '模板' : '数据'}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      ElMessage.error('导出失败')
    }
  } else if (cmd === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      const fd = new FormData()
      fd.append('file', file)
      try {
        const res = await http.post(`/api/workpapers/${props.wpId}/i6/import-data`, fd, {
          params: { sheet: 'I6-3' },
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        const data = res.data?.data ?? res.data
        if (Array.isArray(data?.rows)) {
          state.importRows(data.rows)
          state.saveAndPublish()
        }
        ElMessage.success('导入成功')
      } catch {
        ElMessage.error('导入失败')
      }
    }
    input.click()
  }
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i6-tab-adjustment { font-size: var(--wp-font-size, 13px); padding: 16px; }
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
.note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
:deep(.rje-row) { background-color: #f0f9ff !important; }
</style>
