<!--
  自定义查询弹窗 — 全局多维度数据查询（统一入口）

  Tab 1 业务视图：树形指标 + 预设数据源 + 简单过滤 + 转置/复制/导出（全员可用）
  Tab 2 高级构建器：表选择 + 字段勾选 + 多条件 + SQL 预览 + 导出（仅 admin/manager/partner）
-->
<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    :width="fullscreen ? '100%' : '92%'"
    :top="fullscreen ? '0' : '3vh'"
    :fullscreen="fullscreen"
    append-to-body
    destroy-on-close
    class="gt-cq-dialog"
  >
    <template #header="{ close }">
      <div class="gt-cq-dialog-header">
        <span class="gt-cq-dialog-title">🔍 高级查询</span>
        <span class="gt-cq-dialog-actions">
          <el-tooltip :content="fullscreen ? '退出全屏' : '全屏'" placement="bottom">
            <el-button text :icon="fullscreen ? Aim : FullScreen" @click="fullscreen = !fullscreen" />
          </el-tooltip>
          <el-button text :icon="Close" @click="close" />
        </span>
      </div>
    </template>
    <el-tabs v-model="activeTab" class="gt-cq-tabs" type="border-card">
      <el-tab-pane label="业务视图" name="basic">
        <div class="gt-cq-container">
          <!-- 左侧：指标树 -->
          <div class="gt-cq-sidebar">
            <div class="gt-cq-sidebar-title">数据源</div>
            <el-tree
              ref="treeRef"
              :data="indicatorTree"
              :props="{ label: 'label', children: 'children' }"
              node-key="key"
              highlight-current
              :expand-on-click-node="false"
              :default-expanded-keys="[]"
              @node-click="onIndicatorClick"
            >
              <template #default="{ data }">
                <span style="font-size: var(--gt-font-size-xs)">{{ data.label }}</span>
              </template>
            </el-tree>
          </div>
          <!-- 右侧：查询条件 + 结果 -->
          <div class="gt-cq-main">
            <div class="gt-cq-filter-bar">
              <!-- 项目选择（必填） -->
              <el-select
                v-model="localProjectId"
                size="small"
                style="width:240px"
                placeholder="选择项目"
                filterable
                :loading="projectsLoading"
              >
                <el-option
                  v-for="p in projectOptions"
                  :key="p.id"
                  :label="`${p.name}${p.audit_year ? ' · ' + p.audit_year : '（未配置年度）'}`"
                  :value="p.id"
                />
              </el-select>
              <!-- 年度（可改写：默认从项目继承） -->
              <el-input-number
                v-model="localYear"
                size="small"
                :min="2000"
                :max="2100"
                :step="1"
                style="width:120px"
                controls-position="right"
              />
              <!-- 数据源（受左树大类筛选） -->
              <el-select v-model="selectedSource" size="small" style="width:220px"
                :placeholder="clickedCategory ? `${currentCategoryLabel} 下数据源` : '数据源'">
                <el-option v-for="s in sourceOptions" :key="s.key" :label="s.label" :value="s.key" />
              </el-select>
              <el-tooltip v-if="clickedCategory" content="清除大类筛选，显示全部数据源" placement="top">
                <el-button size="small" text :icon="RefreshLeft" @click="resetCategoryFilter" />
              </el-tooltip>
              <el-input v-model="filterText" size="small" style="width:200px" placeholder="科目名/行次过滤..." clearable />
              <el-button size="small" type="primary" @click="executeQuery" :loading="loading">▶ 查询</el-button>
              <span style="flex:1" />
              <el-button size="small" @click="goToFullCustomQuery" title="跳转独立页支持模板保存/共享">📑 模板</el-button>
              <el-button size="small" @click="transposed = !transposed">{{ transposed ? '↩ 还原' : '↔ 转置' }}</el-button>
              <el-button size="small" @click="copyResult">📋 复制</el-button>
              <el-button size="small" @click="exportResult">📤 导出</el-button>
            </div>
            <!-- 上下文 chip：让用户随时看到本次查询的项目+年度+源 -->
            <div v-if="hasQueried" class="gt-cq-context-chip">
              <el-tag size="small" effect="plain" round>
                项目: {{ currentProjectLabel }}
              </el-tag>
              <el-tag size="small" effect="plain" round type="info">
                年度: {{ localYear }}
              </el-tag>
              <el-tag size="small" effect="plain" round type="success">
                {{ currentSourceLabel }}
              </el-tag>
            </div>
            <!-- 结果表格 -->
            <el-table v-if="!transposed" :data="filteredRows" v-loading="loading" border size="small"
              max-height="calc(100vh - 280px)" style="width:100%" :header-cell-style="{ background: '#f0edf5', fontSize: '12px' }">
              <template #empty>
                <el-empty :description="emptyText" :image-size="60" />
              </template>
              <el-table-column v-for="col in resultColumns" :key="col" :prop="col" :label="columnLabel(col)" min-width="120" show-overflow-tooltip>
                <template #default="{ row }">
                  <span :style="{ textAlign: isNumeric(row[col]) ? 'right' : 'left', display: 'block' }">
                    {{ formatCell(row[col]) }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
            <!-- 转置视图 -->
            <div v-else class="gt-cq-transposed" v-loading="loading">
              <el-table :data="transposedRows" border size="small" max-height="calc(100vh - 280px)" style="width:100%"
                :header-cell-style="{ background: '#f0edf5', whiteSpace: 'nowrap', fontSize: '12px' }">
                <el-table-column prop="_field_label" label="字段" width="140" fixed="left" />
                <el-table-column v-for="(_, ci) in transposedDataCols" :key="ci" :prop="'_v' + ci" :label="'#' + (ci + 1)" min-width="120" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span style="display:block; text-align:right">{{ row['_v' + ci] }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <div class="gt-cq-footer">
              <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">{{ resultRows.length }} 行 × {{ resultColumns.length }} 列{{ filterText ? `（过滤后 ${filteredRows.length} 行）` : '' }}</span>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane v-if="canUseAdvanced" name="advanced">
        <template #label>
          <span>高级构建器 <el-tag size="small" type="info" effect="plain" round style="margin-left:4px">SQL</el-tag></span>
        </template>
        <!-- 高级构建器：表选择 + 字段勾选 + 多条件 + SQL 预览（仅高权限角色可见） -->
        <AdvancedQueryBuilder embedded />
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { FullScreen, Aim, Close, RefreshLeft } from '@element-plus/icons-vue'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
import { fmtAmount } from '@/utils/formatters'
import { useAuthStore } from '@/stores/auth'
import { listProjectsWithProgress } from '@/services/commonApi'
import AdvancedQueryBuilder from '@/views/AdvancedQueryBuilder.vue'

const props = defineProps<{
  modelValue: boolean
  projectId: string
  year: number
  /** 初始 tab：'basic'（默认业务视图）/ 'advanced'（高级构建器） */
  initialTab?: 'basic' | 'advanced'
}>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean] }>()
const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })

