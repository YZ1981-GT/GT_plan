<template>
  <div class="report-page">
    <!-- 顶部操作栏 -->
    <el-card class="toolbar-card" shadow="never">
      <div class="toolbar">
        <div class="left">
          <h2>未审报表</h2>
          <el-tag type="warning" effect="plain">未审数 — 基于试算表原始数据</el-tag>
        </div>
        <div class="right">
          <el-select v-model="currentYear" placeholder="选择年度" style="width:120px;margin-right:12px;" @change="loadReport">
            <el-option v-for="y in yearOptions" :key="y" :label="y + '年'" :value="y" />
          </el-select>
          <el-button :icon="Refresh" type="primary" :loading="syncLoading" @click="handleRefresh">
            刷新同步
          </el-button>
          <el-button :icon="Link" @click="goToAdjusted">审定报表</el-button>
          <el-button :icon="List" @click="goToTrialBalance">试算平衡表</el-button>
          <el-button :icon="EditPen" @click="goToAdjustments">调整分录</el-button>
        </div>
      </div>
    </el-card>

    <!-- 四表 Tab -->
    <el-card class="report-tabs-card" shadow="never">
      <el-tabs v-model="activeReportType" type="border-card" @tab-change="onTabChange">
        <el-tab-pane label="资产负债表" name="balance_sheet">
          <ReportTable :data="reportData" :loading="tableLoading" report-name="资产负债表" @drilldown="handleDrilldown" />
        </el-tab-pane>
        <el-tab-pane label="利润表" name="income_statement">
          <ReportTable :data="reportData" :loading="tableLoading" report-name="利润表" @drilldown="handleDrilldown" />
        </el-tab-pane>
        <el-tab-pane label="现金流量表" name="cash_flow_statement">
          <ReportTable :data="reportData" :loading="tableLoading" report-name="现金流量表" @drilldown="handleDrilldown" />
        </el-tab-pane>
        <el-tab-pane label="所有者权益变动表" name="equity_statement">
          <ReportTable :data="reportData" :loading="tableLoading" report-name="所有者权益变动表" @drilldown="handleDrilldown" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 联动面板：试算表科目映射 -->
    <el-card v-if="drilldownVisible" class="drilldown-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>科目穿透 — 当前行次关联试算表科目</span>
          <el-button :icon="Close" text @click="drilldownVisible = false" />
        </div>
      </template>
      <el-table :data="drilldownData" size="small" border>
        <el-table-column prop="account_code" label="科目代码" width="140" />
        <el-table-column prop="account_name" label="科目名称" />
        <el-table-column prop="amount" label="金额" align="right">
          <template #default="{ row }">
            <span :class="{ negative: row.amount < 0 }">{{ formatNumber(row.amount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 操作提示 -->
    <el-alert
      v-if="syncResult"
      :title="syncResult.message"
      :type="syncResult.success ? 'success' : 'error'"
      show-icon
      closable
      style="margin-top:16px"
      @close="syncResult = null"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Refresh, Link, List, EditPen, Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ReportTable from '@/components/reports/ReportTable.vue'
import { auditReports, trialBalance, getProjectAuditYear } from '@/api/index.js'

const route = useRoute()
const router = useRouter()

// 项目与年度
const currentProjectId = computed(() => route.query.project_id || localStorage.getItem('current_project_id') || '')
const routeYear = computed(() => {
  const value = Number(route.query.year)
  return Number.isFinite(value) && value > 2000 ? value : null
})
const routeType = computed(() => String(route.query.type || 'balance_sheet'))
const projectYear = ref(null)
const currentYear = ref(new Date().getFullYear())
const yearOptions = computed(() => {
  const baseYear = currentYear.value || projectYear.value || routeYear.value || new Date().getFullYear()
  return [baseYear, baseYear - 1, baseYear - 2]
})

// 报表类型
const activeReportType = ref(routeType.value)
const reportData = ref([])
const tableLoading = ref(false)
const syncLoading = ref(false)
const syncResult = ref(null)

// 穿透
const drilldownVisible = ref(false)
const drilldownData = ref([])

async function ensureProjectYear() {
  if (!currentProjectId.value) {
    projectYear.value = null
    currentYear.value = new Date().getFullYear()
    return
  }
  if (routeYear.value !== null) {
    projectYear.value = null
    currentYear.value = routeYear.value
    return
  }
  try {
    projectYear.value = await getProjectAuditYear(currentProjectId.value)
  } catch {
    projectYear.value = null
  }
  currentYear.value = projectYear.value ?? new Date().getFullYear()
}

// 获取未审报表
async function loadReport() {
  if (!currentProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  tableLoading.value = true
  try {
    const data = await auditReports.getUnadjusted(
      currentProjectId.value,
      currentYear.value,
      activeReportType.value
    )
    reportData.value = Array.isArray(data) ? data : []
  } catch (err) {
    ElMessage.error(err.message || '加载未审报表失败')
    reportData.value = []
  } finally {
    tableLoading.value = false
  }
}

// 刷新同步：重算试算表 → 重新获取未审报表
async function handleRefresh() {
  if (!currentProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  syncLoading.value = true
  try {
    // Step 1: 触发试算表全量重算（从科目映射+TB余额同步未审数）
    await trialBalance.recalc(currentProjectId.value, currentYear.value)
    // Step 2: 重新获取未审报表
    await loadReport()
    syncResult.value = {
      success: true,
      message: `刷新同步完成：已重算试算表并重新生成${reportTypeLabel.value}未审数据`,
    }
    ElMessage.success('刷新同步成功')
  } catch (err) {
    syncResult.value = {
      success: false,
      message: `同步失败：${err.message || '未知错误'}`,
    }
    ElMessage.error(`同步失败：${err.message}`)
  } finally {
    syncLoading.value = false
  }
}

// Tab 切换
function onTabChange() {
  loadReport()
}

// 穿透查询：联动后端 drilldown API
async function handleDrilldown(row) {
  if (!currentProjectId.value) return
  drilldownVisible.value = true
  try {
    const result = await auditReports.drilldown(
      currentProjectId.value,
      currentYear.value,
      activeReportType.value,
      row.row_code
    )
    drilldownData.value = (result.contributing_accounts || []).map(a => ({
      account_code: a.account_code,
      account_name: a.account_name || '-',
      amount: a.unadjusted_amount ?? a.amount ?? 0,
    }))
  } catch (err) {
    drilldownData.value = []
    ElMessage.error(err.message || '穿透查询失败')
  }
}

// 联动跳转
function goToAdjusted() {
  router.push({
    path: '/reports/adjusted',
    query: { project_id: currentProjectId.value, year: currentYear.value, type: activeReportType.value },
  })
}
function goToTrialBalance() {
  router.push({
    path: '/reports/trial-balance',
    query: { project_id: currentProjectId.value, year: currentYear.value },
  })
}
function goToAdjustments() {
  router.push({
    path: '/reports/adjustment-entries',
    query: { project_id: currentProjectId.value, year: currentYear.value },
  })
}

// 格式化
function formatNumber(v) {
  if (v === null || v === undefined) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const reportTypeLabel = computed(() => {
  const map = {
    balance_sheet: '资产负债表',
    income_statement: '利润表',
    cash_flow_statement: '现金流量表',
    equity_statement: '所有者权益变动表',
  }
  return map[activeReportType.value] || ''
})

// 监听参数变化
watch(
  () => [currentProjectId.value, routeYear.value, routeType.value],
  async () => {
    activeReportType.value = routeType.value
    await ensureProjectYear()
    await loadReport()
  },
  { immediate: true }
)
</script>

<style scoped>
.report-page {
  padding: 16px;
  background: #f5f7fa;
  min-height: 100vh;
}
.toolbar-card {
  margin-bottom: 16px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.toolbar .left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.toolbar .left h2 {
  margin: 0;
  font-size: 20px;
}
.toolbar .right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.report-tabs-card {
  margin-bottom: 16px;
}
.drilldown-card {
  margin-bottom: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.negative {
  color: #f56c6c;
}
</style>
