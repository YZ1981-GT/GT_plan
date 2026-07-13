<template>
  <div class="h10-adjudication" data-testid="h10-adjudication">
    <div class="h10-toolbar">
      <h3 class="h10-title">H10-1 资产处置损益审定表</h3>
      <div class="h10-actions">
        <GtReviewTrigger section-id="H10-1-adjudication" />
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" data-testid="h10-adj-ai-btn" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
        <el-button size="small" :loading="validateLoading" :disabled="isReadonly" data-testid="h10-validate-btn" @click="runValidate">校验公式</el-button>
      </div>
    </div>

    <GCycleGuideStrip :steps="['H10A 程序', 'H10-1 审定', 'H10-2 明细', 'H10-3 调整', 'H10-4 检查', '附注披露']" />

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：确认资产处置损益（6115 发生额）的完整性与准确性，验证处置损益确认时点恰当、分类列报正确，为财务报表列报提供审定依据。" />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H10-1" :context-project-id="projectId" /></span>
      </div>
    </div>

    <el-alert v-if="adj.detailCrossValidation.value" type="warning" :closable="false" class="cross-alert">
      {{ adj.detailCrossValidation.value }}
      <GtIndexChip v-if="jumpToSection" label="H10-2" :prevent-navigate="true" :validate="false"
        @click="jumpToSection(resolveH10SheetLabel('H10-2'))" />
    </el-alert>
    <el-alert v-else-if="adj.hasDetailData.value" type="success" :closable="false" class="cross-alert">
      H10-1 与 H10-2 明细汇总一致
    </el-alert>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>科目 6115 资产处置损益（损益类/贷方），取<strong>发生额</strong>（贷方-借方），非期末余额。</p>
        <p>审定数 = 未审数 + AJE + RJE；|变动率|&gt;20% 时原因分析必填。</p>
      </div>
    </details>

    <div v-for="group in adj.groupedRows.value" :key="group.groupName" class="group-block">
      <div class="group-head" @click="adj.toggleGroup(group.groupName)">
        <span class="group-toggle">{{ group.collapsed ? '▶' : '▼' }}</span>
        <strong>{{ group.groupName }}</strong>
        <span class="group-sub">本期 {{ fmt(group.subtotal.currentAudited) }}</span>
      </div>
      <el-table v-show="!group.collapsed" :data="group.rows" border size="small" style="font-size:13px" max-height="420">
        <el-table-column label="项目" prop="label" min-width="180" fixed>
          <template #default="{ row }">
            <GtReviewDot row-prefix="H10-adj" :row-key="row.rowKey" />
            {{ row.label }}
          </template>
        </el-table-column>
        <el-table-column label="本期数" align="center">
          <el-table-column label="未审" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.currentUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'currentUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.currentUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="AJE" width="80" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.currentAje" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'currentAje', v ?? 0)" />
              <span v-else>{{ fmt(row.currentAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="RJE" width="80" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.currentRje" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'currentRje', v ?? 0)" />
              <span v-else>{{ fmt(row.currentRje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定" width="88" align="right">
            <template #default="{ row }"><span class="formula-cell" title="未审+AJE+RJE">{{ fmt(row.currentAudited) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="上期审定" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.priorAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="72" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reasonAnalysis" size="small"
              :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
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
      <el-table-column label="本期审定" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.currentAudited) }}</strong></template>
      </el-table-column>
      <el-table-column label="上期审定" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.priorAudited) }}</strong></template>
      </el-table-column>
    </el-table>

    <div class="fine-checks" data-testid="h10-fine-checks">
      <el-tag size="small" :type="adj.hasVarianceHighlight.value ? 'danger' : 'success'">H10-CHK-01 试算表勾稽（6115发生额）</el-tag>
      <el-tag size="small" :type="adj.detailMismatch.value ? 'warning' : 'success'">H10-CHK-02 明细勾稽</el-tag>
      <el-tag size="small" :type="cross.h10VsH6.value.h6Available && !cross.h10VsH6.value.isMatch ? 'warning' : 'success'">
        H10-CHK-03 H6清理勾稽{{ cross.h10VsH6.value.h6Available ? '' : '（无H6数据）' }}
      </el-tag>
      <el-tag size="small" :type="cross.hasSourceWpMismatch.value ? 'warning' : 'success'">H10-CHK-04 源底稿分类型勾稽</el-tag>
    </div>
    <el-alert v-if="cross.h10VsH6.value.h6Available && !cross.h10VsH6.value.isMatch" type="warning" :closable="false" class="cross-alert">
      固定资产处置审定 {{ cross.h10VsH6.value.h10FixedAssetTotal.toFixed(2) }} 与 H6 清理净损益 {{ cross.h10VsH6.value.h6NetGainLoss?.toFixed(2) }} 差异 {{ cross.h10VsH6.value.diff.toFixed(2) }}
    </el-alert>
    <el-alert v-if="cross.hasSourceWpMismatch.value" type="warning" :closable="false" class="cross-alert">
      源底稿明细与审定行不一致：{{ cross.sourceWpMismatches.value.filter(m => !m.isMatch).map(m => m.sourceWp).join('、') }}
    </el-alert>

    <div class="h10-tb-row">
      <span>试算平衡表数（6115 发生额）：</span>
      <el-input-number v-if="!isReadonly" :model-value="adj.trialBalanceAmount.value" size="small" :controls="false"
        style="width:140px" @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span :class="['variance', { 'is-error': adj.hasVarianceHighlight.value }]">差异：{{ fmt(adj.variance.value) }}</span>
      <el-button v-if="!isReadonly" size="small" link @click="adj.loadTrialBalanceFromApi()">刷新TB</el-button>
      <el-button size="small" type="primary" :disabled="isReadonly" :loading="publishLoading" data-testid="h10-publish-adj" @click="onPublish">发布审定数</el-button>
    </div>

    <el-card shadow="never" class="h10-note-card">
      <template #header>审计说明</template>
      <el-input :model-value="adj.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditNote" />
    </el-card>
    <el-card shadow="never" class="h10-note-card">
      <template #header>审计结论</template>
      <el-input :model-value="adj.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { inject, toRef, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useH10Adjudication } from '../../composables/useH10Adjudication'
