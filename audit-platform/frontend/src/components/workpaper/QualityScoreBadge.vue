<script setup lang="ts">
/**
 * 质量评分徽章 + 仪表盘视图扩展
 * Sprint 8 Task 8.5
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  score: number
  size?: 'small' | 'default' | 'large'
  showLabel?: boolean
  dimensions?: {
    completeness: number
    consistency: number
    review_status: number
    procedure_rate: number
    self_check_rate: number
  }
}>(), {
  size: 'default',
  showLabel: true,
})

const scoreColor = computed(() => {
  if (props.score >= 80) return '#67c23a'
  if (props.score >= 60) return '#e6a23c'
  if (props.score >= 40) return '#f56c6c'
  return '#909399'
})

const scoreLabel = computed(() => {
  if (props.score >= 80) return '优'
  if (props.score >= 60) return '良'
  if (props.score >= 40) return '中'
  return '差'
})

const badgeSize = computed(() => {
  switch (props.size) {
    case 'small': return 28
    case 'large': return 48
    default: return 36
  }
})

const fontSize = computed(() => {
  switch (props.size) {
    case 'small': return '11px'
    case 'large': return '16px'
    default: return '13px'
  }
})

const dimensionLabels: Record<string, string> = {
  completeness: '完整性',
  consistency: '一致性',
  review_status: '复核状态',
  procedure_rate: '程序完成率',
  self_check_rate: '自检通过率',
}

const dimensionWeights: Record<string, number> = {
  completeness: 30,
  consistency: 25,
  review_status: 20,
  procedure_rate: 15,
  self_check_rate: 10,
}
</script>

<template>
  <el-tooltip
    :disabled="!dimensions"
    placement="bottom"
    :popper-options="{ modifiers: [{ name: 'offset', options: { offset: [0, 8] } }] }"
  >
    <template #content>
      <div v-if="dimensions" class="score-tooltip">
        <div class="tooltip-title">质量评分明细</div>
        <div v-for="(val, key) in dimensions" :key="key" class="dim-row">
          <span class="dim-label">{{ dimensionLabels[key] || key }} ({{ dimensionWeights[key] }}%)</span>
          <el-progress
            :percentage="val"
            :stroke-width="6"
            :show-text="false"
            style="width: 80px"
          />
          <span class="dim-val">{{ val }}</span>
        </div>
      </div>
    </template>

    <div
      class="quality-badge"
      :style="{
        width: `${badgeSize}px`,
        height: `${badgeSize}px`,
        borderColor: scoreColor,
        fontSize,
      }"
    >
      <span class="score-num" :style="{ color: scoreColor }">{{ score }}</span>
      <span v-if="showLabel" class="score-label" :style="{ color: scoreColor }">
        {{ scoreLabel }}
      </span>
    </div>
  </el-tooltip>
</template>

<style scoped>
.quality-badge {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 2px solid;
  border-radius: 50%;
  cursor: default;
  line-height: 1;
}
.score-num {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.score-label {
  font-size: 9px;
  margin-top: 1px;
}
.score-tooltip {
  min-width: 200px;
}
.tooltip-title {
  font-weight: 600;
  margin-bottom: 8px;
  font-size: 13px;
}
.dim-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 12px;
}
.dim-label {
  width: 110px;
  white-space: nowrap;
}
.dim-val {
  width: 24px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
