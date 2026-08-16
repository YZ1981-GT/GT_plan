<template>
  <div class="s3-simplified-retro2">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：复核采用简化追溯调整法（分期）处理准则变更的适用条件与折现计算过程，确认分期调整后现值及累积影响数计入期初留存收益的准确性。"
      style="margin-bottom: 16px"
    />

    <!-- 蓝色渐变引导区（多步骤底稿） -->
    <div class="guide-banner">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="step-number">①</span>
          <span class="step-text">录入各租赁/合同项目的原始金额、剩余年限和分期月份比例</span>
        </div>
        <div class="guide-step">
          <span class="step-number">②</span>
          <span class="step-text">设定折现率后自动计算现值折现因子和分期调整后现值</span>
        </div>
      </div>
    </div>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>简化的追溯调整法（2）S3-10</span>
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

      <!-- 折现率设定 -->
      <div class="discount-rate-row">
        <span class="rate-label">折现率：</span>
        <el-input-number
          v-model="discountRate"
          :precision="4"
          :step="0.0025"
          :min="0"
          :max="1"
          :controls="true"
          :disabled="isReadonly"
          style="width: 160px"
        />
        <span class="rate-hint">（小数形式，如 0.05 表示 5%）</span>
      </div>

      <!-- 折现计算表（132个公式） -->
      <el-table
        :data="tableData"
        border
        stripe
        style="width: 100%; font-size: 13px"
        :cell-class-name="cellClassName"
        max-height="500"
      >
        <el-table-column type="index" label="序号" width="60" />
        <el-table-column prop="itemName" label="项目名称" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.itemName"
              placeholder="项目名称..."
            />
            <span v-else>{{ row.itemName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="原始金额" min-width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.amount"
              style="width: 110px"
            />
            <span v-else>{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="years" label="折现年份" min-width="90" align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.years"
              :precision="2"
              :min="0"
              :controls="false"
              style="width: 70px"
            />
            <span v-else>{{ row.years }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="monthRatio" label="月份比例" min-width="100" align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.monthRatio"
              :precision="4"
              :min="0"
              :max="1"
              :controls="false"
              style="width: 80px"
            />
            <span v-else>{{ row.monthRatio }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="expired" label="是否到期" width="90" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.expired" :disabled="isReadonly" />
          </template>
        </el-table-column>
        <el-table-column label="折现因子" min-width="110" align="right">
          <template #default="{ row, $index }">
            <span class="formula-cell" title="pvFactor = 1/(1+rate)^years">
              {{ fmtFactor(retroResult.pvFactors[$index]) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="现值" min-width="130" align="right">
          <template #default="{ row, $index }">
            <span class="formula-cell" title="现值 = 原始金额 × 折现因子 × 月份比例">
              {{ fmt(adjustedPV[$index]) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="非经常性损益" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.isNonRecurring" type="warning" size="small">非经常性</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计 -->
      <div class="total-row">
        <span>分期调整后现值合计：</span>
        <span class="formula-cell total-amount" title="合计 = SUM(各项现值 × 月份比例)">
          {{ fmt(totalAdjustedPV) }}
        </span>
      </div>

      <!-- 新增行 -->
      <div v-if="!isReadonly" class="add-row-action">
        <el-button size="small" type="primary" plain @click="addItem">
          + 新增折现项目
        </el-button>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>S3-10 简化的追溯调整法（2）——变体：增加分期计算（月份比例）。源模板含 132 个公式。</p>
      <p>与 S3-9 相比增加月份比例字段（如 D17=9/12），现值 = 原始金额 × 折现因子 × 月份比例。</p>
      <p>注意：S3-10 (2) 副本已合并入本页。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * GtS3SimplifiedRetro2.vue — S3-10 简化的追溯调整法（2）
 *
 * 功能：
 * - 折现计算 + 月份比例分期（132个公式）
 * - 与 S3-9 的区别：增加 monthRatio 分期计算
 * - 使用 calcSimplifiedRetro 纯函数（基础折现），再乘月份比例
 * - 蓝色渐变引导区
 * - S3-10 (2) 副本合并入此组件
 */
import { ref, computed, inject } from 'vue'
import { ElMessageBox } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'
import { calcSimplifiedRetro } from '../composables/useS3AdjustmentEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, label?: string) => void>('openReviewDialog')

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

function fmtFactor(val: number | undefined): string {
  if (val === undefined || val === null) return '-'
  return val.toFixed(6)
}

// ─── 折现率 ──────────────────────────────────────────────────────────────────

const discountRate = ref(0.05)

// ─── 数据行 ──────────────────────────────────────────────────────────────────

interface RetroItem2 {
  id: string
  itemName: string
  amount: number
  years: number
  monthRatio: number  // 月份比例（如 9/12 = 0.75）
  expired: boolean
  isNonRecurring: boolean
}

const tableData = ref<RetroItem2[]>([
  { id: '1', itemName: '', amount: 0, years: 0, monthRatio: 1, expired: false, isNonRecurring: false },
  { id: '2', itemName: '', amount: 0, years: 0, monthRatio: 1, expired: false, isNonRecurring: false },
  { id: '3', itemName: '', amount: 0, years: 0, monthRatio: 1, expired: false, isNonRecurring: false },
])

// ─── 公式引擎 ────────────────────────────────────────────────────────────────

const retroResult = computed(() => {
  return calcSimplifiedRetro({
    items: tableData.value.map(r => ({
      amount: r.amount,
      years: r.years,
      expired: r.expired,
    })),
    discountRate: discountRate.value,
  })
})

/** 分期调整后现值 = 基础现值 × 月份比例 */
const adjustedPV = computed(() => {
  return retroResult.value.pvAmounts.map((pv, i) => {
    const ratio = tableData.value[i]?.monthRatio ?? 1
    return pv * ratio
  })
})

const totalAdjustedPV = computed(() => {
  return adjustedPV.value.reduce((sum, v) => sum + v, 0)
})

function cellClassName({ column }: any): string {
  const label = column?.label || ''
  if (label === '折现因子' || label === '现值') return 'formula-col'
  return ''
}

async function addItem() {
  const { value: name } = await ElMessageBox.prompt('请输入项目名称', '新增折现项目', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '项目名称...',
  })
  if (name) {
    tableData.value.push({
      id: String(Date.now()),
      itemName: name,
      amount: 0,
      years: 0,
      monthRatio: 1,
      expired: false,
      isNonRecurring: false,
    })
  }
}

function handleSave() {
  // TODO: 保存
}

function handleReview() {
  openReviewDialog?.('s3-simplified-retro2', '简化的追溯调整法（2）S3-10')
}
</script>

<style scoped>
.s3-simplified-retro2 {
  padding: 12px;
}
.guide-banner {
  margin-bottom: 16px;
  padding: 16px 20px;
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfa 100%);
  border: 1px solid #b3d8fd;
  border-radius: 8px;
}
.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.guide-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.step-number {
  font-size: 16px;
  font-weight: 700;
  color: #409eff;
  min-width: 20px;
}
.step-text {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
  line-height: 1.5;
}
.discount-rate-row {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.rate-label {
  font-size: 14px;
  font-weight: 500;
}
.rate-hint {
  font-size: 12px;
  color: #909399;
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
.add-row-action {
  margin-top: 12px;
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
