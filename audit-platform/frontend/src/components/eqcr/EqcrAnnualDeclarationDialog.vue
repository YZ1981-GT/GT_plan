<template>
  <el-dialog
    v-model="visible"
    title="年度独立性声明"
    width="700px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    append-to-body
  >
    <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 16px">
      <template #title>请完成 {{ currentYear }} 年度独立性声明</template>
      <div style="font-size: 12px">
        根据事务所质量管理要求，EQCR/签字合伙人/质控合伙人须每年度提交独立性声明后方可访问 EQCR 工作台。
      </div>
    </el-alert>

    <div v-loading="loadingQuestions" class="declaration-questions">
      <div v-for="(group, category) in groupedQuestions" :key="category" class="question-group">
        <h5 class="question-group__title">{{ category }}</h5>
        <div v-for="q in group" :key="q.id" class="question-item">
          <div class="question-item__text">{{ q.id }}. {{ q.question }}</div>
          <el-radio-group v-model="answers[q.id]" size="small">
            <el-radio value="no">否</el-radio>
            <el-radio value="yes">是</el-radio>
          </el-radio-group>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="declaration-footer">
        <span class="declaration-footer__progress">
          已回答 {{ answeredCount }} / {{ totalQuestions }}
        </span>
        <el-button
          type="primary"
          @click="onSubmit"
          :loading="submitting"
          :disabled="answeredCount < totalQuestions"
        >
          提交声明
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/services/apiProxy'
import { eqcr as P_eqcr } from '@/services/apiPaths'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'submitted'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const currentYear = new Date().getFullYear()
const loadingQuestions = ref(false)
const submitting = ref(false)
const questions = ref<any[]>([])
const answers = reactive<Record<number, string>>({})

const totalQuestions = computed(() => questions.value.length)
const answeredCount = computed(() => Object.keys(answers).length)

const groupedQuestions = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const q of questions.value) {
    const cat = q.category || '其他'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(q)
  }
  return groups
})

async function loadQuestions() {
  loadingQuestions.value = true
  try {
    const data = await api.get(P_eqcr.independence.questions)
    questions.value = data.questions || []
  } catch {
    ElMessage.error('加载声明问题失败')
  } finally {
    loadingQuestions.value = false
  }
}

async function onSubmit() {
  submitting.value = true
  try {
    await api.post(P_eqcr.independence.submit, {
      year: currentYear,
      answers: { ...answers },
    })
    ElMessage.success('年度独立性声明已提交')
    emit('submitted')
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

watch(visible, (v) => {
  if (v && questions.value.length === 0) {
    loadQuestions()
  }
})

onMounted(() => {
  if (visible.value) loadQuestions()
})
</script>

<style scoped>
.declaration-questions { max-height: 400px; overflow-y: auto; }
.question-group { margin-bottom: 16px; }
.question-group__title {
  font-size: 14px; font-weight: 600; margin: 0 0 8px;
  color: var(--gt-color-primary, #4b2d77);
  padding-left: 8px;
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
}
.question-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; border-radius: 4px;
  margin-bottom: 4px;
}
.question-item:hover { background: #f5f7fa; }
.question-item__text { flex: 1; font-size: 13px; margin-right: 16px; }
.declaration-footer {
  display: flex; justify-content: space-between; align-items: center; width: 100%;
}
.declaration-footer__progress { font-size: 13px; color: #909399; }
</style>
