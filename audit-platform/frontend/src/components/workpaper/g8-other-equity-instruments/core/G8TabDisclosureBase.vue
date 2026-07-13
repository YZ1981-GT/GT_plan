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

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按{{ variant === 'listed' ? '上市公司' : '国有企业' }}披露格式列示其他权益工具投资（科目1503）的项目、本期/上期金额及附注文本。</p>
        <p>2. 应披露以公允价值计量且变动计入 OCI 的指定情况、各投资公允价值层次（Level 1/2/3）及处置时 OCI 转留存收益的处理。</p>
        <p>3. 披露金额应与审定表 G8-1（科目1503）勾稽一致；审定数经 EventBus 自动同步。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      :title="objectiveTitle"
      class="objective-alert"
    />

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

    <el-card shadow="never" class="audit-note-card">
      <template #header>审计说明</template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：附注披露项目、金额、公允价值层次的核对情况及与审定表（科目1503）勾稽结果。" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>审计结论</template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论：附注披露是否完整、准确，是否符合企业会计准则及监管披露要求。" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, toRef } from 'vue'
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

const objectiveTitle = computed(() =>
  props.variant === 'listed'
    ? '审计目标：核实其他权益工具投资附注披露（上市公司格式）项目、金额与公允价值层次分类的完整准确，确认与审定表（科目1503）勾稽一致，披露符合企业会计准则及监管要求。'
    : '审计目标：核实其他权益工具投资附注披露（国有企业格式）项目、金额与 OCI 相关披露的完整准确，确认与审定表（科目1503）勾稽一致，披露符合企业会计准则要求。',
)

const AUDIT_NOTE_KEY = `G8-disclosure-${props.variant}-audit-note`
const AUDIT_CONCLUSION_KEY = `G8-disclosure-${props.variant}-audit-conclusion`
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(AUDIT_CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: null, remark: v })
})

function fmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g8-disc { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.sync-hint { margin-bottom: 8px; }
.guidance-details { margin-bottom: 10px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 10px; }
.audit-note-card { margin-top: 12px; }
.note-cell { display: flex; align-items: flex-start; gap: 4px; }
.note-card { margin-top: 12px; }
</style>
