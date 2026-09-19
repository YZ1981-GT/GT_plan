<template>
  <div class="f2-questionnaire-wrapper">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本问卷评价被审计单位盘点计划的健全性，覆盖盘点组织、程序、截止控制与差异处理（CAS 1311）。</p>
        <p>2. 点击「填写盘点计划问卷」按 Excel 1~22 题结构填报；叙述题旁可使用 AI 辅助起草。</p>
        <p>3. 第 22 题总体评价驱动后续监盘计划（F2-22）与程序裁剪（F2-21A）。</p>
        <p>4. 检测到旧版 OO 地点表或扁平字段时，打开问卷将自动迁移为结构化数据。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价被审计单位存货盘点计划的健全性，确认盘点组织、程序、截止控制与差异处理足以保证盘点结果的准确与完整。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="hint">盘点计划问卷 F2-21</span>
        <el-tag size="small" :type="progress.filled === progress.total ? 'success' : 'warning'" effect="plain">
          问卷进度 {{ progress.filled }}/{{ progress.total }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F2-21" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F2-21A" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F2-22" :context-project-id="projectId" /></span>
        <el-button type="primary" size="small" @click="dialogOpen = true">
          {{ isReadonly ? '查看问卷' : '填写盘点计划问卷' }}
        </el-button>
      </div>
    </div>

    <F2StocktakeSheetAttachments
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F2-21"
    />

    <el-card shadow="never" class="summary-card">
      <template #header>
        <div class="card-header">
          <span>问卷摘要</span>
          <el-button text type="primary" size="small" @click="dialogOpen = true">打开问卷</el-button>
        </div>
      </template>
      <div class="summary-grid">
        <div class="summary-item">
          <div class="label">盘点地点（Q1）</div>
          <div class="value">{{ locationSummary }}</div>
        </div>
        <div class="summary-item">
          <div class="label">盘点人员（Q2）</div>
          <div class="value">{{ personnelSummary }}</div>
        </div>
        <div class="summary-item">
          <div class="label">计划是否适当（Q22.1）</div>
          <div class="value">
            <el-tag v-if="q22Label" size="small" :type="q22TagType" effect="plain">{{ q22Label }}</el-tag>
            <span v-else class="muted">未评价</span>
          </div>
        </div>
        <div class="summary-item full">
          <div class="label">缺陷与建议（Q22.2）</div>
          <div class="value pre">{{ data.answers.q22_2 || '—' }}</div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>问卷结论</span>
          <el-button
            v-if="wpId"
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="aiFillConclusion"
          >
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="概括对本问卷的总体结论，可索引至 F2-21A / F2-22。"
      />
    </el-card>

    <F2StocktakeQuestionnaireDialog
      v-model="dialogOpen"
      :data="data"
      :is-readonly="isReadonly"
      :wp-id="wpId"
      :project-id="projectId"
      @update:answer="updateAnswer"
      @update:location="updateLocation"
      @add:location="addLocation"
      @remove:location="removeLocation"
      @update:personnel="updatePersonnel"
      @add:personnel="addPersonnel"
      @remove:personnel="removePersonnel"
      @save="saveNow"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, shallowRef, watch } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import F2StocktakeQuestionnaireDialog from './F2StocktakeQuestionnaireDialog.vue'
import F2StocktakeSheetAttachments from './F2StocktakeSheetAttachments.vue'
import { useF2StocktakeQuestionnaire } from '../../composables/useF2StocktakeQuestionnaire'
import { useF2StocktakeAiGenerate } from '../../composables/useF2StocktakeAiGenerate'
import { F21_EVAL_Q22_1_OPTIONS } from './f2StocktakeQuestionnaire'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const dialogOpen = ref(false)
const responsesMap = shallowRef(props.allResponses)
watch(() => props.allResponses, (v) => { responsesMap.value = v })

const {
  data,
  auditNote,
  saveNow,
  updateAnswer,
  updateLocation,
  addLocation,
  removeLocation,
  updatePersonnel,
  addPersonnel,
  removePersonnel,
  progress: progressFn,
} = useF2StocktakeQuestionnaire({
  allResponses: responsesMap,
  isReadonly: toRef(props, 'isReadonly'),
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2StocktakeAiGenerate({
  wpId: toRef(() => props.wpId || '') as any,
  projectId: toRef(() => props.projectId || '') as any,
})

const progress = computed(() => progressFn())

const locationSummary = computed(() => {
  const rows = data.value.locations.filter((r) => r.location.trim() || r.inventoryType.trim())
  if (!rows.length) return '未填写'
  return rows.map((r) => {
    const parts = [r.location, r.inventoryType, r.sharePct ? `${r.sharePct}%` : '', r.countTime].filter(Boolean)
    return parts.join(' · ')
  }).join('；')
})

const personnelSummary = computed(() => {
  const rows = data.value.personnel.filter((r) => r.name.trim())
  if (!rows.length) return '未填写'
  return rows.map((r) => [r.name, r.role, r.location].filter(Boolean).join('/')).join('；')
})

const q22Label = computed(() => {
  const v = data.value.answers.q22_1
  return F21_EVAL_Q22_1_OPTIONS.find((o) => o.value === v)?.label || ''
})

const q22TagType = computed(() => {
  const v = data.value.answers.q22_1
  if (v === 'yes') return 'success'
  if (v === 'partial') return 'warning'
  if (v === 'no') return 'danger'
  return 'info'
})

async function aiFillConclusion() {
  if (props.isReadonly || !props.wpId) return
  const text = await generateAndConfirm(
    'stocktake-questionnaire',
    auditNote.value || '',
    {
      sheet: 'F2-21',
      locations: locationSummary.value === '未填写' ? undefined : locationSummary.value,
      personnel: personnelSummary.value === '未填写' ? undefined : personnelSummary.value,
      q22_1: q22Label.value || undefined,
      q22_2: data.value.answers.q22_2 || undefined,
      filledAnswers: Object.fromEntries(
        Object.entries(data.value.answers).filter(([, v]) => String(v || '').trim()),
      ),
    },
    'AI 生成 · 盘点问卷结论',
  )
  if (text) auditNote.value = text
}
</script>

<style scoped>
.f2-questionnaire-wrapper { font-size: var(--wp-font-size, 13px); padding: 12px; }
.objective-alert { margin-bottom: 12px; }
.guidance-details { margin-bottom: 12px; font-size: 12px; }
.guidance-content { padding: 8px 0; color: var(--el-text-color-secondary); line-height: 1.6; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.hint { font-weight: 600; }
.chip-wrap { display: inline-flex; }
.summary-card, .audit-note-card { margin-bottom: 12px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.summary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}
.summary-item.full { grid-column: 1 / -1; }
.summary-item .label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.summary-item .value { font-size: 13px; line-height: 1.45; }
.summary-item .value.pre { white-space: pre-wrap; }
.muted { color: var(--el-text-color-placeholder); }

@media (max-width: 900px) {
  .summary-grid { grid-template-columns: 1fr; }
}
</style>