import { useH10CrossSheet } from '../../composables/useH10CrossSheet'
import { resolveH10SheetLabel } from '../../composables/h10SheetLabels'
import type { ChecklistResponse } from '../../composables/useF1FormData'
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
  writebackTrialBalance?: (amount: number) => Promise<void>
}>()

const emit = defineEmits<{ imported: [] }>()
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
const validateLoading = ref(false)
const publishLoading = ref(false)

const adj = useH10Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
  writebackTrialBalance: props.writebackTrialBalance,
})

const cross = useH10CrossSheet({ allResponses: toRef(props, 'allResponses') })

async function runValidate(): Promise<void> {
  validateLoading.value = true
  try {
    const ok = await adj.validateWithBackend()
    ElMessage[ok ? 'success' : 'warning'](ok ? '公式校验通过' : '公式校验未通过')
  } finally {
    validateLoading.value = false
  }
}

async function onPublish(): Promise<void> {
  if (props.isReadonly) return
  publishLoading.value = true
  try {
    const ok = await adj.validateWithBackend()
    if (!ok) ElMessage.warning('公式校验未通过，请检查审定表与明细表')
    await adj.publishAdjudicated()
    await adj.saveAdjudicationToBackend()
    ElMessage.success('审定数已发布（6115 发生额已回写）')
  } finally {
    publishLoading.value = false
  }
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
.h10-adjudication { font-size: var(--wp-font-size, 13px); }
.h10-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.h10-title { margin: 0; font-size: 15px; }
.h10-actions { display: flex; gap: 8px; }
.cross-alert { margin-bottom: 8px; }
.objective-alert { margin-bottom: 8px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
.group-block { margin-bottom: 8px; }
.group-head { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: #f5f7fa; cursor: pointer; border-radius: 4px; }
.group-sub { margin-left: auto; font-size: 12px; color: #909399; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.fine-checks { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
.h10-tb-row { display: flex; align-items: center; gap: 12px; margin: 12px 0; flex-wrap: wrap; }
.variance.is-error { color: #f56c6c; font-weight: 600; }
.h10-note-card { margin-top: 8px; }
</style>
