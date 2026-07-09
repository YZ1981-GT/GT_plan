<template>
  <div class="l4-tab-adjudication">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L4-1 应付债券审定表</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('adjudication')">
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
        <strong>应付债券为负债类贷方科目（2502）：</strong>
        期末余额 = 期初 + 贷方发生额（发行/利息调整增加） − 借方发生额（兑付/减少）。
        审定数 = 未审数 + AJE + RJE。各品种（普通债券/可转换债券）下分"成本/利息调整/应计利息"三项+品种小计。
      </div>
    </div>

    <!-- ═══ 审定表主体 ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      show-summary
      :summary-method="getSummaries"
    >
      <!-- 项目（品种+子项） -->
      <el-table-column prop="label" label="项目" min-width="160" fixed>
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.isSubtotal }">{{ row.label }}</span>
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
              @change="(val: number | undefined) => onCellChange(row.rowIndex, 'beginning', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.beginning) }}</span>
        </template>
      </el-table-column>

      <!-- 贷方发生（发行+利息调整） -->
      <el-table-column label="贷方发生" width="130" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.creditAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => onCellChange(row.rowIndex, 'creditAmount', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 借方发生（兑付） -->
      <el-table-column label="借方发生" width="130" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.debitAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => onCellChange(row.rowIndex, 'debitAmount', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 期末（公式列） -->
      <el-table-column label="期末" width="120" align="right">
        <template #header>
          <el-tooltip content="期初 + 贷方 − 借方（负债类贷方！）" placement="top">
            <span class="formula-col-header">期末</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
        </template>
      </el-table-column>

      <!-- 未审数 -->
      <el-table-column label="未审数" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.unadjusted"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => onCellChange(row.rowIndex, 'unadjusted', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- AJE -->
      <el-table-column label="AJE" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.aje"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => onCellChange(row.rowIndex, 'aje', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.aje) }}</span>
        </template>
      </el-table-column>

      <!-- RJE -->
      <el-table-column label="RJE" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.rje"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => onCellChange(row.rowIndex, 'rje', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.rje) }}</span>
        </template>
      </el-table-column>

      <!-- 审定数（公式列） -->
      <el-table-column label="审定数" width="120" align="right">
        <template #header>
          <el-tooltip content="未审 + AJE + RJE" placement="top">
            <span class="formula-col-header">审定数</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 交叉验证区 ═══ -->
    <div class="cross-check-section">
      <span class="cross-check-label">与明细表L4-2交叉验证：</span>
      <el-tag :type="crossCheckOk ? 'success' : 'danger'" size="small">
        {{ crossCheckOk ? '✓ 一致' : '✗ 差异 ' + crossCheckDiff.toFixed(2) + ' 元' }}
      </el-tag>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
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
        placeholder="请填写审定表审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>负债类贷方科目：期末 = 期初 + 贷方 − 借方</li>
        <li>各品种下分：成本（面值）/ 利息调整（溢折价摊销余额）/ 应计利息（到期一次还本付息累计）</li>
        <li>品种小计 = 成本 + 利息调整 + 应计利息</li>
        <li>审定数变化自动回写 TB（科目2502）并通知附注组件</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabAdjudication — L4-1 应付债券审定表
 *
 * Requirements: 2.1-2.7
 * - 负债类单区块：品种(普通/可转换)×子项(成本/利息调整/应计利息/小计)
 * - 公式列：endBalance = 期初+贷方-借方, audited = 未审+AJE+RJE
 * - TB回写(2502) + EventBus 'substantive:adjudicated'
 */
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useL4FormData } from '../../../composables/useL4FormData'
import { useL4Adjudication, type L4AdjudicationRow } from '../../../composables/useL4Adjudication'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useL4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 审定表行数据 ─────────────────────────────────────────────────────────────

const adjudicationData = reactive({
  rows: [
    { variety: '普通债券', subItem: '成本', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { variety: '普通债券', subItem: '利息调整', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { variety: '普通债券', subItem: '应计利息', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { variety: '普通债券', subItem: '小计', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { variety: '可转换债券', subItem: '成本', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { variety: '可转换债券', subItem: '利息调整', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { variety: '可转换债券', subItem: '应计利息', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { variety: '可转换债券', subItem: '小计', beginning: 0, creditAmount: 0, debitAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
  ] as L4AdjudicationRow[],
  total: { beginning: 0, credit: 0, debit: 0, end: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
})

const { computedRows, varietySubtotals, total, updateRow, saveAndWriteback } = useL4Adjudication(formData, adjudicationData)

// ─── 表格数据渲染 ─────────────────────────────────────────────────────────────

interface TableRow {
  label: string
  rowIndex: number
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
}

const tableData = computed<TableRow[]>(() => {
  const rows = computedRows.value
  return rows.map((r, i) => ({
    label: r.subItem === '小计' ? `${r.variety}（小计）` : `${r.variety}—${r.subItem}`,
    rowIndex: i,
    beginning: r.beginning,
    creditAmount: r.creditAmount,
    debitAmount: r.debitAmount,
    endBalance: r.endBalance,
    unadjusted: r.unadjusted,
    aje: r.aje,
    rje: r.rje,
    audited: r.audited,
    isEditable: r.subItem !== '小计',
    isSubtotal: r.subItem === '小计',
  }))
})

// ─── 合计行 ───────────────────────────────────────────────────────────────────

function getSummaries({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const t = total.value
  columns.forEach((col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    const vals = [t.beginning, t.credit, t.debit, t.end, t.unadjusted, t.aje, t.rje, t.audited]
    sums[index] = fmtAmount(vals[index - 1] ?? 0)
  })
  return sums
}

// ─── 交叉验证 ─────────────────────────────────────────────────────────────────

const crossCheckDiff = ref(0)
const crossCheckOk = computed(() => Math.abs(crossCheckDiff.value) <= 0.01)

// ─── 审计说明 ─────────────────────────────────────────────────────────────────

const auditNote = ref('')

function saveAuditNote() {
  formData.debouncedSave('L4-1-auditNote', { remark: auditNote.value || null })
}

// ─── 操作 ─────────────────────────────────────────────────────────────────────

function onCellChange(rowIndex: number, field: 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje', value: number) {
  updateRow(rowIndex, field, value)
}

function handleAI(_section: string) {
  // AI辅助钩子（集成时实现）
}

function handleReview() {
  openReviewDialog?.()
}

function getRowClassName({ row }: { row: TableRow }) {
  if (row.isSubtotal) return 'subtotal-row'
  return ''
}

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 加载 ─────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l4-tab-adjudication {
  padding: 12px;
  font-size: 13px;
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
  font-size: 13px;
  color: #6b5900;
  line-height: 1.6;
}

.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-value {
  color: #409eff;
  font-weight: 500;
}

.row-bold {
  font-weight: 600;
}

:deep(.subtotal-row) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

:deep(.el-table) {
  font-size: 13px;
}

.cross-check-section {
  margin: 12px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.cross-check-label {
  color: #606266;
}

.audit-note-card {
  margin-top: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.l4-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
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
