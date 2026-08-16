<template>
  <div class="g12-adj" data-testid="g12-adjudication">
    <div class="toolbar">
      <h3 class="title">G12-1 净敞口套期收益审定表</h3>
      <div class="actions">
        <GtReviewTrigger section-id="G12-1-adjudication" />
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
      </div>
    </div>

    <GCycleGuideStrip
      label="主闭环"
      :steps="[...G12_CORE_WORKFLOW_STEPS]"
      :active-index="wf.activeIndex.value"
      :completed-indices="wf.completedIndices.value"
    />
    <G12CoreWorkflowChecklist :readiness="wf.readiness.value" />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G12-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ adj.dataRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
      description="核对净敞口套期收益（6103）审定数与试算平衡表一致，验证 G12-1↔G12-2 汇总、G12-2↔G12-4 公允价值测试的勾稽关系，对本期与上期变动率超阈值项目取得合理性解释。"
    />

    <el-alert
      v-if="g12AdjSyncPending"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g12-adj-pending-sync-bar"
    >
      G12-3 有待同步的调整数（6103 净额 {{ fmt(g12AdjPendingNet) }}），请先在 G12-3 点击「同步至审定表」。
      <GtIndexChip
        v-if="jumpToSection"
        label="G12-3"
        :prevent-navigate="true"
        :validate="false"
        class="warn-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-3'))"
      />
    </el-alert>

    <el-alert
      v-if="hedgeCrossMessage"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g12-adj-hedge-cross-bar"
    >
      {{ hedgeCrossMessage }}
      <GtIndexChip
        v-if="jumpToSection"
        label="G12-2"
        :prevent-navigate="true"
        :validate="false"
        class="warn-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-2'))"
      />
    </el-alert>
    <el-alert
      v-else-if="hasHedgeData"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g12-adj-hedge-cross-ok"
    >
      G12-1 与 G12-2 套期明细汇总一致
      <GtIndexChip
        v-if="jumpToSection"
        label="G12-2"
        :prevent-navigate="true"
        :validate="false"
        class="ok-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-2'))"
      />
    </el-alert>
    <el-alert
      v-else
      type="info"
      :closable="false"
      class="cross-alert"
      data-testid="g12-adj-hedge-cross-pending"
    >
      待 G12-2 套期明细录入后自动校验 G12-1↔G12-2 汇总一致
    </el-alert>

    <el-alert
      v-if="fvCrossMessage"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g12-adj-fv-cross-bar"
    >
      {{ fvCrossMessage }}
      <GtIndexChip
        v-if="jumpToSection"
        label="G12-4"
        :prevent-navigate="true"
        :validate="false"
        class="warn-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-4'))"
      />
    </el-alert>
    <el-alert
      v-else-if="hasHedgeData && hasFvTestData"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g12-adj-fv-cross-ok"
    >
      G12-2 与 G12-4 公允价值测试一致
      <GtIndexChip
        v-if="jumpToSection"
        label="G12-4"
        :prevent-navigate="true"
        :validate="false"
        class="ok-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-4'))"
      />
    </el-alert>

    <!-- 四表库取数溯源（口径：本期发生额） -->

    <WpFourTableSourcePanel

      :source-codes="tbSourceCodes"

      gross-label="净敞口套期收益"

      fallback-row-code="IS-014"

    />


    <el-table :data="tableRows" border size="small" style="font-size:13px" max-height="520" :row-class-name="rowClassName">
      <el-table-column label="项目" prop="label" width="200" fixed>
        <template #default="{ row }">
          <GtReviewDot v-if="row.rowKey !== 'total'" row-prefix="G12-adj" :row-key="row.rowKey" />
          {{ row.label }}
        </template>
      </el-table-column>

      <el-table-column label="本期数" align="center">
        <el-table-column label="未审数" width="108" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="自 G12-2 套期关系汇总">{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整数" width="108" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="自 G12-3 调整分录汇总">{{ fmt(row.currentAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="108" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定 = 未审 + 调整">{{ fmt(row.currentAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="上期数" align="center">
        <el-table-column label="未审数" width="108" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorUnadjusted"
              size="small" style="width:100%"
              @update:model-value="(v: number) => adj.updatePriorField(row.rowKey, 'priorUnadjusted', v ?? 0)" />
            <span v-else>{{ fmt(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整数" width="108" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorAdjustment"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => adj.updatePriorField(row.rowKey, 'priorAdjustment', v ?? 0)" />
            <span v-else>{{ fmt(row.priorAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="108" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.priorAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="变动额" width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell">{{ fmt(row.changeAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动率" width="88" align="right">
        <template #default="{ row }">
          <span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原因分析" min-width="120">
        <template #default="{ row }">
          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.reasonAnalysis" size="small"
            :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
            placeholder="|变动率|>20%时必填"
            @change="(v: string) => adj.updatePriorField(row.rowKey, 'reasonAnalysis', v)" />
          <span v-else>{{ row.reasonAnalysis }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="88">
        <template #default="{ row }">
          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.indexRef" size="small"
            @change="(v: string) => adj.updatePriorField(row.rowKey, 'indexRef', v)" />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
        </template>
      </el-table-column>
    </el-table>

    <div class="tb-row">
      <span>试算平衡表(6103)：</span>
      <el-input-number v-if="!isReadonly" :model-value="adj.trialBalanceAmount.value" size="small" :controls="false"
        style="width:140px" @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <el-button size="small" :loading="adj.tbLoading.value" :disabled="isReadonly"
        @click="adj.loadTrialBalanceFromApi(true)">从 TB 取数</el-button>
      <span :class="['variance', { 'is-error': adj.hasVarianceHighlight.value }]">差异：{{ fmt(adj.variance.value) }}</span>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.publishAdjudicated()">发布审定数</el-button>
    </div>

    <el-card shadow="never" class="note-card">
      <template #header>1、审计说明</template>
      <p class="audit-intro">{{ adj.auditNoteIntro.value }}</p>
      <div class="audit-field">
        <label>主要变动原因<span v-if="adj.auditMainReasonRequired.value" class="req-tag">（|变动率|&gt;30% 时必填）</span></label>
        <el-input :model-value="adj.auditMainReason.value" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          :class="{ 'reason-required': adj.auditMainReasonRequired.value && !adj.auditMainReason.value.trim() }"
          placeholder="说明套期关系变化、汇率波动、被套期项目规模变动等主要原因"
          @update:model-value="adj.updateAuditMainReason" />
      </div>
      <div class="audit-field">
        <label>案例描述</label>
        <el-input :model-value="adj.auditCaseDesc.value" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly" placeholder="列示典型套期关系编号及索引（如 G12-2/G12-4）"
          @update:model-value="adj.updateAuditCaseDesc" />
      </div>
      <div class="audit-field">
        <label>补充说明</label>
        <el-input :model-value="adj.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly" @update:model-value="adj.updateAuditNote" />
      </div>
    </el-card>
    <el-card shadow="never" class="note-card">
      <template #header>2、审计结论</template>
      <el-input :model-value="adj.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditConclusion" />
    </el-card>

    <details class="methodology-hint">
      <summary>📋 编制提示（CAS24 套期会计）</summary>
      <p>{{ G12_CORE_WORKFLOW_HINT }}</p>
      <p>本页重点：点「从 TB 取数」→ 核对差异为 0 → 填审计说明（|变动率|&gt;30% 须填主要原因）→ 发布审定数。未审数取自 G12-2，调整数取自 G12-3；|变动率| &gt; 20% 的项目须在「原因分析」列填写说明。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed, inject, toRef } from 'vue'
import { useG12Adjudication } from '../../composables/useG12Adjudication'
import {
  findG12AdjudicationHedgeMismatches,
  findG12FvCrossMismatches,
  formatG12AdjudicationHedgeCrossMessage,
  formatG12FvCrossSummaryMessage,
  hasG12HedgeDetailData,
  hasG12FvTestData,
} from '../../composables/useG12CrossValidate'
import { G12_CORE_WORKFLOW_HINT, G12_CORE_WORKFLOW_STEPS } from '../../composables/g12Constants'
import { g12AdjustmentNeedsSync, g12AdjustmentPendingNet } from '../../composables/g12CoreWorkflowReadiness'
import { useG12CoreWorkflow } from '../../composables/useG12CoreWorkflow'
import { resolveG12SheetLabel } from '../../composables/g12SheetLabels'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GCycleGuideStrip from '../../shared/GCycleGuideStrip.vue'
import G12CoreWorkflowChecklist from '../shared/G12CoreWorkflowChecklist.vue'
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'

const props = defineProps<{
  /** render 下发的本 sheet html_data（含 tb_source_codes） */
  htmlData?: Record<string, any> | null
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()


/**
 * 四表库取数溯源（消费 render 下发的 `tb_source_codes`，消除 dead output）。
 *
 * 科目由后端按**科目名**逐项目解析（`four_table/g_cycle_specs.G12_SPEC`），
 * 取数口径 = 本期发生额。前端单一真源见 `composables/gCycleAccountScope.ts`。
 */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
const adj = useG12Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const wf = useG12CoreWorkflow({ allResponses: toRef(props, 'allResponses'), pageCode: 'G12-1' })

const g12AdjSyncPending = computed(() => g12AdjustmentNeedsSync(props.allResponses))
const g12AdjPendingNet = computed(() => g12AdjustmentPendingNet(props.allResponses))

const tableRows = computed(() => [...adj.dataRows.value, adj.totalRow.value])

const hasHedgeData = computed(() => hasG12HedgeDetailData(props.allResponses))
const hasFvTestData = computed(() => hasG12FvTestData(props.allResponses))

const hedgeCrossMessage = computed(() => {
  const mismatches = findG12AdjudicationHedgeMismatches(
    adj.dataRows.value,
    adj.hedge.totals.value,
  )
  return formatG12AdjudicationHedgeCrossMessage(mismatches)
})

const fvCrossMessage = computed(() => {
  const mismatches = findG12FvCrossMismatches(adj.hedge.rows.value, props.allResponses)
  return formatG12FvCrossSummaryMessage(mismatches)
})

function rowClassName({ row }: { row: { rowKey: string } }): string {
  return row.rowKey === 'total' ? 'g12-row-total' : ''
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | null): string {
  if (rate === null) return '-'
  return `${(rate * 100).toFixed(2)}%`
}
</script>

<style scoped>
.g12-adj { padding: 12px; font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.title { margin: 0; font-size: 15px; font-weight: 600; }
.actions { display: flex; gap: 8px; align-items: center; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #fafafa; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.tb-row { display: flex; align-items: center; gap: 16px; margin: 12px 0; flex-wrap: wrap; }
.variance { font-weight: 600; }
.variance.is-error { color: #f56c6c; }
.note-card { margin-top: 12px; }
.audit-intro { margin: 0 0 12px; padding: 8px 10px; background: #f5f7fa; border-radius: 4px; color: #303133; }
.audit-field { margin-bottom: 12px; }
.audit-field label { display: block; margin-bottom: 4px; font-weight: 500; color: #606266; }
.req-tag { color: #e6a23c; font-weight: 400; font-size: 12px; }
.audit-objective { margin-bottom: 12px; }
.methodology-hint { margin-top: 16px; padding: 10px 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266; }
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.cross-alert { margin-bottom: 12px; }
.warn-chip { margin-left: 8px; }
.ok-chip { margin-left: 8px; }
.cross-ok :deep(.el-alert__content) { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
:deep(.g12-row-total) { font-weight: 700; background: #f5f7fa; }
</style>
