<template>
  <div class="k1-tab-adjudication">
    <!-- 方法论上下文 + K1-4 联动 -->
    <div class="methodology-context">
      <p>K1-1 审定表汇总其他应收款（不含应收利息、应收股利）原值、坏账准备与净值，按组合/账龄/性质三维度列示，并与 TB、K1-2 明细、K1-4 调整勾稽。</p>
      <div class="sync-toolbar">
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleSyncK12">从 K1-2 同步未审数</el-button>
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload
          v-if="!isReadonly"
          :show-file-list="false"
          accept=".xlsx,.xls"
          :auto-upload="false"
          :on-change="onImportChange"
        >
          <el-button size="small" :loading="importing">导入 Excel</el-button>
        </el-upload>
        <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'K1-2')">K1-2 明细 →</el-button>
        <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'K1-6')">K1-6 政策 →</el-button>
        <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'K1-8')">K1-8 测算 →</el-button>
      </div>
      <div v-if="hasK14Data" class="k14-sync-banner">
        <el-tag type="info" size="small">
          K1-4：1221 AJE {{ fmtAmt(k14Sync.receivableAjeNet) }} / RJE {{ fmtAmt(k14Sync.receivableRjeNet) }}；
          1231 AJE {{ fmtAmt(k14Sync.badDebtAjeNet) }}
        </el-tag>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          @click="handleSyncK14('all')"
        >
          从 K1-4 回写全部
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          link
          @click="handleSyncK14('receivable')"
        >
          仅回写 1221
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          link
          @click="handleSyncK14('baddebt')"
        >
          仅回写 1231
        </el-button>
        <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'K1-4')">
          打开 K1-4
        </el-button>
      </div>
      <el-alert
        v-if="adjVsK14Warning"
        type="warning"
        :closable="false"
        class="cross-alert"
        :title="adjVsK14Warning"
      />
      <el-alert
        v-if="detailCrossWarning"
        type="warning"
        :closable="false"
        class="cross-alert"
        :title="detailCrossWarning"
      />
      <el-alert
        v-if="comboCrossCheck.hasK18Data && !comboCrossCheck.isConsistent"
        type="warning"
        :closable="false"
        class="cross-alert"
      >
        <template #title>K1-6/K1-8 组合名称不一致</template>
        <div class="combo-alert-body">
          <span v-if="comboCrossCheck.onlyInK16.length">仅 K1-6：{{ comboCrossCheck.onlyInK16.join('、') }}</span>
          <span v-if="comboCrossCheck.onlyInK18.length">仅 K1-8：{{ comboCrossCheck.onlyInK18.join('、') }}</span>
        </div>
      </el-alert>
      <el-alert
        v-if="varianceAlerts.length"
        type="warning"
        :closable="false"
        class="cross-alert"
      >
        <template #title>变动超 30% 须说明原因（{{ varianceAlerts.filter(a => !a.hasReason).length }} 项待填）</template>
        <div class="variance-alert-list">
          <span v-for="a in varianceAlerts" :key="a.prefix + a.rowKey">
            {{ a.label }} {{ (a.changeRate * 100).toFixed(1) }}%
            <el-tag v-if="a.hasReason" type="success" size="small">已填</el-tag>
          </span>
        </div>
        <el-button v-if="!isReadonly" size="small" type="warning" plain class="variance-draft-btn" @click="handleVarianceDrafts">
          生成变动原因草稿
        </el-button>
      </el-alert>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>记录的其他应收款在资产负债表日确实存在且已恰当记录；</li>
        <li><b>完整性：</b>所有应当记录的其他应收款均已记录，相关披露完整；</li>
        <li><b>权利和义务：</b>记录的其他应收款确为被审计单位拥有或控制；</li>
        <li><b>计价和分摊：</b>其他应收款以恰当金额包括在报表中，计价调整已恰当记录，披露充分适当；</li>
        <li><b>列报与披露：</b>已按企业会计准则规定在财务报表中作出恰当列报。</li>
      </ol>
    </el-alert>

    <!-- 一、其他应收款（组合划分） -->
    <el-card shadow="never" class="block-card section-i-card">
      <template #header>
        <div class="section-title">
          <span>一、其他应收款（不含应收利息、应收股利）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('K1-1-receivable')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <p class="table-hint">{{ receivableSection?.sectionLabel }} — 期初/期末八列宽表</p>
      <el-alert
        v-if="portfolioDeeplinkHint"
        type="info"
        :closable="true"
        class="deeplink-bar"
        @close="portfolioDeeplinkHint = ''"
      >
        <template #title><span>{{ portfolioDeeplinkHint }}</span></template>
      </el-alert>
      <K1AdjWideTable
        ref="receivableTableRef"
        :rows="receivableDisplayRows"
        prefix="receivable"
        :is-readonly="isReadonly"
        :max-height="tableMaxHeight"
        :highlight-row-key="portfolioHighlightRowKey"
        @field-change="onWideFieldChange"
      />
      <div v-for="row in receivableSection?.rows ?? []" :key="row.rowKey" class="link-hint-row">
        <template v-if="portfolioLinkDef(row.label)?.linkSheet === 'K1-8'">
          <el-button
            size="small"
            type="primary"
            link
            @click="navigateToK18(row.label)"
          >
            {{ row.label }} → K1-8
          </el-button>
          <span v-if="portfolioLinkDef(row.label)?.linkHint" class="muted">{{ portfolioLinkDef(row.label)?.linkHint }}</span>
        </template>
        <span v-else-if="portfolioLinkHint(row.label)">{{ row.label }}：{{ portfolioLinkHint(row.label) }}</span>
      </div>
    </el-card>

    <!-- 原值区块（续）：坏账准备 -->
    <el-card shadow="never" class="block-card inner-section-card">
      <template #header>
        <div class="section-title">
          <span>{{ badDebtSection?.sectionLabel }}</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('K1-1-baddebt')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <K1AdjWideTable
        :rows="badDebtDisplayRows"
        prefix="baddebt"
        :is-readonly="isReadonly"
        :max-height="tableMaxHeight"
        @field-change="onWideFieldChange"
      />
    </el-card>

    <!-- 净值 + 勾稽 -->
    <el-card shadow="never" class="block-card reconciliation-card">
      <template #header>
        <div class="section-title">
          <span>{{ netValueSection?.sectionLabel }}</span>
        </div>
      </template>
      <K1AdjWideTable
        :rows="netValueDisplayRows"
        prefix="net"
        :is-readonly="true"
        :max-height="280"
      />
      <el-divider content-position="left">报表核对（其他应收款合计 vs K1-1 净值）</el-divider>
      <div class="fs-reconcile">
        <div class="fs-row">
          <span>应收利息</span>
          <el-input-number
            v-if="!isReadonly"
            :model-value="fsReconciliation.interestReceivable"
            :controls="false"
            size="small"
            class="fs-input"
            @change="onFsField('interest', $event)"
          />
          <span v-else>{{ fmtAmt(fsReconciliation.interestReceivable) }}</span>
        </div>
        <div class="fs-row">
          <span>应收股利</span>
          <el-input-number
            v-if="!isReadonly"
            :model-value="fsReconciliation.dividendReceivable"
            :controls="false"
            size="small"
            class="fs-input"
            @change="onFsField('dividend', $event)"
          />
          <span v-else>{{ fmtAmt(fsReconciliation.dividendReceivable) }}</span>
        </div>
        <div class="fs-row">
          <span>其他应收款合计（报表）</span>
          <el-input-number
            v-if="!isReadonly"
            :model-value="fsReconciliation.fsOtherTotal"
            :controls="false"
            size="small"
            class="fs-input"
            @change="onFsField('other-total', $event)"
          />
          <span v-else>{{ fmtAmt(fsReconciliation.fsOtherTotal) }}</span>
        </div>
        <div class="fs-row">
          <span>K1-1 净值审定合计</span>
          <span>{{ fmtAmt(fsReconciliation.k11NetAudited) }}</span>
        </div>
        <div class="fs-row">
          <span>差异</span>
          <el-tag :type="fsReconciliation.isBalanced ? 'success' : 'danger'" size="small">
            {{ fmtAmt(fsReconciliation.fsDiff) }}
          </el-tag>
        </div>
      </div>
      <el-divider content-position="left">TB 数据核对</el-divider>
      <div class="tb-reconcile">
        <div class="tb-row">
          <span>1221 审定合计</span>
          <span>{{ fmtAmt(tbReconciliation.auditedReceivable) }}</span>
          <span class="muted">TB</span>
          <span>{{ fmtAmt(tbReconciliation.tbReceivable) }}</span>
          <el-tag :type="Math.abs(tbReconciliation.receivableDiff) < 0.01 ? 'success' : 'danger'" size="small">
            差异 {{ fmtAmt(tbReconciliation.receivableDiff) }}
          </el-tag>
        </div>
        <div class="tb-row">
          <span>1231 审定合计</span>
          <span>{{ fmtAmt(tbReconciliation.auditedBadDebt) }}</span>
          <span class="muted">TB</span>
          <span>{{ fmtAmt(tbReconciliation.tbBadDebt) }}</span>
          <el-tag :type="Math.abs(tbReconciliation.badDebtDiff) < 0.01 ? 'success' : 'danger'" size="small">
            差异 {{ fmtAmt(tbReconciliation.badDebtDiff) }}
          </el-tag>
        </div>
      </div>
      <el-divider content-position="left">三角勾稽校验</el-divider>
      <div class="reconciliation-result">
        <el-tag :type="reconciliation.isBalanced ? 'success' : 'danger'" size="large">
          {{ reconciliation.isBalanced ? '✓ 勾稽平衡' : '✗ 勾稽不平' }}
        </el-tag>
        <span v-if="!reconciliation.isBalanced" class="error-amount" style="margin-left:12px;">
          差额: {{ fmtAmt(reconciliation.diff) }}
        </span>
      </div>
    </el-card>

    <!-- 二、账龄分布 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <span class="section-title-text">{{ agingDistribution.blockLabel }}</span>
      </template>
      <DistributionTripleTable
        :block="agingDistribution"
        :is-readonly="isReadonly"
        gross-prefix="aging-gross"
        prov-prefix="aging-prov"
        sub-title="（一）账龄原值 / （二）账龄坏账准备 / （三）账龄净值"
        @field-change="onDistFieldChange"
      />
    </el-card>

    <!-- 三、款项性质分布 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <span class="section-title-text">{{ natureDistribution.blockLabel }}</span>
      </template>
      <DistributionTripleTable
        :block="natureDistribution"
        :is-readonly="isReadonly"
        gross-prefix="nature-gross"
        prov-prefix="nature-prov"
        sub-title="（一）性质原值 / （二）性质坏账准备 / （三）性质净值"
        @field-change="onDistFieldChange"
      />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('adj-note')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明..." :disabled="isReadonly" @blur="saveNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('adj-conclusion')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计结论..." :disabled="isReadonly" @blur="saveConclusion" />
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" @click="handleWritebackTB" :loading="publishing">
        确认审定 → 回写TB
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>结构对齐致同 K1-1：组合划分 → 账龄分布 → 款项性质分布 → 合计/TB核对</li>
        <li>账龄组合/客户类型组合须与 K1-6/K1-8 一致；可从 K1-2 一键同步未审数</li>
        <li>坏账准备：备抵类，期末=期初+贷方-借方</li>
        <li>账面净值=其他应收款-坏账准备</li>
        <li>三角勾稽：期末=期初+增加-减少，差额须为0</li>
        <li>审定数=未审数+AJE+RJE，未审数从TB自动取入(只读)</li>
        <li>K1-4 保存后可「从 K1-4 回写 AJE/RJE」，1221/1231 净额按未审数权重分摊至各行</li>
        <li>"确认审定"将回写trial_balance(1221+坏账准备)并发布EventBus事件</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabAdjudication.vue — K1-1 审定表
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.2
 * Requirements: 2.1-2.10
 * 双区块(1221+坏账准备)+净值+47公式+三角勾稽+TB回写+89行虚拟滚动
 */
