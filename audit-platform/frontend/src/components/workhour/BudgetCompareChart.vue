<template>
  <div class="gt-budget-compare">
    <div class="gt-budget-toolbar">
      <el-radio-group v-model="viewMode" size="small">
        <el-radio-button value="cycle">按循环</el-radio-button>
        <el-radio-button value="user">按人员</el-radio-button>
      </el-radio-group>
    </div>

    <div v-if="loading" v-loading="true" style="height: 300px;" />
    <div v-else-if="warning" class="gt-budget-warning">
      <el-empty :description="warning" />
    </div>
    <div v-else ref="chartRef" class="gt-budget-chart" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'

const route = useRoute()
const projectId = route.params.id as string

const viewMode = ref<'cycle' | 'user'>('cycle')
const loading = ref(false)
const warning = ref('')
const chartRef = ref<HTMLElement | null>(null)

interface BudgetData {
  by_cycle: Array<{
    cycle_name: string
    budget_hours: number
    actual_hours: number
    variance_pct: number
    is_over_budget: boolean
  }>
  by_user: Array<{
    user_id: string
    budget_hours: number
    actual_hours: number
    variance_pct: number
    is_over_budget: boolean
  }>
  warning?: string
}

const data = ref<BudgetData>({ by_cycle: [], by_user: [] })

async function loadData() {
  loading.value = true
  warning.value = ''
  try {
    const res = await api.get(`/api/projects/${projectId}/workhours/budget-vs-actual`) as BudgetData
    data.value = res
    if (res.warning) {
      warning.value = res.warning
    }
  } catch (e: any) {
    warning.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartRef.value || warning.value) return

  const items = viewMode.value === 'cycle' ? data.value.by_cycle : data.value.by_user
  if (!items || items.length === 0) {
    warning.value = '暂无数据'
    return
  }

  const categories = items.map((item: any) =>
    viewMode.value === 'cycle' ? item.cycle_name : (item.user_name || item.user_id?.slice(0, 8))
  )
  const budgetValues = items.map((item: any) => item.budget_hours)
  const actualValues = items.map((item: any) => item.actual_hours)

  // Simple bar chart using DOM (ECharts integration placeholder)
  chartRef.value.innerHTML = `
    <div style="padding: 16px;">
      <table style="width: 100%; border-collapse: collapse;">
        <thead>
          <tr style="border-bottom: 2px solid var(--gt-color-border);">
            <th style="text-align: left; padding: 8px;">${viewMode.value === 'cycle' ? '循环' : '人员'}</th>
            <th style="text-align: right; padding: 8px;">预算(h)</th>
            <th style="text-align: right; padding: 8px;">实际(h)</th>
            <th style="text-align: right; padding: 8px;">偏差%</th>
            <th style="text-align: left; padding: 8px;">状态</th>
          </tr>
        </thead>
        <tbody>
          ${items.map((item: any, i: number) => `
            <tr style="border-bottom: 1px solid var(--gt-color-border-light); ${item.is_over_budget ? 'background: #fff2f0;' : ''}">
              <td style="padding: 8px;">${categories[i]}</td>
              <td style="text-align: right; padding: 8px; font-variant-numeric: tabular-nums;">${item.budget_hours}</td>
              <td style="text-align: right; padding: 8px; font-variant-numeric: tabular-nums;">${item.actual_hours}</td>
              <td style="text-align: right; padding: 8px; color: ${item.is_over_budget ? '#D32F2F' : 'inherit'};">
                ${item.variance_pct > 0 ? '+' : ''}${item.variance_pct}%
              </td>
              <td style="padding: 8px;">
                ${item.is_over_budget ? '<span style="color: #D32F2F; font-weight: 600;">⚠ 超预算</span>' : '<span style="color: #4CAF50;">正常</span>'}
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `
}

watch(viewMode, () => {
  nextTick(renderChart)
})

onMounted(async () => {
  await loadData()
  await nextTick()
  renderChart()
})
</script>

<style scoped>
.gt-budget-compare { padding: 16px; }
.gt-budget-toolbar { margin-bottom: 16px; }
.gt-budget-chart { min-height: 200px; }
.gt-budget-warning { padding: 40px; text-align: center; }
</style>
