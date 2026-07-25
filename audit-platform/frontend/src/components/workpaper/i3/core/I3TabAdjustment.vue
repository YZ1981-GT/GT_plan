<template>
  <div class="i3-tab-adjustment">
    <details class="compile-hint" open>
      <summary>编制提示（对齐 Excel 商誉调整分录汇总表 I3-3）</summary>
      <div class="hint-content">
        <p>1. 列：调整事项说明 / 类别 / 报表项目 / 科目 / 附注项目 / 借方调整金额 / 贷方调整金额 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE）；「其他」按账项调整处理。</p>
        <p>3. 仅列示与商誉相关的审计调整；完整分录通常多行（如借：资产减值损失 / 贷：商誉）且整表及同「调整事项」组内借贷平衡。</p>
        <p>4. 可从 I3-6 生成减值草稿；可与调整分录模块双向同步；账项调整可推送 A13。</p>
        <p>5. 1711 账项/报表净额回写 I3-1 审定表 AJE/RJE；商誉减值一经确认不得转回（CAS8）。</p>
        <p>6. 「被投资单位」请与 I3-2 明细一致（可下拉选择）；从 I3-6 生成草稿时，若该 CGU 仅对应一家被投资单位将自动填入，便于回写 I3-2 审定调整。</p>
        <p class="excel-tip">【注】本底稿适用于调整分录较多、较复杂的项目，且仅列示与本报表项目相关的审计调整。项目组可根据实际情况选择是否使用。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确认商誉相关账项调整（AJE）与报表重分类（RJE）依据充分、借贷平衡、科目正确；同步至 I3-1 审定与调整分录模块；减值调整符合 CAS8 不可转回原则。"
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
      v-else-if="hasGwNet"
      type="success"
      :closable="false"
      class="balance-alert"
    >
      1711 账项净额 {{ fmtAmt(state.goodwillAjeNet.value) }}；报表净额 {{ fmtAmt(state.goodwillRjeNet.value) }}
      （资产类：借增贷减；减值贷记商誉→净额为负）
    </el-alert>

    <div class="adj-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="state.addRow()">
          + 新增调整分录
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          data-testid="i3-3-seed-i36"
          @click="onSeedFromI36"
        >
          从 I3-6 生成减值草稿
        </el-button>
        <I3SheetImportExport
          v-if="!isReadonly"
          sheet="I3-3"
          :wp-id="wpId"
          :project-id="projectId"
        />
        <el-select
          v-if="!isReadonly"
          v-model="impairmentCreditCode"
          size="small"
          style="width: 160px"
          placeholder="减值贷方科目"
          data-testid="i3-3-credit-account"
        >
          <el-option
            v-for="opt in state.accountOptions.filter(a => String(a.code).startsWith('1711'))"
            :key="opt.code"
            :label="`${opt.code} ${opt.name}`"
            :value="opt.code"
          />
        </el-select>
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
          data-testid="i3-3-save-sync"
          @click="handleSaveAndSync"
        >
          保存并回写 I3-1
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
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          :disabled="state.rows.value.length === 0"
          data-testid="i3-3-sync-i32"
          @click="handleSyncToI32"
        >
          回写 I3-2 账项调整
        </el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I3-1')">← 审定表</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I3-2')">明细表 →</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I3-6')">减值测试 →</el-button>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info" effect="plain">共 {{ state.rows.value.length }} 行</el-tag>
        <el-tag :type="state.isBalanced.value ? 'success' : 'danger'" size="small">
          {{ state.isBalanced.value ? '✓ 借贷平衡' : '✗ 借贷不平' }}
        </el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:I3-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
        <el-button size="small" type="default" link @click="openReview('I3-3')">💬 复核</el-button>
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

    <div v-if="state.lastSyncMsg.value || state.lastPushMsg.value || ajePendingHint" class="push-msg">
      {{ ajePendingHint || state.lastSyncMsg.value || state.lastPushMsg.value }}
    </div>

    <el-table
      :data="state.rows.value"
      border
      stripe
      size="small"
      class="adj-table"
      empty-text="暂无调整分录。可「新增」或「从 I3-6 生成减值草稿」。"
      @selection-change="onSelectionChange"
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
              placeholder="如：计提商誉减值-CGU甲 / 入账价值更正"
              @update:model-value="(v: string) => state.updateCell(row.rowId, 'description', v)"
            />
            <span v-else>{{ row.description || '—' }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="被投资单位" min-width="140">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.investee"
            size="small"
            filterable
            allow-create
            clearable
            default-first-option
            placeholder="匹配 I3-2"
            style="width:100%"
            @change="(v: string) => state.updateCell(row.rowId, 'investee', v ?? '')"
          >
            <el-option
              v-for="n in state.investeeOptions.value"
              :key="n"
              :label="n"
              :value="n"
            />
          </el-select>
          <span v-else>{{ row.investee || '—' }}</span>
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
            :precision="2"
            style="width:100%"
            @change="(v: number | undefined) => state.updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="90">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            placeholder="I3-6"
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

    <div class="balance-bar" :class="{ 'balance-ok': state.isBalanced.value, 'balance-err': !state.isBalanced.value }">
      <span>借方合计：<strong>{{ fmtAmt(state.debitTotal.value) }}</strong></span>
      <span>贷方合计：<strong>{{ fmtAmt(state.creditTotal.value) }}</strong></span>
      <span v-if="!state.isBalanced.value" class="diff-warn">
        差额：{{ fmtAmt(Math.abs(state.balanceDiff.value)) }}
      </span>
      <el-tag :type="state.isBalanced.value ? 'success' : 'danger'" size="small">
        {{ state.isBalanced.value ? '✓ 借贷平衡' : '✗ 借贷不平' }}
      </el-tag>
    </div>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="记录调整事项依据、与管理层沟通、减值不可转回复核等…"
        @blur="state.saveNote()"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input
        v-model="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="如：上述调整分录依据充分、借贷平衡，调整后商誉列报恰当；减值调整已回写 I3-1…"
        @blur="state.saveConclusion()"
      />
    </el-card>

    <div class="cross-ref-bar">
      <span class="cross-ref-label">跨底稿联动：</span>
      <GtIndexChip value="I3-1" @click="emit('navigate-sheet', 'I3-1')" />
      <span class="cross-ref-desc">商誉审定表</span>
      <GtIndexChip value="I3-2" @click="emit('navigate-sheet', 'I3-2')" />
      <span class="cross-ref-desc">明细账项调整</span>
      <GtIndexChip value="I3-6" @click="emit('navigate-sheet', 'I3-6')" />
      <span class="cross-ref-desc">减值测试</span>
      <GtIndexChip value="A13" @click="emit('navigate-sheet', 'A13')" />
      <span class="cross-ref-desc">错报汇总</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * I3TabAdjustment.vue — I3-3 商誉调整分录汇总
 * 对齐致同 Excel 列结构；逻辑层 useI3Adjustment
 */
import { computed, inject, ref, toRef, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI3Adjustment } from '../../composables/useI3Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import { useI3Detail } from '../../composables/useI3Detail'
import { useI3CrossSheet, aggregateGoodwillAjeByInvestee } from '../../composables/useI3CrossSheet'
import GtIndexChip from '../../GtIndexChip.vue'
import I3SheetImportExport from '../shared/I3SheetImportExport.vue'

const PENDING_SYNC_I33_KEY = 'i3-pending-sync-i33'

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
const selectedRowIds = ref<string[]>([])
const impairmentCreditCode = ref('1711')

const allResponsesRef = toRef(props, 'allResponses') as any
const state = useI3Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef,
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: toRef(props, 'projectId') as Ref<string>,
  year: centralYear,
  wpId: toRef(props, 'wpId') as Ref<string>,
  wpCode: 'I3',
  itemId: 'I3-3-rows',
  buildLineItems: () => state.rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: state.rows.value.find((r) => r.description)?.description || 'I3 商誉调整',
    adjustmentType: state.rows.value.length > 0 && state.rows.value.every((r) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

const injectedCross = inject<ReturnType<typeof useI3CrossSheet> | null>('i3CrossSheet', null)
const localCross = injectedCross || useI3CrossSheet(allResponsesRef)
const { ajeVariances, detailRows } = localCross

const { syncAjeFromI3_3 } = useI3Detail(
  toRef(props, 'wpId') as Ref<string>,
  allResponsesRef,
  { onSave: (itemId, value) => emit('save', itemId, value) },
)

const hasGwNet = computed(
  () => Math.abs(state.goodwillAjeNet.value) > 0.005 || Math.abs(state.goodwillRjeNet.value) > 0.005,
)

const ajePendingHint = computed(() => {
  const list = ajeVariances.value
  if (!list.length) return ''
  const n = list.length
  const names = list.slice(0, 2).map((v) => v.investee).join('、')
  return `与 I3-2 有 ${n} 处账项调整差异（${names}${n > 2 ? '…' : ''}），可回写明细`
})

function buildCguToInvestees(): Record<string, string[]> {
  const map: Record<string, string[]> = {}
  for (const r of detailRows.value) {
    const cgu = String(r.cguName || '').trim()
    const inv = String(r.investee || '').trim()
    if (!cgu || !inv) continue
    if (!map[cgu]) map[cgu] = []
    if (!map[cgu].includes(inv)) map[cgu].push(inv)
  }
  return map
}

function onSelectionChange(selection: { rowId: string }[]) {
  selectedRowIds.value = selection.map((r) => r.rowId)
}

function getSummary({ columns }: { columns: any[] }): string[] {
  return columns.map((col, idx) => {
    if (idx === 1) return '合计'
    if (col.label === '借方调整金额') return fmtAmt(state.debitTotal.value)
    if (col.label === '贷方调整金额') return fmtAmt(state.creditTotal.value)
    return ''
  })
}

async function handleSaveAndSync() {
  state.saveAndSync()
  try {
    await ElMessageBox.confirm(
      `已保存。1711 账项净额 ${fmtAmt(state.goodwillAjeNet.value)} / 报表净额 ${fmtAmt(state.goodwillRjeNet.value)}。是否跳转 I3-1 并自动同步 AJE/RJE？`,
      '回写 I3-1',
      { confirmButtonText: '跳转并同步', cancelButtonText: '仅保存', type: 'success' },
    )
    sessionStorage.setItem(PENDING_SYNC_I33_KEY, '1')
    emit('navigate-sheet', 'I3-1')
  } catch {
    ElMessage.success('已保存并发布（可稍后在审定表点击「从 I3-3 同步」）')
  }
}

function handleSyncToI32() {
  state.saveAndSync()
  const known = state.investeeOptions.value
  const sync = aggregateGoodwillAjeByInvestee(state.rows.value, known, buildCguToInvestees())
  const result = syncAjeFromI3_3(sync.byInvestee)
  const tips: string[] = []
  if (result.updated > 0) tips.push(`已回写 I3-2 共 ${result.updated} 行`)
  if (result.unmatched.length) {
    tips.push(`明细无此单位：${result.unmatched.slice(0, 3).join('、')}${result.unmatched.length > 3 ? '…' : ''}`)
  }
  if (result.unspecified) tips.push('请先填写被投资单位')
  if (!tips.length) {
    ElMessage.info('无差异可回写（请确认 1711 分录已填被投资单位）')
    return
  }
  ElMessage[result.updated > 0 ? (result.unmatched.length || result.unspecified ? 'warning' : 'success') : 'warning'](
    tips.join('；'),
  )
}

async function onSeedFromI36() {
  const opt = state.accountOptions.find((a) => a.code === impairmentCreditCode.value)
  const n = state.seedFromI36({
    creditAccountCode: impairmentCreditCode.value,
    creditAccountName: opt?.name,
  })
  if (n > 0) ElMessage.success(`已生成 ${n} 行减值调整草稿（贷方 ${impairmentCreditCode.value}）`)
  else ElMessage.info(state.lastSyncMsg.value || '无草稿可生成')
}

async function onSyncFromModule() {
  const n = await state.syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(state.lastSyncMsg.value)
  else ElMessage.info(state.lastSyncMsg.value || '无数据')
}

async function onPushToModule() {
  const n = await state.pushToAdjustmentModule()
  if (n > 0) ElMessage.success(state.lastSyncMsg.value)
  else ElMessage.warning(state.lastSyncMsg.value || '未推送')
}

function handlePushSelected() {
  state.pushToA13(selectedRowIds.value)
  ElMessage.info(state.lastPushMsg.value)
}

function handlePushAll() {
  state.pushToA13()
  ElMessage.info(state.lastPushMsg.value)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || Math.abs(val) < 0.005) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i3-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }

.compile-hint {
  margin-bottom: 12px; font-size: 12px;
  color: var(--el-text-color-secondary);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px; padding: 8px 12px; background: #fafafa;
}
.compile-hint summary { cursor: pointer; font-weight: 600; color: var(--el-text-color-primary); }
.hint-content { margin-top: 8px; line-height: 1.7; }
.hint-content p { margin: 0 0 4px; }
.excel-tip { color: #2563eb; margin-top: 6px !important; }

.objective-alert, .balance-alert { margin-bottom: 12px; }

.adj-toolbar {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 10px;
}
.toolbar-left, .toolbar-right { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.chip-wrap { display: inline-flex; }
.push-msg { font-size: 12px; color: var(--el-color-primary); margin-bottom: 8px; }

.adj-table { font-size: var(--wp-font-size, 13px); }
.adj-table :deep(.el-table__footer) { font-weight: 600; }
.amount-cell { font-variant-numeric: tabular-nums; }
.desc-cell { display: flex; align-items: center; gap: 4px; }
.src-tag { flex-shrink: 0; }

.balance-bar {
  display: flex; align-items: center; gap: 16px;
  padding: 10px 14px; margin-top: 12px; border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.balance-ok { background: var(--el-color-success-light-9, #f0f9eb); }
.balance-err { background: var(--el-color-danger-light-9, #fef0f0); }
.diff-warn { color: var(--el-color-danger); font-weight: 600; }

.note-card { margin-top: 12px; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 14px; margin-top: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px; border: 1px dashed var(--el-border-color); font-size: 12px;
}
.cross-ref-label { color: var(--el-text-color-secondary); font-weight: 500; }
.cross-ref-desc { color: var(--el-text-color-regular); margin-right: 8px; }
</style>
