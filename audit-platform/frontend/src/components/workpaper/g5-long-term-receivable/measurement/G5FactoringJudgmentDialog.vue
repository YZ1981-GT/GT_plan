<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G5FactoringJudgmentDialog — G5-7 保理终止确认：录入基本信息 + CAS23 九步判断弹窗
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  applyConclusionToRow,
  buildJudgmentSummary,
  createJudgmentSteps,
  emptyRow,
  suggestJudgmentConclusion,
  type FactoringCheckRow,
  type FactoringConclusion,
  type FactoringMethod,
  type StepJudgment,
} from '../../composables/useG5FactoringCheck'

const props = defineProps<{
  modelValue: boolean
  row: FactoringCheckRow | null
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'save', row: FactoringCheckRow): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const activeTab = ref('basic')
const activeStep = ref(0)

const draft = reactive<FactoringCheckRow>(emptyRow())

const JUDGMENT_OPTIONS: StepJudgment[] = ['符合', '不符合', '不适用']
const CONCLUSION_OPTIONS: Exclude<FactoringConclusion, ''>[] = [
  '终止确认',
  '不终止确认（继续确认，作质押融资处理）',
  '按继续涉入程度确认',
]
const METHOD_OPTIONS: FactoringMethod[] = ['有追索', '无追索', '其他']

const suggested = computed(() => suggestJudgmentConclusion(draft.judgmentSteps))
const answeredCount = computed(() => draft.judgmentSteps.filter(s => s.judgment).length)
const progressPct = computed(() => Math.round((answeredCount.value / draft.judgmentSteps.length) * 100))
const cur = computed(() => draft.judgmentSteps[activeStep.value])

const recourseWarning = computed(() =>
  draft.method === '有追索'
  && (draft.judgmentConclusion === '终止确认' || suggested.value === '终止确认'),
)

function hydrate(src: FactoringCheckRow | null): void {
  const base = emptyRow(src ? { ...src } : undefined)
  base.judgmentSteps = createJudgmentSteps(src?.judgmentSteps)
  Object.assign(draft, base)
  // ensure nested arrays replaced
  draft.judgmentSteps = base.judgmentSteps
  activeStep.value = 0
  activeTab.value = 'basic'
}

watch(() => [props.modelValue, props.row?.id], ([open]) => {
  if (open) hydrate(props.row)
})

function judgmentTagType(j: StepJudgment): string {
  if (j === '符合') return 'success'
  if (j === '不符合') return 'danger'
  if (j === '不适用') return 'info'
  return 'info'
}

function adoptSuggested(): void {
  if (!suggested.value) return
  applyConclusionToRow(draft, suggested.value)
}

function onStepJudgmentChange(): void {
  if (!draft.judgmentConclusion && suggested.value) {
    applyConclusionToRow(draft, suggested.value)
  }
}

function prev(): void { if (activeStep.value > 0) activeStep.value-- }
function next(): void { if (activeStep.value < draft.judgmentSteps.length - 1) activeStep.value++ }

