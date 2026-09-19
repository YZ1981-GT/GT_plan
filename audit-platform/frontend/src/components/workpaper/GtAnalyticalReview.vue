<script setup lang="ts">
/**
 * GtAnalyticalReview — 分析性复核底稿组件
 *
 * A1-13（母公司 6 sheet）/ A1-14（合并 8 sheet）完成阶段分析性复核。
 * Tab 切换：BS横向/BS纵向/IS横向/IS纵向/比率分析（+同行业/EPS 条件显示）
 *
 * 功能：
 *  - 横向分析表：项目 | 行次 | 上年审定 | 本年审定 | 变动额 | 变动% | 状况 | 原因
 *  - 纵向分析表：项目 | 行次 | 上年审定 | 比重% | 本年审定 | 比重% | 变动 | 状况 | 原因
 *  - 比率分析：按 6 大类分组，公式 + 分子分母 + 指标值 + 增减箭头
 *  - 颜色编码：significant=红底，attention=黄底
 *  - 变动原因列可编辑（debounce 2s 自动保存）
 *  - 科目行点击跳转对应循环底稿（emit navigate-row，由父级处理跳转）
 */
import { ref, computed, reactive, watch, onMounted, onBeforeUnmount } from 'vue'
import { api } from '@/services/apiProxy'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Types ───
interface SheetRow {
  row_code: string
  name: string
  row_number: number
  indent_level: number
  is_total_row: boolean
  prior: number
  current: number
  change: number
  change_pct: number | null
  status: 'significant' | 'attention' | 'normal'
  reason: string | null
  prior_weight_pct?: number | null
  current_weight_pct?: number | null
  weight_change_pct?: number | null
}

interface SheetData {
  title: string
  index: string
  columns: string[]
  rows: SheetRow[]
}

interface RatioItem {
  seq: number
  name: string
  formula: string
  prior_numerator: number | null
  prior_denominator: number | null
  prior_value: number | null
  current_numerator: number | null
  current_denominator: number | null
  current_value: number | null
  change: number | null
  direction: 'up' | 'down' | 'flat' | null
  normal_value: number | null
}

interface RatioCategory {
  name: string
  items: RatioItem[]
}

interface RatioAnalysisData {
  title: string
  index: string
  categories: RatioCategory[]
  notes: string[]
}

interface AnalyticalReviewData {
  wp_code: string
  scope: 'standalone' | 'consolidated'
  year: number
  materiality: number
  is_listed?: boolean
  sheets: {
    bs_horizontal: SheetData
    bs_vertical: SheetData
    is_horizontal: SheetData
    is_vertical: SheetData
    ratio_analysis: RatioAnalysisData | null
    industry_comparison: IndustryComparisonData | null
    eps_roe: EpsRoeData | null
  }
}

interface IndustryComparisonData {
  title: string
  index: string
  years: number[]
  companies: Array<{ key: string; name: string; stock_code: string }>
  financial_data: Record<string, Record<string, Record<string, number | null>>>
  comparison_table: Record<string, Record<string, Record<string, number | null>>>
  financial_metric_labels: Record<string, string>
  comparison_metric_labels: Record<string, string>
  data_source_note: string
}

interface EpsRoeData {
  title: string
  index: string
  year: number
  inputs: Record<string, number | null>
  share_changes: Array<{ id: string; label: string; shares: number | null; months: number; weight: number }>
  computed: {
    roe_diluted: number | null
    roe_weighted: number | null
    basic_eps: number | null
    diluted_eps: number | null
  }
  notes: string[]
}

// ─── Props / Emits ───
const props = withDefaults(defineProps<{
  wpId: string
  sheetName?: string
  schema?: Record<string, unknown>
  htmlData?: { analytical_review: AnalyticalReviewData } | null
  projectId?: string
  readonly?: boolean
}>(), {
  sheetName: '',
  schema: () => ({}),
  htmlData: null,
  projectId: '',
  readonly: false,
})

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'navigate-row', payload: { rowCode: string; name: string }): void
}>()

// ─── State ───
const activeTab = ref('bs_horizontal')
const reasonEdits = ref<Record<string, string>>({})
const saveTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const selfLoadedData = ref<AnalyticalReviewData | null>(null)
const loading = ref(false)
const isFullscreen = ref(false)

// ─── Computed: Data ───
const data = computed(() => props.htmlData?.analytical_review ?? selfLoadedData.value)
const scopeLabel = computed(() => data.value?.scope === 'consolidated' ? '合并' : '母公司')

// ─── Self-Loading: 当 htmlData 未提供时自行获取 render-config ───

async function loadRenderConfig() {
  if (props.htmlData?.analytical_review || !props.wpId) return
  loading.value = true
  try {
    const res = await api.get<any>(`/api/workpapers/${props.wpId}/render-config?force_component_type=analytical-review`)
    const htmlData = res?.sheets?.[0]?.html_data ?? res?.htmlData ?? res
    if (htmlData?.analytical_review) {
      selfLoadedData.value = htmlData.analytical_review
    }
  } catch (e: any) {
    console.warn('[GtAnalyticalReview] render-config 加载失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (!props.htmlData) {
    loadRenderConfig()
  }
})

// ─── Computed: Available tabs ───
interface TabDef {
  key: string
  label: string
  sheetKey: keyof AnalyticalReviewData['sheets']
}

