<template>
  <div class="confirmation-sampling">
    <!-- 自动统计卡片（从发函数据联动） -->
    <div class="confirmation-sampling__stats">
      <el-tooltip content="已录入的函证对象总数" placement="top">
        <div class="confirmation-sampling__stat-item">
          <span class="confirmation-sampling__stat-label">总体笔数</span>
          <span class="confirmation-sampling__stat-value">{{ stats.totalCount }} 笔</span>
        </div>
      </el-tooltip>
      <el-tooltip content="所有函证对象的账面金额合计" placement="top">
        <div class="confirmation-sampling__stat-item">
          <span class="confirmation-sampling__stat-label">总体金额</span>
          <span class="confirmation-sampling__stat-value">{{ stats.totalAmount.toLocaleString() }} 元</span>
        </div>
      </el-tooltip>
      <el-tooltip content="实际纳入函证程序的样本数量（当前=总体）" placement="top">
        <div class="confirmation-sampling__stat-item">
          <span class="confirmation-sampling__stat-label">已选样本</span>
          <span class="confirmation-sampling__stat-value">{{ stats.sampleCount }} 笔</span>
        </div>
      </el-tooltip>
      <el-tooltip content="样本覆盖的金额合计" placement="top">
        <div class="confirmation-sampling__stat-item">
          <span class="confirmation-sampling__stat-label">样本金额</span>
          <span class="confirmation-sampling__stat-value">{{ stats.sampleAmount.toLocaleString() }} 元</span>
        </div>
      </el-tooltip>
      <el-tooltip content="覆盖率 = 样本金额 / 总体金额 × 100%（建议 ≥ 70%）" placement="top">
        <div class="confirmation-sampling__stat-item">
          <span class="confirmation-sampling__stat-label">覆盖率</span>
          <span class="confirmation-sampling__stat-value" :class="{ 'confirmation-sampling__stat-value--warn': stats.coverage < 70 }">
            {{ stats.coverage.toFixed(1) }}%
          </span>
        </div>
      </el-tooltip>
    </div>

    <!-- 表单区 -->
    <el-form label-width="80px" size="small" class="confirmation-sampling__form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="抽样方式">
            <el-select
              :model-value="data.sampling_method"
              :disabled="readonly"
              placeholder="请选择"
              filterable
              allow-create
              @update:model-value="(v) => $emit('update', 'sampling_method', v)"
            >
              <el-option value="随机选样" label="随机选样" />
              <el-option value="金额前N大" label="金额前N大" />
              <el-option value="全部函证" label="全部函证" />
              <el-option value="系统抽样" label="系统抽样" />
              <el-option value="分层抽样" label="分层抽样" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="样本量">
            <el-input
              :model-value="data.sampling_size"
              :disabled="readonly"
              placeholder="如：15 笔 / 金额前 10 大"
              @update:model-value="(v) => $emit('update', 'sampling_size', v)"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="选样标准">
        <el-input
          :model-value="data.sampling_criteria"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          :placeholder="criteriaSuggestion"
          @update:model-value="(v) => $emit('update', 'sampling_criteria', v)"
        />
      </el-form-item>
      <el-form-item label="抽样结论">
        <el-input
          :model-value="data.sampling_conclusion"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          placeholder="抽样结果是否支持审计结论（如：函证覆盖率达到 XX%，满足审计要求）"
          @update:model-value="(v) => $emit('update', 'sampling_conclusion', v)"
        />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SamplingData } from './confirmationTypes'

const props = defineProps<{
  data: SamplingData
  readonly: boolean
  dictData: Record<string, any[]>
  /** 从父组件传入的发函统计数据 */
  totalCount?: number
  totalAmount?: number
  sampleCount?: number
  sampleAmount?: number
}>()

defineEmits<{
  (e: 'update', field: string, value: any): void
}>()

const stats = computed(() => ({
  totalCount: props.totalCount ?? 0,
  totalAmount: props.totalAmount ?? 0,
  sampleCount: props.sampleCount ?? props.totalCount ?? 0,
  sampleAmount: props.sampleAmount ?? props.totalAmount ?? 0,
  coverage: props.totalAmount && props.totalAmount > 0
    ? ((props.sampleAmount ?? props.totalAmount) / props.totalAmount) * 100
    : 0,
}))

const criteriaSuggestion = computed(() => {
  const method = props.data?.sampling_method
  if (method === '金额前N大') return '选取余额前 N 大的客户/供应商进行函证（覆盖科目余额 XX% 以上）'
  if (method === '全部函证') return '科目余额全部函证（期末有余额的所有客户/供应商）'
  if (method === '分层抽样') return '按金额分层：大额全选 + 中额随机 + 小额判断性选取'
  return '根据重要性水平和审计风险确定选样标准（如：余额超过重要性水平 50% 的全选，其余随机）'
})
</script>

<style scoped>
.confirmation-sampling__stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  margin-bottom: 12px;
}
.confirmation-sampling__stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 80px;
}
.confirmation-sampling__stat-label {
  font-size: 11px;
  color: #909399;
}
.confirmation-sampling__stat-value {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.confirmation-sampling__stat-value--warn {
  color: #f56c6c;
}
.confirmation-sampling__form {
  padding: 0 4px;
}
</style>
