<template>
  <el-dialog
    :model-value="modelValue"
    title="盘点计划问卷 F2-21"
    width="920px"
    top="4vh"
    class="f21-questionnaire-dialog"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
    @closed="onClosed"
  >
    <template #header>
      <div class="dlg-header">
        <div>
          <div class="dlg-title">盘点计划问卷 F2-21</div>
          <div class="dlg-sub">
            评价被审计单位存货盘点计划的健全性；若已有书面盘点计划，本问卷作为补充了解记录。
          </div>
        </div>
        <el-tag size="small" type="info" effect="plain">
          已填 {{ progress.filled }}/{{ progress.total }}
        </el-tag>
      </div>
    </template>

    <el-steps :active="step" finish-status="success" align-center class="dlg-steps">
      <el-step v-for="(label, idx) in F21_STEP_LABELS" :key="label" :title="label" @click="step = idx" />
    </el-steps>

    <div class="dlg-body">
      <section v-show="step === 0" class="step-panel">
        <div class="q-head">
          <h4>1. 盘点范围、地点与时间如何确定？</h4>
          <el-tooltip placement="top" :show-after="200">
            <template #content>
              <div class="hint-box">
                多地点时：索取完整存放清单；关注第三方仓库与租赁合同是否隐含额外地点；
                必要时同时盘点或突击盘点。
              </div>
            </template>
            <el-button text type="primary" size="small">编制提示</el-button>
          </el-tooltip>
        </div>
        <el-table :data="data.locations" border size="small" class="edit-table">
          <el-table-column label="地点" min-width="140">
            <template #default="{ row }">
              <el-input
                :model-value="row.location"
                size="small"
                :disabled="isReadonly"
                @update:model-value="(v: string) => updateLocation(row.id, { location: v })"
              />
            </template>
          </el-table-column>
          <el-table-column label="存货类型" min-width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.inventoryType"
                size="small"
                :disabled="isReadonly"
                @update:model-value="(v: string) => updateLocation(row.id, { inventoryType: v })"
              />
            </template>
          </el-table-column>
          <el-table-column label="占存货总额大致比例" width="140">
            <template #default="{ row }">
              <el-input
                :model-value="row.sharePct"
                size="small"
                :disabled="isReadonly"
                placeholder="%"
                @update:model-value="(v: string) => updateLocation(row.id, { sharePct: v })"
              />
            </template>
          </el-table-column>
          <el-table-column label="盘点时间" width="140">
            <template #default="{ row }">
              <el-input
                :model-value="row.countTime"
                size="small"
                :disabled="isReadonly"
                placeholder="如 2025-12-31"
                @update:model-value="(v: string) => updateLocation(row.id, { countTime: v })"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="64" align="center">
            <template #default="{ row }">
              <el-button text type="danger" size="small" @click="removeLocation(row.id)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button v-if="!isReadonly" size="small" class="add-btn" @click="addLocation">+ 增行</el-button>
      </section>

      <section v-show="step === 1" class="step-panel">
        <div class="q-head">
          <h4>2. 盘点人员如何组织？是否胜任？</h4>
        </div>
        <el-table :data="data.personnel" border size="small" class="edit-table">
          <el-table-column label="人员" min-width="100">
            <template #default="{ row }">
              <el-input
                :model-value="row.name"
                size="small"
                :disabled="isReadonly"
                @update:model-value="(v: string) => updatePersonnel(row.id, { name: v })"
              />
            </template>
          </el-table-column>
          <el-table-column label="地点" min-width="110">
            <template #default="{ row }">
              <el-input
                :model-value="row.location"
                size="small"
                :disabled="isReadonly"
                @update:model-value="(v: string) => updatePersonnel(row.id, { location: v })"
              />
            </template>
          </el-table-column>
          <el-table-column label="职责" min-width="110">
            <template #default="{ row }">
              <el-input
                :model-value="row.role"
                size="small"
                :disabled="isReadonly"
                @update:model-value="(v: string) => updatePersonnel(row.id, { role: v })"
              />
            </template>
          </el-table-column>
          <el-table-column label="胜任能力" min-width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.competence"
                size="small"
                :disabled="isReadonly"
                @update:model-value="(v: string) => updatePersonnel(row.id, { competence: v })"
              />
            </template>
          </el-table-column>
          <el-table-column label="电话" width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.phone"
                size="small"
                :disabled="isReadonly"
                @update:model-value="(v: string) => updatePersonnel(row.id, { phone: v })"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="64" align="center">
            <template #default="{ row }">
              <el-button text type="danger" size="small" @click="removePersonnel(row.id)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button v-if="!isReadonly" size="small" class="add-btn" @click="addPersonnel">+ 增行</el-button>
      </section>

      <section v-show="step === 2" class="step-panel">
        <div v-for="q in prepQuestions" :key="q.id" class="q-item">
          <div class="q-label">
            <span>{{ q.no }}. {{ q.label }}</span>
            <div class="q-actions">
              <el-tooltip v-if="q.hint" :content="q.hint" placement="top">
                <el-button text type="primary" size="small">提示</el-button>
              </el-tooltip>
              <el-button
                v-if="wpId"
                text
                type="primary"
                size="small"
                :disabled="isReadonly || !aiAvailable"
                :loading="aiLoadingId === q.id"
                @click="aiFillField(q.id, q.no, q.label)"
              >
                🤖 AI
              </el-button>
            </div>
          </div>
          <el-input
            type="textarea"
            :rows="2"
            :model-value="data.answers[q.id] || ''"
            :disabled="isReadonly"
            placeholder="根据被审计单位实际情况填写"
            @update:model-value="(v: string) => updateAnswer(q.id, v)"
          />
        </div>
      </section>

      <section v-show="step === 3" class="step-panel">
        <div v-for="q in controlQuestions" :key="q.id" class="q-item">
          <div class="q-label">
            <span>{{ q.no }}. {{ q.label }}</span>
            <div class="q-actions">
              <el-tooltip v-if="q.hint" :content="q.hint" placement="top">
                <el-button text type="primary" size="small">提示</el-button>
              </el-tooltip>
              <el-button
                v-if="wpId"
                text
                type="primary"
                size="small"
                :disabled="isReadonly || !aiAvailable"
                :loading="aiLoadingId === q.id"
                @click="aiFillField(q.id, q.no, q.label)"
              >
                🤖 AI
              </el-button>
            </div>
          </div>
          <el-input
            type="textarea"
            :rows="2"
            :model-value="data.answers[q.id] || ''"
            :disabled="isReadonly"
            placeholder="根据被审计单位实际情况填写"
            @update:model-value="(v: string) => updateAnswer(q.id, v)"
          />
        </div>
      </section>

      <section v-show="step === 4" class="step-panel">
        <div v-for="q in evaluateQuestions" :key="q.id" class="q-item">
          <div class="q-label">
            <span>{{ q.no }}. {{ q.label }}</span>
            <div class="q-actions">
              <el-tooltip v-if="q.hint" :content="q.hint" placement="top">
                <el-button text type="primary" size="small">提示</el-button>
              </el-tooltip>
              <el-button
                v-if="wpId"
                text
                type="primary"
                size="small"
                :disabled="isReadonly || !aiAvailable"
                :loading="aiLoadingId === q.id"
                @click="aiFillField(q.id, q.no, q.label)"
              >
                🤖 AI
              </el-button>
            </div>
          </div>
          <el-input
            type="textarea"
            :rows="2"
            :model-value="data.answers[q.id] || ''"
            :disabled="isReadonly"
            placeholder="根据被审计单位实际情况填写"
            @update:model-value="(v: string) => updateAnswer(q.id, v)"
          />
        </div>

        <div class="q-item eval-block">
          <h4>22. 对被审计单位存货盘点计划能否合理确定存货数量和状况作出总体评价</h4>
          <div class="q-label"><span>22.1 被审计单位存货盘点计划是否适当？</span></div>
          <el-radio-group
            :model-value="data.answers.q22_1 || ''"
            :disabled="isReadonly"
            @update:model-value="(v: string | number | boolean | undefined) => updateAnswer('q22_1', String(v ?? ''))"
          >
            <el-radio v-for="opt in F21_EVAL_Q22_1_OPTIONS" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
          <div class="q-label" style="margin-top: 12px">
            <span>22.2 盘点计划是否存在缺陷？如是，应建议被审计单位调整。</span>
            <el-button
              v-if="wpId"
              text
              type="primary"
              size="small"
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoadingId === 'q22_2'"
              @click="aiFillField('q22_2', '22.2', '盘点计划是否存在缺陷？如是，应建议被审计单位调整。')"
            >
              🤖 AI
            </el-button>
          </div>
          <el-input
            type="textarea"
            :rows="3"
            :model-value="data.answers.q22_2 || ''"
            :disabled="isReadonly"
            placeholder="如有缺陷，写明缺陷及建议调整事项；如无，可填「未见重大缺陷」。"
            @update:model-value="(v: string) => updateAnswer('q22_2', v)"
          />
        </div>
      </section>
    </div>

    <template #footer>
      <div class="dlg-footer">
        <el-button :disabled="step <= 0" @click="step -= 1">上一步</el-button>
        <el-button v-if="step < F21_STEP_LABELS.length - 1" type="primary" @click="step += 1">下一步</el-button>
        <el-button type="primary" :disabled="isReadonly" @click="handleSaveClose">保存并关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import {
  F21_STEP_LABELS,
  F21_EVAL_Q22_1_OPTIONS,
  questionsByGroup,
  isQuestionnaireFilled,
  type F21QuestionnaireData,
  type F21LocationRow,
  type F21PersonnelRow,
} from './f2StocktakeQuestionnaire'
import { useF2StocktakeAiGenerate } from '../../composables/useF2StocktakeAiGenerate'