const availableTabs = computed<TabDef[]>(() => {
  const tabs: TabDef[] = [
    { key: 'bs_horizontal', label: 'BS横向', sheetKey: 'bs_horizontal' },
    { key: 'bs_vertical', label: 'BS纵向', sheetKey: 'bs_vertical' },
    { key: 'is_horizontal', label: 'IS横向', sheetKey: 'is_horizontal' },
    { key: 'is_vertical', label: 'IS纵向', sheetKey: 'is_vertical' },
  ]
  if (data.value?.sheets?.ratio_analysis) {
    tabs.push({ key: 'ratio_analysis', label: '比率分析', sheetKey: 'ratio_analysis' })
  }
  // 上市公司专用 tab：按 is_listed 判断显示
  if (data.value?.is_listed && data.value?.sheets?.industry_comparison) {
    tabs.push({ key: 'industry_comparison', label: '同行业对比', sheetKey: 'industry_comparison' })
  }
  if (data.value?.is_listed && data.value?.sheets?.eps_roe) {
    tabs.push({ key: 'eps_roe', label: 'EPS/ROE', sheetKey: 'eps_roe' })
  }
  return tabs
})

// ─── Computed: Current sheet data ───
const currentSheet = computed<SheetData | null>(() => {
  if (!data.value?.sheets) return null
  const key = activeTab.value as keyof AnalyticalReviewData['sheets']
  if (key === 'ratio_analysis' || key === 'industry_comparison' || key === 'eps_roe') return null
  return (data.value.sheets[key] as SheetData) ?? null
})

const currentRatio = computed<RatioAnalysisData | null>(() => {
  if (activeTab.value !== 'ratio_analysis') return null
  return data.value?.sheets?.ratio_analysis ?? null
})

const currentIndustry = computed<IndustryComparisonData | null>(() => {
  if (activeTab.value !== 'industry_comparison') return null
  return data.value?.sheets?.industry_comparison ?? null
})

const currentEpsRoe = computed<EpsRoeData | null>(() => {
  if (activeTab.value !== 'eps_roe') return null
  return data.value?.sheets?.eps_roe ?? null
})

const isHorizontal = computed(() =>
  activeTab.value === 'bs_horizontal' || activeTab.value === 'is_horizontal'
)

const isVertical = computed(() =>
  activeTab.value === 'bs_vertical' || activeTab.value === 'is_vertical'
)

// ─── Methods: Formatting ───
const prefs = useDisplayPrefsStore()


function formatPct(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toFixed(2) + '%'
}

function formatRatioValue(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toFixed(4)
}

// ─── Methods: Row styling ───
function getRowClass(row: SheetRow): string {
  const classes: string[] = []
  if (row.status === 'significant') classes.push('row-significant')
  if (row.status === 'attention') classes.push('row-attention')
  if (row.is_total_row) classes.push('row-total')
  return classes.join(' ')
}

function getIndentStyle(row: SheetRow): Record<string, string> {
  return { paddingLeft: `${(row.indent_level || 0) * 16}px` }
}

// ─── Methods: Row click（向父组件冒泡，由父级决定跳转目标循环底稿）───
function handleRowClick(row: SheetRow) {
  emit('navigate-row', { rowCode: row.row_code, name: row.name })
}

// ─── Methods: Reason editing (debounce 2s) ───
function getReasonValue(rowCode: string, originalReason: string | null): string {
  if (rowCode in reasonEdits.value) {
    return reasonEdits.value[rowCode]
  }
  return originalReason ?? ''
}

function handleReasonInput(rowCode: string, value: string) {
  reasonEdits.value[rowCode] = value
  scheduleSave()
}

function scheduleSave() {
  if (saveTimer.value) {
    clearTimeout(saveTimer.value)
  }
  saveTimer.value = setTimeout(() => {
    doSave()
  }, 2000)
}

function doSave() {
  // TODO: 当前无专用保存端点，emit('save') 通知父组件
  // 后续实现：PUT /api/workpapers/{wpId}/analytical-review/reasons
  emit('save')
}

// ─── Industry Comparison Editing ───
const industryCompanies = ref<Array<{ key: string; name: string; stock_code: string }>>([])
const industryFinancialData = reactive<Record<string, Record<string, Record<string, string | null>>>>({})
const industryComparisonData = reactive<Record<string, Record<string, Record<string, string | null>>>>({})
const industryDataSourceNote = ref('')
const industrySaveTimer = ref<ReturnType<typeof setTimeout> | null>(null)

function initIndustryData() {
  const ind = data.value?.sheets?.industry_comparison
  if (!ind) return
  industryCompanies.value = (ind.companies || []).map(c => ({ ...c }))
  industryDataSourceNote.value = ind.data_source_note || ''
  // Copy financial_data
  for (const [metric, yearData] of Object.entries(ind.financial_data || {})) {
    if (!industryFinancialData[metric]) industryFinancialData[metric] = {}
    for (const [yr, coData] of Object.entries(yearData as Record<string, any>)) {
      if (!industryFinancialData[metric][yr]) industryFinancialData[metric][yr] = {}
      for (const [co, val] of Object.entries(coData as Record<string, any>)) {
        industryFinancialData[metric][yr][co] = val != null ? String(val) : null
      }
    }
  }
  // Copy comparison_table
  for (const [metric, yearData] of Object.entries(ind.comparison_table || {})) {
    if (!industryComparisonData[metric]) industryComparisonData[metric] = {}
    for (const [yr, coData] of Object.entries(yearData as Record<string, any>)) {
      if (!industryComparisonData[metric][yr]) industryComparisonData[metric][yr] = {}
      for (const [co, val] of Object.entries(coData as Record<string, any>)) {
        industryComparisonData[metric][yr][co] = val != null ? String(val) : null
      }
    }
  }
}

