<template>
  <div class="entity-verify-dashboard">
    <div class="entity-verify-dashboard__metrics">
      <!-- 核实完成率 -->
      <div class="entity-verify-dashboard__metric">
        <span class="entity-verify-dashboard__label">核实完成率</span>
        <el-progress
          :percentage="Math.round(metrics.verify_rate)"
          :color="metrics.verify_rate >= 100 ? '#67c23a' : '#409eff'"
          :stroke-width="14"
        />
        <span class="entity-verify-dashboard__count">
          {{ metrics.verified_count }} / {{ metrics.total_count }}
        </span>
      </div>
      <!-- 退回率 -->
      <div class="entity-verify-dashboard__metric">
        <span class="entity-verify-dashboard__label">退回率</span>
        <el-progress
          :percentage="Math.round(metrics.return_rate)"
          :color="metrics.return_rate > 30 ? '#e6a23c' : '#409eff'"
          :stroke-width="14"
        />
        <span class="entity-verify-dashboard__count">
          {{ metrics.returned_count }} / {{ metrics.total_count }}
        </span>
      </div>
    </div>

    <!-- 状态计数 -->
    <div class="entity-verify-dashboard__status-row">
      <el-tag type="info" size="small">总计: {{ metrics.total_count }}</el-tag>
      <el-tag type="success" size="small">已核实: {{ metrics.verified_count }}</el-tag>
      <el-tag type="warning" size="small">待核实: {{ metrics.pending_count }}</el-tag>
      <el-tag type="danger" size="small">退回: {{ metrics.returned_count }}</el-tag>
      <el-badge :value="metrics.fraud_flag_count" :hidden="metrics.fraud_flag_count === 0" class="entity-verify-dashboard__fraud-badge">
        <el-tag :type="metrics.fraud_flag_count > 0 ? 'danger' : 'info'" size="small">
          舞弊标志
        </el-tag>
      </el-badge>
    </div>

    <!-- Warnings -->
    <div v-if="metrics.fraud_flag_count > 0" class="entity-verify-dashboard__alert entity-verify-dashboard__alert--red">
      <el-alert
        title="存在舞弊风险迹象"
        :description="`${metrics.fraud_flag_count} 家单位触发舞弊红旗，请重点关注并记录至D0-8`"
        type="error"
        show-icon
        :closable="false"
      />
    </div>
    <div v-if="metrics.return_rate > 30" class="entity-verify-dashboard__alert entity-verify-dashboard__alert--orange">
      <el-alert
        title="退回率偏高"
        :description="`当前退回率 ${Math.round(metrics.return_rate)}% 超过 30% 阈值，需关注函证地址准确性`"
        type="warning"
        show-icon
        :closable="false"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ProgressMetrics } from './entityVerifyTypes'

defineProps<{
  metrics: ProgressMetrics
}>()
</script>

<style scoped>
.entity-verify-dashboard {
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
}

.entity-verify-dashboard__metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 8px;
}

.entity-verify-dashboard__metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.entity-verify-dashboard__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 500;
}

.entity-verify-dashboard__count {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  text-align: right;
}

.entity-verify-dashboard__status-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.entity-verify-dashboard__fraud-badge {
  line-height: 1;
}

.entity-verify-dashboard__alert {
  margin-top: 8px;
}
</style>
