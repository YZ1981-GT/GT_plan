<template>
  <div class="fraud-risk-conclusion">
    <h4 class="fraud-risk-conclusion__title">审计结论</h4>

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
import { computed } from 'vue'
import type { FraudRiskConclusion, FraudRiskMetrics } from './fraudRiskTypes'
import { FRAUD_RISK_CONCLUSION_OPTIONS } from './fraudRiskEnums'

const props = defineProps<{
  conclusion: FraudRiskConclusion
  metrics: FraudRiskMetrics
  readonly: boolean
}>()

defineEmits<{
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
</script>

<style scoped>
.fraud-risk-conclusion {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 14px 16px;
  margin-top: 12px;
}

.fraud-risk-conclusion__title {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
}

.fraud-risk-conclusion__section {
  margin-bottom: 12px;
}

.fraud-risk-conclusion__label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
  color: var(--el-text-color-primary);
}

.fraud-risk-conclusion__value {
  font-size: 13px;
}

.fraud-risk-conclusion__text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  margin: 0;
}

.fraud-risk-conclusion__pending {
  margin-top: 12px;
}
</style>
