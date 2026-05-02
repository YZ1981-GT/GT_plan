<template>
  <div class="gt-trial-balance gt-fade-in">
    <!-- 页面横幅 -->
    <div class="gt-tb-banner">
      <div class="gt-tb-banner-row1">
        <el-button text style="color: #fff; font-size: 13px; padding: 0; margin-right: 8px" @click="router.push('/projects')">← 返回</el-button>
        <h2 class="gt-tb-title">试算表</h2>
        <div class="gt-tb-info-bar">
          <div class="gt-tb-info-item">
            <span class="gt-tb-info-label">单位</span>
            <el-select v-model="selectedProjectId" size="small" class="gt-tb-unit-select" filterable @change="onProjectChange">
              <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </div>
          <div class="gt-tb-info-sep" />
          <div class="gt-tb-info-item">
            <span class="gt-tb-info-label">年度</span>
            <el-select v-model="selectedYear" size="small" class="gt-tb-year-select" @change="onYearChange">
              <el-option v-for="y in yearOptions" :key="y" :label="y + '年'" :value="y" />
            </el-select>
          </div>
          <div class="gt-tb-info-sep" />
          <div class="gt-tb-info-item">
            <span class="gt-tb-info-badge">{{ rows.length }} 个科目</span>
          </div>
        </div>
      </div>
      <div class="gt-tb-banner-row2">
        <el-tooltip content="检查试算表与四表数据的一致性" placement="bottom">
          <el-button size="small" @click="onConsistencyCheck" :loading="checkLoading">✅ 一致性校验</el-button>
        </el-tooltip>
        <el-tooltip content="从四表数据重新计算未审数、调整数、审定数（需先导入数据）" placement="bottom">
          <el-button size="small" @click="onRecalc" :loading="recalcLoading">🔄 全量重算</el-button>
        </el-tooltip>
        <el-button size="small" @click="onExport">📤 导出Excel</el-button>
        <el-button size="small" @click="showFormulaManager = true">⚙️ 公式管理</el-button>
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

    <!-- 空数据引导提示 -->
    <el-alert
      v-if="!loading && rows.length === 0"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #title>
        <span>试算表暂无数据</span>
      </template>
      <div style="font-size: 12px; line-height: 1.8; margin-top: 4px">
        请先完成以下步骤：① 导入账套数据（科目余额表）→ ② 完成科目映射 → ③ 点击"全量重算"生成试算表。
        <el-button type="primary" text size="small" @click="router.push({ path: `/projects/${projectId}/ledger`, query: { import: '1' } })">前往导入 →</el-button>
      </div>
    </el-alert>

    <!-- 试算表主表 -->
    <el-table
      :data="groupedRows"
      v-loading="loading"
      border
      stripe
      style="width: 100%"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="standard_account_code" label="科目编码" width="130">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal && getLinkedWp(row.standard_account_code)"
            class="clickable" @click="onOpenWorkpaper(row.standard_account_code)"
            :title="'打开底稿 ' + getLinkedWp(row.standard_account_code)?.wp_name">
            {{ row.standard_account_code }}
            <el-icon style="margin-left:2px; font-size:11px; vertical-align:middle"><Link /></el-icon>
          </span>
          <span v-else>{{ row.standard_account_code }}</span>
        </template>
      </el-table-column>
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
            class="clickable" @click="onAdjClick(row, 'rje')">
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
            class="clickable" @click="onAdjClick(row, 'aje')">
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
      <el-table-column label="底稿状态" width="100" align="center">
        <template #default="{ row }">
          <el-tooltip v-if="row.wp_consistency?.status === 'consistent'" content="底稿审定数一致" placement="top">
            <span style="color: #28a745; cursor: pointer" @dblclick="openWorkpaper(row)">✅</span>
          </el-tooltip>
          <el-tooltip v-else-if="row.wp_consistency?.status === 'inconsistent'" :content="`差异 ${row.wp_consistency.diff_amount}`" placement="top">
            <span style="color: #FF5149; cursor: pointer" @dblclick="openWorkpaper(row)">⚠️</span>
          </el-tooltip>
          <span v-else style="color: #ccc">—</span>
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
    <el-dialog append-to-body v-model="adjDialogVisible" :title="`${adjDialogType} 调整明细 — ${adjDialogAccount}`" width="700px">
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

    <!-- 公式管理弹窗 -->
    <FormulaManagerDialog
      v-model="showFormulaManager"
      :rows="rows"
      :project-id="projectId"
      :year="year"
      @applied="fetchData"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Link } from '@element-plus/icons-vue'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import {
  getTrialBalance, recalcTrialBalance, checkConsistency,
  getProjectAuditYear, listAdjustments,
  type TrialBalanceRow, type ConsistencyResult,
} from '@/services/auditPlatformApi'
import { getAllWpMappings, type WpAccountMapping } from '@/services/workpaperApi'
import { useProjectSelector } from '@/composables/useProjectSelector'

