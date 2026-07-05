<template>
  <div class="g8-disc" :data-testid="variant === 'listed' ? 'g8-disclosure-listed' : 'g8-disclosure-soe'">
    <div class="section-head">
      <h3 class="sheet-title">{{ disc.title.value }}</h3>
      <div class="head-actions">
        <el-button size="small" :loading="disc.aiLoading.value" :disabled="isReadonly"
          :data-testid="variant === 'listed' ? 'g8-disclosure-listed-ai' : 'g8-disclosure-soe-ai'"
          @click="disc.generateAiConclusion()">🤖 AI</el-button>
        <GtReviewTrigger :section-id="variant === 'listed' ? 'G8-disclosure-listed' : 'G8-disclosure-soe'" />
      </div>
    </div>

    <el-alert v-if="disc.adjudicatedAmount.value != null" type="success" :closable="false" class="sync-hint">
      已同步审定数（1503）：{{ fmt(disc.adjudicatedAmount.value) }}
      <el-button link size="small" @click="disc.pullLatestAdjudicated()">刷新</el-button>
    </el-alert>

    <el-table :data="disc.rows.value" border size="small" style="font-size:13px" max-height="480">
      <el-table-column label="项目" prop="label" min-width="180" fixed />
      <el-table-column label="本期" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.currentAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => disc.updateField(row.rowKey, 'currentAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.priorAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => disc.updateField(row.rowKey, 'priorAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注文本" min-width="200">
        <template #default="{ row }">
          <div class="note-cell">
            <el-input v-if="!isReadonly" :model-value="row.noteText" size="small" type="textarea" :rows="1"
              @update:model-value="(v: string) => disc.updateField(row.rowKey, 'noteText', v)" />
            <span v-else>{{ row.noteText }}</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              link
              :loading="disc.sectionAiLoading.value[row.rowKey]"
              :data-testid="`g8-disclosure-section-ai-${row.rowKey}`"
              @click="disc.generateSectionAi(row.rowKey)"
            >🤖</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="note-card">
      <template #header>附注汇总</template>
      <el-input :model-value="disc.noteText.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" placeholder="附注披露汇总说明…"
        @update:model-value="disc.updateNoteText" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useG8Disclosure } from '../../composables/useG8Disclosure'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const disc = useG8Disclosure({
  variant: props.variant,
  wpId: toRef(props, 'wpId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

function fmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g8-disc { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.sync-hint { margin-bottom: 8px; }
.note-cell { display: flex; align-items: flex-start; gap: 4px; }
.note-card { margin-top: 12px; }
</style>
