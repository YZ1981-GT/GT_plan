<template>
  <div class="g13-adjudication" data-testid="g13-adjudication">
    <div class="g13-toolbar">
      <h3 class="g13-title">G13-1 公允价值变动收益审定表</h3>
      <div class="g13-actions">
        <GtReviewTrigger section-id="G13-1-adjudication" />
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
      </div>
    </div>

    <GCycleGuideStrip :steps="['G13A 程序', 'G13-1 审定', 'G13-2 明细', 'G13-3 调整', '附注披露']" />

    <el-alert
      v-if="adj.detailCrossValidation.value"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g13-adj-detail-cross-bar"
    >
      {{ adj.detailCrossValidation.value }}
      <GtIndexChip
        v-if="jumpToSection"
        label="G13-2"
        :prevent-navigate="true"
        :validate="false"
        class="warn-chip"
        @click="jumpToSection(resolveG13SheetLabel('G13-2'))"
      />
    </el-alert>
    <el-alert
      v-else-if="adj.hasDetailData.value"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g13-adj-detail-cross-ok"
    >
      G13-1 与 G13-2 明细汇总一致
      <GtIndexChip
        v-if="jumpToSection"
        label="G13-2"
        :prevent-navigate="true"
        :validate="false"
        class="ok-chip"
        @click="jumpToSection(resolveG13SheetLabel('G13-2'))"
      />
    </el-alert>
    <el-alert
      v-else
      type="info"
      :closable="false"
      class="cross-alert"
      data-testid="g13-adj-detail-cross-pending"
    >
      待 G13-2 明细录入后自动校验 G13-1↔G13-2 汇总一致
    </el-alert>

    <el-table :data="tableRows" border size="small" style="font-size:13px" max-height="520"
      :row-class-name="rowClassName">
      <el-table-column label="项目" prop="label" width="200" fixed>
        <template #default="{ row }">
          <GtReviewDot v-if="row.rowKey !== 'total'" row-prefix="G13-adj" :row-key="row.rowKey" />
          {{ row.label }}
        </template>
      </el-table-column>

      <el-table-column label="本期数" align="center">
        <el-table-column label="未审数" width="108" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="自 G13-2 明细按科目汇总">{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整数" width="108" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="自 G13-2 明细汇总">{{ fmt(row.currentAdjustment) }}</span>
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
            <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorUnadjusted"
              size="small" :controls="false" style="width:100%"
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
            <span class="formula-cell" title="审定 = 未审 + 调整">{{ fmt(row.priorAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="变动额" width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="变动额 = 本期审定 - 上期审定">{{ fmt(row.changeAmount) }}</span>
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

    <div class="g13-tb-row">
      <span>试算平衡表数（6101）：</span>
      <el-input-number v-if="!isReadonly" :model-value="adj.trialBalanceAmount.value" size="small" :controls="false"
        style="width:140px" @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span :class="['variance', { 'is-error': adj.hasVarianceHighlight.value }]">
        差异：{{ fmt(adj.variance.value) }}
      </span>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.publishAdjudicated()">
        发布审定数
      </el-button>
    </div>

    <el-card shadow="never" class="g13-note-card">
      <template #header>审计说明</template>
      <el-input :model-value="adj.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditNote" />
    </el-card>
    <el-card shadow="never" class="g13-note-card">
      <template #header>审计结论</template>
      <el-input :model-value="adj.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <p>1. 本期各行未审/调整/审定数自 G13-2 明细按所属科目自动汇总，仅上期数及原因分析需手工录入。</p>
      <p>2. |变动率|>20% 的行须填写原因分析；审定合计应与试算平衡表 6101 发生额一致，差异需查明。</p>
      <p>3. 「发布审定数」将审定合计广播至附注披露与 TB 回写（CAS 39 公允价值计量，损益取发生额口径）。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { useG13Adjudication } from '../composables/useG13Adjudication'
import { resolveG13SheetLabel } from '../composables/g13SheetLabels'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GCycleGuideStrip from '../shared/GCycleGuideStrip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const adj = useG13Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const tableRows = computed(() => [...adj.dataRows.value, adj.totalRow.value])

function rowClassName({ row }: { row: { rowKey: string } }): string {
  return row.rowKey === 'total' ? 'g13-row-total' : ''
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
.g13-adjudication { padding: 12px; font-size: 13px; }
.g13-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.g13-actions { display: flex; gap: 8px; align-items: center; }
.g13-title { margin: 0; font-size: 15px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #fafafa; display: inline-block; width: 100%; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.g13-tb-row { display: flex; align-items: center; gap: 16px; margin: 12px 0; flex-wrap: wrap; }
.variance { font-weight: 600; }
.variance.is-error { color: #f56c6c; }
.g13-note-card { margin-top: 12px; }
.cross-alert { margin-bottom: 12px; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266; }
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
.warn-chip, .ok-chip { margin-left: 8px; }
.cross-ok :deep(.el-alert__content) { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
:deep(.g13-row-total) { font-weight: 700; background: #f5f7fa; }
</style>
