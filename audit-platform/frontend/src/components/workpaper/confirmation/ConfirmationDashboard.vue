<template>
  <div class="confirmation-dashboard">
    <!-- 覆盖率警示 -->
    <el-alert
      v-if="coverage?.warn_level === 'danger'"
      type="error"
      :closable="false"
      show-icon
    >
      回函覆盖率 {{ (coverage?.reply_coverage ?? 0).toFixed(1) }}%，低于80%，证据可能不足
    </el-alert>
    <el-alert
      v-else-if="coverage?.warn_level === 'warn'"
      type="warning"
      :closable="false"
      show-icon
    >
      函证覆盖率 {{ (coverage?.confirmation_coverage ?? 0).toFixed(1) }}%，低于50%，请关注
    </el-alert>
    <!-- population 缺失：函证覆盖率未参与预警 -->
    <el-alert
      v-if="coverage && coverage.population_available === false"
      type="info"
      :closable="false"
      show-icon
    >
      函证覆盖率因缺科目总体金额（试算表审定总额）未参与预警，当前预警仅基于回函覆盖率
    </el-alert>

    <!-- 覆盖率进度 -->
    <div class="confirmation-dashboard__rates">
      <el-tooltip content="回函覆盖率 = 已回函笔数 / 已发函笔数 × 100%（建议 ≥ 80%）" placement="top">
        <div class="confirmation-dashboard__rate-item">
          <span>回函覆盖率</span>
          <el-progress
            :percentage="Math.min(coverage?.reply_coverage ?? 0, 100)"
            :color="rateColor(coverage?.reply_coverage ?? 0, 80)"
          />
        </div>
      </el-tooltip>
      <el-tooltip content="函证覆盖率 = 发函总额 / 科目审定总额(TB) × 100%（建议 ≥ 50%）" placement="top">
        <div class="confirmation-dashboard__rate-item">
          <span>函证覆盖率</span>
          <el-progress
            v-if="coverage?.population_available && coverage?.confirmation_coverage != null"
            :percentage="Math.min(coverage.confirmation_coverage, 100)"
            :color="rateColor(coverage.confirmation_coverage, 50)"
          />
          <span v-else class="confirmation-dashboard__na">需科目总体金额（TB）</span>
        </div>
      </el-tooltip>
      <el-tooltip content="确认覆盖率 =（回函确认 + 替代确认金额）/ 科目审定总额(TB) × 100%" placement="top">
        <div class="confirmation-dashboard__rate-item">
          <span>确认覆盖率</span>
          <el-progress
            v-if="coverage?.population_available && coverage?.confirmed_coverage != null"
            :percentage="Math.min(coverage.confirmed_coverage, 100)"
            :color="rateColor(coverage.confirmed_coverage, 50)"
          />
          <span v-else class="confirmation-dashboard__na">需科目总体金额（TB）</span>
        </div>
      </el-tooltip>
    </div>

    <!-- 指标网格 -->
    <el-table :data="metrics" border size="small" v-if="metrics.length" style="width: 100%">
      <el-table-column prop="account_type" min-width="100">
        <template #header><el-tooltip content="函证对象所属科目类别" placement="top"><span>科目</span></el-tooltip></template>
      </el-table-column>
      <el-table-column prop="total_count" min-width="70" align="center">
        <template #header><el-tooltip content="该科目下函证对象总数" placement="top"><span>总笔数</span></el-tooltip></template>
      </el-table-column>
      <el-table-column prop="replied_count" min-width="70" align="center">
        <template #header><el-tooltip content="已收到对方回函的笔数" placement="top"><span>已回函</span></el-tooltip></template>
      </el-table-column>
      <el-table-column prop="matched_count" min-width="70" align="center">
        <template #header><el-tooltip content="回函金额与账面一致的笔数" placement="top"><span>相符</span></el-tooltip></template>
      </el-table-column>
      <el-table-column min-width="110" align="right">
        <template #header><el-tooltip content="所有函证对象的账面金额合计" placement="top"><span>函证总额</span></el-tooltip></template>
        <template #default="{ row }">{{ fmtAmt(row.total_amount) }}</template>
      </el-table-column>
      <el-table-column min-width="110" align="right">
        <template #header><el-tooltip content="对方已确认金额合计" placement="top"><span>已确认</span></el-tooltip></template>
        <template #default="{ row }">{{ fmtAmt(row.confirmed_amount) }}</template>
      </el-table-column>
      <el-table-column min-width="110" align="right">
        <template #header><el-tooltip content="差异 = 函证总额 − 已确认金额（需调查原因）" placement="top"><span>差异</span></el-tooltip></template>
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
  font-size: var(--wp-font-size, 13px);
  white-space: nowrap;
}
.confirmation-dashboard__na {
  color: var(--el-text-color-placeholder, #a8abb2);
  font-size: 12px;
  font-style: italic;
}
</style>
