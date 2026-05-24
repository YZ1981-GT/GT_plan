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
            <div class="gt-cq-sidebar-title">
              数据源
              <el-tooltip :content="treeViewMode === 'source' ? '切换为按模板形态分组' : '切换为按数据源分类'" placement="top">
                <el-button
                  size="small"
                  circle
                  :type="treeViewMode === 'template' ? 'primary' : 'default'"
                  style="margin-left: auto; font-size: 12px"
                  @click="toggleTreeViewMode"
                >
                  {{ treeViewMode === 'source' ? '📂' : '📋' }}
                </el-button>
              </el-tooltip>
            </div>
            <el-tree
              ref="treeRef"
              :data="displayTree"
              :props="{ label: 'label', children: 'children', disabled: 'disabled' }"
              node-key="key"
              highlight-current
              :expand-on-click-node="false"
              :default-expanded-keys="[]"
              @node-click="onIndicatorClick"
            >
              <template #default="{ data }">
                <span :class="['gt-cq-tree-node', { 'gt-cq-tree-node-disabled': data.disabled }]"
                  :title="data.disabled ? '该底稿在当前项目中已裁剪，不可选' : ''">
                  {{ data.label }}
                </span>
              </template>
            </el-tree>
          </div>
          <!-- 右侧：查询条件 + 结果 -->
          <div class="gt-cq-main">
            <div class="gt-cq-filter-bar">
              <!-- 项目选择（可选：不选 = 模板浏览模式） -->
              <el-select
                v-model="localProjectId"
                size="small"
                style="width:240px"
                placeholder="选择项目（可空 = 模板浏览）"
                filterable
                clearable
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
              <el-button size="small" @click="saveAsTemplate" :disabled="!selectedSource" title="保存当前选区/条件为查询模板">💾 保存</el-button>
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
              <el-tag v-if="sheetCellRange" size="small" effect="dark" round type="warning"
                closable @close="sheetCellRange = ''" @click="reopenSheetPicker"
                style="cursor:pointer">
                选区: {{ sheetCellRange }} (点击重选)
              </el-tag>
            </div>
            <!-- 结果表格 -->
            <el-table v-if="!transposed" :data="filteredRows" v-loading="loading" border size="small"
              max-height="calc(100vh - 280px)" style="width:100%" :header-cell-style="{ background: '#f0edf5', fontSize: '12px' }"
              @row-contextmenu="onRowContextMenu">
              <template #empty>
                <el-empty :description="emptyText" :image-size="60" />
              </template>
              <el-table-column v-for="col in resultColumns" :key="col" :prop="col" :label="columnLabel(col)" min-width="120" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="col === 'cell_ref' && row.wp_code" class="gt-cq-cell-ref-link"
                    @click="jumpToCell(row)" :title="`跳到底稿 ${row.wp_code} ${row.sheet_name || ''} 单元格 ${row[col]}`">
                    {{ formatCell(row[col]) }}
                  </span>
                  <span v-else :style="{ textAlign: isNumeric(row[col]) ? 'right' : 'left', display: 'block' }">
                    {{ formatCell(row[col]) }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
            <!-- 右键菜单（Req 14 AC 2: 跳模板溯源） -->
            <div
              v-if="ctxMenuVisible"
              class="gt-cq-ctx-menu"
              :style="{ left: ctxMenuPos.x + 'px', top: ctxMenuPos.y + 'px' }"
            >
              <div class="gt-cq-ctx-menu-item" @click="onTraceToTemplate">🔗 跳模板溯源</div>
            </div>
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

    <!-- Sheet 单元格区域选择器（点 sheet 叶子时弹出） -->
    <SheetCellRangePicker
      v-model="sheetPickerVisible"
      :wp-code="sheetPickerCtx.wpCode"
      :sheet-name="sheetPickerCtx.sheetName"
      :project-id="localProjectId"
      @confirm="onSheetRangeConfirm"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FullScreen, Aim, Close, RefreshLeft } from '@element-plus/icons-vue'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
import { fmtAmount } from '@/utils/formatters'
import { useAuthStore } from '@/stores/auth'
import { listProjectsWithProgress } from '@/services/commonApi'
import AdvancedQueryBuilder from '@/views/AdvancedQueryBuilder.vue'
import SheetCellRangePicker from '@/components/query/SheetCellRangePicker.vue'

