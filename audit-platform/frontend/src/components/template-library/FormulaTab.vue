<!--
  FormulaTab.vue — 公式管理 Tab [template-library-coordination Sprint 3.1/3.2/3.6]

  需求 6.1-6.6, 7.1-7.6, 8.1-8.5：
  顶部嵌入 FormulaCoverageChart 仪表盘，下方 3 个子 Tab：
    1. 预填充公式（默认）— 94 映射 / 481 单元格 / 按 formula_type 分组统计
    2. 报表公式 — 按准则分 Tab，按报表类型分组，无效引用红色标记
    3. 跨底稿引用 — 全部规则只读展示

  D13 ADR：JSON 源只读
    - 预填充公式 / 跨底稿引用 / 审计报告模板 / 科目映射 4 类 JSON 资源 UI 不提供编辑入口
    - 顶部 el-alert 引导用户编辑 backend/data/<file>.json 后调用 reseed

  D8 ADR：数字列 .gt-amt class，紧凑工具栏
  D16 ADR：所有数字（条目数/覆盖率/数据量）从 API 实时取，前端不硬编码
-->
<template>
  <div class="gt-ftab">
    <!-- 顶部覆盖率仪表盘 -->
    <FormulaCoverageChart ref="coverageChartRef" />

    <!-- 子 Tab 区 -->
    <div class="gt-ftab-body">
      <el-tabs v-model="activeSubTab" class="gt-ftab-tabs">
        <!-- ─── 子 Tab 1: 预填充公式 ─────────────────────────────────── -->
        <el-tab-pane name="prefill" label="预填充公式">
          <template #label>
            <span class="gt-ftab-sub-label">
              <el-icon><Coin /></el-icon>预填充公式
              <el-tag size="small" type="info" effect="plain" round>
                <span class="gt-amt">{{ prefillTotalMappings }}</span>
              </el-tag>
            </span>
          </template>

          <!-- 只读引导横幅（D13 ADR — 通过 useTemplateLibrarySource 统一管理文案） -->
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="gt-ftab-alert"
          >
            <template #title>
              <span class="gt-ftab-alert-title">
                <el-tag type="info" size="small" effect="plain" round style="margin-right: 6px">
                  {{ readonlyBadge }}
                </el-tag>
                <el-tooltip :content="prefillReadonlyHint" placement="top">
                  <span>{{ prefillReadonlyHint }}</span>
                </el-tooltip>
              </span>
            </template>
          </el-alert>

          <!-- 公式类型分组统计 ─── -->
          <div class="gt-ftab-stats">
            <span class="gt-ftab-stats-label">公式类型分布：</span>
            <el-tag
              v-for="t in formulaTypeBadges"
              :key="t.formula_type"
              :class="`gt-ftab-type-tag gt-ftab-type--${t.formula_type.toLowerCase()}`"
              effect="light"
              size="default"
              round
            >
              {{ t.formula_type }}
              <span class="gt-amt gt-ftab-type-count">{{ t.count }}</span>
            </el-tag>
            <span class="gt-ftab-stats-summary">
              共 <span class="gt-amt">{{ prefillTotalCells }}</span> 个公式单元格 /
              <span class="gt-amt">{{ prefillTotalMappings }}</span> 个映射
            </span>
          </div>

          <!-- 工具栏 ─── -->
          <div class="gt-ftab-toolbar">
            <el-input
              v-model="prefillSearch"
              size="small"
              placeholder="搜索 wp_code / wp_name / sheet"
              clearable
              class="gt-ftab-search"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <span class="gt-ftab-spacer" />
            <span class="gt-ftab-filtered">
              展示 <span class="gt-amt">{{ filteredPrefillMappings.length }}</span> /
              <span class="gt-amt">{{ prefillTotalMappings }}</span>
            </span>
          </div>

          <!-- 主表（可展开行）─── -->
          <el-table
            v-loading="prefillLoading"
            :data="filteredPrefillMappings"
            size="small"
            row-key="wp_code"
            :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
            class="gt-ftab-table"
          >
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="gt-ftab-expand">
                  <el-table
                    :data="row.cells || []"
                    size="small"
                    :header-cell-style="{ background: '#f8f6fb', color: '#606266' }"
                  >
                    <el-table-column prop="cell_ref" label="单元格" width="160" />
                    <el-table-column prop="formula" label="公式" min-width="320">
                      <template #default="{ row: cell }">
                        <code class="gt-ftab-formula-code">{{ cell.formula }}</code>
                      </template>
                    </el-table-column>
                    <el-table-column prop="formula_type" label="类型" width="100">
                      <template #default="{ row: cell }">
                        <el-tag
                          :class="`gt-ftab-type-tag gt-ftab-type--${(cell.formula_type || '').toLowerCase()}`"
                          size="small"
                          effect="light"
                        >
                          {{ cell.formula_type }}
                        </el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column prop="description" label="说明" min-width="240" show-overflow-tooltip />
                  </el-table>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="wp_code" label="底稿编码" width="120" sortable />
            <el-table-column prop="wp_name" label="底稿名称" min-width="200" show-overflow-tooltip />
            <el-table-column prop="sheet" label="Sheet" min-width="200" show-overflow-tooltip />
            <el-table-column label="单元格数" width="100" align="right">
              <template #default="{ row }">
                <span class="gt-amt">{{ (row.cells || []).length }}</span>
              </template>
            </el-table-column>
          </el-table>

          <!-- 公式类型说明文档 ─── -->
          <div class="gt-ftab-doc">
            <h4 class="gt-ftab-doc-title">公式类型说明</h4>
            <ul class="gt-ftab-doc-list">
              <li>
                <strong>TB</strong> — 从试算平衡表取单科目数据，语法
                <code>=TB('科目编码','列名')</code>
              </li>
              <li>
                <strong>TB_SUM</strong> — 从试算平衡表取科目范围汇总，语法
                <code>=TB_SUM('起始编码~结束编码','列名')</code>
              </li>
              <li>
                <strong>ADJ</strong> — 从审计调整分录取净额，语法
                <code>=ADJ('科目编码','类型')</code>
              </li>
              <li>
                <strong>PREV</strong> — 从上年同底稿取审定数，语法
                <code>=PREV('底稿编码','工作表名','字段名')</code>
              </li>
              <li>
                <strong>WP</strong> — 从其他底稿取数据（跨底稿引用），语法
                <code>=WP('底稿编码','工作表名','字段名')</code>
              </li>
            </ul>
          </div>
        </el-tab-pane>

        <!-- ─── 子 Tab 2: 报表公式 ─────────────────────────────────── -->
        <el-tab-pane name="report" label="报表公式">
          <template #label>
            <span class="gt-ftab-sub-label">
              <el-icon><PieChart /></el-icon>报表公式
              <el-tag size="small" type="info" effect="plain" round>
                <span class="gt-amt">{{ reportRowsTotal }}</span>
              </el-tag>
            </span>
          </template>

          <!-- 准则切换（4 套） ─── -->
          <el-tabs v-model="activeStandard" class="gt-ftab-std-tabs" @tab-change="onStandardChange">
            <el-tab-pane
              v-for="std in standardTabs"
              :key="std.code"
              :name="std.code"
              :label="std.label"
            >
              <template #label>
                <span>
                  {{ std.label }}
                  <el-tag size="small" type="info" effect="plain" round style="margin-left: 4px">
                    <span class="gt-amt">{{ std.totalRows }}</span>
                  </el-tag>
                </span>
              </template>

              <div v-loading="reportLoading" class="gt-ftab-std-body">
                <el-empty
                  v-if="!reportLoading && (groupedByReportType[std.code] || []).length === 0"
                  description="该准则下暂无报表行配置"
                />
                <div
                  v-for="group in groupedByReportType[std.code] || []"
                  :key="group.report_type"
                  class="gt-ftab-rt-group"
                >
                  <!-- 报表类型标题 + 覆盖率 ─── -->
                  <div class="gt-ftab-rt-header">
                    <span class="gt-ftab-rt-title">
                      {{ formatReportType(group.report_type) }}
                    </span>
                    <span class="gt-ftab-rt-coverage">
                      覆盖率：
                      <span class="gt-amt">{{ group.rows_with_formula }}</span> /
                      <span class="gt-amt">{{ group.total_rows }}</span> =
                      <span class="gt-amt" :class="coverageColor(group.coverage_percent)">
                        {{ formatPct(group.coverage_percent) }}
                      </span>
                    </span>
                  </div>
                  <!-- 公式行表格（只展示有公式的行） ─── -->
                  <el-table
                    :data="group.rows_with_formula_list"
                    size="small"
                    :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
                    class="gt-ftab-rt-table"
                    :row-class-name="rowClassName"
                  >
                    <el-table-column prop="row_code" label="行次" width="100" />
                    <el-table-column prop="row_name" label="项目" min-width="200" show-overflow-tooltip />
                    <el-table-column prop="formula" label="公式" min-width="320">
                      <template #default="{ row }">
                        <code class="gt-ftab-formula-code">{{ row.formula }}</code>
                        <el-tooltip
                          v-if="row._invalid_refs && row._invalid_refs.length"
                          effect="dark"
                          placement="top"
                        >
                          <template #content>
                            <div>引用的 row_code 不存在：</div>
                            <div v-for="r in row._invalid_refs" :key="r" class="gt-ftab-invalid-ref">
                              {{ r }}
                            </div>
                          </template>
                          <el-tag
                            type="danger"
                            size="small"
                            effect="dark"
                            class="gt-ftab-invalid-tag"
                          >
                            ⚠ 无效引用 ×{{ row._invalid_refs.length }}
                          </el-tag>
                        </el-tooltip>
                      </template>
                    </el-table-column>
                    <el-table-column label="标记" width="100" align="center">
                      <template #default="{ row }">
                        <el-tag v-if="row.is_total_row" type="warning" size="small" effect="plain">
                          合计
                        </el-tag>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-tab-pane>

        <!-- ─── 子 Tab 3: 跨底稿引用 ─────────────────────────────── -->
        <el-tab-pane name="xref" label="跨底稿引用">
          <template #label>
            <span class="gt-ftab-sub-label">
              <el-icon><Link /></el-icon>跨底稿引用
              <el-tag size="small" type="info" effect="plain" round>
                <span class="gt-amt">{{ xrefList.length }}</span>
              </el-tag>
            </span>
          </template>

          <!-- 只读引导横幅（D13 ADR — 通过 useTemplateLibrarySource 统一管理文案） -->
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="gt-ftab-alert"
          >
            <template #title>
              <span class="gt-ftab-alert-title">
                <el-tag type="info" size="small" effect="plain" round style="margin-right: 6px">
                  {{ readonlyBadge }}
                </el-tag>
                <el-tooltip :content="xrefReadonlyHint" placement="top">
                  <span>{{ xrefReadonlyHint }}</span>
                </el-tooltip>
              </span>
            </template>
          </el-alert>

          <!-- 工具栏 ─── -->
          <div class="gt-ftab-toolbar">
            <el-input
              v-model="xrefSearch"
              size="small"
              placeholder="搜索 source / target / 描述"
              clearable
              class="gt-ftab-search"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-select
              v-model="xrefCategoryFilter"
              size="small"
              placeholder="分类"
              clearable
              class="gt-ftab-select"
            >
              <el-option label="全部" value="" />
              <el-option
                v-for="cat in xrefCategoryOptions"
                :key="cat"
                :label="cat"
                :value="cat"
              />
            </el-select>
            <span class="gt-ftab-spacer" />
            <span class="gt-ftab-filtered">
              展示 <span class="gt-amt">{{ filteredXrefRows.length }}</span> /
              <span class="gt-amt">{{ xrefRows.length }}</span>
            </span>
          </div>

          <el-table
            v-loading="xrefLoading"
            :data="filteredXrefRows"
            size="small"
            :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
            class="gt-ftab-table"
          >
            <el-table-column prop="source_wp_code" label="来源底稿" width="120" sortable />
            <el-table-column prop="target_wp_code" label="目标底稿" width="120" sortable />
            <el-table-column prop="reference_type" label="引用类型" width="120">
              <template #default="{ row }">
                <el-tag size="small" type="info" effect="plain">
                  {{ row.reference_type }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="严重程度" width="120">
              <template #default="{ row }">
                <el-tag
                  v-if="row.severity"
                  :type="severityType(row.severity)"
                  size="small"
                  effect="plain"
                >
                  {{ row.severity }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="280" show-overflow-tooltip />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Coin, PieChart, Link, Search } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import {
  templateLibraryMgmt as P_tlm,
  reportConfig as P_rc,
} from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { useTemplateLibrarySource } from '@/composables/useTemplateLibrarySource'
import FormulaCoverageChart from '@/components/template-library/FormulaCoverageChart.vue'

// ─── D13 ADR：只读源统一文案管理 ───
const { getReadonlyHint, getReadonlyBadgeText } = useTemplateLibrarySource()
const prefillReadonlyHint = getReadonlyHint('prefill_formula_mapping')
const xrefReadonlyHint = getReadonlyHint('cross_wp_references')
const readonlyBadge = getReadonlyBadgeText()

// ─── State: 顶部覆盖率（用于子 Tab 内的统计） ───
const coverageChartRef = ref<InstanceType<typeof FormulaCoverageChart> | null>(null)

const activeSubTab = ref<'prefill' | 'report' | 'xref'>('prefill')

// ─── 1. 预填充公式 ─────────────────────────────────────────────────────────
interface PrefillCell {
  cell_ref: string
  formula: string
  formula_type: string
  description?: string
}

interface PrefillMapping {
  wp_code: string
  wp_name: string
  sheet: string
  account_codes?: string[]
  cells?: PrefillCell[]
}

const prefillLoading = ref(false)
const prefillMappings = ref<PrefillMapping[]>([])
const prefillTotalMappings = ref(0)
const prefillTotalCells = ref(0)
const prefillSearch = ref('')

const filteredPrefillMappings = computed<PrefillMapping[]>(() => {
  const q = prefillSearch.value.trim().toLowerCase()
  if (!q) return prefillMappings.value
  return prefillMappings.value.filter(m => {
    const code = (m.wp_code || '').toLowerCase()
    const name = (m.wp_name || '').toLowerCase()
    const sheet = (m.sheet || '').toLowerCase()
    return code.includes(q) || name.includes(q) || sheet.includes(q)
  })
})

// 公式类型分组统计（从覆盖率响应取，避免重复加载）
interface FormulaTypeCount {
  formula_type: string
  count: number
}
const formulaTypeBadges = ref<FormulaTypeCount[]>([])

async function loadPrefillFormulas() {
  prefillLoading.value = true
  try {
    const data = await api.get(P_tlm.prefillFormulas)
    prefillMappings.value = (data?.mappings || []) as PrefillMapping[]
    prefillTotalMappings.value = Number(data?.total_mappings ?? prefillMappings.value.length)
    prefillTotalCells.value = Number(data?.total_cells ?? 0)
  } catch (e: any) {
    handleApiError(e, '加载预填充公式')
    prefillMappings.value = []
    prefillTotalMappings.value = 0
    prefillTotalCells.value = 0
  } finally {
    prefillLoading.value = false
  }
}

async function loadFormulaTypeDistribution() {
  try {
    const data = await api.get(P_tlm.formulaCoverage)
    formulaTypeBadges.value = (data?.formula_type_distribution || []) as FormulaTypeCount[]
  } catch {
    formulaTypeBadges.value = []
  }
}

// ─── 2. 报表公式 ───────────────────────────────────────────────────────────
interface ReportConfigRow {
  id?: string
  applicable_standard: string
  report_type: string
  row_code: string
  row_name: string
  formula?: string | null
  is_total_row?: boolean
  sort_order?: number
  _invalid_refs?: string[]
}

interface ReportTypeGroup {
  report_type: string
  total_rows: number
  rows_with_formula: number
  coverage_percent: number
  rows_with_formula_list: ReportConfigRow[]
}

const reportLoading = ref(false)
const reportRowsByStandard = ref<Record<string, ReportConfigRow[]>>({})
const standardTabs = ref<Array<{ code: string; label: string; totalRows: number }>>([])
const activeStandard = ref<string>('soe_standalone')

const STANDARD_LABEL_MAP: Record<string, string> = {
  soe_consolidated: '国企-合并',
  soe_standalone: '国企-单体',
  listed_consolidated: '上市-合并',
  listed_standalone: '上市-单体',
  enterprise: '一般企业',
}

const REPORT_TYPE_LABELS: Record<string, string> = {
  balance_sheet: '资产负债表 (BS)',
  income_statement: '利润表 (IS)',
  cash_flow_statement: '现金流量表 (CFS)',
  cash_flow_supplement: '现金流量附表',
  equity_changes: '所有者权益变动表 (EQ)',
}

function formatReportType(code: string): string {
  return REPORT_TYPE_LABELS[code] || code
}

const reportRowsTotal = computed(() => {
  return Object.values(reportRowsByStandard.value).reduce(
    (s, arr) => s + arr.length,
    0,
  )
})

const groupedByReportType = computed<Record<string, ReportTypeGroup[]>>(() => {
  const result: Record<string, ReportTypeGroup[]> = {}
  for (const [stdCode, rows] of Object.entries(reportRowsByStandard.value)) {
    const groups = new Map<string, ReportTypeGroup>()
    for (const r of rows) {
      const rt = r.report_type || 'unknown'
      if (!groups.has(rt)) {
        groups.set(rt, {
          report_type: rt,
          total_rows: 0,
          rows_with_formula: 0,
          coverage_percent: 0,
          rows_with_formula_list: [],
        })
      }
      const g = groups.get(rt)!
      g.total_rows++
      if (r.formula && r.formula.trim()) {
        g.rows_with_formula++
        g.rows_with_formula_list.push(r)
      }
    }
    // 计算覆盖率
    const arr: ReportTypeGroup[] = []
    for (const g of groups.values()) {
      g.coverage_percent =
        g.total_rows > 0
          ? Math.round((g.rows_with_formula / g.total_rows) * 1000) / 10
          : 0
      // 按 row_code 排序
      g.rows_with_formula_list.sort((a, b) =>
        (a.row_code || '').localeCompare(b.row_code || ''),
      )
      arr.push(g)
    }
    // 按报表类型字典序
    arr.sort((a, b) => a.report_type.localeCompare(b.report_type))
    result[stdCode] = arr
  }
  return result
})

async function loadReportConfigForStandard(stdCode: string) {
  if (reportRowsByStandard.value[stdCode]) return  // 已加载
  reportLoading.value = true
  try {
    const data = await api.get(`${P_rc.list}?applicable_standard=${encodeURIComponent(stdCode)}`)
    const rows = (Array.isArray(data) ? data : (data?.items || [])) as ReportConfigRow[]
    // 标记无效引用
    const validRowCodes = new Set(rows.map(r => r.row_code).filter(Boolean))
    for (const r of rows) {
      r._invalid_refs = findInvalidRefs(r.formula || '', validRowCodes)
    }
    reportRowsByStandard.value[stdCode] = rows
  } catch (e: any) {
    handleApiError(e, `加载 ${STANDARD_LABEL_MAP[stdCode] || stdCode} 报表配置`)
    reportRowsByStandard.value[stdCode] = []
  } finally {
    reportLoading.value = false
  }
}

async function loadAllStandards() {
  // 4 个准则并行加载
  const codes = ['soe_consolidated', 'soe_standalone', 'listed_consolidated', 'listed_standalone']
  await Promise.all(codes.map(loadReportConfigForStandard))
  // 构造 Tab 元数据
  standardTabs.value = codes.map(code => ({
    code,
    label: STANDARD_LABEL_MAP[code] || code,
    totalRows: (reportRowsByStandard.value[code] || []).length,
  }))
}

function onStandardChange(_: string | number) {
  // 当前已全部预加载，无需懒加载；保留 hook 便于未来切换为 lazy 模式
}

// 查找公式中引用的 ROW('xxx') 在 row_codes 集合中不存在的（Property 15 + 需求 7.6）
function findInvalidRefs(formula: string, validRowCodes: Set<string>): string[] {
  if (!formula) return []
  const invalid: string[] = []
  const re = /ROW\(['"]([^'"]+)['"]\)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(formula)) !== null) {
    const ref = m[1]
    if (ref && !validRowCodes.has(ref)) {
      invalid.push(ref)
    }
  }
  // 同样检查 SUM_ROW('a','b') —— 起止两个 row_code
  const sumRe = /SUM_ROW\(['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]\)/g
  while ((m = sumRe.exec(formula)) !== null) {
    const a = m[1]
    const b = m[2]
    if (a && !validRowCodes.has(a)) invalid.push(a)
    if (b && !validRowCodes.has(b)) invalid.push(b)
  }
  return Array.from(new Set(invalid))
}

function rowClassName({ row }: { row: ReportConfigRow }): string {
  return row._invalid_refs && row._invalid_refs.length > 0 ? 'gt-ftab-row-invalid' : ''
}

function coverageColor(pct: number | string | null | undefined): string {
  const v = Number(pct ?? 0)
  if (v >= 80) return 'gt-fcc-c--green'
  if (v >= 40) return 'gt-fcc-c--yellow'
  return 'gt-fcc-c--red'
}

function formatPct(pct: number | string | null | undefined): string {
  const v = Number(pct ?? 0)
  if (Number.isNaN(v)) return '—'
  return `${v.toFixed(1)}%`
}

// ─── 3. 跨底稿引用 ───────────────────────────────────────────────────────
interface XrefRefRaw {
  ref_id?: string
  source_wp?: string
  source_sheet?: string
  source_cell?: string
  targets?: Array<{ wp_code: string; sheet?: string; cell?: string; formula?: string }>
  category?: string
  severity?: string
  description?: string
  // 后端可能直接返回扁平字段
  source_wp_code?: string
  target_wp_code?: string
  reference_type?: string
}

interface XrefRow {
  source_wp_code: string
  target_wp_code: string
  reference_type: string
  severity?: string
  category?: string
  description?: string
}

const xrefLoading = ref(false)
const xrefList = ref<XrefRefRaw[]>([])
const xrefSearch = ref('')
const xrefCategoryFilter = ref('')

// 把后端嵌套结构（一个 source 对应多个 targets）展平为表格行
const xrefRows = computed<XrefRow[]>(() => {
  const rows: XrefRow[] = []
  for (const r of xrefList.value) {
    const sourceCode = r.source_wp_code || r.source_wp || ''
    const refType = r.reference_type || r.category || 'reference'
    const targets = r.targets || []
    if (targets.length === 0) {
      // 后端可能已扁平化（含 target_wp_code 单字段）
      if (r.target_wp_code) {
        rows.push({
          source_wp_code: sourceCode,
          target_wp_code: r.target_wp_code,
          reference_type: refType,
          severity: r.severity,
          category: r.category,
          description: r.description,
        })
      }
    } else {
      for (const t of targets) {
        rows.push({
          source_wp_code: sourceCode,
          target_wp_code: t.wp_code,
          reference_type: refType,
          severity: r.severity,
          category: r.category,
          description: r.description,
        })
      }
    }
  }
  return rows
})

const xrefCategoryOptions = computed<string[]>(() => {
  const set = new Set<string>()
  for (const r of xrefRows.value) {
    if (r.category) set.add(r.category)
  }
  return Array.from(set).sort()
})

const filteredXrefRows = computed<XrefRow[]>(() => {
  const q = xrefSearch.value.trim().toLowerCase()
  const cat = xrefCategoryFilter.value
  return xrefRows.value.filter(r => {
    if (cat && r.category !== cat) return false
    if (q) {
      const s = (r.source_wp_code || '').toLowerCase()
      const t = (r.target_wp_code || '').toLowerCase()
      const d = (r.description || '').toLowerCase()
      if (!s.includes(q) && !t.includes(q) && !d.includes(q)) return false
    }
    return true
  })
})

function severityType(severity?: string): 'success' | 'info' | 'warning' | 'danger' {
  switch ((severity || '').toLowerCase()) {
    case 'blocking': return 'danger'
    case 'warning': return 'warning'
    case 'info': return 'info'
    default: return 'info'
  }
}

async function loadCrossWpReferences() {
  xrefLoading.value = true
  try {
    const data = await api.get(P_tlm.crossWpReferences)
    xrefList.value = (data?.references || []) as XrefRefRaw[]
  } catch (e: any) {
    handleApiError(e, '加载跨底稿引用规则')
    xrefList.value = []
  } finally {
    xrefLoading.value = false
  }
}

// ─── 懒加载策略：当 sub-tab 激活时才拉数据 ───
watch(activeSubTab, async (val) => {
  if (val === 'prefill' && prefillMappings.value.length === 0) {
    await loadPrefillFormulas()
  } else if (val === 'report' && Object.keys(reportRowsByStandard.value).length === 0) {
    await loadAllStandards()
  } else if (val === 'xref' && xrefList.value.length === 0) {
    await loadCrossWpReferences()
  }
}, { immediate: false })

onMounted(async () => {
  // 默认子 Tab 是 prefill，立即加载它 + 类型分布
  await Promise.all([
    loadPrefillFormulas(),
    loadFormulaTypeDistribution(),
  ])
})
</script>

<style scoped>
.gt-ftab {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  min-height: 0;
}

/* ─── 子 Tab 区 ─── */
.gt-ftab-body {
  background: var(--gt-color-bg-white);
  border-radius: 8px;
  border: 1px solid #ebeef5;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
}
.gt-ftab-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  width: 100%;
}
.gt-ftab-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 12px;
  background: var(--gt-color-bg);
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
}
.gt-ftab-tabs :deep(.el-tabs__nav) {
  border: none !important;
}
.gt-ftab-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: auto;
  padding: 12px 16px;
}
.gt-ftab-sub-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
}

