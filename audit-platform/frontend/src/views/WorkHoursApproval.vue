<template>
  <div class="gt-workhours-approval gt-fade-in">
    <!-- 页面头部 -->
    <div class="gt-page-banner">
      <div class="gt-banner-content">
        <h2>⏱️ 工时审批</h2>
        <span class="gt-banner-sub">审批下属已确认的工时记录</span>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="gt-stats-row">
      <div class="gt-stat-card gt-stat-approved">
        <div class="gt-stat-icon">✅</div>
        <div class="gt-stat-info">
          <span class="gt-stat-value">{{ stats.approvedHours }}</span>
          <span class="gt-stat-label">本周已审批（小时）</span>
        </div>
      </div>
      <div class="gt-stat-card gt-stat-pending">
        <div class="gt-stat-icon">⏳</div>
        <div class="gt-stat-info">
          <span class="gt-stat-value">{{ stats.pendingHours }}</span>
          <span class="gt-stat-label">本周未审批（小时）</span>
        </div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="gt-filter-bar">
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        style="width: 300px"
        @change="loadData"
      />
      <el-select v-model="statusFilter" placeholder="状态" style="width: 140px" @change="loadData">
        <el-option label="已确认（待审批）" value="confirmed" />
        <el-option label="已审批" value="approved" />
        <el-option label="全部" value="" />
      </el-select>
      <el-button :loading="loading" @click="loadData">刷新</el-button>
    </div>

    <!-- 批量操作栏 -->
    <div class="gt-batch-bar" v-if="selectedRows.length > 0">
      <span class="gt-batch-info">
        已选 {{ selectedRows.length }} 条（共 {{ selectedTotalHours }} 小时）
      </span>
      <el-button type="success" @click="batchApprove" :loading="batchLoading">
        批量批准
      </el-button>
      <el-button type="warning" @click="showRejectDialog = true" :loading="batchLoading">
        批量退回
      </el-button>
    </div>

    <!-- 工时表格 -->
    <el-table
      ref="tableRef"
      :data="records"
      v-loading="loading"
      stripe
      style="width: 100%"
      :header-cell-style="{ background: '#f5f7fa', fontWeight: '600' }"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="50" :selectable="isSelectable" />
      <el-table-column prop="staff_name" label="员工" min-width="120" />
      <el-table-column prop="work_date" label="日期" min-width="120" sortable />
      <el-table-column prop="project_name" label="项目" min-width="180" />
      <el-table-column prop="hours" label="小时" min-width="80" align="right" />
      <el-table-column prop="description" label="描述" min-width="220" />
      <el-table-column prop="status" label="状态" min-width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="180" align="center">
        <template #default="{ row }">
          <template v-if="row.status === 'confirmed'">
            <el-button link type="success" size="small" @click="approveOne(row)">
              批准
            </el-button>
            <el-button link type="warning" size="small" @click="rejectOne(row)">
              退回
            </el-button>
          </template>
          <span v-else class="gt-status-done">—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 退回原因弹窗（批量） -->
    <el-dialog v-model="showRejectDialog" title="退回工时" width="420px" append-to-body>
      <el-form>
        <el-form-item label="退回原因" required>
          <el-input
            v-model="rejectReason"
            type="textarea"
            :rows="3"
            placeholder="请输入退回原因，将通知员工"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRejectDialog = false">取消</el-button>
        <el-button type="warning" @click="batchReject" :loading="batchLoading">确认退回</el-button>
      </template>
    </el-dialog>

    <!-- 退回原因弹窗（单条） -->
    <el-dialog v-model="showSingleRejectDialog" title="退回工时" width="420px" append-to-body>
      <el-form>
        <el-form-item label="退回原因" required>
          <el-input
            v-model="singleRejectReason"
            type="textarea"
            :rows="3"
            placeholder="请输入退回原因，将通知员工"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSingleRejectDialog = false">取消</el-button>
        <el-button type="warning" @click="confirmSingleReject" :loading="batchLoading">确认退回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import http from '@/utils/http'

// ── 类型 ──
interface WorkHourApprovalRecord {
  id: string
  staff_id: string
  staff_name: string
  project_id: string
  project_name: string
  work_date: string
  hours: number
  description: string
  status: string
}

