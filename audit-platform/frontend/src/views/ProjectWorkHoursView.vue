<template>
  <div class="project-work-hours-view">
    <!-- Header: title + 新增按钮 -->
    <div class="project-work-hours-view__header">
      <h2 class="project-work-hours-view__title">项目工时(细粒度)</h2>
      <el-button type="primary" @click="openCreateDialog">新增工时</el-button>
    </div>

    <!-- 顶部汇总卡 -->
    <div class="project-work-hours-view__summary">
      <el-card shadow="never" class="summary-card">
        <div class="summary-card__label">总工时</div>
        <div class="summary-card__value">{{ summary.total.toFixed(1) }}h</div>
      </el-card>

      <el-card shadow="never" class="summary-card">
        <div class="summary-card__label">按循环分布</div>
        <div class="summary-card__value summary-card__tags">
          <el-tag
            v-for="item in topCycles"
            :key="item.cycle"
            size="small"
            type="info"
          >
            {{ item.cycle }}: {{ item.hours.toFixed(1) }}h
          </el-tag>
          <span v-if="topCycles.length === 0" class="summary-card__empty">暂无数据</span>
        </div>
      </el-card>

      <el-card shadow="never" class="summary-card">
        <div class="summary-card__label">本周填报天数</div>
        <div class="summary-card__value">{{ currentWeekDays }} 天</div>
      </el-card>
    </div>

    <!-- 工时条目列表 -->
    <WorkHourEntryList
      ref="entryListRef"
      :project-id="projectId"
      @edit="handleEdit"
    />

    <!-- 填报弹窗 -->
    <WorkHourEntryDialog
      v-model="dialogVisible"
      :project-id="projectId"
      :entry-id="editingEntryId"
      @saved="handleSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import WorkHourEntryList from '@/components/workhour/WorkHourEntryList.vue'
import WorkHourEntryDialog from '@/components/workhour/WorkHourEntryDialog.vue'
import { getEntrySummary } from '@/services/staffApi'
import { handleApiError } from '@/utils/errorHandler'

// ── 路由参数 ──
const route = useRoute()
const projectId = computed(() => route.params.projectId as string)

// ── 汇总数据 ──
const summary = ref<{ by_day: Record<string, number>; by_cycle: Record<string, number>; total: number }>({
  by_day: {},
  by_cycle: {},
  total: 0,
})

// Top 3 cycles by hours descending
const topCycles = computed(() => {
  const entries = Object.entries(summary.value.by_cycle)
    .map(([cycle, hours]) => ({ cycle, hours }))
    .sort((a, b) => b.hours - a.hours)
  return entries.slice(0, 3)
})

// 本周填报天数: count unique days within current week (Mon~Sun)
const currentWeekDays = computed(() => {
  const now = new Date()
  const dayOfWeek = now.getDay() || 7 // 1=Mon ... 7=Sun
  const monday = new Date(now)
  monday.setHours(0, 0, 0, 0)
  monday.setDate(now.getDate() - dayOfWeek + 1)

  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  sunday.setHours(23, 59, 59, 999)

  let count = 0
  for (const dateStr of Object.keys(summary.value.by_day)) {
    const d = new Date(dateStr + 'T00:00:00')
    if (d >= monday && d <= sunday) {
      count++
    }
  }
  return count
})

async function loadSummary() {
  try {
    summary.value = await getEntrySummary(projectId.value)
  } catch (e: any) {
    handleApiError(e, '加载工时汇总')
  }
}

// ── Dialog 控制 ──
const dialogVisible = ref(false)
const editingEntryId = ref<string | undefined>(undefined)
const entryListRef = ref<InstanceType<typeof WorkHourEntryList> | null>(null)

function openCreateDialog() {
  editingEntryId.value = undefined
  dialogVisible.value = true
}

function handleEdit(entryId: string) {
  editingEntryId.value = entryId
  dialogVisible.value = true
}

function handleSaved() {
  entryListRef.value?.reload()
  loadSummary()
}

// ── 生命周期 ──
onMounted(() => {
  loadSummary()
})
</script>

<style scoped>
.project-work-hours-view {
  padding: 20px;
  font-size: 13px;
}

.project-work-hours-view__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.project-work-hours-view__title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.project-work-hours-view__summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 20px;
}

.summary-card {
  text-align: center;
}

.summary-card__label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.summary-card__value {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.summary-card__tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
  font-weight: normal;
}

.summary-card__empty {
  font-size: 13px;
  font-weight: normal;
  color: #c0c4cc;
}
</style>