import { ref, computed, inject, toRef, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useK1Adjudication, type K1AdjRow, type K14WritebackScope, type K1AdjudicationPrefill } from '../../composables/useK1Adjudication'
import { useK1FormData } from '../../composables/useK1FormData'
import { useK1CrossSheet } from '../../composables/useK1CrossSheet'
import { useK1ImportExport } from '../../composables/useK1ImportExport'
import { useK1AiGenerate } from '../../composables/useK1AiGenerate'
import DistributionTripleTable from './K1DistributionTripleTable.vue'
import K1AdjWideTable from './K1AdjWideTable.vue'
import {
  K1RowNavigationKey,
  buildK1PortfolioDeeplinkHint,
  resolveK11PortfolioRowKey,
} from '../../composables/useK1RowNavigation'
import type { K1AdjRowDef } from '../../composables/k1AdjudicationModel'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted1221: number; audited1221: number; unadjustedBadDebt: number; auditedBadDebt: number }
  adjudicationPrefill?: K1AdjudicationPrefill | null
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const k1Nav = inject(K1RowNavigationKey, null)
const allResponsesRef = computed(() => props.allResponses)
const portfolioDeeplinkHint = ref('')
const portfolioHighlightRowKey = ref('')
const receivableTableRef = ref<InstanceType<typeof K1AdjWideTable>>()

