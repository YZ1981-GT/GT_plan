<script setup lang="ts">
/**
 * 抽样向导
 * Sprint 8 Task 8.10: 统计/非统计/MUS 三种方法向导
 */
import { ref, computed } from 'vue'

interface SamplingResult {
  sample_size: number
  sampling_interval: number
  method: string
  formula_used: string
}

const props = defineProps<{
  populationSize?: number
  populationValue?: number
}>()

const emit = defineEmits<{
  (e: 'calculate', params: Record<string, unknown>): void
  (e: 'select', params: Record<string, unknown>): void
}>()

const method = ref<'statistical' | 'non_statistical' | 'mus'>('statistical')
const confidenceLevel = ref(0.95)
const tolerableRate = ref(0.05)
const expectedRate = ref(0.01)
const tolerableMisstatement = ref(0)
const expectedMisstatement = ref(0)
const populationSize = ref(props.populationSize || 0)
const populationValue = ref(props.populationValue || 0)

const result = ref<SamplingResult | null>(null)

const methodOptions = [
  { value: 'statistical', label: '统计抽样（属性抽样）', desc: '适用于控制测试' },
  { value: 'non_statistical', label: '非统计抽样', desc: '适用于一般实质性程序' },
  { value: 'mus', label: '货币单位抽样 (MUS)', desc: '适用于大金额实质性程序' },
]

const confidenceOptions = [
  { value: 0.80, label: '80%' },
  { value: 0.85, label: '85%' },
  { value: 0.90, label: '90%' },
  { value: 0.95, label: '95%' },
  { value: 0.99, label: '99%' },
]

const showStatisticalParams = computed(() => method.value === 'statistical')
const showMUSParams = computed(() => method.value === 'mus')

function handleCalculate() {
  const params: Record<string, unknown> = {
    method: method.value,
    population_size: populationSize.value,
    population_value: populationValue.value,
    confidence_level: confidenceLevel.value,
    tolerable_rate: tolerableRate.value,
    expected_rate: expectedRate.value,
    tolerable_misstatement: tolerableMisstatement.value,
    expected_misstatement: expectedMisstatement.value,
  }
  emit('calculate', params)
}

function handleSelect() {
  if (!result.value) return
  emit('select', {
    sample_size: result.value.sample_size,
    method: method.value,
    sampling_interval: result.value.sampling_interval,
  })
}

// 暴露给父组件设置结果
function setResult(r: SamplingResult) {
  result.value = r
}

defineExpose({ setResult })
</script>

<template>
  <div class="sampling-wizard">
    <!-- 方法选择 -->
    <div class="section">
      <h4>1. 选择抽样方法</h4>
      <el-radio-group v-model="method" size="small">
        <el-radio-button
          v-for="opt in methodOptions"
          :key="opt.value"
          :value="opt.value"
        >
          {{ opt.label }}
        </el-radio-button>
      </el-radio-group>
      <p class="method-desc">{{ methodOptions.find(o => o.value === method)?.desc }}</p>
    </div>

    <!-- 参数输入 -->
    <div class="section">
      <h4>2. 输入参数</h4>
      <el-form label-width="120px" size="small">
        <el-form-item label="总体数量">
          <el-input-number v-model="populationSize" :min="0" :step="100" />
        </el-form-item>

        <el-form-item v-if="showMUSParams" label="总体金额">
          <el-input-number v-model="populationValue" :min="0" :step="10000" :precision="2" />
        </el-form-item>

        <el-form-item label="置信水平">
          <el-select v-model="confidenceLevel" style="width: 100px">
            <el-option
              v-for="opt in confidenceOptions"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            />
          </el-select>
        </el-form-item>

        <template v-if="showStatisticalParams">
          <el-form-item label="可容忍偏差率">
            <el-input-number v-model="tolerableRate" :min="0.01" :max="0.20" :step="0.01" :precision="2" />
          </el-form-item>
          <el-form-item label="预期偏差率">
            <el-input-number v-model="expectedRate" :min="0" :max="0.10" :step="0.005" :precision="3" />
          </el-form-item>
        </template>

        <template v-if="showMUSParams">
          <el-form-item label="可容忍错报">
            <el-input-number v-model="tolerableMisstatement" :min="0" :step="10000" :precision="2" />
          </el-form-item>
          <el-form-item label="预期错报">
            <el-input-number v-model="expectedMisstatement" :min="0" :step="1000" :precision="2" />
          </el-form-item>
        </template>
      </el-form>

      <el-button type="primary" size="small" @click="handleCalculate">
        计算样本量
      </el-button>
    </div>

    <!-- 计算结果 -->
    <div v-if="result" class="section result-section">
      <h4>3. 计算结果</h4>
      <div class="result-card">
        <div class="result-main">
          <span class="result-label">样本量</span>
          <span class="result-value">{{ result.sample_size }}</span>
        </div>
        <div v-if="result.sampling_interval" class="result-detail">
          抽样间距: {{ result.sampling_interval.toLocaleString() }}
        </div>
        <div class="result-formula">
          <el-text type="info" size="small">{{ result.formula_used }}</el-text>
        </div>
      </div>

      <el-button type="success" size="small" style="margin-top: 12px" @click="handleSelect">
        执行选样
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.sampling-wizard {
  padding: 12px;
}
.section {
  margin-bottom: 20px;
}
.section h4 {
  margin: 0 0 10px;
  font-size: 14px;
  color: #303133;
}
.method-desc {
  margin: 6px 0 0;
  font-size: 12px;
  color: #909399;
}
.result-section {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 14px;
}
.result-card {
  text-align: center;
}
.result-main {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.result-label {
  font-size: 12px;
  color: #909399;
}
.result-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--el-color-primary);
  font-variant-numeric: tabular-nums;
}
.result-detail {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
}
.result-formula {
  margin-top: 8px;
  padding: 6px 10px;
  background: #fff;
  border-radius: 4px;
  font-size: 11px;
}
</style>
