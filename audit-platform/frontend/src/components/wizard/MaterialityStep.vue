<template>
  <div class="materiality-step">
    <h2 class="step-title">重要性水平</h2>
    <p class="step-desc">选择基准类型、设置参数，系统自动计算三级重要性水平</p>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="140px"
      label-position="right"
      class="materiality-form"
    >
      <!-- 基准类型 -->
      <el-form-item label="基准类型" prop="benchmark_type">
        <el-select
          v-model="form.benchmark_type"
          placeholder="请选择基准类型"
          style="width: 100%"
          @change="onBenchmarkTypeChange"
        >
          <el-option label="利润总额" value="pre_tax_profit" />
          <el-option label="营业收入" value="revenue" />
          <el-option label="总资产" value="total_assets" />
          <el-option label="净资产" value="net_assets" />
          <el-option label="自定义" value="custom" />
        </el-select>
      </el-form-item>

      <!-- 基准金额 -->
      <el-form-item label="基准金额" prop="benchmark_amount">
        <div style="display: flex; gap: 8px; width: 100%">
          <el-input-number
            v-model="benchmarkNum"
            :precision="2"
            :controls="false"
            placeholder="基准金额"
            style="flex: 1"
            @change="onParamChange"
          />
          <el-button
            v-if="form.benchmark_type !== 'custom'"
            type="primary"
            plain
            :loading="autoLoading"
            @click="autoPopulate"
          >
            从试算表取数
          </el-button>
        </div>
      </el-form-item>

      <!-- 整体重要性百分比 -->
      <el-form-item label="整体百分比(%)" prop="overall_percentage">
        <el-input-number
          v-model="overallPctNum"
          :min="0"
          :max="100"
          :precision="2"
          :step="0.5"
          style="width: 100%"
          @change="onParamChange"
        />
      </el-form-item>

      <!-- 执行比例 -->
      <el-form-item label="执行比例(%)" prop="performance_ratio">
        <el-slider
          v-model="perfRatioNum"
          :min="0"
          :max="100"
          :step="5"
          show-input
          @change="onParamChange"
        />
      </el-form-item>

      <!-- 微小比例 -->
      <el-form-item label="微小比例(%)" prop="trivial_ratio">
        <el-input-number
          v-model="trivialRatioNum"
          :min="0"
          :max="100"
          :precision="2"
          :step="1"
          style="width: 100%"
          @change="onParamChange"
        />
      </el-form-item>
    </el-form>

    <!-- 计算结果 -->
    <div v-if="result" class="result-panel">
      <h3 class="result-title">计算结果</h3>
      <div class="result-grid">
        <div class="result-card">
          <span class="result-label">整体重要性</span>
          <span class="result-value primary">{{ formatAmount(result.overall_materiality) }}</span>
        </div>
        <div class="result-card">
          <span class="result-label">实际执行重要性</span>
          <span class="result-value">{{ formatAmount(result.performance_materiality) }}</span>
        </div>
        <div class="result-card">
          <span class="result-label">明显微小错报</span>
          <span class="result-value">{{ formatAmount(result.trivial_threshold) }}</span>
        </div>
      </div>

      <!-- 手动覆盖 -->
      <el-collapse class="override-section">
        <el-collapse-item title="手动覆盖（可选）" name="override">
          <el-form label-width="140px">
            <el-form-item label="整体重要性">
              <el-input-number
                v-model="overrideForm.overall_materiality"
                :precision="2"
                :controls="false"
                placeholder="留空则使用计算值"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="执行重要性">
              <el-input-number
                v-model="overrideForm.performance_materiality"
                :precision="2"
                :controls="false"
                placeholder="留空则使用计算值"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="微小错报">
              <el-input-number
                v-model="overrideForm.trivial_threshold"
                :precision="2"
                :controls="false"
                placeholder="留空则使用计算值"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="覆盖原因" required>
              <el-input
                v-model="overrideForm.reason"
                type="textarea"
                :rows="2"
                placeholder="请说明覆盖原因"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="warning"
                :disabled="!overrideForm.reason"
                :loading="overrideLoading"
                @click="submitOverride"
              >
                确认覆盖
              </el-button>
            </el-form-item>
          </el-form>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useWizardStore } from '@/stores/wizard'
