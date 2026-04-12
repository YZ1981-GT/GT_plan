<template>
  <div class="confirmation-summary">
    <h3>函证统计汇总</h3>

    <!-- 汇总卡片 -->
    <div class="summary-cards">
      <div class="summary-card">
        <div class="card-label">总函证数</div>
        <div class="card-value">{{ stats.total }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">已回函</div>
        <div class="card-value">{{ stats.received }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">回函率</div>
        <div class="card-value">{{ stats.responseRate }}%</div>
      </div>
      <div class="summary-card">
        <div class="card-label">函证总金额</div>
        <div class="card-value">{{ formatAmount(stats.totalAmount) }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">已确认金额</div>
        <div class="card-value">{{ formatAmount(stats.confirmedAmount) }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">覆盖率</div>
        <div class="card-value">{{ stats.coverageRate }}%</div>
      </div>
    </div>

    <!-- 饼图 -->
    <div class="chart-section">
      <h4>函证类型分布</h4>
      <div class="pie-chart-wrapper">
        <div
          class="pie-chart"
          :style="pieStyle"
        />
        <div class="pie-legend">
          <div v-for="item in pieLegend" :key="item.type" class="legend-item">
            <span class="legend-dot" :style="{ background: item.color }" />
            {{ item.label }} ({{ item.count }})
          </div>
        </div>
      </div>
    </div>

    <!-- 明细表格 -->
    <el-table :data="summaryRows" stripe class="detail-table">
      <el-table-column prop="counterparty" label="交易对手" min-width="160" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          {{ typeLabel(row.type) }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="请求金额" width="140" align="right">
        <template #default="{ row }">
          {{ formatAmount(row.requested_amount) }}
        </template>
      </el-table-column>
      <el-table-column label="确认金额" width="140" align="right">
        <template #default="{ row }">
          {{ formatAmount(row.confirmed_amount) }}
        </template>
      </el-table-column>
      <el-table-column label="差异" width="140" align="right">
        <template #default="{ row }">
          <span :class="row.difference < 0 ? 'text-danger' : row.difference > 0 ? 'text-warning' : ''">
            {{ formatAmount(row.difference) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="回函率" width="100" align="center">
        <template #default="{ row }">
          {{ row.response_rate }}%
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { confirmationApi } from '@/services/collaborationApi'

const projectId = 'current-project-id'

const typeLabelMap: Record<string, string> = {
  BANK: '银行',
  AR: '应收账款',
  AP: '应付账款',
  LAWYER: '律师',
}

const statusLabelMap: Record<string, string> = {
  PENDING: '待发送',
  SENT: '已发送',
  RECEIVED: '已回函',
  EXCEPTION: '异常',
}

const statusTypeMap: Record<string, string> = {
  PENDING: 'info',
  SENT: 'warning',
  RECEIVED: 'success',
  EXCEPTION: 'danger',
}

const typeLabel = (t: string) => typeLabelMap[t] || t
const statusLabel = (s: string) => statusLabelMap[s] || s
const statusType = (s: string) => statusTypeMap[s] || 'info'

const confirmations = ref<any[]>([])
const summaryRows = ref<any[]>([])

const stats = computed(() => {
  const total = confirmations.value.length
  const received = confirmations.value.filter((c) => c.status === 'RECEIVED').length
  const responseRate = total > 0 ? Math.round((received / total) * 100) : 0
  const totalAmount = confirmations.value.reduce((s: number, c: any) => s + (c.amount || 0), 0)
  const confirmedAmount = confirmations.value.reduce((s: number, c: any) => s + (c.confirmed_amount || 0), 0)
  const coverageRate = totalAmount > 0 ? Math.round((confirmedAmount / totalAmount) * 100) : 0
  return { total, received, responseRate, totalAmount, confirmedAmount, coverageRate }
})

const pieLegend = computed(() => {
  const counts: Record<string, number> = {}
  confirmations.value.forEach((c) => {
    counts[c.type] = (counts[c.type] || 0) + 1
  })
  const colors: Record<string, string> = {
    BANK: '#409EFF',
    AR: '#67C23A',
    AP: '#E6A23C',
    LAWYER: '#F56C6C',
  }
  const labels: Record<string, string> = {
    BANK: '银行',
    AR: '应收账款',
    AP: '应付账款',
    LAWYER: '律师',
  }
  return Object.entries(counts).map(([type, count]) => ({
    type,
    count,
    color: colors[type] || '#909399',
    label: labels[type] || type,
  }))
})

const pieStyle = computed(() => {
  const total = confirmations.value.length
  if (total === 0) return { background: 'conic-gradient(#e0e0e0 0deg 360deg)' }
  const colors: Record<string, string> = {
    BANK: '#409EFF',
    AR: '#67C23A',
    AP: '#E6A23C',
    LAWYER: '#F56C6C',
  }
  const counts: Record<string, number> = {}
  confirmations.value.forEach((c) => {
    counts[c.type] = (counts[c.type] || 0) + 1
  })
  const parts = Object.entries(counts).map(([type, count]) => {
    const deg = (count / total) * 360
    return `${colors[type] || '#909399'} ${deg}deg`
  })
  return { background: `conic-gradient(${parts.join(', ')})` }
})

function formatAmount(val: number) {
  if (!val && val !== 0) return '-'
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', maximumFractionDigits: 2 }).format(val)
}

onMounted(async () => {
  try {
    const { data } = await confirmationApi.list(projectId)
    confirmations.value = data ?? []
    summaryRows.value = confirmations.value.map((c: any) => ({
      counterparty: c.counterparty,
      type: c.type,
      status: c.status,
      requested_amount: c.amount || 0,
      confirmed_amount: c.confirmed_amount || 0,
      difference: (c.confirmed_amount || 0) - (c.amount || 0),
      response_rate: c.status === 'RECEIVED' ? 100 : 0,
    }))
  } catch {
    confirmations.value = []
    summaryRows.value = []
  }
})
</script>

<style scoped>
.confirmation-summary {}
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.summary-card {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.card-label {
  color: #909399;
  font-size: 13px;
  margin-bottom: 6px;
}
.card-value {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}
.chart-section {
  margin-bottom: 20px;
}
.chart-section h4 {
  margin-bottom: 12px;
  font-size: 15px;
}
.pie-chart-wrapper {
  display: flex;
  align-items: center;
  gap: 24px;
}
.pie-chart {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pie-legend {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}
.detail-table {
  margin-top: 12px;
}
.text-danger { color: #F56C6C; }
.text-warning { color: #E6A23C; }
</style>
