<template>
  <div class="fraud-risk-dashboard">
    <el-collapse v-model="expanded">
      <el-collapse-item name="dashboard" title="舞弊风险评价概览">
        <div class="fraud-risk-dashboard__grid">
          <div class="fraud-risk-dashboard__stat">
            <span class="fraud-risk-dashboard__stat-value">{{ metrics.total_count }}</span>
            <span class="fraud-risk-dashboard__stat-label">总条目</span>
          </div>
          <div class="fraud-risk-dashboard__stat fraud-risk-dashboard__stat--danger">
            <span class="fraud-risk-dashboard__stat-value">{{ metrics.exist_count }}</span>
            <span class="fraud-risk-dashboard__stat-label">存在迹象</span>
          </div>
          <div class="fraud-risk-dashboard__stat fraud-risk-dashboard__stat--success">
            <span class="fraud-risk-dashboard__stat-value">{{ metrics.with_measure_count }}</span>
            <span class="fraud-risk-dashboard__stat-label">已填应对</span>
          </div>
          <div
            class="fraud-risk-dashboard__stat"
            :class="{ 'fraud-risk-dashboard__stat--warning': metrics.without_measure_count > 0 }"
          >
            <span class="fraud-risk-dashboard__stat-value">{{ metrics.without_measure_count }}</span>
            <span class="fraud-risk-dashboard__stat-label">未填应对</span>
          </div>
          <div class="fraud-risk-dashboard__stat">
            <span class="fraud-risk-dashboard__stat-value">{{ metrics.completion_rate }}%</span>
            <span class="fraud-risk-dashboard__stat-label">评估完成率</span>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { FraudRiskMetrics } from './fraudRiskTypes'

defineProps<{
  metrics: FraudRiskMetrics
}>()

const expanded = ref(['dashboard'])
</script>

<style scoped>
.fraud-risk-dashboard {
  margin-bottom: 12px;
}

.fraud-risk-dashboard__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 12px;
}

.fraud-risk-dashboard__stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 8px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}

.fraud-risk-dashboard__stat--danger {
  background: var(--el-color-danger-light-9);
}

.fraud-risk-dashboard__stat--danger .fraud-risk-dashboard__stat-value {
  color: var(--el-color-danger);
}

.fraud-risk-dashboard__stat--warning {
  background: var(--el-color-warning-light-9);
}

.fraud-risk-dashboard__stat--warning .fraud-risk-dashboard__stat-value {
  color: var(--el-color-warning);
}

.fraud-risk-dashboard__stat--success {
  background: var(--el-color-success-light-9);
}

.fraud-risk-dashboard__stat--success .fraud-risk-dashboard__stat-value {
  color: var(--el-color-success);
}

.fraud-risk-dashboard__stat-value {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
}

.fraud-risk-dashboard__stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