// 全屏状态：弹窗每次打开重置为非全屏
const fullscreen = ref(false)
const dialogTitle = computed(() => '🔍 高级查询')
watch(visible, (v) => { if (!v) fullscreen.value = false })

const authStore = useAuthStore()
const router = useRouter()
const ADVANCED_ROLES = ['admin', 'manager', 'partner']
const canUseAdvanced = computed(() => ADVANCED_ROLES.includes(authStore.user?.role || ''))

/** 跳转独立页 — 复杂模板保存/共享走那里（避免本弹窗膨胀） */
function goToFullCustomQuery() {
  visible.value = false
  router.push('/custom-query')
}

const activeTab = ref<'basic' | 'advanced'>(props.initialTab || 'basic')
// 弹窗每次打开都按 initialTab 重置 active
watch(visible, (v) => { if (v) activeTab.value = props.initialTab || 'basic' })

// 项目 / 年度（默认从 props 继承，可由用户在弹窗内改写）
const localProjectId = ref<string>(props.projectId || '')
const localYear = ref<number>(props.year || new Date().getFullYear() - 1)
watch(() => props.projectId, (pid) => { if (pid && !localProjectId.value) localProjectId.value = pid })
watch(() => props.year, (y) => { if (y) localYear.value = y })

interface ProjectOption { id: string; name: string; audit_year?: number | null }
const projectOptions = ref<ProjectOption[]>([])
const projectsLoading = ref(false)
async function loadProjectList() {
  if (projectOptions.value.length > 0) return
  projectsLoading.value = true
  try {
    const list = await listProjectsWithProgress()
    projectOptions.value = list.map((p: any) => ({ id: p.id, name: p.name, audit_year: p.audit_year }))
    // 弹窗打开时若 localProjectId 还没值，自动取第一个
    if (!localProjectId.value && projectOptions.value.length > 0) {
      localProjectId.value = projectOptions.value[0].id
      const p0 = projectOptions.value[0]
      if (p0.audit_year) localYear.value = p0.audit_year
    }
  } catch { projectOptions.value = [] } finally { projectsLoading.value = false }
}
// 弹窗打开时按需加载项目列表
watch(visible, (v) => { if (v) loadProjectList() }, { immediate: true })
// 切换项目时若该项目有 audit_year 则同步
watch(localProjectId, (pid) => {
  const p = projectOptions.value.find(x => x.id === pid)
  if (p?.audit_year) localYear.value = p.audit_year
})

