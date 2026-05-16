<!--
  ReportConfigTab.vue — 报表配置 Tab [template-library-coordination Sprint 4.4]

  需求 12.1-12.7：
  - el-tabs 按 applicable_standard 分 4 Tab（soe_consolidated/soe_standalone/listed_consolidated/listed_standalone）
  - 每 Tab 内按 report_type 分组（balance_sheet/income_statement/cash_flow_statement/equity_changes/...）
  - 列：row_code/row_name/indent_level/is_total_row/formula/sort_order/formula_category
  - indent_level 可视化（每级 24px padding-left）
  - 有公式行蓝色标记，合计行加粗+上边框
  - 顶部统计：总行数/有公式行数/合计行数（动态查询，不硬编码）
  - admin/partner 显示"编辑公式"按钮（占位，待 Sprint 5 落地）

  数据源：GET /api/report-config?applicable_standard={std}
  D7 ADR：report_config 是 DB-table editable，admin/partner 可编辑（公式/取数源等）
  D8 ADR：数字列 .gt-amt class
  D16 ADR：所有数字（行数/百分比）从 API 实时取
-->
<template>
  <div class="gt-rct">
    <!-- 顶部统计（当前选中 Tab 的） -->
    <div class="gt-rct-stats">
      <span class="gt-rct-stats-item">
        当前准则：<strong>{{ standardLabel(activeStandard) }}</strong>
      </span>
      <span class="gt-rct-stats-item">
        总行数：<span class="gt-amt">{{ stats.totalRows }}</span>
      </span>
      <span class="gt-rct-stats-item">
        有公式：<span class="gt-amt gt-rct-stats-formula">{{ stats.formulaRows }}</span>
        <span class="gt-rct-stats-pct">（{{ stats.formulaPct }}%）</span>
      </span>
      <span class="gt-rct-stats-item">
        合计行：<span class="gt-amt gt-rct-stats-total">{{ stats.totalRowCount }}</span>
      </span>
      <span class="gt-rct-stats-item">
        无效引用：
        <span class="gt-amt" :class="stats.invalidRefRows > 0 ? 'gt-rct-stats-warn' : ''">
          {{ stats.invalidRefRows }}
        </span>
      </span>
    </div>

    <!-- 准则切换 Tab -->
    <el-tabs
      v-model="activeStandard"
      class="gt-rct-tabs"
      type="border-card"
      @tab-change="onStandardChange"
    >
      <el-tab-pane
        v-for="std in standardTabs"
        :key="std.code"
        :name="std.code"
      >
        <template #label>
          <span class="gt-rct-tab-label">
            {{ std.label }}
            <el-tag
              v-if="standardCounts[std.code] !== undefined"
              size="small"
              type="info"
              effect="plain"
              round
              style="margin-left: 4px"
            >
              <span class="gt-amt">{{ standardCounts[std.code] }}</span>
            </el-tag>
          </span>
        </template>

        <div v-loading="loading" class="gt-rct-pane">
          <div class="gt-rct-pane-toolbar">
            <el-input
              v-model="searchInput"
              size="small"
              placeholder="搜索 row_code / row_name / formula"
              clearable
              class="gt-rct-search"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-checkbox v-model="onlyWithFormula" size="small">仅显示有公式</el-checkbox>
            <el-checkbox v-model="onlyTotalRows" size="small">仅显示合计行</el-checkbox>
            <span class="gt-rct-spacer" />
            <span class="gt-rct-filtered">
              展示 <span class="gt-amt">{{ filteredCount }}</span> /
              <span class="gt-amt">{{ stats.totalRows }}</span>
            </span>
          </div>

          <el-empty
            v-if="!loading && (groupedByReportType[activeStandard] || []).length === 0"
            description="该准则下暂无报表配置数据"
          />
          <div
            v-for="g in (groupedByReportType[activeStandard] || [])"
            :key="g.report_type"
            class="gt-rct-group"
          >
            <!-- 报表类型分组头 -->
            <div class="gt-rct-group-header">
              <span class="gt-rct-group-title">{{ reportTypeLabel(g.report_type) }}</span>
              <span class="gt-rct-group-stats">
                共 <span class="gt-amt">{{ g.total_rows }}</span> 行 /
                有公式 <span class="gt-amt">{{ g.formula_rows }}</span> /
                合计 <span class="gt-amt">{{ g.total_row_count }}</span>
              </span>
            </div>

            <el-table
              :data="g.rows"
              size="small"
              :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
              :row-class-name="rowClassName"
              class="gt-rct-table"
              row-key="id"
            >
              <el-table-column prop="row_code" label="行次编码" width="90">
                <template #default="{ row }">
                  <span class="gt-amt gt-rct-row-code">{{ row.row_code }}</span>
                </template>
              </el-table-column>

              <el-table-column label="项目" min-width="280" show-overflow-tooltip>
                <template #default="{ row }">
                  <span
                    class="gt-rct-row-name"
                    :class="{ 'gt-rct-row-name--total': row.is_total_row }"
                    :style="{ paddingLeft: `${(row.indent_level || 0) * 24}px` }"
                  >
                    <span v-if="row.is_total_row" class="gt-rct-total-mark">∑</span>
                    {{ row.row_name }}
                  </span>
                </template>
              </el-table-column>

              <el-table-column label="缩进" width="60" align="center">
                <template #default="{ row }">
                  <span class="gt-amt gt-rct-em">{{ row.indent_level ?? 0 }}</span>
                </template>
              </el-table-column>

              <el-table-column label="合计" width="60" align="center">
                <template #default="{ row }">
                  <el-icon v-if="row.is_total_row" color="#e6a23c"><Check /></el-icon>
                  <span v-else class="gt-rct-em">—</span>
                </template>
              </el-table-column>

              <el-table-column label="公式" min-width="280">
                <template #default="{ row }">
                  <code v-if="row.formula" class="gt-rct-formula">{{ row.formula }}</code>
                  <span v-else class="gt-rct-em">—</span>
                  <el-tooltip
                    v-if="row._invalid_refs && row._invalid_refs.length"
                    effect="dark"
                    placement="top"
                  >
                    <template #content>
                      <div>引用的 row_code 不存在：</div>
                      <div v-for="r in row._invalid_refs" :key="r" class="gt-rct-invalid-ref">
                        {{ r }}
                      </div>
                    </template>
                    <el-tag
                      type="danger"
                      size="small"
                      effect="dark"
                      class="gt-rct-invalid-tag"
                    >
                      ⚠ ×{{ row._invalid_refs.length }}
                    </el-tag>
                  </el-tooltip>
                </template>
              </el-table-column>

              <el-table-column prop="formula_category" label="类别" width="100">
                <template #default="{ row }">
                  <el-tag
                    v-if="row.formula_category"
                    size="small"
                    :class="`gt-rct-cat--${row.formula_category}`"
                    effect="plain"
                  >
                    {{ formulaCatLabel(row.formula_category) }}
                  </el-tag>
                  <span v-else class="gt-rct-em">—</span>
                </template>
              </el-table-column>

              <el-table-column prop="sort_order" label="排序" width="70" align="right">
                <template #default="{ row }">
                  <span class="gt-amt gt-rct-em">{{ row.row_number ?? row.sort_order ?? '—' }}</span>
                </template>
              </el-table-column>

              <el-table-column v-if="canEdit" label="操作" width="100" align="center" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" link type="primary" @click="onEditFormula(row)">
                    编辑公式
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 编辑公式占位对话框（Sprint 5 完整实装） -->
    <el-dialog
      v-model="editFormulaVisible"
      title="编辑公式"
      width="640px"
      destroy-on-close
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="完整公式编辑器待 Sprint 5 落地"
        description="当前为占位入口，可使用 公式管理 Tab 查看现有公式或通过 API 直接修改。"
        style="margin-bottom: 12px"
      />
      <div v-if="editingRow" class="gt-rct-edit-info">
        <div><strong>行次编码：</strong>{{ editingRow.row_code }}</div>
        <div><strong>项目：</strong>{{ editingRow.row_name }}</div>
        <div><strong>当前公式：</strong>
          <code class="gt-rct-formula">{{ editingRow.formula || '（空）' }}</code>
        </div>
      </div>
      <template #footer>
        <el-button @click="editFormulaVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Search, Check } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { reportConfig as P_rc } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { useAuthStore } from '@/stores/auth'

