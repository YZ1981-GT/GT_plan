<template>
  <div class="confirmation-dashboard">
    <!-- 覆盖率警示 -->
    <el-alert
      v-if="coverage.warn_level === 'danger'"
      type="error"
      :closable="false"
      show-icon
    >
      回函率 {{ coverage.reply_coverage.toFixed(1) }}%，低于80%，证据可能不足
    </el-alert>
    <el-alert
      v-else-if="coverage.warn_level === 'warn'"
      type="warning"
      :closable="false"
      show-icon
    >
      函证覆盖率 {{ coverage.confirmation_coverage.toFixed(1) }}%，低于50%，请关注
    </el-alert>

    <!-- 覆盖率进度 -->
    <div class="confirmation-dashboard__rates">
      <div class="confirmation-dashboard__rate-item">
        <span>回函覆盖率</span>
        <el-progress
          :percentage="Math.min(coverage.reply_coverage, 100)"
          :color="rateColor(coverage.reply_coverage, 80)"
        />
      </div>
      <div class="confirmation-dashboard__rate-item">
        <span>函证覆盖率</span>
        <el-progress
          :percentage="Math.min(coverage.confirmation_coverage, 100)"
          :color="rateColor(coverage.confirmation_coverage, 50)"
        />
      </div>
    </div>

    <!-- 指标网格 -->
    <el-table :data="metrics" border size="small" v-if="metrics.length">
      <el-table-column prop="account_type" label="科目" width="120" />
      <el-table-column prop="total_count" label="总笔数" width="80" align="center" />
      <el-table-column prop="replied_count" label="已回函" width="80" align="center" />
      <el-table-column prop="matched_count" label="相符" width="80" align="center" />
      <el-table-column label="函证总额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmt(row.total_amount) }}</template>
      </el-table-column>
      <el-table-column label="已确认" width="120" align="right">
        <template #default="{ row }">{{ fmtAmt(row.confirmed_amount) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="120" align="right">
        <template #default="{ row }">{{ fmtAmt(row.difference_amount) }}</template>
      </el-table-column>
    </el-table>
    <el-empty v-else description="暂无数据" :image-size="60" />
  </div>
</template>

<script setup lang="ts">
import type { DashboardMetrics, ConfirmationCoverageMetrics } from './confirmationTypes'

defineProps<{
  metrics: DashboardMetrics[]
  coverage: ConfirmationCoverageMetrics
}>()

function fmtAmt(v: number): string {
  return v != null ? v.toLocaleString() + '元' : '—'
}

function rateColor(pct: number, threshold: number): string {
  if (pct < threshold) return '#f56c6c'
  if (pct < threshold + 15) return '#e6a23c'
  return '#67c23a'
}
</script>

<style scoped>
.confirmation-dashboard__rates {
  display: flex;
  gap: 24px;
  margin: 12px 0;
}
.confirmation-dashboard__rate-item {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}
.confirmation-dashboard__rate-item span {
  font-size: 13px;
  white-space: nowrap;
}
</style>
