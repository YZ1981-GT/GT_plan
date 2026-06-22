<template>
  <div class="alternative-dashboard">
    <el-collapse v-model="expandedPanels">
      <el-collapse-item name="overview" title="替代程序概览">
        <div class="alternative-dashboard__stats">
          <div class="stat-card">
            <div class="stat-card__value">{{ metrics.total_companies }}</div>
            <div class="stat-card__label">总公司数</div>
          </div>
          <div class="stat-card stat-card--success">
            <div class="stat-card__value">{{ metrics.completed_companies }}</div>
            <div class="stat-card__label">已完成</div>
          </div>
          <div class="stat-card" :class="{ 'stat-card--danger': metrics.abnormal_companies > 0 }">
            <div class="stat-card__value">{{ metrics.abnormal_companies }}</div>
            <div class="stat-card__label">有异常</div>
          </div>
          <div class="stat-card">
            <div class="stat-card__value">{{ metrics.completion_rate }}%</div>
            <div class="stat-card__label">完成率</div>
          </div>
        </div>

        <!-- 检查比例分布 -->
        <div v-if="metrics.ratio_distribution.length > 0" class="alternative-dashboard__ratios">
          <div class="ratio-title">检查比例分布</div>
          <div class="ratio-grid">
            <div
              v-for="item in metrics.ratio_distribution"
              :key="item.entity_name"
              class="ratio-item"
              :class="{
                'ratio-item--low': isLowRatio(item.receipt_ratio) || isLowRatio(item.shipment_ratio)
              }"
            >
              <span class="ratio-item__name">{{ item.entity_name }}</span>
              <span class="ratio-item__values">
                收款 {{ formatRatio(item.receipt_ratio) }} /
                出库 {{ formatRatio(item.shipment_ratio) }}
              </span>
            </div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { AlternativeD05Metrics } from './alternativeD05Types'

const props = defineProps<{
  metrics: AlternativeD05Metrics
}>()

const expandedPanels = ref(['overview'])

/** 检查比例 < 30% 视为低 */
function isLowRatio(ratio: number | null): boolean {
  if (ratio === null) return false
  return ratio < 30
}

function formatRatio(val: number | null): string {
  if (val === null) return 'N/A'
  return `${val.toFixed(1)}%`
}
</script>

<style scoped>
.alternative-dashboard {
  margin-bottom: 12px;
}

.alternative-dashboard__stats {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.stat-card {
  flex: 1;
  min-width: 100px;
  padding: 12px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  text-align: center;
}

.stat-card--success { background: var(--el-color-success-light-9); }
.stat-card--danger { background: var(--el-color-danger-light-9); }

.stat-card__value {
  font-size: 20px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.stat-card__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.alternative-dashboard__ratios {
  margin-top: 12px;
}

.ratio-title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--el-text-color-regular);
}

.ratio-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 6px;
}

.ratio-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  border-radius: 3px;
  font-size: 12px;
  background: var(--el-fill-color-lighter);
}

.ratio-item--low {
  background: var(--el-color-warning-light-9);
}

.ratio-item__name {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}

.ratio-item__values {
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
</style>