interface ReportConfigRow {
  id?: string
  applicable_standard: string
  report_type: string
  row_number?: number
  row_code: string
  row_name: string
  indent_level?: number
  formula?: string | null
  formula_category?: string | null
  formula_description?: string | null
  formula_source?: string | null
  is_total_row?: boolean
  parent_row_code?: string | null
  sort_order?: number | null
  _invalid_refs?: string[]
}

// ─── 标准 Tabs（4 套） ───────────────────────────────────────────────────
const standardTabs = [
  { code: 'soe_consolidated', label: '国企-合并' },
  { code: 'soe_standalone', label: '国企-单体' },
  { code: 'listed_consolidated', label: '上市-合并' },
  { code: 'listed_standalone', label: '上市-单体' },
] as const

function standardLabel(code: string): string {
  return standardTabs.find(s => s.code === code)?.label || code
}

const REPORT_TYPE_LABELS: Record<string, string> = {
  balance_sheet: '资产负债表 (BS)',
  income_statement: '利润表 (IS)',
  cash_flow_statement: '现金流量表 (CFS)',
  cash_flow_supplement: '现金流量附表',
  equity_changes: '所有者权益变动表 (EQ)',
}
function reportTypeLabel(code: string): string {
  return REPORT_TYPE_LABELS[code] || code
}