const props = defineProps<{
  modelValue: boolean
  projectId: string
  year: number
  /** 初始 tab：'basic'（默认业务视图）/ 'advanced'（高级构建器） */
  initialTab?: 'basic' | 'advanced'
  /** 初始 source（从模板页跳入时预填） */
  initialSource?: string
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

// ─── 树视图模式 (Req 14 AC 4): 按数据源分类 / 按模板形态分组 ─────────────────
type TreeViewMode = 'source' | 'template'
const treeViewMode = ref<TreeViewMode>(
  (sessionStorage.getItem('gt:cq:tree-view-mode') as TreeViewMode) || 'source'
)
function toggleTreeViewMode() {
  treeViewMode.value = treeViewMode.value === 'source' ? 'template' : 'source'
  sessionStorage.setItem('gt:cq:tree-view-mode', treeViewMode.value)
}

// 按模板形态分组视图：把 indicatorTree 重组为 4 大类（底稿/报表/附注/调整分录）
const templateGroupedTree = computed(() => {
  if (!indicatorTree.value.length) return []
  const groups: Record<string, any> = {
    workpaper: { key: '_tpl_workpaper', label: '📋 底稿模板', children: [] as any[] },
    report: { key: '_tpl_report', label: '📊 报表模板', children: [] as any[] },
    note: { key: '_tpl_note', label: '📝 附注模板', children: [] as any[] },
    other: { key: '_tpl_other', label: '🔧 其他（调整/试算）', children: [] as any[] },
  }
  for (const cat of indicatorTree.value) {
    const k = (cat.key || '').toLowerCase()
    if (k.includes('workpaper') || k.includes('底稿') || k.startsWith('wp_')) {
      groups.workpaper.children.push(cat)
    } else if (k.includes('report') || k.includes('报表')) {
      groups.report.children.push(cat)
    } else if (k.includes('disclosure') || k.includes('附注') || k.includes('note')) {
      groups.note.children.push(cat)
    } else {
      groups.other.children.push(cat)
    }
  }
  return Object.values(groups).filter(g => g.children.length > 0)
})

// 当前展示的树数据
const displayTree = computed(() =>
  treeViewMode.value === 'source' ? indicatorTree.value : templateGroupedTree.value
)

// Sheet 单元格区域选择器状态
const sheetPickerVisible = ref(false)
const sheetPickerCtx = ref<{ wpCode: string; sheetName?: string }>({ wpCode: '' })
const sheetCellRange = ref<string>('')  // 用户在 sheet picker 选中的 cell range（如 'A1:E5'）

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
  // 递归找 clickedCategory 节点的 label（任意层）
  function findLabel(nodes: any[]): string | null {
    for (const n of nodes) {
      if (n.key === clickedCategory.value) return n.label || ''
      if (n.children?.length) {
        const r = findLabel(n.children)
        if (r !== null) return r
      }
    }
    return null
  }
  return findLabel(indicatorTree.value) || (clickedCategory.value as string)
})

// 空态文案：根据是否已查询给不同提示
const emptyText = computed(() => {
  if (!hasQueried.value) return '请选择数据源后点击「▶ 查询」（项目可选，未选时仅展示模板结构）'
  if (!localProjectId.value && _sourceRequiresProject(selectedSource.value)) return '该数据源需先选择项目'
  return localProjectId.value
    ? `当前项目「${currentProjectLabel.value}」${localYear.value} 年度暂无该数据源记录`
    : '模板浏览模式（未选项目）：仅显示报表/附注/底稿模板结构，不含项目实际值'
})

/** 判定 source 是否必须传 project_id（试算/账簿/底稿等业务数据必须，报表/附注/调整等模板可缺省） */
function _sourceRequiresProject(s: string): boolean {
  // 模板可浏览的源（无项目时返回模板默认）
  const TEMPLATE_OK_PREFIXES = ['report_', 'disclosure_note:', 'report_lines']
  const TEMPLATE_OK = ['report', 'disclosure', 'disclosure_note', 'report_lines']
  if (TEMPLATE_OK.includes(s)) return false
  if (TEMPLATE_OK_PREFIXES.some(p => s.startsWith(p))) return false
  return true  // 其他源（试算/账簿/底稿单元格/合并单位等）必须传 project_id
}

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