const {
  adjudicationSections,
  agingDistribution,
  natureDistribution,
  portfolioRowDefs,
  reconciliation,
  tbReconciliation,
  fsReconciliation,
  comboCrossCheck,
  varianceAlerts,
  auditNote,
  auditConclusion,
  k14AdjustmentSync,
  syncEndAdjFromK14,
  syncUnadjFromK12,
  applyAdjudicationPrefill,
  ensurePortfolioLabels,
  persistAuditedTotals,
  writeRowField,
  writeFsField,
  generateVarianceReasonDrafts,
} = useK1Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  tbData: computed(() => props.tbData),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const { adjudicationVsK14, adjudicationVsDetail } = useK1CrossSheet(allResponsesRef as any)

const { isImporting: importing, exportTemplate, exportData, importData } = useK1ImportExport({
  wpId: toRef(props, 'wpId'),
})

const { generateAndConfirm } = useK1AiGenerate(toRef(props, 'wpId'))

const k14Sync = computed(() => k14AdjustmentSync.value)
const hasK14Data = computed(() =>
  k14Sync.value.rowCount > 0 ||
  Math.abs(k14Sync.value.receivableAjeNet) >= 0.005 ||
  Math.abs(k14Sync.value.receivableRjeNet) >= 0.005 ||
  Math.abs(k14Sync.value.badDebtAjeNet) >= 0.005,
)
const adjVsK14Warning = computed(() => {
  const chk = adjudicationVsK14.value
  if (chk.isMatch || !hasK14Data.value) return ''
  const parts: string[] = []
  if (Math.abs(chk.receivableAjeDiff) >= 0.01) {
    parts.push(`1221 AJE 差额 ${chk.receivableAjeDiff.toLocaleString('zh-CN')}`)
  }
  if (Math.abs(chk.badDebtAjeDiff) >= 0.01) {
    parts.push(`1231 AJE 差额 ${chk.badDebtAjeDiff.toLocaleString('zh-CN')}`)
  }
  return parts.length ? `K1-1 与 K1-4 未完全勾稽：${parts.join('；')}。可点击「从 K1-4 回写」同步。` : ''
})
const detailCrossWarning = computed(() => {
  const chk = adjudicationVsDetail.value
  if (chk.isMatch) return ''
  return `K1-1 审定合计与 K1-2 明细小计差异 ${chk.diff.toLocaleString('zh-CN')}，请核对或从 K1-2 同步。`
})

