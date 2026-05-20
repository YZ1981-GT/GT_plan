<template>
  <el-dialog
    :model-value="visible"
    title="🏷️ 金融资产分类辅助（G-F11 CAS 22 / IFRS 9）"
    width="720px"
    :close-on-click-modal="false"
    append-to-body
    @update:model-value="emit('update:visible', $event)"
  >
    <el-alert
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #default>
        CAS 22 / IFRS 9 金融资产分类决策树。基于业务模式（持有以收取/既收取又出售/其他）
        与 SPPI 测试结果（合同现金流量仅为本金和利息）共同决定分类。
        <strong>「采纳并写回」会把分类建议写入当前底稿 parsed_data。</strong>
      </template>
    </el-alert>

    <el-form :model="form" label-width="160px" size="small">
      <el-form-item label="金融工具名称">
        <el-input
          v-model="form.instrument_name"
          placeholder="可选，用于结果展示（如 国债 / 应收款项 / 股票投资）"
          style="width: 320px"
        />
      </el-form-item>

      <el-form-item label="业务模式" required>
        <el-radio-group v-model="form.business_model">
          <el-radio value="hold_to_collect">持有以收取合同现金流量</el-radio>
          <el-radio value="hold_and_sell">既持有以收取，也以出售为目的</el-radio>
          <el-radio value="other">其他业务模式（交易性持有等）</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="SPPI 测试结果" required>
        <el-radio-group v-model="form.sppi_result">
          <el-radio value="pass">通过（合同现金流量仅为本金和利息）</el-radio>
          <el-radio value="fail">不通过（含其他对价）</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <!-- 分类预览（客户端实时决策树）-->
    <el-divider>分类决策预览（客户端实时）</el-divider>
    <el-alert
      :type="previewClassification === 'amortized_cost' ? 'success' : (previewClassification === 'fvoci' ? 'warning' : 'info')"
      :closable="false"
      show-icon
    >
      <template #title>
        <strong>{{ previewLabelZh }}</strong>
      </template>
      <template #default>
        建议代码：<code>{{ previewClassification }}</code>
      </template>
    </el-alert>

    <!-- API 计算结果 -->
    <template v-if="result">
      <el-divider>分类辅助结果（来自后端）</el-divider>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="分类建议">
          <el-tag :type="resultTagType" size="default">
            {{ result.classification_label_zh }}
          </el-tag>
          <span class="suggestion-code">（{{ result.classification_suggestion }}）</span>
        </el-descriptions-item>
        <el-descriptions-item label="推理过程">
          <pre class="reasoning-text">{{ result.reasoning }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="LLM 实现">
          <el-tag :type="result.is_llm_stub ? 'info' : 'success'" size="small">
            {{ result.is_llm_stub ? 'stub（待 wp_ai_service 接入）' : '完整推理' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!isFormValid"
        @click="onAnalyze"
      >
        🚀 分析分类
      </el-button>
      <el-button
        v-if="result"
        type="success"
        :loading="applying"
        :disabled="!targetSheet"
        @click="onApplyToSheet"
      >
        ✅ 采纳并写回
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

interface Props {
  visible: boolean
  projectId: string
  wpId: string
  /** 当前活动 sheet 名（用于「采纳并写回」按钮） */
  targetSheet?: string
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

type BusinessModel = 'hold_to_collect' | 'hold_and_sell' | 'other'
type SPPIResult = 'pass' | 'fail'
type ClassificationCode = 'amortized_cost' | 'fvoci' | 'fvtpl'

interface ClassificationCheckResponse {
  business_model: string
  sppi_result: string
  classification_suggestion: ClassificationCode
  classification_label_zh: string
  reasoning: string
  is_llm_stub: boolean
  applied_to_sheet?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<ClassificationCheckResponse | null>(null)

const form = reactive({
  instrument_name: '',
  business_model: 'hold_to_collect' as BusinessModel,
  sppi_result: 'pass' as SPPIResult,
})

// 客户端预览分类决策树（与后端 _classify 保持一致）
const previewClassification = computed<ClassificationCode>(() => {
  if (form.sppi_result === 'fail' || form.business_model === 'other') return 'fvtpl'
  if (form.business_model === 'hold_to_collect') return 'amortized_cost'
  return 'fvoci'
})

const previewLabelZh = computed(() => {
  const map: Record<ClassificationCode, string> = {
    amortized_cost: '以摊余成本计量的金融资产',
    fvoci: '以公允价值计量且其变动计入其他综合收益的金融资产（FVOCI）',
    fvtpl: '以公允价值计量且其变动计入当期损益的金融资产（FVTPL）',
  }
  return map[previewClassification.value]
})

const isFormValid = computed(() => {
  return ['hold_to_collect', 'hold_and_sell', 'other'].includes(form.business_model)
    && ['pass', 'fail'].includes(form.sppi_result)
})

const resultTagType = computed<'success' | 'warning' | 'info'>(() => {
  if (!result.value) return 'info'
  const code = result.value.classification_suggestion
  if (code === 'amortized_cost') return 'success'
  if (code === 'fvoci') return 'warning'
  return 'info'
})

function buildRequestBody(applySheet?: string): Record<string, any> {
  const body: Record<string, any> = {
    business_model: form.business_model,
    sppi_result: form.sppi_result,
  }
  if (form.instrument_name) body.instrument_name = form.instrument_name
  if (applySheet) body.apply_to_sheet = applySheet
  return body
}

async function onAnalyze() {
  loading.value = true
  try {
    const resp = await api.post<ClassificationCheckResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/g1/classification-check`,
      buildRequestBody(),
    )
    result.value = resp
    ElMessage.success(`分类辅助完成：${resp.classification_label_zh}`)
  } catch (e: any) {
    ElMessage.error(e?.message || '分类辅助失败')
  } finally {
    loading.value = false
  }
}

async function onApplyToSheet() {
  if (!props.targetSheet) {
    ElMessage.warning('未识别到当前 sheet，无法写回')
    return
  }
  applying.value = true
  try {
    const resp = await api.post<ClassificationCheckResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/g1/classification-check`,
      buildRequestBody(props.targetSheet),
    )
    result.value = resp
    if (resp?.applied_to_sheet) {
      ElMessage.success(`已采纳并写回 ${resp.applied_to_sheet}`)
      emit('applied', resp.applied_to_sheet)
    } else {
      ElMessage.warning('分析完成但未写回（applied_to_sheet 为空）')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '采纳写回失败')
  } finally {
    applying.value = false
  }
}

watch(() => props.visible, (v) => {
  if (!v) {
    result.value = null
  }
})

defineExpose({
  form,
  result,
  isFormValid,
  buildRequestBody,
  previewClassification,
  previewLabelZh,
  onAnalyze,
  onApplyToSheet,
})
</script>

<style scoped>
.suggestion-code {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
  font-size: 12px;
}
.reasoning-text {
  white-space: pre-wrap;
  font-family: var(--el-font-family);
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin: 0;
  line-height: 1.6;
}
</style>
