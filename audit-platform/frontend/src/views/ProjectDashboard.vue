<template>
  <div class="gt-proj-dash gt-fade-in">
    <div class="gt-pd-header">
      <h2 class="gt-page-title">项目看板</h2>
      <el-button size="small" @click="refresh" :loading="loading">刷新</el-button>
    </div>
    <el-row :gutter="16">
      <el-col :span="8">
        <div class="gt-pd-card">
          <h4>项目进度</h4>
          <v-chart v-if="progressOption" :option="progressOption" autoresize style="height: 200px" />
          <el-empty v-else :image-size="60" description="暂无数据" />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="gt-pd-card">
          <h4>底稿完成度</h4>
          <div v-if="wpProgress">
            <div v-for="(v, k) in wpProgress.by_cycle" :key="k" style="margin-bottom: 8px">
              <span style="display: inline-block; width: 30px; font-weight: 600">{{ k }}</span>
              <el-progress :percentage="v.total ? Math.round((v.prepared + (v.reviewed||0) + (v.archived||0)) / v.total * 100) : 0"
                :stroke-width="12" style="flex: 1" />
            </div>
            <div style="margin-top: 12px; font-size: 13px; color: #666">整体完成率：{{ wpProgress.rate }}%</div>
          </div>
          <el-empty v-else :image-size="60" description="暂无底稿数据" />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="gt-pd-card">
          <h4>团队工作量</h4>
          <v-chart v-if="teamOption" :option="teamOption" autoresize style="height: 200px" />
          <el-empty v-else :image-size="60" description="暂无工时数据" />
        </div>
      </el-col>
    </el-row>
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="12">
        <div class="gt-pd-card">
          <h4>关键待办 Top10</h4>
          <el-table :data="overdue" border size="small" max-height="250" empty-text="无逾期底稿">
            <el-table-column prop="wp_code" label="编号" width="100" />
            <el-table-column prop="wp_name" label="名称" min-width="180" />
            <el-table-column prop="overdue_days" label="逾期天数" width="90" align="right" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="gt-pd-card">
          <h4>数据一致性</h4>
          <div v-if="consistency">
            <div v-for="c in consistency.checks" :key="c.check_name" style="margin-bottom: 6px">
              <span>{{ c.passed ? '✅' : '⚠️' }} {{ c.check_name }}</span>
            </div>
          </div>
          <el-empty v-else :image-size="60" description="点击刷新加载" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { use } from 'echarts/core'
import { PieChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import http from '@/utils/http'

use([PieChart, BarChart, TitleComponent, TooltipComponent, GridComponent, CanvasRenderer])

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const loading = ref(false)
const wpProgress = ref<any>(null)
const overdue = ref<any[]>([])
const consistency = ref<any>(null)
const progressOption = ref<any>(null)
const teamOption = ref<any>(null)

async function refresh() {
  loading.value = true
  try {
    const [wp, od, con, wh] = await Promise.all([
      http.get(`/api/projects/${projectId.value}/workpapers/progress`).then(r => r.data.data ?? r.data).catch(() => null),
      http.get(`/api/projects/${projectId.value}/workpapers/overdue?days=7`).then(r => r.data.data ?? r.data).catch(() => []),
      http.get(`/api/projects/${projectId.value}/consistency-check?year=2025`).then(r => r.data.data ?? r.data).catch(() => null),
      http.get(`/api/projects/${projectId.value}/work-hours`).then(r => r.data.data ?? r.data).catch(() => []),
    ])
    wpProgress.value = wp
    overdue.value = Array.isArray(od) ? od : []
    consistency.value = con
    if (wp) {
      const done = wp.done || 0, total = wp.total || 1
      progressOption.value = {
        series: [{ type: 'pie', radius: ['50%', '70%'], data: [
          { value: done, name: '已完成', itemStyle: { color: '#4b2d77' } },
          { value: total - done, name: '未完成', itemStyle: { color: '#e8e0f0' } },
        ]}],
      }
    }
    if (Array.isArray(wh) && wh.length) {
      teamOption.value = {
        xAxis: { type: 'category', data: wh.map((w: any) => w.staff_name) },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: wh.map((w: any) => w.total_hours), itemStyle: { color: '#4b2d77' } }],
      }
    }
  } finally { loading.value = false }
}
onMounted(refresh)
</script>
<style scoped>
.gt-proj-dash { padding: var(--gt-space-4); }
.gt-pd-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
.gt-pd-card { background: white; border-radius: var(--gt-radius-md); padding: 16px; box-shadow: var(--gt-shadow-sm); min-height: 240px; }
.gt-pd-card h4 { margin: 0 0 12px; font-size: 14px; color: #333; }
</style>