// 数据源全集：从 indicatorTree 递归扁平化派生（支持 N 层嵌套）
// 每个叶子带 ancestorKeys（从顶到自己的所有祖先 key 路径），用于按任意层过滤下拉
const allSources = computed(() => {
  if (!indicatorTree.value.length) return STATIC_SOURCES.map(s => ({ ...s, ancestorKeys: [s.parentKey] }))
  const list: { key: string; label: string; parentKey: string; ancestorKeys: string[] }[] = []
  function walk(node: any, ancestors: string[], prefix: string) {
    // 灰度节点跳过（不进入下拉数据源池）
    if (node.disabled) return
    const childList = node.children || []
    const myAncestors = [...ancestors, node.key]
    if (childList.length === 0) {
      // 叶子
      list.push({
        key: node.key,
        label: prefix ? `${prefix} / ${node.label}` : node.label,
        parentKey: ancestors[0] || node.key,
        ancestorKeys: myAncestors,
      })
      return
    }
    for (const child of childList) {
      const nextPrefix = prefix ? `${prefix} / ${node.label}` : node.label
      walk(child, myAncestors, nextPrefix)
    }
  }
  for (const cat of indicatorTree.value) {
    const icon = cat.icon || ''
    walk(cat, [], icon)
  }
  return list.length
    ? list
    : STATIC_SOURCES.map(s => ({ ...s, ancestorKeys: [s.parentKey] }))
})

