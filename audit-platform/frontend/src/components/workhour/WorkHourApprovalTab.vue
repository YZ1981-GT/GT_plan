<!--
  WorkHourApprovalTab — 工时审批 Tab 子组件 [技术债 5]
  从 WorkHoursPage.vue 抽取，减少主文件体积。

  用法（在 WorkHoursPage 的 el-tab-pane 内）：
    <WorkHourApprovalTab />
-->
<template>
  <div class="gt-wh-approval-tab">
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
      <el-date-picker v-model="dateRange" type="daterange" range-separator="至"
        start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD"
        style="width: 300px" @change="loadData" />
      <el-select v-model="statusFilter" placeholder="状态" style="width: 140px" @change="loadData">
        <el-option label="已确认（待审批）" value="confirmed" />
        <el-option label="已审批" value="approved" />
        <el-option label="全部" value="" />
      </el-select>
      <el-button :loading="loading" @click="loadData">刷新</el-button>
    </div>

    <!-- 批量操作栏 -->
    <div class="gt-batch-bar" v-if="selectedRows.length > 0">
      <span class="gt-batch-info">已选 {{ selectedRows.length }} 条（共 {{ selectedTotalHours }} 小时）</span>
      <el-button type="success" @click="batchApprove" :loading="batchLoading">批量批准</el-button>
      <el-button type="warning" @click="showRejectDialog = true" :loading="batchLoading">批量退回</el-button>
    </div>

    <!-- 工时表格 -->
    <el-table ref="tableRef" :data="records" v-loading="loading"
      stripe style="width: 100%" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="50" :selectable="isSelectable" />
      <el-table-column prop="staff_name" label="员工" min-width="120" />
      <el-table-column prop="work_date" label="日期" min-width="120" sortable />
      <el-table-column prop="project_name" label="项目" min-width="180" />
      <el-table-column prop="hours" label="小时" min-width="80" align="right" />
      <el-table-column prop="description" label="描述" min-width="220" />
      <el-table-column prop="status" label="状态" min-width="100" align="center">
        <template #default="{ row }">
          <GtStatusTag :value="row.status" dict-key="workhour_status" />
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="180" align="center">
        <template #default="{ row }">
          <template v-if="row.status === 'confirmed'">
            <el-button link type="success" size="small" @click="approveOne(row)">批准</el-button>
            <el-button link type="warning" size="small" @click="rejectOne(row)">退回</el-button>
          </template>
          <span v-else style="color: var(--gt-color-text-tertiary)">—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 退回原因弹窗 -->
    <el-dialog v-model="showRejectDialog" title="退回工时" width="420px" append-to-body>
      <el-input v-model="rejectReason" type="textarea" :rows="3" placeholder="请输入退回原因" />
      <template #footer>
        <el-button @click="showRejectDialog = false">取消</el-button>
        <el-button type="warning" @click="batchReject" :loading="batchLoading">确认退回</el-button>
      </template>
    </el-dialog>

    <!-- 单条退回弹窗 -->
    <el-dialog v-model="showSingleRejectDialog" title="退回工时" width="420px" append-to-body>
      <el-input v-model="singleRejectReason" type="textarea" :rows="3" placeholder="请输入退回原因" />
      <template #footer>
        <el-button @click="showSingleRejectDialog = false">取消</el-button>
        <el-button type="warning" @click="confirmSingleReject" :loading="batchLoading">确认退回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import http from '@/utils/http'
import { workHours as P_wh } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import GtStatusTag from '@/components/common/GtStatusTag.vue'

interface ApprovalRecord {
  id: string; staff_name: string; project_name: string
  work_date: string; hours: number; description: string; status: string
}

const records = ref<ApprovalRecord[]>([])
const loading = ref(false)
const batchLoading = ref(false)
const selectedRows = ref<ApprovalRecord[]>([])
const tableRef = ref<any>(null)
const dateRange = ref<[string, string] | null>(null)
const statusFilter = ref('confirmed')
const stats = ref({ approvedHours: 0, pendingHours: 0 })
const showRejectDialog = ref(false)
const rejectReason = ref('')
const showSingleRejectDialog = ref(false)
const singleRejectReason = ref('')
const singleRejectRow = ref<ApprovalRecord | null>(null)

const selectedTotalHours = computed(() => selectedRows.value.reduce((s, r) => s + r.hours, 0))

function isSelectable(row: ApprovalRecord) { return row.status === 'confirmed' }
function onSelectionChange(rows: ApprovalRecord[]) { selectedRows.value = rows }

function getLastWeekRange(): [string, string] {
  const today = new Date()
  const dow = today.getDay()
  const daysBack = dow === 0 ? 13 : dow + 6
  const mon = new Date(today); mon.setDate(today.getDate() - daysBack)
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6)
  const fmt = (d: Date) => d.toISOString().slice(0, 10)
  return [fmt(mon), fmt(sun)]
}

