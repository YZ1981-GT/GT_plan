<template>
  <div class="g9-adjudication" data-testid="g9-adjudication">
    <div class="g9-toolbar">
      <h3 class="g9-title">G9-1 其他非流动金融资产审定表</h3>
      <div class="g9-actions">
        <GtIndexChip value="wp:G9-1" />
        <el-tag size="small" type="info">共 {{ adjRowCount }} 行</el-tag>
        <GtReviewTrigger section-id="G9-1-adjudication" />
        <el-button size="small" :loading="validateLoading" :disabled="isReadonly" data-testid="g9-validate-btn" @click="runValidate">校验公式</el-button>
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：确认其他非流动金融资产（1504）期末余额真实存在、完整、计价准确，混合计量分类与附注列报恰当。"
    />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>科目 1504 其他非流动金融资产（借方/资产类），含 FVTPL、FVOCI、摊余成本混合计量。</p>
        <p>审定数 = 未审 + AJE + RJE；|变动率|&gt;20% 时原因分析必填。</p>
      </div>
    </details>

    <div v-if="adj.hasVarianceHighlight.value" class="tb-bar tb-warn">
      试算表取数(1504): {{ fmt(adj.trialBalanceAmount.value) }}
      | 差异: {{ fmt(adj.variance.value) }}
      <el-button v-if="!isReadonly" size="small" link @click="adj.loadTrialBalanceFromApi()">刷新TB</el-button>
    </div>
    <div v-else class="tb-bar">
      试算表取数(1504): {{ fmt(adj.trialBalanceAmount.value) }}
      | 差异: {{ fmt(adj.variance.value) }}
      <el-button v-if="!isReadonly" size="small" link @click="adj.loadTrialBalanceFromApi()">刷新TB</el-button>
    </div>

    <el-alert
      v-if="adj.hasMissingReasons.value"
      type="warning"
      :closable="false"
      class="reason-alert"
      data-testid="g9-adj-reason-warn"
      :title="`有 ${adj.missingReasonCount.value} 行 |变动率|>20%，请填写原因分析`"
    />

    <div v-if="useVirtualScroll" class="virtual-toolbar" data-testid="g9-adj-virtual-toolbar">
      <el-button size="small" @click="toggleBrowseMode">{{ browseMode ? '切换编辑模式' : '切换浏览模式' }}</el-button>
      <span class="hint">74 行数据 — 双击行进入编辑</span>
    </div>

    <el-table-v2
      v-if="useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="browseRows"
      :width="tableWidth"
      :height="tableHeight"
      :row-event-handlers="rowEventHandlers"
      fixed
      style="margin-bottom:12px"
      data-testid="g9-adj-virtual-table"
    />

    <template v-if="!useVirtualScroll || !browseMode">
    <div v-for="group in adj.groupedRows.value" :key="group.groupKey" class="group-block">
      <div class="group-head" @click="adj.toggleGroup(group.groupKey)">
        <span>{{ group.collapsed ? '▶' : '▼' }}</span>
        <strong>{{ group.groupName }}</strong>
        <span class="group-sub">期末 {{ fmt(group.subtotal.closingAdjusted) }}</span>
      </div>
      <el-table
        v-show="!group.collapsed"
        :data="group.rows"
        border size="small"
        style="font-size:13px"
        :max-height="480"
        :row-class-name="rowClassName"
      >
        <el-table-column label="项目" prop="label" min-width="160" fixed>
          <template #default="{ row }">
            <GtReviewDot row-prefix="G9-adj" :row-key="row.rowKey" />
            {{ row.label }}
          </template>
        </el-table-column>
        <el-table-column label="期初未审" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingUnadjusted" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingUnadjusted', v ?? 0)" />
            <span v-else>{{ fmt(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingAJE" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingAJE', v ?? 0)" />
            <span v-else>{{ fmt(row.openingAJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingRJE" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingRJE', v ?? 0)" />
            <span v-else>{{ fmt(row.openingRJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定" width="92" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期初审定 = 期初未审 + AJE + RJE">{{ fmt(row.openingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="期末未审" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingUnadjusted" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingUnadjusted', v ?? 0)" />
            <span v-else>{{ fmt(row.closingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingAJE" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingAJE', v ?? 0)" />
            <span v-else>{{ fmt(row.closingAJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingRJE" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingRJE', v ?? 0)" />
            <span v-else>{{ fmt(row.closingRJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定" width="92" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期末审定 = 期末未审 + AJE + RJE">{{ fmt(row.closingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="72" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reasonAnalysis" size="small"
              :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis?.trim() }"
              placeholder="|变动率|>20%时必填"
              @update:model-value="(v: string) => adj.updateField(row.rowKey, 'reasonAnalysis', v)" />
            <span v-else>{{ row.reasonAnalysis }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="72">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
              @update:model-value="(v: string) => adj.updateField(row.rowKey, 'indexRef', v)" />
            <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          </template>
        </el-table-column>
      </el-table>
    </div>
    </template>

    <div class="total-row">
      <strong>合计</strong> 期末审定 {{ fmt(adj.totalRow.value.closingAdjusted) }}
    </div>

    <div v-if="adj.hasDetailCrossMismatch.value" class="cross-warn" data-testid="g9-detail-cross-warn">
      G9-1 合计 {{ fmt(adj.totalRow.value.closingAdjusted) }} 与 G9-2 明细合计
      {{ fmt(adj.detailTotalClosing.value ?? 0) }} 差异 {{ fmt(adj.detailCrossVariance.value ?? 0) }}
    </div>

    <div class="fine-checks" data-testid="g9-fine-checks">
      <el-tag size="small" :type="adj.hasVarianceHighlight.value ? 'danger' : 'success'">G9-CHK-01 试算表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasDetailCrossMismatch.value ? 'warning' : 'success'">G9-CHK-02 明细表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasMissingReasons.value ? 'warning' : 'success'">G9-CHK-03 变动率原因</el-tag>
    </div>

    <div class="g9-tb-row">
      <span>试算平衡表数（1504）：</span>
      <el-input-number v-if="!isReadonly" :model-value="adj.trialBalanceAmount.value" size="small" :controls="false"
        style="width:140px" @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span :class="['variance', { 'is-error': adj.hasVarianceHighlight.value }]">差异：{{ fmt(adj.variance.value) }}</span>
      <el-button v-if="!isReadonly" size="small" link @click="adj.loadTrialBalanceFromApi()">刷新TB</el-button>
      <el-button size="small" type="primary" :disabled="isReadonly" data-testid="g9-publish-adj" @click="adj.publishAdjudicated()">发布审定数</el-button>
    </div>

    <el-card shadow="never" class="g9-note-card">
      <template #header>审计说明</template>
      <el-input v-if="!isReadonly" v-model="noteProxy" type="textarea" :rows="3" placeholder="审定分析说明" />
      <p v-else class="note-text">{{ adj.auditNote.value || '—' }}</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, ref } from 'vue'
import { ElMessage } from 'element-plus'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG9Adjudication } from '../../composables/useG9Adjudication'
import { useWorkpaperBrowseMode } from '../../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const validateLoading = ref(false)

const adj = useG9Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const noteProxy = computed({
  get: () => adj.auditNote.value,
  set: (v: string) => adj.updateAuditNote(v),
})

const adjRowCount = computed(() =>
  adj.groupedRows.value.reduce((n, g) => n + g.rows.length, 0),
)

const browseRows = computed(() =>
  adj.groupedRows.value.flatMap((g) =>
    g.rows.map((r) => ({
      groupName: g.groupName,
      label: r.label,
      openingAdjusted: r.openingAdjusted,
      closingAdjusted: r.closingAdjusted,
      closingAJE: r.closingAJE,
      closingRJE: r.closingRJE,
      changeRate: r.changeRate,
    })),
  ),
)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('groupName', '分组', 200),
  virtualTextCol('label', '项目', 180),
  virtualNumCol('openingAdjusted', '期初审定', 100, (v) => fmt(Number(v) || 0)),
  virtualNumCol('closingAJE', '期末AJE', 88, (v) => fmt(Number(v) || 0)),
  virtualNumCol('closingRJE', '期末RJE', 88, (v) => fmt(Number(v) || 0)),
  virtualNumCol('closingAdjusted', '期末审定', 100, (v) => fmt(Number(v) || 0)),
])

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  threshold: 30,
  tableWidth: 1100,
  tableHeight: 520,
})

async function runValidate() {
  validateLoading.value = true
  try {
    const res = await adj.validateFormulasRemote()
    if (res.ok) ElMessage.success('公式校验通过')
    else ElMessage.warning(`发现 ${res.errors.length} 处公式差异`)
  } finally {
    validateLoading.value = false
  }
}

function fmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRate(r: number | null): string {
  if (r === null) return '—'
  return `${(r * 100).toFixed(1)}%`
}

function rowClassName({ row }: { row: { reasonRequired?: boolean; reasonAnalysis?: string } }): string {
  if (row.reasonRequired && !row.reasonAnalysis?.trim()) return 'row-warn'
  return ''
}
</script>

<style scoped>
.g9-adjudication { font-size: 13px; }
.g9-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.g9-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.g9-title { margin: 0; font-size: 15px; }
.tb-bar { margin-bottom: 10px; padding: 8px; background: #f5f7fa; border-radius: 4px; }
.tb-warn { color: #f56c6c; background: #fef0f0; }
.group-head { cursor: pointer; padding: 8px; background: #fafafa; border: 1px solid #ebeef5; margin-top: 8px; display: flex; gap: 8px; align-items: center; }
.group-sub { margin-left: auto; color: #606266; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #f5f7fa; display: inline-block; width: 100%; }
.audit-objective { margin-bottom: 10px; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-alert { margin-bottom: 8px; }
:deep(.reason-required .el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
:deep(.row-warn) { background: #fdf6ec !important; }
.total-row { margin-top: 12px; padding: 10px; background: #ecf5ff; font-weight: 600; }
.cross-warn { margin-top: 8px; padding: 8px 12px; background: #fdf6ec; color: #e6a23c; border-radius: 4px; font-size: 12px; }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.virtual-toolbar .hint { color: #909399; font-size: 12px; }
.guidance-details { margin-bottom: 10px; font-size: 12px; color: #606266; }
.g9-tb-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 10px 0; }
.variance.is-error { color: #f56c6c; font-weight: 600; }
.g9-note-card { margin-top: 8px; }
.note-text { margin: 0; white-space: pre-wrap; }
.fine-checks { display: flex; gap: 8px; margin: 10px 0; flex-wrap: wrap; }
</style>
