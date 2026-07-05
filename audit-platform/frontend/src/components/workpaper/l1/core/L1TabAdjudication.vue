<template>
  <div class="l1-tab-adjudication">
    <!-- ═══ 返回目录 + 标题 ═══ -->
    <div class="adj-header">
      <el-button text size="small" @click="$emit('navigate', '底稿目录')">
        ← 返回目录
      </el-button>
      <h3 class="adj-title">L1-1 短期借款审定表</h3>
    </div>

    <!-- ═══ 方法论上下文（琥珀色：负债类方向说明） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>负债类贷方科目方向铁律：</strong>
        期末余额 = 期初 + 贷方发生额（借入/增加） − 借方发生额（归还/减少）。
        与资产类（期末=期初+借-贷）<strong>方向相反</strong>。此为 L 筹资循环（L1~L7）所有底稿的共同规则。
      </div>
    </div>

    <!-- ═══ 审定表主体 ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      :span-method="spanMethod"
    >
      <!-- 项目列 -->
      <el-table-column prop="label" label="项目" min-width="140" fixed>
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.isSubtotal || row.isTotal }">{{ row.label }}</span>
        </template>
      </el-table-column>

      <!-- 期初 -->
      <el-table-column label="期初" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.beginning"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellChange(row.index, 'beginning', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.beginning) }}</span>
        </template>
      </el-table-column>

      <!-- 贷方发生（借入） -->
      <el-table-column label="贷方发生(借入)" width="130" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.creditAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellChange(row.index, 'creditAmount', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 借方发生（归还） -->
      <el-table-column label="借方发生(归还)" width="130" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.debitAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellChange(row.index, 'debitAmount', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 期末（公式列） -->
      <el-table-column label="期末" width="120" align="right">
        <template #header>
          <el-tooltip content="期末 = 期初 + 贷方(借入) − 借方(归还)（负债类！）" placement="top">
            <span class="formula-col-header">期末</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="期末 = 期初 + 贷方 − 借方" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 未审 -->
      <el-table-column label="未审" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.unadjusted"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellChange(row.index, 'unadjusted', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- AJE -->
      <el-table-column label="AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.aje"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellChange(row.index, 'aje', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.aje) }}</span>
        </template>
      </el-table-column>

      <!-- RJE -->
      <el-table-column label="RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.rje"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellChange(row.index, 'rje', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.rje) }}</span>
        </template>
      </el-table-column>

      <!-- 审定数（公式列） -->
      <el-table-column label="审定数" width="120" align="right">
        <template #header>
          <el-tooltip content="审定数 = 未审 + AJE + RJE" placement="top">
            <span class="formula-col-header">审定数</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="审定数 = 未审 + AJE + RJE" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.audited) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 勾稽校验状态（与明细表对比） ═══ -->
    <div class="cross-check-section">
      <div class="cross-check-row">
        <span class="cross-check-label">审定表合计 vs 明细表合计：</span>
        <span :class="crossCheckClass">
          <template v-if="crossCheckResult.isMatch">
            ✓ 匹配
          </template>
          <template v-else>
            ✗ 差额 {{ fmtAmount(crossCheckResult.diff) }}
          </template>
        </span>
      </div>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>科目方向</strong>：短期借款为负债类贷方科目，期末 = 期初 + 贷方（借入）− 借方（归还）</li>
        <li><strong>分类</strong>：按信用/保证/抵押/质押四种借款类型分类汇总</li>
        <li><strong>审定数</strong>：审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)</li>
        <li><strong>勾稽</strong>：审定表期末合计应与明细表（L1-2）各行期末合计一致</li>
        <li><strong>TB回写</strong>：审定数变化自动回写试算平衡表科目 2001</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabAdjudication — L1-1 短期借款审定表
 *
 * 负债类贷方科目审定汇总：
 * - 按借款类型分类（信用/保证/抵押/质押）+ 分类小计 + 合计行
 * - 公式列（虚线下划线+tooltip）：期末=期初+贷方-借方；审定数=未审+AJE+RJE
 * - TB回写：审定数变化 → writebackTB(2001) + EventBus 'substantive:adjudicated'
 * - 与L1-2明细合计交叉验证（勾稽状态显示）
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 4.2
 * Requirements: 2.1-2.7
 */
