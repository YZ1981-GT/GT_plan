<template>
  <div class="s3-simplified-retro1">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：复核采用简化追溯调整法处理准则变更的适用条件与折现计算过程，确认累积影响数计入期初留存收益的准确性。"
      style="margin-bottom: 16px"
    />

    <!-- 蓝色渐变引导区（多步骤底稿） -->
    <div class="guide-banner">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="step-number">①</span>
          <span class="step-text">录入各租赁/合同项目的原始金额、剩余年限</span>
        </div>
        <div class="guide-step">
          <span class="step-number">②</span>
          <span class="step-text">设定折现率后自动计算现值折现因子和调整后现值</span>
        </div>
      </div>
    </div>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>简化的追溯调整法（1）S3-9</span>
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

      <!-- 折现计算表（137个公式） -->
      <el-table
        :data="tableData"
        border
        stripe
        style="width: 100%; font-size: 13px"
        :cell-class-name="cellClassName"
        max-height="500"
      >
        <el-table-column type="index" label="序号" width="60" />
        <el-table-column prop="itemName" label="项目名称" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.itemName"
              placeholder="项目名称..."
            />
            <span v-else>{{ row.itemName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="原始金额" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.amount"
              :precision="2"
              :controls="false"
              style="width: 120px"
            />
            <span v-else>{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="years" label="折现年份" min-width="100" align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.years"
              :precision="2"
              :min="0"
              :controls="false"
              style="width: 80px"
            />
            <span v-else>{{ row.years }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="expired" label="是否到期" width="100" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.expired" :disabled="isReadonly" />
          </template>
        </el-table-column>
        <el-table-column label="折现因子" min-width="120" align="right">
          <template #default="{ row, $index }">
            <span class="formula-cell" title="pvFactor = 1/(1+rate)^years">
              {{ fmtFactor(retroResult.pvFactors[$index]) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="现值" min-width="140" align="right">
          <template #default="{ row, $index }">
            <span class="formula-cell" title="现值 = 原始金额 × 折现因子">
              {{ fmt(retroResult.pvAmounts[$index]) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="非经常性损益" width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.isNonRecurring" type="warning" size="small">非经常性</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计 -->
      <div class="total-row">
        <span>现值合计：</span>
        <span class="formula-cell total-amount" title="合计 = SUM(各项现值)">
          {{ fmt(retroResult.totalPV) }}
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
      <p>S3-9 简化的追溯调整法（1）：核心为折现计算。源模板含 137 个公式。</p>
      <p>公式链：剩余年限 → 折现因子 H{r} = 1/(1+$H$10)^G{r} → 现值 I{r} = B{r} × H{r}</p>
      <p>条件公式：C{r} = IF(E{r}=1, 0, B{r})——到期则现值=0。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS3SimplifiedRetro1.vue — S3-9 简化的追溯调整法（1）
 *
 * 功能：
 * - 折现计算核心：pvFactor = 1/(1+rate)^years, pv = amount × pvFactor
 * - 到期项：现值为 0
 * - 使用 calcSimplifiedRetro 纯函数
 * - 源模板 137 个公式
 * - 蓝色渐变引导区（多步骤底稿）
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

interface RetroItem {
  id: string
  itemName: string
  amount: number
  years: number
  expired: boolean
  isNonRecurring: boolean
}

const tableData = ref<RetroItem[]>([
  { id: '1', itemName: '', amount: 0, years: 0, expired: false, isNonRecurring: false },
  { id: '2', itemName: '', amount: 0, years: 0, expired: false, isNonRecurring: false },
  { id: '3', itemName: '', amount: 0, years: 0, expired: false, isNonRecurring: false },
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
      expired: false,
      isNonRecurring: false,
    })
  }
}

function handleSave() {
  // TODO: 保存
}

function handleReview() {
  openReviewDialog?.('s3-simplified-retro1', '简化的追溯调整法（1）S3-9')
}
</script>

<style scoped>
.s3-simplified-retro1 {
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
  font-size: 13px;
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
