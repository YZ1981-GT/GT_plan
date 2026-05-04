<template>
  <div class="gt-trial-balance gt-fade-in" :class="{ 'gt-fullscreen': tbFullscreen }">
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
          <div class="gt-tb-info-sep" />
          <div class="gt-tb-info-item">
            <span class="gt-tb-info-label">单位</span>
            <span class="gt-tb-info-badge">{{ displayPrefs.unitSuffix }}</span>
          </div>
        </div>
      </div>
      <div class="gt-tb-banner-row2">
        <el-tooltip content="复制整个表格（可粘贴到 Word/Excel）" placement="bottom">
          <el-button size="small" @click="copyTbTable">📋 复制整表</el-button>
        </el-tooltip>
        <el-tooltip content="全屏查看（ESC 退出）" placement="bottom">
          <el-button size="small" @click="toggleTbFullscreen()">{{ tbFullscreen ? '退出全屏' : '全屏' }}</el-button>
        </el-tooltip>
        <el-tooltip content="检查试算表与四表数据的一致性" placement="bottom">
          <el-button size="small" @click="onConsistencyCheck" :loading="checkLoading">✅ 一致性校验</el-button>
        </el-tooltip>
        <el-tooltip content="从四表数据重新计算未审数、调整数、审定数（需先导入数据）" placement="bottom">
          <el-button size="small" @click="onRecalc" :loading="recalcLoading">🔄 全量重算</el-button>
        </el-tooltip>
        <el-button size="small" @click="onExport">📤 导出Excel</el-button>
        <el-button size="small" @click="showTbImport = true">📥 Excel导入</el-button>
        <el-button size="small" @click="showFormulaManager = true">⚙️ 公式管理</el-button>
      </div>
    </div>

    <!-- 视图切换：科目明细 / 试算平衡表 -->
    <div style="display:flex;gap:0;margin-bottom:8px;border-bottom:2px solid #f0edf5">
      <span class="gt-tb-view-tag" :class="{ 'gt-tb-view-tag--active': tbViewMode === 'detail' }" @click="tbViewMode = 'detail'">科目明细</span>
      <span class="gt-tb-view-tag" :class="{ 'gt-tb-view-tag--active': tbViewMode === 'summary' }" @click="tbViewMode = 'summary'; loadTbSummary()">试算平衡表</span>
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

    <!-- 搜索栏（Ctrl+F 触发，表格上方） -->
    <TableSearchBar
      :is-visible="tbSearch.isVisible.value"
      :keyword="tbSearch.keyword.value"
      :match-info="tbSearch.matchInfo.value"
      :has-matches="tbSearch.matches.value.length > 0"
      :case-sensitive="tbSearch.caseSensitive.value"
      :show-replace="false"
      @update:keyword="tbSearch.keyword.value = $event"
      @update:case-sensitive="tbSearch.caseSensitive.value = $event"
      @search="tbSearch.search()"
      @next="tbSearch.nextMatch()"
      @prev="tbSearch.prevMatch()"
      @close="tbSearch.close()"
    />

    <!-- 试算表主表（科目明细视图） -->
    <el-table
      ref="tbTableRef"
      v-if="tbViewMode === 'detail'"
      :data="groupedRows"
      v-loading="loading"
      border
      stripe
      style="width: 100%"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :row-class-name="rowClassName"
      :cell-class-name="tbCellClassName"
      @cell-click="onTbCellClick"
      @cell-contextmenu="onTbCellContextMenu"
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
        <template #default="{ row, $index }">
          <CommentTooltip :comment="tbComments.getComment('trial_balance', $index, 2)">
          <span v-if="!row._isSubtotal && !row._isTotal"
            class="clickable" @click="onUnadjustedClick(row)"
            :class="displayPrefs.amountClass(row.unadjusted_amount)">
            {{ fmt(row.unadjusted_amount) }}
          </span>
          <span v-else class="subtotal-val" :class="displayPrefs.amountClass(row.unadjusted_amount)">{{ fmt(row.unadjusted_amount) }}</span>
          </CommentTooltip>
        </template>
      </el-table-column>
      <el-table-column label="RJE调整" width="140" align="right">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal && row.rje_adjustment !== '0'"
            class="clickable" @click="onAdjClick(row, 'rje')">
            {{ fmt(row.rje_adjustment) }}
          </span>
          <span v-else :class="{ 'subtotal-val': row._isSubtotal || row._isTotal }">
            {{ fmt(row.rje_adjustment) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="AJE调整" width="140" align="right">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal && row.aje_adjustment !== '0'"
            class="clickable" @click="onAdjClick(row, 'aje')">
            {{ fmt(row.aje_adjustment) }}
          </span>
          <span v-else :class="{ 'subtotal-val': row._isSubtotal || row._isTotal }">
            {{ fmt(row.aje_adjustment) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="审定数" width="150" align="right">
        <template #default="{ row, $index }">
          <CommentTooltip :comment="tbComments.getComment('trial_balance', $index, 5)">
          <span :class="['subtotal-val', displayPrefs.amountClass(row.audited_amount)]" v-if="row._isSubtotal || row._isTotal">
            {{ fmt(row.audited_amount) }}
          </span>
          <span v-else :class="displayPrefs.amountClass(row.audited_amount)">
            {{ fmt(row.audited_amount) }}
          </span>
          </CommentTooltip>
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

    <!-- 试算平衡表视图（报表行次级别） -->
    <div v-if="tbViewMode === 'summary'">
      <!-- 报表类型切换 -->
      <div style="display:flex;gap:0;margin-bottom:8px;border-bottom:2px solid #f0edf5">
        <span v-for="rt in tbSummaryTypes" :key="rt.key"
          class="gt-tb-view-tag" :class="{ 'gt-tb-view-tag--active': tbSummaryType === rt.key }"
          @click="tbSummaryType = rt.key; loadTbSummary()">{{ rt.label }}</span>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:8px;align-items:center">
        <el-button size="small" @click="loadTbSummary()" :loading="tbSummaryLoading">🔄 刷新</el-button>
        <el-button size="small" @click="exportTbSummary">📤 导出</el-button>
        <el-button size="small" @click="saveTbSummary">💾 保存</el-button>
        <span style="flex:1" />
        <span style="font-size:11px;color:#999">{{ tbSummaryRows.length }} 行 · 审定数=未审数+审计调整借-贷+重分类借-贷</span>
      </div>
      <div style="overflow-x:auto;max-height:calc(100vh - 300px)">
        <table class="gt-tb-summary-table" :style="{ fontSize: displayPrefs.fontConfig.tableFont }">
          <thead>
            <tr>
              <th rowspan="2" style="min-width:60px">行次</th>
              <th rowspan="2" style="min-width:200px">项目</th>
              <th rowspan="2" style="min-width:120px">未审数</th>
              <th colspan="2">审计调整</th>
              <th colspan="2">重分类调整</th>
              <th rowspan="2" class="gt-tb-sum-audited-th" style="min-width:120px">审定数</th>
            </tr>
            <tr>
              <th style="min-width:100px">借方</th><th style="min-width:100px">贷方</th>
              <th style="min-width:100px">借方</th><th style="min-width:100px">贷方</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in tbSummaryRows" :key="ri"
              :class="{ 'gt-tb-sum-total': row.is_total, 'gt-tb-sum-category': row.is_category }">
              <td style="text-align:center;color:#999;font-size:11px">{{ row.row_code }}</td>
              <td :style="{ paddingLeft: (row.indent || 0) * 14 + 'px' }">{{ row.row_name }}</td>
              <td class="gt-tb-sum-num gt-tb-sum-unadj">{{ fmt(row.unadjusted) }}</td>
              <td class="gt-tb-sum-num"><el-input-number v-if="tbSumLazyEdit.isEditing(ri, 0)" v-model="row.aje_dr" size="small" :controls="false" style="width:100%" @blur="tbSumLazyEdit.stopEdit()" autofocus /><span v-else class="gt-tb-editable" @click="tbSumLazyEdit.startEdit(ri, 0)">{{ fmt(row.aje_dr) }}</span></td>
              <td class="gt-tb-sum-num"><el-input-number v-if="tbSumLazyEdit.isEditing(ri, 1)" v-model="row.aje_cr" size="small" :controls="false" style="width:100%" @blur="tbSumLazyEdit.stopEdit()" autofocus /><span v-else class="gt-tb-editable" @click="tbSumLazyEdit.startEdit(ri, 1)">{{ fmt(row.aje_cr) }}</span></td>
              <td class="gt-tb-sum-num"><el-input-number v-if="tbSumLazyEdit.isEditing(ri, 2)" v-model="row.rcl_dr" size="small" :controls="false" style="width:100%" @blur="tbSumLazyEdit.stopEdit()" autofocus /><span v-else class="gt-tb-editable" @click="tbSumLazyEdit.startEdit(ri, 2)">{{ fmt(row.rcl_dr) }}</span></td>
              <td class="gt-tb-sum-num"><el-input-number v-if="tbSumLazyEdit.isEditing(ri, 3)" v-model="row.rcl_cr" size="small" :controls="false" style="width:100%" @blur="tbSumLazyEdit.stopEdit()" autofocus /><span v-else class="gt-tb-editable" @click="tbSumLazyEdit.startEdit(ri, 3)">{{ fmt(row.rcl_cr) }}</span></td>
              <td class="gt-tb-sum-num gt-tb-sum-audited">{{ fmt(row.audited) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <el-empty v-if="!tbSummaryRows.length && !tbSummaryLoading" description="点击刷新从科目明细汇总生成" />
    </div>

    <!-- 选中区域状态栏 -->
    <SelectionBar :stats="tbCtx.selectionStats()" />

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
          <template #default="{ row }">{{ fmt(row.total_debit) }}</template>
        </el-table-column>
        <el-table-column prop="total_credit" label="贷方" width="130" align="right">
          <template #default="{ row }">{{ fmt(row.total_credit) }}</template>
        </el-table-column>
        <el-table-column prop="review_status" label="状态" width="100">
          <template #default="{ row }">
            <GtStatusTag :status-map="ADJUSTMENT_STATUS" :value="row.review_status" />
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

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showTbImport"
      import-type="trial_balance"
      :project-id="projectId"
      :year="year"
      @imported="onTbImported"
    />
  </div>

  <!-- 右键菜单（统一组件） -->
  <CellContextMenu
    :visible="tbCtx.contextMenu.visible"
    :x="tbCtx.contextMenu.x"
    :y="tbCtx.contextMenu.y"
    :item-name="tbCtx.contextMenu.itemName"
    :value="tbCtx.selectedCells.value.length === 1 ? tbCtx.selectedCells.value[0]?.value : undefined"
    :multi-count="tbCtx.selectedCells.value.length"
    @copy="onTbCtxCopy"
    @formula="onTbCtxFormula"
    @sum="onTbCtxSum"
    @compare="onTbCtxCompare"
  >
    <div class="gt-ucell-ctx-item" @click="onTbCtxDrillDown"><span class="gt-ucell-ctx-icon">📊</span> 查看明细</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxOpenWp"><span class="gt-ucell-ctx-icon">📝</span> 打开底稿</div>
  </CellContextMenu>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Link } from '@element-plus/icons-vue'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import { useCellComments } from '@/composables/useCellComments'
import { useLazyEdit } from '@/composables/useLazyEdit'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableSearch } from '@/composables/useTableSearch'
import { fmtAmount } from '@/utils/formatters'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import {
  getTrialBalance, recalcTrialBalance, checkConsistency,
  getProjectAuditYear, listAdjustments,
  type TrialBalanceRow, type ConsistencyResult,
} from '@/services/auditPlatformApi'
import { getAllWpMappings, type WpAccountMapping } from '@/services/workpaperApi'
import { useProjectStore } from '@/stores/project'
import GtStatusTag from '@/components/common/GtStatusTag.vue'
import { ADJUSTMENT_STATUS } from '@/utils/statusMaps'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const projectId = computed(() => projectStore.projectId)
const selectedProjectId = ref(projectStore.projectId)
const projectOptions = computed(() => projectStore.projectOptions)
const selectedYear = ref(projectStore.year)
const yearOptions = computed(() => projectStore.yearOptions)

function onProjectChange(pid: string) {
  router.push({
    path: `/projects/${pid}/trial-balance`,
    query: { year: String(selectedYear.value) },
  })
}

function onYearChange(y: number) {
  selectedYear.value = y
  projectStore.changeYear(y)
  router.push({
    path: `/projects/${projectId.value}/trial-balance`,
    query: { year: String(y) },
  })
}

const displayPrefs = useDisplayPrefsStore()
/** 格式化金额（跟随全局单位设置） */
const fmt = (v: any) => displayPrefs.fmt(v)

const routeYear = computed(() => {
  const value = Number(route.query.year)
  return Number.isFinite(value) && value > 2000 ? value : null
})
const projectYear = ref<number | null>(null)
const year = computed(() => routeYear.value ?? projectYear.value ?? new Date().getFullYear())

const loading = ref(false)
const showTbImport = ref(false)
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

function rowClassName({ row }: { row: DisplayRow }) {
  if (row._isTotal) return 'total-row'
  if (row._isSubtotal) return 'subtotal-row'
  if (row._highlight) return 'highlight-row'
  return ''
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

function onTbImported() {
  showTbImport.value = false
  fetchData()
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
    selectedProjectId.value = projectId.value
    selectedYear.value = year.value
    await fetchData()
    if (!projectStore.projectOptions.length) projectStore.loadProjectOptions()
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

// ─── Ctrl+F 快捷键注册 + shortcut:save 监听 ─────────────────────────────────
onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  eventBus.on('shortcut:save', onShortcutSave)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  eventBus.off('shortcut:save', onShortcutSave)
})

/** 快捷键保存：根据当前视图保存试算平衡表 */
function onShortcutSave() {
  if (tbViewMode.value === 'summary') {
    saveTbSummary()
  } else {
    onRecalc()
  }
}

// ─── 试算平衡表（报表行次级别） ──────────────────────────────────────────────
const tbViewMode = ref<'detail' | 'summary'>('detail')
const tbSummaryType = ref('balance_sheet')
const tbSummaryLoading = ref(false)
const tbSummaryRows = ref<any[]>([])
const selectedTemplateType = ref('soe')

function recalcTbSummaryAudited() {
  for (const r of tbSummaryRows.value) {
    const u = Number(r.unadjusted) || 0
    const ad = Number(r.aje_dr) || 0
    const ac = Number(r.aje_cr) || 0
    const rd = Number(r.rcl_dr) || 0
    const rc = Number(r.rcl_cr) || 0
    const result = u + ad - ac + rd - rc
    r.audited = result !== 0 ? Math.round(result * 100) / 100 : null
  }
}

watch(tbSummaryRows, recalcTbSummaryAudited, { deep: true })
const { isFullscreen: tbFullscreen, toggleFullscreen: toggleTbFullscreen } = useFullscreen()

function copyTbTable() {
  const data = tbViewMode.value === 'summary' ? tbSummaryRows.value : groupedRows.value
  if (!data?.length) { ElMessage.warning('无数据可复制'); return }
  let headers: string[], dataRows: any[][]
  if (tbViewMode.value === 'summary') {
    headers = ['行次', '项目', '未审数', '审计调整-借', '审计调整-贷', '重分类-借', '重分类-贷', '审定数']
    dataRows = data.map((r: any) => [r.row_code, r.row_name, r.unadjusted, r.aje_dr, r.aje_cr, r.rcl_dr, r.rcl_cr, r.audited])
  } else {
    headers = ['科目编码', '科目名称', '未审数', 'RJE调整', 'AJE调整', '审定数']
    dataRows = data.map((r: any) => [r.standard_account_code, r.account_name, r.unadjusted_amount, r.rje_adjustment, r.aje_adjustment, r.audited_amount])
  }
  const text = [headers.join('\t'), ...dataRows.map(r => r.join('\t'))].join('\n')
  const html = `<table border="1"><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>${dataRows.map(r => `<tr>${r.map(c => `<td>${c ?? ''}</td>`).join('')}</tr>`).join('')}</table>`
  try {
    navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })])
    ElMessage.success(`已复制 ${dataRows.length} 行`)
  } catch { navigator.clipboard?.writeText(text); ElMessage.success('已复制') }
}