import { computed, inject, type Ref } from 'vue'
import type { useL1FormData } from '@/composables/useL1FormData'
import { useL1Adjudication } from '@/composables/useL1Adjudication'
import type { AdjudicationVsDetailResult } from '@/composables/useL1CrossSheet'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject formData (由父组件 provide) ──────────────────────────────────────

const formData = inject<ReturnType<typeof useL1FormData>>('l1FormData')!

// ─── Composable: 审定表业务逻辑 ─────────────────────────────────────────────

const { computedCategories, total, updateCategory } = useL1Adjudication(formData)

// ─── Inject 勾稽校验 ─────────────────────────────────────────────────────────

const adjudicationVsDetail = inject<Ref<AdjudicationVsDetailResult>>(
  'adjudicationVsDetail',
  computed(() => ({ diff: 0, isMatch: true })) as unknown as Ref<AdjudicationVsDetailResult>,
)

// ─── Table Data：分类行 + 合计行 ─────────────────────────────────────────────

interface TableRow {
  label: string
  index: number
  beginning: number
  creditAmount: number
  debitAmount: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  isEditable: boolean
  isSubtotal: boolean
  isTotal: boolean
}

const tableData = computed<TableRow[]>(() => {
  const rows: TableRow[] = []

  // 分类行
  computedCategories.value.forEach((cat, idx) => {
    rows.push({
      label: cat.name,
      index: idx,
      beginning: cat.beginning,
      creditAmount: cat.creditAmount,
      debitAmount: cat.debitAmount,
      endBalance: cat.endBalance,
      unadjusted: cat.unadjusted,
      aje: cat.aje,
      rje: cat.rje,
      audited: cat.audited,
      isEditable: true,
      isSubtotal: false,
      isTotal: false,
    })
  })

  // 合计行
  rows.push({
    label: '合  计',
    index: -1,
    beginning: total.value.beginning,
    creditAmount: total.value.credit,
    debitAmount: total.value.debit,
    endBalance: total.value.end,
    unadjusted: total.value.unadjusted,
    aje: total.value.aje,
    rje: total.value.rje,
    audited: total.value.audited,
    isEditable: false,
    isSubtotal: false,
    isTotal: true,
  })

  return rows
})

// ─── 勾稽校验结果 ────────────────────────────────────────────────────────────

const crossCheckResult = computed<AdjudicationVsDetailResult>(() => {
  return adjudicationVsDetail.value
})

const crossCheckClass = computed(() => ({
  'cross-check-match': crossCheckResult.value.isMatch,
  'cross-check-diff': !crossCheckResult.value.isMatch,
}))

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: TableRow }): string {
  if (row.isTotal) return 'total-row'
  if (row.isSubtotal) return 'subtotal-row'
  return ''
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function spanMethod({ row, column, rowIndex, columnIndex }: any) {
  // 合计行项目列不合并（保持标准表格结构）
  return undefined
}

// ─── 编辑处理 ────────────────────────────────────────────────────────────────

type EditableField = 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje'

function handleCellChange(index: number, field: EditableField, value: number): void {
  if (index < 0) return // 合计行不可编辑
  updateCategory(index, field, value)
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
.l1-tab-adjudication {
  padding: 12px;
  font-size: 13px;
}

/* ─── 头部 ─── */
.adj-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.adj-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: 13px;
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
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

/* ─── 行粗体 ─── */
.row-bold {
  font-weight: 700;
}

/* ─── 合计行样式 ─── */
:deep(.total-row) {
  background-color: #f0f9eb !important;
  font-weight: 700;
}

:deep(.subtotal-row) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-table th .cell) {
  font-size: 13px;
  font-weight: 600;
}

/* ─── 勾稽校验区 ─── */
.cross-check-section {
  margin-top: 16px;
  padding: 10px 14px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.cross-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.cross-check-label {
  color: #606266;
}

.cross-check-match {
  color: #67c23a;
  font-weight: 600;
}

.cross-check-diff {
  color: #f56c6c;
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l1-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.l1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