const loading = ref(false)
const transposed = ref(false)
const filterText = ref('')
const selectedSource = ref('report_balance_sheet')
const filterReportType = ref('balance_sheet')
const resultRows = ref<any[]>([])
const resultColumns = ref<string[]>([])
const indicatorTree = ref<any[]>([])
const treeRef = ref<any>(null)
// 是否已发起过查询（用于显示上下文 chip 与友好空态）
const hasQueried = ref(false)
// 左树点击的大类 key（null = 未点击大类，下拉显示全部）
const clickedCategory = ref<string | null>(null)

// 当前项目/数据源的可读标签（chip 显示）
const currentProjectLabel = computed(() => {
  const p = projectOptions.value.find(x => x.id === localProjectId.value)
  return p ? p.name : '—'
})
const currentSourceLabel = computed(() => {
  return sourceOptions.value.find(s => s.key === selectedSource.value)?.label || selectedSource.value
})
const currentCategoryLabel = computed(() => {
  if (!clickedCategory.value) return ''
  const cat = indicatorTree.value.find((c: any) => c.key === clickedCategory.value)
  return cat?.label || clickedCategory.value
})

// 空态文案：根据是否已查询给不同提示
const emptyText = computed(() => {
  if (!hasQueried.value) return '请选择项目 + 数据源后点击「▶ 查询」'
  if (!localProjectId.value) return '请先选择项目'
  return `当前项目「${currentProjectLabel.value}」${localYear.value} 年度暂无该数据源记录`
})

// 静态预设数据源（树未加载时的兜底 + 用于补全树里没有的旧 key）
const STATIC_SOURCES = [
  { key: 'report_balance_sheet', label: '📊 资产负债表', parentKey: 'report' },
  { key: 'report_income_statement', label: '📊 利润表', parentKey: 'report' },
  { key: 'report_cash_flow_statement', label: '📊 现金流量表', parentKey: 'report' },
  { key: 'tb_detail', label: '📋 科目明细', parentKey: 'trial_balance' },
  { key: 'tb_summary', label: '📋 试算平衡表', parentKey: 'trial_balance' },
  { key: 'disclosure_note', label: '📝 附注数据', parentKey: 'disclosure' },
  { key: 'adj_aje', label: '📐 审计调整(AJE)', parentKey: 'adjustment' },
  { key: 'adj_rcl', label: '📐 重分类(RCL)', parentKey: 'adjustment' },
  { key: 'ws_info', label: '📑 基本信息表', parentKey: 'worksheet' },
  { key: 'ws_elimination', label: '📑 抵消分录', parentKey: 'worksheet' },
]

