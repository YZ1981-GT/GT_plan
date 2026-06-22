<template>
  <div class="followup-dashboard">
    <el-row :gutter="12">
      <el-col :span="4">
        <div class="followup-dashboard__card">
          <div class="followup-dashboard__value">{{ metrics.total_count }}</div>
          <div class="followup-dashboard__label">总记录数</div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="followup-dashboard__card">
          <div class="followup-dashboard__value followup-dashboard__value--success">
            {{ metrics.signed_count }}
          </div>
          <div class="followup-dashboard__label">已签名</div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="followup-dashboard__card">
          <div class="followup-dashboard__value followup-dashboard__value--success">
            {{ metrics.control_pass_count }}
          </div>
          <div class="followup-dashboard__label">控制通过</div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="followup-dashboard__card">
          <div class="followup-dashboard__value followup-dashboard__value--danger">
            {{ metrics.control_fail_count }}
          </div>
          <div class="followup-dashboard__label">控制未通过</div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="followup-dashboard__card">
          <div class="followup-dashboard__value followup-dashboard__value--warning">
            {{ metrics.anomaly_count }}
          </div>
          <div class="followup-dashboard__label">异常项</div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="followup-dashboard__card followup-dashboard__card--rates">
          <div class="followup-dashboard__rate-item">
            <span class="followup-dashboard__rate-label">签名率</span>
            <el-progress
              :percentage="roundRate(metrics.sign_rate)"
              :stroke-width="8"
              :color="rateColor(metrics.sign_rate)"
            />
          </div>
          <div class="followup-dashboard__rate-item">
            <span class="followup-dashboard__rate-label">控制通过率</span>
            <el-progress
              :percentage="roundRate(metrics.control_pass_rate)"
              :stroke-width="8"
              :color="rateColor(metrics.control_pass_rate)"
            />
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- Anomaly alerts -->
    <div v-if="metrics.anomaly_count > 0" class="followup-dashboard__alert">
      <el-alert
        :title="`发现 ${metrics.anomaly_count} 项控制异常`"
        description="存在控制检查项为「否」的记录，请关注并记录应对措施"
        type="error"
        show-icon
        :closable="false"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FollowupProgressMetrics } from './followupTypes'

defineProps<{
  metrics: FollowupProgressMetrics
}>()

function roundRate(rate: number): number {
  return Math.round(rate * 10) / 10
}

function rateColor(rate: number): string {
  if (rate >= 80) return '#67c23a'
  if (rate >= 50) return '#e6a23c'
  return '#f56c6c'
}
</script>

<style scoped>
.followup-dashboard {
  margin-bottom: 16px;
}

.followup-dashboard__card {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 12px;
  text-align: center;
}

.followup-dashboard__card--rates {
  text-align: left;
  padding: 8px 12px;
}

.followup-dashboard__value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
}

.followup-dashboard__value--success {
  color: #67c23a;
}

.followup-dashboard__value--danger {
  color: #f56c6c;
}

.followup-dashboard__value--warning {
  color: #e6a23c;
}

.followup-dashboard__label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.followup-dashboard__rate-item {
  margin-bottom: 4px;
}

.followup-dashboard__rate-item:last-child {
  margin-bottom: 0;
}

.followup-dashboard__rate-label {
  font-size: 11px;
  color: #909399;
}

.followup-dashboard__alert {
  margin-top: 12px;
}
</style>
