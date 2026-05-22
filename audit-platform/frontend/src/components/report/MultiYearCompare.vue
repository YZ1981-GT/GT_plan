<template>
  <div class="gt-multi-year-compare">
    <!-- 控制栏 -->
    <div class="gt-myc-controls">
      <div class="gt-myc-controls__left">
        <span class="gt-myc-label">年度选择</span>
        <el-select
          v-model="selectedYears"
          multiple
          :multiple-limit="5"
          placeholder="选择年度（最多5年）"
          size="small"
          style="width: 320px"
          @change="onYearsChange"
        >
          <el-option
            v-for="yr in availableYears"
            :key="yr"
            :label="`${yr}年`"
            :value="yr"
          />
        </el-select>
      </div>
      <div class="gt-myc-controls__right">
        <el-radio-group v-model="reportType" size="small" @change="fetchData">
          <el-radio-button value="balance_sheet">资产负债表</el-radio-button>
          <el-radio-button value="income_statement">利润表</el-radio-button>
          <el-radio-button value="cash_flow_statement">现金流量表</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="onExport" :loading="exporting" style="margin-left: 12px">
          📥 导出Excel
        </el-button>
      </div>
    </div>

    <!-- 数据表格 -->
    <el-table
      v-loading="loading"
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      :max-height="600"
      :header-cell-style="{ background: '#f8f6fb', color: '#333', whiteSpace: 'nowrap', fontSize: '12px' }"
      :row-class-name="rowClassName"
    >
      <!-- 项目名称列 (fixed) -->
      <el-table-column prop="item_name" label="项目" fixed min-width="260" :resizable="true">
        <template #default="{ row }">
          <span style="font-size: 13px">{{ row.item_name }}</span>
        </template>
      </el-table-column>

      <!-- 动态年度列 -->
      <template v-for="(yr, idx) in sortedYears" :key="yr">
        <!-- 金额列 -->
        <el-table-column :label="`${yr}年`" align="right" min-width="140" :resizable="true">
          <template #default="{ row }">
            <span class="gt-amt">{{ formatAmount(row.values[String(yr)]) }}</span>
          </template>
        </el-table-column>
        <!-- YoY 变动列（第一年无变动率） -->
        <el-table-column
          v-if="idx > 0"
          :label="`${yr} YoY`"
          align="right"
          width="110"
          :resizable="true"
        >
          <template #default="{ row }">
            <span :class="getChangeClass(row.yoy_changes[String(yr)])">
              {{ formatChange(row.yoy_changes[String(yr)]) }}
              <span v-if="row.yoy_changes[String(yr)] != null" class="gt-myc-arrow">
                {{ getArrow(row.yoy_changes[String(yr)]) }}
              </span>
            </span>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <!-- 空状态 -->
    <div v-if="!loading && tableData.length === 0 && selectedYears.length > 0" class="gt-myc-empty">
      <span>暂无数据，请确认已生成对应年度的报表</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { reports as reportsApi } from '@/services/apiPaths'
import { exportData, type ExcelColumn } from '@/composables/useExcelIO'

/* ── Props ── */
const props = defineProps<{
  projectId: string
  currentYear: number
}>()

/* ── State ── */
const loading = ref(false)
const exporting = ref(false)
const reportType = ref<string>('balance_sheet')
const selectedYears = ref<number[]>([])
const tableData = ref<any[]>([])

/* ── Computed ── */
const availableYears = computed(() => {
  const current = props.currentYear || new Date().getFullYear()
  const years: number[] = []
  for (let i = current; i >= current - 9; i--) {
    years.push(i)
  }
  return years
})

const sortedYears = computed(() => [...selectedYears.value].sort((a, b) => a - b))

/* ── Methods ── */
function onYearsChange() {
  if (selectedYears.value.length >= 2) {
    fetchData()
  } else {
    tableData.value = []
  }
}

async function fetchData() {
  if (selectedYears.value.length < 2) {
    tableData.value = []
    return
  }

  loading.value = true
  try {
    const url = reportsApi.multiYear(props.projectId, sortedYears.value, reportType.value)
    const resp = await axios.get(url)
    tableData.value = resp.data.rows || []
  } catch (err: any) {
    const msg = err?.response?.data?.detail || '查询失败'
    ElMessage.error(msg)
    tableData.value = []
  } finally {
    loading.value = false
  }
}