// 下拉选项：受 clickedCategory 过滤（点击任意层时只显示该节点子树下叶子，未点击 = 显示全部）
const sourceOptions = computed(() => {
  if (!clickedCategory.value) return allSources.value
  return allSources.value.filter(s => s.ancestorKeys.includes(clickedCategory.value as string))
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
  // 灰度节点不可选中
  if (data.disabled) {
    ElMessage.info('该底稿在当前项目中已裁剪，无法查询')
    return
  }
  if (data.children?.length) {
    // 大类/中间层节点：clickedCategory 直接设为该节点 key（精确过滤当前子树）
    clickedCategory.value = data.key
    const firstLeaf = findFirstLeaf(data)
    if (firstLeaf?.key) {
      selectedSource.value = firstLeaf.key
      if (firstLeaf.key.startsWith('report_')) filterReportType.value = firstLeaf.key.replace('report_', '')
    }
  } else if (data.key) {
    // 叶子节点：设 source，clickedCategory 设为该叶子的直接父节点（让下拉只显示同 sheet 范围）
    selectedSource.value = data.key
    if (data.key.startsWith('report_')) filterReportType.value = data.key.replace('report_', '')
    const src = allSources.value.find(s => s.key === data.key)
    if (src && src.ancestorKeys.length >= 2) {
      // 取叶子的直接父节点 key（ancestorKeys 倒数第二个，最后一个是叶子自己）
      clickedCategory.value = src.ancestorKeys[src.ancestorKeys.length - 2]
    } else {
      clickedCategory.value = leafToCategory.value[data.key] || findTopCategoryOf(data.key)
    }
    // 底稿 sheet 叶子（含 |）→ 弹出单元格区域选择器
    if (data.key.startsWith('workpaper:') && data.key.includes('|')) {
      const tail = data.key.slice('workpaper:'.length)
      const [wpCode, sheetName] = tail.split('|', 2)
      sheetPickerCtx.value = { wpCode, sheetName }
      sheetPickerVisible.value = true
    }
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
  // 用户在右侧下拉直接切换到 sheet 选项 → 同样弹出选区器
  if (v.startsWith('workpaper:') && v.includes('|')) {
    const tail = v.slice('workpaper:'.length)
    const [wpCode, sheetName] = tail.split('|', 2)
    // 不在弹窗已开时重复弹（避免左树点击时再开一次）
    if (!sheetPickerVisible.value || sheetPickerCtx.value.wpCode !== wpCode || sheetPickerCtx.value.sheetName !== sheetName) {
      sheetPickerCtx.value = { wpCode, sheetName }
      sheetPickerVisible.value = true
    }
    // 切换 sheet 时重置已选 cell range（旧选区不再适用）
    sheetCellRange.value = ''
  } else {
    // 切到非 sheet 选项时清空 range 上下文
    sheetCellRange.value = ''
  }
})

function onSheetRangeConfirm(payload: { wp_code: string; sheet_name?: string; range: string }) {
  sheetCellRange.value = payload.range
  // 在结果表格区直接预览：把选区拆成 cell 清单（如 A1:C3 → A1,A2,A3,B1,...,C3）
  const cells = _expandRange(payload.range)
  resultColumns.value = ['index', 'wp_code', 'sheet_name', 'cell_ref', 'value']
  resultRows.value = cells.map((c, i) => ({
    index: i + 1,
    wp_code: payload.wp_code,
    sheet_name: payload.sheet_name || '',
    cell_ref: c,
    value: '— 待查询 —',
  }))
  hasQueried.value = true
  ElMessage.success(`已锁定 ${payload.wp_code} / ${payload.sheet_name || ''} 选区 ${payload.range}（共 ${cells.length} 个单元格），点「▶ 查询」调取后台数据`)
}

/** 展开 'A1:C3' / 'B5' 形式 range 为单元格清单 */
function _expandRange(range: string): string[] {
  const m = /^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$/.exec(range)
  if (!m) return []
  const c1 = _colToIdx(m[1]); const r1 = parseInt(m[2], 10)
  const c2 = m[3] ? _colToIdx(m[3]) : c1
  const r2 = m[4] ? parseInt(m[4], 10) : r1
  const out: string[] = []
  const MAX = 500  // 防爆量
  for (let r = r1; r <= r2; r++) {
    for (let c = c1; c <= c2; c++) {
      out.push(`${_idxToCol(c)}${r}`)
      if (out.length >= MAX) return out
    }
  }
  return out
}
function _colToIdx(s: string): number {
  let n = 0
  for (let i = 0; i < s.length; i++) n = n * 26 + (s.charCodeAt(i) - 64)
  return n - 1
}
function _idxToCol(i: number): string {
  if (i < 26) return String.fromCharCode(65 + i)
  return String.fromCharCode(65 + Math.floor(i / 26) - 1) + String.fromCharCode(65 + (i % 26))
}

function reopenSheetPicker() {
  // chip 点击重选：当前 selectedSource 必须是 sheet 形式才能重开
  const v = selectedSource.value
  if (!v.startsWith('workpaper:') || !v.includes('|')) return
  const tail = v.slice('workpaper:'.length)
  const [wpCode, sheetName] = tail.split('|', 2)
  sheetPickerCtx.value = { wpCode, sheetName }
  sheetPickerVisible.value = true
}

/** 保存当前选区+条件为查询模板（POST /api/custom-query/templates） */
async function saveAsTemplate() {
  if (!selectedSource.value) return
  try {
    const { value: name } = await ElMessageBox.prompt('为该查询模板命名（项目+源+选区会自动记录）', '保存查询模板', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputPattern: /.+/,
      inputErrorMessage: '请输入名称',
    })
    if (!name) return
    const config: Record<string, any> = {
      project_id: localProjectId.value,
      year: localYear.value,
      source: selectedSource.value,
      filter_text: filterText.value,
    }
    if (sheetCellRange.value) config.cell_range = sheetCellRange.value
    if (sheetPickerCtx.value.sheetName) config.sheet_name = sheetPickerCtx.value.sheetName
    await api.post('/api/custom-query/templates', {
      name,
      description: `${currentSourceLabel.value}${sheetCellRange.value ? ' / ' + sheetCellRange.value : ''}`,
      data_source: selectedSource.value,
      config,
      scope: 'private',
    })
    ElMessage.success(`已保存模板「${name}」`)
  } catch (err: any) {
    if (err === 'cancel' || err?.action === 'cancel') return
    handleApiError(err, '保存失败')
  }
}

/** 结果表格 cell_ref 列点击 → 跳到 WorkpaperEditor + 高亮该 cell */
async function jumpToCell(row: any) {
  if (!row.wp_code || !localProjectId.value) return
  try {
    const data = await api.get('/api/custom-query/wp-id-by-code', {
      params: { project_id: localProjectId.value, wp_code: row.wp_code },
    }) as any
    const wpId = data?.wp_id
    if (!wpId) {
      ElMessage.warning(`底稿 ${row.wp_code} 在当前项目不存在`)
      return
    }
    visible.value = false  // 关闭弹窗
    router.push({
      name: 'WorkpaperEditor',
      params: { projectId: localProjectId.value, wpId },
      query: {
        sheet: row.sheet_name || undefined,
        highlight: row.cell_ref || undefined,
      },
    })
  } catch (err: any) {
    handleApiError(err, '跳转失败')
  }
}