const props = defineProps<{
  modelValue: boolean
  data: F21QuestionnaireData
  isReadonly: boolean
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  'update:answer': [id: string, val: string]
  'update:location': [id: string, patch: Partial<F21LocationRow>]
  'add:location': []
  'remove:location': [id: string]
  'update:personnel': [id: string, patch: Partial<F21PersonnelRow>]
  'add:personnel': []
  'remove:personnel': [id: string]
  save: []
}>()

const step = ref(0)
const aiLoadingId = ref('')

const { aiAvailable, generateAndConfirm } = useF2StocktakeAiGenerate({
  wpId: toRef(() => props.wpId || '') as any,
  projectId: toRef(() => props.projectId || '') as any,
})

watch(() => props.modelValue, (open) => {
  if (open) step.value = 0
})

const progress = computed(() => isQuestionnaireFilled(props.data))
const prepQuestions = questionsByGroup('prep')
const controlQuestions = questionsByGroup('control')
const evaluateQuestions = questionsByGroup('evaluate')

function buildAiContext(): Record<string, unknown> {
  const locs = props.data.locations
    .filter((r) => r.location.trim())
    .map((r) => [r.location, r.inventoryType, r.sharePct, r.countTime].filter(Boolean).join('/'))
    .join('；')
  const people = props.data.personnel
    .filter((r) => r.name.trim())
    .map((r) => [r.name, r.role, r.location].filter(Boolean).join('/'))
    .join('；')
  const filledAnswers = Object.fromEntries(
    Object.entries(props.data.answers).filter(([, v]) => String(v || '').trim()),
  )
  return {
    sheet: 'F2-21',
    locations: locs || undefined,
    personnel: people || undefined,
    filledAnswers,
  }
}

