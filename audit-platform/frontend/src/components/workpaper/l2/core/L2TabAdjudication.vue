<template>
  <div class="l2-tab-adjudication">
    <!-- ═══ 标题行 + 复核按钮 ═══ -->
    <div class="adj-header">
      <h3 class="adj-title">L2-1 应付利息审定表</h3>
      <div class="adj-header-actions">
        <el-button
          v-if="!isReadonly"
          type="primary"
          text
          size="small"
          @click="handleReview"
        >
          复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>负债类贷方科目方向铁律：</strong>
        期末余额 = 期初 + 贷方发生额（计提/增加） − 借方发生额（支付/减少）。
        与资产类（期末=期初+借-贷）<strong>方向相反</strong>。应付利息汇聚L1短期借款、L3长期借款、L4应付债券的利息计提。
      </div>
    </div>

    <!-- ═══ 勾稽校验指示器 ═══ -->
    <div class="cross-check-indicator">
      <span class="cross-check-label">审定表 vs 明细表：</span>
      <span :class="crossCheckClass">
        <template v-if="adjudicationVsDetail.isMatch">
          ✓ 匹配
        </template>
        <template v-else>
          ✗ 差额 {{ fmtAmount(adjudicationVsDetail.diff) }}
        </template>
      </span>
    </div>

    <!-- ═══ 审定表主体（el-card包裹） ═══ -->
    <el-card shadow="never" class="adj-table-card">
      <el-table
        :data="tableData"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- 项目列 -->
        <el-table-column prop="label" label="项目" min-width="150" fixed>
          <template #default="{ row }">
            <span :class="{ 'row-bold': row.isTotal }">{{ row.label }}</span>
          </template>
        </el-table-column>

        <!-- 期初 -->
        <el-table-column label="期初" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.isEditable && !isReadonly">
              <el-input-number
                :model-value="row.beginBalance"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleCellChange(row.rowKey, 'beginBalance', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>

        <!-- 贷方发生（计提） -->
        <el-table-column label="贷方(计提)" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.isEditable && !isReadonly">
              <el-input-number
                :model-value="row.creditAmount"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleCellChange(row.rowKey, 'creditAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 借方发生（支付） -->
        <el-table-column label="借方(支付)" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.isEditable && !isReadonly">
              <el-input-number
                :model-value="row.debitAmount"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleCellChange(row.rowKey, 'debitAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 期末（公式列：虚线下划线+cursor:help+tooltip） -->
        <el-table-column label="期末" min-width="120" align="right">
          <template #header>
            <el-tooltip content="期末 = 期初 + 贷方(计提) − 借方(支付)（负债类！）" placement="top">
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
        <el-table-column label="未审" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.isEditable && !isReadonly">
              <el-input-number
                :model-value="row.unadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleCellChange(row.rowKey, 'unadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- AJE -->
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row.isEditable && !isReadonly">
              <el-input-number
                :model-value="row.aje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleCellChange(row.rowKey, 'aje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- RJE -->
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row.isEditable && !isReadonly">
              <el-input-number
                :model-value="row.rje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleCellChange(row.rowKey, 'rje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- 审定数（公式列：虚线下划线+cursor:help+tooltip） -->
        <el-table-column label="审定" min-width="120" align="right">
          <template #header>
            <el-tooltip content="审定 = 未审 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="审定 = 未审 + AJE + RJE" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ TB回写按钮 ═══ -->
    <div class="adj-footer">
      <el-button
        type="primary"
        :disabled="isReadonly || isSubmitting"
        :loading="isSubmitting"
        @click="handleSubmit"
      >
        TB回写
      </el-button>
      <span class="footer-hint">回写审定数至试算平衡表（科目2231应付利息）</span>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>科目方向</strong>：应付利息为负债类贷方科目，期末 = 期初 + 贷方（计提）− 借方（支付）</li>
        <li><strong>分类</strong>：按利息来源分类：短期借款利息 / 长期借款利息 / 应付债券利息</li>
        <li><strong>审定数</strong>：审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)</li>
        <li><strong>勾稽</strong>：审定表期末合计应与明细表（L2-2）各行期末合计一致</li>
        <li><strong>TB回写</strong>：审定数变化点击回写按钮写入试算平衡表科目 2231</li>
        <li><strong>联动</strong>：L1短期借款/L3长期借款利息测算 → 本表计提核对 → L8财务费用</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabAdjudication — L2-1 应付利息审定表
 *
 * 负债类贷方单区块审定表：
 * - 按来源分类（短期借款利息/长期借款利息/应付债券利息）+ 合计行
 * - 公式列（虚线下划线+tooltip）：期末=期初+贷方-借方；审定=未审+AJE+RJE
 * - TB回写：审定数 → writebackTB(2231) + EventBus 'substantive:adjudicated'
 * - 与L2-2明细合计交叉验证（adjudicationVsDetail指示器）
 * - 复核按钮（inject openReviewDialog）
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 4.2
 * Requirements: 2.1-2.7
 *
 * 科目：2231 应付利息（贷方/负债类！）
 */
import { computed, ref, inject, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useL2FormData } from '../../composables/useL2FormData'
import { useL2Adjudication, type AdjudicationRow } from '../../composables/useL2Adjudication'
import { useL2CrossSheet } from '../../composables/useL2CrossSheet'

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
  writebackTB,
} = useL2FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// 加载数据
loadData()

// ─── Composable: useL2Adjudication ──────────────────────────────────────────

const {
  rows,
  subtotalRow,
  totalAuditedAmount,
  updateCell,
  submitAdjudication,
} = useL2Adjudication({
  allResponses,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  saveField,
  debouncedSave,
  writebackTB,
})

// ─── Composable: useL2CrossSheet（勾稽校验） ────────────────────────────────

const { adjudicationVsDetail } = useL2CrossSheet(allResponses)

// ─── Table Data：数据行 + 合计行 ─────────────────────────────────────────────

interface TableRow extends AdjudicationRow {
  isTotal: boolean
}

const tableData = computed<TableRow[]>(() => {
  const dataRows: TableRow[] = rows.value.map(r => ({
    ...r,
    isTotal: false,
  }))

  // 合计行
  dataRows.push({
    ...subtotalRow.value,
    isTotal: true,
  })

  return dataRows
})

// ─── 勾稽校验状态样式 ────────────────────────────────────────────────────────

const crossCheckClass = computed(() => ({
  'cross-check-match': adjudicationVsDetail.value.isMatch,
  'cross-check-diff': !adjudicationVsDetail.value.isMatch,
}))

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: TableRow }): string {
  if (row.isTotal) return 'total-row'
  return ''
}

