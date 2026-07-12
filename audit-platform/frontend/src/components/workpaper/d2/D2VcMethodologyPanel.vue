<script setup lang="ts">
/**
 * D2VcMethodologyPanel — 方法学参数区子组件
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 7.4
 *
 * 六区段：
 * 1. 测试总体（AI 生成描述 + 金额/笔数计算字段）
 * 2. 特定样本列表（客户名/金额/标记原因/确认/取消）
 * 3. 抽样总体（只读计算 = 测试总体 - 确认的特定样本）
 * 4. 抽样方法（下拉 + AI 推荐标签）
 * 5. 样本量（输入 + 推荐值 + 偏离标记）
 * 6. 抽样程序（textarea）
 *
 * Requirements: 2.3, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 11.4, 11.5
 */
import { computed } from 'vue'
import type { PopulationDesc, SpecificSampleItem } from '../composables/useD2VcMethodology'

const props = defineProps<{
  isReadonly: boolean
  methodology: any // Return type of useD2VcMethodology
}>()

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtNum(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtCount(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return '0'
  return val.toLocaleString('zh-CN')
}

// ─── Computed from methodology ───────────────────────────────────────────────

const testPopulation = computed<PopulationDesc>(() => props.methodology.testPopulation.value)
const specificSamples = computed<SpecificSampleItem[]>(() => props.methodology.specificSamples.value)
const samplingPopulation = computed<PopulationDesc>(() => props.methodology.samplingPopulation.value)
const samplingMethod = computed({
  get: () => props.methodology.samplingMethod.value,
  set: (v: string) => {
    props.methodology.samplingMethod.value = v
    props.methodology.saveToResponses()
  },
})
const samplingProcedure = computed({
  get: () => props.methodology.samplingProcedure.value,
  set: (v: string) => {
    props.methodology.samplingProcedure.value = v
    props.methodology.saveToResponses()
  },
})
const userSampleSize = computed({
  get: () => props.methodology.userSampleSize.value,
  set: (v: number) => {
    props.methodology.userSampleSize.value = v
    props.methodology.saveToResponses()
  },
})
const recommendedMethod = computed(() => props.methodology.recommendedMethod.value)
const recommendedSampleSize = computed(() => props.methodology.recommendedSampleSize.value)
const recommendedReason = computed(() => props.methodology.recommendedReason.value)
const sampleSizeDeviation = computed(() => props.methodology.sampleSizeDeviation.value)
const aiGenerating = computed(() => props.methodology.aiGenerating.value)

// 特定样本统计
const confirmedSamples = computed(() => specificSamples.value.filter(s => s.confirmed))
const confirmedTotalAmount = computed(() => confirmedSamples.value.reduce((sum, s) => sum + s.amount, 0))

// ─── Actions ─────────────────────────────────────────────────────────────────

function handleGenerateDescription() {
  if (props.isReadonly || aiGenerating.value) return
  props.methodology.generateTestPopulationDescription()
}

function handleDescriptionChange(val: string) {
  props.methodology.testPopulation.value = {
    ...props.methodology.testPopulation.value,
    description: val,
  }
  props.methodology.saveToResponses()
}

function handleConfirmSample(index: number, val: boolean) {
  const samples = [...specificSamples.value]
  samples[index] = { ...samples[index], confirmed: val }
  props.methodology.specificSamples.value = samples
  props.methodology.computeRecommendation()
  props.methodology.saveToResponses()
}

function handleRemoveSample(index: number) {
  const samples = [...specificSamples.value]
  samples.splice(index, 1)
  props.methodology.specificSamples.value = samples
  props.methodology.computeRecommendation()
  props.methodology.saveToResponses()
}

// 抽样方法选项
const methodOptions = [
  { value: '随机抽样', label: '随机抽样' },
  { value: 'mus', label: 'MUS（货币单元抽样）' },
  { value: '分层抽样', label: '分层抽样' },
  { value: '特定项目', label: '特定项目' },
]
</script>

<template>
  <div class="vc-methodology-panel">
    <!-- 1. 测试总体 -->
    <div class="methodology-section">
      <div class="section-header">
        <span class="section-label">测试总体</span>
        <el-button
          v-if="!isReadonly"
          type="primary"
          link
          size="small"
          :loading="aiGenerating"
          :disabled="aiGenerating"
          class="ai-btn"
          @click="handleGenerateDescription"
        >
          🤖 AI 生成
        </el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2 }"
        :model-value="testPopulation.description"
        :disabled="isReadonly"
        placeholder="描述测试总体范围..."
        @update:model-value="handleDescriptionChange"
      />
      <div class="computed-fields">
        <el-tooltip content="从试算表获取的科目1122本期借方发生额合计" placement="top">
          <span class="computed-value">
            金额: {{ fmtNum(testPopulation.amount) }} 元
          </span>
        </el-tooltip>
        <el-tooltip content="测试总体涉及的交易笔数" placement="top">
          <span class="computed-value">
            笔数: {{ fmtCount(testPopulation.count) }} 笔
          </span>
        </el-tooltip>
      </div>
    </div>

    <!-- 2. 特定样本 -->
    <div class="methodology-section">
      <div class="section-header">
        <span class="section-label">特定样本</span>
      </div>
      <div v-if="specificSamples.length === 0" class="empty-hint">
        暂无特定样本（金额≥可容忍错报 / 关联方 / 异常日期的交易将被自动标记）
      </div>
      <el-table
        v-else
        :data="specificSamples"
        size="small"
        border
        class="specific-sample-table"
      >
        <el-table-column prop="customerName" label="客户名称" min-width="120" />
        <el-table-column label="金额" min-width="110" align="right">
          <template #default="{ row }">
            {{ fmtNum(row.amount) }}
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="标记原因" min-width="140" />
        <el-table-column label="确认" width="70" align="center">
          <template #default="{ row, $index }">
            <el-checkbox
              :model-value="row.confirmed"
              :disabled="isReadonly"
              @update:model-value="(val: boolean) => handleConfirmSample($index, val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ $index }">
            <el-button
              type="danger"
              link
              size="small"
              :disabled="isReadonly"
              @click="handleRemoveSample($index)"
            >
              取消标记
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="specificSamples.length > 0" class="sample-summary">
        已确认: {{ confirmedSamples.length }} 笔，合计金额: {{ fmtNum(confirmedTotalAmount) }} 元
      </div>
    </div>

    <!-- 3. 抽样总体（只读计算） -->
    <div class="methodology-section">
      <div class="section-header">
        <span class="section-label">抽样总体</span>
        <span class="computed-hint">（自动计算 = 测试总体 − 已确认特定样本）</span>
      </div>
      <div class="computed-fields">
        <el-tooltip content="抽样总体金额 = 测试总体金额 − 确认的特定样本金额合计" placement="top">
          <span class="computed-value">
            金额: {{ fmtNum(samplingPopulation.amount) }} 元
          </span>
        </el-tooltip>
        <el-tooltip content="抽样总体笔数 = 测试总体笔数 − 确认的特定样本笔数" placement="top">
          <span class="computed-value">
            笔数: {{ fmtCount(samplingPopulation.count) }} 笔
          </span>
        </el-tooltip>
      </div>
      <div v-if="samplingPopulation.description" class="computed-desc">
        {{ samplingPopulation.description }}
      </div>
    </div>

    <!-- 4. 抽样方法 -->
    <div class="methodology-section">
      <div class="section-header">
        <span class="section-label">抽样方法</span>
      </div>
      <div class="method-row">
        <el-select
          v-model="samplingMethod"
          :disabled="isReadonly"
          placeholder="选择抽样方法"
          style="width: 200px"
        >
          <el-option
            v-for="opt in methodOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-tooltip
          v-if="recommendedMethod"
          :content="recommendedReason || '基于 B15/B50 联动推荐'"
          placement="top"
        >
          <el-tag type="warning" size="small" class="ai-recommend-tag">
            🤖 建议: {{ recommendedMethod }}
          </el-tag>
        </el-tooltip>
      </div>
    </div>

    <!-- 5. 样本量 -->
    <div class="methodology-section">
      <div class="section-header">
        <span class="section-label">样本量</span>
      </div>
      <div class="sample-size-row">
        <el-input-number
          v-model="userSampleSize"
          :disabled="isReadonly"
          :min="0"
          :step="1"
          controls-position="right"
          style="width: 140px"
        />
        <el-tooltip
          v-if="recommendedSampleSize > 0"
          :content="recommendedReason || '基于 B15/B50 推荐'"
          placement="top"
        >
          <el-tag type="warning" size="small" class="ai-recommend-tag">
            🤖 建议: {{ recommendedSampleSize }} 笔
          </el-tag>
        </el-tooltip>
        <!-- 偏离指示器 -->
        <el-tag
          v-if="sampleSizeDeviation === 'below'"
          type="warning"
          size="small"
          class="deviation-tag"
        >
          ⚠️ 样本量低于建议值
        </el-tag>
        <el-tag
          v-else-if="sampleSizeDeviation === 'ok'"
          type="success"
          size="small"
          class="deviation-tag"
        >
          ✓ 样本量满足要求
        </el-tag>
      </div>
    </div>

    <!-- 6. 抽样程序 -->
    <div class="methodology-section">
      <div class="section-header">
        <span class="section-label">抽样程序</span>
      </div>
      <el-input
        v-model="samplingProcedure"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="描述具体的抽样执行步骤..."
      />
    </div>
  </div>
