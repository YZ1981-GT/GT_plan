<template>
  <div class="qc-inspection-workbench">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner gt-page-banner--teal">
      <div class="gt-banner-content">
        <h2>🔍 质控抽查工作台</h2>
        <span class="gt-banner-sub">
          共 {{ batches.length }} 个抽查批次
        </span>
      </div>
      <div class="gt-banner-actions">
        <el-button size="small" type="primary" @click="showNewInspection = true">新建抽查</el-button>
        <el-button size="small" type="success" @click="generateReport" :loading="generatingReport" :disabled="!selectedBatch">
          📄 生成质控报告
        </el-button>
        <el-button size="small" @click="loadBatches" :loading="loadingBatches">刷新</el-button>
      </div>
    </div>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" class="workbench-tabs">
      <el-tab-pane label="抽查工作台" name="inspection">
        <!-- 两栏布局 -->
        <div class="workbench-layout">
          <!-- 左侧：批次列表 -->
          <div class="workbench-left">
            <el-table
              :data="batches"
              v-loading="loadingBatches"
              stripe
              highlight-current-row
              @current-change="onBatchSelect"
              style="width: 100%;"
            >
              <el-table-column label="项目" prop="project_name" min-width="140" />
              <el-table-column label="策略" prop="strategy" width="100" align="center">
                <template #default="{ row }">
                  <el-tag size="small">{{ strategyLabel(row.strategy) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="创建时间" prop="created_at" width="160">
                <template #default="{ row }">
                  {{ formatDate(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="状态" prop="status" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row.status)" size="small">
                    {{ statusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 右侧：抽查项列表 -->
          <div class="workbench-right">
            <div v-if="!selectedBatch" class="empty-hint">
              <el-empty description="请在左侧选择一个抽查批次" />
            </div>
            <div v-else>
              <h3 style="margin: 0 0 12px 0;">
                抽查项 — {{ selectedBatch.project_name }}
              </h3>
              <el-table
                :data="items"
                v-loading="loadingItems"
                stripe
                style="width: 100%;"
              >
                <el-table-column label="底稿编号" prop="wp_code" width="120">
                  <template #default="{ row }">
                    <span style="font-family: monospace; color: #409eff;">{{ row.wp_code }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="底稿名称" prop="wp_name" min-width="200" />
                <el-table-column label="结论" prop="verdict" width="130" align="center">
                  <template #default="{ row }">
                    <el-tag :type="verdictTagType(row.verdict)" size="small" effect="dark">
                      {{ verdictLabel(row.verdict) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="120" align="center">
                  <template #default="{ row }">
                    <el-button size="small" type="primary" link @click="openVerdictDialog(row)">
                      录入结论
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="日志合规抽查" name="audit-log">
        <!-- 日志合规抽查内容 -->
        <div class="audit-log-section">
          <div class="audit-log-toolbar">
            <el-button type="primary" size="small" @click="runAuditLogScan" :loading="scanLoading">
              执行扫描
            </el-button>
            <el-button size="small" @click="loadAuditLogFindings" :loading="auditLogLoading">
              刷新
            </el-button>
            <span class="audit-log-count" v-if="auditLogFindings.length > 0">
              共 {{ auditLogTotal }} 条命中
            </span>
          </div>

          <el-table
            :data="auditLogFindings"
            v-loading="auditLogLoading"
            stripe
            style="width: 100%; margin-top: 12px;"
          >
            <el-table-column label="时间" prop="ts" width="160">
              <template #default="{ row }">
                {{ formatDate(row.ts) }}
              </template>
            </el-table-column>
            <el-table-column label="用户" prop="user_name" width="100">
              <template #default="{ row }">
                {{ row.user_name || row.user_id || '—' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" prop="action_type" width="140" />
            <el-table-column label="规则" prop="rule_code" width="90">
              <template #default="{ row }">
                <span style="font-family: monospace; font-weight: 600;">{{ row.rule_code }}</span>
              </template>
            </el-table-column>
            <el-table-column label="严重程度" prop="severity" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="severityTagType(row.severity)" size="small" effect="dark">
                  {{ severityLabel(row.severity) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="详情" prop="message" min-width="200" show-overflow-tooltip />
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag
                  :type="row.review_status === 'reviewed' ? 'success' : (row.review_status === 'escalated' ? 'danger' : 'info')"
                  size="small"
                >
                  {{ reviewStatusLabel(row.review_status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.review_status === 'pending'"
                  size="small"
                  type="success"
                  link
                  @click="markAsReviewed(row)"
                >
                  标记已处理
                </el-button>
                <span v-else style="color: #67c23a; font-size: 12px;">✓ 已处理</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 录入结论对话框 -->
    <el-dialog v-model="verdictDialogVisible" title="录入抽查结论" width="500px">
      <el-form :model="verdictForm" label-width="80px">
        <el-form-item label="底稿">
          <span>{{ verdictForm.wp_code }} — {{ verdictForm.wp_name }}</span>
        </el-form-item>
        <el-form-item label="结论">
          <el-select v-model="verdictForm.verdict" style="width: 100%;">
            <el-option label="通过" value="pass" />
            <el-option label="不通过" value="fail" />
            <el-option label="有条件通过" value="conditional_pass" />
          </el-select>
        </el-form-item>
        <el-form-item label="发现">
          <el-input
            v-model="verdictForm.findings"
            type="textarea"
            :rows="4"
            placeholder="请描述检查发现..."
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="verdictDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitVerdict" :loading="submittingVerdict">确定</el-button>
      </template>
    </el-dialog>

    <!-- 新建抽查对话框 -->
    <el-dialog v-model="showNewInspection" title="新建抽查" width="500px">
      <el-form :model="newForm" label-width="80px">
        <el-form-item label="项目">
          <el-input v-model="newForm.project_name" placeholder="输入项目名称" />
        </el-form-item>
        <el-form-item label="策略">
          <el-select v-model="newForm.strategy" style="width: 100%;">
            <el-option label="随机抽样" value="random" />
            <el-option label="风险导向" value="risk_based" />
            <el-option label="全周期" value="full_cycle" />
            <el-option label="混合" value="mixed" />
          </el-select>
        </el-form-item>
        <el-form-item label="复核人">
          <el-input v-model="newForm.reviewer" placeholder="复核人姓名" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showNewInspection = false">取消</el-button>
        <el-button type="primary" @click="createInspection" :loading="creating">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ──────────────────────────────────────────────────────────────────

interface InspectionBatch {
  id: string
  project_name: string
  strategy: string
  created_at: string
  status: string
}

interface InspectionItem {
  id: string
  wp_code: string
  wp_name: string
  verdict: string
}

interface AuditLogFinding {
  id: string
  entry_id: string
  ts: string
  action_type: string
  user_id: string
  user_name: string
  ip: string
  rule_code: string
  rule_title: string
  severity: string
  message: string
  review_status: string
  reviewed_by: string | null
  reviewed_at: string | null
}

// ─── State ──────────────────────────────────────────────────────────────────

const activeTab = ref('inspection')

// Inspection tab state
const batches = ref<InspectionBatch[]>([])
const items = ref<InspectionItem[]>([])
const selectedBatch = ref<InspectionBatch | null>(null)
const loadingBatches = ref(false)
const loadingItems = ref(false)

// Verdict dialog
const verdictDialogVisible = ref(false)
const submittingVerdict = ref(false)
const verdictForm = ref({
  item_id: '',
  wp_code: '',
  wp_name: '',
  verdict: 'pass',
  findings: '',
})

// New inspection dialog
const showNewInspection = ref(false)
const creating = ref(false)
const generatingReport = ref(false)
const newForm = ref({
  project_name: '',
  strategy: 'random',
  reviewer: '',
})

// Audit log tab state
const auditLogFindings = ref<AuditLogFinding[]>([])
const auditLogTotal = ref(0)
const auditLogLoading = ref(false)
const scanLoading = ref(false)

// ─── Helpers ────────────────────────────────────────────────────────────────

function strategyLabel(s: string): string {
  const map: Record<string, string> = {
    random: '随机',
    risk_based: '风险导向',
    full_cycle: '全周期',
    mixed: '混合',
  }
  return map[s] || s
}

function statusTagType(status: string): 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case 'completed': return 'success'
    case 'in_progress': return 'warning'
    case 'pending': return 'info'
    default: return 'info'
  }
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    completed: '已完成',
    in_progress: '进行中',
    pending: '待处理',
  }
  return map[status] || status
}

function verdictTagType(verdict: string): 'success' | 'danger' | 'warning' | 'info' {
  switch (verdict) {
    case 'pass': return 'success'
    case 'fail': return 'danger'
    case 'conditional_pass': return 'warning'
    default: return 'info'
  }
}

function verdictLabel(verdict: string): string {
  const map: Record<string, string> = {
    pass: '通过',
    fail: '不通过',
    conditional_pass: '有条件通过',
    pending: '待检查',
  }
  return map[verdict] || verdict
}

function severityTagType(severity: string): 'danger' | 'warning' | 'info' | 'success' {
  switch (severity) {
    case 'blocking': return 'danger'
    case 'warning': return 'warning'
    case 'info': return 'info'
    default: return 'info'
  }
}

function severityLabel(severity: string): string {
  const map: Record<string, string> = {
    blocking: '阻断',
    warning: '警告',
    info: '提示',
  }
  return map[severity] || severity
}

function reviewStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待处理',
    reviewed: '已审查',
    escalated: '已上报',
  }
  return map[status] || status
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '—'
  return dateStr.replace('T', ' ').slice(0, 16)
}

// ─── Inspection Tab Data Loading ────────────────────────────────────────────

async function loadBatches() {
  loadingBatches.value = true
  try {
    const data = await api.get<any>('/api/qc/inspections')
    if (Array.isArray(data)) {
      batches.value = data
    } else if (data && Array.isArray(data.items)) {
      batches.value = data.items
    } else {
      batches.value = []
    }
  } catch {
    batches.value = []
  } finally {
    loadingBatches.value = false
  }
}

async function onBatchSelect(batch: InspectionBatch | null) {
  selectedBatch.value = batch
  if (!batch) {
    items.value = []
    return
  }
  loadingItems.value = true
  try {
    const data = await api.get<any>(`/api/qc/inspections/${batch.id}`)
    items.value = data.items || data || []
  } catch {
    items.value = []
  } finally {
    loadingItems.value = false
  }
}

function openVerdictDialog(item: InspectionItem) {
  verdictForm.value = {
    item_id: item.id,
    wp_code: item.wp_code,
    wp_name: item.wp_name,
    verdict: item.verdict === 'pending' ? 'pass' : item.verdict,
    findings: '',
  }
  verdictDialogVisible.value = true
}

async function submitVerdict() {
  if (!selectedBatch.value) return
  submittingVerdict.value = true
  try {
    await api.post(
      `/api/qc/inspections/${selectedBatch.value.id}/items/${verdictForm.value.item_id}/verdict`,
      {
        verdict: verdictForm.value.verdict,
        findings: verdictForm.value.findings,
      }
    )
    ElMessage.success('结论已录入')
    verdictDialogVisible.value = false
    // Reload items
    await onBatchSelect(selectedBatch.value)
  } catch {
    ElMessage.error('录入失败')
  } finally {
    submittingVerdict.value = false
  }
}

async function createInspection() {
  creating.value = true
  try {
    await api.post('/api/qc/inspections', {
      project_name: newForm.value.project_name,
      strategy: newForm.value.strategy,
      reviewer: newForm.value.reviewer,
    })
    ElMessage.success('抽查已创建')
    showNewInspection.value = false
    newForm.value = { project_name: '', strategy: 'random', reviewer: '' }
    await loadBatches()
  } catch {
    ElMessage.error('创建失败')
  } finally {
    creating.value = false
  }
}

// ─── Audit Log Tab Data Loading ─────────────────────────────────────────────

async function loadAuditLogFindings() {
  auditLogLoading.value = true
  try {
    const data = await api.get<any>('/api/qc/audit-log-compliance/findings')
    if (data && Array.isArray(data.items)) {
      auditLogFindings.value = data.items
      auditLogTotal.value = data.total || data.items.length
    } else if (Array.isArray(data)) {
      auditLogFindings.value = data
      auditLogTotal.value = data.length
    } else {
      auditLogFindings.value = []
      auditLogTotal.value = 0
    }
  } catch {
    auditLogFindings.value = []
    auditLogTotal.value = 0
  } finally {
    auditLogLoading.value = false
  }
}

async function runAuditLogScan() {
  scanLoading.value = true
  try {
    const result = await api.post<any>('/api/qc/audit-log-compliance/run', {
      time_window_hours: 720,
    })
    ElMessage.success(result.message || '扫描完成')
    // 刷新列表
    await loadAuditLogFindings()
  } catch {
    ElMessage.error('扫描执行失败')
  } finally {
    scanLoading.value = false
  }
}

async function markAsReviewed(finding: AuditLogFinding) {
  try {
    await api.patch(`/api/qc/audit-log-compliance/findings/${finding.id}/status`, {
      status: 'reviewed',
    })
    finding.review_status = 'reviewed'
    ElMessage.success('已标记为已处理')
  } catch {
    ElMessage.error('标记失败')
  }
}

async function generateReport() {
  if (!selectedBatch.value) return
  generatingReport.value = true
  try {
    const response = await import('@/utils/http').then(m =>
      m.default.get(`/api/qc/inspections/${selectedBatch.value!.id}/report`, { responseType: 'blob' })
    )
    const blob = new Blob([response.data])
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `质控抽查报告_${selectedBatch.value.project_name || 'report'}.docx`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('质控报告已生成')
  } catch {
    ElMessage.error('报告生成失败，请确认抽查已完成')
  } finally {
    generatingReport.value = false
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  loadBatches()
  loadAuditLogFindings()
})
</script>

<style scoped>
.qc-inspection-workbench {
  padding: 0;
}

.workbench-tabs {
  padding: 0 16px;
}

.workbench-layout {
  display: flex;
  gap: 16px;
  padding: 16px 0;
  min-height: 500px;
}

.workbench-left {
  width: 40%;
  min-width: 300px;
}

.workbench-right {
  width: 60%;
  flex: 1;
}

.empty-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 300px;
}

.audit-log-section {
  padding: 16px 0;
}

.audit-log-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.audit-log-count {
  color: #909399;
  font-size: 13px;
  margin-left: 8px;
}
</style>