onMounted(() => {
  ensurePortfolioLabels()
  if (props.adjudicationPrefill) {
    applyAdjudicationPrefill(props.adjudicationPrefill)
  }
  applyIncomingPortfolioFocus()
  eventBus.on('adjustment:created', onAdjustmentCreated)
})

onBeforeUnmount(() => {
  eventBus.off('adjustment:created', onAdjustmentCreated)
})

/** K1-4 保存调整后自动回写 1221/1231 净额至审定表 */
function onAdjustmentCreated(payload: any): void {
  if (props.isReadonly) return
  const code = String(payload?.accountCode ?? payload?.account_code ?? '')
  const wp = String(payload?.wpCode ?? payload?.wp_code ?? '')
  if (wp && wp !== 'K1' && !wp.startsWith('K1')) return
  if (code && !/^1221|^1231/.test(code) && wp !== 'K1') return
  const r = syncEndAdjFromK14('all')
  if (r?.applied) {
    persistAuditedTotals()
    ElMessage.success(r.message || '已从 K1-4 自动回写审定表调整列')
  }
}

function applyIncomingPortfolioFocus(): void {
  const focus = k1Nav?.consumeFocus('K1-1')
  if (!focus?.portfolioLabel) return
  const rowKey = resolveK11PortfolioRowKey(focus.portfolioLabel)
  if (!rowKey) return
  portfolioHighlightRowKey.value = rowKey
  portfolioDeeplinkHint.value = buildK1PortfolioDeeplinkHint(focus)
  k1Nav?.focusRow(rowKey)
  nextTick(() => scrollToPortfolioRow(rowKey))
}