function getIndustryValue(table: 'financial' | 'comparison', metric: string, year: number, co: string): string {
  const store = table === 'financial' ? industryFinancialData : industryComparisonData
  return store[metric]?.[String(year)]?.[co] ?? ''
}

function setIndustryValue(table: 'financial' | 'comparison', metric: string, year: number, co: string, val: string) {
  const store = table === 'financial' ? industryFinancialData : industryComparisonData
  if (!store[metric]) store[metric] = {}
  if (!store[metric][String(year)]) store[metric][String(year)] = {}
  store[metric][String(year)][co] = val || null
  scheduleIndustrySave()
}

function scheduleIndustrySave() {
  if (industrySaveTimer.value) clearTimeout(industrySaveTimer.value)
  industrySaveTimer.value = setTimeout(() => doIndustrySave(), 2000)
}

async function doIndustrySave() {
  if (!data.value) return
  const projectId = extractProjectId()
  if (!projectId) return
  const yr = data.value.year
  // Build payload with numeric conversion
  const financialPayload: Record<string, Record<string, Record<string, number | null>>> = {}
  for (const [metric, yearData] of Object.entries(industryFinancialData)) {
    financialPayload[metric] = {}
    for (const [y, coData] of Object.entries(yearData)) {
      financialPayload[metric][y] = {}
      for (const [co, val] of Object.entries(coData)) {
        financialPayload[metric][y][co] = val ? parseFloat(val) || null : null
      }
    }
  }
  const comparisonPayload: Record<string, Record<string, Record<string, number | null>>> = {}
  for (const [metric, yearData] of Object.entries(industryComparisonData)) {
    comparisonPayload[metric] = {}
    for (const [y, coData] of Object.entries(yearData)) {
      comparisonPayload[metric][y] = {}
      for (const [co, val] of Object.entries(coData)) {
        comparisonPayload[metric][y][co] = val ? parseFloat(val) || null : null
      }
    }
  }
  try {
    await api.post(
      `/api/projects/${projectId}/analytical-review/industry-comparison?year=${yr}`,
      {
        companies: industryCompanies.value,
        financial_data: financialPayload,
        comparison_table: comparisonPayload,
        data_source_note: industryDataSourceNote.value,
      }
    )
  } catch (e) {
    console.warn('[GtAnalyticalReview] 同行业对比保存失败:', e)
  }
}

// ─── EPS-ROE Editing ───
const epsParams = reactive<Record<string, any>>({
  net_profit: null,
  equity_end: null,
  equity_begin: null,
  preferred_dividend: 0,
})
const epsShareChanges = ref<Array<Record<string, any>>>([])
const epsDilution = reactive<Record<string, any>>({
  convertible_bond_face_value: 0,
  convertible_bond_rate: 0,
  convertible_bond_shares: 0,
  option_exercise_price: 0,
  option_shares: 0,
})
const epsComputed = reactive<Record<string, number | null>>({
  roe_diluted: null,
  roe_weighted: null,
  basic_eps: null,
  diluted_eps: null,
})
const epsRoeSaveTimer = ref<ReturnType<typeof setTimeout> | null>(null)

function initEpsRoeData() {
  const eps = data.value?.sheets?.eps_roe
  if (!eps) return
  epsParams.net_profit = eps.inputs?.net_profit
  epsParams.equity_end = eps.inputs?.equity_end
  epsParams.equity_begin = eps.inputs?.equity_begin
  epsParams.preferred_dividend = eps.inputs?.preferred_dividend || 0
  epsShareChanges.value = (eps.share_changes || []).map((item: any) => ({ ...item }))
  if (eps.dilution_factors) {
    Object.assign(epsDilution, eps.dilution_factors)
  }
  if (eps.computed) {
    Object.assign(epsComputed, eps.computed)
  }
}

function addShareChange() {
  const id = `s${Date.now()}`
  epsShareChanges.value.push({
    id,
    date: '',
    event_type: '',
    shares_changed: 0,
    cum_shares: 0,
    time_weight_months: 0,
  })
}

function removeShareChange(idx: number) {
  epsShareChanges.value.splice(idx, 1)
  scheduleEpsRoeSave()
}

function scheduleEpsRoeSave() {
  if (epsRoeSaveTimer.value) clearTimeout(epsRoeSaveTimer.value)
  epsRoeSaveTimer.value = setTimeout(() => doEpsRoeSave(), 2000)
}

