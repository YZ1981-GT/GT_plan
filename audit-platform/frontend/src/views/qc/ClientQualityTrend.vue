<template>
  <div class="client-quality-trend">
    <GtPageHeader title="客户质量趋势" :show-back="false">
      <template #actions>
        <span style="margin-right: 8px; font-size: 13px;">年数：</span>
        <el-select v-model="years" size="small" style="width: 80px;" @change="loadTrend">
          <el-option v-for="y in 10" :key="y" :label="`${y}`" :value="y" />
        </el-select>
        <el-button size="small" @click="loadTrend" :loading="loading" style="margin-left: 8px;">
          刷新
        </el-button>
      </template>
    </GtPageHeader>

    <!-- 趋势表格 -->
    <el-table
      :data="trendData"
      v-loading="loading"
      stripe
      style="width: 100%; margin-top: 16px;"
    >
      <el-table-column label="年度" prop="year" width="100" align="center" />

      <el-table-column label="评级" prop="rating" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.rating" :type="ratingTagType(row.rating)" size="small" effect="dark">
            {{ row.rating }}
          </el-tag>
          <span v-else class="no-data">—</span>
        </template>
      </el-table-column>

      <el-table-column label="问题数量" prop="issue_count" width="120" align="center">
        <template #default="{ row }">
          <span v-if="row.issue_count != null">{{ row.issue_count }}</span>
          <span v-else class="no-data">—</span>
        </template>
      </el-table-column>

      <el-table-column label="错报金额" prop="misstatement_amount" min-width="180">
        <template #default="{ row }">
          <div v-if="row.misstatement_amount != null" class="amount-bar">
            <el-progress
              :percentage="calcPercentage(row.misstatement_amount)"
              :color="amountColor(row.misstatement_amount)"
              :stroke-width="14"
              :show-text="false"
              style="flex: 1;"
            />
            <span class="amount-value">{{ formatAmount(row.misstatement_amount) }}</span>
          </div>
          <span v-else class="no-data">—</span>
        </template>
      </el-table-column>

      <el-table-column label="重要性水平" prop="materiality_level" min-width="160">
        <template #default="{ row }">
          <span v-if="row.materiality_level != null">{{ formatAmount(row.materiality_level) }}</span>
          <span v-else class="no-data">—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 简易趋势可视化 -->
    <div v-if="trendData.length" class="trend-visual">
      <h4>问题数量趋势</h4>
      <div class="bar-chart">
        <div
          v-for="item in trendData"
          :key="item.year"
          class="bar-item"
        >
          <el-progress
            :percentage="calcIssuePercentage(item.issue_count)"
            :color="issueBarColor(item.issue_count)"
            :stroke-width="20"
            :show-text="false"
            style="width: 100%;"
            direction="vertical"
          />
          <div class="bar-label">{{ item.year }}</div>
          <div class="bar-value">{{ item.issue_count ?? '—' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import * as P from '@/services/apiPaths'
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

// ─── Types ──────────────────────────────────────────────────────────────────

interface TrendItem {
  year: number
  rating: string | null
  issue_count: number | null
  misstatement_amount: number | null
  materiality_level: number | null
}

// ─── State ──────────────────────────────────────────────────────────────────

const route = useRoute()
const clientName = computed(() => (route.params.clientName as string) || '未知客户')
const years = ref(3)
const loading = ref(false)
const trendData = ref<TrendItem[]>([])

// ─── Helpers ────────────────────────────────────────────────────────────────

function ratingTagType(rating: string): 'success' | 'warning' | 'info' | 'primary' | 'danger' | undefined {
  switch (rating) {
    case 'A': return 'success'
    case 'B': return undefined
    case 'C': return 'warning'
    case 'D': return 'danger'
    default: return undefined
  }
}

function formatAmount(amount: number | null): string {
  if (amount == null) return '—'
  return amount.toLocaleString('zh-CN', { style: 'currency', currency: 'CNY' })
}

const maxAmount = computed(() => {
  const amounts = trendData.value
    .map((d) => d.misstatement_amount)
    .filter((a): a is number => a != null)
  return amounts.length ? Math.max(...amounts) : 1
})

const maxIssueCount = computed(() => {
  const counts = trendData.value
    .map((d) => d.issue_count)
    .filter((c): c is number => c != null)
  return counts.length ? Math.max(...counts) : 1
})

function calcPercentage(amount: number): number {
  if (!maxAmount.value) return 0
  return Math.round((amount / maxAmount.value) * 100)
}

function calcIssuePercentage(count: number | null): number {
  if (count == null || !maxIssueCount.value) return 0
  return Math.round((count / maxIssueCount.value) * 100)
}

function amountColor(amount: number): string {
  const pct = calcPercentage(amount)
  if (pct > 75) return '#f56c6c'
  if (pct > 50) return '#e6a23c'
  return '#67c23a'
}

function issueBarColor(count: number | null): string {
  if (count == null) return '#c0c4cc'
  const pct = calcIssuePercentage(count)
  if (pct > 75) return '#f56c6c'
  if (pct > 50) return '#e6a23c'
  return '#409eff'
}

// ─── Data Loading ───────────────────────────────────────────────────────────

async function loadTrend() {
  loading.value = true
  try {
    const data = await api.get<any>(
      `${P.qcDashboard.clientQualityTrend(clientName.value)}?years=${years.value}`
    )
    if (Array.isArray(data)) {
      trendData.value = data
    } else if (data && Array.isArray(data.items)) {
      trendData.value = data.items
    } else {
      trendData.value = []
    }
  } catch (e: any) {
    trendData.value = []
    handleApiError(e, '加载质量趋势')
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

.no-data {
  color: #c0c4cc;
}

.amount-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.amount-value {
  font-size: 12px;
  white-space: nowrap;
  color: #606266;
}

.trend-visual {
  margin-top: 24px;
  padding: 16px;
}

.trend-visual h4 {
  margin: 0 0 12px 0;
  color: #303133;
}

.bar-chart {
  display: flex;
  gap: 16px;
  align-items: flex-end;
}

.bar-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 60px;
}

.bar-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.bar-value {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
</style>
