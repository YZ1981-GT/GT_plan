<script setup lang="ts">
/**
 * D4WalkthroughMatrix — D4-14 穿行测试矩阵视图（只读）
 *
 * 行=TransactionItem[], 列=序号 + 7维度(✓/×+金额+警告) + 一致性分数 + 检查结论
 * 用于现场经理快速评估穿行测试完成度与一致性
 */
import { computed } from 'vue'
import {
  isDimensionComplete,
  DIMENSION_GROUPS,
  type TransactionItem,
} from '../../composables/useD4WalkthroughTest'

const props = defineProps<{
  items: TransactionItem[]
  totalAmount: number
  coverageRate: number
  anomalyRate: number
}>()

// ─── 维度列配置（排除 other 的金额展示） ────────────────────────────

const dimensionColumns = DIMENSION_GROUPS.map(g => ({
  key: g.key,
  label: g.label,
  hasAmount: g.key !== 'other',
}))

// ─── 辅助函数 ────────────────────────────────────────────────────────

function getDimAmount(item: TransactionItem, dimKey: string): number {
  const dim = item[dimKey as keyof TransactionItem] as any
  return dim?.amount ?? 0
}

function isAmountInconsistent(item: TransactionItem, dimKey: string): boolean {
  if (!item.consistencyDetails) return false
  const amountMatch = item.consistencyDetails.amountMatch
  if (amountMatch.isConsistent) return false
  const dimGroup = DIMENSION_GROUPS.find(g => g.key === dimKey)
  if (!dimGroup) return false
  return amountMatch.mismatchDimensions.includes(dimGroup.label)
}

function fmtAmount(v: number): string {
  if (!v || v === 0) return ''
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function scoreColor(score: number): string {
  if (score === 100) return '#67c23a'
  if (score >= 80) return '#e6a23c'
  return '#f56c6c'
}

function conclusionTag(conclusion: string): { text: string; type: string } {
  if (conclusion === '无异常') return { text: '无异常', type: 'success' }
  if (conclusion === '存在差异已解释') return { text: '差异', type: 'warning' }
  if (conclusion === '存在重大异常') return { text: '异常', type: 'danger' }
  return { text: '—', type: 'info' }
}

// ─── 汇总统计 ────────────────────────────────────────────────────────

const conclusionCounts = computed(() => {
  let normal = 0, diff = 0, anomaly = 0
  for (const item of props.items) {
    if (item.conclusion === '无异常') normal++
    else if (item.conclusion === '存在差异已解释') diff++
    else if (item.conclusion === '存在重大异常') anomaly++
  }
  return { normal, diff, anomaly }
})
</script>

<template>
  <div class="d4-walkthrough-matrix">
    <el-table
      :data="items"
      border
      style="width: 100%"
      class="matrix-table"
    >
      <!-- 序号列 -->
      <el-table-column
        fixed
        label="序号"
        min-width="60"
        align="center"
      >
        <template #default="{ row }">
          <span class="index-cell">{{ row.indexNo }}</span>
        </template>
      </el-table-column>

      <!-- 7维度列 -->
      <el-table-column
        v-for="dim in dimensionColumns"
        :key="dim.key"
        :label="dim.label"
        min-width="120"
        align="center"
      >
        <template #default="{ row }">
          <div class="dim-cell">
            <!-- ✓/× 指示器 -->
            <el-tag
              :type="isDimensionComplete(row[dim.key], dim.key) ? 'success' : 'info'"
              size="small"
              effect="plain"
              class="dim-tag"
            >
              {{ isDimensionComplete(row[dim.key], dim.key) ? '✓' : '×' }}
            </el-tag>
            <!-- 金额显示（other维度无amount） -->
            <span v-if="dim.hasAmount && getDimAmount(row, dim.key)" class="dim-amount">
              {{ fmtAmount(getDimAmount(row, dim.key)) }}
            </span>
            <!-- 金额不一致警告 -->
            <el-tooltip
              v-if="dim.hasAmount && isAmountInconsistent(row, dim.key)"
              content="金额与其他维度不一致"
              placement="top"
            >
              <span class="warn-icon">⚠️</span>
            </el-tooltip>
          </div>
        </template>
      </el-table-column>

      <!-- 一致性分数列 -->
      <el-table-column
        label="一致性分数"
        min-width="90"
        align="center"
      >
        <template #default="{ row }">
          <span
            class="score-cell"
            :style="{ color: scoreColor(row.consistencyScore) }"
          >
            {{ row.consistencyScore }}%
          </span>
        </template>
      </el-table-column>

      <!-- 检查结论列 -->
      <el-table-column
        label="检查结论"
        min-width="120"
        align="center"
      >
        <template #default="{ row }">
          <el-tag
            v-if="row.conclusion"
            :type="conclusionTag(row.conclusion).type"
            size="small"
            effect="plain"
          >
            {{ conclusionTag(row.conclusion).text }}
          </el-tag>
          <span v-else class="empty-cell">—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部汇总条 -->
    <div class="matrix-summary">
      <div class="summary-item">
        <span class="summary-label">合计金额</span>
        <span class="summary-value">{{ fmtAmount(totalAmount) || '—' }} 元</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">检查比例</span>
        <span class="summary-value" :class="{ warn: coverageRate < 60 }">
          {{ coverageRate.toFixed(1) }}%
        </span>
      </div>
      <div class="summary-item">
        <span class="summary-label">异常率</span>
        <span class="summary-value" :class="{ danger: anomalyRate > 0 }">
          {{ anomalyRate.toFixed(1) }}%
        </span>
      </div>
      <div class="summary-item">
        <span class="summary-label">结论分布</span>
        <span class="summary-tags">
          <el-tag type="success" size="small" effect="plain">{{ conclusionCounts.normal }}份无异常</el-tag>
          <el-tag type="warning" size="small" effect="plain">{{ conclusionCounts.diff }}份差异</el-tag>
          <el-tag type="danger" size="small" effect="plain">{{ conclusionCounts.anomaly }}份异常</el-tag>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.d4-walkthrough-matrix,
.matrix-table { font-size: 13px; }
.index-cell { font-weight: 500; color: #606266; font-size: 12px; }
.dim-cell { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.dim-tag { font-size: 12px; }
.dim-amount { font-size: 11px; color: #606266; font-variant-numeric: tabular-nums; }
.warn-icon { font-size: 12px; cursor: help; }
.score-cell { font-weight: 600; font-size: 13px; }
.empty-cell { color: #c0c4cc; }
.matrix-summary {
  display: flex; align-items: center; gap: 24px;
  padding: 12px 16px; background: #f5f7fa;
  border: 1px solid #ebeef5; border-top: none; border-radius: 0 0 8px 8px;
}
.summary-item { display: flex; align-items: center; gap: 8px; }
.summary-label { color: #909399; font-size: 13px; }
.summary-value { font-weight: 600; color: #303133; font-size: 13px; }
.summary-value.warn { color: #e6a23c; }
.summary-value.danger { color: #f56c6c; }
.summary-tags { display: flex; gap: 6px; }
:deep(.el-table) { --el-table-border-color: #ebeef5; }
:deep(.el-table th) { font-size: 13px; font-weight: 500; }
:deep(.el-table td) { font-size: 13px; padding: 8px 6px; }
</style>