// 数据源全集：从 indicatorTree 递归扁平化派生（支持 N 层嵌套，每个叶子带顶层 parentKey）
// 附注 3 层：disclosure → 货币资金大类 → 五-1-1 明细，明细的 parentKey 仍归到 'disclosure'
const allSources = computed(() => {
  if (!indicatorTree.value.length) return STATIC_SOURCES
  const list: { key: string; label: string; parentKey: string }[] = []
  function walk(node: any, topKey: string, prefix: string) {
    const childList = node.children || []
    if (childList.length === 0) {
      // 叶子
      list.push({
        key: node.key,
        label: prefix ? `${prefix} / ${node.label}` : node.label,
        parentKey: topKey,
      })
      return
    }
    for (const child of childList) {
      const nextPrefix = prefix ? `${prefix} / ${node.label}` : node.label
      walk(child, topKey, nextPrefix)
    }
  }
  for (const cat of indicatorTree.value) {
    const icon = cat.icon || ''
    for (const leaf of (cat.children || [])) {
      walk(leaf, cat.key, icon)
    }
  }
  return list.length ? list : STATIC_SOURCES
})

// 下拉选项：受 clickedCategory 过滤（未点大类时显示全部）
const sourceOptions = computed(() => {
  if (!clickedCategory.value) return allSources.value
  return allSources.value.filter(s => s.parentKey === clickedCategory.value)
})

// 叶子 → 父大类反查表
const leafToCategory = computed(() => {
  const m: Record<string, string> = {}
  for (const s of allSources.value) m[s.key] = s.parentKey
  return m
})

const filteredRows = computed(() => {
  if (!filterText.value) return resultRows.value
  const kw = filterText.value.toLowerCase()
  return resultRows.value.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(kw)))
})

// 转置视图数据：每个原始列变成一行，每个原始行变成一列
const transposedDataCols = computed(() => filteredRows.value.slice(0, 50))
const transposedRows = computed(() => {
  const rows = transposedDataCols.value
  return resultColumns.value.map(col => {
    const entry: Record<string, any> = { _field_label: columnLabel(col) }
    rows.forEach((row, ci) => { entry['_v' + ci] = formatCell(row[col]) })
    return entry
  })
})

const COLUMN_LABELS: Record<string, string> = {
  row_code: '行次', row_name: '项目', current_period_amount: '本期金额', prior_period_amount: '上期金额',
  account_code: '科目编码', account_name: '科目名称', opening_balance: '期初余额', closing_balance: '期末余额',
  debit_amount: '借方发生额', credit_amount: '贷方发生额', unadjusted: '未审数', audited: '审定数',
  aje_dr: 'AJE借', aje_cr: 'AJE贷', rcl_dr: 'RCL借', rcl_cr: 'RCL贷',
  entry_number: '分录号', description: '说明', status: '状态', section_id: '章节ID',
  company_name: '企业名称', company_code: '企业代码', holding_type: '持股类型',
  direction: '借贷', subject: '科目', amount: '金额', desc: '说明',
  summary: '审定汇总', equity_dr: '权益抵消借', equity_cr: '权益抵消贷',
  indent: '层级', is_total: '合计行', non_common_ratio: '持股比例',
  headers: '表头', row_count: '行数',
}
function columnLabel(col: string) { return COLUMN_LABELS[col] || col }
function isNumeric(v: any) { return v != null && !isNaN(Number(v)) }
function formatCell(v: any) {
  if (v == null) return '-'
  if (Array.isArray(v)) return v.join(', ')
  if (typeof v === 'boolean') return v ? '是' : '否'
  const s = String(v)
  // 不格式化长字符串（如信用代码、编码等）
  if (s.length > 12 || /[a-zA-Z\u4e00-\u9fff]/.test(s)) return s
  const n = Number(v)
  if (!isNaN(n) && s.trim() !== '') return fmtAmount(n)
  return s
}