async function doEpsRoeSave() {
  if (!data.value) return
  const projectId = extractProjectId()
  if (!projectId) return
  const yr = data.value.year
  try {
    const resp = await api.post(
      `/api/projects/${projectId}/analytical-review/eps-roe?year=${yr}`,
      {
        params: {
          net_profit: parseFloat(epsParams.net_profit) || null,
          equity_end: parseFloat(epsParams.equity_end) || null,
          equity_begin: parseFloat(epsParams.equity_begin) || null,
          preferred_dividend: parseFloat(epsParams.preferred_dividend) || 0,
        },
        share_changes: epsShareChanges.value.map(item => ({
          ...item,
          shares_changed: parseFloat(item.shares_changed) || 0,
          cum_shares: parseFloat(item.cum_shares) || 0,
          time_weight_months: parseFloat(item.time_weight_months) || 0,
        })),
        dilution_factors: {
          convertible_bond_face_value: parseFloat(epsDilution.convertible_bond_face_value) || 0,
          convertible_bond_rate: parseFloat(epsDilution.convertible_bond_rate) || 0,
          convertible_bond_shares: parseFloat(epsDilution.convertible_bond_shares) || 0,
          option_exercise_price: parseFloat(epsDilution.option_exercise_price) || 0,
          option_shares: parseFloat(epsDilution.option_shares) || 0,
        },
      }
    )
    // Update computed results from server response
    if (resp?.computed) {
      Object.assign(epsComputed, resp.computed)
    }
  } catch (e) {
    console.warn('[GtAnalyticalReview] EPS-ROE 保存失败:', e)
  }
}

// ─── Utility: Extract project ID from wpId ───
function extractProjectId(): string | null {
  // wpId is passed from parent; the API route uses project_id
  // We need to find the project_id — it's available in the data response or the URL
  // The render-config response includes project_id context
  // For now, extract from current window location
  const match = window.location.pathname.match(/\/projects\/([^/]+)/)
  return match ? match[1] : null
}

// ─── Methods: Direction arrow ───
function getDirectionArrow(direction: 'up' | 'down' | 'flat' | null): string {
  switch (direction) {
    case 'up': return '▲'
    case 'down': return '▼'
    case 'flat': return '—'
    default: return '—'
  }
}

function getDirectionClass(direction: 'up' | 'down' | 'flat' | null): string {
  switch (direction) {
    case 'up': return 'direction-up'
    case 'down': return 'direction-down'
    default: return 'direction-flat'
  }
}

// ─── Lifecycle ───
watch(() => props.htmlData, () => {
  // Reset edits on data change
  reasonEdits.value = {}
  initIndustryData()
  initEpsRoeData()
}, { immediate: true })

onBeforeUnmount(() => {
  if (saveTimer.value) {
    clearTimeout(saveTimer.value)
    saveTimer.value = null
    if (Object.keys(reasonEdits.value).length > 0) {
      doSave()
    }
  }
  if (industrySaveTimer.value) {
    clearTimeout(industrySaveTimer.value)
    industrySaveTimer.value = null
  }
  if (epsRoeSaveTimer.value) {
    clearTimeout(epsRoeSaveTimer.value)
    epsRoeSaveTimer.value = null
  }
})
</script>

