<template>
  <div class="g8-adjudication" data-testid="g8-adjudication">
    <div class="g8-toolbar">
      <h3 class="g8-title">G8-1 其他权益工具投资审定表</h3>
      <div class="g8-actions">
        <GtReviewTrigger section-id="G8-1-adjudication" />
        <el-button size="small" :loading="validateLoading" :disabled="isReadonly" data-testid="g8-validate-btn" @click="runValidate">校验公式</el-button>
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>科目 1503 其他权益工具投资（借方/资产类），公允价值计量且变动计入 OCI。</p>
        <p>审定数 = 未审 + 账项调整；|变动率|&gt;20% 时原因分析必填。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实其他权益工具投资（科目1503）期末余额的存在与计价，验证以公允价值计量且变动计入其他综合收益（OCI）分类的恰当性，确认审定数与试算表、明细表勾稽一致。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rowCount }} 行</el-tag>
      </div>
    </div>

    <el-alert
      v-if="adj.hasMissingReasons.value"
      type="warning"
      :closable="false"
      class="reason-alert"
      data-testid="g8-adj-reason-warn"
      :title="`有 ${adj.missingReasonCount.value} 行 |变动率|>20%，请填写原因分析`"
    />

    <div v-for="group in adj.groupedRows.value" :key="group.groupKey" class="group-block">
      <div class="group-head" @click="adj.toggleGroup()">
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
        :max-height="480"
        :row-class-name="rowClassName"
      >
        <el-table-column label="项目" prop="label" min-width="180" fixed>
          <template #default="{ row }">
            <GtReviewDot row-prefix="G8-adj" :row-key="row.rowKey" />
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
            <template #default="{ row }"><span class="formula-cell" title="未审+调整">{{ fmt(row.openingAdjusted) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末" align="center">
          <el-table-column label="未审" width="92" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.closingUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.closingUnadjusted) }}</span>
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
            <template #default="{ row }"><span class="formula-cell" title="未审+调整">{{ fmt(row.closingAdjusted) }}</span></template>
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
      data-testid="g8-detail-cross-alert"
    >
      G8-1 合计 {{ fmt(adj.totalRow.value.closingAdjusted) }} 与 G8-2 明细合计
      {{ fmt(adj.detailTotalClosing.value ?? 0) }} 差异 {{ fmt(adj.detailCrossVariance.value ?? 0) }}
    </el-alert>

    <div class="fine-checks" data-testid="g8-fine-checks">
      <el-tag size="small" :type="adj.hasVarianceHighlight.value ? 'danger' : 'success'">G8-CHK-01 试算表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasDetailCrossMismatch.value ? 'warning' : 'success'">G8-CHK-02 明细表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasMissingReasons.value ? 'warning' : 'success'">G8-CHK-03 变动率原因</el-tag>
    </div>

    <div class="g8-tb-row">
      <span>试算平衡表数（1503）：</span>
      <el-input-number v-if="!isReadonly" :model-value="adj.trialBalanceAmount.value" size="small" :controls="false"
        style="width:140px" @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span :class="['variance', { 'is-error': adj.hasVarianceHighlight.value }]">差异：{{ fmt(adj.variance.value) }}</span>
      <el-button v-if="!isReadonly" size="small" link @click="adj.loadTrialBalanceFromApi()">刷新TB</el-button>
      <el-button size="small" type="primary" :disabled="isReadonly" data-testid="g8-publish-adj" @click="adj.publishAdjudicated()">发布审定数</el-button>
    </div>

    <el-card shadow="never" class="g8-note-card">
      <template #header>审计说明</template>
      <el-input v-if="!isReadonly" v-model="noteProxy" type="textarea" :rows="3" placeholder="审定分析说明" />
      <p v-else class="note-text">{{ adj.auditNote.value || '—' }}</p>
    </el-card>

    <el-card shadow="never" class="g8-note-card">
      <template #header>审计结论</template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论：审定数是否准确、分类（OCI）是否恰当，是否与试算表及明细表勾稽一致。" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG8Adjudication } from '../../composables/useG8Adjudication'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const validateLoading = ref(false)

const AUDIT_CONCLUSION_KEY = 'G8-1-audit-conclusion'
const auditConclusion = ref(props.allResponses.get(AUDIT_CONCLUSION_KEY)?.remark ?? '')
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: null, remark: v })
})

const adj = useG8Adjudication({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const noteProxy = computed({
  get: () => adj.auditNote.value,
  set: (v: string) => adj.updateAuditNote(v),
})

const rowCount = computed(() =>
  adj.groupedRows.value.reduce((n, g) => n + (g.rows?.length ?? 0), 0),
)

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
</script>

<style scoped>
.g8-adjudication { font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }
.g8-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.g8-title { margin: 0; font-size: 15px; }
.g8-actions { display: flex; gap: 8px; }
.guidance-details { margin-bottom: 10px; font-size: 12px; color: #606266; }
.reason-alert { margin-bottom: 8px; }
.group-block { margin-bottom: 8px; }
.group-head { display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: #f5f7fa; cursor: pointer; border-radius: 4px; }
.group-toggle { font-size: 11px; color: #909399; }
.group-sub { margin-left: auto; font-size: 12px; color: #606266; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.g8-tb-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 10px 0; }
.variance.is-error { color: #f56c6c; font-weight: 600; }
.g8-note-card { margin-top: 8px; }
.note-text { margin: 0; white-space: pre-wrap; }
.total-table { margin-top: 8px; }
.cross-alert { margin: 8px 0; }
.fine-checks { display: flex; gap: 8px; margin: 10px 0; flex-wrap: wrap; }
:deep(.row-warn) { background-color: #fdf6ec !important; }
</style>
