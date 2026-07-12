<template>
  <div class="l4-tab-initial-measure">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L4-6 应付债券初始计量</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('initialMeasure')">
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
        <strong>初始计量公式：</strong>
        初始入账金额 = 发行价格 − 交易费用；溢折价 = 初始入账 − 面值（正=溢价发行，负=折价发行，零=平价发行）。
        实际利率(EIR)：使未来现金流的现值 = 初始入账金额的折现率，可通过IRR求解。
      </div>
    </div>

    <!-- ═══ 初始计量表 ═══ -->
    <el-table
      :data="computedRows"
      border
      size="small"
      style="width: 100%"
    >
      <el-table-column type="index" label="#" width="50" align="center" />

      <el-table-column prop="bondName" label="债券名称" min-width="180">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.bondName" size="small" @change="(val: string) => onUpdate($index, 'bondName', val)" />
          <span v-else>{{ row.bondName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="面值" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => onUpdate($index, 'faceValue', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.faceValue) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="发行价格" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.issuePrice" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => onUpdate($index, 'issuePrice', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.issuePrice) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="交易费用" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.transactionCost" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => onUpdate($index, 'transactionCost', val ?? 0)" />
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

      <el-table-column label="溢折价" min-width="110" align="right">
        <template #header>
          <el-tooltip content="初始入账 − 面值" placement="top">
            <span class="formula-col-header">溢折价</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tag size="small" :type="getTagType(row.premiumDiscount)">
            {{ getPremiumDiscountType(row.premiumDiscount) }}
          </el-tag>
          <span :class="['formula-value', row.premiumDiscount < 0 ? 'text-danger' : '']" style="margin-left:4px">
            {{ fmtAmount(row.premiumDiscount) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="票面利率(%)" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.couponRate * 100" :controls="false" :precision="4" size="small" style="width:100%" @change="(val: number | undefined) => onUpdate($index, 'couponRate', (val ?? 0) / 100)" />
          <span v-else>{{ (row.couponRate * 100).toFixed(4) }}%</span>
        </template>
      </el-table-column>

      <el-table-column label="期限(年)" min-width="80" align="center">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.periods" :controls="false" :min="1" size="small" style="width:100%" @change="(val: number | undefined) => onUpdate($index, 'periods', val ?? 1)" />
          <span v-else>{{ row.periods }}</span>
        </template>
      </el-table-column>

      <el-table-column label="付息方式" min-width="140">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" :model-value="row.paymentType" size="small" style="width:100%" @change="(val: string) => onUpdate($index, 'paymentType', val)">
            <el-option label="分期付息到期一次还本" value="installment" />
            <el-option label="到期一次还本付息" value="bullet" />
          </el-select>
          <span v-else>{{ row.paymentType === 'bullet' ? '到期一次还本付息' : '分期付息' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="实际利率(%)" min-width="120" align="right">
        <template #header>
          <el-tooltip content="IRR求解或手动输入" placement="top">
            <span class="formula-col-header">实际利率(%)</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <div class="eir-cell">
            <span :class="row.isEirSolved ? 'formula-value' : ''">
              {{ row.effectiveRate ? (row.effectiveRate * 100).toFixed(4) + '%' : '—' }}
            </span>
            <el-button v-if="!isReadonly" type="primary" text size="small" :loading="isSolvingEIR" @click="handleSolveEIR($index)">
              求解
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计区 ═══ -->
    <div class="summary-bar">
      <span>初始入账合计：<strong>{{ fmtAmount(totalInitialAmount) }}</strong></span>
      <span>溢折价合计：<strong>{{ fmtAmount(totalPremiumDiscount) }}</strong></span>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写初始计量审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>初始入账 = 发行价格 − 交易费用</li>
        <li>溢折价 = 初始入账 − 面值（正=溢价，负=折价）</li>
        <li>实际利率IRR求解：使未来现金流现值 = 初始入账金额</li>
        <li>求解后的初始摊余成本和EIR将传递给L4-7后续计量</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabInitialMeasure — L4-6 应付债券初始计量
 *
 * Requirements: 6.1-6.5
 * - 发行价-交易费用=初始入账
 * - 溢折价=初始入账-面值
 * - IRR求解实际利率
 * - 对接L4-7期初摊余成本
 */
import { computed, inject, onMounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useL4FormData } from '../../composables/useL4FormData'
import { useL4InitialMeasure, type L4InitialMeasureRow } from '../../composables/useL4InitialMeasure'

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

const measureRows = ref<L4InitialMeasureRow[]>([])

const {
  isSolvingEIR,
  computedRows,
  totalInitialAmount,
  totalPremiumDiscount,
  updateRow,
  solveRowEIR,
  getPremiumDiscountType: _getPdType,
} = useL4InitialMeasure(formData, measureRows)

// ─── 审计说明 ─────────────────────────────────────────────────────────────────

const auditNote = ref('')

function saveAuditNote() {
  formData.debouncedSave('L4-6-auditNote', { remark: auditNote.value || null })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function onUpdate(index: number, field: keyof L4InitialMeasureRow, value: string | number | boolean) {
  updateRow(index, field, value)
}

function handleSolveEIR(index: number) {
  solveRowEIR(index)
}

function getPremiumDiscountType(val: number): string {
  if (val > 0.01) return '溢价'
  if (val < -0.01) return '折价'
  return '平价'
}

function getTagType(val: number): 'success' | 'danger' | 'info' {
  if (val > 0.01) return 'success'
  if (val < -0.01) return 'danger'
  return 'info'
}

function handleAI(_section: string) {}
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
.l4-tab-initial-measure {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.text-danger { color: #f56c6c !important; }

.eir-cell { display: flex; align-items: center; gap: 4px; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

.summary-bar {
  display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px;
  background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266;
}

.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

.l4-details-tip {
  margin-top: 16px; padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266;
}
.l4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