// ─── 单元格选中与右键菜单（统一 composable） ─────────────────────────────────
const tbCtx = useCellSelection()
const tbComments = useCellComments(() => projectId.value, () => year.value, 'trial_balance')
const tbSumLazyEdit = useLazyEdit()

// ─── 拖拽框选（鼠标左键按住拖动选中连续区域） ──────────────────────────────
const tbTableRef = ref<any>(null)

tbCtx.setupTableDrag(tbTableRef, (rowIdx: number, colIdx: number) => {
  const row = groupedRows.value[rowIdx]
  if (!row) return null
  if (colIdx === 0) return row.standard_account_code
  if (colIdx === 1) return row.account_name
  if (colIdx === 2) return row.unadjusted_amount
  if (colIdx === 3) return row.rje_adjustment
  if (colIdx === 4) return row.aje_adjustment
  if (colIdx === 5) return row.audited_amount
  return null
})

// ─── 表格内搜索（Ctrl+F） ──────────────────────────────────────────────────
const tbSearch = useTableSearch(
  computed(() => tbViewMode.value === 'detail' ? groupedRows.value : tbSummaryRows.value),
  ['standard_account_code', 'account_name'],
)

/** Ctrl+F 快捷键触发搜索栏（拦截浏览器默认搜索） */
function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    e.preventDefault()
    e.stopPropagation()
    tbSearch.toggle()
  }
}

