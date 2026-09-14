<template>
  <div class="g14-adjudication" data-testid="g14-adjudication">
    <header class="g14-header">
      <div class="g14-header-main">
        <h3 class="g14-title">G14-1 信用减值损失审定表</h3>
        <span class="g14-subtitle">科目 6702 · CAS 22 预期信用损失（ECL）</span>
      </div>
      <div class="g14-actions">
        <GtIndexChip value="wp:G14-1" :context-project-id="projectId" />
        <el-tag size="small" type="info" effect="plain">{{ adj.dataRows.value.length }} 类减值来源</el-tag>
        <GtReviewTrigger section-id="G14-1-adjudication" />
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">
          AI 说明
        </el-button>
      </div>
    </header>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标"
      description="确认本期信用减值损失（6702，损益发生额：借方计提−贷方转回）充分、准确；各减值来源与 D1/D2/D5/F1/G4/G5 等源科目 ECL 勾稽一致；重大变动可解释且附注披露完整。"
    />

    <GCycleGuideStrip :steps="['G14A 程序', 'G14-1 审定', 'G14-2 明细', 'G14-3 调整', '附注披露']" />

    <!-- 状态摘要条 -->
    <div
      class="status-strip"
      :class="{ 'is-ok': adj.statusSummary.value.allOk, 'is-warn': !adj.statusSummary.value.allOk }"
      data-testid="g14-adj-status-strip"
    >
      <div class="status-item">
        <span class="status-label">本期审定合计</span>
        <span class="status-value">{{ fmt(adj.statusSummary.value.currentAudited) }}</span>
      </div>
      <div class="status-divider" />
      <div class="status-item">
        <span class="status-label">较上期变动</span>
        <span class="status-value" :class="{ 'rate-warn': adj.statusSummary.value.changeWarn }">
          {{ fmt(adj.statusSummary.value.changeAmount) }}
          <small>（{{ adj.statusSummary.value.changePctText }}）</small>
        </span>
      </div>
      <div class="status-divider" />
      <div class="status-item">
        <span class="status-label">差异数</span>
        <span class="status-value" :class="{ 'is-error': adj.hasVarianceHighlight.value }">
          {{ fmt(adj.variance.value) }}
        </span>
      </div>
      <div class="status-checks">
        <el-tag size="small" :type="adj.statusSummary.value.tbOk ? 'success' : 'danger'" effect="light">
          TB勾稽
        </el-tag>
        <el-tag size="small" :type="adj.statusSummary.value.detailOk ? 'success' : 'warning'" effect="light">
          明细勾稽
        </el-tag>
        <el-tag size="small" :type="adj.statusSummary.value.reasonOk ? 'success' : 'warning'" effect="light">
          变动分析
        </el-tag>
      </div>
    </div>

    <el-alert
      v-if="adj.detailCrossValidation.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g14-adj-detail-cross-bar"
    >
      {{ adj.detailCrossValidation.value }}
      <GtIndexChip
        v-if="jumpToSection"
        label="G14-2"
        :prevent-navigate="true"
        :validate="false"
        class="inline-chip"
        @click="jumpToSection(resolveG14SheetLabel('G14-2'))"
      />
    </el-alert>
    <el-alert
      v-else-if="!adj.hasDetailData.value"
      type="info"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g14-adj-detail-cross-pending"
      title="待 G14-2 明细录入后自动校验 G14-1↔G14-2 汇总一致"
    />

    <el-alert
      v-if="adj.hasMissingReasons.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g14-adj-missing-reason"
      :title="`有 ${adj.missingReasonCount.value} 行变动超阈值（|变动率|>30% 或 |变动额|≥10万）未填原因分析，请补充后再发布`"
    />

    <div class="table-wrap">
      <!-- 四表库取数溯源（口径：本期发生额） -->
      <WpFourTableSourcePanel
        :source-codes="tbSourceCodes"
        gross-label="信用减值损失"
        fallback-row-code="IS-016"
      />

      <el-table
        :data="tableRows"
        border
        size="small"
        class="g14-table"
        max-height="480"
        :row-class-name="rowClassName"
      >
        <el-table-column label="项目" prop="label" min-width="168" fixed>
          <template #default="{ row }">
            <div class="label-cell">
              <GtReviewDot v-if="row.rowKey !== 'total'" row-prefix="G14-adj" :row-key="row.rowKey" />
              <span :class="{ 'is-total-label': row.rowKey === 'total' }">{{ row.label }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="本期数" align="center">
          <el-table-column label="未审数" width="108" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="自 G14-2 明细同步">{{ fmt(row.currentUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整数" width="108" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="自 G14-2 明细同步">{{ fmt(row.currentAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="108" align="right">
            <template #default="{ row }">
              <span class="formula-cell audited" title="审定 = 未审 + 调整">{{ fmt(row.currentAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="上期数" align="center">
          <el-table-column label="未审数" width="108" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.rowKey !== 'total' && !isReadonly"
                :model-value="row.priorUnadjusted"
                size="small"
                class="cell-input"
                @update:model-value="(v: number) => adj.updatePriorField(row.rowKey, 'priorUnadjusted', v ?? 0)"
              />
              <span v-else>{{ fmt(row.priorUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整数" width="108" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.rowKey !== 'total' && !isReadonly"
                :model-value="row.priorAdjustment"
                size="small"
                :controls="false"
                class="cell-input"
                @update:model-value="(v: number) => adj.updatePriorField(row.rowKey, 'priorAdjustment', v ?? 0)"
              />
              <span v-else>{{ fmt(row.priorAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="108" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定 = 未审 + 调整">{{ fmt(row.priorAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="本期与上期审定数比较" align="center">
          <el-table-column label="变动额" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="变动额 = 本期审定 − 上期审定">{{ fmt(row.changeAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动率" width="88" align="right">
            <template #default="{ row }">
              <span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="原因分析" min-width="148">
          <template #default="{ row }">
            <el-input
              v-if="row.rowKey !== 'total' && !isReadonly"
              :model-value="row.reasonAnalysis"
              size="small"
              :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
              placeholder="|变动率|>30% 或 |变动额|≥10万 必填"
              @change="(v: string) => adj.updatePriorField(row.rowKey, 'reasonAnalysis', v)"
            />
            <span v-else class="muted">{{ row.reasonAnalysis || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="100">
          <template #default="{ row }">
            <template v-if="row.rowKey === 'total'">—</template>
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.indexRef"
              size="small"
              placeholder="wp:D2-1"
              @change="(v: string) => adj.updatePriorField(row.rowKey, 'indexRef', v)"
            />
            <GtIndexChip v-else-if="row.indexRef?.startsWith('wp:')" :value="row.indexRef" />
            <span v-else class="muted">{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 试算勾稽区 -->
    <section class="recon-panel" data-testid="g14-adj-recon">
      <div class="recon-title">试算平衡表勾稽（6702 本期发生额）</div>
      <div class="recon-body">
        <div class="recon-field">
          <label>试算平衡表数</label>
          <el-input-number
            v-if="!isReadonly"
            :model-value="adj.trialBalanceAmount.value"
            size="small"
            :controls="false"
            class="tb-input"
            @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)"
          />
          <span v-else class="tb-readonly">{{ fmt(adj.trialBalanceAmount.value) }}</span>
        </div>
        <el-button
          size="small"
          :loading="adj.tbLoading.value"
          :disabled="isReadonly"
          @click="adj.loadTrialBalanceFromApi(true)"
        >
          从 TB 取数
        </el-button>
        <div
          class="recon-diff"
          :class="{ 'is-error': adj.hasVarianceHighlight.value, 'is-ok': !adj.hasVarianceHighlight.value }"
        >
          <span class="recon-diff-label">差异数</span>
          <strong>{{ fmt(adj.variance.value) }}</strong>
          <span v-if="!adj.hasVarianceHighlight.value" class="recon-ok-mark">✓</span>
        </div>
        <el-button
          size="small"
          type="primary"
          :disabled="isReadonly"
          data-testid="g14-adj-publish"
          @click="adj.publishAdjudicated()"
        >
          发布审定数
        </el-button>
      </div>
      <p v-if="adj.tbFetchStatus.value === 'missing'" class="recon-hint">
        试算表未命中 6702，可手工录入；若本年无余额且审定为 0，差异应为 0。
      </p>
    </section>

    <div class="notes-grid">
      <el-card shadow="never" class="note-card" data-testid="g14-adj-audit-note">
        <template #header>
          <div class="note-card-head">
            <span>1、审计说明</span>
            <el-tag
              v-if="adj.overallChangeExceedsThreshold.value"
              size="small"
              type="warning"
              effect="plain"
            >
              合计变动超 30%
            </el-tag>
          </div>
        </template>
        <div class="audit-explain">
          <p class="explain-line">
            （1）信用减值损失本期较上期
            <strong :class="{ 'rate-warn': adj.overallChangeExceedsThreshold.value }">
              {{ adj.overallChangePctText.value }}
            </strong>
            <span class="muted">（负数为减少）</span>
          </p>
          <p class="explain-line">
            （2）主要原因 / 情况说明
            <span v-if="adj.overallChangeExceedsThreshold.value" class="req-tag">必填</span>
          </p>
        </div>
        <el-input
          :model-value="adj.auditNote.value"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 6 }"
          :disabled="isReadonly"
          :class="{ 'reason-required': adj.overallChangeExceedsThreshold.value && !adj.auditNote.value?.trim() }"
          placeholder="结合应收类/债权投资等源科目 ECL 阶段迁移、坏账政策变更、大额核销或转回等，说明重大变动…"
          @update:model-value="adj.updateAuditNote"
        />
      </el-card>

      <el-card shadow="never" class="note-card">
        <template #header>
          <span>2、审计结论</span>
        </template>
        <el-input
          :model-value="adj.auditConclusion.value"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="经审计，信用减值损失在所有重大方面公允反映…"
          @update:model-value="adj.updateAuditConclusion"
        />
      </el-card>
    </div>

    <details class="compile-hint">
      <summary>编制说明【非打印内容】· CAS 22</summary>
      <ol class="hint-list">
        <li v-for="(hint, i) in G14_PREP_HINTS" :key="i">{{ hint }}</li>
      </ol>
      <p class="scope-note">{{ G14_SCOPE_NOTE }}</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
import { computed, inject, toRef } from 'vue'
import { useG14Adjudication } from '../composables/useG14Adjudication'
import { resolveG14SheetLabel } from '../composables/g14SheetLabels'
import { G14_PREP_HINTS, G14_SCOPE_NOTE } from '../composables/g14Constants'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GCycleGuideStrip from '../shared/GCycleGuideStrip.vue'
import WpFourTableSourcePanel from '../shared/WpFourTableSourcePanel.vue'

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
 * 科目由后端按**科目名**逐项目解析（`four_table/g_cycle_specs.G14_SPEC`），
 * 取数口径 = 本期发生额。前端单一真源见 `composables/gCycleAccountScope.ts`。
 */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const adj = useG14Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const tableRows = computed(() => [...adj.dataRows.value, adj.totalRow.value])

function rowClassName({ row }: { row: { rowKey: string; changeRateHighlight?: boolean } }): string {
  const cls: string[] = []
  if (row.rowKey === 'total') cls.push('g14-row-total')
  else if (row.changeRateHighlight) cls.push('g14-row-rate-warn')
  return cls.join(' ')
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
.g14-adjudication {
  padding: 14px 16px 20px;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
  background: linear-gradient(180deg, #f8fafc 0%, #fff 120px);
  border-radius: 8px;
}

.g14-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.g14-header-main { display: flex; flex-direction: column; gap: 2px; }
.g14-title {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
  letter-spacing: 0.02em;
  color: #1f2a37;
}
.g14-subtitle { font-size: 12px; color: #909399; }
.g14-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.objective-alert { margin-bottom: 10px; }
.objective-alert :deep(.el-alert__title) { font-weight: 600; }

.status-strip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 14px;
  margin: 10px 0 12px;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  background: #fff;
  box-shadow: 0 1px 2px rgba(31, 42, 55, 0.04);
}
.status-strip.is-ok { border-color: #b3e19d; background: #f0f9eb; }
.status-strip.is-warn { border-color: #f5dab1; background: #fdf6ec; }
.status-item { display: flex; flex-direction: column; gap: 2px; min-width: 110px; }
.status-label { font-size: 11px; color: #909399; letter-spacing: 0.02em; }
.status-value { font-size: 14px; font-weight: 650; font-variant-numeric: tabular-nums; }
.status-value small { font-size: 12px; font-weight: 500; color: #606266; margin-left: 4px; }
.status-divider { width: 1px; height: 28px; background: #e4e7ed; }
.status-checks { display: flex; gap: 6px; margin-left: auto; flex-wrap: wrap; }

.cross-alert { margin-bottom: 10px; }
.inline-chip { margin-left: 8px; vertical-align: middle; }

.table-wrap {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #ebeef5;
  background: #fff;
}
.g14-table { width: 100%; }
.g14-table :deep(.el-table__header th) {
  background: #f5f7fa !important;
  color: #606266;
  font-weight: 600;
}
.label-cell { display: inline-flex; align-items: center; gap: 4px; }
.is-total-label { font-weight: 700; }
.formula-cell {
  display: inline-block;
  width: 100%;
  border-bottom: 1px dashed #c0c4cc;
  background: #fafafa;
  cursor: help;
  font-variant-numeric: tabular-nums;
  padding: 0 2px;
}
.formula-cell.audited { background: #f0f7ff; border-bottom-color: #a0cfff; font-weight: 600; }
.cell-input { width: 100%; }
.rate-warn { color: #e6a23c; font-weight: 650; }
.is-error { color: #f56c6c; }
.muted { color: #909399; }
.reason-required :deep(.el-input__wrapper),
.reason-required :deep(.el-textarea__inner) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

.recon-panel {
  margin: 14px 0;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid #d9ecff;
  background: #f5faff;
}
.recon-title {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 10px;
}
.recon-body {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.recon-field {
  display: flex;
  align-items: center;
  gap: 8px;
}
.recon-field label { color: #606266; white-space: nowrap; }
.tb-input { width: 148px; }
.tb-readonly { font-variant-numeric: tabular-nums; font-weight: 600; }
.recon-diff {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #e4e7ed;
  font-variant-numeric: tabular-nums;
}
.recon-diff.is-ok { border-color: #b3e19d; color: #67c23a; }
.recon-diff.is-error { border-color: #fbc4c4; color: #f56c6c; background: #fef0f0; }
.recon-diff-label { font-size: 12px; color: #909399; font-weight: 500; }
.recon-ok-mark { font-weight: 700; }
.recon-hint { margin: 8px 0 0; font-size: 12px; color: #909399; }

.notes-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 4px;
}
@media (max-width: 960px) {
  .notes-grid { grid-template-columns: 1fr; }
  .status-divider { display: none; }
  .status-checks { margin-left: 0; width: 100%; }
}
.note-card {
  border-radius: 8px;
  border: 1px solid #ebeef5;
}
.note-card :deep(.el-card__header) {
  padding: 10px 14px;
  background: #fafbfc;
  border-bottom: 1px solid #ebeef5;
  font-weight: 600;
}
.note-card :deep(.el-card__body) { padding: 12px 14px; }
.note-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.audit-explain { margin-bottom: 8px; }
.explain-line { margin: 0 0 6px; color: #606266; line-height: 1.55; }
.req-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  font-size: 11px;
  color: #e6a23c;
  background: #fdf6ec;
  border: 1px solid #f5dab1;
  border-radius: 4px;
  font-weight: 600;
}

.compile-hint {
  margin-top: 16px;
  border-radius: 8px;
  border: 1px solid #d9ecff;
  background: #f5faff;
  padding: 0;
  overflow: hidden;
}
.compile-hint summary {
  cursor: pointer;
  padding: 10px 14px;
  color: #409eff;
  font-weight: 600;
  font-size: 13px;
  list-style: none;
  user-select: none;
}
.compile-hint summary::-webkit-details-marker { display: none; }
.compile-hint[open] summary { border-bottom: 1px solid #d9ecff; background: #ecf5ff; }
.hint-list {
  margin: 0;
  padding: 10px 14px 10px 32px;
  font-size: 12px;
  color: #606266;
  line-height: 1.75;
}
.hint-list li { margin-bottom: 4px; }
.scope-note {
  margin: 0;
  padding: 8px 14px 12px;
  font-size: 12px;
  color: #606266;
  border-top: 1px dashed #b3d8ff;
  background: #fafcff;
  line-height: 1.65;
}

:deep(.g14-row-total) {
  font-weight: 700;
  background: #f0f2f5 !important;
}
:deep(.g14-row-rate-warn) td {
  background: #fffbf0;
}
</style>
