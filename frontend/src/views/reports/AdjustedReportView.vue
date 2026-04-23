<template>
  <div class="report-page">
    <el-card class="toolbar-card" shadow="never">
      <div class="toolbar">
        <div class="left">
          <h2>审定报表</h2>
          <el-tag type="success" effect="plain">审定数 — 含调整分录后</el-tag>
        </div>
        <div class="right">
          <el-select v-model="currentYear" placeholder="选择年度" style="width:120px;margin-right:12px;">
            <el-option v-for="y in yearOptions" :key="y" :label="y + '年'" :value="y" />
          </el-select>
          <el-button :icon="RefreshRight" @click="loadReport">刷新</el-button>
          <el-button :icon="Document" @click="goToUnadjusted">未审报表</el-button>
          <el-button :icon="List" @click="goToTrialBalance">试算平衡表</el-button>
          <el-button :icon="EditPen" @click="goToAdjustments">调整分录</el-button>
        </div>
      </div>
    </el-card>

    <el-card class="report-tabs-card" shadow="never">
      <el-tabs v-model="activeReportType" type="border-card" @tab-change="onTabChange">
        <el-tab-pane label="资产负债表" name="balance_sheet">
          <ReportTable :data="reportData" :loading="tableLoading" report-name="资产负债表（审定）" />
        </el-tab-pane>
        <el-tab-pane label="利润表" name="income_statement">
          <ReportTable :data="reportData" :loading="tableLoading" report-name="利润表（审定）" />
        </el-tab-pane>
        <el-tab-pane label="现金流量表" name="cash_flow_statement">
          <ReportTable :data="reportData" :loading="tableLoading" report-name="现金流量表（审定）" />
        </el-tab-pane>
        <el-tab-pane label="所有者权益变动表" name="equity_statement">
          <ReportTable :data="reportData" :loading="tableLoading" report-name="所有者权益变动表（审定）" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-alert
      v-if="reportData.length === 0 && !tableLoading"
      title="当前报表未生成，请先在「未审报表」页面点击「刷新同步」或在后台生成报表。"
      type="info"
      show-icon
      closable
      style="margin-top:16px"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { RefreshRight, Document, List, EditPen } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ReportTable from '@/components/reports/ReportTable.vue'
import { auditReports } from '@/api/index.js'

const route = useRoute()
const router = useRouter()

const currentProjectId = computed(() => route.query.project_id || localStorage.getItem('current_project_id') || '')
const currentYear = ref(parseInt(route.query.year) || new Date().getFullYear())
const yearOptions = computed(() => {
  const y = new Date().getFullYear()
  return [y, y - 1, y - 2]
})

const activeReportType = ref(route.query.type || 'balance_sheet')
const reportData = ref([])
const tableLoading = ref(false)

async function loadReport() {
  if (!currentProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  tableLoading.value = true
  try {
    const data = await auditReports.getAdjusted(
      currentProjectId.value,
      currentYear.value,
      activeReportType.value
    )
    reportData.value = Array.isArray(data) ? data : []
  } catch (err) {
    ElMessage.error(err.message || '加载审定报表失败')
    reportData.value = []
  } finally {
    tableLoading.value = false
  }
}

function onTabChange() {
  loadReport()
}

function goToUnadjusted() {
  router.push({
    path: '/reports/unadjusted',
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

watch([currentProjectId, currentYear], () => {
  loadReport()
}, { immediate: true })
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
</style>
