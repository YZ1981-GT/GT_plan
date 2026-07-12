<script setup lang="ts">
/**
 * D2VcAuditSummaryPanel — 审计说明统计区子组件
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 7.5
 *
 * 职责：
 * - 6 项统计指标卡片（3列 grid）
 * - 只读计算字段样式（灰底虚线下划线 + cursor:help + tooltip 显示计算来源）
 * - AI 生成审计说明按钮
 * - 审计说明 el-card 包裹的 autosize textarea
 * - 实时更新（检查表数据变更后 2 秒内刷新，由 composable watch 处理）
 *
 * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
 */
import { computed } from 'vue'

const props = defineProps<{
  isReadonly: boolean
  auditSummary: any // Return type of useD2VcAuditSummary
}>()

// ─── Computed metrics ────────────────────────────────────────────────────────

const metrics = computed(() => {
  const s = props.auditSummary?.stats?.value ?? props.auditSummary?.stats ?? {}
  return [
    {
      label: '本期发生额合计',
      value: formatAmount(s.occurrenceAmount ?? 0),
      tooltip: '数据来源：试算表科目 1122 本期借方发生额',
    },
    {
      label: '已检查金额',
      value: formatAmount(s.checkedAmount ?? 0),
      tooltip: '计算方式：双区检查表所有行(借方+贷方)金额合计',
    },
    {
      label: '检查覆盖比例',
      value: formatPercent(s.coverageRatio ?? 0),
      tooltip: '计算方式：已检查金额 ÷ 本期发生额 × 100%',
    },
    {
      label: '异常笔数',
      value: String(s.abnormalCount ?? 0),
      tooltip: '计算方式：\'是否异常\'列非空的行数',
    },
    {
      label: '异常金额合计',
      value: formatAmount(s.abnormalAmount ?? 0),
      tooltip: '计算方式：异常行的(借方+贷方)金额合计',
    },
    {
      label: '异常率',
      value: formatPercent(s.abnormalRate ?? 0),
      tooltip: '计算方式：异常笔数 ÷ 已检查笔数 × 100%',
    },
  ]
})

// ─── Formatting helpers ──────────────────────────────────────────────────────

function formatAmount(val: number): string {
  if (val === 0) return '0.00'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPercent(val: number): string {
  return val.toFixed(1) + '%'
}

// ─── AI generation ───────────────────────────────────────────────────────────

const isGenerating = computed(() => props.auditSummary?.isGenerating?.value ?? false)
const isLoadingTb = computed(() => props.auditSummary?.isLoadingTb?.value ?? false)

async function handleGenerate() {
  if (props.isReadonly || isGenerating.value) return
  await props.auditSummary?.generateAuditSummary?.()
}

// ─── Summary text ────────────────────────────────────────────────────────────

const summaryText = computed({
  get: () => props.auditSummary?.summaryText?.value ?? '',
  set: (val: string) => {
    if (props.auditSummary?.summaryText) {
      props.auditSummary.summaryText.value = val
    }
  },
})

function handleSummaryChange() {
  props.auditSummary?.saveToResponses?.()
}
</script>

<template>
  <div class="vc-audit-summary-panel">
    <!-- ═══ 统计指标 Grid ═══ -->
    <div v-if="isLoadingTb" class="stats-loading">
      <el-skeleton :rows="2" animated />
    </div>
    <div v-else class="stats-grid">
      <el-tooltip
        v-for="(m, idx) in metrics"
        :key="idx"
        :content="m.tooltip"
        placement="top"
        :show-after="300"
      >
        <div class="metric-field">
          <div class="metric-label">{{ m.label }}</div>
          <div class="metric-value">{{ m.value }}</div>
        </div>
      </el-tooltip>
    </div>

    <!-- ═══ 审计说明 textarea ═══ -->
    <div class="summary-section">
      <div class="section-header">
        <span class="section-title">审计说明</span>
        <el-tooltip
          :content="isReadonly ? '只读模式' : (isGenerating ? '正在生成...' : 'AI 辅助生成审计说明')"
          placement="top"
        >
          <el-button
            size="small"
            type="primary"
            plain
            :loading="isGenerating"
            :disabled="isReadonly || isGenerating"
            @click="handleGenerate"
          >
            🤖 AI 生成
          </el-button>
        </el-tooltip>
      </div>

      <el-card shadow="never" class="summary-card">
        <el-input
          v-model="summaryText"
          type="textarea"
          :autosize="{ minRows: 5 }"
          :disabled="isReadonly"
          placeholder="根据凭证检查结果，说明检查范围、方法、结果及异常情况..."
          @change="handleSummaryChange"
        />
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.vc-audit-summary-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ─── Stats Grid ─── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stats-loading {
  padding: 12px;
}

/* ─── Metric Card (只读计算字段) ─── */
.metric-field {
  background: #f5f7fa;
  border-bottom: 1px dashed #dcdfe6;
  cursor: help;
  padding: 8px 12px;
  border-radius: 4px;
  transition: background 0.2s;
}

.metric-field:hover {
  background: #ebeef5;
}

.metric-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.metric-value {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

/* ─── Summary Section ─── */
.summary-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.summary-card {
  --el-card-padding: 12px;
}

.summary-card :deep(.el-textarea__inner) {
  font-size: 13px;
}
</style>
