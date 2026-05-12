<template>
  <div class="gt-import-history">
    <!-- 页头 -->
    <div class="gt-ih-header">
      <div class="gt-ih-header__left">
        <el-button text size="small" @click="goBack">← 返回账簿查询</el-button>
        <h3>导入历史</h3>
      </div>
      <div class="gt-ih-header__right">
        <el-select v-model="selectedYear" size="small" style="width: 100px" @change="loadAll">
          <el-option v-for="y in yearOptions" :key="y" :value="y" :label="`${y}年`" />
        </el-select>
        <el-button size="small" @click="loadAll" :loading="loading">刷新</el-button>
      </div>
    </div>

    <!-- 当前状态卡片 -->
    <div class="gt-ih-status-cards">
      <div class="gt-ih-card">
        <div class="gt-ih-card__label">当前活跃数据集</div>
        <div class="gt-ih-card__value" :class="{ 'gt-ih-card__value--ok': activeDatasetId }">
          {{ activeDatasetId ? '已激活' : '无' }}
        </div>
      </div>
      <div class="gt-ih-card">
        <div class="gt-ih-card__label">导入作业</div>
        <div class="gt-ih-card__value">{{ jobs.length }} 个</div>
      </div>
      <div class="gt-ih-card">
        <div class="gt-ih-card__label">数据集版本</div>
        <div class="gt-ih-card__value">{{ datasets.length }} 个</div>
      </div>
      <div class="gt-ih-card" v-if="latestJob">
        <div class="gt-ih-card__label">最近导入</div>
        <div class="gt-ih-card__value gt-ih-card__value--small">
          <el-tag :type="jobTagType(latestJob.status) || undefined" size="small">{{ latestJob.status }}</el-tag>
          <span v-if="latestJob.progress_pct != null" style="margin-left: 4px">{{ latestJob.progress_pct }}%</span>
        </div>
      </div>
    </div>

    <!-- 错误提示 -->
    <el-alert v-if="loadError" type="error" :closable="true" style="margin-bottom: 12px" show-icon>
      <template #title>加载失败</template>
      {{ loadError }}
    </el-alert>

    <!-- Tab 内容 -->
    <el-tabs v-model="activeTab">
      <!-- 导入作业 -->
      <el-tab-pane label="导入作业" name="jobs">
        <el-empty v-if="!loading && jobs.length === 0" description="暂无导入作业记录" />
        <el-table v-else :data="jobs" v-loading="loading" border size="small" style="width: 100%">
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="jobTagType(row.status) || undefined" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="progress_pct" label="进度" width="160">
            <template #default="{ row }">
              <el-progress :percentage="Math.max(0, Math.min(row.progress_pct || 0, 100))" :stroke-width="14" />
            </template>
          </el-table-column>
          <el-table-column prop="progress_message" label="阶段" min-width="200" show-overflow-tooltip />
          <el-table-column prop="created_by_name" label="导入人" width="100" />
          <el-table-column prop="created_at" label="创建时间" width="170">
            <template #default="{ row }"><span class="gt-amt">{{ fmtTime(row.created_at) }}</span></template>
          </el-table-column>
          <el-table-column prop="error_message" label="错误信息" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.error_message" style="color: #f56c6c">{{ row.error_message }}</span>
              <span v-else style="color: #999">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button v-if="['failed', 'timed_out'].includes(row.status)" size="small" @click="retry(row)">重试</el-button>
              <el-button v-if="['pending', 'queued', 'running', 'validating', 'writing', 'activating'].includes(row.status)" size="small" type="danger" @click="cancel(row)">取消</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 数据集版本 -->
      <el-tab-pane label="数据集版本" name="datasets">
        <el-empty v-if="!loading && datasets.length === 0" description="暂无数据集版本" />
        <el-table v-else :data="datasets" v-loading="loading" border size="small" style="width: 100%">
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="datasetTagType(row.status) || undefined" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="id" label="ID" width="120" show-overflow-tooltip>
            <template #default="{ row }"><span class="gt-amt">{{ row.id?.slice(0, 8) }}...</span></template>
          </el-table-column>
          <el-table-column prop="record_summary" label="数据量" min-width="240">
            <template #default="{ row }">{{ formatRecordSummary(row.record_summary) }}</template>
          </el-table-column>
          <el-table-column prop="activated_at" label="激活时间" width="170">
            <template #default="{ row }"><span class="gt-amt">{{ fmtTime(row.activated_at) }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'active' && row.previous_dataset_id"
                size="small" type="warning" @click="rollback(row)"
              >回滚</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 激活记录 -->
      <el-tab-pane label="激活记录" name="records">
        <el-empty v-if="!loading && records.length === 0" description="暂无激活/回滚记录" />
        <el-table v-else :data="records" v-loading="loading" border size="small" style="width: 100%">
          <el-table-column prop="action" label="动作" width="100">
            <template #default="{ row }">
              <el-tag :type="row.action === 'activate' ? 'success' : row.action === 'rollback' ? 'warning' : 'info'" size="small">
                {{ row.action === 'activate' ? '激活' : row.action === 'rollback' ? '回滚' : row.action }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="dataset_id" label="数据集" width="120" show-overflow-tooltip>
            <template #default="{ row }"><span class="gt-amt">{{ row.dataset_id?.slice(0, 8) }}...</span></template>
          </el-table-column>
          <el-table-column prop="performed_at" label="时间" width="170">
            <template #default="{ row }"><span class="gt-amt">{{ fmtTime(row.performed_at) }}</span></template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="240" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { confirmDangerous } from '@/utils/confirm'
import {
  cancelImportJob,
  getActiveLedgerDataset,
  listActivationRecords,
  listImportJobs,
  listLedgerDatasets,
  retryImportJob,
  rollbackLedgerDataset,
  type ImportJob,
  type LedgerDataset,
} from '@/services/ledgerImportApi'
import { IMPORT_JOB_STATUS } from '@/constants/statusEnum'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const selectedYear = ref(Number(route.query.year) || new Date().getFullYear())
const yearOptions = Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i)
const loading = ref(false)
const loadError = ref('')
const activeTab = ref('jobs')
const activeDatasetId = ref<string | null>(null)
const datasets = ref<LedgerDataset[]>([])
const jobs = ref<ImportJob[]>([])
const records = ref<any[]>([])

