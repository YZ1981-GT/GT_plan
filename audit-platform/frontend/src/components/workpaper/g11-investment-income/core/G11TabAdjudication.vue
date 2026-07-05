<template>
  <div class="g11-adjudication" data-testid="g11-adjudication">
    <div class="g11-toolbar">
      <h3 class="g11-title">G11-1 投资收益审定表</h3>
      <div class="g11-actions">
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-1" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G11-1-adjudication" />
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
      </div>
    </div>

    <GCycleGuideStrip :steps="['G11A 程序', 'G11-1 审定', 'G11-2 明细', 'G11-3 调整', 'G11-4 收益率', '附注披露']" />

    <el-alert
      v-if="adj.detailCrossValidation.value"
      type="warning"
      :closable="false"
      class="cross-alert"
    >
      {{ adj.detailCrossValidation.value }}
      <GtIndexChip v-if="jumpToSection" label="G11-2" :prevent-navigate="true" :validate="false" class="warn-chip"
        @click="jumpToSection(resolveG11SheetLabel('G11-2'))" />
    </el-alert>
    <el-alert v-else-if="adj.hasDetailData.value" type="success" :closable="false" class="cross-alert">
      G11-1 与 G11-2 明细汇总一致
    </el-alert>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>科目 6111 投资收益（损益类/贷方），列为本期数与上期数比较，取发生额非余额递推。</p>
        <p>审定数 = 未审数 + 账项调整；|变动率|&gt;20% 时原因分析必填。</p>
      </div>
    </details>

    <div v-for="group in adj.groupedRows.value" :key="group.groupName" class="group-block">
      <div class="group-head" @click="adj.toggleGroup(group.groupName)">
        <span class="group-toggle">{{ group.collapsed ? '▶' : '▼' }}</span>
        <strong>{{ group.groupName }}</strong>
        <span class="group-sub">本期 {{ fmt(group.subtotal.currentAudited) }}</span>
      </div>
      <el-table v-show="!group.collapsed" :data="group.rows" border size="small" style="font-size:13px" max-height="420"
        :row-class-name="rowClassName">
        <el-table-column label="项目" prop="label" min-width="200" fixed>
          <template #default="{ row }">
            <GtReviewDot row-prefix="G11-adj" :row-key="row.rowKey" />
            {{ row.label }}
          </template>
        </el-table-column>
        <el-table-column label="本期数" align="center">
          <el-table-column label="未审数" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.currentUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'currentUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.currentUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.currentAdjustment" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'currentAdjustment', v ?? 0)" />
              <span v-else>{{ fmt(row.currentAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定=未审+调整">{{ fmt(row.currentAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="上期数" align="center">
          <el-table-column label="未审数" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.priorUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'priorUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.priorUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.priorAdjustment" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'priorAdjustment', v ?? 0)" />
              <span v-else>{{ fmt(row.priorAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.priorAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="变动额" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="80" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reasonAnalysis" size="small"
              :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
              placeholder="|变动率|>20%时必填"
              @change="(v: string) => adj.updateField(row.rowKey, 'reasonAnalysis', v)" />
            <span v-else>{{ row.reasonAnalysis }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
              @change="(v: string) => adj.updateField(row.rowKey, 'indexRef', v)" />
            <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-table :data="[adj.totalRow.value]" border size="small" class="total-table" style="font-size:13px">
      <el-table-column label="项目" prop="label" min-width="200" />
      <el-table-column label="本期审定" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.currentAudited) }}</strong></template>
      </el-table-column>
      <el-table-column label="上期审定" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.priorAudited) }}</strong></template>
      </el-table-column>
      <el-table-column label="变动额" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.changeAmount) }}</template>
      </el-table-column>
      <el-table-column label="变动率" width="80" align="right">
        <template #default="{ row }"><span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span></template>
      </el-table-column>
    </el-table>

    <div class="fine-checks" data-testid="g11-fine-checks">
      <el-tag size="small" :type="adj.hasVarianceHighlight.value ? 'danger' : 'success'">G11-CHK-01 试算表勾稽</el-tag>
      <el-tag size="small" :type="adj.detailMismatch.value ? 'warning' : 'success'">G11-CHK-02 明细勾稽</el-tag>
    </div>

    <div class="g11-tb-row">
      <span>试算平衡表数（6111）：</span>
      <el-input-number v-if="!isReadonly" :model-value="adj.trialBalanceAmount.value" size="small" :controls="false"
        style="width:140px" @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span :class="['variance', { 'is-error': adj.hasVarianceHighlight.value }]">差异：{{ fmt(adj.variance.value) }}</span>
      <el-button size="small" type="primary" :disabled="isReadonly" :loading="publishLoading" @click="onPublish">发布审定数</el-button>
    </div>

    <el-card shadow="never" class="g11-note-card">
      <template #header>审计说明</template>
      <el-input :model-value="adj.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditNote" />
    </el-card>
    <el-card shadow="never" class="g11-note-card">
      <template #header>审计结论</template>
      <el-input :model-value="adj.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditConclusion" />
    </el-card>

    <details class="guidance-details guidance-table-block" open>
      <summary>📋 审计程序指引（{{ guidanceRows.length }} 行，只读）</summary>
      <el-table :data="guidanceRows" border size="small" max-height="360" style="font-size:12px;margin-top:8px">
        <el-table-column label="序号" prop="seq" width="56" align="center" />
        <el-table-column label="程序分类" prop="section" width="120" />
        <el-table-column label="审计程序" prop="procedure" min-width="280" show-overflow-tooltip />
        <el-table-column label="索引提示" prop="indexHint" width="88" />
      </el-table>
    </details>
  </div>
