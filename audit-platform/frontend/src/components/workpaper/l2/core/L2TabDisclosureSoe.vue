<template>
  <div class="l2-tab-disclosure-soe">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>附注披露（国有企业）规范：</strong>
        按国有企业财务报告披露要求，列示应付利息分类汇总。
        国企格式较上市公司简化，侧重来源分类和期末期初对比。数据来源于L2-2明细表。
      </div>
    </div>

    <!-- ════════════════════════════════════════════════════════════════════ -->
    <!-- Section ① 应付利息分类汇总（按来源） -->
    <!-- ════════════════════════════════════════════════════════════════════ -->
    <div class="disclosure-section">
      <div class="section-header">
        <h4 class="section-title">① 应付利息分类汇总</h4>
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
        <el-table-column prop="source" label="利息来源" min-width="180" />
        <el-table-column label="审定期末" min-width="140" align="right">
          <template #default="{ row }">
            {{ fmtAmount(row.auditedEnd) }}
          </template>
        </el-table-column>
        <el-table-column label="审定期初" min-width="140" align="right">
          <template #default="{ row }">
            {{ fmtAmount(row.auditedBegin) }}
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ════════════════════════════════════════════════════════════════════ -->
    <!-- Section ② 逾期利息明细（如有） -->
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
          <el-table-column prop="contractName" label="借款名称" min-width="200" />
          <el-table-column label="逾期金额" min-width="140" align="right">
            <template #default="{ row }">
              {{ fmtAmount(row.overdueAmount) }}
            </template>
          </el-table-column>
          <el-table-column prop="overdueReason" label="逾期原因" min-width="220" />
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
        <li><strong>国企简化</strong>：国有企业格式较上市公司精简，仅需来源/期末/期初</li>
        <li><strong>逾期披露</strong>：如有逾期利息在Section②列示，否则显示为空</li>
        <li><strong>自动刷新</strong>：L2-1审定表提交后自动刷新附注数据（EventBus订阅）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabDisclosureSoe — L2 附注披露信息（国有企业）
 *
 * 功能：
 * - Same as Listed but simplified（fewer columns, SOE format）
 * - Section ① 应付利息分类汇总：来源/审定期末/审定期初
 * - Section ② 逾期利息明细（if any）
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

// ─── Section ①: 按来源分类汇总（简化版） ────────────────────────────────────

interface SourceSummaryRow {
  source: string
  auditedEnd: number
  auditedBegin: number
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
    const key = index === 1 ? 'auditedEnd' : 'auditedBegin'
    const total = calcSubtotal(data.map(row => (row as any)[key] ?? 0))
    sums[index] = fmtAmount(total)
  })
  return sums
}

// ─── Section ②: 逾期利息明细（简化，仅名称+金额+原因） ──────────────────────

interface OverdueDisplayRow {
  contractName: string
  overdueAmount: number
  overdueReason: string
}

const overdueData = computed<OverdueDisplayRow[]>(() => {
  return overdueRows.value.map(row => ({
    contractName: row.contractName || '-',
    overdueAmount: row.endBalance,
    overdueReason: row.overdueReason || '-',
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
    'source-summary': 'L2附注-利息分类汇总（国企）',
    'overdue-detail': 'L2附注-逾期利息明细（国企）',
  }
  openReviewDialog(`L2-disclosure-soe-${section}`, labels[section] || section)
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
.l2-tab-disclosure-soe {
  padding: 12px;
  font-size: 13px;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: 13px;
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

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-table th .cell) {
  font-size: 13px;
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
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