const FORMULA_CAT_LABELS: Record<string, string> = {
  auto_calc: '自动运算',
  logic_check: '逻辑审核',
  reasonability: '合理性',
}
function formulaCatLabel(code: string): string {
  return FORMULA_CAT_LABELS[code] || code
}

// ─── State ────────────────────────────────────────────────────────────────
const loading = ref(false)
const activeStandard = ref<string>('soe_standalone')
const rowsByStandard = ref<Record<string, ReportConfigRow[]>>({})
const standardCounts = ref<Record<string, number>>({})

const searchInput = ref('')
const searchText = ref('')
let searchDebouncer: ReturnType<typeof setTimeout> | null = null
watch(searchInput, (v) => {
  if (searchDebouncer) clearTimeout(searchDebouncer)
  searchDebouncer = setTimeout(() => { searchText.value = (v || '').trim() }, 250)
})
const onlyWithFormula = ref(false)
const onlyTotalRows = ref(false)

const editFormulaVisible = ref(false)
const editingRow = ref<ReportConfigRow | null>(null)

const authStore = useAuthStore()
const canEdit = computed(() => {
  const role = authStore.user?.role || ''
  return role === 'admin' || role === 'partner'
})

// ─── 数据加载 ─────────────────────────────────────────────────────────────
async function loadStandard(stdCode: string) {
  if (rowsByStandard.value[stdCode]) return  // 已加载
  loading.value = true
  try {
    const data = await api.get(`${P_rc.list}?applicable_standard=${encodeURIComponent(stdCode)}`)
    const rows = (Array.isArray(data) ? data : (data?.items || [])) as ReportConfigRow[]
    // 标记无效引用（同 FormulaTab.vue 逻辑）
    const validRowCodes = new Set(
      rows.map(r => r.row_code).filter((c): c is string => !!c),
    )
    for (const r of rows) {
      r._invalid_refs = findInvalidRefs(r.formula || '', validRowCodes)
    }
    rowsByStandard.value[stdCode] = rows
    standardCounts.value[stdCode] = rows.length
  } catch (e: any) {
    handleApiError(e, `加载 ${standardLabel(stdCode)} 报表配置`)
    rowsByStandard.value[stdCode] = []
    standardCounts.value[stdCode] = 0
  } finally {
    loading.value = false
  }
}

function onStandardChange(_: string | number) {
  loadStandard(activeStandard.value)
}

onMounted(async () => {
  await loadStandard(activeStandard.value)
  // 后台预加载其他 Tab 的计数（不阻塞 UI）
  for (const std of standardTabs) {
    if (std.code !== activeStandard.value) {
      // 仅获取条数，避免大量数据一次性加载
      api.get(`${P_rc.list}?applicable_standard=${encodeURIComponent(std.code)}`)
        .then(data => {
          const rows = (Array.isArray(data) ? data : (data?.items || [])) as ReportConfigRow[]
          standardCounts.value[std.code] = rows.length
          // 顺便缓存（用户切换时无需重新加载）
          const validRowCodes = new Set(
            rows.map(r => r.row_code).filter((c): c is string => !!c),
          )
          for (const r of rows) {
            r._invalid_refs = findInvalidRefs(r.formula || '', validRowCodes)
          }
          rowsByStandard.value[std.code] = rows
        })
        .catch(() => { /* 静默 */ })
    }
  }
})

