<template>
  <div class="qc-dashboard">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner gt-page-banner--teal">
      <div class="gt-banner-content">
        <h2>🔍 质控看板</h2>
        <span class="gt-banner-sub" v-if="overview">
          QC 通过率 {{ overview.qc_pass_rate }}% · {{ overview.qc_passed }}/{{ overview.qc_checked }} 通过
        </span>
      </div>
      <div class="gt-banner-actions">
        <el-button size="small" @click="loadAll" :loading="loading">刷新</el-button>
        <el-button size="small" @click="activeTab = 'archive'">📦 归档检查</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <!-- Tab 1: QC 总览 -->
      <el-tab-pane label="质量总览" name="overview">
        <div v-if="overview" class="gt-stat-cards">
          <div class="gt-stat-card gt-stat-card--success">
            <div class="gt-stat-num">{{ overview.qc_passed }}</div>
            <div class="gt-stat-label">QC 通过</div>
          </div>
          <div class="gt-stat-card gt-stat-card--danger">
            <div class="gt-stat-num">{{ overview.qc_blocking }}</div>
            <div class="gt-stat-label">有阻断问题</div>
          </div>
          <div class="gt-stat-card gt-stat-card--muted">
            <div class="gt-stat-num">{{ overview.qc_not_checked }}</div>
            <div class="gt-stat-label">未自检</div>
          </div>
          <div class="gt-stat-card gt-stat-card--primary">
            <div class="gt-stat-num">{{ overview.total }}</div>
            <div class="gt-stat-label">底稿总数</div>
          </div>
        </div>

        <!-- 复核状态分布 -->
        <div class="section" v-if="overview">
          <h3>复核状态分布</h3>
          <div class="review-dist">
            <div v-for="(count, status) in overview.review_distribution" :key="status" class="dist-item">
              <el-tag :type="reviewTagType(status)" size="small">{{ reviewLabel(status) }}</el-tag>
              <span class="dist-count">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- 最近 QC 失败 -->
        <div class="section" v-if="overview?.recent_failures?.length">
          <h3>最近 QC 未通过的底稿</h3>
          <el-table :data="overview.recent_failures" stripe size="small">
            <el-table-column label="底稿ID" prop="wp_id" width="120">
              <template #default="{ row }">{{ row.wp_id?.slice(0, 8) }}...</template>
            </el-table-column>
            <el-table-column label="阻断" prop="blocking_count" width="60" />
            <el-table-column label="警告" prop="warning_count" width="60" />
            <el-table-column label="检查时间" width="160">
              <template #default="{ row }">{{ row.check_time ? new Date(row.check_time).toLocaleString('zh-CN') : '-' }}</template>
            </el-table-column>
            <el-table-column label="首要问题" min-width="200">
              <template #default="{ row }">{{ row.findings?.[0]?.message || '-' }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 人员进度 -->
      <el-tab-pane label="人员进度" name="staff">
        <el-table :data="staffProgress" stripe v-loading="staffLoading">
          <el-table-column label="人员" prop="user_name" width="120" />
          <el-table-column label="分配" prop="total" width="60" align="center" />
          <el-table-column label="已通过" width="70" align="center">
            <template #default="{ row }">
              <span style="color: #67c23a; font-weight: 600">{{ row.passed }}</span>
            </template>
          </el-table-column>
          <el-table-column label="待复核" prop="pending_review" width="70" align="center" />
          <el-table-column label="退回" width="60" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.rejected > 0 ? '#f56c6c' : '#999' }">{{ row.rejected }}</span>
            </template>
          </el-table-column>
          <el-table-column label="编制中" prop="in_progress" width="70" align="center" />
          <el-table-column label="未开始" prop="not_started" width="70" align="center" />
          <el-table-column label="完成率" width="120">
            <template #default="{ row }">
              <el-progress :percentage="row.completion_rate" :stroke-width="6" :show-text="true"
                :color="row.completion_rate >= 80 ? '#67c23a' : row.completion_rate >= 50 ? '#e6a23c' : '#f56c6c'" />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 3: 未解决意见 -->
      <el-tab-pane name="issues">
        <template #label>
          未解决意见
          <el-badge v-if="openIssueCount > 0" :value="openIssueCount" :max="99" type="danger" style="margin-left: 4px" />
        </template>
        <el-table :data="openIssues" stripe size="small" v-loading="issuesLoading">
          <el-table-column label="底稿" width="120">
            <template #default="{ row }">{{ row.wp_id?.slice(0, 8) || '-' }}...</template>
          </el-table-column>
          <el-table-column label="单元格" prop="cell_ref" width="80" />
          <el-table-column label="意见内容" prop="content" min-width="250" show-overflow-tooltip />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'open' ? 'danger' : 'warning'" size="small">
                {{ row.status === 'open' ? '待处理' : '已回复' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="提出时间" width="160">
            <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!issuesLoading && openIssues.length === 0" description="所有复核意见已解决 ✅" />
      </el-tab-pane>

      <!-- Tab 4: 归档检查 -->
      <el-tab-pane label="归档检查" name="archive">
        <div v-if="archiveResult" class="archive-panel">
          <div class="gt-check-status" :class="archiveResult.ready ? 'gt-check-status--pass' : 'gt-check-status--fail'">
            <span>{{ archiveResult.ready ? '✅' : '⚠️' }}</span>
            <span>{{ archiveResult.ready ? '项目满足归档条件' : '项目尚未满足归档条件' }}</span>
            <span class="gt-check-score">{{ archiveResult.passed_count }}/{{ archiveResult.total_checks }} 通过</span>
          </div>
          <div style="display: flex; align-items: center; justify-content: space-between; margin: 8px 0 12px">
            <span v-if="archiveResult.checked_at" style="font-size: 12px; color: #909399">
              上次检查时间：{{ new Date(archiveResult.checked_at).toLocaleString('zh-CN') }}
            </span>
            <span v-else style="font-size: 12px; color: #909399">上次检查时间：未知</span>
            <el-button size="small" type="primary" @click="loadArchive" :loading="archiveLoading">重新检查</el-button>
          </div>
          <div class="gt-check-list">
            <div v-for="check in archiveResult.checks" :key="check.id" class="gt-check-item">
              <span class="gt-check-icon">{{ check.passed ? '✅' : '❌' }}</span>
              <div>
                <div class="gt-check-label">{{ check.label }}</div>
                <div class="gt-check-detail">{{ check.detail }}</div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="archive-empty">
          <el-button type="primary" @click="loadArchive" :loading="archiveLoading">执行归档前检查</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getQCOverview, getStaffProgress, getOpenIssues, getArchiveReadiness, runArchiveReadinessCheck,
  type QCOverview, type StaffProgressItem, type OpenIssue, type ArchiveReadiness,
} from '@/services/qcDashboardApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)

const activeTab = ref('overview')
const loading = ref(false)

// Overview
const overview = ref<QCOverview | null>(null)

// Staff progress
const staffProgress = ref<StaffProgressItem[]>([])
const staffLoading = ref(false)

// Open issues
const openIssues = ref<OpenIssue[]>([])
const openIssueCount = ref(0)
const issuesLoading = ref(false)

// Archive
const archiveResult = ref<ArchiveReadiness | null>(null)
const archiveLoading = ref(false)

function reviewLabel(s: string): string {
  const m: Record<string, string> = {
    not_submitted: '未提交', pending_level1: '待一级复核', level1_in_progress: '一级复核中',
    level1_passed: '一级通过', level1_rejected: '一级退回',
    pending_level2: '待二级复核', level2_in_progress: '二级复核中',
    level2_passed: '二级通过', level2_rejected: '二级退回',
  }
  return m[s] || s
}

function reviewTagType(s: string): string {
  if (s.includes('passed')) return 'success'
  if (s.includes('rejected')) return 'danger'
  if (s.includes('pending')) return 'warning'
  return 'info'
}

async function loadOverview() {
  loading.value = true
  try { overview.value = await getQCOverview(projectId.value) } catch { ElMessage.error('加载QC总览失败') }
  finally { loading.value = false }
}

async function loadStaff() {
  staffLoading.value = true
  try {
    const result = await getStaffProgress(projectId.value)
    staffProgress.value = result.staff_progress || []
  } catch { /* ignore */ }
  finally { staffLoading.value = false }
}

async function loadIssues() {
  issuesLoading.value = true
  try {
    const result = await getOpenIssues(projectId.value)
    openIssues.value = result.issues || []
    openIssueCount.value = result.total_open || 0
  } catch { /* ignore */ }
  finally { issuesLoading.value = false }
}

async function loadArchive() {
  archiveLoading.value = true
  try { archiveResult.value = await runArchiveReadinessCheck(projectId.value) }
  catch { ElMessage.error('归档检查失败') }
  finally { archiveLoading.value = false }
}

async function tryLoadArchiveCache() {
  // 切换到归档 Tab 时，先尝试加载上次结果，失败时静默处理（不自动执行检查）
  if (archiveResult.value) return
  try {
    archiveResult.value = await getArchiveReadiness(projectId.value)
  } catch {
    // 静默处理，不自动执行检查
  }
}

watch(activeTab, (tab) => {
  if (tab === 'archive') {
    tryLoadArchiveCache()
  }
})

async function loadAll() {
  await Promise.all([loadOverview(), loadStaff(), loadIssues()])
}

onMounted(loadAll)
</script>

<style scoped>
.qc-dashboard { padding: 0; }
.section { margin-bottom: var(--gt-space-6); }
.section h3 { font-size: var(--gt-font-size-md); margin-bottom: var(--gt-space-3); color: var(--gt-color-text); }
.review-dist { display: flex; flex-wrap: wrap; gap: var(--gt-space-3); }
.dist-item { display: flex; align-items: center; gap: 6px; }
.dist-count { font-weight: 600; font-size: var(--gt-font-size-lg); color: var(--gt-color-text); }
.archive-panel { padding: var(--gt-space-4); }
.archive-empty { text-align: center; padding: var(--gt-space-10); }
</style>