function formatAmount(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatChange(val: number | null | undefined): string {
  if (val == null) return '-'
  return `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`
}

function getArrow(val: number | null | undefined): string {
  if (val == null) return ''
  if (val > 0) return '↑'
  if (val < 0) return '↓'
  return '→'
}

function getChangeClass(val: number | null | undefined): string {
  if (val == null) return 'gt-myc-change'
  const abs = Math.abs(val)
  if (abs >= 20) return 'gt-myc-change gt-myc-change--alert'
  if (val > 0) return 'gt-myc-change gt-myc-change--up'
  if (val < 0) return 'gt-myc-change gt-myc-change--down'
  return 'gt-myc-change'
}

function rowClassName({ row }: { row: any }): string {
  // 检查是否有任何 YoY 变动 >= 20%
  if (row.yoy_changes) {
    for (const key of Object.keys(row.yoy_changes)) {
      const val = row.yoy_changes[key]
      if (val != null && Math.abs(val) >= 20) {
        return 'gt-myc-row--highlight'
      }
    }
  }
  return ''
}

async function onExport() {
  if (tableData.value.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }

  exporting.value = true
  try {
    const reportTypeLabel: Record<string, string> = {
      balance_sheet: '资产负债表',
      income_statement: '利润表',
      cash_flow_statement: '现金流量表',
    }

    // 构建列定义
    const columns: ExcelColumn[] = [
      { key: 'item_name', header: '项目', width: 30 },
    ]

    for (let i = 0; i < sortedYears.value.length; i++) {
      const yr = sortedYears.value[i]
      columns.push({ key: `val_${yr}`, header: `${yr}年金额`, width: 18 })
      if (i > 0) {
        columns.push({ key: `yoy_${yr}`, header: `${yr}年同比变动率(%)`, width: 18 })
      }
    }

    // 构建数据
    const data = tableData.value.map(row => {
      const obj: Record<string, any> = { item_name: row.item_name }
      for (let i = 0; i < sortedYears.value.length; i++) {
        const yr = sortedYears.value[i]
        obj[`val_${yr}`] = row.values[String(yr)] ?? ''
        if (i > 0) {
          const yoy = row.yoy_changes[String(yr)]
          obj[`yoy_${yr}`] = yoy != null ? `${yoy.toFixed(2)}%` : '-'
        }
      }
      return obj
    })

    const label = reportTypeLabel[reportType.value] || '报表'
    const yearsStr = sortedYears.value.join('-')
    await exportData({
      data,
      columns,
      sheetName: '多年度对比',
      fileName: `${label}_多年度对比_${yearsStr}.xlsx`,
    })
  } catch (err: any) {
    ElMessage.error('导出失败：' + (err.message || '未知错误'))
  } finally {
    exporting.value = false
  }
}

/* ── Lifecycle ── */
onMounted(() => {
  // 默认选中当前年度 + 前一年度
  const current = props.currentYear || new Date().getFullYear()
  selectedYears.value = [current - 1, current]
  fetchData()
})

/* ── Expose for parent ── */
defineExpose({ fetchData, onExport })
</script>

<style scoped>
.gt-multi-year-compare {
  padding: 0;
}

.gt-myc-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.gt-myc-controls__left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-myc-controls__right {
  display: flex;
  align-items: center;
}

.gt-myc-label {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #666);
  white-space: nowrap;
}

.gt-myc-change {
  font-size: 12px;
  white-space: nowrap;
}

.gt-myc-change--up {
  color: var(--gt-color-coral, #e74c3c);
}

.gt-myc-change--down {
  color: var(--gt-color-success, #27ae60);
}

.gt-myc-change--alert {
  color: var(--gt-color-coral, #e74c3c);
  font-weight: 700;
}

.gt-myc-arrow {
  margin-left: 2px;
}

.gt-myc-empty {
  text-align: center;
  padding: 40px 0;
  color: var(--gt-color-text-tertiary, #999);
  font-size: 14px;
}

:deep(.gt-myc-row--highlight) {
  background-color: rgba(231, 76, 60, 0.06) !important;
}

:deep(.gt-myc-row--highlight td) {
  background-color: rgba(231, 76, 60, 0.06) !important;
}
</style>
