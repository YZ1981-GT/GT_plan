<template>
  <div class="client-quality-trend">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner gt-page-banner--teal">
      <div class="gt-banner-content">
        <h2>📈 客户质量趋势 — {{ clientName }}</h2>
        <span class="gt-banner-sub">
          近 {{ selectedYears }} 年审计质量变化
        </span>
      </div>
      <div class="gt-banner-actions">
        <el-select
          v-model="selectedYears"
          size="small"
          style="width: 100px"
          @change="loadTrend"
        >
          <el-option :value="3" label="近 3 年" />
          <el-option :value="5" label="近 5 年" />
          <el-option :value="10" label="近 10 年" />
        </el-select>
        <el-button size="small" @click="loadTrend" :loading="loading">刷新</el-button>
        <el-button size="small" @click="$router.back()">返回</el-button>
      </div>
    </div>

    <!-- 折线图 -->
    <div class="chart-section">
      <h3 class="section-title">质量评分趋势</h3>
      <GTChart :option="chartOption" :height="320" :loading="loading" empty-text="暂无趋势数据" />
    </div>

    <!-- 年度对比表 -->
    <div class="table-section">
      <h3 class="section-title">年度对比明细</h3>
      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
        style="width: 100%"
        row-key="year"
      >
        <el-table-column label="年度" prop="year" width="100" align="center" />
        <el-table-column label="评级" width="100" align="center">
          <template #default="{ row }">
            <template v-if="row.hasData">
              <el-tag
                :type="ratingTagType(row.rating)"
                size="default"
                effect="dark"
              >
                {{ row.rating || '—' }}
              </el-tag>
            </template>
            <span v-else class="no-data-text">该年份无审计项目</span>
          </template>
        </el-table-column>
        <el-table-column label="评分" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.hasData">{{ row.score != null ? row.score : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="问题数" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.hasData">{{ row.issue_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="错报金额" min-width="140" align="right">
          <template #default="{ row }">
            <span v-if="row.hasData">{{ formatAmount(row.misstatement_amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重要性水平" min-width="140" align="right">
          <template #default="{ row }">
            <span v-if="row.hasData">
              {{ row.materiality_level != null ? formatAmount(row.materiality_level) : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="项目数" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.hasData">{{ row.project_count }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import GTChart from '@/components/GTChart.vue'
import {
  getClientQualityTrend,
  type ClientQualityTrendItem,
} from '@/services/qcDashboardApi'

const route = useRoute()

// ─── State ──────────────────────────────────────────────────────────────────

const clientName = computed(() => decodeURIComponent(route.params.clientName as string))
const selectedYears = ref(3)
const loading = ref(false)
const trendData = ref<ClientQualityTrendItem[]>([])

// ─── Chart Option ───────────────────────────────────────────────────────────

const chartOption = computed(() => {
  const years = trendData.value.map((t) => String(t.year))
  const scores = trendData.value.map((t) => (t.data?.score != null ? t.data.score : null))

  if (years.length === 0 || scores.every((s) => s === null)) {
    return { series: [] }
  }

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        const idx = p.dataIndex
        const item = trendData.value[idx]
        if (!item?.data) return `${item?.year}：该年份无审计项目`
        return `
          <strong>${item.year}</strong><br/>
          评级：${item.data.rating || '—'}<br/>
          评分：${item.data.score != null ? item.data.score : '—'}<br/>
          问题数：${item.data.issue_count}<br/>
          错报金额：${formatAmount(item.data.misstatement_amount)}
        `
      },
    },
    grid: { left: 60, right: 30, top: 40, bottom: 40 },
    xAxis: {
      type: 'category',
      data: years,
      name: '年度',
    },
    yAxis: {
      type: 'value',
      name: '评分',
      min: 0,
      max: 100,
    },
    series: [
      {
        name: '质量评分',
        type: 'line',
        data: scores,
        smooth: true,
        connectNulls: false,
        symbol: 'circle',
        symbolSize: 8,
        lineStyle: { width: 3 },
        areaStyle: {
          opacity: 0.15,
        },
        markLine: {
          silent: true,
          data: [
            { yAxis: 90, name: 'A', lineStyle: { color: '#67c23a', type: 'dashed' } },
            { yAxis: 75, name: 'B', lineStyle: { color: '#409eff', type: 'dashed' } },
            { yAxis: 60, name: 'C', lineStyle: { color: '#e6a23c', type: 'dashed' } },
          ],
          label: { position: 'end', formatter: '{b}≥{c}' },
        },
      },
    ],
  }
})

// ─── Table Data ─────────────────────────────────────────────────────────────

interface TableRow {
  year: number
  hasData: boolean
  rating: string | null
  score: number | null
  issue_count: number
  misstatement_amount: number
  materiality_level: number | null
  project_count: number
}

const tableData = computed<TableRow[]>(() => {
  return trendData.value.map((item) => {
    if (item.data) {
      return {
        year: item.year,
        hasData: true,
        rating: item.data.rating,
        score: item.data.score,
        issue_count: item.data.issue_count,
        misstatement_amount: item.data.misstatement_amount,
        materiality_level: item.data.materiality_level,
        project_count: item.data.project_count,
      }
    }
    return {
      year: item.year,
      hasData: false,
      rating: null,
      score: null,
      issue_count: 0,
      misstatement_amount: 0,
      materiality_level: null,
      project_count: 0,
    }
  })
})

// ─── Helpers ────────────────────────────────────────────────────────────────

function ratingTagType(rating: string | null): 'success' | 'primary' | 'warning' | 'danger' | 'info' {
  switch (rating) {
    case 'A': return 'success'
    case 'B': return 'primary'
    case 'C': return 'warning'
    case 'D': return 'danger'
    default: return 'info'
  }
}

function formatAmount(val: number | null | undefined): string {
  if (val == null) return '—'
  if (val === 0) return '0'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

// ─── Data Loading ───────────────────────────────────────────────────────────

async function loadTrend() {
  loading.value = true
  try {
    const res = await getClientQualityTrend(clientName.value, selectedYears.value)
    trendData.value = res.trend
  } catch (e: any) {
    ElMessage.error('加载客户质量趋势失败')
    trendData.value = []
  } finally {
    loading.value = false
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  loadTrend()
})
</script>

<style scoped>
.client-quality-trend {
  padding: 0;
}

.chart-section,
.table-section {
  padding: 20px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #1d1d1f;
  margin: 0 0 12px 0;
}

.no-data-text {
  color: #909399;
  font-size: 12px;
  font-style: italic;
}
</style>
