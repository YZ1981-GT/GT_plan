<template>
  <div class="gt-trial-balance gt-fade-in">
    <!-- 顶部操作栏 -->
    <div class="gt-tb-header">
      <h2 class="gt-page-title">试算表</h2>
      <div class="gt-tb-actions">
        <el-button @click="onConsistencyCheck" :loading="checkLoading">一致性校验</el-button>
        <el-button @click="onRecalc" :loading="recalcLoading">全量重算</el-button>
        <el-button type="primary" @click="onExport">导出 Excel</el-button>
      </div>
    </div>

    <!-- 一致性校验结果 -->
    <el-alert
      v-if="consistencyResult"
      :type="consistencyResult.consistent ? 'success' : 'warning'"
      :title="consistencyResult.consistent ? '数据一致' : `发现 ${consistencyResult.issues.length} 项不一致`"
      :closable="true"
      show-icon
      style="margin-bottom: 12px"
    />

    <!-- 试算表主表 -->
    <el-table
      :data="groupedRows"
      v-loading="loading"
      border
      stripe
      style="width: 100%"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="standard_account_code" label="科目编码" width="130" />
      <el-table-column prop="account_name" label="科目名称" min-width="180" />
      <el-table-column label="未审数" width="150" align="right">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal"
            class="clickable" @click="onUnadjustedClick(row)">
            {{ fmtAmt(row.unadjusted_amount) }}
          </span>
          <span v-else class="subtotal-val">{{ fmtAmt(row.unadjusted_amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="RJE调整" width="140" align="right">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal && row.rje_adjustment !== '0'"
            class="clickable" @click="onAdjClick(row, 'RJE')">
            {{ fmtAmt(row.rje_adjustment) }}
          </span>
          <span v-else :class="{ 'subtotal-val': row._isSubtotal || row._isTotal }">
            {{ fmtAmt(row.rje_adjustment) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="AJE调整" width="140" align="right">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal && row.aje_adjustment !== '0'"
            class="clickable" @click="onAdjClick(row, 'AJE')">
            {{ fmtAmt(row.aje_adjustment) }}
          </span>
          <span v-else :class="{ 'subtotal-val': row._isSubtotal || row._isTotal }">
            {{ fmtAmt(row.aje_adjustment) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="审定数" width="150" align="right">
        <template #default="{ row }">
          <span :class="{ 'subtotal-val': row._isSubtotal || row._isTotal }">
            {{ fmtAmt(row.audited_amount) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷平衡指示器 -->
    <div class="gt-tb-balance-indicator" v-if="!loading">
      <span :class="isBalanced ? 'gt-tb-balanced' : 'gt-tb-unbalanced'">
        {{ isBalanced ? '✓ 借贷平衡' : '✗ 借贷不平衡' }}
      </span>
    </div>

    <!-- 调整分录明细弹窗 -->
    <el-dialog v-model="adjDialogVisible" :title="`${adjDialogType} 调整明细 — ${adjDialogAccount}`" width="700px">
      <el-table :data="adjDialogList" border stripe>
        <el-table-column prop="adjustment_no" label="编号" width="120" />
        <el-table-column prop="description" label="摘要" min-width="180" />
        <el-table-column prop="total_debit" label="借方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.total_debit) }}</template>
        </el-table-column>
        <el-table-column prop="total_credit" label="贷方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.total_credit) }}</template>
        </el-table-column>
        <el-table-column prop="review_status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.review_status)" size="small">
              {{ statusLabel(row.review_status) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getTrialBalance, recalcTrialBalance, checkConsistency,
  listAdjustments,
  type TrialBalanceRow, type ConsistencyResult,
} from '@/services/auditPlatformApi'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const loading = ref(false)
const recalcLoading = ref(false)
const checkLoading = ref(false)
const rows = ref<TrialBalanceRow[]>([])
const consistencyResult = ref<ConsistencyResult | null>(null)

// 调整明细弹窗
const adjDialogVisible = ref(false)
const adjDialogType = ref('')
const adjDialogAccount = ref('')
const adjDialogList = ref<any[]>([])

const CATEGORY_ORDER = ['asset', 'liability', 'equity', 'revenue', 'cost', 'expense']
const CATEGORY_LABELS: Record<string, string> = {
  asset: '资产', liability: '负债', equity: '权益',
  revenue: '收入', cost: '成本', expense: '费用',
}

interface DisplayRow extends TrialBalanceRow {
  _isSubtotal?: boolean
  _isTotal?: boolean
  _highlight?: boolean
}

const groupedRows = computed<DisplayRow[]>(() => {
  const result: DisplayRow[] = []
  const totals = { unadjusted: 0, rje: 0, aje: 0, audited: 0 }

  for (const cat of CATEGORY_ORDER) {
    const catRows = rows.value.filter(r => r.account_category === cat)
    if (!catRows.length) continue

    const sub = { unadjusted: 0, rje: 0, aje: 0, audited: 0 }
    for (const r of catRows) {
      const u = num(r.unadjusted_amount)
      const rj = num(r.rje_adjustment)
      const aj = num(r.aje_adjustment)
      const au = num(r.audited_amount)
      sub.unadjusted += u; sub.rje += rj; sub.aje += aj; sub.audited += au
      result.push({ ...r, _highlight: r.exceeds_materiality })
    }
    // 小计行
    result.push({
      standard_account_code: '',
      account_name: `${CATEGORY_LABELS[cat] || cat} 小计`,
      account_category: cat,
      unadjusted_amount: String(sub.unadjusted),
      rje_adjustment: String(sub.rje),
      aje_adjustment: String(sub.aje),
      audited_amount: String(sub.audited),
      opening_balance: null,
      exceeds_materiality: false,
      below_trivial: false,
      _isSubtotal: true,
    } as DisplayRow)

    totals.unadjusted += sub.unadjusted
    totals.rje += sub.rje
    totals.aje += sub.aje
    totals.audited += sub.audited
  }
  // 合计行
  result.push({
    standard_account_code: '',
    account_name: '合计',
    account_category: null,
    unadjusted_amount: String(totals.unadjusted),
    rje_adjustment: String(totals.rje),
    aje_adjustment: String(totals.aje),
    audited_amount: String(totals.audited),
    opening_balance: null,
    exceeds_materiality: false,
    below_trivial: false,
    _isTotal: true,
  } as DisplayRow)

  return result
})

const isBalanced = computed(() => {
  // 简化：检查合计行借贷是否平衡（审定数合计接近0）
  const totalRow = groupedRows.value.find(r => (r as DisplayRow)._isTotal)
  if (!totalRow) return true
  return Math.abs(num(totalRow.audited_amount)) < 0.01
})

function num(v: string | null | undefined): number {
  return v != null ? parseFloat(v) || 0 : 0
}

function fmtAmt(v: string | null | undefined): string {
  const n = num(v)
  if (n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: { row: DisplayRow }) {
  if (row._isTotal) return 'total-row'
  if (row._isSubtotal) return 'subtotal-row'
  if (row._highlight) return 'highlight-row'
  return ''
}

function statusTagType(s: string) {
  const m: Record<string, string> = { draft: 'info', pending_review: 'warning', approved: 'success', rejected: 'danger' }
  return m[s] || 'info'
}

function statusLabel(s: string) {
  const m: Record<string, string> = { draft: '草稿', pending_review: '待复核', approved: '已批准', rejected: '已驳回' }
  return m[s] || s
}

async function fetchData() {
  loading.value = true
  try {
    rows.value = await getTrialBalance(projectId.value, year.value)
  } finally {
    loading.value = false
  }
}

async function onRecalc() {
  recalcLoading.value = true
  try {
    await recalcTrialBalance(projectId.value, year.value)
    ElMessage.success('重算完成')
    await fetchData()
  } finally {
    recalcLoading.value = false
  }
}

async function onConsistencyCheck() {
  checkLoading.value = true
  try {
    consistencyResult.value = await checkConsistency(projectId.value, year.value)
  } finally {
    checkLoading.value = false
  }
}

function onExport() {
  // 简单实现：打开导出URL
  window.open(`/api/projects/${projectId.value}/trial-balance/export?year=${year.value}`, '_blank')
}

function onUnadjustedClick(_row: TrialBalanceRow) {
  router.push({
    name: 'Drilldown',
    params: { projectId: projectId.value },
    query: { year: String(year.value) },
  })
}

async function onAdjClick(row: TrialBalanceRow, type: string) {
  adjDialogType.value = type
  adjDialogAccount.value = `${row.standard_account_code} ${row.account_name || ''}`
  adjDialogVisible.value = true
  try {
    const result = await listAdjustments(projectId.value, year.value, {
      adjustment_type: type, page_size: 200,
    })
    // Filter by account code from line_items
    const items = Array.isArray(result) ? result : (result.items || [])
    adjDialogList.value = items.filter((e: any) =>
      e.line_items?.some((li: any) => li.standard_account_code === row.standard_account_code)
    )
  } catch {
    adjDialogList.value = []
  }
}

onMounted(fetchData)
</script>

<style scoped>
.gt-trial-balance { padding: var(--gt-space-4); }
.gt-tb-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
.gt-tb-actions { display: flex; gap: var(--gt-space-2); }
.clickable { cursor: pointer; color: var(--el-color-primary); }
.clickable:hover { text-decoration: underline; }
.subtotal-val { font-weight: 600; }
.gt-tb-balance-indicator { margin-top: var(--gt-space-3); text-align: right; font-size: var(--gt-font-size-base); }
.gt-tb-balanced { color: var(--gt-color-success); font-weight: 600; }
.gt-tb-unbalanced { color: var(--gt-color-coral); font-weight: 600; }

:deep(.subtotal-row) { background-color: var(--gt-color-primary-bg) !important; font-weight: 600; }
:deep(.total-row) { background-color: #e8e0f0 !important; font-weight: 700; }
:deep(.highlight-row) { background-color: var(--gt-color-wheat-light) !important; }
</style>