const route = useRoute()
const router = useRouter()
const {
  projectId, selectedProjectId, projectOptions, selectedYear, yearOptions,
  onProjectChange, onYearChange, loadProjectOptions, syncFromRoute,
} = useProjectSelector('trial-balance')

const routeYear = computed(() => {
  const value = Number(route.query.year)
  return Number.isFinite(value) && value > 2000 ? value : null
})
const projectYear = ref<number | null>(null)
const year = computed(() => routeYear.value ?? projectYear.value ?? new Date().getFullYear())

const loading = ref(false)
const recalcLoading = ref(false)
const checkLoading = ref(false)
const showFormulaManager = ref(false)
const rows = ref<TrialBalanceRow[]>([])
const consistencyResult = ref<ConsistencyResult | null>(null)

// 调整明细弹窗
const adjDialogVisible = ref(false)
const adjDialogType = ref('')
const adjDialogAccount = ref('')
const adjDialogList = ref<any[]>([])

// 底稿-科目映射
const wpMappings = ref<WpAccountMapping[]>([])
const wpMappingIndex = ref<Record<string, WpAccountMapping>>({})

function getLinkedWp(accountCode: string): WpAccountMapping | undefined {
  return wpMappingIndex.value[accountCode]
}

function onOpenWorkpaper(accountCode: string) {
  const mapping = getLinkedWp(accountCode)
  if (!mapping) return
  // 跳转到底稿列表页，高亮对应底稿
  router.push({
    path: `/projects/${projectId.value}/workpapers`,
    query: { highlight: mapping.wp_code },
  })
}

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

async function ensureProjectYear() {
  if (routeYear.value !== null) {
    projectYear.value = null
    return
  }
  try {
    projectYear.value = await getProjectAuditYear(projectId.value)
  } catch {
    projectYear.value = null
  }
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
  import('@/services/commonApi').then(({ downloadFileAsBlob }) => {
    downloadFileAsBlob(`/api/projects/${projectId.value}/trial-balance/export?year=${year.value}`, `试算表_${year.value}.xlsx`)
  })
}

function openWorkpaper(row: TrialBalanceRow) {
  const wpId = (row as any).wp_consistency?.wp_id
  if (wpId) {
    router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId } })
  } else {
    ElMessage.info('该科目未关联底稿')
  }
}

function onUnadjustedClick(_row: TrialBalanceRow) {
  router.push({
    name: 'Drilldown',
    params: { projectId: projectId.value },
    query: { year: String(year.value) },
  })
}