// ─── 计算属性 ─────────────────────────────────────────────────────────────
function findInvalidRefs(formula: string, validRowCodes: Set<string>): string[] {
  if (!formula) return []
  const invalid: string[] = []
  const re = /ROW\(['"]([^'"]+)['"]\)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(formula)) !== null) {
    const ref = m[1]
    if (ref && !validRowCodes.has(ref)) invalid.push(ref)
  }
  const sumRe = /SUM_ROW\(['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]\)/g
  while ((m = sumRe.exec(formula)) !== null) {
    if (m[1] && !validRowCodes.has(m[1])) invalid.push(m[1])
    if (m[2] && !validRowCodes.has(m[2])) invalid.push(m[2])
  }
  return Array.from(new Set(invalid))
}

const currentRows = computed<ReportConfigRow[]>(() =>
  rowsByStandard.value[activeStandard.value] || [],
)

const filteredRows = computed<ReportConfigRow[]>(() => {
  const q = searchText.value.toLowerCase()
  return currentRows.value.filter(r => {
    if (onlyWithFormula.value && (!r.formula || !r.formula.trim())) return false
    if (onlyTotalRows.value && !r.is_total_row) return false
    if (q) {
      const hay = [r.row_code, r.row_name, r.formula || ''].join(' ').toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

const filteredCount = computed(() => filteredRows.value.length)

const stats = computed(() => {
  const all = currentRows.value
  const total = all.length
  const withFormula = all.filter(r => r.formula && r.formula.trim()).length
  const totalRowCount = all.filter(r => r.is_total_row).length
  const invalid = all.filter(r => (r._invalid_refs?.length || 0) > 0).length
  return {
    totalRows: total,
    formulaRows: withFormula,
    formulaPct: total > 0 ? Math.round((withFormula / total) * 1000) / 10 : 0,
    totalRowCount,
    invalidRefRows: invalid,
  }
})

interface ReportTypeGroup {
  report_type: string
  total_rows: number
  formula_rows: number
  total_row_count: number
  rows: ReportConfigRow[]
}

const groupedByReportType = computed<Record<string, ReportTypeGroup[]>>(() => {
  const result: Record<string, ReportTypeGroup[]> = {}
  for (const std of standardTabs) {
    const stdCode = std.code
    const rows = stdCode === activeStandard.value
      ? filteredRows.value
      : (rowsByStandard.value[stdCode] || [])
    const groups = new Map<string, ReportTypeGroup>()
    for (const r of rows) {
      const rt = r.report_type || 'unknown'
      if (!groups.has(rt)) {
        groups.set(rt, {
          report_type: rt,
          total_rows: 0,
          formula_rows: 0,
          total_row_count: 0,
          rows: [],
        })
      }
      const g = groups.get(rt)!
      g.total_rows++
      if (r.formula && r.formula.trim()) g.formula_rows++
      if (r.is_total_row) g.total_row_count++
      g.rows.push(r)
    }
    // 每组按 row_number 升序，缺失则按 row_code 字典序
    const arr: ReportTypeGroup[] = []
    for (const g of groups.values()) {
      g.rows.sort((a, b) => {
        const an = a.row_number ?? null
        const bn = b.row_number ?? null
        if (an !== null && bn !== null) return an - bn
        return (a.row_code || '').localeCompare(b.row_code || '')
      })
      arr.push(g)
    }
    arr.sort((a, b) => a.report_type.localeCompare(b.report_type))
    result[stdCode] = arr
  }
  return result
})

function rowClassName({ row }: { row: ReportConfigRow }): string {
  const classes: string[] = []
  if (row.is_total_row) classes.push('gt-rct-row--total')
  if (row.formula && row.formula.trim()) classes.push('gt-rct-row--has-formula')
  if (row._invalid_refs && row._invalid_refs.length > 0) classes.push('gt-rct-row--invalid')
  return classes.join(' ')
}

function onEditFormula(row: ReportConfigRow) {
  editingRow.value = row
  editFormulaVisible.value = true
}
</script>

<style scoped>
.gt-rct {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

/* ─── 顶部统计 ─── */
.gt-rct-stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 8px 12px;
  background: var(--gt-color-primary-bg);
  border-radius: 6px;
  border-left: 3px solid var(--gt-color-primary);
  flex-shrink: 0;
}
.gt-rct-stats-item {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-rct-stats-pct {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}
.gt-rct-stats-formula { color: var(--gt-color-teal); }
.gt-rct-stats-total { color: var(--gt-color-wheat); }
.gt-rct-stats-warn { color: var(--gt-color-coral); }

.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  white-space: nowrap;
}

/* ─── Tabs ─── */
.gt-rct-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.gt-rct-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: auto;
  padding: 12px 16px;
}
.gt-rct-tab-label {
  display: inline-flex;
  align-items: center;
  font-size: var(--gt-font-size-sm);
}

/* ─── Pane ─── */
.gt-rct-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gt-rct-pane-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.gt-rct-search { width: 280px; }
.gt-rct-spacer { flex: 1; min-width: 8px; }
.gt-rct-filtered {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}

/* ─── 分组 ─── */
.gt-rct-group {
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 8px;
  overflow: hidden;
}
.gt-rct-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: var(--gt-color-primary-bg);
  border-bottom: 1px solid var(--gt-color-border-lighter);
  border-left: 3px solid var(--gt-color-primary);
}
.gt-rct-group-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 700;
  color: var(--gt-color-text-primary);
}
.gt-rct-group-stats {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}

/* ─── 表格 ─── */
.gt-rct-table :deep(.el-table__row:hover > td) {
  background-color: rgba(75, 45, 119, 0.06) !important;
}
/* 合计行：加粗 + 上边框 */
.gt-rct-table :deep(.el-table__row.gt-rct-row--total > td) {
  font-weight: 700 !important;
  border-top: 2px solid var(--gt-color-primary) !important;
  background-color: var(--gt-color-primary-bg) !important;
}
/* 有公式行：浅蓝背景 */
.gt-rct-table :deep(.el-table__row.gt-rct-row--has-formula > td) {
  background-color: rgba(64, 158, 255, 0.04) !important;
}
.gt-rct-table :deep(.el-table__row.gt-rct-row--total.gt-rct-row--has-formula > td) {
  background-color: var(--gt-color-primary-bg) !important;
}
/* 无效引用行：浅红 */
.gt-rct-table :deep(.el-table__row.gt-rct-row--invalid > td) {
  background-color: var(--gt-bg-danger) !important;
  border-left: 3px solid var(--gt-color-coral);
}

/* row_code monospace */
.gt-rct-row-code {
  display: inline-block;
  font-family: 'Consolas', 'Courier New', monospace;
  background: var(--gt-color-bg);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-primary);
}

.gt-rct-row-name {
  display: inline-block;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary);
}
.gt-rct-row-name--total {
  font-weight: 700;
  color: var(--gt-color-primary);
}
.gt-rct-total-mark {
  display: inline-block;
  margin-right: 4px;
  color: var(--gt-color-wheat);
  font-weight: 700;
}

.gt-rct-formula {
  display: inline-block;
  padding: 2px 6px;
  background: var(--gt-color-bg);
  border: 1px solid var(--gt-color-border-light);
  border-radius: 3px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-teal);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gt-rct-invalid-tag {
  margin-left: 6px;
}
.gt-rct-invalid-ref {
  font-family: 'Consolas', monospace;
  margin: 2px 0;
}
.gt-rct-em {
  color: var(--gt-color-text-placeholder);
  font-size: var(--gt-font-size-xs);
}

/* 公式类别 */
.gt-rct-cat--auto_calc { background: var(--gt-bg-info); color: var(--gt-color-teal); }
.gt-rct-cat--logic_check { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.gt-rct-cat--reasonability { background: var(--gt-color-primary-bg); color: var(--gt-color-primary-light); }

/* 编辑公式对话框 */
.gt-rct-edit-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: var(--gt-font-size-sm);
}
.gt-rct-edit-info > div {
  padding: 8px 12px;
  background: var(--gt-color-primary-bg);
  border-radius: 4px;
}
</style>