interface ApprovalStats {
  approvedHours: number
  pendingHours: number
}

// ── 状态 ──
const records = ref<WorkHourApprovalRecord[]>([])
const loading = ref(false)
const batchLoading = ref(false)
const selectedRows = ref<WorkHourApprovalRecord[]>([])
const tableRef = ref<any>(null)

// 筛选
const dateRange = ref<[string, string] | null>(null)
const statusFilter = ref('confirmed')

// 统计
const stats = ref<ApprovalStats>({ approvedHours: 0, pendingHours: 0 })

// 退回弹窗
const showRejectDialog = ref(false)
const rejectReason = ref('')
const showSingleRejectDialog = ref(false)
const singleRejectReason = ref('')
const singleRejectRow = ref<WorkHourApprovalRecord | null>(null)

// ── 计算 ──
const selectedTotalHours = computed(() =>
  selectedRows.value.reduce((sum, r) => sum + r.hours, 0)
)

// ── 初始化日期范围为上周一到上周日 ──
function getLastWeekRange(): [string, string] {
  const today = new Date()
  const dayOfWeek = today.getDay() // 0=Sun, 1=Mon, ...
  // 上周一：当前日期 - (dayOfWeek + 6) 天（如果今天是周一则 -7）
  const daysToLastMonday = dayOfWeek === 0 ? 13 : dayOfWeek + 6
  const lastMonday = new Date(today)
  lastMonday.setDate(today.getDate() - daysToLastMonday)
  const lastSunday = new Date(lastMonday)
  lastSunday.setDate(lastMonday.getDate() + 6)

  const fmt = (d: Date) => {
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  }
  return [fmt(lastMonday), fmt(lastSunday)]
}

// ── 加载数据 ──
async function loadData() {
  loading.value = true
  try {
    const params: Record<string, string> = {}
    if (statusFilter.value) params.status = statusFilter.value
    if (dateRange.value) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const data = await api.get('/api/workhours', { params })
    records.value = (Array.isArray(data) ? data : data?.items || []) as WorkHourApprovalRecord[]
  } catch (err: any) {
    const msg = err?.detail?.message || err?.message || '加载失败'
    ElMessage.error(`加载工时数据失败：${msg}`)
  } finally {
    loading.value = false
  }
}

// ── 加载统计 ──
// TODO [Batch 3]: loadData + loadStats 共发 3 次 /api/workhours（主列表 + 本周已审批 + 本周待审批）。
// 应合并为单个 GET /api/workhours/summary?week=current 端点一次返回
// { items, approved_hours, pending_hours }，减少网络往返和后端负载。
async function loadStats() {
  try {
    // 本周范围
    const today = new Date()
    const dayOfWeek = today.getDay()
    const daysToMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1
    const thisMonday = new Date(today)
    thisMonday.setDate(today.getDate() - daysToMonday)
    const thisSunday = new Date(thisMonday)
    thisSunday.setDate(thisMonday.getDate() + 6)

    const fmt = (d: Date) => {
      const y = d.getFullYear()
      const m = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      return `${y}-${m}-${day}`
    }

    const weekFrom = fmt(thisMonday)
    const weekTo = fmt(thisSunday)

    // 获取本周已审批
    const approvedData = await api.get('/api/workhours', {
      params: { status: 'approved', date_from: weekFrom, date_to: weekTo },
    })
    const approvedList = (Array.isArray(approvedData) ? approvedData : approvedData?.items || []) as WorkHourApprovalRecord[]
    const approvedHours = approvedList.reduce((sum: number, r: WorkHourApprovalRecord) => sum + r.hours, 0)

    // 获取本周待审批
    const pendingData = await api.get('/api/workhours', {
      params: { status: 'confirmed', date_from: weekFrom, date_to: weekTo },
    })
    const pendingList = (Array.isArray(pendingData) ? pendingData : pendingData?.items || []) as WorkHourApprovalRecord[]
    const pendingHours = pendingList.reduce((sum: number, r: WorkHourApprovalRecord) => sum + r.hours, 0)

    stats.value = { approvedHours, pendingHours }
  } catch {
    // 统计加载失败不阻断主流程
  }
}

