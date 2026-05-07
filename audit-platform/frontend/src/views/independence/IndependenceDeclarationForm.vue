<template>
  <div class="independence-form">
    <div class="gt-page-banner">
      <div class="gt-banner-content">
        <h2>📋 独立性声明</h2>
        <span class="gt-banner-sub">{{ currentYear }} 年度 · 项目 {{ projectId }}</span>
      </div>
      <div class="gt-banner-actions">
        <el-button size="small" @click="saveDraft" :loading="saving" :disabled="submitted">
          保存草稿
        </el-button>
        <el-button size="small" type="primary" @click="handleSubmit" :loading="submitting" :disabled="submitted">
          提交声明
        </el-button>
      </div>
    </div>

    <!-- 已提交成功状态 -->
    <el-result v-if="submitted" icon="success" title="独立性声明已提交" sub-title="声明已签字留痕，可在归档包中查看">
      <template #extra>
        <el-button type="primary" @click="$router.back()">返回</el-button>
      </template>
    </el-result>

    <!-- 表单主体 -->
    <div v-else v-loading="loading" class="independence-form-body">
      <el-alert
        v-if="declaration && declaration.status === 'pending_conflict_review'"
        type="warning"
        :closable="false"
        style="margin-bottom: 16px"
      >
        本声明存在潜在利益冲突，已提交首席风控合伙人复核。
      </el-alert>

      <el-form ref="formRef" label-position="top" size="default">
        <div v-for="(group, gIdx) in groupedQuestions" :key="gIdx" class="question-group">
          <h3 class="group-title">{{ categoryLabel(group.category) }}</h3>

          <div v-for="q in group.questions" :key="q.id" class="question-item">
            <el-form-item :label="`${q.id}. ${q.question}`">
              <!-- yes_no 类型 -->
              <template v-if="q.answer_type === 'yes_no'">
                <el-radio-group v-model="answers[q.id]" @change="onAnswerChange(q)">
                  <el-radio value="no">否</el-radio>
                  <el-radio value="yes">是</el-radio>
                </el-radio-group>
                <!-- 详细说明（当回答 yes 时展开） -->
                <div v-if="answers[q.id] === 'yes' && q.requires_detail_if === 'yes'" class="detail-input">
                  <el-input
                    v-model="details[q.id]"
                    type="textarea"
                    :rows="3"
                    :placeholder="q.detail_prompt || '请补充说明'"
                  />
                </div>
              </template>

              <!-- text 类型 -->
              <template v-else-if="q.answer_type === 'text'">
                <el-input
                  v-model="answers[q.id]"
                  type="textarea"
                  :rows="4"
                  :placeholder="q.detail_prompt || '请填写'"
                />
              </template>

              <!-- multi_choice 类型（预留） -->
              <template v-else-if="q.answer_type === 'multi_choice'">
                <el-checkbox-group v-model="answers[q.id]">
                  <el-checkbox
                    v-for="opt in (q.options || [])"
                    :key="opt"
                    :value="opt"
                    :label="opt"
                  />
                </el-checkbox-group>
              </template>
            </el-form-item>
          </div>
        </div>

        <!-- 附件上传 -->
        <div class="question-group">
          <h3 class="group-title">附件上传</h3>
          <el-form-item label="如有相关证据文件，请上传">
            <el-upload
              v-model:file-list="fileList"
              action=""
              :auto-upload="false"
              multiple
              :limit="10"
            >
              <el-button size="small" type="primary" plain>选择文件</el-button>
              <template #tip>
                <div class="el-upload__tip">支持 PDF、Word、图片等格式，最多 10 个文件</div>
              </template>
            </el-upload>
          </el-form-item>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { confirmDangerous } from '@/utils/confirm'
import type { UploadUserFile } from 'element-plus'
import { api } from '@/services/apiProxy'
import { independenceDeclarations as P_id } from '@/services/apiPaths'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const projectId = computed(() => route.params.projectId as string)
const currentYear = new Date().getFullYear()

const loading = ref(false)
const saving = ref(false)
const submitting = ref(false)
const submitted = ref(false)

// 问题模板
interface Question {
  id: string
  category: string
  question: string
  answer_type: 'yes_no' | 'text' | 'multi_choice'
  requires_detail_if?: string
  detail_prompt?: string
  options?: string[]
}

const questions = ref<Question[]>([])
const answers = ref<Record<string, any>>({})
const details = ref<Record<string, string>>({})
const fileList = ref<UploadUserFile[]>([])
const declaration = ref<any>(null)