<template>
  <div :class="['gt-analytical-review', { 'gt-analytical-review--fullscreen': isFullscreen }]" v-loading="loading">
    <!-- ─── Tab 导航 + 元信息（合并一行） ─── -->
    <div class="gt-analytical-review__tab-bar">
      <el-tabs v-model="activeTab" class="gt-analytical-review__tabs">
        <el-tab-pane
          v-for="tab in availableTabs"
          :key="tab.key"
          :label="tab.label"
          :name="tab.key"
        />
      </el-tabs>
      <div v-if="data" class="gt-analytical-review__meta">
        <span>{{ data.wp_code }} · {{ data.year }}年度</span>
        <span class="gt-analytical-review__materiality">
          重要性水平: {{ prefs.fmt(data.materiality) }}
        </span>
        <el-button size="small" @click="isFullscreen = !isFullscreen">
          {{ isFullscreen ? '退出全屏' : '全屏' }}
        </el-button>
      </div>
    </div>

    <!-- ─── 表格区域 ─── -->
    <div class="gt-analytical-review__content">
      <!-- 横向分析表 -->
      <template v-if="isHorizontal && currentSheet">
        <div class="gt-analytical-review__sheet-title">
          {{ currentSheet.title }}
          <span class="sheet-index">{{ currentSheet.index }}</span>
        </div>
        <div class="gt-analytical-review__table-wrap">
          <table class="gt-ar-table gt-compact-table">
            <thead>
              <tr>
                <th class="col-name">项目</th>
                <th class="col-row-num">行次</th>
                <th class="col-amount">上年审定数</th>
                <th class="col-amount">本年审定数</th>
                <th class="col-amount">变动额</th>
                <th class="col-pct">变动%</th>
                <th class="col-status">状况</th>
                <th class="col-reason">显著变动原因分析</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in currentSheet.rows"
                :key="row.row_code"
                :class="getRowClass(row)"
                @click="handleRowClick(row)"
              >
                <td class="col-name" :style="getIndentStyle(row)">
                  <span :class="{ 'is-total': row.is_total_row }">{{ row.name }}</span>
                </td>
                <td class="col-row-num">{{ row.row_number }}</td>
                <td class="col-amount">{{ prefs.fmt(row.prior) }}</td>
                <td class="col-amount">{{ prefs.fmt(row.current) }}</td>
                <td class="col-amount">{{ prefs.fmt(row.change) }}</td>
                <td class="col-pct">{{ formatPct(row.change_pct) }}</td>
                <td class="col-status">
                  <span v-if="row.status === 'significant'" class="status-tag status-significant">显著</span>
                  <span v-else-if="row.status === 'attention'" class="status-tag status-attention">关注</span>
                  <span v-else class="status-tag status-normal">正常</span>
                </td>
                <td class="col-reason" @click.stop>
                  <el-input
                    v-if="row.status !== 'normal' || getReasonValue(row.row_code, row.reason)"
                    :model-value="getReasonValue(row.row_code, row.reason)"
                    size="small"
                    placeholder="填写变动原因"
                    :disabled="readonly"
                    @input="(val: string) => handleReasonInput(row.row_code, val)"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- 纵向分析表 -->
      <template v-if="isVertical && currentSheet">
        <div class="gt-analytical-review__sheet-title">
          {{ currentSheet.title }}
          <span class="sheet-index">{{ currentSheet.index }}</span>
        </div>
        <div class="gt-analytical-review__table-wrap">
          <table class="gt-ar-table gt-compact-table">
            <thead>
              <tr>
                <th class="col-name">项目</th>
                <th class="col-row-num">行次</th>
                <th class="col-amount">上年审定数</th>
                <th class="col-pct">比重%</th>
                <th class="col-amount">本年审定数</th>
                <th class="col-pct">比重%</th>
                <th class="col-pct">变动</th>
                <th class="col-status">状况</th>
                <th class="col-reason">显著变动原因分析</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in currentSheet.rows"
                :key="row.row_code"
                :class="getRowClass(row)"
                @click="handleRowClick(row)"
              >
                <td class="col-name" :style="getIndentStyle(row)">
                  <span :class="{ 'is-total': row.is_total_row }">{{ row.name }}</span>
                </td>
                <td class="col-row-num">{{ row.row_number }}</td>
                <td class="col-amount">{{ prefs.fmt(row.prior) }}</td>
                <td class="col-pct">{{ formatPct(row.prior_weight_pct) }}</td>
                <td class="col-amount">{{ prefs.fmt(row.current) }}</td>
                <td class="col-pct">{{ formatPct(row.current_weight_pct) }}</td>
                <td class="col-pct">{{ formatPct(row.weight_change_pct) }}</td>
                <td class="col-status">
                  <span v-if="row.status === 'significant'" class="status-tag status-significant">显著</span>
                  <span v-else-if="row.status === 'attention'" class="status-tag status-attention">关注</span>
                  <span v-else class="status-tag status-normal">正常</span>
                </td>
                <td class="col-reason" @click.stop>
                  <el-input
                    v-if="row.status !== 'normal' || getReasonValue(row.row_code, row.reason)"
                    :model-value="getReasonValue(row.row_code, row.reason)"
                    size="small"
                    placeholder="填写变动原因"
                    :disabled="readonly"
                    @input="(val: string) => handleReasonInput(row.row_code, val)"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- 比率分析表 -->
      <template v-if="activeTab === 'ratio_analysis' && currentRatio">
        <div class="gt-analytical-review__sheet-title">
          {{ currentRatio.title }}
          <span class="sheet-index">{{ currentRatio.index }}</span>
        </div>
        <div class="gt-analytical-review__table-wrap">
          <template v-for="category in currentRatio.categories" :key="category.name">
            <div class="gt-ar-ratio-category">{{ category.name }}</div>
            <table class="gt-ar-table gt-ar-ratio-table gt-compact-table">
              <thead>
                <tr>
                  <th class="col-seq">序号</th>
                  <th class="col-ratio-name">指标名称</th>
                  <th class="col-formula">公式</th>
                  <th class="col-ratio-val">上年值</th>
                  <th class="col-ratio-val">本年值</th>
                  <th class="col-ratio-val">增减</th>
                  <th class="col-direction">方向</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in category.items" :key="item.seq">
                  <td class="col-seq">{{ item.seq }}</td>
                  <td class="col-ratio-name">{{ item.name }}</td>
                  <td class="col-formula">{{ item.formula }}</td>
                  <td class="col-ratio-val">{{ formatRatioValue(item.prior_value) }}</td>
                  <td class="col-ratio-val">{{ formatRatioValue(item.current_value) }}</td>
                  <td class="col-ratio-val">{{ formatRatioValue(item.change) }}</td>
                  <td class="col-direction">
                    <span :class="getDirectionClass(item.direction)">
                      {{ getDirectionArrow(item.direction) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </template>

          <!-- 比率注释 -->
          <div v-if="currentRatio.notes?.length" class="gt-ar-ratio-notes">
            <div class="gt-ar-ratio-notes__title">注：</div>
            <div v-for="(note, idx) in currentRatio.notes" :key="idx" class="gt-ar-ratio-notes__item">
              {{ idx + 1 }}. {{ note }}
            </div>
          </div>
        </div>
      </template>

      <!-- 同行业对比（A1-14 上市公司专用 — 可编辑） -->
      <template v-if="activeTab === 'industry_comparison' && currentIndustry">
        <div class="gt-analytical-review__sheet-title">
          {{ currentIndustry.title }}
          <span class="sheet-index">{{ currentIndustry.index }}</span>
        </div>
        <div class="gt-analytical-review__table-wrap">
          <div class="gt-ar-subsection-title">可比公司</div>
          <table class="gt-ar-table gt-compact-table">
            <thead>
              <tr>
                <th>代号</th>
                <th>证券简称</th>
                <th>证券代码</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>本公司</td>
                <td colspan="2">—</td>
              </tr>
              <tr v-for="co in industryCompanies" :key="co.key">
                <td>{{ co.key }}</td>
                <td>
                  <el-input
                    v-model="co.name"
                    size="small"
                    placeholder="证券简称"
                    :disabled="readonly"
                    @input="scheduleIndustrySave"
                  />
                </td>
                <td>
                  <el-input
                    v-model="co.stock_code"
                    size="small"
                    placeholder="证券代码"
                    :disabled="readonly"
                    @input="scheduleIndustrySave"
                  />
                </td>
              </tr>
            </tbody>
          </table>

          <div class="gt-ar-subsection-title">主要财务数据</div>
          <table class="gt-ar-table gt-compact-table">
            <thead>
              <tr>
                <th rowspan="2">指标</th>
                <th v-for="y in currentIndustry.years" :key="y" :colspan="industryCompanies.length + 1">{{ y }}年</th>
              </tr>
              <tr>
                <template v-for="y in currentIndustry.years" :key="`hdr-${y}`">
                  <th>本公司</th>
                  <th v-for="co in industryCompanies" :key="`${y}-${co.key}`">{{ co.key }}</th>
                </template>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(label, key) in currentIndustry.financial_metric_labels" :key="key">
                <td>{{ label }}</td>
                <template v-for="y in currentIndustry.years" :key="`${key}-${y}`">
                  <td>
                    <el-input
                      :model-value="getIndustryValue('financial', key, y, 'self')"
                      size="small"
                      :disabled="readonly"
                      @input="(val: string) => setIndustryValue('financial', key, y, 'self', val)"
                    />
                  </td>
                  <td v-for="co in industryCompanies" :key="`${key}-${y}-${co.key}`">
                    <el-input
                      :model-value="getIndustryValue('financial', key, y, co.key)"
                      size="small"
                      :disabled="readonly"
                      @input="(val: string) => setIndustryValue('financial', key, y, co.key, val)"
                    />
                  </td>
                </template>
              </tr>
            </tbody>
          </table>

          <div class="gt-ar-subsection-title">对比分析表</div>
          <table class="gt-ar-table gt-compact-table">
            <thead>
              <tr>
                <th rowspan="2">指标</th>
                <th v-for="y in currentIndustry.years" :key="`cmp-${y}`" :colspan="industryCompanies.length + 1">{{ y }}年</th>
              </tr>
              <tr>
                <template v-for="y in currentIndustry.years" :key="`cmp-hdr-${y}`">
                  <th>本公司</th>
                  <th v-for="co in industryCompanies" :key="`cmp-${y}-${co.key}`">{{ co.key }}</th>
                </template>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(label, key) in currentIndustry.comparison_metric_labels" :key="`cmp-${key}`">
                <td>{{ label }}</td>
                <template v-for="y in currentIndustry.years" :key="`cmp-${key}-${y}`">
                  <td>
                    <el-input
                      :model-value="getIndustryValue('comparison', key, y, 'self')"
                      size="small"
                      :disabled="readonly"
                      @input="(val: string) => setIndustryValue('comparison', key, y, 'self', val)"
                    />
                  </td>
                  <td v-for="co in industryCompanies" :key="`cmp-${key}-${y}-${co.key}`">
                    <el-input
                      :model-value="getIndustryValue('comparison', key, y, co.key)"
                      size="small"
                      :disabled="readonly"
                      @input="(val: string) => setIndustryValue('comparison', key, y, co.key, val)"
                    />
                  </td>
                </template>
              </tr>
            </tbody>
          </table>

          <div class="gt-ar-subsection-title">数据来源标注</div>
          <el-input
            v-model="industryDataSourceNote"
            placeholder="请填写数据来源（如：Wind资讯、巨潮资讯网等）"
            :disabled="readonly"
            @input="scheduleIndustrySave"
          />
        </div>
      </template>

      <!-- EPS-ROE 计算表（A1-14 上市公司专用 — 可编辑） -->
      <template v-if="activeTab === 'eps_roe' && currentEpsRoe">
        <div class="gt-analytical-review__sheet-title">
          {{ currentEpsRoe.title }}
          <span class="sheet-index">{{ currentEpsRoe.index }}</span>
        </div>
        <div class="gt-analytical-review__table-wrap">
          <!-- 参数区 -->
          <div class="gt-ar-subsection-title">基本参数</div>
          <table class="gt-ar-table gt-compact-table">
            <thead>
              <tr>
                <th>参数</th>
                <th>数值</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>归属于普通股股东的净利润</td>
                <td>
                  <el-input
                    v-model="epsParams.net_profit"
                    size="small"
                    :disabled="readonly"
                    @input="scheduleEpsRoeSave"
                  />
                </td>
                <td class="gt-ar-hint">自动从利润表取数，可手动覆盖</td>
              </tr>
              <tr>
                <td>期末净资产</td>
                <td>
                  <el-input
                    v-model="epsParams.equity_end"
                    size="small"
                    :disabled="readonly"
                    @input="scheduleEpsRoeSave"
                  />
                </td>
                <td class="gt-ar-hint">自动从资产负债表取数</td>
              </tr>
              <tr>
                <td>期初净资产</td>
                <td>
                  <el-input
                    v-model="epsParams.equity_begin"
                    size="small"
                    :disabled="readonly"
                    @input="scheduleEpsRoeSave"
                  />
                </td>
                <td class="gt-ar-hint">自动从上年资产负债表取数</td>
              </tr>
              <tr>
                <td>优先股股利</td>
                <td>
                  <el-input
                    v-model="epsParams.preferred_dividend"
                    size="small"
                    placeholder="0"
                    :disabled="readonly"
                    @input="scheduleEpsRoeSave"
                  />
                </td>
                <td class="gt-ar-hint">无优先股填 0</td>
              </tr>
            </tbody>
          </table>

          <!-- 股本变动明细 -->
          <div class="gt-ar-subsection-title">
            股本变动明细
            <el-button v-if="!readonly" size="small" type="primary" link @click="addShareChange">
              + 新增行
            </el-button>
          </div>
          <table class="gt-ar-table gt-compact-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>事件类型</th>
                <th>股份变动数</th>
                <th>累计股份数</th>
                <th>时间权重(月)</th>
                <th v-if="!readonly">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, idx) in epsShareChanges" :key="item.id">
                <td>
                  <el-input
                    v-model="item.date"
                    size="small"
                    placeholder="YYYY-MM-DD"
                    :disabled="readonly"
                    @input="scheduleEpsRoeSave"
                  />
                </td>
                <td>
                  <el-input
                    v-model="item.event_type"
                    size="small"
                    placeholder="如：期初/增发/回购"
                    :disabled="readonly"
                    @input="scheduleEpsRoeSave"
                  />
                </td>
                <td>
                  <el-input
                    v-model="item.shares_changed"
                    size="small"
                    placeholder="0"
                    :disabled="readonly"
                    @input="scheduleEpsRoeSave"
                  />
                </td>
                <td>
                  <el-input
                    v-model="item.cum_shares"
                    size="small"
                    :disabled="readonly"
                    @input="scheduleEpsRoeSave"
                  />
                </td>
                <td>
                  <el-input
                    v-model="item.time_weight_months"
                    size="small"
                    placeholder="12"
                    :disabled="readonly"
                    @input="scheduleEpsRoeSave"
                  />
                </td>
                <td v-if="!readonly">
                  <el-button size="small" type="danger" link @click="removeShareChange(idx)">删除</el-button>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 稀释因素 -->
          <div class="gt-ar-subsection-title">稀释因素</div>
          <table class="gt-ar-table gt-compact-table">
            <thead>
              <tr>
                <th>项目</th>
                <th>数值</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>可转债面值</td>
                <td>
                  <el-input v-model="epsDilution.convertible_bond_face_value" size="small" placeholder="0" :disabled="readonly" @input="scheduleEpsRoeSave" />
                </td>
              </tr>
              <tr>
                <td>可转债票面利率(%)</td>
                <td>
                  <el-input v-model="epsDilution.convertible_bond_rate" size="small" placeholder="0" :disabled="readonly" @input="scheduleEpsRoeSave" />
                </td>
              </tr>
              <tr>
                <td>可转债假定转股数</td>
                <td>
                  <el-input v-model="epsDilution.convertible_bond_shares" size="small" placeholder="0" :disabled="readonly" @input="scheduleEpsRoeSave" />
                </td>
              </tr>
              <tr>
                <td>期权行权价</td>
                <td>
                  <el-input v-model="epsDilution.option_exercise_price" size="small" placeholder="0" :disabled="readonly" @input="scheduleEpsRoeSave" />
                </td>
              </tr>
              <tr>
                <td>期权假定行权增加股数</td>
                <td>
                  <el-input v-model="epsDilution.option_shares" size="small" placeholder="0" :disabled="readonly" @input="scheduleEpsRoeSave" />
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 计算结果 -->
          <div class="gt-ar-subsection-title">计算结果</div>
          <table class="gt-ar-table gt-compact-table">
            <tbody>
              <tr>
                <td>净资产收益率（全面摊薄）</td>
                <td class="col-amount">{{ formatRatioValue(epsComputed.roe_diluted) }}%</td>
              </tr>
              <tr>
                <td>净资产收益率（加权平均）</td>
                <td class="col-amount">{{ formatRatioValue(epsComputed.roe_weighted) }}%</td>
              </tr>
              <tr>
                <td>基本每股收益</td>
                <td class="col-amount">{{ formatRatioValue(epsComputed.basic_eps) }}</td>
              </tr>
              <tr>
                <td>稀释每股收益</td>
                <td class="col-amount">{{ formatRatioValue(epsComputed.diluted_eps) }}</td>
              </tr>
            </tbody>
          </table>

          <div v-if="currentEpsRoe.notes?.length" class="gt-ar-ratio-notes">
            <div class="gt-ar-ratio-notes__title">注：</div>
            <div v-for="(note, idx) in currentEpsRoe.notes" :key="idx" class="gt-ar-ratio-notes__item">
              {{ idx + 1 }}. {{ note }}
            </div>
          </div>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-if="!data" class="gt-analytical-review__empty">
        <p>暂无分析性复核数据</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gt-analytical-review {
  display: flex;
  flex-direction: column;
  height: 100%;
  font-family: var(--gt-font-family);
  background: var(--gt-color-bg-white);
}

/* ─── Tab Bar (tabs + meta in one row) ─── */
.gt-analytical-review--fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2000;
  background: #fff;
  overflow-y: auto;
  padding: 8px 0;
}