async function loadData() {
  loading.value = true
  try {
    const params: Record<string, string> = {}
    if (statusFilter.value) params.status = statusFilter.value
    if (dateRange.value) { params.date_from = dateRange.value[0]; params.date_to = dateRange.value[1] }
    const data = await api.get(P_wh.list, { params })
    records.value = (Array.isArray(data) ? data : (data as any)?.items || []) as ApprovalRecord[]
  } catch (e) { handleApiError(e, '加载工时') }
  finally { loading.value = false }
}

async function loadStats() {
  try {
    const data = await api.get(P_wh.summary, { params: { week: 'current' } })
    stats.value = { approvedHours: (data as any)?.approved_hours ?? 0, pendingHours: (data as any)?.pending_hours ?? 0 }
  } catch { /* ignore */ }
}

function idempotencyKey() { return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}` }

async function batchApprove() {
  if (!selectedRows.value.length) return
  batchLoading.value = true
  try {
    await http.post(P_wh.batchApprove, { hour_ids: selectedRows.value.map(r => r.id), action: 'approve' }, { headers: { 'Idempotency-Key': idempotencyKey() } })
    ElMessage.success(`已批准 ${selectedRows.value.length} 条`)
    tableRef.value?.clearSelection()
    loadData(); loadStats()
  } catch (e) { handleApiError(e, '批量批准') }
  finally { batchLoading.value = false }
}

async function batchReject() {
  if (!rejectReason.value.trim()) { ElMessage.warning('请输入退回原因'); return }
  batchLoading.value = true
  try {
    await http.post(P_wh.batchApprove, { hour_ids: selectedRows.value.map(r => r.id), action: 'reject', reason: rejectReason.value.trim() }, { headers: { 'Idempotency-Key': idempotencyKey() } })
    ElMessage.success(`已退回 ${selectedRows.value.length} 条`)
    showRejectDialog.value = false; rejectReason.value = ''
    tableRef.value?.clearSelection()
    loadData(); loadStats()
  } catch (e) { handleApiError(e, '批量退回') }
  finally { batchLoading.value = false }
}

async function approveOne(row: ApprovalRecord) {
  batchLoading.value = true
  try {
    await http.post(P_wh.batchApprove, { hour_ids: [row.id], action: 'approve' }, { headers: { 'Idempotency-Key': idempotencyKey() } })
    ElMessage.success(`已批准 ${row.staff_name} 的工时`)
    loadData(); loadStats()
  } catch (e) { handleApiError(e, '批准工时') }
  finally { batchLoading.value = false }
}

function rejectOne(row: ApprovalRecord) {
  singleRejectRow.value = row; singleRejectReason.value = ''; showSingleRejectDialog.value = true
}

async function confirmSingleReject() {
  if (!singleRejectReason.value.trim()) { ElMessage.warning('请输入退回原因'); return }
  if (!singleRejectRow.value) return
  batchLoading.value = true
  try {
    await http.post(P_wh.batchApprove, { hour_ids: [singleRejectRow.value.id], action: 'reject', reason: singleRejectReason.value.trim() }, { headers: { 'Idempotency-Key': idempotencyKey() } })
    ElMessage.success(`已退回 ${singleRejectRow.value.staff_name} 的工时`)
    showSingleRejectDialog.value = false
    loadData(); loadStats()
  } catch (e) { handleApiError(e, '退回工时') }
  finally { batchLoading.value = false }
}

onMounted(() => {
  dateRange.value = getLastWeekRange()
  loadData(); loadStats()
})
</script>

<style scoped>
.gt-wh-approval-tab { padding: var(--gt-space-2) 0; }
.gt-stats-row { display: flex; gap: 16px; margin-bottom: 20px; }
.gt-stat-card { display: flex; align-items: center; gap: 12px; background: var(--gt-color-bg-white); border: 1px solid var(--gt-color-border-light); border-radius: var(--gt-radius-md); padding: 16px 24px; min-width: 200px; }
.gt-stat-icon { font-size: var(--gt-font-size-3xl); }
.gt-stat-info { display: flex; flex-direction: column; }
.gt-stat-value { font-size: 24px /* allow-px: special */; font-weight: 700; color: var(--gt-color-primary); }
.gt-stat-approved .gt-stat-value { color: var(--gt-color-success); }
.gt-stat-pending .gt-stat-value { color: var(--gt-color-wheat); }
.gt-stat-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); margin-top: 2px; }
.gt-filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.gt-batch-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding: 10px 16px; background: var(--gt-color-success-light); border: 1px solid var(--gt-color-border-success); border-radius: var(--gt-radius-md); }
.gt-batch-info { font-size: var(--gt-font-size-sm); color: var(--gt-color-text); font-weight: 500; }
</style>