function scrollToPortfolioRow(rowKey: string): void {
  const root = receivableTableRef.value?.$el as HTMLElement | undefined
  const rowEl = root?.querySelector(`tr[data-row-key="${rowKey}"]`) as HTMLElement | null
  rowEl?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

function navigateToK18(label: string): void {
  if (k1Nav) {
    k1Nav.navigateToRow({ sheet: 'K1-8', portfolioLabel: label, sourceSheet: 'K1-1' })
    return
  }
  emit('navigate-sheet', '坏账准备测算K1-8')
}

function portfolioLinkDef(label: string): K1AdjRowDef | undefined {
  return portfolioRowDefs.find((d) => d.label === label)
}

const { writebackTB, debouncedSave } = useK1FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const tableMaxHeight = 520
const publishing = ref(false)

const receivableSection = computed(() => adjudicationSections.value[0])
const badDebtSection = computed(() => adjudicationSections.value[1])
const netValueSection = computed(() => adjudicationSections.value[2])

const receivableDisplayRows = computed((): K1AdjRow[] => {
  const sec = receivableSection.value
  if (!sec) return []
  return [...sec.rows, { ...sec.subtotalRow, label: '合计' }]
})
const badDebtDisplayRows = computed((): K1AdjRow[] => {
  const sec = badDebtSection.value
  if (!sec) return []
  return [...sec.rows, { ...sec.subtotalRow, label: '合计' }]
})
const netValueDisplayRows = computed((): K1AdjRow[] => {
  const sec = netValueSection.value
  if (!sec) return []
  return [...sec.rows, { ...sec.subtotalRow, label: '合计' }]
})

function onWideFieldChange(payload: { prefix: string; rowKey: string; field: string; value: string | number }) {
  writeRowField(payload.prefix, payload.rowKey, payload.field, payload.value)
  persistAuditedTotals()
}

function onFsField(field: 'interest' | 'dividend' | 'other-total', value: number | undefined) {
  writeFsField(field, value ?? 0)
}

function handleVarianceDrafts() {
  const res = generateVarianceReasonDrafts()
  if (res.filled) ElMessage.success(`已生成 ${res.filled} 条变动原因草稿${res.skipped ? `，跳过 ${res.skipped} 条已有说明` : ''}`)
  else ElMessage.info(res.skipped ? '所有变动行均已填写原因' : '暂无超 30% 变动行')
}

function onDistFieldChange(payload: { prefix: string; rowKey: string; field: 'aje' | 'rje' | string; value: number | string }) {
  if (payload.field === 'aje' || payload.field === 'rje') {
    const itemId = `K1-1-${payload.prefix}-${payload.rowKey}-${payload.field}`
    props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: String(payload.value) })
    emit('save', itemId, { remark: String(payload.value) })
    persistAuditedTotals()
    return
  }
  writeRowField(payload.prefix, payload.rowKey, payload.field, payload.value)
  persistAuditedTotals()
}

function saveNote() {
  const itemId = 'K1-1-audit-note'
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: auditNote.value })
  debouncedSave(itemId, { remark: auditNote.value })
}
function saveConclusion() {
  const itemId = 'K1-1-audit-conclusion'
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: auditConclusion.value })
  debouncedSave(itemId, { remark: auditConclusion.value })
}

function portfolioLinkHint(label: string): string {
  const def = portfolioRowDefs.find((d) => d.label === label)
  return def?.linkHint || ''
}

function handleSyncK12() {
  const res = syncUnadjFromK12()
  if (res.applied) ElMessage.success(res.message)
  else ElMessage.info(res.message)
}