// ─── 右键菜单：跳模板溯源 (Req 14 AC 2) ─────────────────────────────────────
const ctxMenuVisible = ref(false)
const ctxMenuPos = ref({ x: 0, y: 0 })
const ctxMenuRow = ref<any>(null)

function onRowContextMenu(row: any, _col: any, event: MouseEvent) {
  event.preventDefault()
  ctxMenuRow.value = row
  ctxMenuPos.value = { x: event.clientX, y: event.clientY }
  ctxMenuVisible.value = true
  // 点击其他地方关闭
  const closeMenu = () => {
    ctxMenuVisible.value = false
    document.removeEventListener('click', closeMenu)
  }
  setTimeout(() => document.addEventListener('click', closeMenu), 0)
}

async function onTraceToTemplate() {
  ctxMenuVisible.value = false
  const row = ctxMenuRow.value
  if (!row) return

  // 构建 URI：优先用 source 字段，否则从 row 数据推断
  let uri = ''
  if (row.wp_code && row.sheet_name) {
    uri = `workpaper:${row.wp_code}|${row.sheet_name}`
    if (row.cell_ref) uri += `|${row.cell_ref}`
  } else if (row.module === 'report' && row.report_type) {
    uri = `report:${row.report_type}`
  } else if (row.module === 'note' && row.section_id) {
    uri = `note:${row.section_id}`
  } else if (selectedSource.value) {
    uri = selectedSource.value
  }

  if (!uri) {
    ElMessage.warning('无法确定数据源 URI')
    return
  }

  try {
    const resp = await api.get('/api/custom-query/address-resolve', {
      params: { uri },
    }) as any
    if (!resp.registered && resp.module === 'workpaper') {
      ElMessage.warning('该模板未在 registry，请先 migrate')
      return
    }
    visible.value = false
    router.push({ path: resp.route_path, query: resp.route_query })
  } catch (err: any) {
    handleApiError(err, '模板溯源失败')
  }
}

async function executeQuery() {
  if (!localProjectId.value && _sourceRequiresProject(selectedSource.value)) {
    ElMessage.warning('该数据源需先选择项目（模板浏览模式仅支持报表/附注/底稿模板）')
    return
  }
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
      project_id: localProjectId.value, year: localYear.value, source,
      filters: sheetCellRange.value ? { ...filters, cell_range: sheetCellRange.value } : filters,
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

// 加载指标树（按 project_id + 后端 schema_version 双键缓存：树结构改动后端升 schema 即自动失效）
// 缓存键形如 'gt:custom-query:indicators:{schema_version}:{pid}'，schema 升版后旧 key 自然不命中
const INDICATOR_CACHE_KEY_PREFIX = 'gt:custom-query:indicators:'
const INDICATOR_SCHEMA_HEADER = 'x-indicators-schema-version'

function _indicatorCacheKey(pid: string | undefined, schemaVersion: string | number) {
  return `${INDICATOR_CACHE_KEY_PREFIX}${schemaVersion}:${pid || 'no-project'}`
}

async function loadIndicators(pid: string | undefined) {
  // 拉数据：用原始 fetch 才能拿到 response headers（apiProxy 只返 body）
  const url = pid ? `/api/custom-query/indicators?project_id=${encodeURIComponent(pid)}` : '/api/custom-query/indicators'
  try {
    const token = localStorage.getItem('access_token') || ''
    const resp = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    const schemaVersion = resp.headers.get(INDICATOR_SCHEMA_HEADER) || 'unknown'
    const cacheKey = _indicatorCacheKey(pid, schemaVersion)
    // 命中缓存优先（同 schema_version 下结构稳定）
    try {
      const cached = sessionStorage.getItem(cacheKey)
      if (cached) {
        indicatorTree.value = JSON.parse(cached)
        return
      }
    } catch { /* ignore */ }
    const json = await resp.json()
    // 后端 ApiResponse 包装 {code, data} 或裸数组
    const tree = Array.isArray(json) ? json : (json?.data ?? json ?? [])
    indicatorTree.value = Array.isArray(tree) ? tree : []
    try { sessionStorage.setItem(cacheKey, JSON.stringify(indicatorTree.value)) } catch { /* ignore */ }
    // 清理旧 schema 版本的缓存（保持 sessionStorage 干净）
    _purgeStaleIndicatorCache(schemaVersion)
  } catch {
    // 兜底：用 STATIC_SOURCES 重建一棵简易树（按 parentKey 分组）
    const grouped: Record<string, any[]> = {}
    for (const s of STATIC_SOURCES) {
      (grouped[s.parentKey] ||= []).push({ key: s.key, label: s.label })
    }
    indicatorTree.value = Object.entries(grouped).map(([k, children]) => ({ key: k, label: k, children }))
  }
}

function _purgeStaleIndicatorCache(currentVersion: string) {
  try {
    const keys: string[] = []
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i)
      if (k && k.startsWith(INDICATOR_CACHE_KEY_PREFIX) && !k.startsWith(`${INDICATOR_CACHE_KEY_PREFIX}${currentVersion}:`)) {
        keys.push(k)
      }
    }
    keys.forEach(k => sessionStorage.removeItem(k))
  } catch { /* ignore */ }
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