function tbCellClassName({ rowIndex, columnIndex }: any) {
  const classes: string[] = []
  const selClass = tbCtx.cellClassName({ rowIndex, columnIndex })
  if (selClass) classes.push(selClass)
  const ccClass = tbComments.commentCellClass('tb_detail', rowIndex, columnIndex)
  if (ccClass) classes.push(ccClass)
  return classes.join(' ')
}

function onTbCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  tbCtx.closeContextMenu()
  const rowIdx = groupedRows.value.indexOf(row)
  const colLabels: Record<string, number> = { '科目编码': 0, '科目名称': 1, '未审数': 2, 'RJE调整': 3, 'AJE调整': 4, '审定数': 5 }
  const colIdx = colLabels[column.label] ?? -1
  if (rowIdx < 0 || colIdx < 0) return
  const value = colIdx === 2 ? row.unadjusted_amount : colIdx === 3 ? row.rje_adjustment : colIdx === 4 ? row.aje_adjustment : colIdx === 5 ? row.audited_amount : row.account_name
  tbCtx.selectCell(rowIdx, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
  tbCtx.contextMenu.rowData = row
  tbCtx.contextMenu.itemName = row.account_name || ''
}

function onTbCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  const rowIdx = groupedRows.value.indexOf(row)
  const colLabels: Record<string, number> = { '科目编码': 0, '科目名称': 1, '未审数': 2, 'RJE调整': 3, 'AJE调整': 4, '审定数': 5 }
  const colIdx = colLabels[column.label] ?? -1
  // 如果右键点击的单元格已在选区内，保持选区不变
  if (rowIdx >= 0 && colIdx >= 0 && !tbCtx.isCellSelected(rowIdx, colIdx)) {
    const value = colIdx === 2 ? row.unadjusted_amount : colIdx === 3 ? row.rje_adjustment : colIdx === 4 ? row.aje_adjustment : colIdx === 5 ? row.audited_amount : row.account_name
    tbCtx.selectCell(rowIdx, colIdx, value, false)
  }
  tbCtx.contextMenu.rowData = row
  tbCtx.contextMenu.itemName = row.account_name || ''
  tbCtx.openContextMenu(event, tbCtx.contextMenu.itemName, row)
}

