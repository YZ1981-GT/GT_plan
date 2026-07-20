<template>
  <div class="g9-disc" :data-testid="variant === 'listed' ? 'g9-disclosure-listed' : 'g9-disclosure-soe'">
    <div class="section-head">
      <h3 class="sheet-title">{{ disc.title.value }}</h3>
      <div class="head-actions">
        <GtIndexChip value="wp:G9-1" />
        <el-tag size="small" type="info">共 {{ disc.dataRows.value.length }} 行 + 合计</el-tag>
        <G9ImportExportDropdown
          :wp-id="wpId"
          :sheet="variant === 'listed' ? '附注上市' : '附注国企'"
          @imported="onImported"
        />
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          data-testid="g9-disclosure-pull-adj"
          @click="disc.pullFromAdjudication()"
        >↓ 从 G9-1/G9-2 分项带入</el-button>
        <el-button
          size="small"
          :loading="disc.aiLoading.value"
          :disabled="isReadonly"
          :data-testid="variant === 'listed' ? 'g9-disclosure-listed-ai' : 'g9-disclosure-soe-ai'"
          @click="disc.generateAiConclusion()"
        >🤖 AI</el-button>
        <GtReviewTrigger :section-id="variant === 'listed' ? 'G9-disclosure-listed' : 'G9-disclosure-soe'" />
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      :title="objectiveTitle"
    />

    <el-alert
      v-if="disc.adjudicatedAmount.value != null && !disc.hasAdjCrossMismatch.value"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已同步审定数（1504）：{{ fmt(disc.adjudicatedAmount.value) }}；附注{{ disc.colLabels.value.current }}合计
      {{ fmt(disc.disclosureCurrentSum.value) }} 勾稽一致。
      <el-button link size="small" @click="disc.pullLatestAdjudicated(false)">刷新</el-button>
    </el-alert>

    <el-alert
      v-if="disc.adjChangedSincePull.value"
      type="info"
      :closable="false"
      show-icon
      class="sync-hint"
      data-testid="g9-disclosure-adj-stale"
    >
      G9-1 审定数已更新为 {{ fmt(disc.adjudicatedAmount.value ?? 0) }}，披露分项尚未重新带入（不会自动覆盖手工数）。
      <el-button
        v-if="!isReadonly"
        link
        size="small"
        type="primary"
        @click="disc.pullFromAdjudication()"
      >重新分项带入</el-button>
    </el-alert>

    <el-alert
      v-if="disc.pullSummary.value"
      :type="disc.lastPullUsedResidual.value ? 'warning' : 'info'"
      :closable="true"
      class="sync-hint"
          data-testid="g9-disclosure-pull-meta"
          @close="disc.clearPullSummary()"
        >
      带入来源：{{ disc.pullSummary.value }}
    </el-alert>

    <el-alert
      v-if="disc.hasAdjCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="sync-hint"
      data-testid="g9-disclosure-adj-cross"
    >
      附注{{ disc.colLabels.value.current }}合计 {{ fmt(disc.disclosureCurrentSum.value) }} 与 G9-1 审定数
      {{ fmt(disc.adjudicatedAmount.value ?? 0) }} 差异
      {{ fmt(disc.adjCrossVariance.value ?? 0) }}。
      <el-button
        v-if="!isReadonly"
        link
        size="small"
        type="primary"
        data-testid="g9-disclosure-sync-adj"
        @click="disc.pullFromAdjudication()"
      >从 G9-1/G9-2 分项带入</el-button>
      <el-button link size="small" @click="disc.pullLatestAdjudicated(false)">刷新</el-button>
    </el-alert>

    <el-alert
      v-for="c in disc.crossChecks.value.filter((x) => x.code !== 'disclosure-sum-vs-adj')"
      :key="c.code"
      :type="c.level === 'info' ? 'info' : 'warning'"
      :closable="false"
      class="sync-hint"
      :title="c.message"
      :data-testid="`g9-disclosure-check-${c.code}`"
    />

    <el-table
      :data="disc.rows.value"
      border
      size="small"
      style="font-size:13px"
      max-height="480"
      :row-class-name="rowClass"
      data-testid="g9-disclosure-balance-table"
    >
      <el-table-column :label="disc.colLabels.value.item" prop="label" min-width="200" fixed>
        <template #default="{ row }">
          <span :class="{ 'total-label': row.isTotal }">{{ row.label }}</span>
        </template>
      </el-table-column>

      <el-table-column :label="disc.colLabels.value.current" width="130" align="right">
        <template #default="{ row }">
          <span v-if="row.isTotal" class="formula-cell">{{ fmt(row.currentAmount) }}</span>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.currentAmount"
            size="small"
            :controls="false"
            style="width:100%"
            @update:model-value="(v: number) => disc.updateField(row.rowKey, 'currentAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column :label="disc.colLabels.value.prior" width="130" align="right">
        <template #default="{ row }">
          <span v-if="row.isTotal" class="formula-cell">{{ fmt(row.priorAmount) }}</span>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorAmount"
            size="small"
            :controls="false"
            style="width:100%"
            @update:model-value="(v: number) => disc.updateField(row.rowKey, 'priorAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注文本" min-width="200">
        <template #default="{ row }">
          <div v-if="!row.isTotal" class="note-cell">
            <el-input
              v-if="!isReadonly"
              :model-value="row.noteText"
              size="small"
              type="textarea"
              :rows="1"
              @update:model-value="(v: string) => disc.updateField(row.rowKey, 'noteText', v)"
            />
            <span v-else>{{ row.noteText }}</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              link
              :loading="disc.sectionAiLoading.value[row.rowKey]"
              :data-testid="`g9-disclosure-section-ai-${row.rowKey}`"
              @click="disc.generateSectionAi(row.rowKey)"
            >🤖</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="note-card">
      <template #header>附注汇总</template>
      <el-input
        :model-value="disc.noteText.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="附注披露汇总说明…"
        @update:model-value="disc.updateNoteText"
      />
    </el-card>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>结构与 Excel 底稿一致：{{ disc.colLabels.value.item }} / {{ disc.colLabels.value.current }} / {{ disc.colLabels.value.prior }} + 合计行。</p>
        <p>建议在 G9-2 填写「工具种类」与「指定 FVTPL」，再点「分项带入」（明细优先于 G9-1 标签汇总）。</p>
        <p>无分项时审定数会写入「其他」——请按种类手工分拆；审定数变更后不会自动覆盖，需点「重新分项带入」。</p>
        <p>按 CAS 37：有 Level3 余额时应在附注汇总说明公允价值层次及调节过程。</p>
      </div>
    </details>

    <G9AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="disclosure-note"
      conclusion-ai-section="disclosure-conclusion"
      note-placeholder="填写审计说明：可概述（1）披露项完整性与列报格式合规性核对情况；（2）与审定数勾稽、拟调整事项及其影响。"
      note-hint="覆盖披露完整性、列报格式及与 G9-1 / G9-5 勾稽。"
      :related-context="{ variant }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, ref, watch } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G9AuditTextCards from '../G9AuditTextCards.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import { useG9Disclosure } from '../../composables/useG9Disclosure'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const disc = useG9Disclosure({
  variant: props.variant,
  wpId: toRef(props, 'wpId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const objectiveTitle = computed(() =>
  props.variant === 'listed'
    ? '审计目标：确认其他非流动金融资产附注（上市公司格式：种类 / 期末余额 / 上年年末余额）披露充分恰当，并与 G9-1 审定勾稽。'
    : '审计目标：确认其他非流动金融资产附注（国企格式：项目 / 期末公允价值 / 期初公允价值）披露充分恰当，并与 G9-1 审定勾稽。',
)

const NOTE_KEY = `G9-disclosure-${props.variant}-audit-note`
const CONCLUSION_KEY = `G9-disclosure-${props.variant}-audit-conclusion`
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')

watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })
})

function onImported(): void {
  emit('imported')
}

function fmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClass({ row }: { row: { isTotal?: boolean } }): string {
  return row.isTotal ? 'is-total-row' : ''
}
</script>

<style scoped>
.g9-disc { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.sync-hint { margin-bottom: 8px; }
.audit-objective { margin-bottom: 8px; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.note-cell { display: flex; align-items: flex-start; gap: 4px; }
.note-card { margin-top: 12px; }
.total-label { font-weight: 600; }
.formula-cell { font-weight: 600; font-variant-numeric: tabular-nums; }
:deep(.is-total-row) { background: var(--el-fill-color-light); }
</style>