const latestJob = computed(() => jobs.value[0] || null)

function goBack() {
  router.push({ path: `/projects/${projectId.value}/ledger`, query: { year: String(selectedYear.value) } })
}

function fmtTime(v: string | null | undefined) {
  if (!v) return '—'
  try { return new Date(v).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }
  catch { return v }
}

function formatRecordSummary(summary: Record<string, unknown> | null | undefined) {
  if (!summary) return '—'
  const parts: string[] = []
  if (summary.tb_balance) parts.push(`余额 ${summary.tb_balance}`)
  if (summary.tb_aux_balance) parts.push(`辅助余额 ${summary.tb_aux_balance}`)
  if (summary.tb_ledger) parts.push(`序时账 ${summary.tb_ledger}`)
  if (summary.tb_aux_ledger) parts.push(`辅助明细 ${summary.tb_aux_ledger}`)
  return parts.length > 0 ? parts.join(' / ') : JSON.stringify(summary).slice(0, 60)
}

function datasetTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'active') return 'success'
  if (status === 'failed' || status === 'rolled_back') return 'danger'
  if (status === 'staged') return 'warning'
  return 'info'
}

function jobTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  if (status === IMPORT_JOB_STATUS.COMPLETED) return 'success'
  if (status === IMPORT_JOB_STATUS.FAILED || status === IMPORT_JOB_STATUS.TIMED_OUT || status === IMPORT_JOB_STATUS.CANCELED) return 'danger'
  if (status === IMPORT_JOB_STATUS.RUNNING || status === 'writing' || status === 'activating') return 'warning'
  return 'info'
}

async function loadAll() {
  if (!projectId.value) return
  loading.value = true
  loadError.value = ''
  try {
    const results = await Promise.allSettled([
      getActiveLedgerDataset(projectId.value, selectedYear.value),
      listLedgerDatasets(projectId.value, selectedYear.value),
      listImportJobs(projectId.value, selectedYear.value),
      listActivationRecords(projectId.value, selectedYear.value),
    ])
    // 逐个处理，单个失败不影响其他
    if (results[0].status === 'fulfilled') {
      activeDatasetId.value = (results[0].value as any)?.active_dataset_id ?? null
    }
    if (results[1].status === 'fulfilled') {
      datasets.value = (results[1].value as LedgerDataset[]) ?? []
    }
    if (results[2].status === 'fulfilled') {
      jobs.value = (results[2].value as ImportJob[]) ?? []
    }
    if (results[3].status === 'fulfilled') {
      records.value = (results[3].value as any[]) ?? []
    }
    // 收集错误
    const errors = results.filter(r => r.status === 'rejected').map(r => (r as PromiseRejectedResult).reason?.message || '未知错误')
    if (errors.length > 0) {
      loadError.value = errors.join('; ')
    }
  } finally {
    loading.value = false
  }
}

async function rollback(row: LedgerDataset) {
  await confirmDangerous('确认回滚到上一版本？回滚后依赖该数据的底稿/报表将标记为"数据过期"。', '回滚确认')
  try {
    await rollbackLedgerDataset(projectId.value, row.id, selectedYear.value, '用户从导入历史发起回滚')
    ElMessage.success('回滚成功')
    await loadAll()
  } catch (err: any) {
    const detail = err?.detail || err?.response?.data?.message
    if (err?.response?.status === 409) {
      ElMessageBox.alert('无法回滚：已有签字报表绑定了当前数据集。如需强制回滚请联系管理员。', '回滚被拒绝', { type: 'error' })
    } else {
      handleApiError(err, '回滚数据集')
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
.gt-import-history {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 400px;
}

.gt-ih-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--gt-space-4);
}
.gt-ih-header__left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.gt-ih-header__left h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--gt-color-primary-dark, #4b2d77);
}
.gt-ih-header__right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-ih-status-cards {
  display: flex;
  gap: 12px;
  margin-bottom: var(--gt-space-4);
}
.gt-ih-card {
  flex: 1;
  padding: 12px 16px;
  background: #f8f7fc;
  border: 1px solid #e8e4f0;
  border-radius: 8px;
}
.gt-ih-card__label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.gt-ih-card__value {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.gt-ih-card__value--ok {
  color: #67c23a;
}
.gt-ih-card__value--small {
  font-size: 13px;
}

.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

:deep(.el-table .el-table__cell) {
  font-size: 13px;
}
</style>
