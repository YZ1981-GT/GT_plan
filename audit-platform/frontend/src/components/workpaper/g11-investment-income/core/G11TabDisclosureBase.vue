<template>
  <div class="g11-disclosure">
    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly" @click="dis.generateAiConclusion()">🤖 AI</el-button>
        <GtReviewTrigger :section-id="variant === 'listed' ? 'G11-disclosure-listed' : 'G11-disclosure-soe'" />
      </div>
    </div>
    <el-alert v-if="dis.adjudicatedAmount.value != null" type="success" :closable="false" class="sync-hint">
      已同步审定数（6111）：{{ fmt(dis.adjudicatedAmount.value) }}
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
      <el-table-column label="变动额" width="110" align="right">
        <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.remark" size="small"
            @update:model-value="(v: string) => dis.updateField(row.rowKey, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
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
import { useG11Disclosure } from '../../composables/useG11Disclosure'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const dis = useG11Disclosure({
  variant: props.variant,
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
})

function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.g11-disclosure { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.sync-hint { margin-bottom: 8px; }
.formula-cell { border-bottom: 1px dashed #999; }
.note-card { margin-top: 8px; }
:deep(.total-row) { font-weight: 600; background: #f5f7fa; }
</style>
