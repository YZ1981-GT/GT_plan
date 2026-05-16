<!--
  FormulaCoverageChart.vue — 公式覆盖率仪表盘 [template-library-coordination Sprint 3.4]

  需求 8.1-8.5：
  - 顶部预填充覆盖率（有公式主编码数 / 主编码总数，从 API 动态取）+ 报表公式覆盖率（动态查询）
  - 按循环展示预填充覆盖率（如 D 循环 N_with_formula/N_total = 百分比）
  - 按报表类型展示公式覆盖率（如 BS 有公式行数 / 总行数）
  - 颜色编码：绿色 ≥80%、黄色 40-79%、红色 <40%
  - "无公式底稿"清单

  D16 ADR：所有数字（覆盖率/主编码总数等）由后端 SQL 实时统计，前端不硬编码任何百分比

  数据源：GET /api/template-library-mgmt/formula-coverage
-->
<template>
  <div v-loading="loading" class="gt-fcc">
    <!-- 顶部两个大型统计卡片 -->
    <div class="gt-fcc-top">
      <div class="gt-fcc-card">
        <div class="gt-fcc-card-label">预填充公式覆盖率</div>
        <div class="gt-fcc-card-main">
          <span class="gt-amt gt-fcc-pct" :class="coverageColor(prefillPct)">
            {{ formatPct(prefillPct) }}
          </span>
          <span class="gt-fcc-card-sub">
            <span class="gt-amt">{{ prefillNumerator }}</span> /
            <span class="gt-amt">{{ prefillDenominator }}</span> 主编码
          </span>
        </div>
        <el-progress
          :percentage="clampPct(prefillPct)"
          :color="progressBarColor(prefillPct)"
          :show-text="false"
          :stroke-width="8"
        />
      </div>

      <div class="gt-fcc-card">
        <div class="gt-fcc-card-label">报表公式覆盖率</div>
        <div class="gt-fcc-card-main">
          <span class="gt-amt gt-fcc-pct" :class="coverageColor(reportPct)">
            {{ formatPct(reportPct) }}
          </span>
          <span class="gt-fcc-card-sub">
            <span class="gt-amt">{{ reportNumerator }}</span> /
            <span class="gt-amt">{{ reportDenominator }}</span> 行
          </span>
        </div>
        <el-progress
          :percentage="clampPct(reportPct)"
          :color="progressBarColor(reportPct)"
          :show-text="false"
          :stroke-width="8"
        />
      </div>
    </div>

    <!-- 颜色图例 -->
    <div class="gt-fcc-legend">
      <span class="gt-fcc-legend-item">
        <span class="gt-fcc-dot gt-fcc-c--green"></span>≥ 80%
      </span>
      <span class="gt-fcc-legend-item">
        <span class="gt-fcc-dot gt-fcc-c--yellow"></span>40 - 79%
      </span>
      <span class="gt-fcc-legend-item">
        <span class="gt-fcc-dot gt-fcc-c--red"></span>&lt; 40%
      </span>
    </div>

    <!-- 按循环展示预填充覆盖率 -->
    <div class="gt-fcc-section">
      <div class="gt-fcc-section-header">
        <h3 class="gt-fcc-section-title">按循环展示预填充覆盖率</h3>
        <span class="gt-fcc-section-meta">
          共 <span class="gt-amt">{{ prefillCoverage.length }}</span> 个循环
        </span>
      </div>
      <el-table
        :data="prefillCoverage"
        size="small"
        :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
        class="gt-fcc-table"
      >
        <el-table-column prop="cycle" label="循环" width="80" />
        <el-table-column prop="cycle_name" label="名称" min-width="160" />
        <el-table-column prop="total_templates" label="主编码总数" width="120" align="right">
          <template #default="{ row }">
            <span class="gt-amt">{{ row.total_templates }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="templates_with_formula" label="有公式" width="100" align="right">
          <template #default="{ row }">
            <span class="gt-amt">{{ row.templates_with_formula }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="coverage_percent" label="覆盖率" min-width="240">
          <template #default="{ row }">
            <div class="gt-fcc-coverage-cell">
              <el-progress
                :percentage="clampPct(row.coverage_percent)"
                :color="progressBarColor(row.coverage_percent)"
                :show-text="false"
                :stroke-width="10"
                class="gt-fcc-coverage-bar"
              />
              <span class="gt-amt gt-fcc-coverage-val" :class="coverageColor(row.coverage_percent)">
                {{ formatPct(row.coverage_percent) }}
              </span>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 按报表类型展示公式覆盖率 -->
    <div class="gt-fcc-section">
      <div class="gt-fcc-section-header">
        <h3 class="gt-fcc-section-title">按报表类型展示公式覆盖率</h3>
        <span class="gt-fcc-section-meta">
          共 <span class="gt-amt">{{ reportCoverage.length }}</span> 个报表标准×类型
        </span>
      </div>
      <el-table
        :data="reportCoverage"
        size="small"
        :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
        class="gt-fcc-table"
      >
        <el-table-column prop="applicable_standard" label="准则" min-width="160">
          <template #default="{ row }">
            <span class="gt-fcc-std-tag">{{ formatStandard(row.applicable_standard) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="report_type" label="报表类型" min-width="140">
          <template #default="{ row }">
            {{ formatReportType(row.report_type) }}
          </template>
        </el-table-column>
        <el-table-column prop="total_rows" label="总行数" width="100" align="right">
          <template #default="{ row }">
            <span class="gt-amt">{{ row.total_rows }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rows_with_formula" label="有公式" width="100" align="right">
          <template #default="{ row }">
            <span class="gt-amt">{{ row.rows_with_formula }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="coverage_percent" label="覆盖率" min-width="240">
          <template #default="{ row }">
            <div class="gt-fcc-coverage-cell">
              <el-progress
                :percentage="clampPct(row.coverage_percent)"
                :color="progressBarColor(row.coverage_percent)"
                :show-text="false"
                :stroke-width="10"
                class="gt-fcc-coverage-bar"
              />
              <span class="gt-amt gt-fcc-coverage-val" :class="coverageColor(row.coverage_percent)">
                {{ formatPct(row.coverage_percent) }}
              </span>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 无公式底稿清单（折叠区） -->
    <div class="gt-fcc-section">
      <el-collapse v-model="noFormulaCollapse">
        <el-collapse-item name="list">
          <template #title>
            <span class="gt-fcc-collapse-title">
              <el-icon class="gt-fcc-warn-icon"><Warning /></el-icon>
              无公式底稿清单
              <el-tag size="small" type="warning" effect="plain">
                <span class="gt-amt">{{ noFormulaTemplates.length }}</span> 个
              </el-tag>
            </span>
          </template>
          <el-empty
            v-if="noFormulaTemplates.length === 0"
            description="无 — 全部主编码均已配置预填充公式"
            :image-size="60"
          />
          <div v-else class="gt-fcc-no-formula-grid">
            <div
              v-for="item in noFormulaTemplates"
              :key="item.wp_code"
              class="gt-fcc-no-formula-item"
            >
              <span class="gt-fcc-no-formula-cycle">{{ item.cycle || '?' }}</span>
              <span class="gt-fcc-no-formula-code">{{ item.wp_code }}</span>
              <span v-if="item.wp_name" class="gt-fcc-no-formula-name">{{ item.wp_name }}</span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Warning } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { templateLibraryMgmt as P_tlm } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface CycleCoverage {
  cycle: string
  cycle_name: string
  total_templates: number
  templates_with_formula: number
  coverage_percent: number
}

interface ReportTypeCoverage {
  report_type: string
  applicable_standard: string
  total_rows: number
  rows_with_formula: number
  coverage_percent: number
}

interface NoFormulaItem {
  wp_code: string
  wp_name?: string | null
  cycle?: string | null
}

interface CoverageSummary {
  total_primary_templates?: number
  primary_with_formula?: number
  prefill_coverage_percent?: number
  total_report_rows?: number
  report_rows_with_formula?: number
  report_coverage_percent?: number
  total_prefill_mappings?: number
  total_prefill_cells?: number
}

const loading = ref(false)
const prefillCoverage = ref<CycleCoverage[]>([])
const reportCoverage = ref<ReportTypeCoverage[]>([])
const noFormulaTemplates = ref<NoFormulaItem[]>([])
const summary = ref<CoverageSummary>({})

const noFormulaCollapse = ref<string[]>([])

// ─── 顶部统计推导（全部从 API summary 取，不硬编码） ───
const prefillNumerator = computed(() => summary.value.primary_with_formula ?? 0)
const prefillDenominator = computed(() => summary.value.total_primary_templates ?? 0)
const prefillPct = computed(() => Number(summary.value.prefill_coverage_percent ?? 0))

const reportNumerator = computed(() => summary.value.report_rows_with_formula ?? 0)
const reportDenominator = computed(() => summary.value.total_report_rows ?? 0)
const reportPct = computed(() => Number(summary.value.report_coverage_percent ?? 0))

// ─── 颜色编码（需求 8.4 + Property 7） ───
function coverageColor(pct: number | string | null | undefined): string {
  const v = Number(pct ?? 0)
  if (v >= 80) return 'gt-fcc-c--green'
  if (v >= 40) return 'gt-fcc-c--yellow'
  return 'gt-fcc-c--red'
}

function progressBarColor(pct: number | string | null | undefined): string {
  const v = Number(pct ?? 0)
  if (v >= 80) return '#67c23a'
  if (v >= 40) return '#e6a23c'
  return '#f56c6c'
}

function clampPct(pct: number | string | null | undefined): number {
  const v = Number(pct ?? 0)
  if (Number.isNaN(v)) return 0
  return Math.max(0, Math.min(100, v))
}

function formatPct(pct: number | string | null | undefined): string {
  const v = Number(pct ?? 0)
  if (Number.isNaN(v)) return '—'
  return `${v.toFixed(1)}%`
}

const STANDARD_LABELS: Record<string, string> = {
  soe_consolidated: '国企-合并',
  soe_standalone: '国企-单体',
  listed_consolidated: '上市-合并',
  listed_standalone: '上市-单体',
  enterprise: '一般企业',
  unknown: '未指定',
}

function formatStandard(code: string): string {
  return STANDARD_LABELS[code] || code
}

const REPORT_TYPE_LABELS: Record<string, string> = {
  balance_sheet: '资产负债表 (BS)',
  income_statement: '利润表 (IS)',
  cash_flow_statement: '现金流量表 (CFS)',
  cash_flow_supplement: '现金流量附表',
  equity_changes: '所有者权益变动表 (EQ)',
  unknown: '未知',
}

function formatReportType(code: string): string {
  return REPORT_TYPE_LABELS[code] || code
}

// ─── 数据加载 ───
async function loadCoverage() {
  loading.value = true
  try {
    const data = await api.get(P_tlm.formulaCoverage)
    prefillCoverage.value = (data?.prefill_coverage || []) as CycleCoverage[]
    reportCoverage.value = (data?.report_formula_coverage || []) as ReportTypeCoverage[]
    noFormulaTemplates.value = (data?.no_formula_templates || []) as NoFormulaItem[]
    summary.value = (data?.summary || {}) as CoverageSummary
  } catch (e: any) {
    handleApiError(e, '加载公式覆盖率')
    prefillCoverage.value = []
    reportCoverage.value = []
    noFormulaTemplates.value = []
    summary.value = {}
  } finally {
    loading.value = false
  }
}

defineExpose({ refresh: loadCoverage })

onMounted(() => {
  loadCoverage()
})
</script>

<style scoped>
.gt-fcc {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px;
}

/* ─── 顶部两个大型卡片 ─── */
.gt-fcc-top {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.gt-fcc-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
  background: var(--gt-color-bg-white);
  border-radius: 8px;
  border: 1px solid #ebeef5;
  border-left: 3px solid #4b2d77;
}
.gt-fcc-card-label {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-info);
  font-weight: 500;
}
.gt-fcc-card-main {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.gt-fcc-pct {
  font-size: 32px /* allow-px: special */;
  font-weight: 700;
  line-height: 1;
}
.gt-fcc-card-sub {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
}
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* ─── 颜色编码 ─── */
.gt-fcc-c--green { color: var(--gt-color-success); }
.gt-fcc-c--yellow { color: var(--gt-color-wheat); }
.gt-fcc-c--red { color: var(--gt-color-coral); }

/* ─── 图例 ─── */
.gt-fcc-legend {
  display: flex;
  gap: 24px;
  padding: 0 4px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-fcc-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.gt-fcc-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.gt-fcc-dot.gt-fcc-c--green { background: var(--gt-color-success); }
.gt-fcc-dot.gt-fcc-c--yellow { background: var(--gt-color-wheat); }
.gt-fcc-dot.gt-fcc-c--red { background: var(--gt-color-coral); }

/* ─── 分组段落 ─── */
.gt-fcc-section {
  background: var(--gt-color-bg-white);
  border-radius: 8px;
  border: 1px solid #ebeef5;
  padding: 12px 16px;
}
.gt-fcc-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.gt-fcc-section-title {
  margin: 0;
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.gt-fcc-section-meta {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}

/* ─── 表格 ─── */
.gt-fcc-table :deep(.el-table__row:hover > td) {
  background-color: var(--gt-color-primary-bg) !important;
}

.gt-fcc-coverage-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}
.gt-fcc-coverage-bar {
  flex: 1;
  min-width: 100px;
}
.gt-fcc-coverage-val {
  width: 60px;
  text-align: right;
  font-weight: 600;
}

/* ─── 准则标签 ─── */
.gt-fcc-std-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-xs);
  font-weight: 500;
}

/* ─── 折叠标题 ─── */
.gt-fcc-collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.gt-fcc-warn-icon {
  color: var(--gt-color-wheat);
}

/* ─── 无公式清单网格 ─── */
.gt-fcc-no-formula-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
  padding: 8px 0;
}
.gt-fcc-no-formula-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--gt-color-wheat-light);
  border-radius: 4px;
  border-left: 3px solid #e6a23c;
  font-size: var(--gt-font-size-sm);
}
.gt-fcc-no-formula-cycle {
  display: inline-block;
  width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
  background: var(--gt-color-primary);
  color: var(--gt-color-text-inverse);
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  flex-shrink: 0;
}
.gt-fcc-no-formula-code {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.gt-fcc-no-formula-name {
  color: var(--gt-color-text-regular);
  font-size: var(--gt-font-size-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