function onTbCtxCopy() {
  tbCtx.closeContextMenu()
  tbCtx.copySelectedValues()
  ElMessage.success('已复制')
}

function onTbCtxDrillDown() {
  tbCtx.closeContextMenu()
  if (tbCtx.contextMenu.rowData) onUnadjustedClick(tbCtx.contextMenu.rowData)
}

function onTbCtxFormula() {
  tbCtx.closeContextMenu()
  showFormulaManager.value = true
}

function onTbCtxOpenWp() {
  tbCtx.closeContextMenu()
  if (tbCtx.contextMenu.rowData?.standard_account_code) onOpenWorkpaper(tbCtx.contextMenu.rowData.standard_account_code)
}

function onTbCtxSum() {
  tbCtx.closeContextMenu()
  const sum = tbCtx.sumSelectedValues()
  ElMessage.info(`选中 ${tbCtx.selectedCells.value.length} 格，合计：${fmtAmount(sum)}`)
}

function onTbCtxCompare() {
  tbCtx.closeContextMenu()
  if (tbCtx.selectedCells.value.length < 2) return
  const vals = tbCtx.selectedCells.value.map(c => Number(c.value) || 0)
  const diff = vals[0] - vals[1]
  ElMessage.info(`差异：${fmtAmount(diff)}`)
}

