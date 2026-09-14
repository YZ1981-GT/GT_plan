<template>
  <div class="gt-wh-stats">
    <!-- 顶部汇总卡片 -->
    <div class="gt-wh-stats__cards">
      <el-card shadow="never" class="gt-wh-stats__card">
        <div class="gt-wh-stats__card-label">本周总工时</div>
        <div class="gt-wh-stats__card-value">{{ weekTotal }}h</div>
      </el-card>
      <el-card shadow="never" class="gt-wh-stats__card">
        <div class="gt-wh-stats__card-label">本月总工时</div>
        <div class="gt-wh-stats__card-value">{{ monthTotal }}h</div>
      </el-card>
      <el-card shadow="never" class="gt-wh-stats__card">
        <div class="gt-wh-stats__card-label">本月加班天数</div>
        <div class="gt-wh-stats__card-value" :class="{ 'gt-wh-stats__card-value--warn': overtimeDays > 5 }">
          {{ overtimeDays }}天
        </div>
      </el-card>
      <el-card shadow="never" class="gt-wh-stats__card">
        <div class="gt-wh-stats__card-label">日均工时</div>
        <div class="gt-wh-stats__card-value">{{ dailyAvg }}h</div>
      </el-card>
    </div>

    <!-- 周工时分布(近4周) -->
    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>
        <span style="font-weight: 600; font-size: 14px;">近4周工时分布</span>
      </template>
      <div v-if="loading" v-loading="true" style="height: 160px;" />
      <div v-else-if="weeklyData.length === 0" style="padding: 32px; text-align: center; color: var(--gt-color-text-secondary);">
        暂无工时数据
      </div>
      <div v-else class="gt-wh-stats__weekly">
        <div v-for="week in weeklyData" :key="week.label" class="gt-wh-stats__week-row">
          <span class="gt-wh-stats__week-label">{{ week.label }}</span>
          <div class="gt-wh-stats__week-bar-bg">
            <div
              class="gt-wh-stats__week-bar"
              :style="{ width: `${Math.min(week.pct, 100)}%`, background: week.hours > 40 ? '#E53935' : 'var(--el-color-primary)' }"
            />
          </div>
          <span class="gt-wh-stats__week-hours">{{ week.hours }}h</span>
        </div>
      </div>
    </el-card>

    <!-- 按项目分布 -->
    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>
        <span style="font-weight: 600; font-size: 14px;">本月按项目分布</span>
      </template>
      <div v-if="projectData.length === 0" style="padding: 32px; text-align: center; color: var(--gt-color-text-secondary);">
        暂无数据
      </div>
      <el-table v-else :data="projectData" size="small" :show-header="true" style="width: 100%;">
        <el-table-column prop="project_name" label="项目" min-width="180" />
        <el-table-column prop="hours" label="工时(h)" width="100" align="right">
          <template #default="{ row }">
            <span style="font-variant-numeric: tabular-nums;">{{ row.hours }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占比" width="160">
          <template #default="{ row }">
            <el-progress :percentage="row.pct" :stroke-width="8" :show-text="false" />
          </template>
        </el-table-column>
        <el-table-column prop="pct" label="%" width="60" align="right">
          <template #default="{ row }">
            {{ row.pct }}%
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 日历热力图（近30天） -->
    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>
        <span style="font-weight: 600; font-size: 14px;">近30天工时热力图</span>
      </template>
      <div v-if="loading" v-loading="true" style="height: 80px;" />
      <div v-else class="gt-wh-heatmap">
        <div class="gt-wh-heatmap__grid">
          <div
            v-for="day in heatmapDays"
            :key="day.date"
            class="gt-wh-heatmap__cell"
            :class="day.level"
            :title="`${day.date}: ${day.hours}h`"
          />
        </div>
        <div class="gt-wh-heatmap__legend">
          <span class="gt-wh-heatmap__legend-label">少</span>
          <div class="gt-wh-heatmap__cell level-0" />
          <div class="gt-wh-heatmap__cell level-1" />
          <div class="gt-wh-heatmap__cell level-2" />
          <div class="gt-wh-heatmap__cell level-3" />
          <div class="gt-wh-heatmap__cell level-4" />
          <span class="gt-wh-heatmap__legend-label">多</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { listEntries, getMyAssignments } from '@/services/staffApi'
import type { WorkHourEntryRecord } from '@/services/staffApi'

const props = defineProps<{ staffId: string }>()

const loading = ref(false)
const records = ref<WorkHourEntryRecord[]>([])

// ── 计算区间 ──
function getMonthRange(): [string, string] {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), 1)
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0)
  return [fmt(start), fmt(end)]
}

function get4WeeksRange(): [string, string] {
  const now = new Date()
  const start = new Date(now)
  start.setDate(now.getDate() - 27) // 近28天
  return [fmt(start), fmt(now)]
}

function getWeekRange(): [string, string] {
  const now = new Date()
  const dow = now.getDay()
  const mon = new Date(now)
  mon.setDate(now.getDate() - (dow === 0 ? 6 : dow - 1))
  const sun = new Date(mon)
  sun.setDate(mon.getDate() + 6)
  return [fmt(mon), fmt(sun)]
}

function fmt(d: Date): string {
  return d.toISOString().slice(0, 10)
}

// ── 汇总指标 ──
const weekTotal = computed(() => {
  const [start, end] = getWeekRange()
  return sumHours(records.value.filter(r => r.date >= start && r.date <= end))
})

const monthTotal = computed(() => {
  const [start, end] = getMonthRange()
  return sumHours(records.value.filter(r => r.date >= start && r.date <= end))
})