// ─── Req 14 AC 5: open-custom-query 事件带 source 时自动选中 + 树 reveal ────
watch(() => props.initialSource, (source) => {
  if (!source) return
  // 等树加载完成后再 reveal
  const doReveal = () => {
    selectedSource.value = source
    // 在树中查找匹配节点并展开 + 选中
    if (treeRef.value) {
      treeRef.value.setCurrentKey(source)
      // 尝试展开祖先节点
      const node = treeRef.value.getNode(source)
      if (node) {
        let parent = node.parent
        while (parent && parent.key) {
          parent.expanded = true
          parent = parent.parent
        }
        // scroll into view
        setTimeout(() => {
          const el = treeRef.value?.$el?.querySelector('.is-current')
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }, 100)
      }
    }
  }
  if (indicatorTree.value.length) {
    doReveal()
  } else {
    // 树尚未加载，等加载完成后 reveal
    const stop = watch(indicatorTree, (tree) => {
      if (tree.length) {
        stop()
        setTimeout(doReveal, 50)
      }
    })
  }
})
</script>

<style scoped>
.gt-cq-container { display: flex; gap: 12px; height: calc(100vh - 140px); }
.gt-cq-sidebar { width: 200px; flex-shrink: 0; border-right: 1px solid var(--gt-color-border-purple); padding-right: 8px; overflow-y: auto; }
.gt-cq-sidebar-title { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-primary); margin-bottom: 8px; display: flex; align-items: center; }
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

/* 树节点：灰度（项目裁剪后不存在的底稿）*/
.gt-cq-tree-node { font-size: var(--gt-font-size-xs); }
.gt-cq-tree-node-disabled {
  color: var(--gt-color-text-tertiary, #b0b0b0) !important;
  text-decoration: line-through;
  font-style: italic;
  cursor: not-allowed;
}

/* 结果表格 cell_ref 列穿透跳转链接 */
.gt-cq-cell-ref-link {
  color: var(--gt-color-primary);
  cursor: pointer;
  text-decoration: underline;
  font-family: 'Consolas', 'Monaco', monospace;
}
.gt-cq-cell-ref-link:hover {
  color: var(--gt-color-primary-dark, #5a2db8);
  text-decoration: none;
  background: rgba(124, 58, 237, 0.08);
  padding: 0 4px;
  border-radius: 3px;
}

/* 右键菜单 (Req 14 AC 2) */
.gt-cq-ctx-menu {
  position: fixed;
  z-index: 9999;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-lighter, #e4e7ed);
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  padding: 4px 0;
  min-width: 140px;
}
.gt-cq-ctx-menu-item {
  padding: 6px 16px;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}
.gt-cq-ctx-menu-item:hover {
  background: var(--gt-color-primary-bg, #f5f0ff);
  color: var(--gt-color-primary, #7c3aed);
}
</style>