async function aiFillField(id: string, no: string, label: string) {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = id
  try {
    const text = await generateAndConfirm(
      'stocktake-questionnaire-field',
      props.data.answers[id] || '',
      {
        ...buildAiContext(),
        questionId: id,
        questionNo: no,
        questionLabel: label,
      },
      `AI 生成 · 问卷第 ${no} 题`,
    )
    if (text) emit('update:answer', id, text)
  } finally {
    aiLoadingId.value = ''
  }
}

function updateAnswer(id: string, val: string) {
  emit('update:answer', id, val)
}
function updateLocation(id: string, patch: Partial<F21LocationRow>) {
  emit('update:location', id, patch)
}
function addLocation() { emit('add:location') }
function removeLocation(id: string) { emit('remove:location', id) }
function updatePersonnel(id: string, patch: Partial<F21PersonnelRow>) {
  emit('update:personnel', id, patch)
}
function addPersonnel() { emit('add:personnel') }
function removePersonnel(id: string) { emit('remove:personnel', id) }

function handleSaveClose() {
  emit('save')
  emit('update:modelValue', false)
}

function onClosed() {
  emit('save')
}
</script>

<style scoped>
.dlg-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding-right: 28px;
}
.dlg-title { font-size: 16px; font-weight: 600; }
.dlg-sub { margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.4; }
.dlg-steps { margin: 4px 0 16px; cursor: pointer; }
.dlg-body { max-height: calc(80vh - 200px); overflow: auto; padding-right: 4px; }
.step-panel { min-height: 280px; }
.q-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.q-head h4, .eval-block h4 { margin: 0 0 8px; font-size: 13px; }
.q-item { margin-bottom: 14px; }
.q-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 13px;
  line-height: 1.45;
}
.q-actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
.edit-table { width: 100%; }
.add-btn { margin-top: 8px; }
.dlg-footer { display: flex; justify-content: flex-end; gap: 8px; width: 100%; }
.hint-box { max-width: 280px; line-height: 1.5; }
.eval-block {
  margin-top: 8px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
</style>