// ── 选择变更 ──
function onSelectionChange(rows: WorkHourApprovalRecord[]) {
  selectedRows.value = rows
}

function isSelectable(row: WorkHourApprovalRecord): boolean {
  return row.status === 'confirmed'
}

// ── 生成幂等键 ──
function generateIdempotencyKey(): string {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// ── 预算超支检查 ──
interface BudgetOverrunWarning {
  project_name: string
  budget_hours: number
  actual_hours: number
  approve_hours: number
  overrun_hours: number
}

async function checkBudgetOverrun(): Promise<BudgetOverrunWarning[]> {
  // 按项目分组选中的工时
  const projectHoursMap = new Map<string, { name: string; hours: number }>()
  for (const row of selectedRows.value) {
    const existing = projectHoursMap.get(row.project_id)
    if (existing) {
      existing.hours += row.hours
    } else {
      projectHoursMap.set(row.project_id, { name: row.project_name, hours: row.hours })
    }
  }

  const warnings: BudgetOverrunWarning[] = []

  // 并行获取各项目的成本概览
  const results = await Promise.allSettled(
    Array.from(projectHoursMap.entries()).map(async ([projectId, info]) => {
      try {
        const costData = await api.get(`/api/projects/${projectId}/cost-overview`) as any
        if (costData && costData.budget_hours && costData.budget_hours > 0) {
          const afterApprove = (costData.actual_hours ?? 0) + info.hours
          if (afterApprove > costData.budget_hours) {
            warnings.push({
              project_name: info.name,
              budget_hours: costData.budget_hours,
              actual_hours: costData.actual_hours ?? 0,
              approve_hours: info.hours,
              overrun_hours: Math.round((afterApprove - costData.budget_hours) * 10) / 10,
            })
          }
        }
      } catch {
        // Cost data not available, skip check
      }
    })
  )

  return warnings
}

async function showBudgetOverrunConfirm(warnings: BudgetOverrunWarning[]): Promise<boolean> {
  const lines = warnings.map(w =>
    `• ${w.project_name}：审批后将超预算 ${w.overrun_hours} 小时（预算 ${w.budget_hours}h，已耗 ${w.actual_hours}h，本次 +${w.approve_hours}h）`
  )
  const message = `⚠️ 以下项目审批后将超出预算：\n\n${lines.join('\n')}\n\n确认继续批准？`

  try {
    await ElMessageBox.confirm(message, '预算超支警告', {
      confirmButtonText: '确认批准',
      cancelButtonText: '取消',
      type: 'warning',
      dangerouslyUseHTMLString: false,
    })
    return true
  } catch {
    return false
  }
}

// ── 批量批准 ──
async function batchApprove() {
  if (!selectedRows.value.length) return

  // 预估审批后是否超预算
  const overrunWarnings = await checkBudgetOverrun()
  if (overrunWarnings.length > 0) {
    const confirmed = await showBudgetOverrunConfirm(overrunWarnings)
    if (!confirmed) return
  }

  batchLoading.value = true
  try {
    const hourIds = selectedRows.value.map(r => r.id)
    const { data } = await http.post('/api/workhours/batch-approve', {
      hour_ids: hourIds,
      action: 'approve',
    }, {
      headers: { 'Idempotency-Key': generateIdempotencyKey() },
    })
    const result = data as any
    ElMessage.success(`已批准 ${result?.approved_count ?? hourIds.length} 条工时`)
    tableRef.value?.clearSelection()
    await loadData()
    await loadStats()
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err?.message || '操作失败'
    ElMessage.error(`批量批准失败：${msg}`)
  } finally {
    batchLoading.value = false
  }
}

// ── 批量退回 ──
async function batchReject() {
  if (!rejectReason.value.trim()) {
    ElMessage.warning('请输入退回原因')
    return
  }
  batchLoading.value = true
  try {
    const hourIds = selectedRows.value.map(r => r.id)
    const { data } = await http.post('/api/workhours/batch-approve', {
      hour_ids: hourIds,
      action: 'reject',
      reason: rejectReason.value.trim(),
    }, {
      headers: { 'Idempotency-Key': generateIdempotencyKey() },
    })
    const result = data as any
    ElMessage.success(`已退回 ${result?.rejected_count ?? hourIds.length} 条工时`)
    showRejectDialog.value = false
    rejectReason.value = ''
    tableRef.value?.clearSelection()
    await loadData()
    await loadStats()
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err?.message || '操作失败'
    ElMessage.error(`批量退回失败：${msg}`)
  } finally {
    batchLoading.value = false
  }
}

// ── 单条批准 ──
async function approveOne(row: WorkHourApprovalRecord) {
  batchLoading.value = true
  try {
    const { data } = await http.post('/api/workhours/batch-approve', {
      hour_ids: [row.id],
      action: 'approve',
    }, {
      headers: { 'Idempotency-Key': generateIdempotencyKey() },
    })
    ElMessage.success(`已批准 ${row.staff_name} 的工时`)
    await loadData()
    await loadStats()
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err?.message || '操作失败'
    ElMessage.error(`批准失败：${msg}`)
  } finally {
    batchLoading.value = false
  }
}

// ── 单条退回 ──
function rejectOne(row: WorkHourApprovalRecord) {
  singleRejectRow.value = row
  singleRejectReason.value = ''
  showSingleRejectDialog.value = true
}

async function confirmSingleReject() {
  if (!singleRejectReason.value.trim()) {
    ElMessage.warning('请输入退回原因')
    return
  }
  if (!singleRejectRow.value) return
  batchLoading.value = true
  try {
    const { data } = await http.post('/api/workhours/batch-approve', {
      hour_ids: [singleRejectRow.value.id],
      action: 'reject',
      reason: singleRejectReason.value.trim(),
    }, {
      headers: { 'Idempotency-Key': generateIdempotencyKey() },
    })
    ElMessage.success(`已退回 ${singleRejectRow.value.staff_name} 的工时`)
    showSingleRejectDialog.value = false
    singleRejectReason.value = ''
    singleRejectRow.value = null
    await loadData()
    await loadStats()
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err?.message || '操作失败'
    ElMessage.error(`退回失败：${msg}`)
  } finally {
    batchLoading.value = false
  }
}

// ── 辅助函数 ──
function statusTagType(status: string): 'success' | 'warning' | 'info' {
  if (status === 'approved') return 'success'
  if (status === 'confirmed') return 'warning'
  return 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    draft: '草稿',
    confirmed: '已确认',
    approved: '已审批',
  }
  return map[status] || status
}

