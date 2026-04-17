<template>
  <div class="gt-report-view gt-fade-in">
    <div class="gt-rv-header">
      <h2 class="gt-page-title">财务报表</h2>
      <div class="gt-rv-actions">
        <el-radio-group v-model="reportMode" size="small" style="margin-right: 12px" @change="fetchReport">
          <el-radio-button value="audited">已审报表</el-radio-button>
          <el-radio-button value="unadjusted">未审报表</el-radio-button>
          <el-radio-button value="compare">对比视图</el-radio-button>
        </el-radio-group>
        <el-button @click="onGenerate" :loading="genLoading">重新生成</el-button>
        <el-button @click="onConsistencyCheck" :loading="checkLoading">一致性校验</el-button>
        <el-button @click="onExportExcel">导出 Excel</el-button>
        <el-button type="primary" @click="$router.push({ name: 'PDFExport', params: { projectId } })">导出 PDF</el-button>
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
    <el-dialog v-model="drilldownVisible" :title="`穿透查询 — ${drilldownData?.row_name || ''}`" width="700px">
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
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  generateReports, getReport, getReportDrilldown, getReportConsistencyCheck,
  getReportExcelUrl,
  type ReportRow, type ReportDrilldownData, type ReportConsistencyCheck,
} from '@/services/auditPlatformApi'

const route = useRoute()
const router = useRouter()

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const loading = ref(false)
const genLoading = ref(false)
const checkLoading = ref(false)
const activeTab = ref('balance_sheet')
const reportMode = ref('audited')
const rows = ref<ReportRow[]>([])
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
  window.open(getReportExcelUrl(projectId.value, year.value, activeTab.value), '_blank')
}

async function onDrilldown(row: ReportRow) {
  if (!row.row_code || row.is_total_row) return
  drilldownVisible.value = true
  drilldownLoading.value = true
  drilldownData.value = null
  try {
    drilldownData.value = await getReportDrilldown(projectId.value, year.value, activeTab.value, row.row_code)
  } catch {
    ElMessage.error('穿透查询失败')
  } finally {
    drilldownLoading.value = false
  }
}

function openWorkpaper(wpId: string) {
  router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId } })
}

onMounted(fetchReport)
</script>

<style scoped>
.gt-report-view { padding: var(--gt-space-4); }
.gt-rv-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
.gt-rv-actions { display: flex; gap: var(--gt-space-2); }
.gt-rv-amount-cell { cursor: pointer; color: var(--el-color-primary); }
.gt-rv-amount-cell:hover { text-decoration: underline; }
.gt-rv-check-item { font-size: var(--gt-font-size-sm); margin-top: var(--gt-space-1); }
.gt-rv-drilldown-content .gt-rv-dd-section { margin-bottom: var(--gt-space-2); }
.gt-rv-dd-label { font-weight: 600; color: var(--gt-color-text-secondary); }
.gt-rv-dd-section code { background: var(--gt-color-bg); padding: 2px 6px; border-radius: var(--gt-radius-sm); font-size: var(--gt-font-size-sm); }
:deep(.total-row) { background-color: #e8e0f0 !important; font-weight: 700; }
:deep(.diff-row) { background-color: #fff3e0 !important; }
</style>
