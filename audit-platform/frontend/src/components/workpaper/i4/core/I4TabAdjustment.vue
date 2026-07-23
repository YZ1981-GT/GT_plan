<template>
  <div class="i4-tab-adjustment">
    <details class="compile-hint" open>
      <summary>编制提示（对齐 Excel 长期待摊费用调整分录汇总表 I4-3）</summary>
      <div class="hint-content">
        <p>1. 列：调整事项说明 / 类别 / 报表项目 / 科目 / 附注项目 / 借方调整金额 / 贷方调整金额 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE）；「其他」按账项调整处理。</p>
        <p>3. 仅列示与长期待摊相关的审计调整；完整分录通常多行（如借：管理费用 / 贷：长期待摊）且整表及同「调整事项」组内借贷平衡。</p>
        <p>4. 可生成费用化/补提摊销草稿；可与调整分录模块双向同步；账项调整可推送 A13。</p>
        <p>5. 1801 账项/报表净额回写 I4-1 审定表 AJE/RJE；「明细项目」请与 I4-2 一致以便精确匹配。</p>
        <p class="excel-tip">【注】本底稿适用于调整分录较多、较复杂的项目，且仅列示与本报表项目相关的审计调整。项目组可根据实际情况选择是否使用。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确认长期待摊相关账项调整（AJE）与报表重分类（RJE）依据充分、借贷平衡、科目正确；同步至 I4-1 审定与调整分录模块。"
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
      v-else-if="hasLtpaNet"
      type="success"
      :closable="false"
      class="balance-alert"
    >
      1801 账项净额 {{ fmtAmt(state.ltpaAjeNet.value) }}；报表净额 {{ fmtAmt(state.ltpaRjeNet.value) }}
      （资产类：借增贷减；摊销/费用化贷记长期待摊→净额为负）
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
          @click="onSeedExpenseReclass"
        >
          费用化重分类草稿
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          @click="onSeedAmortDiff"
        >
          从 I4-6/7 差异补提
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          @click="onSeedCurrentPortion"
        >
          一年内到期重分类草稿
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
          保存并回写 I4-1
        </el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I4-1')">← 审定表</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I4-2')">明细表 →</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I4-5')">针对性检查 →</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I4-6')">摊销测算 →</el-button>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info" effect="plain">共 {{ state.rows.value.length }} 行</el-tag>
        <el-tag :type="state.isBalanced.value ? 'success' : 'danger'" size="small">
          {{ state.isBalanced.value ? '✓ 借贷平衡' : '✗ 借贷不平' }}
        </el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:I4-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
        <el-button size="small" type="default" link @click="openReview('I4-3')">💬 复核</el-button>
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
      empty-text="暂无调整分录。可「新增」或生成费用化/补提草稿。"
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
              placeholder="如：补提摊销-办公室装修 / 费用化重分类"
              @update:model-value="(v: string) => state.updateCell(row.rowId, 'description', v)"
            />
            <span v-else>{{ row.description || '—' }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="明细项目" min-width="120">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.projectName"
            size="small"
            filterable
            allow-create
            clearable
            default-first-option
            placeholder="匹配 I4-2"
            style="width:100%"
            @change="(v: string) => state.updateCell(row.rowId, 'projectName', v ?? '')"
          >
            <el-option
              v-for="n in state.projectNameOptions.value"
              :key="n"
              :label="n"
              :value="n"
            />
          </el-select>
          <span v-else>{{ row.projectName || '—' }}</span>
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
            placeholder="I4-5"
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
        placeholder="记录调整事项依据、与管理层沟通、与 I4-2/I4-5/I4-6 勾稽等…"
        @blur="state.saveNote()"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-header">
          <span>审计结论</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            @click="applyConclusionTpl"
          >套用结论模板</el-button>
        </div>
      </template>
      <el-input
        v-model="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="如：上述调整分录依据充分、借贷平衡，调整后长期待摊列报恰当；已回写 I4-1…"
        @blur="state.saveConclusion()"
      />
    </el-card>

    <div class="cross-ref-bar">
      <span class="cross-ref-label">跨底稿联动：</span>
      <GtIndexChip value="I4-1" @click="emit('navigate-sheet', 'I4-1')" />
      <span class="cross-ref-desc">审定表</span>
      <GtIndexChip value="I4-2" @click="emit('navigate-sheet', 'I4-2')" />
      <span class="cross-ref-desc">明细</span>
      <GtIndexChip value="I4-5" @click="emit('navigate-sheet', 'I4-5')" />
      <span class="cross-ref-desc">针对性检查</span>
      <GtIndexChip value="I4-6" @click="emit('navigate-sheet', 'I4-6')" />
      <span class="cross-ref-desc">摊销测算</span>
      <GtIndexChip value="A13" @click="emit('navigate-sheet', 'A13')" />
      <span class="cross-ref-desc">错报汇总</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabAdjustment.vue — I4-3 长期待摊费用调整分录汇总
 * 对齐致同 Excel 列结构；逻辑层 useI4Adjustment
 */
import { computed, inject, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI4Adjustment } from '../../composables/useI4Adjustment'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const emit = defineEmits<{
  'save': [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const selectedRowIds = ref<string[]>([])

const state = useI4Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  isReadonly: toRef(props, 'isReadonly'),
  auditYear: toRef(props, 'year'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const hasLtpaNet = computed(() =>
  Math.abs(state.ltpaAjeNet.value) > 0.005 || Math.abs(state.ltpaRjeNet.value) > 0.005,
)

function fmtAmt(v: number): string {
  if (v == null || Math.abs(v) < 0.005) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function openReview(id: string) {
  openReviewDialog(id)
}

function onSelectionChange(selection: Array<{ rowId: string }>) {
  selectedRowIds.value = selection.map((r) => r.rowId)
}

function getSummary({ columns }: { columns: any[] }): string[] {
  const sums: string[] = []
  columns.forEach((col, idx) => {
    if (idx <= 1) { sums[idx] = idx === 1 ? '合计' : ''; return }
    if (col.label === '借方调整金额') { sums[idx] = fmtAmt(state.debitTotal.value); return }
    if (col.label === '贷方调整金额') { sums[idx] = fmtAmt(state.creditTotal.value); return }
    sums[idx] = ''
  })
  return sums
}

function handlePushSelected() {
  state.pushToA13(selectedRowIds.value)
  ElMessage.success(state.lastPushMsg.value || '已推送')
}

function handlePushAll() {
  state.pushToA13()
  ElMessage.info(state.lastPushMsg.value || '已处理')
}

function handleSaveAndSync() {
  state.saveAndSync()
  ElMessage.success('已保存并触发回写 I4-1（请在审定表确认同步 AJE/RJE）')
}

async function onSyncFromModule() {
  const n = await state.syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(state.lastSyncMsg.value)
  else ElMessage.info(state.lastSyncMsg.value || '无新分录')
}

async function onPushToModule() {
  const n = await state.pushToAdjustmentModule()
  if (n > 0) ElMessage.success(state.lastSyncMsg.value)
  else ElMessage.warning(state.lastSyncMsg.value || '推送未完成')
}

async function onSeedExpenseReclass() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入：项目名称|金额（如：办公室装修|50000）',
      '费用化重分类草稿',
      { confirmButtonText: '生成', cancelButtonText: '取消', inputPattern: /\S+\|\d/, inputErrorMessage: '格式：项目名|金额' },
    )
    const [name, amtStr] = value.split('|')
    const n = state.seedExpenseReclass({
      projectName: name.trim(),
      amount: Number(amtStr),
      indexRef: 'I4-5',
    })
    if (n) ElMessage.success(`已生成 ${n} 行草稿`)
    else ElMessage.info('未生成（金额无效或同说明已存在）')
  } catch { /* cancelled */ }
}

function _parseAmortDiffRows(raw: any): Array<{ projectName: string; amount: number; indexRef: string }> {
  if (!Array.isArray(raw)) return []
  const out: Array<{ projectName: string; amount: number; indexRef: string }> = []
  for (const r of raw) {
    const name = String(r.projectName ?? r.itemName ?? r.name ?? '').trim()
    // 优先取本期差异（测算−账面）；正数表示需补提
    const diff = Number(
      r.periodDiff ?? r.diffPeriod ?? r.diff ?? r.variance ?? 0,
    )
    if (!name || !(diff > 0.005)) continue
    out.push({ projectName: name, amount: diff, indexRef: 'I4-6' })
  }
  return out
}

async function onSeedAmortDiff() {
  const raw6 = props.allResponses.get('I4-6-rows')
  const raw7 = props.allResponses.get('I4-7-rows')
  let diffs: Array<{ projectName: string; amount: number; indexRef: string }> = []
  try {
    const p6 = raw6?.remark ? JSON.parse(raw6.remark) : []
    const p7 = raw7?.remark ? JSON.parse(raw7.remark) : []
    diffs = [
      ..._parseAmortDiffRows(p6).map((d) => ({ ...d, indexRef: 'I4-6' })),
      ..._parseAmortDiffRows(p7).map((d) => ({ ...d, indexRef: 'I4-7' })),
    ]
  } catch {
    ElMessage.error('摊销测算数据解析失败')
    return
  }
  if (!diffs.length) {
    ElMessage.info('I4-6/I4-7 未发现需补提的正差异（测算＞账面）')
    return
  }
  try {
    await ElMessageBox.confirm(
      `发现 ${diffs.length} 项正差异，将生成补提摊销草稿（跳过已有同说明）。是否继续？`,
      '从摊销测算生成',
      { type: 'warning' },
    )
  } catch { return }
  const n = state.seedFromAmortDiff(diffs)
  ElMessage.success(n ? `已生成 ${n} 行草稿` : '无新增（可能已存在同说明）')
}

async function onSeedCurrentPortion() {
  const raw = props.allResponses.get('I4-2-rows')
  let detail: any[] = []
  try {
    detail = raw?.remark ? JSON.parse(raw.remark) : []
    if (!Array.isArray(detail)) detail = []
  } catch {
    ElMessage.error('I4-2 明细解析失败')
    return
  }
  const { extractI4CurrentPortionCandidates } = await import('../../composables/i4AdjudicationModel')
  const candidates = extractI4CurrentPortionCandidates(detail)
  if (!candidates.length) {
    ElMessage.info('I4-2 无剩余月数≤12且期末余额>0 的项目')
    return
  }
  try {
    await ElMessageBox.confirm(
      `发现 ${candidates.length} 项一年内到期候选。将生成报表重分类(RJE)草稿，须人工确认政策后入账（自然摊销通常可不强制重分类）。是否继续？`,
      '一年内到期重分类',
      { type: 'warning' },
    )
  } catch { return }
  const n = state.seedCurrentPortionReclass(candidates)
  ElMessage.success(n ? `已生成 ${n} 行 RJE 草稿` : '无新增（可能已存在同说明）')
}

function applyConclusionTpl() {
  state.auditConclusion.value = state.suggestConclusionTemplate()
  state.saveConclusion()
}
</script>

<style scoped>
.i4-tab-adjustment {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

.compile-hint {
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.hint-content { padding: 8px 0 0 4px; line-height: 1.7; }
.excel-tip { color: var(--el-color-primary); margin-top: 6px; }

.objective-alert, .balance-alert { margin-bottom: 10px; }

.adj-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.toolbar-left, .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; }

.push-msg {
  font-size: 12px;
  color: var(--el-color-warning);
  margin-bottom: 8px;
}

.adj-table { font-size: 12px; margin-bottom: 8px; }
.adj-table :deep(.el-table__footer td) { font-weight: 600; background: #f0f9ff; }
.desc-cell { display: flex; align-items: center; gap: 4px; }
.src-tag { flex-shrink: 0; }
.amount-cell { font-variant-numeric: tabular-nums; }

.balance-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 13px;
  background: var(--el-fill-color-light);
}
.balance-bar.balance-ok { border-left: 3px solid var(--el-color-success); }
.balance-bar.balance-err { border-left: 3px solid var(--el-color-danger); }
.diff-warn { color: var(--el-color-danger); font-weight: 600; }

.note-card { margin-bottom: 12px; }
.note-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.cross-ref-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 12px;
}
.cross-ref-label { color: var(--el-text-color-secondary); }
.cross-ref-desc { color: var(--el-text-color-placeholder); margin-right: 8px; }
</style>
