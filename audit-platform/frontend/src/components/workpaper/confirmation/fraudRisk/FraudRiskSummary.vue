<template>
  <div class="fraud-risk-summary">
    <h4 class="fraud-risk-summary__title">舞弊风险汇总评价</h4>

    <!-- 财务报表层次 -->
    <div class="fraud-risk-summary__section">
      <label class="fraud-risk-summary__label">财务报表层次舞弊风险评价</label>
      <el-input
        v-if="!readonly"
        :model-value="summary.statement_level_risk"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="请评价财务报表层次的舞弊风险（如：是否存在管理层凌驾内控之上的系统性风险）"
        @change="(val: string) => $emit('update', 'statement_level_risk', val)"
      />
      <p v-else class="fraud-risk-summary__text">
        {{ summary.statement_level_risk || '—' }}
      </p>
    </div>

    <!-- 认定层次 -->
    <div class="fraud-risk-summary__section">
      <label class="fraud-risk-summary__label">认定层次舞弊风险评价</label>
      <el-input
        v-if="!readonly"
        :model-value="summary.assertion_level_risk"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="请评价认定层次的舞弊风险（如：收入确认认定中是否存在通过虚构交易高估收入的风险）"
        @change="(val: string) => $emit('update', 'assertion_level_risk', val)"
      />
      <p v-else class="fraud-risk-summary__text">
        {{ summary.assertion_level_risk || '—' }}
      </p>
    </div>

    <!-- 初步应对 -->
    <div class="fraud-risk-summary__section">
      <label class="fraud-risk-summary__label">初步应对措施</label>
      <el-input
        v-if="!readonly"
        :model-value="summary.initial_response"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="请描述初步应对措施（如：扩大函证范围/追加实质性程序/与治理层沟通等）"
        @change="(val: string) => $emit('update', 'initial_response', val)"
      />
      <p v-else class="fraud-risk-summary__text">
        {{ summary.initial_response || '—' }}
      </p>
    </div>

    <!-- B50 跳转 -->
    <div class="fraud-risk-summary__section fraud-risk-summary__jump">
      <el-button type="primary" text @click="$emit('jump-b50')">
        → 跳转 B50 风险评估底稿
      </el-button>
      <span class="fraud-risk-summary__hint">
        （舞弊风险评价结果应同步更新至 B50 整体风险评估）
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FraudRiskSummary } from './fraudRiskTypes'

defineProps<{
  summary: FraudRiskSummary
  readonly: boolean
}>()

defineEmits<{
  (e: 'update', field: string, value: string): void
  (e: 'jump-b50'): void
}>()
</script>

<style scoped>
.fraud-risk-summary {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 14px 16px;
  margin-top: 12px;
}

.fraud-risk-summary__title {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
}

.fraud-risk-summary__section {
  margin-bottom: 12px;
}

.fraud-risk-summary__section:last-child {
  margin-bottom: 0;
}

.fraud-risk-summary__label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--el-text-color-primary);
}

.fraud-risk-summary__text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  margin: 0;
  padding: 4px 0;
}

.fraud-risk-summary__jump {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-extra-light);
}

.fraud-risk-summary__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
