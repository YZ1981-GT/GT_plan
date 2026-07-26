<template>
  <div class="h6-tab-adjudication">
    <details class="guidance-details">
      <summary>📋 编制提示（对齐致同 Excel 审定表 H6-1）</summary>
      <div class="guidance-content">
        <p>1. 结构：项目行 ← H6-2 明细；列组为期初/期末×未审·账项调整·审定 + 审定变动额/率。</p>
        <p>2. 审定数=未审数+账项调整；变动额=期末审定−期初审定；变动率对齐 Excel（期初为0时特殊处理）。</p>
        <p>3. 优先「从 H6-2 回填项目」；H6-3 确认后「回写期末账项调整」（1606 净额按未审权重分摊）。</p>
        <p>4. 1606 为过渡科目，期末审定应为 0；变动率≥{{ state.CHANGE_RATE_THRESHOLD }}% 须在说明(1)解释；与报表核对填入(3)。</p>
        <p>5.「带入调整」：从集中登记按科目 1606 拉取调整分录（资产借方净额=借−贷），逐笔分配到各项目的期末账项调整（增量累加），带入后审定数自动更新并联动附注。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实固定资产清理（1606 过渡科目）期末余额的存在、完整与计价；审定后结转完整（期末应为0），与 H6-2/H6-3/TB/报表及 H10 处置损益勾稽，为列报提供审定依据。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          v-if="!props.isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleSyncFromH62"
        >
          从 H6-2 回填项目
        </el-button>
        <el-button
          v-if="!props.isReadonly"
          size="small"
          plain
          :disabled="h63Sync.rowCount === 0 && h63Sync.clearingAjeNet === 0 && h63Sync.clearingRjeNet === 0"
          @click="syncFromH63"
        >
          从 H6-3 回写期末账项调整
        </el-button>
        <el-button
          v-if="!props.isReadonly"
          size="small"
          plain
          :loading="seedingFa"
          @click="handleSeedFaFromH1"
        >
          带入固定资产净值(H1-1)
        </el-button>
        <el-button
          v-if="!props.isReadonly && state.significantChangeItems.value.length"
          size="small"
          plain
          @click="handleApplySignificantNote"
        >
          重大变动→说明(1)
        </el-button>
        <el-button
          v-if="!props.isReadonly"
          size="small"
          type="primary"
          plain
          :loading="adjPull.loading.value"
          @click="openBringInAdjustment"
        >
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-tag v-if="h63Sync.rowCount > 0 || h63Sync.clearingAjeNet !== 0" size="small" type="info" effect="plain">
          H6-3：1606账项净额 {{ fmtAmt(h63Sync.clearingAjeNet) }}（{{ h63Sync.rowCount }}行）
        </el-tag>
        <el-tag
          v-if="state.significantChangeItems.value.length"
          size="small"
          type="danger"
          effect="plain"
        >
          变动≥{{ state.CHANGE_RATE_THRESHOLD }}%：{{ state.significantChangeItems.value.length }} 项
        </el-tag>
        <el-tag
          v-if="state.transitCheck.value.isZero"
          size="small"
          type="success"
          effect="plain"
        >
          ✓ 期末余额为0
        </el-tag>
        <el-tag v-else size="small" type="danger" effect="plain">
          ⚠ 期末≠0
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H6-1" :context-project-id="props.projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H6-2" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H6-3" :validate="false" /></span>
        <el-tag size="small" type="info">项目 {{ state.detailRows.value.length }} 项</el-tag>
      </div>
    </div>

    <el-alert
      v-if="!state.transitCheck.value.isZero"
      type="error"
      :closable="false"
      show-icon
      class="warn-alert"
      :title="state.transitCheck.value.warning"
    />
    <el-alert
      v-if="!state.h10CrossCheck.value.isMatch && h10HasData"
      type="warning"
      :closable="false"
      show-icon
      class="warn-alert"
      :title="state.h10CrossCheck.value.warning"
    />
    <el-alert
      v-if="crossSheetWarning"
      type="warning"
      :closable="false"
      show-icon
      class="warn-alert"
      :title="crossSheetWarning"
    />

    <!-- 审定主表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>固定资产清理审定（科目1606）</span>
          <el-button size="small" circle @click="openReview('H6-1')">💬</el-button>
        </div>
      </template>

      <el-table
        :data="state.displayRows.value"
        border
        stripe
        size="small"
        class="adj-table"
        :row-class-name="rowClassName"
      >
        <el-table-column prop="name" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !props.isReadonly"
              v-model="row.name"
              size="small"
              @change="state.updateCell(row.rowId, 'name', row.name)"
            />
            <span v-else :class="{ 'subtotal-label': row.isTotal }">{{ row.name }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isTotal && !props.isReadonly"
                v-model="row.beginUnadjusted"
                :controls="false"
                size="small"
                class="amt-input"
                @change="state.updateCell(row.rowId, 'beginUnadjusted', $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.beginUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isTotal && !props.isReadonly"
                v-model="row.beginAdjustment"
                :controls="false"
                size="small"
                class="amt-input"
                @change="state.updateCell(row.rowId, 'beginAdjustment', $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.beginAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定=未审+账项调整">{{ fmtAmt(row.beginAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isTotal && !props.isReadonly"
                v-model="row.endUnadjusted"
                :controls="false"
                size="small"
                class="amt-input"
                @change="state.updateCell(row.rowId, 'endUnadjusted', $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.endUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isTotal && !props.isReadonly"
                v-model="row.endAdjustment"
                :controls="false"
                size="small"
                class="amt-input"
                @change="state.updateCell(row.rowId, 'endAdjustment', $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.endAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="110" align="right">
            <template #default="{ row }">
              <span
                class="formula-cell"
                :class="{ 'error-amount': row.isTotal && !state.transitCheck.value.isZero }"
                title="审定=未审+账项调整"
              >{{ fmtAmt(row.endAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="本期审定数与上期审定数的比较" align="center">
          <el-table-column label="变动额" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="变动额=期末审定−期初审定">{{ fmtAmt(row.auditedChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动率" min-width="100" align="right">
            <template #default="{ row }">
              <span
                class="formula-cell"
                :class="{ 'sig-rate': row.isSignificant }"
                title="变动率对齐 Excel IF 公式"
              >{{ fmtRate(row.auditedChangeRate) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="!props.isReadonly" label="" width="45">
          <template #default="{ row }">
            <el-button
              v-if="!row.isTotal"
              size="small"
              type="danger"
              link
              @click="state.deleteRow(row.rowId)"
            >✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!props.isReadonly" class="add-row-bar">
        <el-button size="small" @click="handleAddRow">+ 新增项目</el-button>
      </div>
      <p class="hint-line">
        变动率绝对值≥{{ state.CHANGE_RATE_THRESHOLD }}% 须在下方说明(1)解释原因；过渡科目合计期末审定应为 0。
      </p>
    </el-card>

    <!-- TB 取数核对 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>TB取数核对（科目1606）</span></div>
      </template>
      <div class="tb-compare">
        <div class="tb-row">
          <span class="tb-label">期末审定数(H6-1)：</span>
          <span class="tb-value" :class="{ 'error-amount': !state.transitCheck.value.isZero }">
            {{ fmtAmt(state.endBalanceAudited.value) }}
          </span>
        </div>
        <div class="tb-row">
          <span class="tb-label">期初审定数(H6-1)：</span>
          <span class="tb-value">{{ fmtAmt(state.beginBalanceAudited.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">TB未审数(1606)：</span>
          <span class="tb-value">{{ fmtAmt(state.tbUnadjusted.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">TB审定数(1606)：</span>
          <span class="tb-value">{{ fmtAmt(state.tbAudited.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">差异(期末−TB审定)：</span>
          <span class="tb-value" :class="{ 'error-amount': !state.isTbMatch.value }">
            {{ fmtAmt(state.tbDiff.value) }}
          </span>
        </div>
        <div class="tb-row">
          <span class="tb-label">清理净损益(↔H10)：</span>
          <span class="tb-value">{{ fmtAmt(state.disposalGainLoss.value) }}</span>
        </div>
      </div>
    </el-card>

    <!-- (3) 与经审计的财务报表核对 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>(3) 与经审计的财务报表核对</span>
          <span class="section-hint">固定资产净值 + 固定资产清理 ↔ 报表列报（可从 H1-1 带入净值）</span>
        </div>
      </template>
      <el-table :data="state.fsCompareRows.value" size="small" border>
        <el-table-column prop="label" label="项目" min-width="220" />
        <el-table-column label="期末数" align="right" min-width="140">
          <template #default="{ row }">
            <template v-if="row.editable && !props.isReadonly">
              <el-input-number
                :model-value="row.kind === 'fa' ? state.fsReconcile.value.faNetEndAudited : state.fsReconcile.value.fsEndAmount"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number) => onFsChange(row.kind, 'end', v ?? 0)"
              />
            </template>
            <span
              v-else
              :class="{ 'error-amount': row.kind === 'diff' && Math.abs(row.endAudited) > 0.01 }"
            >{{ fmtAmt(row.endAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初数" align="right" min-width="140">
          <template #default="{ row }">
            <template v-if="row.editable && !props.isReadonly">
              <el-input-number
                :model-value="row.kind === 'fa' ? state.fsReconcile.value.faNetBeginAudited : state.fsReconcile.value.fsBeginAmount"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number) => onFsChange(row.kind, 'begin', v ?? 0)"
              />
            </template>
            <span
              v-else
              :class="{ 'error-amount': row.kind === 'diff' && Math.abs(row.beginAudited) > 0.01 }"
            >{{ fmtAmt(row.beginAudited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 1、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>1、审计说明</span>
          <el-button size="small" circle @click="openReview('H6-1-note')">💬</el-button>
        </div>
      </template>
      <div class="qual-grid">
        <div class="qual-item">
          <label>
            (1) 固定资产清理期末余额较期初余额增加（负数为减少）主要原因
            <span class="req-hint">（比例超过{{ state.CHANGE_RATE_THRESHOLD }}%）</span>
          </label>
          <el-input
            v-model="state.qualitativeNotes.value.fluctuation"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            :disabled="props.isReadonly"
            :placeholder="fluctuationPlaceholder"
            @blur="state.saveQualitativeNotes()"
          />
        </div>
        <div class="qual-item">
          <label>(2) 情况说明</label>
          <el-input
            v-model="state.qualitativeNotes.value.situation"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="props.isReadonly"
            placeholder="长期挂账、超1年清理进展、结转时点、与 H6-4/H10 相关说明…"
            @blur="state.saveQualitativeNotes()"
          />
        </div>
      </div>
      <el-divider content-position="left">综合说明</el-divider>
      <el-input
        v-model="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="概述取数来源、过渡科目清零情况、重大调整及风险应对…"
        :disabled="props.isReadonly"
        @blur="state.saveNote(state.auditNote.value)"
      />
    </el-card>

    <!-- 2、审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>2、审计结论</span>
          <div v-if="!props.isReadonly" class="conclusion-actions">
            <el-button size="small" @click="state.applyConclusionTemplate('A')">套用 A</el-button>
            <el-button size="small" @click="state.applyConclusionTemplate('B')">套用 B</el-button>
            <el-button size="small" type="warning" @click="state.applyConclusionTemplate('C')">套用 C</el-button>
            <el-button size="small" circle @click="openReview('H6-1-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="参考：A、未见异常。 B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。 C、由于存在重大未调整事项或范围限制，不可确认。"
        :disabled="props.isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)"
      />
    </el-card>

    <div v-if="!props.isReadonly" class="action-bar">
      <el-button type="primary" :loading="publishing" @click="handlePublish">
        确认审定 → 回写TB(1606)
      </el-button>
    </div>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1606 固定资产清理"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * H6TabAdjudication.vue — H6-1 审定表
 * 对齐致同 Excel：期初/期末×未审·账项调整·审定 + 变动额/率；
 * 过渡科目期末=0 + H6-2/H6-3 回填 + 报表核对 + 结构化说明
 */
import { ref, computed, inject, toRef, onMounted, onUnmounted, type Ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useAcnr } from '@/services/acnr/useAcnr'
import { useH6Adjudication } from '../../composables/useH6Adjudication'
import { useH6CrossSheet } from '../../composables/useH6CrossSheet'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', (itemId, value) => {
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
})
const publishing = ref(false)
const seedingFa = ref(false)
const { resolveInstance } = useAcnr()

// H10 跨底稿审定数（由主入口 GtH6 provide，经 h6H10Pull 异步拉取）
const h10AmountInjected = inject<Ref<number>>('h10Amount', ref(0))

const allResponsesRef = computed(() => props.allResponses)

const state = useH6Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  h10Amount: h10AmountInjected,
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
  onWritebackTB: async (amount: number) => {
    // 统一走 eventBus（crossWpEventBridge 自动桥接 window 供旧监听者）
    const { eventBus } = await import('@/utils/eventBus')
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'H6',
      accountCode: '1606',
      auditedAmount: amount,
      adjudicatedAmount: amount,
      isTransitAccount: true,
      timestamp: Date.now(),
    } as any)
  },
})

const crossSheet = useH6CrossSheet(allResponsesRef as any)
const h63Sync = computed(() => crossSheet.h63AdjustmentSync.value)

// ─── 从集中登记带入调整（1606 固定资产清理，资产借方；单一账项调整列→带入期末账项调整，增量累加） ───
const bringInRows = computed(() =>
  state.detailRows.value.map((r) => ({ rowKey: r.rowId, name: r.name, aje: 0, rje: 0 })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1606',
  direction: 'debit',
  subjectCode: '1606',
  wpCode: 'H6',
  subjectLabel: '固定资产清理(1606)',
  rows: bringInRows,
  // 单一账项调整列：忽略 field，读期末账项调整实时值增量累加
  updateCell: (rowKey: string, _field: any, value: number) => {
    const r = state.detailRows.value.find((x) => x.rowId === rowKey)
    const cur = Number(r?.endAdjustment) || 0
    state.updateCell(rowKey, 'endAdjustment', cur + value)
  },
  totalAudited: () => state.endBalanceAudited.value,
})

const h10HasData = computed(() => {
  // 优先使用从 H10 跨底稿拉取的真实审定数（由主入口 provide）
  if (h10AmountInjected.value !== 0) return true
  // 回退：旧路径 allResponses 键（被 crossWpEventBridge 写入时可用）
  const h10Resp = props.allResponses.get('H10-disposal-income')
  return h10Resp != null && h10Resp.remark != null
})

const crossSheetWarning = computed(() => {
  const check = crossSheet.adjudicationVsDetail.value
  if (!check.isMatch && check.diff !== 0) {
    const sign = check.diff > 0 ? '+' : ''
    return `审定净损益≠H6-2明细合计，差额：${sign}${fmtAmt(check.diff)}元`
  }
  return ''
})

const fluctuationPlaceholder = computed(() => {
  const items = state.significantChangeItems.value
  if (!items.length) {
    return '本期变动率均未超过阈值，如有其他重大变动说明可填写…'
  }
  const names = items.map((i) => i.name).join('、')
  return `以下项目变动率≥${state.CHANGE_RATE_THRESHOLD}%：${names}。请说明主要原因…`
})

function rowClassName({ row }: { row: { isTotal?: boolean; isSignificant?: boolean } }) {
  if (row.isTotal) return 'subtotal-row'
  if (row.isSignificant) return 'sig-row'
  return ''
}

function syncFromH63() {
  if (props.isReadonly) return
  const { clearingAjeNet, clearingRjeNet } = h63Sync.value
  state.syncAjeRjeFromAdjustment(clearingAjeNet, clearingRjeNet)
  ElMessage.success(`已从 H6-3 回写：账项 ${fmtAmt(clearingAjeNet)} / 报表 ${fmtAmt(clearingRjeNet)}`)
}

function handleSyncFromH62() {
  const r = state.syncFromH62('overwrite')
  if (r.applied) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleApplySignificantNote() {
  state.applySignificantFluctuationDraft()
  ElMessage.success('已将重大变动草稿写入说明(1)')
}

function parseRemarkJson(raw: unknown): any {
  if (raw == null) return null
  if (typeof raw !== 'string') return raw
  try { return JSON.parse(raw) } catch { return null }
}

async function fetchH11Parts(): Promise<{ costRows: any[]; depRows: any[]; impairRows: any[] } | null> {
  if (!props.projectId) return null
  try {
    let wpId: string | undefined
    const inst = await resolveInstance(props.projectId, 'H1', 'H1-1')
    if (inst?.found && inst.wp_id) wpId = inst.wp_id
    if (!wpId) {
      const inst2 = await resolveInstance(props.projectId, 'H1', 'H1')
      if (!inst2?.found || !inst2.wp_id) return null
      wpId = inst2.wp_id
    }
    const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(data) ? data : (data?.data ?? data?.items ?? [])
    const pick = (id: string) => {
      const item = list.find((x: any) => x.item_id === id || x.itemId === id)
      const parsed = parseRemarkJson(item?.remark ?? item?.conclusion)
      return Array.isArray(parsed) ? parsed : []
    }
    return {
      costRows: pick('H1-1-cost-rows'),
      depRows: pick('H1-1-dep-rows'),
      impairRows: pick('H1-1-impair-rows'),
    }
  } catch {
    return null
  }
}

async function handleSeedFaFromH1() {
  seedingFa.value = true
  try {
    const parts = await fetchH11Parts()
    if (!parts || (!parts.costRows.length && !parts.depRows.length && !parts.impairRows.length)) {
      ElMessage.warning('未找到 H1-1 审定数据，请先编制固定资产审定表')
      return
    }
    const r = state.seedFaNetFromH11(parts, 'overwrite')
    if (r.applied) ElMessage.success(r.message)
    else ElMessage.warning(r.message)
  } finally {
    seedingFa.value = false
  }
}

function onH1Adjudicated(ev: Event) {
  const detail = (ev as CustomEvent).detail || {}
  const wp = String(detail.wpCode ?? detail.wp_code ?? '')
  if (wp !== 'H1') return
  const end = Number(detail.net_value ?? detail.netValue) || 0
  const begin = Number(detail.net_value_begin ?? detail.netValueBegin) || 0
  if (!end && !begin) return
  const cur = state.fsReconcile.value
  if (cur.faNetEndAudited !== 0 || cur.faNetBeginAudited !== 0) return
  state.seedFaNet(end, begin || end)
  ElMessage.info(`已从 H1 审定事件带入固定资产净值：期末 ${end.toLocaleString('zh-CN')}`)
}

onMounted(() => {
  window.addEventListener('substantive:adjudicated', onH1Adjudicated)
})
onUnmounted(() => {
  window.removeEventListener('substantive:adjudicated', onH1Adjudicated)
})

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入项目名称', '新增审定项目', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value)
  } catch { /* cancelled */ }
}

function onFsChange(kind: string, side: 'end' | 'begin', value: number) {
  if (kind === 'fa') {
    state.updateFsField(side === 'end' ? 'faNetEndAudited' : 'faNetBeginAudited', value)
  } else if (kind === 'fs') {
    state.updateFsField(side === 'end' ? 'fsEndAmount' : 'fsBeginAmount', value)
  }
}

async function handlePublish() {
  publishing.value = true
  try {
    await state.publishAdjudicated()
    ElMessage.success('已确认审定并回写 TB(1606)')
  } finally {
    publishing.value = false
  }
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(val: number | null | undefined): string {
  if (val == null) return '-'
  return `${val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}
</script>

<style scoped>
.h6-tab-adjudication { padding: 16px; font-size: var(--wp-font-size, 13px); }

.guidance-details {
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 12px;
  background: #fafafa;
}
.guidance-details summary { cursor: pointer; font-weight: 600; font-size: 13px; }
.guidance-content { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.6; }
.guidance-content p { margin: 4px 0; }

.objective-alert { margin-bottom: 12px; }
.warn-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
}
.tab-toolbar .toolbar-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

.block-card { margin-bottom: 16px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  font-size: 14px; font-weight: 600;
}
.section-hint { font-size: 12px; font-weight: 400; color: var(--el-text-color-secondary); }

.adj-table { font-size: var(--wp-font-size, 13px); }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; }

.formula-cell {
  display: block; text-align: right;
  border-bottom: 1px dashed #67c23a;
  cursor: help;
  color: var(--el-text-color-primary);
}
.sig-rate { color: #f56c6c; font-weight: 600; }

.subtotal-label { font-weight: 700; }
:deep(.subtotal-row) { background-color: #f0f9eb !important; font-weight: 600; }
:deep(.sig-row) { background-color: #fef0f0 !important; }

.add-row-bar { margin-top: 8px; }
.hint-line { margin: 8px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }

.tb-compare { display: flex; flex-wrap: wrap; gap: 16px; padding: 8px 0; }
.tb-row { display: flex; align-items: center; gap: 8px; }
.tb-label { color: var(--el-text-color-secondary); min-width: 150px; }
.tb-value { font-weight: 500; font-variant-numeric: tabular-nums; }

.error-amount { color: #f56c6c; font-weight: 600; }
.audit-note-card { margin-bottom: 12px; }
.qual-grid { display: flex; flex-direction: column; gap: 12px; }
.qual-item label { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 500; }
.req-hint { color: #f56c6c; font-weight: 400; font-size: 12px; }
.conclusion-actions { display: flex; align-items: center; gap: 4px; }
.action-bar { display: flex; justify-content: flex-end; margin-bottom: 12px; padding-top: 8px; }
</style>