// 工具：递归找节点的第一个叶子（用于点大类自动选明细）
function findFirstLeaf(node: any): any | null {
  if (!node) return null
  if (!node.children?.length) return node
  for (const c of node.children) {
    const r = findFirstLeaf(c)
    if (r) return r
  }
  return null
}

// 工具：在 indicatorTree 中找节点 key 对应的顶层大类 key（disclosure/report/...）
function findTopCategoryOf(targetKey: string): string | null {
  for (const top of indicatorTree.value) {
    if (top.key === targetKey) return top.key
    function walk(n: any): boolean {
      if (n.key === targetKey) return true
      for (const c of (n.children || [])) {
        if (walk(c)) return true
      }
      return false
    }
    for (const c of (top.children || [])) {
      if (walk(c)) return top.key
    }
  }
  return null
}

function onIndicatorClick(data: any) {
  if (data.children?.length) {
    // 大类/中间层节点：定位顶层 category + 递归找第一明细叶子
    const topKey = findTopCategoryOf(data.key) || data.key
    clickedCategory.value = topKey
    const firstLeaf = findFirstLeaf(data)
    if (firstLeaf?.key) {
      selectedSource.value = firstLeaf.key
      if (firstLeaf.key.startsWith('report_')) filterReportType.value = firstLeaf.key.replace('report_', '')
    }
  } else if (data.key) {
    // 叶子节点：设 source，并反查顶层大类同步 clickedCategory
    selectedSource.value = data.key
    if (data.key.startsWith('report_')) filterReportType.value = data.key.replace('report_', '')
    const parent = leafToCategory.value[data.key] || findTopCategoryOf(data.key)
    if (parent) clickedCategory.value = parent
  }
}

function resetCategoryFilter() {
  clickedCategory.value = null
  if (treeRef.value) {
    try { treeRef.value.setCurrentKey(null) } catch { /* ignore */ }
  }
}

// selectedSource 改变时自动派生 filterReportType 并同步左侧树高亮
watch(selectedSource, (v) => {
  if (v.startsWith('report_')) filterReportType.value = v.replace('report_', '')
  // 反向高亮树节点
  if (treeRef.value && v) {
    try { treeRef.value.setCurrentKey(v) } catch { /* ignore */ }
  }
})

async function executeQuery() {
  if (!localProjectId.value) { ElMessage.warning('请先选择项目'); return }
  hasQueried.value = true
  loading.value = true
  try {
    const source = selectedSource.value
    const filters: Record<string, any> = {}
    if (source.startsWith('report_')) filters.report_type = filterReportType.value
    if (source === 'adj_aje') filters.adjustment_type = 'AJE'
    if (source === 'adj_rcl') filters.adjustment_type = 'RCL'
    if (source.startsWith('ws_')) filters.sheet_key = source.replace('ws_', '')
    if (filterText.value && (source === 'tb_detail')) filters.account_name = filterText.value

    const data = await api.post('/api/custom-query/execute', {
      project_id: localProjectId.value, year: localYear.value, source, filters,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data
    resultRows.value = result?.rows || []
    resultColumns.value = result?.columns || (resultRows.value.length ? Object.keys(resultRows.value[0]) : [])
    if (!resultRows.value.length) ElMessage.info('查询无结果')
  } catch (err: any) {
    handleApiError(err, '查询失败')
  } finally { loading.value = false }
}

function copyResult() {
  if (!resultRows.value.length) { ElMessage.warning('无数据'); return }
  const headers = resultColumns.value.map(c => columnLabel(c))
  const dataRows = filteredRows.value.map(r => resultColumns.value.map(c => r[c] ?? ''))
  const text = [headers.join('\t'), ...dataRows.map(r => r.join('\t'))].join('\n')
  const html = `<table border="1"><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>${dataRows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`
  try {
    navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })])
    ElMessage.success(`已复制 ${filteredRows.value.length} 行`)
  } catch { navigator.clipboard?.writeText(text); ElMessage.success('已复制为文本') }
}

