<script setup lang="ts">
/**
 * GtOcrTimeline — OCR 任务状态迁移时间线组件（Task 5.5, Wave 4）
 *
 * 显示 OCR Job 的所有状态迁移记录，时间线形式。
 */
import { computed } from 'vue'

export interface TimelineTransition {
  id: string
  from_state: string | null
  to_state: string
  actor_type: string
  error_code: string | null
  error_message: string | null
  created_at: string
}

const props = defineProps<{
  transitions: TimelineTransition[]
  loading?: boolean
}>()

const STATE_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '识别中',
  awaiting_confirmation: '待确认',
  confirmed: '已确认',
  written_back: '已写回',
  failed: '失败',
}

const STATE_COLORS: Record<string, string> = {
  queued: '#909399',
  running: '#409EFF',
  awaiting_confirmation: '#E6A23C',
  confirmed: '#67C23A',
  written_back: '#67C23A',
  failed: '#F56C6C',
}

function stateLabel(state: string | null): string {
  if (!state) return '创建'
  return STATE_LABELS[state] || state
}

function stateColor(state: string): string {
  return STATE_COLORS[state] || '#909399'
}

function formatTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
  return d.toLocaleString('zh-CN', { hour12: false })
}

const sortedTransitions = computed(() => {
  return [...props.transitions].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  )
})
</script>

<template>
  <div class="ocr-timeline">
    <el-timeline v-if="sortedTransitions.length > 0">
      <el-timeline-item
        v-for="t in sortedTransitions"
        :key="t.id"
        :color="stateColor(t.to_state)"
        :timestamp="formatTime(t.created_at)"
        placement="top"
      >
        <div class="timeline-content">
          <span class="state-change">
            {{ stateLabel(t.from_state) }} → {{ stateLabel(t.to_state) }}
          </span>
          <el-tag size="small" :type="t.actor_type === 'service' ? 'info' : ''">
            {{ t.actor_type === 'service' ? '系统' : '人工' }}
          </el-tag>
          <div v-if="t.error_message" class="error-msg">
            <el-text type="danger" size="small">{{ t.error_message }}</el-text>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else-if="!loading" description="暂无状态迁移记录" />
    <el-skeleton v-if="loading" :rows="3" animated />
  </div>
</template>

<style scoped>
.ocr-timeline {
  padding: 12px 0;
}
.timeline-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.state-change {
  font-size: 13px;
  font-weight: 500;
}
.error-msg {
  width: 100%;
  margin-top: 4px;
}
</style>
