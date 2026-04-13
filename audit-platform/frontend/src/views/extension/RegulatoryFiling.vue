<template>
  <div class="gt-filing-page">
    <div class="gt-page-header">
      <h2 class="gt-page-title">监管备案</h2>
      <div class="gt-header-actions">
        <el-select v-model="filterType" placeholder="备案类型" clearable size="small" style="width: 160px" @change="loadFilings">
          <el-option label="中注协报告备案" value="cicpa_report" />
          <el-option label="电子底稿归档" value="archival_standard" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="状态" clearable size="small" style="width: 120px" @change="loadFilings">
          <el-option label="已提交" value="submitted" />
          <el-option label="待审核" value="pending" />
          <el-option label="已通过" value="approved" />
          <el-option label="已驳回" value="rejected" />
        </el-select>
        <el-button type="primary" size="small" @click="showCICPA = true">新建中注协备案</el-button>
        <el-button size="small" @click="showArchival = true">新建归档备案</el-button>
      </div>
    </div>

    <el-table :data="filings" v-loading="loading" stripe size="small" style="width: 100%">
      <el-table-column prop="project_name" label="项目" min-width="180" show-overflow-tooltip />
      <el-table-column prop="filing_type" label="备案类型" width="140" align="center">
        <template #default="{ row }">
          {{ row.filing_type === 'cicpa_report' ? '中注协报告备案' : '电子底稿归档' }}
        </template>
      </el-table-column>
      <el-table-column prop="filing_status" label="状态" width="100" align="center">
        <template #default="{ row }">
          <FilingStatus :status="row.filing_status" :submitted-at="row.submitted_at" :responded-at="row.responded_at" />
        </template>
      </el-table-column>
      <el-table-column prop="submitted_at" label="提交时间" width="140">
        <template #default="{ row }">{{ fmtTime(row.submitted_at) }}</template>
      </el-table-column>
      <el-table-column prop="responded_at" label="响应时间" width="140">
        <template #default="{ row }">{{ fmtTime(row.responded_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="viewDetail(row)">详情</el-button>
          <template v-if="row.filing_status === 'rejected' || row.error_message">
            <el-button link type="warning" size="small" @click="showError(row)">错误</el-button>
            <el-button link type="success" size="small" @click="retryFiling(row)">重试</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- 中注协备案表单 -->
    <CICPAReportForm v-model="showCICPA" @submitted="loadFilings" />
    <!-- 归档标准表单 -->
    <ArchivalStandardForm v-model="showArchival" @submitted="loadFilings" />
    <!-- 错误详情 -->
    <FilingError v-model="showErrorDialog" :filing="currentFiling" @retried="loadFilings" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import FilingStatus from '@/components/extension/FilingStatus.vue'
import FilingError from '@/components/extension/FilingError.vue'
import CICPAReportForm from '@/components/extension/CICPAReportForm.vue'
import ArchivalStandardForm from '@/components/extension/ArchivalStandardForm.vue'
import http from '@/utils/http'

const loading = ref(false)
const filings = ref<any[]>([])
const filterType = ref('')
const filterStatus = ref('')
const showCICPA = ref(false)
const showArchival = ref(false)
const showErrorDialog = ref(false)
const currentFiling = ref<any>(null)

async function loadFilings() {
  loading.value = true
  try {
    const params: any = {}
    if (filterType.value) params.filing_type = filterType.value
    if (filterStatus.value) params.filing_status = filterStatus.value
    const { data } = await http.get('/api/regulatory/filings', { params })
    filings.value = data.data ?? data ?? []
  } catch { filings.value = [] }
  finally { loading.value = false }
}

function viewDetail(_row: any) {
  ElMessage.info('备案详情功能开发中')
}

function showError(row: any) {
  currentFiling.value = row
  showErrorDialog.value = true
}

async function retryFiling(row: any) {
  try {
    await http.post(`/api/regulatory/filings/${row.id}/retry`)
    ElMessage.success('重试请求已提交')
    loadFilings()
  } catch { ElMessage.error('重试失败') }
}

function fmtTime(d: string) { return d ? new Date(d).toLocaleString('zh-CN') : '-' }

onMounted(loadFilings)
</script>

<style scoped>
.gt-filing-page { padding: var(--gt-space-4); }
.gt-page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-4); flex-wrap: wrap; gap: var(--gt-space-2);
}
.gt-page-title { font-size: var(--gt-font-size-xl); font-weight: 600; margin: 0; }
.gt-header-actions { display: flex; gap: var(--gt-space-2); align-items: center; }
</style>
