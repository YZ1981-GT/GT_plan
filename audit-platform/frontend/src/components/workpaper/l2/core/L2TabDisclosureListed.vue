<template>
  <div class="l2-tab-disclosure-listed">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>附注披露（上市公司）规范：</strong>
        按CAS 30/上市公司信息披露准则，列示应付利息分类汇总及逾期利息明细。
        数据来源于L2-2明细表审定数，审定变化时自动刷新（EventBus订阅）。
      </div>
    </div>

    <!-- ════════════════════════════════════════════════════════════════════ -->
    <!-- Section ① 应付利息分类汇总（按来源） -->
    <!-- ════════════════════════════════════════════════════════════════════ -->
    <div class="disclosure-section">
      <div class="section-header">
        <h4 class="section-title">① 应付利息分类汇总（按来源）</h4>
        <el-button
          v-if="!isReadonly"
          type="primary"
          text
          size="small"
          @click="handleReview('source-summary')"
        >
          复核
        </el-button>
      </div>

      <el-table
        :data="sourceSummaryData"
        border
        size="small"
        style="width: 100%"
        show-summary
        :summary-method="getSourceSummary"
      >
        <el-table-column prop="source" label="利息来源" min-width="160" />
        <el-table-column label="审定期末" min-width="130" align="right">
          <template #default="{ row }">
            {{ fmtAmount(row.auditedEnd) }}
          </template>
        </el-table-column>
        <el-table-column label="审定期初" min-width="130" align="right">
          <template #default="{ row }">
            {{ fmtAmount(row.auditedBegin) }}
          </template>
        </el-table-column>
        <el-table-column label="变动额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="变动额 = 审定期末 − 审定期初" placement="top">
              <span class="formula-col-header">变动额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="变动额 = 审定期末 − 审定期初" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.change) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ════════════════════════════════════════════════════════════════════ -->
    <!-- Section ② 逾期利息明细 -->
    <!-- ════════════════════════════════════════════════════════════════════ -->
    <div class="disclosure-section">
      <div class="section-header">
        <h4 class="section-title">② 逾期利息明细</h4>
        <el-button
          v-if="!isReadonly"
          type="primary"
          text
          size="small"
          @click="handleReview('overdue-detail')"
        >
          复核
        </el-button>
      </div>

      <template v-if="overdueData.length > 0">
        <el-table
          :data="overdueData"
          border
          size="small"
          style="width: 100%"
        >
          <el-table-column prop="contractName" label="借款名称" min-width="180" />
          <el-table-column label="逾期金额" min-width="130" align="right">
            <template #default="{ row }">
              {{ fmtAmount(row.overdueAmount) }}
            </template>
          </el-table-column>
          <el-table-column prop="overdueReason" label="逾期原因" min-width="200" />
          <el-table-column label="逾期月数" min-width="90" align="center">
            <template #default="{ row }">
              {{ row.overdueMonths > 0 ? `${row.overdueMonths}个月` : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="source" label="借款类别" min-width="120" />
        </el-table>
      </template>
      <template v-else>
        <el-empty description="无逾期利息" :image-size="60" />
      </template>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>数据来源</strong>：附注数据自动从L2-2明细表审定结果提取，只读展示</li>
        <li><strong>分类汇总</strong>：按借款来源（短期借款/长期借款/应付债券）汇总审定期末/期初</li>
        <li><strong>逾期利息</strong>：从L2-2中逾期标记行(isOverdue)提取，需在明细表标注逾期</li>
        <li><strong>自动刷新</strong>：L2-1审定表提交后自动刷新附注数据（EventBus订阅）</li>
        <li><strong>披露格式</strong>：上市公司需额外披露逾期原因及是否涉及诉讼担保</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabDisclosureListed — L2 附注披露信息（上市公司）
 *
 * 功能：
 * - Section ① 应付利息分类汇总（按来源）
 * - Section ② 逾期利息明细
 * - 数据来源于 L2-2 明细表（只读展示）
 * - Subscribe 'substantive:adjudicated' EventBus → refresh display
 * - inject openReviewDialog
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 4.5
 * Requirements: 5.4, 5.5
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { computed, ref, inject, toRef, onUnmounted } from 'vue'
import { useL2FormData } from '../../composables/useL2FormData'
import { useL2Detail, type DetailRow } from '../../composables/useL2Detail'
import { calcSubtotal } from '../../composables/useL2FormulaEngine'
import { eventBus } from '@/utils/eventBus'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── Inject openReviewDialog ─────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {},
)

// ─── Composable: useL2FormData ───────────────────────────────────────────────

const {
  allResponses,
  isLoading,
  loadData,
  saveField,
  debouncedSave,
} = useL2FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// 加载数据
loadData()

// ─── Composable: useL2Detail（提取明细数据） ─────────────────────────────────

const {
  rows: detailRows,
  overdueRows,
} = useL2Detail({
  allResponses,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  debouncedSave,
  saveField,
})

// ─── Section ①: 按来源分类汇总 ──────────────────────────────────────────────

interface SourceSummaryRow {
  source: string
  auditedEnd: number
  auditedBegin: number
  change: number
}

const sourceSummaryData = computed<SourceSummaryRow[]>(() => {
  const grouped: Record<string, { auditedEnd: number; auditedBegin: number }> = {}

  for (const row of detailRows.value) {
    const key = row.source || '未分类'
    if (!grouped[key]) {
      grouped[key] = { auditedEnd: 0, auditedBegin: 0 }
    }
    grouped[key].auditedEnd += row.audited || 0
    grouped[key].auditedBegin += row.adjustedBegin || 0
  }

  return Object.entries(grouped).map(([source, data]) => ({
    source,
    auditedEnd: data.auditedEnd,
    auditedBegin: data.auditedBegin,
    change: data.auditedEnd - data.auditedBegin,
  }))
})

/** 自定义合计行 */
function getSourceSummary({ columns, data }: { columns: any[]; data: SourceSummaryRow[] }) {
  const sums: string[] = []
  columns.forEach((_col: any, index: number) => {
    if (index === 0) {
      sums[index] = '合计'
      return
    }
    const key = index === 1 ? 'auditedEnd' : index === 2 ? 'auditedBegin' : 'change'
    const total = calcSubtotal(data.map(row => (row as any)[key] ?? 0))
    sums[index] = fmtAmount(total)
  })
  return sums
}

// ─── Section ②: 逾期利息明细 ────────────────────────────────────────────────

interface OverdueDisplayRow {
  contractName: string
  overdueAmount: number
  overdueReason: string
  overdueMonths: number
  source: string
}

const overdueData = computed<OverdueDisplayRow[]>(() => {
  return overdueRows.value.map(row => ({
    contractName: row.contractName || '-',
    overdueAmount: row.endBalance,
    overdueReason: row.overdueReason || '-',
    overdueMonths: row.overdueMonths,
    source: row.source || '-',
  }))
})

// ─── EventBus: subscribe 'substantive:adjudicated' → refresh ─────────────────

function handleAdjudicatedEvent(): void {
  loadData()
}

eventBus.on('substantive:adjudicated', handleAdjudicatedEvent)

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicatedEvent)
})

// ─── 复核 ────────────────────────────────────────────────────────────────────

function handleReview(section: string): void {
  const labels: Record<string, string> = {
    'source-summary': 'L2附注-利息分类汇总（上市）',
    'overdue-detail': 'L2附注-逾期利息明细（上市）',
  }
  openReviewDialog(`L2-disclosure-listed-${section}`, labels[section] || section)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l2-tab-disclosure-listed {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── Disclosure Section ─── */
.disclosure-section {
  margin-bottom: 20px;
}

/* ─── Section标题行 + 复核按钮右对齐 ─── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 公式列表头（虚线下划线 + cursor:help） ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* ─── 公式列单元格（虚线下划线 + cursor:help） ─── */
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  display: inline-block;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