</template>

<style scoped>
.vc-methodology-panel {
  font-size: 13px;
}

.methodology-section {
  margin-bottom: 18px;
}

.section-header {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  gap: 8px;
}

.section-label {
  font-weight: 600;
  font-size: 13px;
  color: #303133;
}

.computed-hint {
  font-size: 12px;
  color: #909399;
}

.ai-btn {
  margin-left: auto;
}

.computed-fields {
  display: flex;
  gap: 20px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.computed-value {
  display: inline-block;
  padding: 4px 10px;
  background: #f5f7fa;
  border-bottom: 1px dashed #dcdfe6;
  cursor: help;
  font-size: 13px;
  color: #606266;
  border-radius: 2px;
}

.computed-desc {
  margin-top: 6px;
  padding: 4px 10px;
  background: #f5f7fa;
  border-bottom: 1px dashed #dcdfe6;
  cursor: help;
  font-size: 12px;
  color: #909399;
}

.empty-hint {
  color: #c0c4cc;
  font-size: 12px;
  padding: 8px 0;
}

.specific-sample-table {
  font-size: 13px;
}

.sample-summary {
  margin-top: 6px;
  font-size: 12px;
  color: #606266;
}

.method-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.sample-size-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.ai-recommend-tag {
  cursor: help;
}

.deviation-tag {
  cursor: default;
}
</style>