async function onAdjClick(row: TrialBalanceRow, type: string) {
  adjDialogType.value = type.toUpperCase()
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

watch(
  () => [projectId.value, routeYear.value],
  async () => {
    await ensureProjectYear()
    syncFromRoute()
    selectedYear.value = year.value
    await fetchData()
    if (!projectOptions.value.length) loadProjectOptions()
    // 加载底稿-科目映射
    try {
      wpMappings.value = await getAllWpMappings(projectId.value)
      const idx: Record<string, WpAccountMapping> = {}
      for (const m of wpMappings.value) {
        for (const code of m.account_codes) {
          idx[code] = m
        }
      }
      wpMappingIndex.value = idx
    } catch { /* ignore */ }
  },
  { immediate: true }
)
</script>

<style scoped>
  .gt-trial-balance { padding: var(--gt-space-5); }

  /* ── 页面横幅 ── */
  .gt-tb-banner {
    display: flex; flex-direction: column; gap: 10px;
    background: var(--gt-gradient-primary);
    border-radius: var(--gt-radius-lg);
    padding: 18px 28px;
    margin-bottom: var(--gt-space-5);
    color: #fff;
    position: relative; overflow: hidden;
    box-shadow: 0 4px 20px rgba(75, 45, 119, 0.2);
    background-image: var(--gt-gradient-primary), linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
    background-size: 100% 100%, 20px 20px, 20px 20px;
  }
  .gt-tb-banner::before {
    content: '';
    position: absolute; top: -40%; right: -10%;
    width: 45%; height: 180%;
    background: radial-gradient(ellipse, rgba(255,255,255,0.07) 0%, transparent 65%);
    pointer-events: none;
  }
  .gt-tb-banner-row1 {
    display: flex; align-items: center; gap: 16px;
    position: relative; z-index: 1;
  }
  .gt-tb-title { margin: 0; font-size: 18px; font-weight: 700; white-space: nowrap; }
  .gt-tb-info-bar {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  }
  .gt-tb-info-item {
    display: flex; align-items: center; gap: 4px;
  }
  .gt-tb-info-label {
    font-size: 11px; opacity: 0.8; white-space: nowrap;
  }
  .gt-tb-info-badge {
    font-size: 11px; background: rgba(255,255,255,0.18); padding: 2px 10px;
    border-radius: 10px; white-space: nowrap;
  }
  .gt-tb-info-sep {
    width: 1px; height: 16px; background: rgba(255,255,255,0.25);
  }
  .gt-tb-unit-select, .gt-tb-year-select {
    width: 160px;
  }
  .gt-tb-unit-select :deep(.el-input__wrapper),
  .gt-tb-year-select :deep(.el-input__wrapper) {
    background: rgba(255,255,255,0.15) !important;
    border: 1px solid rgba(255,255,255,0.25) !important;
    box-shadow: none !important;
  }
  .gt-tb-unit-select :deep(.el-input__inner),
  .gt-tb-year-select :deep(.el-input__inner) {
    color: #fff !important; font-size: 12px;
  }
  .gt-tb-unit-select :deep(.el-input__suffix),
  .gt-tb-year-select :deep(.el-input__suffix) {
    color: rgba(255,255,255,0.7) !important;
  }
  .gt-tb-banner-row2 {
    display: flex; gap: 8px; align-items: center;
    position: relative; z-index: 1;
  }
  .gt-tb-banner-row2 .el-button {
    background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff;
  }
  .gt-tb-banner-row2 .el-button:hover { background: rgba(255,255,255,0.25); }

  .clickable {
    cursor: pointer; color: var(--gt-color-primary); font-weight: 500;
    transition: color var(--gt-transition-fast);
  }
  .clickable:hover { color: var(--gt-color-primary-light); text-decoration: underline; }
  .subtotal-val { font-weight: 700; }

  .gt-tb-balance-indicator {
    margin-top: var(--gt-space-4); text-align: right;
    font-size: var(--gt-font-size-base);
  }
  .gt-tb-balanced {
    color: var(--gt-color-success); font-weight: 600;
    padding: 6px 14px; border-radius: var(--gt-radius-full);
    background: var(--gt-color-success-light);
    display: inline-flex; align-items: center; gap: 4px;
  }
  .gt-tb-unbalanced {
    color: var(--gt-color-coral); font-weight: 600;
    padding: 6px 14px; border-radius: var(--gt-radius-full);
    background: var(--gt-color-coral-light);
    display: inline-flex; align-items: center; gap: 4px;
  }

  :deep(.subtotal-row) {
    background: linear-gradient(90deg, #f8f5fd, var(--gt-color-primary-bg)) !important;
    font-weight: 600;
  }
  :deep(.subtotal-row td) { border-bottom: 1px solid var(--gt-color-primary-lighter) !important; }
  :deep(.total-row) {
    background: linear-gradient(90deg, #ece4f5, #e8e0f0) !important;
    font-weight: 700;
  }
  :deep(.total-row td) { border-bottom: 2px solid var(--gt-color-primary-lighter) !important; }
  :deep(.highlight-row) {
    background: linear-gradient(90deg, #fffbf0, var(--gt-color-wheat-light)) !important;
  }

  :deep(.el-tabs__item.is-active) { font-weight: 600; }
</style>
