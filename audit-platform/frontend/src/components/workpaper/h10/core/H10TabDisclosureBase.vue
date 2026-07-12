<template>
  <div class="h10-disclosure" :data-testid="variant === 'listed' ? 'h10-disclosure-listed' : 'h10-disclosure-soe'">
    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly" data-testid="h10-disclosure-ai-btn" @click="dis.generateAiConclusion()">🤖 AI</el-button>
        <GtReviewTrigger :section-id="variant === 'listed' ? 'H10-disclosure-listed' : 'H10-disclosure-soe'" />
      </div>
    </div>
    <el-alert v-if="dis.adjudicatedAmount.value != null" type="success" :closable="false" class="sync-hint">
      已同步审定数（6115 发生额）：{{ fmt(dis.adjudicatedAmount.value) }}
      <el-button link size="small" @click="dis.pullLatestAdjudicated()">刷新</el-button>
    </el-alert>
    <el-table :data="dis.displayRows.value" border size="small" style="font-size:13px" max-height="480"
      :row-class-name="({ row }) => row.rowKey === 'total' ? 'total-row' : ''">
      <el-table-column label="项目" prop="label" min-width="220" fixed />
      <el-table-column label="本期发生额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'currentAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期发生额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'priorAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="variant === 'soe'" label="非经常性" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.nonRecurringAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'nonRecurringAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.nonRecurringAmount ?? 0) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="110" align="right">
        <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
    </el-table>
    <el-card shadow="never" class="note-card">
      <template #header>附注文本</template>
      <el-input :model-value="dis.noteText.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="dis.updateNoteText" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useH10Disclosure } from '../../composables/useH10Disclosure'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const dis = useH10Disclosure({
  variant: props.variant,
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
})

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h10-disclosure { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; }
.sync-hint { margin-bottom: 8px; }
.formula-cell { border-bottom: 1px dashed #999; }
.note-card { margin-top: 8px; }
:deep(.total-row) { font-weight: 600; background: #f5f7fa; }
</style>
