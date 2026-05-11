<template>
  <div class="ledger-import-history">
    <div class="page-header">
      <div>
        <h2>账表导入历史</h2>
        <p>查看导入作业、数据集版本、激活记录，并支持回滚到上一有效版本。</p>
      </div>
      <div class="actions">
        <el-input-number v-model="selectedYear" :min="2000" :max="2100" size="small" />
        <el-button :loading="loading" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <el-alert
      v-if="activeDatasetId"
      type="success"
      :closable="false"
      show-icon
      :title="`当前 active dataset：${activeDatasetId}`"
      style="margin-bottom: 16px"
    />
    <el-alert
      v-else
      type="warning"
      :closable="false"
      show-icon
      title="当前年度尚无 active dataset"
      style="margin-bottom: 16px"
    />

    <el-tabs>
      <el-tab-pane label="数据集版本">
        <el-table :data="datasets" v-loading="loading" border>
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="(datasetTagType(row.status)) || undefined">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="id" label="Dataset ID" min-width="260" show-overflow-tooltip />
          <el-table-column prop="record_summary" label="记录摘要" min-width="220">
            <template #default="{ row }">{{ formatJson(row.record_summary) }}</template>
          </el-table-column>
          <el-table-column prop="validation_summary" label="校验摘要" min-width="220">
            <template #default="{ row }">{{ formatJson(row.validation_summary) }}</template>
          </el-table-column>
          <el-table-column prop="activated_at" label="激活时间" width="190" />
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'active' && row.previous_dataset_id"
                size="small"
                type="warning"
                @click="rollback(row)"
              >
                回滚
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="导入作业">
        <el-table :data="jobs" v-loading="loading" border>
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="(jobTagType(row.status)) || undefined">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="id" label="Job ID" min-width="260" show-overflow-tooltip />
          <el-table-column prop="progress_pct" label="进度" width="180">
            <template #default="{ row }">
              <el-progress :percentage="Math.max(0, Math.min(row.progress_pct || 0, 100))" />
            </template>
          </el-table-column>
          <el-table-column prop="progress_message" label="阶段信息" min-width="220" show-overflow-tooltip />
          <el-table-column prop="error_message" label="错误" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button v-if="['failed', 'timed_out'].includes(row.status)" size="small" @click="retry(row)">重试</el-button>
              <el-button v-if="['pending', 'queued', 'running', 'validating', 'writing', 'activating'].includes(row.status)" size="small" type="danger" @click="cancel(row)">取消</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="激活记录">
        <el-table :data="records" v-loading="loading" border>
          <el-table-column prop="action" label="动作" width="120" />
          <el-table-column prop="dataset_id" label="Dataset ID" min-width="260" show-overflow-tooltip />
          <el-table-column prop="previous_dataset_id" label="Previous" min-width="260" show-overflow-tooltip />
          <el-table-column prop="performed_at" label="时间" width="190" />
          <el-table-column prop="reason" label="原因" min-width="220" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="上传产物">
        <el-table :data="artifacts" v-loading="loading" border>
          <el-table-column prop="status" label="状态" width="120" />
          <el-table-column prop="upload_token" label="Upload Token" min-width="260" show-overflow-tooltip />
          <el-table-column prop="file_count" label="文件数" width="100" />
          <el-table-column prop="storage_uri" label="存储位置" min-width="220" show-overflow-tooltip />
          <el-table-column prop="total_size_bytes" label="大小" width="140">
            <template #default="{ row }">{{ formatBytes(row.total_size_bytes) }}</template>
          </el-table-column>
          <el-table-column prop="checksum" label="Checksum" min-width="260" show-overflow-tooltip />
          <el-table-column prop="expires_at" label="过期时间" width="190" />
        </el-table>
      </el-tab-pane>

      <!-- 10.9: 导入历史时间轴 -->
      <el-tab-pane label="时间轴">
        <ImportTimeline
          :project-id="projectId"
          :initial-year="selectedYear"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { confirmDangerous } from '@/utils/confirm'
import {
  cancelImportJob,
  getActiveLedgerDataset,
  listActivationRecords,
  listImportArtifacts,
  listImportJobs,
  listLedgerDatasets,
  retryImportJob,
  rollbackLedgerDataset,
  type ImportJob,
  type LedgerDataset,
  type ImportArtifact,
} from '@/services/ledgerImportApi'
import ImportTimeline from '@/components/ledger-import/ImportTimeline.vue'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const selectedYear = ref(Number(route.query.year) || new Date().getFullYear() - 1)
const loading = ref(false)
const activeDatasetId = ref<string | null>(null)
const datasets = ref<LedgerDataset[]>([])
const jobs = ref<ImportJob[]>([])
const records = ref<any[]>([])
const artifacts = ref<ImportArtifact[]>([])

