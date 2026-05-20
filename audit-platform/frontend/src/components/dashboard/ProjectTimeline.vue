<template>
  <div class="project-timeline">
    <el-steps
      :active="activeStep"
      finish-status="success"
      process-status="process"
      align-center
    >
      <el-step
        v-for="(stage, index) in stageList"
        :key="stage.key"
        :title="stage.label"
        :status="getStepStatus(index)"
      >
        <template #description>
          <div class="stage-description">
            <template v-if="stage.data?.status === 'completed' && stage.data.completed_at">
              <span class="stage-time">{{ formatTime(stage.data.completed_at) }}</span>
            </template>
            <template v-else-if="stage.data?.status === 'current' && stage.data.entered_at">
              <span class="stage-time stage-time--current">{{ formatTime(stage.data.entered_at) }} 进入</span>
            </template>
            <!-- 执行阶段当前时显示全循环完成率摘要 -->
            <template v-if="stage.key === 'execution' && stage.data?.status === 'current' && stage.data.summary">
              <div class="stage-summary">{{ stage.data.summary }}</div>
            </template>
          </div>
        </template>
      </el-step>
    </el-steps>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TimelineData, StageItem } from '@/composables/useDashboardData'

interface Props {
  timeline: TimelineData | null
}

const props = defineProps<Props>()

/** 四阶段定义：key → 中文标签 */
const STAGE_DEFS = [
  { key: 'planning', label: '计划' },
  { key: 'execution', label: '执行' },
  { key: 'review', label: '复核' },
  { key: 'reporting', label: '报告' },
] as const

/** 合并后端 stages 数据到固定四阶段 */
const stageList = computed(() => {
  return STAGE_DEFS.map((def) => {
    const data = props.timeline?.stages?.find((s) => s.name === def.key) ?? null
    return { ...def, data }
  })
})

/** 当前激活步骤索引（el-steps 的 active 属性） */
const activeStep = computed(() => {
  if (!props.timeline) return 0
  const idx = STAGE_DEFS.findIndex((d) => d.key === props.timeline!.current_stage)
  return idx >= 0 ? idx : 0
})

/**
 * 获取每个步骤的状态
 * - completed → 'success'
 * - current → 'process'
 * - pending → 'wait'
 */
function getStepStatus(index: number): 'success' | 'process' | 'wait' {
  const stage = stageList.value[index]
  if (!stage.data) {
    return index < activeStep.value ? 'success' : index === activeStep.value ? 'process' : 'wait'
  }
  switch (stage.data.status) {
    case 'completed':
      return 'success'
    case 'current':
      return 'process'
    default:
      return 'wait'
  }
}

/** 格式化时间为简短日期 */
function formatTime(isoStr: string): string {
  try {
    const date = new Date(isoStr)
    const month = date.getMonth() + 1
    const day = date.getDate()
    return `${month}/${day}`
  } catch {
    return ''
  }
}
</script>

<style scoped>
.project-timeline {
  width: 100%;
  padding: 8px 0;
}

.stage-description {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.stage-time {
  font-size: 12px;
  color: var(--el-color-success, #67c23a);
}

.stage-time--current {
  color: var(--el-color-primary, #4b2d77);
}

.stage-summary {
  font-size: 11px;
  color: var(--el-text-color-secondary, #909399);
  max-width: 120px;
  text-align: center;
  line-height: 1.3;
  word-break: break-all;
}
</style>
