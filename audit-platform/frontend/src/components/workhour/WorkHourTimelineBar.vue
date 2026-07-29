<template>
  <div class="wh-timeline" v-loading="loading">
    <div class="wh-timeline__header">
      <span class="wh-timeline__title">📊 时间轴</span>
      <span class="wh-timeline__total">共 {{ totalHours }}h</span>
    </div>
    <div class="wh-timeline__bar">
      <!-- 时间刻度 -->
      <div class="wh-timeline__ticks">
        <span v-for="h in hours" :key="h" class="wh-timeline__tick" :style="{ left: tickPosition(h) + '%' }">
          {{ h }}:00
        </span>
      </div>
      <!-- 条形区域 -->
      <div class="wh-timeline__track">
        <div
          v-for="(item, idx) in timelineItems"
          :key="item.id || idx"
          class="wh-timeline__block"
          :style="blockStyle(item)"
          :title="blockTitle(item)"
          :class="{ 'wh-timeline__block--auto': item.source === 'auto_collected', 'wh-timeline__block--draft': item.status === 'draft' }"
        >
          <span class="wh-timeline__block-label" v-if="blockWidth(item) > 8">
            {{ item.activity_type || item.description || '' }}
          </span>
        </div>
      </div>
    </div>
    <!-- 图例 -->
    <div class="wh-timeline__legend" v-if="timelineItems.length">
      <span class="wh-timeline__legend-item" v-for="(item, idx) in timelineItems" :key="idx">
        <span class="wh-timeline__legend-dot" :style="{ background: getColor(idx) }"></span>
        {{ item.activity_type || '工作' }} {{ item.hours }}h
        <el-tag v-if="item.source === 'auto_collected'" size="small" type="info" effect="plain">采集</el-tag>
      </span>
    </div>
    <div v-if="!loading && !timelineItems.length" class="wh-timeline__empty">
      当日暂无工时数据
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'

const props = defineProps<{
  date: string // YYYY-MM-DD
}>()

const loading = ref(false)
const totalHours = ref(0)
const timelineItems = ref<any[]>([])

// 08:00 - 20:00
const hours = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
const START_MINUTES = 480 // 08:00
const END_MINUTES = 1200  // 20:00
const RANGE = END_MINUTES - START_MINUTES // 720 min

const COLORS = [
  '#4b2d77', '#1890ff', '#52c41a', '#faad14', '#f5222d',
  '#722ed1', '#13c2c2', '#eb2f96', '#fa8c16', '#2f54eb',
]

function getColor(idx: number) {
  return COLORS[idx % COLORS.length]
}

function tickPosition(h: number) {
  return ((h * 60 - START_MINUTES) / RANGE) * 100
}

function parseTime(t: string): number {
  const [hh, mm] = t.split(':').map(Number)
  return hh * 60 + (mm || 0)
}

function blockStyle(item: any) {
  const slots = item.time_slots?.[0]
  if (!slots) return { display: 'none' }
  const start = Math.max(parseTime(slots.start), START_MINUTES)
  const end = Math.min(parseTime(slots.end), END_MINUTES)
  const left = ((start - START_MINUTES) / RANGE) * 100
  const width = ((end - start) / RANGE) * 100
  const idx = timelineItems.value.indexOf(item)
  return {
    left: `${Math.max(0, left)}%`,
    width: `${Math.max(1, width)}%`,
    background: getColor(idx),
  }
}

function blockWidth(item: any) {
  const slots = item.time_slots?.[0]
  if (!slots) return 0
  const start = parseTime(slots.start)
  const end = parseTime(slots.end)
  return ((end - start) / RANGE) * 100
}

function blockTitle(item: any) {
  const slots = item.time_slots?.[0]
  const time = slots ? `${slots.start}-${slots.end}` : ''
  return `${item.activity_type || '工作'} ${item.hours}h ${time}\n${item.description || ''}`
}

async function loadTimeline() {
  if (!props.date) return
  loading.value = true
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.get('/api/timeline', { params: { target_date: props.date } }) as any
    totalHours.value = res?.total_hours || 0
    timelineItems.value = res?.items || []
  } catch {
    timelineItems.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.date, () => loadTimeline())
onMounted(loadTimeline)

defineExpose({ reload: loadTimeline })
</script>

<style scoped>
.wh-timeline { margin: 12px 0; padding: 12px; background: #fafafa; border-radius: 8px; border: 1px solid #f0f0f0; }
.wh-timeline__header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.wh-timeline__title { font-weight: 600; font-size: 13px; }
.wh-timeline__total { font-size: 12px; color: #666; }
.wh-timeline__bar { position: relative; height: 40px; margin: 8px 0; }
.wh-timeline__ticks { position: relative; height: 16px; }
.wh-timeline__tick { position: absolute; font-size: 10px; color: #999; transform: translateX(-50%); }
.wh-timeline__track { position: relative; height: 24px; background: #e8e8e8; border-radius: 4px; overflow: hidden; }
.wh-timeline__block {
  position: absolute; top: 2px; height: 20px; border-radius: 3px; opacity: 0.85;
  cursor: pointer; transition: opacity 0.2s; display: flex; align-items: center; padding: 0 4px; overflow: hidden;
}
.wh-timeline__block:hover { opacity: 1; }
.wh-timeline__block--draft { opacity: 0.6; border: 1px dashed #999; }
.wh-timeline__block-label { font-size: 10px; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wh-timeline__legend { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; font-size: 12px; }
.wh-timeline__legend-item { display: flex; align-items: center; gap: 4px; }
.wh-timeline__legend-dot { width: 8px; height: 8px; border-radius: 50%; }
.wh-timeline__empty { text-align: center; color: #999; font-size: 12px; padding: 8px; }
</style>
