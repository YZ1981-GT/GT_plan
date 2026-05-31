<template>
  <div class="gt-rcb gt-fade-in">
    <GtPageHeader title="报表配置主模板管理" :show-back="true" back-mode="history" />

    <!-- stale 提示 banner -->
    <div v-if="staleInfo.is_stale" class="rcb-stale-banner">
      <div class="rcb-stale-content">
        <span class="rcb-stale-icon">⚠️</span>
        <span>主模板已更新，当前项目有 <strong>{{ staleInfo.stale_count }}</strong> 行配置与主模板不同步</span>
      </div>
      <div class="rcb-stale-actions">
        <el-button size="small" type="primary" plain @click="showDiffDialog = true">
          查看差异
        </el-button>
        <el-button size="small" type="primary" @click="onApplyMasterUpdate">
          同步主模板更新
        </el-button>
      </div>
    </div>

    <!-- Tab 切换：项目配置 / 候选审核（admin） -->
    <el-tabs v-model="activeTab">
      <el-tab-pane label="项目配置" name="project">
        <!-- 工具栏 -->
        <div class="rcb-toolbar">
          <el-select v-model="selectedStandard" size="small" style="width: 140px" @change="loadProjectConfigs">
            <el-option label="国企版合并" value="soe_consolidated" />
            <el-option label="国企版单体" value="soe_standalone" />
            <el-option label="上市版合并" value="listed_consolidated" />
            <el-option label="上市版单体" value="listed_standalone" />
          </el-select>
          <el-select v-model="selectedReportType" size="small" style="width: 130px" @change="loadProjectConfigs">
            <el-option label="资产负债表" value="balance_sheet" />
            <el-option label="利润表" value="income_statement" />
            <el-option label="现金流量表" value="cash_flow_statement" />
            <el-option label="权益变动表" value="equity_statement" />
          </el-select>
          <el-tag type="info" size="small" effect="plain">{{ projectRows.length }} 行</el-tag>
        </div>

        <!-- 项目配置表格 -->
        <el-table
          :data="projectRows"
          v-loading="loadingProject"
          border
          size="small"
          style="width: 100%"
          :header-cell-style="{ background: '#f0edf5', fontWeight: '600' }"
        >
          <el-table-column prop="row_code" label="行次编码" width="120" />
          <el-table-column prop="row_name" label="项目名称" min-width="200" />
          <el-table-column prop="formula" label="公式" min-width="240">
            <template #default="{ row }">
              <span class="rcb-formula">{{ row.formula || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" align="center">
            <template #default="{ row }">
              <el-button
                size="small"
                link
                type="primary"
                @click="onSuggestToMaster(row)"
                :disabled="!row.formula"
              >
                提交主模板候选
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- admin 审核候选列表 -->
      <el-tab-pane v-if="isAdmin" label="候选审核" name="review">
        <div class="rcb-toolbar">
          <el-select v-model="candidateFilter" size="small" style="width: 120px" @change="loadCandidates">
            <el-option label="待审核" value="pending" />
            <el-option label="已通过" value="approved" />
            <el-option label="已驳回" value="rejected" />
          </el-select>
          <el-tag type="info" size="small" effect="plain">{{ candidates.length }} 条</el-tag>
        </div>

        <el-table
          :data="candidates"
          v-loading="loadingCandidates"
          border
          size="small"
          style="width: 100%"
          :header-cell-style="{ background: '#f0edf5', fontWeight: '600' }"
        >
          <el-table-column prop="standard" label="标准" width="140" />
          <el-table-column prop="report_type" label="报表类型" width="130" />
          <el-table-column prop="row_code" label="行次编码" width="120" />
          <el-table-column prop="candidate_formula" label="候选公式" min-width="240">
            <template #default="{ row }">
              <span class="rcb-formula">{{ row.candidate_formula || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" align="center">
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <el-button size="small" link type="success" @click="onReview(row, true)">通过</el-button>
                <el-button size="small" link type="danger" @click="onReview(row, false)">驳回</el-button>
              </template>
              <span v-else class="rcb-reviewed">已处理</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 差异对话框 -->
    <el-dialog v-model="showDiffDialog" title="项目 vs 主模板差异" width="720px">
      <el-table :data="diffRows" border size="small" v-loading="loadingDiff">
        <el-table-column prop="row_code" label="行次编码" width="120" />
        <el-table-column prop="report_type" label="报表类型" width="130" />
        <el-table-column prop="project_formula" label="项目公式" min-width="180">
          <template #default="{ row }">
            <span class="rcb-formula">{{ row.project_formula || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="master_formula" label="主模板公式" min-width="180">
          <template #default="{ row }">
            <span class="rcb-formula">{{ row.master_formula || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="diff_type" label="差异类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="diffTagType(row.diff_type)" size="small">
              {{ diffLabel(row.diff_type) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="showDiffDialog = false">关闭</el-button>
        <el-button type="primary" @click="onApplyMasterUpdate">选择性同步</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'
import { useAuthStore } from '@/stores/auth'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const authStore = useAuthStore()
const isAdmin = computed(() => (authStore.user?.role || '') === 'admin')

const projectId = computed(() => route.params.projectId as string || '')

// --- Tab ---
const activeTab = ref('project')

// --- 项目配置 ---
const selectedStandard = ref('soe_standalone')
const selectedReportType = ref('balance_sheet')
const projectRows = ref<any[]>([])
const loadingProject = ref(false)

async function loadProjectConfigs() {
  if (!projectId.value) return
  loadingProject.value = true
  try {
    const data = await api.get(P.reportConfig.list, {
      params: {
        report_type: selectedReportType.value,
        project_id: projectId.value,
      },
    })
    projectRows.value = Array.isArray(data) ? data : []
  } catch {
    projectRows.value = []
  } finally {
    loadingProject.value = false
  }
}

// --- stale 状态 ---
const staleInfo = ref<{ is_stale: boolean; stale_count: number }>({ is_stale: false, stale_count: 0 })

async function loadStaleStatus() {
  if (!projectId.value) return
  try {
    const data = await api.get(P.reportConfig.staleStatus(projectId.value))
    staleInfo.value = data
  } catch {
    staleInfo.value = { is_stale: false, stale_count: 0 }
  }
}

// --- 提交主模板候选 ---
async function onSuggestToMaster(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认将行次 ${row.row_code} 的公式提交为主模板候选？`,
      '提交主模板候选',
      { confirmButtonText: '确认提交', cancelButtonText: '取消', type: 'info' },
    )
    await api.post(P.reportConfig.suggestToMaster, {
      project_id: projectId.value,
      row_code: row.row_code,
      report_type: selectedReportType.value,
      standard: selectedStandard.value,
      candidate_formula: row.formula,
    })
    ElMessage.success('已提交主模板候选，等待 admin 审核')
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      handleApiError(e, '提交候选')
    }
  }
}

// --- 差异对话框 ---
const showDiffDialog = ref(false)
const diffRows = ref<any[]>([])
const loadingDiff = ref(false)

async function loadDiff() {
  if (!projectId.value) return
  loadingDiff.value = true
  try {
    const data = await api.get(P.reportConfig.diffVsMaster(projectId.value), {
      params: { standard: selectedStandard.value },
    })
    diffRows.value = data?.diffs || []
  } catch {
    diffRows.value = []
  } finally {
    loadingDiff.value = false
  }
}

// 打开差异对话框时加载
import { watch } from 'vue'
watch(showDiffDialog, (val) => {
  if (val) loadDiff()
})

// --- 同步主模板更新 ---
async function onApplyMasterUpdate() {
  try {
    await ElMessageBox.confirm(
      '确认同步主模板更新到当前项目？已自定义的行将保留本地覆盖。',
      '同步主模板更新',
      { confirmButtonText: '确认同步', cancelButtonText: '取消', type: 'warning' },
    )
    const data = await api.post(P.reportConfig.applyMasterUpdate, {
      project_id: projectId.value,
      standard: selectedStandard.value,
      keep_local: true,
    })
    ElMessage.success(data?.message || '同步完成')
    showDiffDialog.value = false
    await loadStaleStatus()
    await loadProjectConfigs()
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      handleApiError(e, '同步')
    }
  }
}

// --- 候选审核（admin） ---
const candidateFilter = ref('pending')
const candidates = ref<any[]>([])
const loadingCandidates = ref(false)

async function loadCandidates() {
  loadingCandidates.value = true
  try {
    const data = await api.get(P.reportConfig.candidates, {
      params: { status: candidateFilter.value },
    })
    candidates.value = Array.isArray(data) ? data : []
  } catch {
    candidates.value = []
  } finally {
    loadingCandidates.value = false
  }
}

async function onReview(row: any, approved: boolean) {
  const action = approved ? '通过' : '驳回'
  try {
    await ElMessageBox.confirm(
      `确认${action}行次 ${row.row_code} 的候选公式？`,
      `审核${action}`,
      { confirmButtonText: `确认${action}`, cancelButtonText: '取消', type: approved ? 'success' : 'warning' },
    )
    await api.post(P.reportConfig.reviewCandidate, {
      candidate_id: row.id,
      approved,
    })
    ElMessage.success(`候选已${action}`)
    await loadCandidates()
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      handleApiError(e, '审核')
    }
  }
}

// --- 辅助函数 ---
function statusTagType(status: string) {
  if (status === 'pending') return 'warning'
  if (status === 'approved') return 'success'
  if (status === 'rejected') return 'danger'
  return 'info'
}

function statusLabel(status: string) {
  if (status === 'pending') return '待审核'
  if (status === 'approved') return '已通过'
  if (status === 'rejected') return '已驳回'
  return status
}

function diffTagType(diffType: string) {
  if (diffType === 'modified') return 'warning'
  if (diffType === 'project_only') return 'info'
  if (diffType === 'master_only') return 'danger'
  return ''
}

function diffLabel(diffType: string) {
  if (diffType === 'modified') return '已修改'
  if (diffType === 'project_only') return '仅项目'
  if (diffType === 'master_only') return '仅主模板'
  return diffType
}

// --- 初始化 ---
onMounted(async () => {
  await loadProjectConfigs()
  await loadStaleStatus()
  if (isAdmin.value) {
    await loadCandidates()
  }
})
</script>

<style scoped>
.gt-rcb {
  padding: 16px 20px;
}

/* stale banner */
.rcb-stale-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: var(--gt-bg-warning, #fdf6ec);
  border: 1px solid var(--gt-color-border-warning, #e6a23c);
  border-radius: 8px;
}
.rcb-stale-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.rcb-stale-icon {
  font-size: 18px;
}
.rcb-stale-actions {
  display: flex;
  gap: 8px;
}

/* 工具栏 */
.rcb-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  margin-bottom: 8px;
}

/* 公式单元格 */
.rcb-formula {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: var(--gt-color-teal, #0d9488);
  word-break: break-all;
}

/* 已处理标记 */
.rcb-reviewed {
  color: var(--gt-color-info, #909399);
  font-size: 12px;
}
</style>
