<template>
  <div class="g14-adjudication" data-testid="g14-adjudication">
    <div class="g14-toolbar tab-toolbar">
      <h3 class="g14-title">G14-1 信用减值损失审定表</h3>
      <div class="g14-actions">
        <GtIndexChip value="wp:G14-1" />
        <el-tag size="small" type="info">共 {{ adj.dataRows.value.length }} 行</el-tag>
        <GtReviewTrigger section-id="G14-1-adjudication" />
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：确认本期信用减值损失（6702，损益类，取本期发生额 借方计提−贷方转回）计提/转回充分、准确，
        各减值来源与 D1/D2/D5/G4/G5 等源科目 ECL 勾稽一致，变动合理且披露完整（CAS 22 金融工具 — 预期信用损失 ECL）。
      </template>
    </el-alert>

    <GCycleGuideStrip :steps="['G14A 程序', 'G14-1 审定', 'G14-2 明细', 'G14-3 调整', '附注披露']" />

    <el-alert
      v-if="adj.detailCrossValidation.value"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g14-adj-detail-cross-bar"
    >
      {{ adj.detailCrossValidation.value }}
      <GtIndexChip
        v-if="jumpToSection"
        label="G14-2"
        :prevent-navigate="true"
        :validate="false"
        class="warn-chip"
        @click="jumpToSection(resolveG14SheetLabel('G14-2'))"
      />
    </el-alert>
    <el-alert
      v-else-if="adj.hasDetailData.value"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g14-adj-detail-cross-ok"
    >
      G14-1 与 G14-2 明细汇总一致
      <GtIndexChip
        v-if="jumpToSection"
        label="G14-2"
        :prevent-navigate="true"
        :validate="false"
        class="ok-chip"
        @click="jumpToSection(resolveG14SheetLabel('G14-2'))"
      />
    </el-alert>
    <el-alert
      v-else
      type="info"
      :closable="false"
      class="cross-alert"
      data-testid="g14-adj-detail-cross-pending"
    >
      待 G14-2 明细录入后自动校验 G14-1↔G14-2 汇总一致
    </el-alert>

    <el-table :data="tableRows" border size="small" style="font-size:13px" max-height="520"
      :row-class-name="rowClassName">
      <el-table-column label="项目" prop="label" width="168" fixed>
        <template #default="{ row }">
          <GtReviewDot v-if="row.rowKey !== 'total'" row-prefix="G14-adj" :row-key="row.rowKey" />
          {{ row.label }}
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
      <el-table-column label="原因分析" min-width="140">
        <template #default="{ row }">
          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.reasonAnalysis" size="small"
            :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
            placeholder="|变动率|>30%时必填"
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

    <div class="g14-tb-row">
      <span>试算平衡表数（6702）：</span>
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

    <el-card shadow="never" class="g14-note-card">
      <template #header>审计说明</template>
      <el-input :model-value="adj.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditNote" />
    </el-card>
    <el-card shadow="never" class="g14-note-card">
      <template #header>审计结论</template>
      <el-input :model-value="adj.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <div class="hint-content">
        1. 本期数（未审/调整/审定）自 G14-2 明细自动汇总；上期数独立录入，用于变动分析。<br>
        2. 变动率 |&gt;30%| 时「原因分析」必填；审定合计须与试算平衡表 6702 发生额一致（差异高亮）。<br>
        3. CAS 22 金融工具确认与计量：信用减值损失反映预期信用损失（ECL）模型下坏账/债权投资减值准备的本期计提与转回，损益方向为借方计提、贷方转回，取本期发生额。<br>
        4. 「发布审定数」后经 EventBus 同步至附注披露；各减值来源与 D1/D2/D5/G4/G5 源科目 ECL 交叉核对。
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { useG14Adjudication } from '../composables/useG14Adjudication'
import { resolveG14SheetLabel } from '../composables/g14SheetLabels'
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

const adj = useG14Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const tableRows = computed(() => [...adj.dataRows.value, adj.totalRow.value])

function rowClassName({ row }: { row: { rowKey: string } }): string {
  return row.rowKey === 'total' ? 'g14-row-total' : ''
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
.g14-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g14-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.g14-actions { display: flex; gap: 8px; align-items: center; }
.g14-title { margin: 0; font-size: 15px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.g14-tb-row { display: flex; align-items: center; gap: 16px; margin: 12px 0; flex-wrap: wrap; }
.variance { font-weight: 600; }
.variance.is-error { color: #f56c6c; }
.g14-note-card { margin-top: 12px; }
.audit-objective { margin-bottom: 12px; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; }
.compile-hint summary { padding: 8px 12px; cursor: pointer; font-size: var(--wp-font-size, 13px); color: #409eff; }
.hint-content { padding: 0 12px 12px; font-size: 12px; color: #606266; line-height: 1.8; }
.cross-alert { margin-bottom: 12px; }
.warn-chip, .ok-chip { margin-left: 8px; }
.cross-ok :deep(.el-alert__content) { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
:deep(.g14-row-total) { font-weight: 700; background: #f5f7fa; }
</style>