function formatJson(value: unknown) {
  if (!value) return '-'
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function formatBytes(value: number) {
  if (!value) return '0 B'
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function datasetTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (status === 'active') return 'success'
  if (status === 'failed' || status === 'rolled_back') return 'danger'
  if (status === 'staged') return 'warning'
  return 'info'
}

function jobTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (status === 'completed') return 'success'
  if (status === 'failed' || status === 'timed_out' || status === 'canceled') return 'danger'
  if (status === 'running' || status === 'writing' || status === 'activating') return 'warning'
  return 'info'
}

async function loadAll() {
  if (!projectId.value) return
  loading.value = true
  try {
    const [active, datasetList, jobList, recordList, artifactList] = await Promise.all([
      getActiveLedgerDataset(projectId.value, selectedYear.value),
      listLedgerDatasets(projectId.value, selectedYear.value),
      listImportJobs(projectId.value, selectedYear.value),
      listActivationRecords(projectId.value, selectedYear.value),
      listImportArtifacts(projectId.value),
    ])
    activeDatasetId.value = active.active_dataset_id
    datasets.value = datasetList
    jobs.value = jobList
    records.value = recordList
    artifacts.value = artifactList
  } finally {
    loading.value = false
  }
}

async function rollback(row: LedgerDataset) {
  // 8.23: 展示影响对象清单
  let impactMessage = '确认回滚到上一 active 数据集？该操作会切换当前可见账表数据。'
  try {
    // Try to get active dataset info to show bound objects
    const { api } = await import('@/services/apiProxy')
    const { ledger: ledgerPaths } = await import('@/services/apiPaths')
    const activeInfo: any = await api.get(ledgerPaths.import.datasetsActive(projectId.value), { params: { year: selectedYear.value } })
    if (activeInfo?.bound_reports_count || activeInfo?.bound_workpapers_count) {
      const parts: string[] = []
      if (activeInfo.bound_reports_count) parts.push(`${activeInfo.bound_reports_count} 份报表`)
      if (activeInfo.bound_workpapers_count) parts.push(`${activeInfo.bound_workpapers_count} 个底稿`)
      impactMessage = `以下对象将受影响：${parts.join(' / ')}\n\n回滚后这些对象将标记为"数据过期"(stale)，需要重新核对。`
    }
  } catch {
    // If we can't get impact info, proceed with basic confirmation
  }

  await confirmDangerous(impactMessage, '回滚确认')

  try {
    await rollbackLedgerDataset(projectId.value, row.id, selectedYear.value, '用户从导入历史页面发起回滚')
    ElMessage.success('回滚成功')
    await loadAll()
  } catch (err: any) {
    // 8.23: Handle 409 SIGNED_REPORTS_BOUND — show the reports list from error detail
    const detail = err?.detail || err?.response?.data?.detail || err?.response?.data?.message
    if (detail?.error_code === 'SIGNED_REPORTS_BOUND' || err?.response?.status === 409) {
      const reports = detail?.bound_reports || detail?.reports || []
      const reportList = reports.length > 0
        ? reports.map((r: any) => `• ${r.title || r.id}`).join('\n')
        : '（已签字报表）'
      ElMessageBox.alert(
        `无法回滚：以下已签字报表绑定了当前数据集，回滚将导致数据不一致。\n\n${reportList}\n\n如需强制回滚，请联系管理员使用"强制解绑"功能。`,
        '回滚被拒绝',
        { type: 'error', confirmButtonText: '知道了' },
      )
    } else {
      ElMessage.error('回滚失败: ' + (detail?.message || err?.message || '未知错误'))
    }
  }
}

async function retry(row: ImportJob) {
  await retryImportJob(projectId.value, row.id)
  ElMessage.success('已重新排队')
  await loadAll()
}

async function cancel(row: ImportJob) {
  await cancelImportJob(projectId.value, row.id)
  ElMessage.success('已取消')
  await loadAll()
}

watch(selectedYear, loadAll)
onMounted(loadAll)
</script>

<style scoped>
.ledger-import-history {
  padding: 20px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0 0 6px;
}

.page-header p {
  margin: 0;
  color: #666;
}

.actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