// ── 生命周期 ──
onMounted(() => {
  dateRange.value = getLastWeekRange()
  loadData()
  loadStats()
})
</script>

<style scoped>
.gt-workhours-approval {
  padding: var(--gt-space-4);
  max-width: 1400px;
}

/* 页面头部 */
.gt-page-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 16px 20px;
  background: linear-gradient(135deg, #f8f6fb 0%, #eee8f5 100%);
  border-radius: var(--gt-radius-md);
}
.gt-banner-content h2 {
  margin: 0 0 4px;
  font-size: 20px;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-banner-sub {
  font-size: 13px;
  color: var(--gt-color-text-secondary);
}

/* 统计卡片 */
.gt-stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}
.gt-stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-md);
  padding: 16px 24px;
  min-width: 200px;
  box-shadow: var(--gt-shadow-sm);
}
.gt-stat-icon {
  font-size: 28px;
}
.gt-stat-info {
  display: flex;
  flex-direction: column;
}
.gt-stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-stat-approved .gt-stat-value {
  color: var(--el-color-success, #67c23a);
}
.gt-stat-pending .gt-stat-value {
  color: var(--el-color-warning, #e6a23c);
}
.gt-stat-label {
  font-size: 12px;
  color: var(--gt-color-text-secondary);
  margin-top: 2px;
}

/* 筛选栏 */
.gt-filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

/* 批量操作栏 */
.gt-batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 16px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: var(--gt-radius-md);
}
.gt-batch-info {
  font-size: 13px;
  color: var(--gt-color-text);
  font-weight: 500;
}

/* 表格内 */
.gt-status-done {
  color: var(--gt-color-text-tertiary);
}
</style>
