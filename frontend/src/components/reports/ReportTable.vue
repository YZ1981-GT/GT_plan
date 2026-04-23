<template>
  <div class="report-table-wrapper">
    <div class="report-title">{{ reportName }}</div>
    <el-table
      :data="data"
      v-loading="loading"
      size="small"
      border
      stripe
      style="width: 100%"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="row_code" label="行次" width="80" align="center" />
      <el-table-column prop="row_name" label="项目" min-width="240">
        <template #default="{ row }">
          <span :style="indentStyle(row.indent_level)">{{ row.row_name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" align="right" min-width="160">
        <template #default="{ row }">
          <span :class="{ negative: Number(row.current_period_amount) < 0 }">
            {{ formatNumber(row.current_period_amount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="年初余额" align="right" min-width="160">
        <template #default="{ row }">
          <span :class="{ negative: Number(row.prior_period_amount) < 0 }">
            {{ formatNumber(row.prior_period_amount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button :icon="View" link type="primary" size="small" @click="$emit('drilldown', row)">
            穿透
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="!data || data.length === 0" class="empty-tip">
      <el-empty description="暂无数据，请点击「刷新同步" />
    </div>
  </div>
</template>

<script setup>
import { View } from '@element-plus/icons-vue'

defineProps({
  data: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  reportName: { type: String, default: '' },
})

defineEmits(['drilldown'])

function formatNumber(v) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  if (isNaN(n)) return v
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function indentStyle(level) {
  const l = Number(level) || 0
  return { paddingLeft: `${l * 20 + 4}px` }
}

function rowClassName({ row }) {
  if (row.is_total_row) return 'total-row'
  return ''
}
</script>

<style scoped>
.report-table-wrapper {
  padding: 8px 0;
}
.report-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #303133;
}
.empty-tip {
  padding: 40px 0;
}
.negative {
  color: #f56c6c;
}
:deep(.total-row) {
  background-color: #f0f9eb;
  font-weight: bold;
}
:deep(.el-table__cell) {
  padding: 6px 0;
}
</style>