// ─── 编辑处理 ────────────────────────────────────────────────────────────────

function handleCellChange(rowKey: string, field: string, value: number): void {
  if (rowKey === '__subtotal__') return // 合计行不可编辑
  updateCell(rowKey, field, value)
}

// ─── TB回写提交 ──────────────────────────────────────────────────────────────

const isSubmitting = ref(false)

async function handleSubmit(): Promise<void> {
  isSubmitting.value = true
  try {
    await submitAdjudication()
    ElMessage.success('审定数已回写至试算平衡表（科目2231）')
  } catch {
    ElMessage.error('回写失败，请稍后重试')
  } finally {
    isSubmitting.value = false
  }
}

// ─── 复核 ────────────────────────────────────────────────────────────────────

function handleReview(): void {
  openReviewDialog('L2-1-adjudication', 'L2-1 应付利息审定表')
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
.l2-tab-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 标题行 + 复核按钮右对齐 ─── */
.adj-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.adj-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.adj-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
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

/* ─── 勾稽校验指示器 ─── */
.cross-check-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
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

/* ─── 审定表卡片 ─── */
.adj-table-card {
  margin-bottom: 16px;
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

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── TB回写按钮区域 ─── */
.adj-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.footer-hint {
  font-size: 12px;
  color: #909399;
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