const tbSummaryTypes = [
  { key: 'balance_sheet', label: '资产负债表' },
  { key: 'income_statement', label: '利润表' },
  { key: 'cash_flow_statement', label: '现金流量表' },
]

async function loadTbSummary() {
  tbSummaryLoading.value = true
  try {
    // 1. 加载报表行结构
    const standard = `${selectedTemplateType.value}_standalone`
    const reportData = await api.get('/api/report-config', {
      params: { report_type: tbSummaryType.value, applicable_standard: standard, project_id: projectId.value },
      validateStatus: (s: number) => s < 600,
    })
    const reportRows = Array.isArray(reportData) ? reportData : []

    // 2. 从科目明细汇总未审数（按报表行次映射）
    // 用现有的 rows（科目明细）按 account_name 匹配报表行
    const unadjMap: Record<string, number> = {}
    for (const r of rows.value) {
      if (r.account_name && r.unadjusted_amount) {
        unadjMap[r.account_name.trim()] = (unadjMap[r.account_name.trim()] || 0) + Number(r.unadjusted_amount || 0)
      }
    }

    // 3. 从调整分录汇总 AJE/RCL
    const ajeMap: Record<string, { dr: number; cr: number }> = {}
    const rclMap: Record<string, { dr: number; cr: number }> = {}
    for (const r of rows.value) {
      const name = (r.account_name || '').trim()
      if (!name) continue
      const aje = Number(r.aje_adjustment || 0)
      const rje = Number(r.rje_adjustment || 0)
      if (aje > 0) { ajeMap[name] = ajeMap[name] || { dr: 0, cr: 0 }; ajeMap[name].dr += aje }
      else if (aje < 0) { ajeMap[name] = ajeMap[name] || { dr: 0, cr: 0 }; ajeMap[name].cr += Math.abs(aje) }
      if (rje > 0) { rclMap[name] = rclMap[name] || { dr: 0, cr: 0 }; rclMap[name].dr += rje }
      else if (rje < 0) { rclMap[name] = rclMap[name] || { dr: 0, cr: 0 }; rclMap[name].cr += Math.abs(rje) }
    }

    // 4. 构建试算平衡表行
    tbSummaryRows.value = reportRows.map((r: any) => {
      const name = (r.row_name || '').trim().replace(/^[△▲*#\s]+/, '')
      const unadj = unadjMap[name] || Number(r.current_period_amount || 0) || null
      const aje = ajeMap[name] || { dr: 0, cr: 0 }
      const rcl = rclMap[name] || { dr: 0, cr: 0 }
      return {
        row_code: r.row_code || '',
        row_name: r.row_name || '',
        indent: r.indent_level || 0,
        is_total: r.is_total_row || false,
        is_category: (r.indent_level === 0 && !r.is_total_row),
        unadjusted: unadj,
        aje_dr: aje.dr || null,
        aje_cr: aje.cr || null,
        rcl_dr: rcl.dr || null,
        rcl_cr: rcl.cr || null,
        audited: null as number | null,
      }
    })
    recalcTbSummaryAudited()

    // 5. 尝试加载已保存的数据覆盖
    try {
      const saved = await api.get(
        `/api/consol-worksheet-data/${projectId.value}/${selectedYear.value}/tb_summary_${tbSummaryType.value}`,
        { validateStatus: (s: number) => s < 600 }
      )
      const savedData = saved
      if (savedData?.content?.rows) {
        for (const sr of savedData.content.rows) {
          const target = tbSummaryRows.value.find((r: any) => r.row_code === sr.row_code)
          if (target) {
            if (sr.aje_dr != null) target.aje_dr = sr.aje_dr
            if (sr.aje_cr != null) target.aje_cr = sr.aje_cr
            if (sr.rcl_dr != null) target.rcl_dr = sr.rcl_dr
            if (sr.rcl_cr != null) target.rcl_cr = sr.rcl_cr
          }
        }
      }
    } catch { /* 首次无数据 */ }
  } catch { tbSummaryRows.value = [] }
  finally { tbSummaryLoading.value = false }
}

async function saveTbSummary() {
  try {
    const saveRows = tbSummaryRows.value.map((r: any) => ({
      row_code: r.row_code, row_name: r.row_name,
      unadjusted: r.unadjusted, aje_dr: r.aje_dr, aje_cr: r.aje_cr,
      rcl_dr: r.rcl_dr, rcl_cr: r.rcl_cr,
    }))
    await api.put(
      `/api/consol-worksheet-data/${projectId.value}/${selectedYear.value}/tb_summary_${tbSummaryType.value}`,
      { sheet_key: `tb_summary_${tbSummaryType.value}`, data: { rows: saveRows } },
      { validateStatus: (s: number) => s < 600 }
    )
    ElMessage.success('试算平衡表已保存')
  } catch { ElMessage.error('保存失败') }
}

async function exportTbSummary() {
  if (!tbSummaryRows.value.length) return
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const headers = ['行次', '项目', '未审数', '审计调整-借', '审计调整-贷', '重分类-借', '重分类-贷', '审定数']
  const dataRows = tbSummaryRows.value.map((r: any) => [
    r.row_code, r.row_name, r.unadjusted, r.aje_dr, r.aje_cr, r.rcl_dr, r.rcl_cr, r.audited,
  ])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = headers.map((_, i) => ({ wch: i < 2 ? 20 : 14 }))
  XLSX.utils.book_append_sheet(wb, ws, '试算平衡表')
  const label = tbSummaryTypes.find(t => t.key === tbSummaryType.value)?.label || ''
  XLSX.writeFile(wb, `试算平衡表_${label}.xlsx`)
  ElMessage.success('已导出')
}
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

/* 视图切换标签 */

.gt-tb-view-tag {
  padding: 6px 16px; font-size: 13px; cursor: pointer; color: #999;
  border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.15s; user-select: none;
}
.gt-tb-view-tag:hover { color: #4b2d77; }
.gt-tb-view-tag--active { color: #4b2d77; font-weight: 600; border-bottom-color: #4b2d77; }

/* 试算平衡表 */
.gt-tb-summary-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.gt-tb-summary-table th, .gt-tb-summary-table td { border: 1px solid #e8e4f0; padding: 4px 8px; }
.gt-tb-summary-table thead th { background: #f0edf5; font-weight: 600; text-align: center; position: sticky; top: 0; z-index: 2; }
.gt-tb-sum-num { text-align: right; }
.gt-tb-editable { cursor: text; border-bottom: 1px dashed #e5e5ea; padding: 2px 4px; border-radius: 2px; display: inline-block; min-width: 60px; text-align: right; }
.gt-tb-editable:hover { background: #f4f0fa; }
.gt-tb-sum-unadj { background: rgba(75,45,119,0.03); }
.gt-tb-sum-audited { font-weight: 700; color: #4b2d77; background: rgba(75,45,119,0.06); }
.gt-tb-sum-audited-th { background: #e8e0f0 !important; color: #4b2d77; }
.gt-tb-sum-total td { font-weight: 700; background: #f8f6fb !important; }
.gt-tb-sum-category td { font-weight: 600; color: #4b2d77; }
.gt-tb-summary-table :deep(.el-input-number) { width: 100%; }
.gt-tb-summary-table :deep(.el-input-number .el-input__inner) { text-align: right; font-size: 12px; height: 28px; }


</style>


