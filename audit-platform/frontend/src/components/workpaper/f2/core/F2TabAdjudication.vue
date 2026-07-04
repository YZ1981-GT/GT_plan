<template>
  <div class="f2-adjudication">
    <el-alert
      v-if="detailCrossValidation"
      type="warning"
      :title="detailCrossValidation"
      :closable="false"
      show-icon
      class="cross-alert"
    />

    <div class="toolbar">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="publishAdjudicated()">
        发布审定数
      </el-button>
      <F2ReviewChip section-id="F2-1-gross" />
      <el-tag size="small" type="info">数据来源：F2-3~13 明细自动聚合至原值区</el-tag>
      <GtIndexChip value="F2-2" :context-project-id="projectId" />
    </div>

    <details class="guidance-details"><summary>📋 编制提示</summary><p>三大块结构：一原值(13类别未审/账项调整/审定) → 二跌价准备(同结构) → 三净值(=原值-跌价，只读)。底部试算差异为0方可发布。</p></details>

    <el-collapse v-model="activeBlocks">
      <el-collapse-item title="一、存货原值" name="gross">
        <F2AdjudicationBlockTable
          :rows="grossRows"
          :subtotal="grossSubtotal"
          block="gross"
          :project-id="projectId"
          :readonly="isReadonly"
          @update="updateCell"
        />
      </el-collapse-item>
      <el-collapse-item title="二、存货跌价准备" name="impairment">
        <F2AdjudicationBlockTable
          :rows="impairmentRows"
          :subtotal="impairmentSubtotal"
          block="impairment"
          :project-id="projectId"
          :readonly="isReadonly"
          @update="updateCell"
        />
      </el-collapse-item>
      <el-collapse-item title="三、存货净值（自动计算）" name="net">
        <F2AdjudicationBlockTable
          :rows="netRows"
          :subtotal="netSubtotal"
          block="gross"
          readonly
        />
      </el-collapse-item>
    </el-collapse>

    <div class="tb-diff-row">
      <span>试算平衡表数：
        <el-input-number
          :model-value="trialBalanceAmount"
          size="small"
          :controls="false"
          :disabled="isReadonly"
          @change="(v: number) => updateTrialBalanceAmount(v ?? 0)"
        />
      </span>
      <span :class="{ 'diff-red': trialBalanceDiff !== 0 }">
        差异：{{ trialBalanceDiff.toLocaleString() }}
        <template v-if="trialBalanceDiff === 0"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="note-header">
          <span class="note-title">审计说明</span>
          <div class="note-actions">
            <F2ReviewChip section-id="F2-1-note" />
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateNote">AI 生成</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :rows="2" :disabled="isReadonly" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="note-header">
          <span class="note-title">审计结论</span>
          <div class="note-actions">
            <F2ReviewChip section-id="F2-1-conclusion" />
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateConclusion">AI 生成</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :rows="2" :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, type Ref } from 'vue'
import { useF2Adjudication } from '../../composables/useF2Adjudication'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { useF2CrossSheet } from '../../composables/useF2CrossSheet'
import F2AdjudicationBlockTable from './F2AdjudicationBlockTable.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet?: ReturnType<typeof useF2CrossSheet>
}>()

const activeBlocks = ref(['gross', 'impairment'])

const {
  grossRows,
  impairmentRows,
  netRows,
  grossSubtotal,
  impairmentSubtotal,
  netSubtotal,
  trialBalanceAmount,
  trialBalanceDiff,
  detailCrossValidation,
  auditNote,
  conclusion,
  updateCell,
  updateTrialBalanceAmount,
  publishAdjudicated,
} = useF2Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  crossSheet: props.crossSheet,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateNote() {
  const text = await generateAndConfirm(
    'adj-note',
    auditNote.value,
    { netTotal: netSubtotal.value.endAudited, trialBalanceDiff: trialBalanceDiff.value },
    'AI 生成 · 存货审计说明',
  )
  if (text) auditNote.value = text
}

async function generateConclusion() {
  const text = await generateAndConfirm(
    'adj-conclusion',
    conclusion.value,
    { netTotal: netSubtotal.value.endAudited, trialBalanceDiff: trialBalanceDiff.value },
    'AI 生成 · 存货审计结论',
  )
  if (text) conclusion.value = text
}
</script>

<style scoped>
.f2-adjudication { padding: 12px; font-size: 13px; }
.cross-alert { margin-bottom: 12px; }
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
.tb-diff-row { display: flex; gap: 24px; margin: 16px 0; align-items: center; }
.diff-red { color: #f56c6c; font-weight: 600; }
.audit-note-card { margin-top: 12px; }
.note-header { display: flex; justify-content: space-between; align-items: center; }
.note-title { font-weight: 600; font-size: 13px; }
.note-actions { display: flex; gap: 8px; align-items: center; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
</style>
