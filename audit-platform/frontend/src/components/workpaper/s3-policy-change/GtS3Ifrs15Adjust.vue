<template>
  <div class="s3-ifrs15-adjust">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：复核首次执行新收入准则（CAS 14）追溯调整的计量与列报，确认收入确认时点、合同资产/合同负债重分类及留存收益调整的恰当性。"
      style="margin-bottom: 16px"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="context-content">
        <p>
          首次执行新收入准则的调整（CAS 14）：对原有收入确认模式进行调整，
          按五步法模型重新确认收入，差异调入留存收益。
          调整差异 = 新准则账面价值 - 原准则账面价值。
        </p>
      </div>
    </div>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>首次执行新收入准则的调整 S3-6</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              @click="handleSave"
            >保存</el-button>
            <el-button size="small" @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>

      <!-- 调整差异表 -->
      <el-table
        :data="adjustmentItems"
        border
        stripe
        style="width: 100%; font-size: 13px"
        :cell-class-name="cellClassName"
      >
        <el-table-column type="index" label="序号" width="60" />
        <el-table-column prop="accountItem" label="科目/项目" min-width="220" />
        <el-table-column prop="oldStandard" label="原准则账面价值" min-width="150" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.oldStandard"
              style="width: 130px"
            />
            <span v-else>{{ fmt(row.oldStandard) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="newStandard" label="新准则账面价值" min-width="150" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.newStandard"
              style="width: 130px"
            />
            <span v-else>{{ fmt(row.newStandard) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整差异" min-width="140" align="right">
          <template #default="{ row, $index }">
            <span class="formula-cell" title="差异 = 新准则账面 - 原准则账面">
              {{ fmt(diffs[$index]) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="非经常性损益" width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.isNonRecurring" type="warning" size="small">非经常性</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="total-row">
        <span>调整差异合计：</span>
        <span class="formula-cell total-amount" title="合计 = SUM(各项差异)">
          {{ fmt(totalDiff) }}
        </span>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>S3-6 记录首次执行新收入准则（CAS 14）的调整差异。</p>
      <p>公式：调整差异 = 新准则账面价值 - 原准则账面价值。源模板含 4 个公式。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * GtS3Ifrs15Adjust.vue — S3-6 首次执行新收入准则的调整
 *
 * 功能：
 * - 调整差异 = 新准则账面 - 原准则账面
 * - 使用 calcAdjustmentDiff 纯函数
 * - 非经常性损益标注
 */
import { ref, computed, inject } from 'vue'
import { fmtAmount } from '@/utils/formatters'
import { calcAdjustmentDiff } from '../composables/useS3AdjustmentEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, label?: string) => void>('openReviewDialog')

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

interface AdjustmentItem {
  accountItem: string
  oldStandard: number
  newStandard: number
  isNonRecurring: boolean
}

const adjustmentItems = ref<AdjustmentItem[]>([
  { accountItem: '合同资产', oldStandard: 0, newStandard: 0, isNonRecurring: false },
  { accountItem: '合同负债', oldStandard: 0, newStandard: 0, isNonRecurring: false },
  { accountItem: '应收账款', oldStandard: 0, newStandard: 0, isNonRecurring: false },
  { accountItem: '预收款项', oldStandard: 0, newStandard: 0, isNonRecurring: false },
])

const diffs = computed(() => {
  const input = { items: adjustmentItems.value.map(i => ({ oldStandard: i.oldStandard, newStandard: i.newStandard })) }
  return calcAdjustmentDiff(input).diffs
})

const totalDiff = computed(() => {
  const input = { items: adjustmentItems.value.map(i => ({ oldStandard: i.oldStandard, newStandard: i.newStandard })) }
  return calcAdjustmentDiff(input).totalDiff
})

function cellClassName({ column }: any): string {
  if (column?.label === '调整差异') return 'formula-col'
  return ''
}

function handleSave() {
  // TODO: 保存
}

function handleReview() {
  openReviewDialog?.('s3-ifrs15-adjust', '首次执行新收入准则的调整 S3-6')
}
</script>

<style scoped>
.s3-ifrs15-adjust {
  padding: 12px;
}
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  border-left: 3px solid #e6a23c;
  background-color: #fdf6ec;
  border-radius: 4px;
}
.methodology-context .context-content p {
  margin: 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
:deep(.formula-col) {
  background-color: #fafafa;
}
.total-row {
  margin-top: 12px;
  padding: 8px 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
}
.total-amount {
  font-size: 15px;
  color: #303133;
}
.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}
.edit-hints summary {
  cursor: pointer;
  user-select: none;
}
</style>
