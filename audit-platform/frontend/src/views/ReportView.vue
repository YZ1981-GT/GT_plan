<template>
  <div class="report-view-page">
    <div class="rv-header">
      <h2 class="rv-title">财务报表</h2>
      <div class="rv-actions">
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
      <div v-for="c in consistencyResult.checks.filter(x => !x.passed)" :key="c.name" class="check-item">
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

    <!-- 报表表格 -->
    <el-table :data="rows" v-loading="loading" border stripe style="width: 100%"
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
          <span class="amount-cell" @click="onDrilldown(row)">
            {{ fmtAmt(row.current_period_amount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="160" align="right">
        <template #default="{ row }">{{ fmtAmt(row.prior_period_amount) }}</template>
      </el-table-column>
    </el-table>

    <!-- 穿透弹窗 -->
    <el-dialog v-model="drilldownVisible" :title="`穿透查询 — ${drilldownData?.row_name || ''}`" width="700px">
      <div v-if="drilldownData" class="drilldown-content">
        <div class="dd-section">
          <span class="dd-label">公式：</span>
          <code>{{ drilldownData.formula }}</code>
        </div>
        <el-table :data="drilldownData.accounts" border size="small" style="margin-top: 12px">
          <el-table-column prop="code" label="科目编码" width="120" />
          <el-table-column prop="name" label="科目名称" min-width="200" />
          <el-table-column label="金额" width="150" align="right">
            <template #default="{ row }">{{ fmtAmt(row.amount) }}</template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else v-loading="drilldownLoading" style="min-height: 100px" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  generateReports, getReport, getReportDrilldown, getReportConsistencyCheck,
  getReportExcelUrl,
  type ReportRow, type ReportDrilldownData, type ReportConsistencyCheck,
} from '@/services/auditPlatformApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const loading = ref(false)
const genLoading = ref(false)
const checkLoading = ref(false)
const activeTab = ref('balance_sheet')
const rows = ref<ReportRow[]>([])
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
    rows.value = await getReport(projectId.value, year.value, activeTab.value)
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
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

onMounted(fetchReport)
</script>

<style scoped>
.report-view-page { padding: 16px; }
.rv-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.rv-title { margin: 0; color: var(--gt-color-primary); font-size: 20px; }
.rv-actions { display: flex; gap: 8px; }
.amount-cell { cursor: pointer; color: var(--el-color-primary); }
.amount-cell:hover { text-decoration: underline; }
.check-item { font-size: 13px; margin-top: 4px; }
.drilldown-content .dd-section { margin-bottom: 8px; }
.dd-label { font-weight: 600; color: #666; }
.dd-section code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
:deep(.total-row) { background-color: #e8e0f0 !important; font-weight: 700; }
</style>