function onSave(): void {
  if (!draft.debtor?.trim()) {
    ElMessage.warning('请填写债务人/项目名称')
    activeTab.value = 'basic'
    return
  }
  if (!draft.judgmentConclusion && suggested.value) {
    applyConclusionToRow(draft, suggested.value)
  }
  if (draft.judgmentConclusion) {
    applyConclusionToRow(draft, draft.judgmentConclusion)
  }
  draft.basis = buildJudgmentSummary(draft)
  if (!draft.analysisConclusion && draft.judgmentConclusion) {
    draft.analysisConclusion = draft.judgmentConclusion
  }
  if (!draft.conclusion) draft.conclusion = draft.judgmentConclusion || draft.analysisConclusion
  emit('save', { ...draft, judgmentSteps: draft.judgmentSteps.map(s => ({ ...s })) })
  visible.value = false
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="draft.debtor ? `保理终止确认判断 · ${draft.debtor}` : '保理业务录入与终止确认判断（CAS 23 · 9 步）'"
    width="920px"
    top="4vh"
    append-to-body
    destroy-on-close
    class="g5-fc-dialog"
  >
    <el-alert
      v-if="recourseWarning"
      type="warning"
      :closable="false"
      show-icon
      class="warn-alert"
      title="有追索权保理通常保留信用风险，一般不应终止确认。请核对合同追索/回购/增信条款后再确认结论。"
    />

    <el-tabs v-model="activeTab">
      <el-tab-pane label="① 业务信息" name="basic">
        <el-form label-width="120px" size="small" class="basic-form">
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="债务人/项目" required>
                <el-input v-model="draft.debtor" :disabled="readonly" placeholder="债务人名称或项目" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="保理商/转入方">
                <el-input v-model="draft.factor" :disabled="readonly" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="账面金额">
                <WpAmountInput v-model="draft.amount" :disabled="readonly" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="追索方式">
                <el-select v-model="draft.method" :disabled="readonly" style="width:100%">
                  <el-option v-for="m in METHOD_OPTIONS" :key="m" :label="m" :value="m" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="转移方式">
                <el-input v-model="draft.transferMethod" :disabled="readonly" placeholder="保理 / ABS / 其他" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="索引号">
                <el-input v-model="draft.indexRef" :disabled="readonly" placeholder="合同/凭证索引" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-divider content-position="left">金额与继续涉入（按判断结论填写对应栏）</el-divider>
          <el-row :gutter="12">
            <el-col :span="8">
              <el-form-item label="终止确认金额">
                <WpAmountInput v-model="draft.derecognizedAmount" :disabled="readonly" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="终止确认损益">
                <el-input-number v-model="draft.gainLoss" :controls="false" :disabled="readonly" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label=" " />
            </el-col>
            <el-col :span="12">
              <el-form-item label="继续涉入资产">
                <el-input-number v-model="draft.continuingAsset" :controls="false" :disabled="readonly" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="继续涉入负债">
                <el-input-number v-model="draft.continuingLiability" :controls="false" :disabled="readonly" style="width:100%" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item label="主要合同条款">
            <el-input
              v-model="draft.contractTerms"
              type="textarea"
              :rows="3"
              :disabled="readonly"
              placeholder="关注：追索权、回购条件、优先/劣后、可变利益、逾期罚息、自留份额增信等（应用指南第38号）"
            />
          </el-form-item>
          <el-form-item label="分析结论">
            <el-input v-model="draft.analysisConclusion" type="textarea" :rows="2" :disabled="readonly" placeholder="对该笔转移是否满足终止确认条件的分析结论" />
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane name="judge">
        <template #label>
          ② 九步判断
          <el-badge v-if="answeredCount" :value="`${answeredCount}/9`" type="primary" class="tab-badge" />
        </template>

        <div class="derec-progress">
          <span>进度 {{ answeredCount }}/9</span>
          <el-progress :percentage="progressPct" :stroke-width="10" style="flex:1" />
          <el-tag v-if="suggested" type="warning" effect="light" size="small">建议：{{ suggested }}</el-tag>
        </div>

        <div class="derec-body">
          <el-steps :active="activeStep" direction="vertical" class="derec-steps">
            <el-step
              v-for="(s, i) in draft.judgmentSteps"
              :key="s.stepId"
              :title="s.title"
              :status="s.judgment ? 'finish' : (i === activeStep ? 'process' : 'wait')"
              @click="activeStep = i"
            >
              <template #description>
                <el-tag v-if="s.judgment" :type="judgmentTagType(s.judgment)" size="small">{{ s.judgment }}</el-tag>
              </template>
            </el-step>
          </el-steps>

          <div v-if="cur" class="derec-content">
            <h4 class="step-title">{{ cur.title }}</h4>
            <div class="step-note">📌 {{ cur.note }}</div>

            <div class="block">
              <div class="block-label">本步判断</div>
              <el-radio-group
                v-model="cur.judgment"
                :disabled="readonly"
                @change="onStepJudgmentChange"
              >
                <el-radio-button v-for="o in JUDGMENT_OPTIONS" :key="o" :value="o">{{ o }}</el-radio-button>
              </el-radio-group>
              <el-input
                v-model="cur.userNote"
                type="textarea"
                :rows="3"
                :disabled="readonly"
                placeholder="判断依据 / 合同条款摘录"
                style="margin-top:8px"
              />
            </div>

            <div class="step-nav">
              <el-button size="small" :disabled="activeStep === 0" @click="prev">← 上一步</el-button>
              <el-button size="small" :disabled="activeStep === draft.judgmentSteps.length - 1" @click="next">下一步 →</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <div class="footer">
        <div class="concl-row">
          <span class="concl-label">判断结论：</span>
          <el-select
            v-model="draft.judgmentConclusion"
            placeholder="选择或采用建议结论"
            :disabled="readonly"
            clearable
            style="width: 340px"
            @change="(v: FactoringConclusion) => v && applyConclusionToRow(draft, v)"
          >
            <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <el-button
            v-if="suggested && draft.judgmentConclusion !== suggested"
            size="small"
            text
            type="warning"
            :disabled="readonly"
            @click="adoptSuggested"
          >采用建议</el-button>
        </div>
        <div class="footer-actions">
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" :disabled="readonly" @click="onSave">保存并回填底稿</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.warn-alert { margin-bottom: 12px; }
.basic-form { padding-right: 8px; }
.tab-badge { margin-left: 6px; }
.derec-progress { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: 13px; }
.derec-body { display: flex; gap: 16px; max-height: 52vh; }
.derec-steps { width: 280px; flex-shrink: 0; overflow-y: auto; padding-right: 8px; }
.derec-steps :deep(.el-step__title) { font-size: 12px; line-height: 1.3; cursor: pointer; }
.derec-content { flex: 1; overflow-y: auto; padding: 0 8px 0 16px; border-left: 1px solid #ebeef5; }
.step-title { margin: 0 0 8px; font-size: 15px; color: #303133; }
.step-note {
  font-size: 13px; color: #96631b; background: #fdf6ec; border-left: 3px solid #e6a23c;
  padding: 8px 12px; border-radius: 0 4px 4px 0; margin-bottom: 14px; line-height: 1.6;
}
.block { margin-bottom: 16px; }
.block-label { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.step-nav { display: flex; justify-content: space-between; margin-top: 14px; }
.footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; width: 100%; }
.concl-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.concl-label { font-size: 13px; font-weight: 600; }
.footer-actions { display: flex; gap: 8px; }
</style>