.gt-analytical-review__tab-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
}

.gt-analytical-review__tab-bar .gt-analytical-review__tabs {
  flex: 1;
  padding: 0;
}

.gt-analytical-review__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--gt-font-size-sm, 12px);
  color: var(--gt-color-text-secondary, #909399);
  white-space: nowrap;
}

.gt-analytical-review__materiality {
  padding: 2px 8px;
  background: var(--gt-color-primary-bg, #f5f0ff);
  border: 1px solid var(--gt-color-border-purple-light, #d9b8ff);
  border-radius: var(--gt-radius-sm, 4px);
}

/* ─── Tabs ─── */
.gt-analytical-review__tabs {
  padding: 0 16px;
  border-bottom: 1px solid var(--gt-color-border);
}

.gt-analytical-review__tabs :deep(.el-tabs__item) {
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-sm);
}

.gt-analytical-review__tabs :deep(.el-tabs__item.is-active) {
  color: var(--gt-color-primary);
  font-weight: 500;
}

.gt-analytical-review__tabs :deep(.el-tabs__active-bar) {
  background-color: var(--gt-color-primary);
}

/* ─── Content ─── */
.gt-analytical-review__content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.gt-analytical-review__sheet-title {
  font-size: var(--gt-font-size-base);
  font-weight: 600;
  color: var(--gt-color-text);
  margin-bottom: 12px;
}

.sheet-index {
  font-weight: 400;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  margin-left: 8px;
}

.gt-analytical-review__table-wrap {
  overflow-x: auto;
}

/* ─── Table ─── */
.gt-ar-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--gt-font-size-xs);
  line-height: 1.4;
}

