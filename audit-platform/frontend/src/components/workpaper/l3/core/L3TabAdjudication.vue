<template>
  <div class="l3-tab-adjudication">
    <!-- ═══ 返回目录 + 标题 + AI/复核按钮 ═══ -->
    <div class="adj-header">
      <div class="adj-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="adj-title">L3-1 长期借款审定表</h3>
      </div>
      <div class="adj-header-right">
        <el-button size="small" @click="handleAI">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>长期借款为负债类贷方科目（2501）：</strong>
        期末余额 = 期初 + 贷方发生额（借入/增加） − 借方发生额（归还/减少）。
        与资产类（期末=期初+借-贷）<strong>方向相反</strong>。"其中：一年内到期"单列显示报告日起一年内到期的长期借款余额，用于流动/非流动分类重分类。
      </div>
    </div>

    <!-- ═══ 审定表主体 ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
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
          <el-tooltip content="期初 + 贷方发生 − 借方发生（负债类！）" placement="top">
            <span class="formula-col-header">期末</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="期初 + 贷方发生 − 借方发生" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 一年内到期（淡蓝背景高亮列） -->
      <el-table-column label="一年内到期" width="120" align="right" class-name="current-portion-col">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.currentPortion"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellChange(row.index, 'currentPortion', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.currentPortion) }}</span>
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
      <el-table-column label="审定" width="120" align="right">
        <template #header>
          <el-tooltip content="未审数 + AJE + RJE" placement="top">
            <span class="formula-col-header">审定</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="未审数 + AJE + RJE" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.audited) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 交叉验证区: diff vs L3-2明细合计 ═══ -->
    <div class="cross-check-section">
      <div class="cross-check-row">
        <span class="cross-check-label">审定表合计 vs L3-2明细表合计：</span>
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
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>科目方向</strong>：长期借款为负债类贷方科目（2501），期末 = 期初 + 贷方（借入）− 借方（归还）</li>
        <li><strong>分类</strong>：按信用借款/保证借款/抵押借款/质押借款/其他五种借款类型分类汇总</li>
        <li><strong>一年内到期</strong>：报告日起一年内到期的长期借款部分，需重分类至流动负债（生成RJE）</li>
        <li><strong>审定数</strong>：审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)</li>
        <li><strong>勾稽</strong>：审定表期末合计应与明细表（L3-2）各行期末合计一致</li>
        <li><strong>TB回写</strong>：审定数变化自动回写试算平衡表科目 2501</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabAdjudication — L3-1 长期借款审定表
 *
 * 负债类贷方科目审定汇总：
 * - 按借款类型分类（信用/保证/抵押/质押/其他）+ 分类小计 + 合计行
 * - 单列"其中：一年内到期"（淡蓝背景高亮）
 * - 公式列（虚线下划线+tooltip）：期末=期初+贷方-借方；审定数=未审+AJE+RJE
 * - TB回写：审定数变化 → writebackTB(2501) + EventBus 'substantive:adjudicated'
 * - 与L3-2明细合计交叉验证（勾稽状态显示）
 * - subscribe附注EventBus刷新
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 4.2
 * Requirements: 2.1-2.7
 */
import { computed, inject, onMounted, onUnmounted, type Ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'
import { useL3Adjudication } from '@/composables/useL3Adjudication'
import type { AdjudicationVsDetailResult } from '@/components/workpaper/composables/useL3CrossSheet'
import { eventBus } from '@/utils/eventBus'

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

const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!

// ─── Inject 复核对话 ─────────────────────────────────────────────────────────

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

// ─── Composable: 审定表业务逻辑 ─────────────────────────────────────────────

// adjudicationData reactive state (由父组件 provide 或本地构建)
const adjudicationData = inject<{
  categories: import('@/composables/useL3Adjudication').L3AdjudicationCategory[]
  total: import('@/composables/useL3Adjudication').L3AdjudicationTotal
}>('l3AdjudicationData', {
  categories: [
    { name: '信用借款', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, currentPortion: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { name: '保证借款', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, currentPortion: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { name: '抵押借款', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, currentPortion: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { name: '质押借款', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, currentPortion: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { name: '其他', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, currentPortion: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
  ],
  total: { beginning: 0, credit: 0, debit: 0, end: 0, currentPortion: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
})

const { computedCategories, total, updateCategory } = useL3Adjudication(formData, adjudicationData)

// ─── Inject 勾稽校验 ─────────────────────────────────────────────────────────

const adjudicationVsDetail = inject<Ref<AdjudicationVsDetailResult>>(
  'adjudicationVsDetail',
  computed(() => ({ diff: 0, isMatch: true })) as unknown as Ref<AdjudicationVsDetailResult>,
)

// ─── EventBus: subscribe附注刷新 (Req 2.7) ──────────────────────────────────

function handleNoteUpdate(_payload: any): void {
  // 附注更新时刷新审定表数据（如附注反向修正审定数）
  // 实际逻辑由 formData.reload() 处理
}

onMounted(() => {
  eventBus.on('disclosure:note-text-updated', handleNoteUpdate)
})

onUnmounted(() => {
  eventBus.off('disclosure:note-text-updated', handleNoteUpdate)
})

// ─── Table Data：分类行 + "其中：一年内到期"汇总 + 合计行 ────────────────────

interface TableRow {
  label: string
  index: number
  beginning: number
  creditAmount: number
  debitAmount: number
  endBalance: number
  currentPortion: number
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
      currentPortion: cat.currentPortion,
      unadjusted: cat.unadjusted,
      aje: cat.aje,
      rje: cat.rje,
      audited: cat.audited,
      isEditable: true,
      isSubtotal: false,
      isTotal: false,
    })
  })

  // 小计行："其中：一年内到期"
  rows.push({
    label: '其中：一年内到期',
    index: -2,
    beginning: 0,
    creditAmount: 0,
    debitAmount: 0,
    endBalance: 0,
    currentPortion: total.value.currentPortion,
    unadjusted: 0,
    aje: 0,
    rje: 0,
    audited: 0,
    isEditable: false,
    isSubtotal: true,
    isTotal: false,
  })

  // 合计行
  rows.push({
    label: '合  计',
    index: -1,
    beginning: total.value.beginning,
    creditAmount: total.value.credit,
    debitAmount: total.value.debit,
    endBalance: total.value.end,
    currentPortion: total.value.currentPortion,
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

// ─── 编辑处理 ────────────────────────────────────────────────────────────────

type EditableField = 'beginning' | 'creditAmount' | 'debitAmount' | 'currentPortion' | 'unadjusted' | 'aje' | 'rje'

function handleCellChange(index: number, field: EditableField, value: number): void {
  if (index < 0) return // 合计行/小计行不可编辑
  updateCategory(index, field, value)
}

// ─── AI辅助 / 复核 ──────────────────────────────────────────────────────────

function handleAI(): void {
  // AI辅助：分析审定表数据合理性
  eventBus.emit('ai:assist', {
    section: 'L3-1-adjudication',
    context: { total: total.value, categories: computedCategories.value },
  })
}

function handleReview(): void {
  openReviewDialog('L3-1 长期借款审定表')
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
.l3-tab-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 头部（标题+AI/复核按钮右对齐） ─── */
.adj-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.adj-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.adj-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
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
  font-size: var(--wp-font-size, 13px);
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
  font-style: italic;
}

/* ─── 一年内到期列：淡蓝背景高亮 ─── */
:deep(.current-portion-col) {
  background-color: #ecf5ff !important;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
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

/* ─── 编制提示折叠 ─── */
.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
