<template>
  <div v-if="trimmingOverview?.available" class="trimming-overview">
    <!-- 汇总统计 -->
    <div class="trimming-summary">
      <div class="summary-item">
        <span class="summary-label">总裁剪数</span>
        <span class="summary-value">{{ trimmingOverview.trimmed_count }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">总程序数</span>
        <span class="summary-value">{{ trimmingOverview.total_procedures }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">裁剪率</span>
        <span class="summary-value">{{ formatRate(trimmingOverview.trim_rate) }}%</span>
      </div>
    </div>

    <!-- 按循环分布 -->
    <div class="cycle-distribution">
      <div
        v-for="item in trimmingOverview.by_cycle"
        :key="item.cycle"
        class="cycle-row"
        :class="{ 'cycle-row--warning': item.warning }"
      >
        <div class="cycle-info">
          <span class="cycle-name">{{ item.cycle }}</span>
          <el-tag
            v-if="item.warning"
            type="warning"
            size="small"
            effect="light"
          >
            &gt;50%
          </el-tag>
        </div>
        <el-progress
          :percentage="Math.min(item.rate, 100)"
          :stroke-width="14"
          :color="item.warning ? '#e6a23c' : '#409eff'"
          :format="() => `${item.trimmed}/${item.total}`"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TrimmingData } from '@/composables/useDashboardData'

interface Props {
  trimmingOverview: TrimmingData | null
}

defineProps<Props>()

/** 格式化百分比，保留一位小数 */
function formatRate(rate: number): string {
  return rate.toFixed(1)
}
</script>

<style scoped>
.trimming-overview {
  width: 100%;
}

.trimming-summary {
  display: flex;
  justify-content: space-around;
  margin-bottom: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.summary-label {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.summary-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}

.cycle-distribution {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cycle-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.cycle-row--warning {
  background-color: rgba(230, 162, 60, 0.08);
  border-left: 3px solid #e6a23c;
}

.cycle-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cycle-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular, #606266);
}
</style>