// 分类标签
const CATEGORY_LABELS: Record<string, string> = {
  financial_interest: '经济利益',
  employment_relationship: '雇佣关系',
  family_relationship: '家庭关系',
  non_audit_service: '非审计服务',
  fee_dependency: '收费依赖',
  long_term_relationship: '长期关系',
  gift_hospitality: '礼品招待',
  litigation: '诉讼争议',
  management_decision: '管理层决策',
  overall_assessment: '综合评估',
}

function categoryLabel(cat: string): string {
  return CATEGORY_LABELS[cat] || cat
}

// 按 category 分组
const groupedQuestions = computed(() => {
  const groups: { category: string; questions: Question[] }[] = []
  const seen = new Set<string>()
  for (const q of questions.value) {
    if (!seen.has(q.category)) {
      seen.add(q.category)
      groups.push({ category: q.category, questions: [] })
    }
    groups.find(g => g.category === q.category)!.questions.push(q)
  }
  return groups
})

function onAnswerChange(_q: Question) {
  // 可用于联动逻辑
}

// 加载问题模板 + 当前声明
async function loadData() {
  loading.value = true
  try {
    const [qRes, dRes] = await Promise.allSettled([
      api.get<{ questions: Question[] }>(P_id.questions),
      api.get<{ declarations: any[] }>(P_id.list(projectId.value), {
        params: { year: currentYear },
      }),
    ])

    if (qRes.status === 'fulfilled') {
      questions.value = qRes.value.questions || []
    }

    if (dRes.status === 'fulfilled' && dRes.value.declarations?.length) {
      // 取最新一份
      const latest = dRes.value.declarations[0]
      declaration.value = latest
      // 恢复已有答案
      if (latest.answers) {
        for (const [key, val] of Object.entries(latest.answers as Record<string, any>)) {
          if (typeof val === 'object' && val !== null && 'answer' in val) {
            answers.value[key] = val.answer
            if (val.detail) details.value[key] = val.detail
          } else {
            answers.value[key] = val
          }
        }
      }
      if (latest.status === 'submitted' || latest.status === 'approved') {
        submitted.value = true
      }
    }
  } catch {
    ElMessage.error('加载独立性声明数据失败')
  } finally {
    loading.value = false
  }
}

// 构建 answers payload
function buildAnswersPayload(): Record<string, any> {
  const payload: Record<string, any> = {}
  for (const q of questions.value) {
    const ans = answers.value[q.id]
    if (q.answer_type === 'yes_no') {
      payload[q.id] = {
        answer: ans || 'no',
        detail: ans === 'yes' ? (details.value[q.id] || '') : '',
      }
    } else {
      payload[q.id] = { answer: ans || '' }
    }
  }
  return payload
}

// 保存草稿
async function saveDraft() {
  saving.value = true
  try {
    const payload = buildAnswersPayload()
    if (declaration.value) {
      // PATCH 更新
      const { data } = await http.patch(
        P_id.detail(projectId.value, declaration.value.id),
        { answers: payload },
      )
      declaration.value = data
    } else {
      // 先创建再更新
      const created = await api.post<any>(
        P_id.list(projectId.value),
        { declarant_id: authStore.userId, declaration_year: currentYear },
      )
      declaration.value = created
      const { data } = await http.patch(
        P_id.detail(projectId.value, created.id),
        { answers: payload },
      )
      declaration.value = data
    }
    ElMessage.success('草稿已保存')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 提交声明
async function handleSubmit() {
  try {
    await confirmDangerous('提交后将触发签字留痕，确认提交独立性声明？', '确认提交')
  } catch {
    return
  }

  submitting.value = true
  try {
    // 先保存最新答案
    const payload = buildAnswersPayload()
    if (!declaration.value) {
      const created = await api.post<any>(
        P_id.list(projectId.value),
        { declarant_id: authStore.userId, declaration_year: currentYear },
      )
      declaration.value = created
    }
    await http.patch(
      P_id.detail(projectId.value, declaration.value.id),
      { answers: payload },
    )

    // 提交
    const result = await api.post<any>(
      P_id.submit(projectId.value, declaration.value.id),
    )
    declaration.value = result
    submitted.value = true
    ElMessage.success('独立性声明已提交')
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err?.message || '提交失败'
    ElMessage.error(typeof msg === 'string' ? msg : '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.independence-form { padding: 0; }
.independence-form-body { padding: 16px 0; }

.question-group {
  margin-bottom: 24px;
  padding: 16px 20px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: var(--gt-radius-md, 8px);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
}

.group-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--gt-color-text, #303133);
  margin: 0 0 16px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--gt-color-border-light, #ebeef5);
}

.question-item {
  margin-bottom: 8px;
}

.detail-input {
  margin-top: 8px;
  padding-left: 24px;
}
</style>
