<template>
  <div class="gt-report-view gt-fade-in">
    <!-- 页面横幅 -->
    <div class="gt-rv-banner">
      <div class="gt-rv-banner-text">
        <h2>财务报表</h2>
        <p>{{ activeTabLabel }} · {{ reportModeLabel }}</p>
      </div>
      <div class="gt-rv-banner-actions">
        <el-radio-group v-model="reportMode" size="small" @change="fetchReport">
          <el-radio-button value="audited">已审</el-radio-button>
          <el-radio-button value="unadjusted">未审</el-radio-button>
          <el-radio-button value="compare">对比</el-radio-button>
        </el-radio-group>
        <el-button v-if="reportMode === 'unadjusted'" type="primary" size="small" @click="onSyncUnadjusted" :loading="syncLoading" round>刷新未审数</el-button>
        <el-button size="small" @click="onGenerate" :loading="genLoading" round>重新生成</el-button>
        <el-button size="small" @click="onConsistencyCheck" :loading="checkLoading" round>一致性校验</el-button>
        <el-button size="small" @click="onExportExcel" round>导出 Excel</el-button>
        <el-button size="small" @click="onEditConfig" round>编辑结构</el-button>
      </div>
    </div>

    <!-- 一致性校验结果 -->
    <el-alert v-if="consistencyResult && !consistencyResult.consistent" type="error" :closable="true"
      show-icon style="margin-bottom: 12px">
      <template #title>
        跨报表一致性校验未通过
      </template>
      <div v-for="c in consistencyResult.checks.filter(x => !x.passed)" :key="c.name" class="gt-rv-check-item">
        {{ c.name }}：期望 {{ c.expected }}，实际 {{ c.actual }}，差额 {{ c.diff }}
      </div>
    </el-alert>
    <el-alert v-if="consistencyResult?.consistent" type="success" :closable="true"
      title="跨报表一致性校验通过" show-icon style="margin-bottom: 12px" />

    <!-- 四张报表 Tab -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="资产负债表" name="balance_sheet" />
      <el-tab-pane label="利润表" name="income_statement" />
      <el-tab-pane label="现金流量表" name="cash_flow_statement" />
      <el-tab-pane label="所有者权益变动表" name="equity_statement" />
    </el-tabs>

    <!-- 报表表格 — 普通模式 -->
    <el-table v-if="reportMode !== 'compare'" :data="rows" v-loading="loading" border stripe style="width: 100%"
      :row-class-name="rowClassName">
      <el-table-column prop="row_code" label="行次" width="100" />
      <el-table-column label="项目" min-width="250">
        <template #default="{ row }">
          <span :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">
            {{ row.row_name }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" width="160" align="right">
        <template #default="{ row }">
          <span class="gt-rv-amount-cell" @click="onDrilldown(row)">
            {{ fmtAmt(row.current_period_amount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="160" align="right">
        <template #default="{ row }">{{ fmtAmt(row.prior_period_amount) }}</template>
      </el-table-column>
    </el-table>

    <!-- 报表表格 — 对比视图 -->
    <el-table v-if="reportMode === 'compare'" :data="compareRows" v-loading="loading" border stripe style="width: 100%"
      :row-class-name="compareRowClassName">
      <el-table-column prop="row_code" label="行次" width="80" />
      <el-table-column label="项目" min-width="200">
        <template #default="{ row }">
          <span :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">{{ row.row_name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="未审金额" width="140" align="right">
        <template #default="{ row }">{{ fmtAmt(row.unadjusted_amount) }}</template>
      </el-table-column>
      <el-table-column label="调整影响" width="140" align="right">
        <template #default="{ row }">
          <span :style="{ color: row.adjustment !== 0 ? '#FF5149' : '#999' }">{{ fmtAmt(row.adjustment) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="已审金额" width="140" align="right">
        <template #default="{ row }">{{ fmtAmt(row.audited_amount) }}</template>
      </el-table-column>
    </el-table>

    <!-- 穿透弹窗 -->
    <el-dialog append-to-body v-model="drilldownVisible" :title="`穿透查询 — ${drilldownData?.row_name || ''}`" width="700px">
      <div v-if="drilldownData" class="gt-rv-drilldown-content">
        <div class="gt-rv-dd-section">
          <span class="gt-rv-dd-label">公式：</span>
          <code>{{ drilldownData.formula }}</code>
        </div>
        <el-table :data="drilldownData.accounts" border size="small" style="margin-top: 12px">
          <el-table-column prop="code" label="科目编码" width="120" />
          <el-table-column prop="name" label="科目名称" min-width="200" />
          <el-table-column label="金额" width="150" align="right">
            <template #default="{ row }">{{ fmtAmt(row.amount) }}</template>
          </el-table-column>
          <el-table-column label="底稿" width="100" align="center">
            <template #default="{ row }">
              <el-button v-if="row.wp_id" link type="primary" size="small"
                @click="openWorkpaper(row.wp_id)">打开底稿</el-button>
              <span v-else style="color: #ccc">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else v-loading="drilldownLoading" style="min-height: 100px" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  generateReports, getReport, getReportDrilldown, getReportConsistencyCheck, recalcTrialBalance,
  getReportExcelUrl, getProjectAuditYear,
  type ReportRow, type ReportDrilldownData, type ReportConsistencyCheck,
} from '@/services/auditPlatformApi'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const routeYear = computed(() => {
  const value = Number(route.query.year)
  return Number.isFinite(value) && value > 2000 ? value : null
})
const projectYear = ref<number | null>(null)
const year = computed(() => routeYear.value ?? projectYear.value ?? new Date().getFullYear())

const loading = ref(false)
const genLoading = ref(false)
const checkLoading = ref(false)
const syncLoading = ref(false)
const activeTab = ref('balance_sheet')
const reportMode = ref('audited')
const rows = ref<ReportRow[]>([])

const activeTabLabel = computed(() => {
  const m: Record<string, string> = { balance_sheet: '资产负债表', income_statement: '利润表', cash_flow_statement: '现金流量表', equity_statement: '权益变动表' }
  return m[activeTab.value] || ''
})
const reportModeLabel = computed(() => {
  const m: Record<string, string> = { audited: '已审报表', unadjusted: '未审报表', compare: '对比视图' }
  return m[reportMode.value] || ''
})
const compareRows = ref<any[]>([])
const consistencyResult = ref<ReportConsistencyCheck | null>(null)

// Drilldown
const drilldownVisible = ref(false)
const drilldownLoading = ref(false)
const drilldownData = ref<ReportDrilldownData | null>(null)

function fmtAmt(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  const n = typeof v === 'string' ? parseFloat(v) || 0 : v
  if (n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: { row: ReportRow }) {
  if (row.is_total_row) return 'total-row'
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

async function fetchReport() {
  loading.value = true
  try {
    if (reportMode.value === 'compare') {
      // 对比视图：同时加载未审+已审
      const [audited, unadjusted] = await Promise.all([
        getReport(projectId.value, year.value, activeTab.value, false),
        getReport(projectId.value, year.value, activeTab.value, true),
      ])
      // 合并为对比行
      const uMap = new Map(unadjusted.map((r: any) => [r.row_code, r]))
      compareRows.value = audited.map((r: any) => {
        const u = uMap.get(r.row_code)
        const uAmt = parseFloat(u?.current_period_amount || '0')
        const aAmt = parseFloat(r.current_period_amount || '0')
        return {
          ...r,
          unadjusted_amount: uAmt,
          audited_amount: aAmt,
          adjustment: Math.round((aAmt - uAmt) * 100) / 100,
        }
      })
      rows.value = audited
    } else {
      rows.value = await getReport(projectId.value, year.value, activeTab.value, reportMode.value === 'unadjusted')
      compareRows.value = []
    }
  } catch {
    rows.value = []
    compareRows.value = []
  } finally {
    loading.value = false
  }
}

function compareRowClassName({ row }: { row: any }) {
  if (row.is_total_row) return 'total-row'
  if (row.adjustment && row.adjustment !== 0) return 'diff-row'
  return ''
}

function onTabChange() { fetchReport() }

async function onSyncUnadjusted() {
  syncLoading.value = true
  try {
    await recalcTrialBalance(projectId.value, year.value)
    await fetchReport()
    ElMessage.success('未审数已按四表账套科目重新同步')
  } finally {
    syncLoading.value = false
  }
}

async function onGenerate() {
  genLoading.value = true
  try {
    await generateReports(projectId.value, year.value)
    ElMessage.success('报表生成完成')
    await fetchReport()
  } finally {
    genLoading.value = false
  }
}

async function onConsistencyCheck() {
  checkLoading.value = true
  try {
    consistencyResult.value = await getReportConsistencyCheck(projectId.value, year.value)
  } finally {
    checkLoading.value = false
  }
}

function onExportExcel() {
  import('@/services/commonApi').then(({ downloadFileAsBlob }) => {
    const url = getReportExcelUrl(projectId.value, year.value, activeTab.value)
    downloadFileAsBlob(url, `报表_${activeTab.value}_${year.value}.xlsx`)
  })
}

function onEditConfig() {
  router.push(`/projects/${projectId.value}/report-config`)
}

async function onDrilldown(row: ReportRow) {
  if (!row.row_code || row.is_total_row) return
  drilldownVisible.value = true
  drilldownLoading.value = true
  drilldownData.value = null
  try {
    const result = await getReportDrilldown(projectId.value, year.value, activeTab.value, row.row_code)
    drilldownData.value = {
      ...result,
      accounts: result.accounts.map((item: any) => ({
        ...item,
        amount: reportMode.value === 'unadjusted'
          ? (item.unadjusted_amount ?? item.amount ?? '0')
          : (item.audited_amount ?? item.amount ?? '0'),
      })),
    }
  } catch {
    ElMessage.error('穿透查询失败')
  } finally {
    drilldownLoading.value = false
  }
}

function openWorkpaper(wpId: string) {
  router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId } })
}

watch(
  () => [projectId.value, routeYear.value],
  async () => {
    await ensureProjectYear()
    await fetchReport()
  },
  { immediate: true }
)
</script>

<style scoped>
.gt-report-view { padding: var(--gt-space-5); }

/* ── 页面横幅 ── */
.gt-rv-banner {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 20px 28px;
  margin-bottom: var(--gt-space-5);
  color: #fff;
  position: relative; overflow: hidden;
  box-shadow: 0 4px 20px rgba(75, 45, 119, 0.2);
  background-image: var(--gt-gradient-primary), linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
}
.gt-rv-banner::before {
  content: '';
  position: absolute; top: -40%; right: -10%;
  width: 45%; height: 180%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.07) 0%, transparent 65%);
  pointer-events: none;
}
.gt-rv-banner-text h2 { margin: 0 0 2px; font-size: 18px; font-weight: 700; }
.gt-rv-banner-text p { margin: 0; font-size: 12px; opacity: 0.75; }
.gt-rv-banner-actions {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  position: relative; z-index: 1;
}
.gt-rv-banner-actions .el-button { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff; }
.gt-rv-banner-actions .el-button:hover { background: rgba(255,255,255,0.25); }
.gt-rv-banner-actions :deep(.el-radio-button__inner) { background: rgba(255,255,255,0.1); border-color: rgba(255,255,255,0.2); color: rgba(255,255,255,0.85); }
.gt-rv-banner-actions :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) { background: rgba(255,255,255,0.25); color: #fff; font-weight: 600; }

/* ── 金额单元格 ── */
.gt-rv-amount-cell {
  cursor: pointer; color: var(--gt-color-primary); font-weight: 500;
  font-variant-numeric: tabular-nums;
  transition: all var(--gt-transition-fast);
  padding: 2px 4px; border-radius: var(--gt-radius-sm);
}
.gt-rv-amount-cell:hover { color: var(--gt-color-primary-light); background: var(--gt-color-primary-bg); }

.gt-rv-check-item {
  font-size: var(--gt-font-size-sm); margin-top: var(--gt-space-1);
  padding: 6px 10px; background: rgba(255,81,73,0.06); border-radius: var(--gt-radius-md);
  border-left: 3px solid var(--gt-color-coral);
}

.gt-rv-drilldown-content .gt-rv-dd-section { margin-bottom: var(--gt-space-3); }
.gt-rv-dd-label { font-weight: 600; color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-sm); }
.gt-rv-dd-section code {
  background: linear-gradient(135deg, #f8f6fb, #f4f0fa);
  padding: 4px 12px; border-radius: var(--gt-radius-md);
  font-size: var(--gt-font-size-sm); border: 1px solid rgba(75,45,119,0.08);
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  display: inline-block;
}

:deep(.total-row) { background: linear-gradient(90deg, #ece4f5, #e8e0f0) !important; font-weight: 700; }
:deep(.total-row td) { border-bottom: 2px solid var(--gt-color-primary-lighter) !important; }
:deep(.diff-row) { background: linear-gradient(90deg, #fff8f0, #fff3e0) !important; }
:deep(.el-tabs__item) { font-size: 14px; }
:deep(.el-tabs__item.is-active) { font-weight: 600; }
:deep(.el-tabs__active-bar) { height: 3px; border-radius: 2px; }
</style>