</template>

<script setup lang="ts">
import { inject, toRef, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useG11Adjudication } from '../../composables/useG11Adjudication'
import { G11_AUDIT_GUIDANCE_ROWS } from '../../composables/g11Constants'
import { resolveG11SheetLabel } from '../../composables/g11SheetLabels'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GCycleGuideStrip from '../../shared/GCycleGuideStrip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const guidanceRows = G11_AUDIT_GUIDANCE_ROWS

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const adj = useG11Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const publishLoading = ref(false)

async function onPublish(): Promise<void> {
  if (props.isReadonly) return
  publishLoading.value = true
  try {
    const ok = await adj.validateWithBackend()
    if (!ok) ElMessage.warning('公式校验未通过，请检查审定表与明细表')
    adj.publishAdjudicated()
    await adj.saveAdjudicationToBackend()
    ElMessage.success('审定数已发布')
  } finally {
    publishLoading.value = false
  }
}

function rowClassName({ row }: { row: { changeRateHighlight: boolean; reasonRequired: boolean; reasonAnalysis: string } }): string {
  if (row.changeRateHighlight) return 'g11-row-warn'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | null): string {
  if (rate === null) return 'N/A'
  return (rate * 100).toFixed(1) + '%'
}
</script>

<style scoped>
.g11-adjudication { font-size: 13px; }
.g11-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.g11-title { margin: 0; font-size: 15px; }
.g11-actions { display: flex; gap: 8px; }
.cross-alert { margin-bottom: 8px; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
.group-block { margin-bottom: 8px; }
.group-head { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: #f5f7fa; cursor: pointer; border-radius: 4px; }
.group-sub { margin-left: auto; font-size: 12px; color: #909399; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.g11-tb-row { display: flex; align-items: center; gap: 12px; margin: 12px 0; flex-wrap: wrap; }
.fine-checks { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
.variance.is-error { color: #f56c6c; font-weight: 600; }
.g11-note-card { margin-top: 8px; }
.total-table { margin-top: 4px; }
:deep(.g11-row-warn) { background-color: #fdf6ec !important; }
</style>
