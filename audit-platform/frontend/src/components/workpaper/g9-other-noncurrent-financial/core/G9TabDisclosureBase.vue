<template>

  <div class="g9-disc" :data-testid="variant === 'listed' ? 'g9-disclosure-listed' : 'g9-disclosure-soe'">

    <div class="section-head">

      <h3 class="sheet-title">{{ disc.title.value }}</h3>

      <div class="head-actions">

        <GtIndexChip value="wp:G9-1" />

        <el-tag size="small" type="info">共 {{ disc.rows.value.length }} 行</el-tag>

        <el-button size="small" :loading="disc.aiLoading.value" :disabled="isReadonly"

          :data-testid="variant === 'listed' ? 'g9-disclosure-listed-ai' : 'g9-disclosure-soe-ai'"

          @click="disc.generateAiConclusion()">🤖 AI</el-button>

        <GtReviewTrigger :section-id="variant === 'listed' ? 'G9-disclosure-listed' : 'G9-disclosure-soe'" />

      </div>

    </div>



    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：确认其他非流动金融资产的分类、公允价值层次、减值及风险敞口在财务报表附注中充分、恰当披露。"
    />

    <el-alert v-if="disc.adjudicatedAmount.value != null" type="success" :closable="false" class="sync-hint">

      已同步审定数（1504）：{{ fmt(disc.adjudicatedAmount.value) }}

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

        <template #header>

          <span>附注文本</span>

        </template>

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

              :data-testid="`g9-disclosure-section-ai-${row.rowKey}`"

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

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>按 CAS 37 金融工具列报：披露金融资产的分类、账面价值、公允价值层次、以及信用风险、市场风险敞口。</p>
        <p>本期数应与 G9-1 审定表（1504）勾稽一致，可点击「刷新」同步最新审定数。</p>
      </div>
    </details>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述（1）披露项完整性与列报格式合规性核对情况；（2）与审定数勾稽、拟调整事项及其影响。"
        @change="(val: string) => saveAuditNote(val)" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。"
        @change="(val: string) => saveAuditConclusion(val)" />
    </el-card>

  </div>

</template>



<script setup lang="ts">

import { computed, toRef, ref, onMounted } from 'vue'

import GtReviewTrigger from '../../GtReviewTrigger.vue'

import GtIndexChip from '../../GtIndexChip.vue'

import { useG9Disclosure } from '../../composables/useG9Disclosure'

import type { ChecklistResponse } from '../../composables/useF1FormData'



const props = defineProps<{

  variant: 'listed' | 'soe'

  allResponses: Map<string, ChecklistResponse>

  wpId: string

  isReadonly: boolean

  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void

}>()



const disc = useG9Disclosure({

  variant: props.variant,

  wpId: toRef(props, 'wpId'),

  allResponses: computed(() => props.allResponses),

  debouncedSave: props.debouncedSave,

  isReadonly: computed(() => props.isReadonly),

})



// ─── 审计说明 / 审计结论（按 variant 区分持久化，防串写）───────────────────
const NOTE_KEY = `G9-disclosure-${props.variant}-audit-note`
const CONCLUSION_KEY = `G9-disclosure-${props.variant}-audit-conclusion`
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) auditConclusion.value = c.remark
})



function fmt(n: number): string {

  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

}

</script>



<style scoped>

.g9-disc { font-size: var(--wp-font-size, 13px); }

.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }

.sheet-title { margin: 0; font-size: 15px; }

.head-actions { display: flex; gap: 8px; align-items: center; }

.sync-hint { margin-bottom: 8px; }

.audit-objective { margin-bottom: 8px; }

.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }

.guidance-content p { margin: 4px 0; }

.note-cell { display: flex; align-items: flex-start; gap: 4px; }

.note-card { margin-top: 12px; }

.audit-note-card { margin-top: 16px; }

.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }

</style>


