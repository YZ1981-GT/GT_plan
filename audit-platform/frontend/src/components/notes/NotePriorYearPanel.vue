<template>
  <!-- C.3.10: 上年对比侧栏 -->
  <el-drawer
    v-model="visible"
    title="上年对比"
    direction="rtl"
    size="450px"
  >
    <div class="prior-panel" v-loading="loading">
      <el-alert
        v-if="!priorYearNote"
        title="无上年数据"
        type="info"
        :closable="false"
        show-icon
      />

      <template v-else>
        <!-- 概览 -->
        <el-descriptions :column="1" border size="small" style="margin-bottom: 12px">
          <el-descriptions-item label="上年章节标题">{{ priorYearNote.section_title || '—' }}</el-descriptions-item>
          <el-descriptions-item label="上年公式数">{{ priorFormulaCount }}</el-descriptions-item>
          <el-descriptions-item label="差异行数">{{ diffRows.length }}</el-descriptions-item>
        </el-descriptions>

        <!-- 行级差异表 -->
        <h4>行级差异</h4>
        <el-table
          v-if="diffRows.length"
          :data="diffRows"
          size="small"
          border
          max-height="400"
        >
          <el-table-column prop="row_index" label="行号" width="60" />
          <el-table-column prop="label" label="项目" />
          <el-table-column label="上年" align="right" width="120">
            <template #default="{ row }">
              <span class="prior-value">{{ formatAmount(row.prior_value) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本年" align="right" width="120">
            <template #default="{ row }">
              <span :class="getChangeClass(row)">{{ formatAmount(row.current_value) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变化" align="right" width="100">
            <template #default="{ row }">
              <el-tag
                v-if="row.change !== null"
                :type="row.change > 0 ? 'success' : row.change < 0 ? 'danger' : 'info'"
                size="small"
              >
                {{ row.change > 0 ? '+' : '' }}{{ formatPercent(row.change_pct) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-else description="无行级差异" />

        <!-- 上年文本对比 -->
        <div v-if="priorYearNote.text_content" style="margin-top: 16px">
          <h4>上年段落</h4>
          <div class="prior-text">{{ priorYearNote.text_content }}</div>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface Props {
  modelValue: boolean
  priorYearNote: any
  currentNote: any
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), { loading: false })
const emit = defineEmits<{ 'update:modelValue': [val: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

interface DiffRow {
  row_index: number
  label: string
  prior_value: number | null
  current_value: number | null
  change: number | null
  change_pct: number | null
}

const diffRows = computed<DiffRow[]>(() => {
  if (!props.priorYearNote?.table_data?.rows || !props.currentNote?.table_data?.rows) return []

  const priorRows = props.priorYearNote.table_data.rows
  const currentRows = props.currentNote.table_data.rows

  const result: DiffRow[] = []
  const maxLen = Math.max(priorRows.length, currentRows.length)

  for (let i = 0; i < maxLen; i++) {
    const prior = priorRows[i]
    const current = currentRows[i]
    const label = (current?.label || prior?.label || `行${i + 1}`) as string

    // Try to extract numeric value (assume amount is at index 1 or first numeric cell)
    const priorVal = extractNumeric(prior)
    const currentVal = extractNumeric(current)

    if (priorVal === null && currentVal === null) continue

    let change: number | null = null
    let changePct: number | null = null
    if (priorVal !== null && currentVal !== null) {
      change = currentVal - priorVal
      changePct = priorVal !== 0 ? (change / Math.abs(priorVal)) * 100 : null
    }

    result.push({
      row_index: i + 1,
      label,
      prior_value: priorVal,
      current_value: currentVal,
      change,
      change_pct: changePct,
    })
  }

  // Filter to rows with actual differences
  return result.filter(r => r.change !== null && Math.abs(r.change) > 0.01)
})

const priorFormulaCount = computed(() => {
  const formulas = props.priorYearNote?.table_data?._formulas || {}
  return Object.keys(formulas).length
})

function extractNumeric(row: any): number | null {
  if (!row) return null
  const cells = row.cells || row.values || []
  for (const cell of cells) {
    const val = typeof cell === 'object' ? cell?.value : cell
    if (val === null || val === undefined || val === '') continue
    const num = Number(val)
    if (!isNaN(num)) return num
  }
  return null
}

function formatAmount(val: number | null): string {
  if (val === null || val === undefined) return '—'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function formatPercent(val: number | null): string {
  if (val === null || val === undefined) return '—'
  return `${val.toFixed(1)}%`
}

function getChangeClass(row: DiffRow): string {
  if (row.change === null) return ''
  if (row.change > 0) return 'change-up'
  if (row.change < 0) return 'change-down'
  return ''
}
</script>

<style scoped>
.prior-panel {
  padding: 0 4px;
}
.prior-panel h4 {
  margin: 12px 0 8px;
  font-size: 14px;
  color: #303133;
}
.prior-value {
  color: #909399;
}
.change-up {
  color: #67c23a;
  font-weight: 500;
}
.change-down {
  color: #f56c6c;
  font-weight: 500;
}
.prior-text {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}
</style>
