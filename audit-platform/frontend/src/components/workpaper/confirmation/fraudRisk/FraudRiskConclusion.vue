<template>
  <div class="fraud-risk-conclusion">
    <div class="fraud-risk-conclusion__header">
      <h4 class="fraud-risk-conclusion__title">审计结论</h4>
      <el-button
        v-if="!readonly"
        type="primary"
        size="small"
        plain
        :loading="aiLoading"
        @click="handleAiFill"
      >
        AI 智能填充
      </el-button>
    </div>

    <!-- 结论类型 -->
    <div class="fraud-risk-conclusion__section">
      <label class="fraud-risk-conclusion__label">结论类型</label>
      <el-radio-group
        v-if="!readonly"
        :model-value="conclusion.conclusion_type"
        @change="(val: string) => $emit('update', 'conclusion_type', val)"
      >
        <el-radio
          v-for="opt in FRAUD_RISK_CONCLUSION_OPTIONS"
          :key="opt.value"
          :value="opt.value"
        >
          {{ opt.label }}
        </el-radio>
      </el-radio-group>
      <span v-else class="fraud-risk-conclusion__value">
        {{ conclusionLabel || '—' }}
      </span>
    </div>

    <!-- 结论说明 -->
    <div class="fraud-risk-conclusion__section">
      <label class="fraud-risk-conclusion__label">结论说明</label>
      <el-input
        v-if="!readonly"
        :model-value="conclusion.conclusion_text"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="请填写审计结论说明"
        @change="(val: string) => $emit('update', 'conclusion_text', val)"
      />
      <p v-else class="fraud-risk-conclusion__text">
        {{ conclusion.conclusion_text || '—' }}
      </p>
    </div>

    <!-- 未决事项提示 -->
    <div v-if="hasPendingItems" class="fraud-risk-conclusion__pending">
      <el-alert type="warning" :closable="false" show-icon>
        存在 {{ pendingCount }} 条已识别舞弊风险迹象尚未填写应对措施，请补充完善后形成最终结论。
      </el-alert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { FraudRiskConclusion, FraudRiskMetrics } from './fraudRiskTypes'
import { FRAUD_RISK_CONCLUSION_OPTIONS } from './fraudRiskEnums'

const props = defineProps<{
  conclusion: FraudRiskConclusion
  metrics: FraudRiskMetrics
  readonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update', field: string, value: any): void
}>()

const conclusionLabel = computed(() => {
  const opt = FRAUD_RISK_CONCLUSION_OPTIONS.find(
    (o) => o.value === props.conclusion.conclusion_type
  )
  return opt?.label ?? ''
})

const hasPendingItems = computed(() => props.metrics.without_measure_count > 0)
const pendingCount = computed(() => props.metrics.without_measure_count)

const aiLoading = ref(false)

function handleAiFill() {
  aiLoading.value = true
  try {
    const existCount = props.metrics.exist_count ?? 0
    const withoutMeasure = props.metrics.without_measure_count ?? 0

    // 推荐结论类型
    if (!props.conclusion.conclusion_type) {
      if (existCount === 0) {
        emit('update', 'conclusion_type', 'A')
      } else if (existCount <= 3 && withoutMeasure === 0) {
        emit('update', 'conclusion_type', 'B')
      } else {
        emit('update', 'conclusion_type', 'C')
      }
    }

    // 生成结论说明
    if (!props.conclusion.conclusion_text) {
      let text = ''
      if (existCount === 0) {
        text = '经对函证程序全过程中的舞弊风险迹象逐项评估，未发现舞弊风险迹象。函证程序获取的审计证据充分、适当，可作为形成审计意见的基础。'
      } else if (withoutMeasure === 0) {
        text = `共识别 ${existCount} 项舞弊风险迹象，已全部制定应对措施。经评估，已识别的风险迹象影响有限，通过追加的审计程序已获取充分证据，不影响审计意见。建议将评价结果更新至 B50。`
      } else {
        text = `共识别 ${existCount} 项舞弊风险迹象，其中 ${withoutMeasure} 项尚未制定应对措施。存在重大舞弊风险迹象，需进一步扩大审计程序范围、与治理层沟通，并考虑对审计意见类型的影响。`
      }
      emit('update', 'conclusion_text', text)
    }

    ElMessage.success('已根据风险评估数据生成审计结论（仅供参考，请根据实际情况修改）')
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.fraud-risk-conclusion {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 14px 16px;
  margin-top: 12px;
}

.fraud-risk-conclusion__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.fraud-risk-conclusion__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.fraud-risk-conclusion__section {
  margin-bottom: 12px;
}

.fraud-risk-conclusion__label {
  display: block;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  margin-bottom: 6px;
  color: var(--el-text-color-primary);
}

.fraud-risk-conclusion__value {
  font-size: var(--wp-font-size, 13px);
}

.fraud-risk-conclusion__text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  color: var(--el-text-color-regular);
  margin: 0;
}

.fraud-risk-conclusion__pending {
  margin-top: 12px;
}
</style>