const overtimeDays = computed(() => {
  const [start, end] = getMonthRange()
  const byDay: Record<string, number> = {}
  for (const r of records.value) {
    if (r.date >= start && r.date <= end) {
      byDay[r.date] = (byDay[r.date] || 0) + r.hours
    }
  }
  return Object.values(byDay).filter(h => h > 8).length
})

const dailyAvg = computed(() => {
  const [start, end] = getMonthRange()
  const filtered = records.value.filter(r => r.date >= start && r.date <= end)
  const days = new Set(filtered.map(r => r.date)).size
  if (days === 0) return 0
  return +(sumHours(filtered) / days).toFixed(1)
})

// ── 近4周柱图数据 ──
const weeklyData = computed(() => {
  const weeks: Array<{ label: string; hours: number; pct: number }> = []
  const now = new Date()
  for (let w = 3; w >= 0; w--) {
    const end = new Date(now)
    end.setDate(now.getDate() - w * 7)
    const start = new Date(end)
    start.setDate(end.getDate() - 6)
    const startStr = fmt(start)
    const endStr = fmt(end)
    const hours = sumHours(records.value.filter(r => r.date >= startStr && r.date <= endStr))
    weeks.push({
      label: `${start.getMonth() + 1}/${start.getDate()}-${end.getMonth() + 1}/${end.getDate()}`,
      hours,
      pct: Math.round((hours / 50) * 100),
    })
  }
  return weeks
})

// ── 按项目分布 ──
const projectData = computed(() => {
  const [start, end] = getMonthRange()
  const byProject: Record<string, { name: string; hours: number }> = {}
  for (const r of records.value) {
    if (r.date >= start && r.date <= end) {
      const key = r.project_id
      if (!byProject[key]) byProject[key] = { name: key.slice(0, 8), hours: 0 }
      byProject[key].hours += r.hours
    }
  }
  const items = Object.values(byProject).sort((a, b) => b.hours - a.hours)
  const total = items.reduce((s, i) => s + i.hours, 0)
  return items.map(i => ({
    project_name: i.name,
    hours: +i.hours.toFixed(1),
    pct: total > 0 ? Math.round(i.hours / total * 100) : 0,
  }))
})

function sumHours(arr: WorkHourEntryRecord[]): number {
  return +(arr.reduce((s, r) => s + r.hours, 0)).toFixed(1)
}

// ── 热力图数据（近30天） ──
const heatmapDays = computed(() => {
  const now = new Date()
  const days: Array<{ date: string; hours: number; level: string }> = []
  for (let i = 29; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(now.getDate() - i)
    const dateStr = fmt(d)
    const dayHours = records.value
      .filter(r => r.date === dateStr)
      .reduce((s, r) => s + r.hours, 0)
    let level = 'level-0'
    if (dayHours > 0 && dayHours <= 2) level = 'level-1'
    else if (dayHours > 2 && dayHours <= 4) level = 'level-2'
    else if (dayHours > 4 && dayHours <= 8) level = 'level-3'
    else if (dayHours > 8) level = 'level-4'
    days.push({ date: dateStr, hours: +dayHours.toFixed(1), level })
  }
  return days
})

// ── 加载 ──
onMounted(async () => {
  if (!props.staffId) return
  loading.value = true
  try {
    const [start] = get4WeeksRange()
    const now = fmt(new Date())
    // 从所有参与项目加载 entries
    const assignments = await getMyAssignments()
    const allEntries: WorkHourEntryRecord[] = []
    for (const a of assignments) {
      try {
        const entries = await listEntries(a.project_id, { start_date: start, end_date: now })
        allEntries.push(...entries)
      } catch { /* 静默 */ }
    }
    records.value = allEntries
  } catch { /* 静默 */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.gt-wh-stats__cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.gt-wh-stats__card {
  text-align: center;
}
.gt-wh-stats__card-label {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #666);
  margin-bottom: 4px;
}
.gt-wh-stats__card-value {
  font-size: 24px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--gt-color-text-primary, #1a1a1a);
}
.gt-wh-stats__card-value--warn {
  color: #E53935;
}

.gt-wh-stats__weekly {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.gt-wh-stats__week-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.gt-wh-stats__week-label {
  width: 90px;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #666);
  flex-shrink: 0;
}
.gt-wh-stats__week-bar-bg {
  flex: 1;
  height: 16px;
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 4px;
  overflow: hidden;
}
.gt-wh-stats__week-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}
.gt-wh-stats__week-hours {
  width: 50px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 768px) {
  .gt-wh-stats__cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 热力图 */
.gt-wh-heatmap__grid {
  display: grid;
  grid-template-columns: repeat(30, 1fr);
  gap: 3px;
}
.gt-wh-heatmap__cell {
  width: 14px;
  height: 14px;
  border-radius: 2px;
  background: var(--el-fill-color-lighter, #f5f7fa);
}
.gt-wh-heatmap__cell.level-0 { background: #ebedf0; }
.gt-wh-heatmap__cell.level-1 { background: #d6e685; }
.gt-wh-heatmap__cell.level-2 { background: #8cc665; }
.gt-wh-heatmap__cell.level-3 { background: #44a340; }
.gt-wh-heatmap__cell.level-4 { background: #1e6823; }
.gt-wh-heatmap__legend {
  display: flex;
  align-items: center;
  gap: 3px;
  margin-top: 8px;
  justify-content: flex-end;
}
.gt-wh-heatmap__legend-label {
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #999);
  margin: 0 4px;
}
</style>