import http from '@/utils/http'

const wizardStore = useWizardStore()
const formRef = ref<FormInstance>()
const autoLoading = ref(false)
const overrideLoading = ref(false)

// Numeric refs for el-input-number (which doesn't bind strings well)
const benchmarkNum = ref<number | undefined>(undefined)
const overallPctNum = ref(5)
const perfRatioNum = ref(50)
const trivialRatioNum = ref(5)

const form = reactive({
  benchmark_type: '',
  benchmark_amount: '',
  overall_percentage: '5',
  performance_ratio: '50',
  trivial_ratio: '5',
})

const rules: FormRules = {
  benchmark_type: [{ required: true, message: '请选择基准类型', trigger: 'change' }],
  benchmark_amount: [{ required: true, message: '请输入基准金额', trigger: 'blur' }],
  overall_percentage: [{ required: true, message: '请输入百分比', trigger: 'blur' }],
}

const result = ref<Record<string, any> | null>(null)

const overrideForm = reactive({
  overall_materiality: undefined as number | undefined,
  performance_materiality: undefined as number | undefined,
  trivial_threshold: undefined as number | undefined,
  reason: '',
})

function formatAmount(val: any): string {
  const n = Number(val)
  if (isNaN(n)) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getYear(): number {
  const basic = wizardStore.stepData.basic_info as any
  return basic?.audit_year ?? new Date().getFullYear()
}

async function onBenchmarkTypeChange() {
  if (form.benchmark_type && form.benchmark_type !== 'custom') {
    await autoPopulate()
  }
}

async function autoPopulate() {
  if (!wizardStore.projectId || !form.benchmark_type) return
  autoLoading.value = true
  try {
    const year = getYear()
    const { data } = await http.get(
      `/api/projects/${wizardStore.projectId}/materiality/benchmark`,
      { params: { year, benchmark_type: form.benchmark_type } }
    )
    const resp = data.data ?? data
    const amount = Number(resp.benchmark_amount)
    benchmarkNum.value = amount
    form.benchmark_amount = String(amount)
    onParamChange()
  } catch {
    // error handled by interceptor
  } finally {
    autoLoading.value = false
  }
}

async function onParamChange() {
  // Sync numeric refs to form strings
  form.benchmark_amount = benchmarkNum.value != null ? String(benchmarkNum.value) : ''
  form.overall_percentage = String(overallPctNum.value)
  form.performance_ratio = String(perfRatioNum.value)
  form.trivial_ratio = String(trivialRatioNum.value)

  // Auto-calculate if all params present
  if (!wizardStore.projectId || !form.benchmark_type || !form.benchmark_amount) return
  if (!overallPctNum.value) return

  try {
    const year = getYear()
    const { data } = await http.post(
      `/api/projects/${wizardStore.projectId}/materiality/calculate`,
      {
        benchmark_type: form.benchmark_type,
        benchmark_amount: form.benchmark_amount,
        overall_percentage: form.overall_percentage,
        performance_ratio: form.performance_ratio,
        trivial_ratio: form.trivial_ratio,
      },
      { params: { year } }
    )
    result.value = data.data ?? data
  } catch {
    // silent
  }
}

async function submitOverride() {
  if (!wizardStore.projectId || !overrideForm.reason) return
  overrideLoading.value = true
  try {
    const year = getYear()
    const body: Record<string, any> = { override_reason: overrideForm.reason }
    if (overrideForm.overall_materiality != null) body.overall_materiality = String(overrideForm.overall_materiality)
    if (overrideForm.performance_materiality != null) body.performance_materiality = String(overrideForm.performance_materiality)
    if (overrideForm.trivial_threshold != null) body.trivial_threshold = String(overrideForm.trivial_threshold)

    const { data } = await http.put(
      `/api/projects/${wizardStore.projectId}/materiality/override`,
      body,
      { params: { year } }
    )
    result.value = data.data ?? data
    ElMessage.success('覆盖成功')
  } catch {
    // error handled by interceptor
  } finally {
    overrideLoading.value = false
  }
}

/** Restore from store */
onMounted(async () => {
  const saved = wizardStore.stepData.materiality as any
  if (saved) {
    form.benchmark_type = saved.benchmark_type || ''
    form.benchmark_amount = saved.benchmark_amount || ''
    form.overall_percentage = saved.overall_percentage || '5'
    form.performance_ratio = saved.performance_ratio || '50'
    form.trivial_ratio = saved.trivial_ratio || '5'
    benchmarkNum.value = form.benchmark_amount ? Number(form.benchmark_amount) : undefined
    overallPctNum.value = Number(form.overall_percentage)
    perfRatioNum.value = Number(form.performance_ratio)
    trivialRatioNum.value = Number(form.trivial_ratio)
  }
  // Load existing materiality if project exists
  if (wizardStore.projectId) {
    try {
      const year = getYear()
      const { data } = await http.get(
        `/api/projects/${wizardStore.projectId}/materiality`,
        { params: { year } }
      )
      const existing = data.data ?? data
      if (existing) {
        result.value = existing
        form.benchmark_type = existing.benchmark_type
        form.benchmark_amount = String(existing.benchmark_amount)
        form.overall_percentage = String(existing.overall_percentage)
        form.performance_ratio = String(existing.performance_ratio)
        form.trivial_ratio = String(existing.trivial_ratio)
        benchmarkNum.value = Number(existing.benchmark_amount)
        overallPctNum.value = Number(existing.overall_percentage)
        perfRatioNum.value = Number(existing.performance_ratio)
        trivialRatioNum.value = Number(existing.trivial_ratio)
      }
    } catch {
      // no existing data
    }
  }
})

/** Validate and return data for wizard save */
async function validate(): Promise<Record<string, any> | null> {
  if (!formRef.value) return null
  try {
    await formRef.value.validate()
    if (!result.value) {
      ElMessage.warning('请先完成重要性水平计算')
      return null
    }
    return {
      benchmark_type: form.benchmark_type,
      benchmark_amount: form.benchmark_amount,
      overall_percentage: form.overall_percentage,
      performance_ratio: form.performance_ratio,
      trivial_ratio: form.trivial_ratio,
      overall_materiality: result.value.overall_materiality,
      performance_materiality: result.value.performance_materiality,
      trivial_threshold: result.value.trivial_threshold,
    }
  } catch {
    return null
  }
}

defineExpose({ validate })
</script>

<style scoped>
.materiality-step {
  max-width: 700px;
  margin: 0 auto;
}
.step-title {
  color: var(--gt-color-primary);
  margin-bottom: var(--gt-space-1);
  font-size: 20px;
}
.step-desc {
  color: #999;
  margin-bottom: var(--gt-space-6);
  font-size: 14px;
}
.materiality-form {
  padding: var(--gt-space-4) 0;
}
.result-panel {
  margin-top: var(--gt-space-6);
  padding: var(--gt-space-4);
  background: #f8f9fa;
  border-radius: var(--gt-radius-md);
}
.result-title {
  font-size: 16px;
  color: var(--gt-color-primary);
  margin-bottom: var(--gt-space-4);
}
.result-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--gt-space-4);
  margin-bottom: var(--gt-space-4);
}
.result-card {
  background: #fff;
  border-radius: var(--gt-radius-sm);
  padding: var(--gt-space-4);
  text-align: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.result-label {
  display: block;
  font-size: 13px;
  color: #999;
  margin-bottom: var(--gt-space-2);
}
.result-value {
  display: block;
  font-size: 20px;
  font-weight: 600;
  color: #333;
}
.result-value.primary {
  color: var(--gt-color-primary);
}
.override-section {
  margin-top: var(--gt-space-4);
}
</style>
