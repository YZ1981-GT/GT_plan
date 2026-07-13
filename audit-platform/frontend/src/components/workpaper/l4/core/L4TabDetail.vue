<template>
  <div class="l4-tab-detail">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L4-2 应付债券明细表</h3>
        <el-tag type="warning" size="small">89列·区段Tab</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增债券
        </el-button>
        <el-button size="small" @click="handleAI('detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>89列极宽表按区段Tab拆分：</strong>
        基础信息（名称/发行日/到期日/面值/利率/付息方式） → 发行信息（发行价/交易费用/初始入账/溢折价） → 计息付息（票面利息/实际利息/摊销） → 摊余成本（期初/贷方/借方/期末） → 兑付信息。行跨区段同步，同一债券在各Tab中保持一致。
      </div>
    </div>

    <!-- ═══ 区段Tab切换器 ═══ -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" class="segment-switcher" />

    <!-- ═══ 明细表主体（当前区段） ═══ -->
    <el-table
      :data="computedRows"
      border
      size="small"
      style="width: 100%"
      highlight-current-row
    >
      <!-- 序号列（全局固定） -->
      <el-table-column type="index" label="#" width="50" align="center" fixed />

      <!-- 债券名称（全局固定） -->
      <el-table-column prop="bondName" label="债券名称" min-width="180" fixed>
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.bondName"
              size="small"
              @change="(val: string) => handleUpdate($index, 'bondName', val)"
            />
          </template>
          <span v-else>{{ row.bondName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 基础信息区段 -->
      <template v-if="activeSegment === 'basic'">
        <el-table-column label="发行日" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker v-if="!isReadonly" :model-value="row.issueDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(val: string) => handleUpdate($index, 'issueDate', val)" />
            <span v-else>{{ row.issueDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker v-if="!isReadonly" :model-value="row.maturityDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(val: string) => handleUpdate($index, 'maturityDate', val)" />
            <span v-else>{{ row.maturityDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="面值总额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'faceValue', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.faceValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="票面利率(%)" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.couponRate * 100" :controls="false" :precision="4" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'couponRate', (val ?? 0) / 100)" />
            <span v-else>{{ (row.couponRate * 100).toFixed(4) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="实际利率(%)" min-width="100" align="right">
          <template #header>
            <el-tooltip content="实际利率(EIR)，由L4-6 IRR求解" placement="top">
              <span class="formula-col-header">实际利率(%)</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.effectiveRate * 100" :controls="false" :precision="4" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'effectiveRate', (val ?? 0) / 100)" />
            <span v-else>{{ (row.effectiveRate * 100).toFixed(4) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="付息方式" min-width="140">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.paymentType" size="small" style="width:100%" @change="(val: string) => handleUpdate($index, 'paymentType', val)">
              <el-option label="分期付息到期一次还本" value="installment" />
              <el-option label="到期一次还本付息" value="bullet" />
            </el-select>
            <span v-else>{{ row.paymentType === 'bullet' ? '到期一次还本付息' : '分期付息到期一次还本' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 发行信息区段 -->
      <template v-if="activeSegment === 'issue'">
        <el-table-column label="发行价格" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.issuePrice" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'issuePrice', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.issuePrice) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="交易费用" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.transactionCost" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'transactionCost', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.transactionCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="初始入账" min-width="120" align="right">
          <template #header>
            <el-tooltip content="发行价 − 交易费用" placement="top">
              <span class="formula-col-header">初始入账</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.initialAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="溢折价" min-width="120" align="right">
          <template #header>
            <el-tooltip content="初始入账 − 面值（正=溢价，负=折价）" placement="top">
              <span class="formula-col-header">溢折价</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', row.premiumDiscount < 0 ? 'text-danger' : '']">
              {{ fmtAmount(row.premiumDiscount) }}
            </span>
          </template>
        </el-table-column>
      </template>

      <!-- 计息付息区段 -->
      <template v-if="activeSegment === 'interest'">
        <el-table-column label="票面利息" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.couponInterest" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'couponInterest', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.couponInterest) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="实际利息费用" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期初摊余成本 × 实际利率" placement="top">
              <span class="formula-col-header">实际利息费用</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.interestExpense" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'interestExpense', val ?? 0)" />
            <span v-else class="formula-value">{{ fmtAmount(row.interestExpense) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="利息调整摊销" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.amortization" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'amortization', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.amortization) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 摊余成本区段 -->
      <template v-if="activeSegment === 'amortized'">
        <el-table-column label="期初成本" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginCostPrincipal" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginCostPrincipal', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginCostPrincipal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初利息调整" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginCostInterestAdj" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginCostInterestAdj', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginCostInterestAdj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初应计" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginCostAccrued" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginCostAccrued', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginCostAccrued) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方(发行)" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditIssue" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'creditIssue', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.creditIssue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方(利息调整)" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditInterestAdj" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'creditInterestAdj', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.creditInterestAdj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方(兑付)" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitRedemption" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'debitRedemption', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.debitRedemption) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方(利息调整)" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitInterestAdj" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'debitInterestAdj', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.debitInterestAdj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末成本" min-width="110" align="right">
          <template #header>
            <el-tooltip content="期初+贷方−借方（负债类）" placement="top">
              <span class="formula-col-header">期末成本</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endCostPrincipal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末利息调整" min-width="110" align="right">
          <template #header>
            <el-tooltip content="期初+贷方−借方（负债类）" placement="top">
              <span class="formula-col-header">期末利息调整</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endCostInterestAdj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末应计" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.endCostAccrued" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'endCostAccrued', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.endCostAccrued) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 兑付信息区段 -->
      <template v-if="activeSegment === 'redemption'">
        <el-table-column label="兑付日期" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker v-if="!isReadonly" :model-value="row.redemptionDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(val: string) => handleUpdate($index, 'redemptionDate', val)" />
            <span v-else>{{ row.redemptionDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="兑付金额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.redemptionAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'redemptionAmount', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.redemptionAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已兑付" width="80" align="center">
          <template #default="{ row, $index }">
            <el-checkbox :model-value="row.isRedeemed" :disabled="isReadonly" @change="(val: boolean) => handleUpdate($index, 'isRedeemed', val)" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="200">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(val: string) => handleUpdate($index, 'remark', val)" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列 -->
      <el-table-column label="操作" width="70" align="center" fixed="right" v-if="!isReadonly">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计区 ═══ -->
    <div class="summary-bar">
      <span>面值合计：<strong>{{ fmtAmount(totalFaceValue) }}</strong></span>
      <span>期末摊余成本合计：<strong>{{ fmtAmount(totalEndAmortizedCost) }}</strong></span>
      <span>共 <strong>{{ computedRows.length }}</strong> 只债券</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>89列按5区段Tab拆分，行跨区段同步（切换Tab不影响行数据）</li>
        <li>新增债券需弹窗输入名称后创建</li>
        <li>期末成本/利息调整为公式列（期初+贷方−借方，负债类）</li>
        <li>明细合计应与审定表L4-1核对一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabDetail — L4-2 应付债券明细表（89列极宽表！）
 *
 * Requirements: 3.1-3.5
 * - 区段Tab拆分: 基础/发行/计息付息/摊余成本/兑付
 * - 行同步 + 动态行 + ElMessageBox.prompt
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL4FormData } from '../../composables/useL4FormData'
import { useL4Detail, type L4DetailRow, type L4DetailSegment } from '../../composables/useL4Detail'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData + Composable ───────────────────────────────────────────────────

const formData = useL4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const detailRows = ref<L4DetailRow[]>([])

const {
  activeSegment,
  switchSegment,
  computedRows,
  totalEndAmortizedCost,
  totalFaceValue,
  addRow,
  removeRow,
  updateRow,
} = useL4Detail(formData, detailRows)

// ─── 区段Tab选项 ─────────────────────────────────────────────────────────────

const segmentOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '发行信息', value: 'issue' },
  { label: '计息付息', value: 'interest' },
  { label: '摊余成本', value: 'amortized' },
  { label: '兑付信息', value: 'redemption' },
]

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() {
  addRow()
}

function handleRemoveRow(index: number) {
  removeRow(index)
}

function handleUpdate(index: number, field: keyof L4DetailRow, value: string | number | boolean) {
  updateRow(index, field, value)
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l4-detail-${section}`,
      prompt: `请基于应付债券明细表"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.() }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l4-tab-detail {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
  line-height: 1.6;
}

.segment-switcher {
  margin-bottom: 12px;
}

.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-value {
  color: #409eff;
  font-weight: 500;
}

.text-danger {
  color: #f56c6c !important;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

.summary-bar {
  display: flex;
  gap: 24px;
  padding: 10px 16px;
  margin-top: 12px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l4-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l4-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.l4-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