async function reloadFromServer() {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items: any[] = Array.isArray(res?.data?.data) ? res.data.data : Array.isArray(res?.data) ? res.data : []
    for (const item of items) {
      const id = item.item_id || item.itemId
      if (!id || !String(id).startsWith('K1-1')) continue
      props.allResponses.set(id, {
        item_id: id,
        remark: item.remark ?? null,
        conclusion: item.conclusion ?? null,
      })
    }
    ensurePortfolioLabels()
    persistAuditedTotals()
  } catch {
    /* keep local state */
  }
}

function onExportTemplate() {
  exportTemplate('K1-1')
}

function onExportData() {
  exportData('K1-1')
}

async function onImportChange(uploadFile: UploadFile) {
  const raw = uploadFile.raw
  if (!raw) return
  const result = await importData('K1-1', raw)
  if (result) await reloadFromServer()
}

async function handleWritebackTB() {
  publishing.value = true
  try {
    const recSec = receivableSection.value
    const bdSec = badDebtSection.value
    if (!recSec || !bdSec) return
    await writebackTB(recSec.subtotalRow.audited, bdSec.subtotalRow.audited)
    persistAuditedTotals()
    ElMessage.success('审定数已回写TB（1221+坏账准备）')
  } catch { ElMessage.error('TB回写失败') }
  finally { publishing.value = false }
}
function handleSyncK14(scope: K14WritebackScope = 'all') {
  const res = syncEndAdjFromK14(undefined, undefined, undefined, undefined, scope)
  if (res.applied) ElMessage.success(res.message)
  else ElMessage.info(res.message)
}
async function handleAiGenerate(section: 'adj-note' | 'adj-conclusion') {
  const recSec = receivableSection.value
  const bdSec = badDebtSection.value
  const ctx = {
    receivableAudited: recSec?.subtotalRow.audited ?? 0,
    badDebtAudited: bdSec?.subtotalRow.audited ?? 0,
    netAudited: netValueSection.value?.subtotalRow.audited ?? 0,
    varianceCount: varianceAlerts.value.length,
    comboConsistent: comboCrossCheck.value.isConsistent,
    tbBalanced: tbReconciliation.value.isBalanced,
  }
  const existing = section === 'adj-note' ? auditNote.value : auditConclusion.value
  const title = section === 'adj-note' ? 'AI 生成 K1-1 审计说明' : 'AI 生成 K1-1 审计结论'
  const content = await generateAndConfirm('overall-opinion', existing, ctx, title)
  if (!content) return
  if (section === 'adj-note') {
    auditNote.value = content
    saveNote()
  } else {
    auditConclusion.value = content
    saveConclusion()
  }
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k1-tab-adjudication { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
}
.sync-toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 8px; }
.section-title-text { font-weight: 600; }
.section-i-card { margin-bottom: 8px; }
.inner-section-card { margin-top: -4px; }
.link-hint-row { font-size: 11px; color: var(--el-color-primary); margin-top: 4px; }
.deeplink-bar { margin-bottom: 8px; }
.table-hint { font-size: 12px; color: var(--el-text-color-secondary); margin: 0 0 8px; }
.combo-alert-body, .variance-alert-list { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; margin-top: 4px; }
.variance-draft-btn { margin-top: 8px; }
.fs-reconcile { display: flex; flex-direction: column; gap: 8px; font-size: 12px; margin-bottom: 12px; }
.fs-row { display: grid; grid-template-columns: 180px 1fr; gap: 8px; align-items: center; }
.fs-input { width: 160px; }
.tb-reconcile { display: flex; flex-direction: column; gap: 8px; font-size: 12px; margin-bottom: 8px; }
.tb-row { display: grid; grid-template-columns: 120px 1fr 40px 1fr auto; gap: 8px; align-items: center; }
.muted { color: var(--el-text-color-secondary); }
.k14-sync-banner { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 8px; }
.cross-alert { margin-top: 8px; }
.methodology-context p {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}
.audit-objective { margin-bottom: 14px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.adj-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.tb-auto { color: var(--el-text-color-secondary); font-style: italic; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.reconciliation-card { margin-bottom: 16px; }
.reconciliation-result { display: flex; align-items: center; padding: 8px 0; }
.note-card { margin-bottom: 12px; }
.action-bar { margin-top: 16px; text-align: right; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