.gt-ar-table th,
.gt-ar-table td {
  padding: 4px 8px;
  border: 1px solid var(--gt-color-border);
  text-align: left;
  white-space: nowrap;
}

.gt-ar-table th {
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary);
  font-weight: 500;
  position: sticky;
  top: 0;
  z-index: 1;
}

.gt-ar-table tbody tr {
  cursor: pointer;
  transition: background var(--gt-transition-fast);
}

.gt-ar-table tbody tr:hover {
  background: var(--gt-color-bg-purple-hover);
}

/* Column widths */
.col-name { min-width: 140px; white-space: normal; }
.col-row-num { width: 50px; text-align: center; }
.col-amount { width: 120px; text-align: right; font-variant-numeric: tabular-nums; }
.col-pct { width: 70px; text-align: right; font-variant-numeric: tabular-nums; }
.col-status { width: 60px; text-align: center; }
.col-reason { min-width: 180px; }

/* Ratio table columns */
.col-seq { width: 40px; text-align: center; }
.col-ratio-name { min-width: 120px; }
.col-formula { min-width: 200px; font-size: 11px; color: var(--gt-color-text-secondary); white-space: normal; }
.col-ratio-val { width: 80px; text-align: right; font-variant-numeric: tabular-nums; }
.col-direction { width: 50px; text-align: center; }