async function exportResult() {
  if (!resultRows.value.length) { ElMessage.warning('无数据'); return }
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const headers = resultColumns.value.map(c => columnLabel(c))
  const dataRows = filteredRows.value.map(r => resultColumns.value.map(c => r[c] ?? ''))
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = headers.map(() => ({ wch: 16 }))
  XLSX.utils.book_append_sheet(wb, ws, '查询结果')
  // 文件名带项目名 + 数据源标签 + 年度，便于用户辨识
  const projName = (currentProjectLabel.value || '查询').replace(/[\\/:*?"<>|]/g, '_')
  const srcName = (currentSourceLabel.value || selectedSource.value).replace(/[📊📋📝📐📑\s]/g, '')
  XLSX.writeFile(wb, `${projName}_${srcName}_${localYear.value}.xlsx`)
  ElMessage.success('已导出')
}

// 加载指标树（按项目缓存：每个项目独立 sessionStorage key）
const INDICATOR_CACHE_KEY_PREFIX = 'gt:custom-query:indicators-v5:'

function _indicatorCacheKey(pid: string | undefined) {
  return `${INDICATOR_CACHE_KEY_PREFIX}${pid || 'no-project'}`
}

async function loadIndicators(pid: string | undefined) {
  const cacheKey = _indicatorCacheKey(pid)
  // 先尝试缓存
  try {
    const cached = sessionStorage.getItem(cacheKey)
    if (cached) {
      indicatorTree.value = JSON.parse(cached)
      return
    }
  } catch { /* ignore */ }
  try {
    const url = pid ? `/api/custom-query/indicators?project_id=${encodeURIComponent(pid)}` : '/api/custom-query/indicators'
    const data = await api.get(url)
    indicatorTree.value = Array.isArray(data) ? data : (data ?? [])
    try { sessionStorage.setItem(cacheKey, JSON.stringify(indicatorTree.value)) } catch { /* ignore */ }
  } catch {
    // 兜底：用 STATIC_SOURCES 重建一棵简易树（按 parentKey 分组）
    const grouped: Record<string, any[]> = {}
    for (const s of STATIC_SOURCES) {
      (grouped[s.parentKey] ||= []).push({ key: s.key, label: s.label })
    }
    indicatorTree.value = Object.entries(grouped).map(([k, children]) => ({ key: k, label: k, children }))
  }
}

// 项目切换 → 重新拉树（带项目级缓存）
watch(localProjectId, (pid) => {
  if (pid) loadIndicators(pid)
}, { immediate: false })

// 弹窗第一次打开时按当前 project 加载（如果尚未加载）
watch(visible, (v) => {
  if (v && !indicatorTree.value.length) loadIndicators(localProjectId.value)
})

// 初次挂载时按现有 projectId 加载（弹窗未必打开但提前缓存）
loadIndicators(localProjectId.value)
</script>

<style scoped>
.gt-cq-container { display: flex; gap: 12px; height: calc(100vh - 140px); }
.gt-cq-sidebar { width: 200px; flex-shrink: 0; border-right: 1px solid var(--gt-color-border-purple); padding-right: 8px; overflow-y: auto; }
.gt-cq-sidebar-title { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-primary); margin-bottom: 8px; }
.gt-cq-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.gt-cq-filter-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.gt-cq-context-chip {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
  padding: 4px 0;
}
.gt-cq-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.gt-cq-dialog-title {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-text);
}
.gt-cq-dialog-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.gt-cq-footer { padding: 6px 0; }
.gt-cq-transposed { overflow: auto; flex: 1; }
</style>