/* ─── 提示横幅 ─── */
.gt-ftab-alert {
  margin-bottom: 12px;
}
.gt-ftab-alert-title code {
  background: rgba(75, 45, 119, 0.08);
  color: var(--gt-color-primary);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: var(--gt-font-size-xs);
}

/* ─── 顶部统计 ─── */
.gt-ftab-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--gt-color-primary-bg);
  border-radius: 6px;
  border-left: 3px solid #4b2d77;
}
.gt-ftab-stats-label {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
  font-weight: 500;
  margin-right: 4px;
}
.gt-ftab-stats-summary {
  margin-left: auto;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-ftab-type-tag {
  border: 1px solid transparent;
}
.gt-ftab-type-count {
  margin-left: 4px;
  font-weight: 700;
}
.gt-ftab-type--tb { background: var(--gt-bg-info); color: var(--gt-color-teal); border-color: #b3d9f0; }
.gt-ftab-type--tb_sum { background: var(--gt-bg-info); color: var(--gt-color-teal); border-color: #98c8eb; }
.gt-ftab-type--adj { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); border-color: #f0c898; }
.gt-ftab-type--prev { background: var(--gt-color-success-light); color: var(--gt-color-success); border-color: #b8d8b8; }
.gt-ftab-type--wp { background: var(--gt-color-primary-bg); color: var(--gt-color-primary-light); border-color: #d4bff0; }

/* ─── 工具栏 ─── */
.gt-ftab-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.gt-ftab-search { width: 280px; }
.gt-ftab-select { width: 160px; }
.gt-ftab-spacer { flex: 1; }
.gt-ftab-filtered {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
  white-space: nowrap;
}

.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  white-space: nowrap;
}

/* ─── 表格 ─── */
.gt-ftab-table :deep(.el-table__row:hover > td) {
  background-color: var(--gt-color-primary-bg) !important;
}
.gt-ftab-table :deep(.el-table__row.gt-ftab-row-invalid > td) {
  background-color: var(--gt-bg-danger) !important;
  border-left: 3px solid #f56c6c;
}

.gt-ftab-expand {
  padding: 8px 24px 8px 32px;
  background: var(--gt-color-bg);
}

.gt-ftab-formula-code {
  display: inline-block;
  padding: 2px 8px;
  background: var(--gt-color-bg);
  border: 1px solid #e0e0e0;
  border-radius: 3px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-primary);
}

.gt-ftab-invalid-tag {
  margin-left: 8px;
}

.gt-ftab-invalid-ref {
  font-family: 'Consolas', monospace;
  margin: 2px 0;
}

/* ─── 报表公式分组样式 ─── */
.gt-ftab-std-tabs :deep(.el-tabs__header) {
  margin-bottom: 8px;
  background: transparent;
  border-bottom: 1px solid #ebeef5;
}
.gt-ftab-std-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.gt-ftab-rt-group {
  background: var(--gt-color-bg);
  border-radius: 6px;
  padding: 12px;
}
.gt-ftab-rt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding: 0 4px;
}
.gt-ftab-rt-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
}
.gt-ftab-rt-coverage {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-fcc-c--green { color: var(--gt-color-success); }
.gt-fcc-c--yellow { color: var(--gt-color-wheat); }
.gt-fcc-c--red { color: var(--gt-color-coral); }

.gt-ftab-rt-table {
  border-radius: 4px;
  overflow: hidden;
}

/* ─── 文档说明 ─── */
.gt-ftab-doc {
  margin-top: 16px;
  padding: 12px 16px;
  background: var(--gt-color-primary-bg);
  border-left: 3px solid #4b2d77;
  border-radius: 4px;
}
.gt-ftab-doc-title {
  margin: 0 0 8px 0;
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
}
.gt-ftab-doc-list {
  margin: 0;
  padding-left: 20px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
  line-height: 1.8;
}
.gt-ftab-doc-list code {
  background: rgba(75, 45, 119, 0.08);
  color: var(--gt-color-primary);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: var(--gt-font-size-xs);
}
</style>