/* ─── Row status colors ─── */
.row-significant td {
  background-color: #fff0ef !important;
}

.row-attention td {
  background-color: #fff8e6 !important;
}

.row-total td {
  font-weight: 600;
  border-top: 2px solid var(--gt-color-border);
}

.is-total {
  font-weight: 600;
}

/* ─── Status tags ─── */
.status-tag {
  display: inline-block;
  padding: 1px 6px;
  border-radius: var(--gt-radius-sm);
  font-size: 11px;
  font-weight: 500;
}

.status-significant {
  background: var(--gt-color-coral-light);
  color: var(--gt-color-coral);
  border: 1px solid var(--gt-color-border-danger);
}

.status-attention {
  background: var(--gt-color-wheat-light);
  color: #b8860b;
  border: 1px solid var(--gt-color-border-warning);
}

.status-normal {
  background: var(--gt-bg-subtle);
  color: var(--gt-color-text-tertiary);
}

/* ─── Direction arrows ─── */
.direction-up {
  color: var(--gt-color-success);
  font-weight: 600;
}

.direction-down {
  color: var(--gt-color-coral);
  font-weight: 600;
}

.direction-flat {
  color: var(--gt-color-text-tertiary);
}

/* ─── Ratio category header ─── */
.gt-ar-ratio-category {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
  padding: 12px 0 6px;
  border-bottom: 1px solid var(--gt-color-border-purple);
  margin-bottom: 4px;
}

.gt-ar-ratio-table {
  margin-bottom: 16px;
}

/* ─── Ratio notes ─── */
.gt-ar-ratio-notes {
  margin-top: 16px;
  padding: 12px;
  background: var(--gt-bg-subtle);
  border-radius: var(--gt-radius-md);
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}

.gt-ar-ratio-notes__title {
  font-weight: 500;
  margin-bottom: 4px;
}

.gt-ar-ratio-notes__item {
  padding: 2px 0;
}

.gt-ar-subsection-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
  margin: 16px 0 8px;
}

.gt-ar-data-source {
  margin-top: 12px;
}

.gt-ar-hint {
  font-size: 11px;
  color: var(--gt-color-text-tertiary);
  font-style: italic;
}

/* ─── Empty state ─── */
.gt-analytical-review__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
}

/* ─── Override Element tabs border ─── */
.gt-analytical-review__tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

/* ─── Reason column input compact ─── */
.col-reason :deep(.el-input) {
  height: 22px;
}
.col-reason :deep(.el-input__wrapper) {
  padding: 0 6px;
  min-height: 22px;
}
.col-reason :deep(.el-input__inner) {
  height: 20px;
  line-height: 20px;
  font-size: 12px;
}
</style>
