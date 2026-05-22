<template>
  <div class="graph-legend" :class="{ collapsed }">
    <div class="legend-header" @click="collapsed = !collapsed">
      <span class="legend-title">图例</span>
      <span class="legend-toggle">{{ collapsed ? '展开' : '收起' }}</span>
    </div>
    <div v-if="!collapsed" class="legend-body">
      <div class="legend-section">
        <div class="legend-section-title">节点 · 循环</div>
        <div class="legend-grid">
          <div
            v-for="cycle in nodeCycles"
            :key="cycle"
            class="legend-item"
            :title="CYCLE_DISPLAY_NAME[cycle] ?? cycle"
          >
            <span
              class="legend-dot"
              :style="{ backgroundColor: cycleColor(cycle) }"
            ></span>
            <span class="legend-label">{{ CYCLE_DISPLAY_NAME[cycle] ?? cycle }}</span>
          </div>
        </div>
      </div>
      <div class="legend-section">
        <div class="legend-section-title">边 · 严重度</div>
        <div class="legend-grid">
          <div
            v-for="sev in severities"
            :key="sev"
            class="legend-item"
          >
            <span
              class="legend-line"
              :style="{
                backgroundColor: severityColor(sev),
                height: severityWidth(sev) + 'px',
              }"
            ></span>
            <span class="legend-label">{{ SEVERITY_DISPLAY_NAME[sev] ?? sev }}</span>
          </div>
        </div>
      </div>
      <div class="legend-section">
        <div class="legend-section-title">状态</div>
        <div class="legend-item">
          <span class="legend-dot stale-dot"></span>
          <span class="legend-label">过期 (stale)</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * GraphLegend.vue — 联动全景图图例面板（右下角固定）
 *
 * Validates: Requirements 3.4, 4.4
 */
import { ref, computed } from 'vue'
import {
  CYCLE_DISPLAY_NAME,
  SEVERITY_DISPLAY_NAME,
  cycleColor,
  severityColor,
  severityWidth,
} from './colorMaps'

const props = defineProps<{
  /** 当前图中实际出现的 cycle 集合，未传则展示全部 */
  visibleCycles?: string[]
}>()

const collapsed = ref(false)

const nodeCycles = computed(() => {
  // 默认顺序：业务循环 D~N → 辅助 A/B/C/S → 报表 → 附注 → 模块 → 其他
  const order = [
    'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N',
    'A', 'B', 'C', 'S',
    'report', 'note', 'module', 'other',
  ]
  if (!props.visibleCycles || props.visibleCycles.length === 0) return order
  const visible = new Set(props.visibleCycles)
  return order.filter(c => visible.has(c))
})

const severities = ['blocking', 'required', 'warning', 'recommended', 'info']
</script>

<style scoped>
.graph-legend {
  position: absolute;
  right: 16px;
  bottom: 16px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  max-width: 280px;
  z-index: 5;
  user-select: none;
}

.legend-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  font-weight: 600;
  color: #333;
}

.legend-toggle {
  font-size: 11px;
  color: #888;
  font-weight: normal;
}

.legend-body {
  margin-top: 8px;
}

.legend-section {
  margin-bottom: 8px;
}

.legend-section:last-child {
  margin-bottom: 0;
}

.legend-section-title {
  font-size: 11px;
  color: #666;
  font-weight: 600;
  margin-bottom: 4px;
}

.legend-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 8px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-line {
  display: inline-block;
  width: 16px;
  flex-shrink: 0;
  border-radius: 1px;
}

.legend-label {
  color: #444;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stale-dot {
  background: transparent;
  border: 2px dashed #FDD835;
  width: 12px;
  height: 12px;
}
</style>
