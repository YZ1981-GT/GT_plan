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
          type="primary"
          plain
          data-testid="g9-disclosure-sync-notes"
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
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
      已同步审定数（{{ accountLabel }}）：{{ fmt(disc.adjudicatedAmount.value) }}；附注{{ disc.colLabels.value.current }}合计
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
    </el-table>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>结构与 Excel 底稿一致：{{ disc.colLabels.value.item }} / {{ disc.colLabels.value.current }} / {{ disc.colLabels.value.prior }} + 合计行。</p>
        <p>建议在 G9-2 填写「工具种类」与「指定 FVTPL」，再点「分项带入」（明细优先于 G9-1 标签汇总）。</p>
        <p>无分项时审定数会写入「其他」——请按种类手工分拆；审定数变更后不会自动覆盖，需点「重新分项带入」。</p>
        <p>有 Level3 余额时，公允价值层次及调节过程见 G9-5。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import { useG9Disclosure } from '../../composables/useG9Disclosure'
import { g9AccountLabel } from '../../composables/g9AccountMatch'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildG9SyncPayload } from '../../composables/g9DisclosureSyncPayload'
import { G9_NOTE_SECTION } from '../../composables/g9NoteSectionMap'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  applicableStandards?: string[]
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

const isSyncing = ref(false)
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || props.isReadonly || !props.projectId) return
  const payload = buildG9SyncPayload(props.wpId, props.variant, props.applicableStandards, {
    rows: disc.dataRows.value,
    noteText: disc.noteText.value,
  })
  if (!payload) return
  isSyncing.value = true
  try {
    const res: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const rows = Number((res?.data ?? res)?.rows_synced ?? 0)
    ElMessage.success(
      `已同步 ${rows} 行到附注模块「${G9_NOTE_SECTION[props.variant]} 其他非流动金融资产」`,
    )
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

// 数据变更后自动同步（防抖 800ms；只读/失败静默）。监听实际数据，不监听提示横幅状态。
watch(
  [disc.dataRows, disc.noteText],
  () => { autoSync.scheduleAutoSync(syncToDisclosureNotes) },
  { deep: true },
)

const objectiveTitle = computed(() =>
  props.variant === 'listed'
    ? '审计目标：确认其他非流动金融资产附注（上市公司格式：种类 / 期末余额 / 上年年末余额）披露充分恰当，并与 G9-1 审定勾稽。'
    : '审计目标：确认其他非流动金融资产附注（国企格式：项目 / 期末公允价值 / 期初公允价值）披露充分恰当，并与 G9-1 审定勾稽。',
)

function onImported(): void {
  emit('imported')
}

const accountLabel = computed(() => g9AccountLabel())

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
.total-label { font-weight: 600; }
.formula-cell { font-weight: 600; font-variant-numeric: tabular-nums; }
:deep(.is-total-row) { background: var(--el-fill-color-light); }
</style>
