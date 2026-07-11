<template>
  <div class="s3-ifrs16-adjust">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：复核首次执行新租赁准则（CAS 21）追溯调整，确认使用权资产与租赁负债的初始计量、折现处理及留存收益调整的准确性。"
      style="margin-bottom: 16px"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="context-content">
        <p>
          首次执行新租赁准则的调整（CAS 21）：承租人对经营租赁重新确认使用权资产和租赁负债。
          使用权资产初始确认 = 总额 - 扣除项；租赁负债初始确认 = 各组成项目正加负减。
        </p>
      </div>
    </div>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>首次执行新租赁准则的调整 S3-8</span>
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

      <!-- 使用权资产初始确认 -->
      <h4 class="sub-section-title">使用权资产初始确认</h4>
      <el-table
        :data="rouAssetData"
        border
        stripe
        style="width: 100%; font-size: 13px"
      >
        <el-table-column prop="item" label="项目" min-width="240" />
        <el-table-column prop="amount" label="金额" min-width="150" align="right">
          <template #default="{ row }">
            <template v-if="row.isFormula">
              <span class="formula-cell" :title="row.formulaHint">
                {{ fmt(row.amount) }}
              </span>
            </template>
            <template v-else>
              <el-input-number
                v-if="!isReadonly"
                v-model="row.amount"
                :precision="2"
                :controls="false"
                style="width: 130px"
              />
              <span v-else>{{ fmt(row.amount) }}</span>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <!-- 租赁负债初始确认 -->
      <h4 class="sub-section-title">租赁负债初始确认</h4>
      <el-table
        :data="leaseLiabilityData"
        border
        stripe
        style="width: 100%; font-size: 13px"
      >
        <el-table-column prop="item" label="项目" min-width="240" />
        <el-table-column prop="amount" label="金额" min-width="150" align="right">
          <template #default="{ row }">
            <template v-if="row.isFormula">
              <span class="formula-cell" :title="row.formulaHint">
                {{ fmt(row.amount) }}
              </span>
            </template>
            <template v-else>
              <el-input-number
                v-if="!isReadonly"
                v-model="row.amount"
                :precision="2"
                :controls="false"
                style="width: 130px"
              />
              <span v-else>{{ fmt(row.amount) }}</span>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <!-- 计算结果 -->
      <div class="result-summary">
        <div class="result-item">
          <span>使用权资产初始确认金额：</span>
          <span class="formula-cell result-amount" title="= 总额 - 扣除项">
            {{ fmt(leaseResult.rouAsset) }}
          </span>
        </div>
        <div class="result-item">
          <span>租赁负债初始确认金额：</span>
          <span class="formula-cell result-amount" title="= SUM(各组成项目)">
            {{ fmt(leaseResult.leaseLiability) }}
          </span>
        </div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>S3-8 记录首次执行新租赁准则（CAS 21）的调整。源模板含 6 个公式。</p>
      <p>F55 = F53 - F54（使用权资产 = 总额 - 扣除项）</p>
      <p>F63 = F56+F57+F58-F59-F60-F61-F62（租赁负债 = 各组成项目正加负减）</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS3Ifrs16Adjust.vue — S3-8 首次执行新租赁准则的调整
 *
 * 功能：
 * - 使用权资产 = total - deduction（6个公式）
 * - 租赁负债 = SUM(components)
 * - 使用 calcLeaseAdjust 纯函数
 */
import { ref, computed, inject } from 'vue'
import { fmtAmount } from '@/utils/formatters'
import { calcLeaseAdjust } from '../composables/useS3AdjustmentEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, label?: string) => void>('openReviewDialog')

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

// ─── 使用权资产 ──────────────────────────────────────────────────────────────

const rouTotal = ref(0)
const rouDeduction = ref(0)

const rouAssetData = computed(() => [
  { item: '租赁付款额现值', amount: rouTotal.value, isFormula: false, formulaHint: '' },
  { item: '扣除：租赁激励等', amount: rouDeduction.value, isFormula: false, formulaHint: '' },
  { item: '使用权资产初始确认', amount: leaseResult.value.rouAsset, isFormula: true, formulaHint: '= 总额 - 扣除项' },
])

// ─── 租赁负债 ────────────────────────────────────────────────────────────────

const leaseComponents = ref([0, 0, 0, 0, 0, 0, 0]) // F56~F62 (正加负减)

const leaseLiabilityData = computed(() => [
  { item: '固定付款额', amount: leaseComponents.value[0], isFormula: false, formulaHint: '' },
  { item: '实质固定付款额', amount: leaseComponents.value[1], isFormula: false, formulaHint: '' },
  { item: '基于指数的可变付款额', amount: leaseComponents.value[2], isFormula: false, formulaHint: '' },
  { item: '减：租赁激励', amount: leaseComponents.value[3], isFormula: false, formulaHint: '' },
  { item: '减：初始直接费用', amount: leaseComponents.value[4], isFormula: false, formulaHint: '' },
  { item: '减：预计拆除恢复成本', amount: leaseComponents.value[5], isFormula: false, formulaHint: '' },
  { item: '减：已付租赁付款额', amount: leaseComponents.value[6], isFormula: false, formulaHint: '' },
  { item: '租赁负债初始确认', amount: leaseResult.value.leaseLiability, isFormula: true, formulaHint: '= SUM(正项) - SUM(减项)' },
])

// ─── 公式引擎 ────────────────────────────────────────────────────────────────

const leaseResult = computed(() => {
  return calcLeaseAdjust({
    total: rouTotal.value,
    deduction: rouDeduction.value,
    components: leaseComponents.value,
  })
})

function handleSave() {
  // TODO: 保存
}

function handleReview() {
  openReviewDialog?.('s3-ifrs16-adjust', '首次执行新租赁准则的调整 S3-8')
}
</script>

<style scoped>
.s3-ifrs16-adjust {
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
  font-size: 13px;
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
.sub-section-title {
  margin: 16px 0 8px;
  font-size: 14px;
  color: #303133;
}
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
.result-summary {
  margin-top: 16px;
  padding: 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
}
.result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 14px;
}
.result-amount {
  font-size: 15px;
  font-weight: 500;
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
