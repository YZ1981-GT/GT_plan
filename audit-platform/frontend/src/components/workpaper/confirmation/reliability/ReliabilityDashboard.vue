<template>
  <div class="reliability-dashboard">
    <el-collapse v-model="expanded">
      <el-collapse-item title="可靠性验证概览" name="overview">
        <!-- 指标卡片 -->
        <div class="reliability-dashboard__cards">
          <div class="reliability-dashboard__card">
            <div class="reliability-dashboard__card-value">{{ metrics.total_count }}</div>
            <div class="reliability-dashboard__card-label">总行数</div>
          </div>
          <div class="reliability-dashboard__card">
            <div
              class="reliability-dashboard__card-value"
              :class="{ 'reliability-dashboard__card-value--warn': metrics.verified_rate < 100 }"
            >
              {{ metrics.verified_rate }}%
            </div>
            <div class="reliability-dashboard__card-label">已验证率</div>
          </div>
          <div class="reliability-dashboard__card">
            <div class="reliability-dashboard__card-value reliability-dashboard__card-value--ok">
              {{ metrics.reliable_count }}
            </div>
            <div class="reliability-dashboard__card-label">可靠</div>
          </div>
          <div class="reliability-dashboard__card">
            <div class="reliability-dashboard__card-value reliability-dashboard__card-value--warn">
              {{ metrics.partial_count }}
            </div>
            <div class="reliability-dashboard__card-label">部分可靠</div>
          </div>
          <div
            class="reliability-dashboard__card"
            :class="{ 'reliability-dashboard__card--danger': metrics.unreliable_count > 0 }"
          >
            <div class="reliability-dashboard__card-value">{{ metrics.unreliable_count }}</div>
            <div class="reliability-dashboard__card-label">不可靠</div>
          </div>
          <div class="reliability-dashboard__card">
            <div class="reliability-dashboard__card-value">{{ metrics.original_returned_count }}</div>
            <div class="reliability-dashboard__card-label">已寄回原件</div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- 质量警示 -->
    <div v-if="alerts.length" class="reliability-dashboard__alerts">
      <el-alert
        v-for="(alert, idx) in alerts"
        :key="idx"
        :title="alert.title"
        :type="alert.type"
        :closable="false"
        show-icon
        class="reliability-dashboard__alert-item"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ReliabilityMetrics } from './reliabilityTypes'

const props = defineProps<{
  metrics: ReliabilityMetrics
}>()

const expanded = ref<string[]>(['overview'])

// ─── 质量警示 ────────────────────────────────────────────────────────────────

interface AlertItem {
  title: string
  type: 'warning' | 'error' | 'info'
}

const alerts = computed<AlertItem[]>(() => {
  const list: AlertItem[] = []

  const unverified = props.metrics.total_count - props.metrics.verified_count - props.metrics.original_returned_count
  if (unverified > 0) {
    list.push({
      title: `${unverified} 笔电子回函尚未完成验证（结论未填写）`,
      type: 'warning',
    })
  }

  if (props.metrics.unreliable_count > 0) {
    list.push({
      title: `${props.metrics.unreliable_count} 笔回函被评定为"不可靠"，请评估是否需要替代程序或追加审计证据`,
      type: 'error',
    })
  }

  if (props.metrics.partial_count > 0) {
    list.push({
      title: `${props.metrics.partial_count} 笔为"部分可靠需补充"，请确认补充程序是否已执行`,
      type: 'info',
    })
  }

  return list
})
</script>

<style scoped>
.reliability-dashboard__cards {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.reliability-dashboard__card {
  flex: 1;
  min-width: 100px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  text-align: center;
}

.reliability-dashboard__card--danger {
  background: var(--el-color-danger-light-9);
  border: 1px solid var(--el-color-danger-light-5);
}

.reliability-dashboard__card-value {
  font-size: 20px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-primary);
}

.reliability-dashboard__card-value--ok {
  color: var(--el-color-success);
}

.reliability-dashboard__card-value--warn {
  color: var(--el-color-warning);
}

.reliability-dashboard__card-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.reliability-dashboard__alerts {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.reliability-dashboard__alert-item {
  margin: 0;
}
</style>
