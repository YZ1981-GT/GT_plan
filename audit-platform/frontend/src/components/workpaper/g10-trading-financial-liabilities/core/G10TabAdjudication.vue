<template>
  <div class="g10-adjudication" data-testid="g10-adjudication">
    <div class="g10-toolbar">
      <h3 class="g10-title">G10-1 交易性金融负债审定表</h3>
      <div class="g10-actions">
        <GtReviewTrigger section-id="G10-1-adjudication" />
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>科目 2101 交易性金融负债（贷方/负债类），期末未审 = 期初审定 + 贷方发生额 − 借方发生额。</p>
        <p>审定数 = 未审 + 账项调整；|变动率|&gt;20% 时原因分析必填。</p>
      </div>
    </details>

    <div v-for="group in adj.groupedRows.value" :key="group.groupKey" class="group-block">
      <div class="group-head" @click="adj.toggleGroup(group.groupKey)">
        <span class="group-toggle">{{ group.collapsed ? '▶' : '▼' }}</span>
        <strong>{{ group.groupName }}</strong>
        <span class="group-sub">期末 {{ fmt(group.subtotal.closingAdjusted) }}</span>
      </div>
      <el-table
        v-show="!group.collapsed"
        :data="group.rows"
        border
        size="small"
        style="font-size:13px"
        :max-height="tableMaxHeight"
        :row-class-name="rowClassName"
      >
        <el-table-column label="项目" prop="label" min-width="180" fixed>
          <template #default="{ row }">
            <GtReviewDot row-prefix="G10-adj" :row-key="row.rowKey" />
            {{ row.label }}
          </template>
        </el-table-column>
        <el-table-column label="期初" align="center">
          <el-table-column label="未审" width="92" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.openingUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.openingUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.openingAdjustment" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingAdjustment', v ?? 0)" />
              <span v-else>{{ fmt(row.openingAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定" width="92" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmt(row.openingAdjusted) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="本期发生" align="center">
          <el-table-column label="贷方" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.periodCredit" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'periodCredit', v ?? 0)" />
              <span v-else>{{ fmt(row.periodCredit) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="借方" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.periodDebit" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'periodDebit', v ?? 0)" />
              <span v-else>{{ fmt(row.periodDebit) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末" align="center">
          <el-table-column label="未审" width="92" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期初审定+贷方-借方">{{ fmt(row.closingUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.closingAdjustment" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingAdjustment', v ?? 0)" />
              <span v-else>{{ fmt(row.closingAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定" width="92" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmt(row.closingAdjusted) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="变动额" width="92" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="76" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reasonAnalysis" size="small"
              :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
              placeholder="|变动率|>20%时必填"
              @change="(v: string) => adj.updateField(row.rowKey, 'reasonAnalysis', v)" />
            <span v-else>{{ row.reasonAnalysis }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="72">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
              @change="(v: string) => adj.updateField(row.rowKey, 'indexRef', v)" />
            <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-table :data="[adj.totalRow.value]" border size="small" class="total-table" style="font-size:13px">
      <el-table-column label="项目" prop="label" min-width="180" />
      <el-table-column label="期初审定" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.openingAdjusted) }}</strong></template>
      </el-table-column>
      <el-table-column label="期末审定" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.closingAdjusted) }}</strong></template>
      </el-table-column>
      <el-table-column label="变动额" width="92" align="right">
        <template #default="{ row }">{{ fmt(row.changeAmount) }}</template>
      </el-table-column>
      <el-table-column label="变动率" width="76" align="right">
        <template #default="{ row }"><span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span></template>
      </el-table-column>
    </el-table>

    <el-alert
      v-if="adj.hasDetailCrossMismatch.value"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g10-detail-cross-alert"
    >
      G10-1 合计 {{ fmt(adj.totalRow.value.closingAdjusted) }} 与 G10-2 明细合计
      {{ fmt(adj.detailTotalClosing.value ?? 0) }} 差异 {{ fmt(adj.detailCrossVariance.value ?? 0) }}
    </el-alert>

    <div class="fine-checks" data-testid="g10-fine-checks">
      <el-tag size="small" :type="adj.hasVarianceHighlight.value ? 'danger' : 'success'">G10-CHK-01 试算表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasFormulaMismatch.value ? 'warning' : 'success'">G10-CHK-02 贷方公式勾稽</el-tag>
      <el-tag size="small" :type="adj.hasDetailCrossMismatch.value ? 'warning' : 'success'">G10-CHK-03 明细表勾稽</el-tag>
    </div>

    <div class="g10-tb-row">
      <span>试算平衡表数（2101）：</span>
      <el-input-number v-if="!isReadonly" :model-value="adj.trialBalanceAmount.value" size="small" :controls="false"
        style="width:140px" @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span :class="['variance', { 'is-error': adj.hasVarianceHighlight.value }]">差异：{{ fmt(adj.variance.value) }}</span>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.publishAdjudicated()">发布审定数</el-button>
    </div>

    <el-card shadow="never" class="g10-note-card">
      <template #header>审计说明</template>
      <el-input v-if="!isReadonly" v-model="noteProxy" type="textarea" :rows="3" placeholder="审定分析说明" />
      <p v-else class="note-text">{{ adj.auditNote.value || '—' }}</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG10Adjudication } from '../../composables/useG10Adjudication'
import { G10_VIRTUAL_SCROLL_THRESHOLD } from '../../composables/g10Constants'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const adj = useG10Adjudication({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const tableMaxHeight = computed(() =>
  adj.dataRows.value.length >= G10_VIRTUAL_SCROLL_THRESHOLD ? 480 : undefined,
)

const noteProxy = computed({
  get: () => adj.auditNote.value,
  set: (v: string) => adj.updateAuditNote(v),
})

function fmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | null): string {
  if (rate == null) return '—'
  return (rate * 100).toFixed(1) + '%'
}

function rowClassName({ row }: { row: { reasonRequired?: boolean; reasonAnalysis?: string } }) {
  if (row.reasonRequired && !row.reasonAnalysis) return 'row-warn'
  return ''
}
</script>

<style scoped>
.g10-adjudication { font-size: 13px; }
.g10-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.g10-title { margin: 0; font-size: 15px; }
.g10-actions { display: flex; gap: 8px; }
.guidance-details { margin-bottom: 10px; font-size: 12px; color: #606266; }
.group-block { margin-bottom: 8px; }
.group-head { display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: #f5f7fa; cursor: pointer; border-radius: 4px; }
.group-toggle { font-size: 11px; color: #909399; }
.group-sub { margin-left: auto; font-size: 12px; color: #606266; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.fine-checks { display: flex; gap: 8px; margin: 10px 0; }
.g10-tb-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 10px 0; }
.variance.is-error { color: #f56c6c; font-weight: 600; }
.g10-note-card { margin-top: 8px; }
.note-text { margin: 0; white-space: pre-wrap; }
.total-table { margin-top: 8px; }
:deep(.row-warn) { background-color: #fdf6ec !important; }
</style>
