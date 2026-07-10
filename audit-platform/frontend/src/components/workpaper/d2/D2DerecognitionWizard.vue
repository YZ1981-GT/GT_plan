<script setup lang="ts">
/**
 * D2DerecognitionWizard — 保理终止确认判断向导（D2-12）
 *
 * 9 步终止确认判断闭环：附件上传+OCR → 知识库引用 → AI 辅助判断 → 用户确认 → 回填底稿。
 */
import { ref, toRef, computed, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD2Derecognition, type KnowledgeRef, type StepJudgment } from '../composables/useD2Derecognition'

const props = defineProps<{
  modelValue: boolean
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /** 当前判断的保理合同 ID（rowId） */
  contractId: string
  /** 保理合同标签（债务人/保理商，用于标题与摘要） */
  contractLabel?: string
  /** 保理上下文（笔数/金额等，供 AI 参考） */
  factoringContext?: Record<string, unknown>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'applied', payload: { contractId: string; conclusion: string; summary: string }): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const {
  steps, conclusion, overallNote, activeStep, loading,
  suggestedConclusion, answeredCount, progressPct,
  load, uploadOcr, searchKnowledge, addKnowledgeRef, removeKnowledgeRef,
  aiJudge, adoptAi, save, buildSummaryText,
} = useD2Derecognition({
  wpId: toRef(props, 'wpId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  contractId: toRef(props, 'contractId') as Ref<string>,
})

// 打开或切换合同时重新加载对应判断
watch(() => [props.modelValue, props.contractId], ([v]) => { if (v) load() }, { immediate: true })

const cur = computed(() => steps.value[activeStep.value])

const JUDGMENT_OPTIONS: StepJudgment[] = ['符合', '不符合', '不适用']
const CONCLUSION_OPTIONS = [
  '终止确认',
  '不终止确认（继续确认，作质押融资处理）',
  '按继续涉入程度确认',
]

function judgmentTagType(j: StepJudgment): string {
  if (j === '符合') return 'success'
  if (j === '不符合') return 'danger'
  if (j === '不适用') return 'info'
  return 'info'
}

async function onUpload(file: File): Promise<boolean> {
  await uploadOcr(activeStep.value, file)
  return false
}

async function onAiJudge(): Promise<void> {
  await aiJudge(activeStep.value, props.factoringContext || {})
}

// ─── 知识库检索（el-autocomplete） ─────────────────────────────────────────
async function queryKnowledge(q: string, cb: (items: any[]) => void): Promise<void> {
  const results = await searchKnowledge(q)
  cb(results.map(r => ({ value: r.name, ref: r })))
}
function onKnowledgeSelect(item: any): void {
  if (item?.ref) addKnowledgeRef(activeStep.value, item.ref as KnowledgeRef)
  knowledgeInput.value = ''
}
const knowledgeInput = ref('')

function prev(): void { if (activeStep.value > 0) activeStep.value-- }
function next(): void { if (activeStep.value < steps.value.length - 1) activeStep.value++ }

function onSaveApply(): void {
  if (!conclusion.value) conclusion.value = suggestedConclusion.value
  if (!conclusion.value) {
    ElMessage.warning('请先完成关键步骤判断并确定结论')
    return
  }
  save()
  emit('applied', { contractId: props.contractId, conclusion: conclusion.value, summary: buildSummaryText(props.contractLabel) })
  visible.value = false
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="contractLabel ? `保理终止确认判断向导 · ${contractLabel}（CAS 23 · 9 步）` : '保理终止确认判断向导（CAS 23 · 9 步）'"
    width="960px"
    top="5vh"
    append-to-body
    class="d2-derec-dialog"
  >
    <div class="derec-progress">
      <span>判断进度 {{ answeredCount }}/{{ steps.length }}</span>
      <el-progress :percentage="progressPct" :stroke-width="10" style="flex:1" />
      <el-tag v-if="suggestedConclusion" type="warning" effect="light">AI 建议结论：{{ suggestedConclusion }}</el-tag>
    </div>

    <div class="derec-body">
      <!-- 左侧步骤导航 -->
      <el-steps :active="activeStep" direction="vertical" class="derec-steps">
        <el-step
          v-for="(s, i) in steps"
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

      <!-- 右侧当前步内容 -->
      <div v-if="cur" class="derec-content" v-loading="loading">
        <h4 class="step-title">{{ cur.title }}</h4>
        <div class="step-note">📌 判断要点：{{ cur.note }}</div>

        <!-- 证据：附件 OCR + 文本 -->
        <div class="block">
          <div class="block-label">
            证据（合同/协议）
            <el-upload :show-file-list="false" accept=".pdf,.png,.jpg,.jpeg" :before-upload="onUpload" style="display:inline-block">
              <el-button size="small" :disabled="isReadonly">📎 上传附件并 OCR</el-button>
            </el-upload>
            <span v-if="cur.attachmentName" class="att-name">已上传：{{ cur.attachmentName }}</span>
          </div>
          <el-input
            v-model="cur.evidenceText"
            type="textarea"
            :rows="3"
            :disabled="isReadonly"
            placeholder="OCR 识别的合同条款文本，或手动粘贴关键条款（用于 AI 判断与留痕）"
          />
        </div>

        <!-- 知识库引用 -->
        <div class="block">
          <div class="block-label">引用知识库（准则/案例/内部指引）</div>
          <el-autocomplete
            v-model="knowledgeInput"
            :fetch-suggestions="queryKnowledge"
            placeholder="搜索知识库文档名/内容…"
            :disabled="isReadonly"
            style="width: 100%"
            @select="onKnowledgeSelect"
          />
          <div v-if="cur.knowledgeRefs.length" class="ref-tags">
            <el-tag
              v-for="r in cur.knowledgeRefs"
              :key="r.id"
              closable
              size="small"
              type="info"
              @close="removeKnowledgeRef(activeStep, r.id)"
            >📚 {{ r.name }}</el-tag>
          </div>
        </div>

        <!-- AI 辅助判断 -->
        <div class="block ai-block">
          <div class="block-label">
            AI 辅助判断
            <el-button size="small" type="primary" plain :loading="loading" :disabled="isReadonly" @click="onAiJudge">🤖 AI 判断本步</el-button>
          </div>
          <div v-if="cur.aiSuggestion" class="ai-result">
            <el-tag :type="judgmentTagType(cur.aiSuggestion)" size="small">AI 建议：{{ cur.aiSuggestion }}</el-tag>
            <span class="ai-reason">{{ cur.aiReasoning }}</span>
            <el-button size="small" text type="success" :disabled="isReadonly" @click="adoptAi(activeStep)">采纳为我的判断 ↓</el-button>
          </div>
          <div v-else class="ai-hint">结合上方证据与知识库引用，点击「AI 判断本步」获取专业建议（仅供参考，人工确认为准）。</div>
        </div>

        <!-- 用户判断 -->
        <div class="block user-block">
          <div class="block-label">我的判断（人工确认，以此为准）</div>
          <el-radio-group v-model="cur.judgment" :disabled="isReadonly">
            <el-radio-button v-for="o in JUDGMENT_OPTIONS" :key="o" :value="o">{{ o }}</el-radio-button>
          </el-radio-group>
          <el-input
            v-model="cur.userNote"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="判断依据/说明"
            style="margin-top:8px"
          />
        </div>

        <div class="step-nav">
          <el-button size="small" :disabled="activeStep === 0" @click="prev">← 上一步</el-button>
          <el-button size="small" :disabled="activeStep === steps.length - 1" @click="next">下一步 →</el-button>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="derec-footer">
        <div class="concl-row">
          <span class="concl-label">终止确认结论：</span>
          <el-select v-model="conclusion" placeholder="选择结论（默认采用 AI 建议）" :disabled="isReadonly" style="width: 360px">
            <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <el-button v-if="suggestedConclusion && !conclusion" size="small" text type="warning" @click="conclusion = suggestedConclusion">采用建议：{{ suggestedConclusion }}</el-button>
        </div>
        <div class="footer-actions">
          <el-button @click="visible = false">关闭</el-button>
          <el-button type="primary" :disabled="isReadonly" @click="onSaveApply">✅ 保存并回填底稿</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.derec-progress { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: 13px; }
.derec-body { display: flex; gap: 16px; max-height: 62vh; }
.derec-steps { width: 300px; flex-shrink: 0; overflow-y: auto; padding-right: 8px; }
.derec-steps :deep(.el-step__title) { font-size: 13px; line-height: 1.3; cursor: pointer; }
.derec-content { flex: 1; overflow-y: auto; padding: 0 8px 0 16px; border-left: 1px solid #ebeef5; }
.step-title { margin: 0 0 8px; font-size: 15px; color: #303133; }
.step-note {
  font-size: 13px; color: #96631b; background: #fdf6ec; border-left: 3px solid #e6a23c;
  padding: 8px 12px; border-radius: 0 4px 4px 0; margin-bottom: 14px; line-height: 1.6;
}
.block { margin-bottom: 16px; }
.block-label { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 6px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.att-name { font-size: 12px; color: #67c23a; font-weight: 400; }
.ref-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.ai-block { background: #f5f7fa; border-radius: 6px; padding: 10px 12px; }
.ai-result { display: flex; align-items: flex-start; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.ai-reason { flex: 1; min-width: 200px; color: #606266; line-height: 1.6; }
.ai-hint { font-size: 12px; color: #909399; }
.user-block { border-top: 1px dashed #dcdfe6; padding-top: 12px; }
.step-nav { display: flex; justify-content: space-between; margin-top: 14px; }
.derec-footer { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.concl-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.concl-label { font-size: 13px; font-weight: 600; }
.footer-actions { display: flex; gap: 8px; }
</style>
