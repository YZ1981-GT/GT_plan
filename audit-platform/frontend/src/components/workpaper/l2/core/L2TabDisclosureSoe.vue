<template>
  <div class="l2-tab-disclosure-soe">
    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>附注披露（国有企业）规范：</strong>
        按利息来源分类列示应付利息期末余额与期初余额，并披露重要的逾期未付利息。
        国企与上市结构一致（列头为「期初余额」），数据自 L2-2 明细表审定数按类别聚合，
        审定变化时自动刷新（EventBus订阅）。
      </div>
    </div>

    <!-- ═══ Section ① 应付利息分类列示 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <h4 class="section-title">① 应付利息（按来源分类）</h4>
        <el-button v-if="!isReadonly" type="primary" text size="small" @click="handleReview('classification')">复核</el-button>
      </div>

      <el-table :data="disclosureTableData" border size="small" style="width: 100%" :row-class-name="rowClass">
        <el-table-column prop="label" label="项目" min-width="240">
          <template #default="{ row }">
            <span :class="{ 'row-bold': row.isTotal, 'row-indent': row.isSub }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="160" align="right">
          <template #default="{ row }">{{ fmtAmount(row.endAmount) }}</template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="160" align="right">
          <template #default="{ row }">{{ fmtAmount(row.priorAmount) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ Section ② 重要的逾期未付利息 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <h4 class="section-title">② 重要的逾期未付利息</h4>
        <el-button v-if="!isReadonly" type="primary" text size="small" @click="handleReview('overdue')">复核</el-button>
      </div>

      <template v-if="overdueRows.length > 0">
        <el-table :data="overdueRows" border size="small" style="width: 100%">
          <el-table-column prop="borrower" label="借款单位" min-width="200" />
          <el-table-column label="逾期金额" min-width="150" align="right">
            <template #default="{ row }">{{ fmtAmount(row.overdueAmount) }}</template>
          </el-table-column>
          <el-table-column prop="overdueReason" label="逾期原因" min-width="220" />
        </el-table>
      </template>
      <template v-else>
        <el-empty description="无重要逾期未付利息" :image-size="60" />
      </template>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>分类固定行</strong>：分期付息长借利息/企业债券/短借/优先股永续债（工具1/2）/其他/合计，对齐源模板</li>
        <li><strong>数据来源</strong>：从 L2-2 明细按类别 SUMIF 聚合，期末=审定期末，期初=审定期初，只读展示</li>
        <li><strong>逾期利息</strong>：从 L2-2 逾期标记行（isOverdue）提取借款单位/逾期金额/逾期原因</li>
        <li><strong>自动刷新</strong>：L2-1 审定表提交后自动刷新（EventBus 订阅 substantive:adjudicated）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabDisclosureSoe — L2 附注披露信息（国有企业，源模板重建）
 *
 * - 分类固定行（源模板 5 类 + 优先股[工具1/2] + 其他 + 合计）：期末余额 / 期初余额
 * - 重要的逾期未付利息表（借款单位/逾期金额/逾期原因）
 * - 与上市版共享 useL2Disclosure，仅第二列列头为「期初余额」
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { inject, toRef, onUnmounted } from 'vue'
import { useL2FormData } from '../../composables/useL2FormData'
import { useL2Disclosure } from '../../composables/useL2Disclosure'
import { eventBus } from '@/utils/eventBus'
import type { DisclosureRow } from '../../composables/useL2Disclosure'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

const { allResponses, loadData } = useL2FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})
loadData()

const { disclosureTableData, overdueRows } = useL2Disclosure(allResponses)

// ─── EventBus: 审定变化刷新 ──────────────────────────────────────────────────
function handleAdjudicatedEvent(): void {
  loadData()
}
eventBus.on('substantive:adjudicated', handleAdjudicatedEvent)
onUnmounted(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicatedEvent)
})

function rowClass({ row }: { row: DisclosureRow }): string {
  if (row.isTotal) return 'total-row'
  if (row.rowKey === 'preferred-perpetual') return 'agg-row'
  return ''
}

function handleReview(section: string): void {
  const labels: Record<string, string> = {
    classification: 'L2附注-应付利息分类（国企）',
    overdue: 'L2附注-逾期未付利息（国企）',
  }
  openReviewDialog(`L2-disclosure-soe-${section}`, labels[section] || section)
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l2-tab-disclosure-soe {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #78350f;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b45309;
}

.disclosure-section {
  margin-bottom: 20px;
}

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

.row-bold {
  font-weight: 700;
}

.row-indent {
  padding-left: 20px;
  color: #909399;
}

:deep(.total-row) {
  background-color: #f0f9eb !important;
  font-weight: 700;
}

:deep(.agg-row) {
  background-color: #fafafa !important;
  font-weight: 600;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

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
