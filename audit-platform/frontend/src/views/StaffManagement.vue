<template>
  <div class="gt-staff-page gt-fade-in">
    <div class="gt-staff-header">
      <h2 class="gt-page-title">人员库管理</h2>
      <div class="gt-staff-actions">
        <el-input v-model="searchQuery" placeholder="搜索姓名/工号" clearable style="width: 220px"
          @input="debouncedSearch" />
        <el-select v-model="filterDept" placeholder="部门" clearable style="width: 150px" @change="loadStaff">
          <el-option label="审计一部" value="审计一部" />
          <el-option label="审计二部" value="审计二部" />
          <el-option label="审计三部" value="审计三部" />
        </el-select>
        <el-button type="primary" @click="showCreateDialog = true">新增人员</el-button>
        <el-button @click="showStaffImport = true">Excel导入</el-button>
      </div>
    </div>

    <el-table :data="staffList" v-loading="loading" border stripe style="width: 100%">
      <el-table-column prop="employee_no" label="工号" width="100" sortable />
      <el-table-column prop="name" label="姓名" width="100" />
      <el-table-column prop="department" label="部门" width="100" />
      <el-table-column prop="title" label="职级" width="100" />
      <el-table-column prop="partner_name" label="所属合伙人" width="120" />
      <el-table-column prop="specialty" label="专业领域" min-width="150" />
      <el-table-column label="来源" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.source === 'seed' ? 'info' : 'success'" size="small">
            {{ row.source === 'seed' ? '初始' : '自定义' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="phone" label="联系电话" width="130" />
      <el-table-column label="操作" width="220" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="editStaff(row)">编辑</el-button>
          <el-button link type="primary" size="small" @click="viewResume(row)">简历</el-button>
          <el-button link type="warning" size="small" @click="openHandover(row)">交接</el-button>
          <el-button v-if="row.source === 'custom'" link type="danger" size="small" @click="onDeleteStaff(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination v-if="total > pageSize" :current-page="currentPage" :page-size="pageSize"
      :total="total" layout="total, prev, pager, next" style="margin-top: 16px; justify-content: flex-end"
      @current-change="onPageChange" />

    <!-- 创建/编辑弹窗 -->
    <el-dialog append-to-body v-model="showCreateDialog" :title="editingStaff ? '编辑人员' : '新增人员'" width="500px">
      <el-form :model="formData" label-width="90px">
        <el-form-item label="姓名" required><el-input v-model="formData.name" /></el-form-item>
        <el-form-item label="工号"><el-input v-model="formData.employee_no" /></el-form-item>
        <el-form-item label="部门"><el-input v-model="formData.department" /></el-form-item>
        <el-form-item label="职级">
          <el-select v-model="formData.title" style="width: 100%">
            <el-option v-for="t in titles" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属合伙人"><el-input v-model="formData.partner_name" /></el-form-item>
        <el-form-item label="专业领域"><el-input v-model="formData.specialty" /></el-form-item>
        <el-form-item label="联系电话"><el-input v-model="formData.phone" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="formData.email" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveStaff" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 简历弹窗 -->
    <el-dialog append-to-body v-model="showResumeDialog" title="人员简历" width="600px">
      <div v-if="resumeData">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="姓名">{{ resumeData.name }}</el-descriptions-item>
          <el-descriptions-item label="职级">{{ resumeData.title }}</el-descriptions-item>
          <el-descriptions-item label="部门">{{ resumeData.department }}</el-descriptions-item>
          <el-descriptions-item label="参与项目数">{{ resumeData.total_projects }}</el-descriptions-item>
        </el-descriptions>
        <h4 style="margin: 16px 0 8px">参与项目历史</h4>
        <el-table :data="resumeData.recent_projects" border size="small" max-height="300">
          <el-table-column prop="project_name" label="项目名称" />
          <el-table-column prop="client_name" label="客户" />
          <el-table-column prop="role" label="角色" width="100" />
          <el-table-column prop="assigned_at" label="委派时间" width="120" />
        </el-table>
      </div>
    </el-dialog>

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showStaffImport"
      import-type="staff"
      @imported="onStaffImported"
    />

    <!-- 交接弹窗 -->
    <el-dialog
      v-model="showHandoverDialog"
      title="人员工作交接"
      width="560px"
      append-to-body
      :close-on-click-modal="false"
      @close="resetHandoverForm"
    >
      <el-form :model="handoverForm" label-width="100px">
        <el-form-item label="交接人">
          <span style="font-weight: 600">{{ handoverTarget?.name }}（{{ handoverTarget?.title || '—' }}）</span>
        </el-form-item>
        <el-form-item label="目标人" required>
          <el-select
            v-model="handoverForm.target_staff_id"
            filterable
            placeholder="请选择接收人"
            style="width: 100%"
            @change="onTargetChange"
          >
            <el-option
              v-for="s in handoverCandidates"
              :key="s.id"
              :label="`${s.name}（${s.title || '—'}）`"
              :value="s.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="原因" required>
          <el-select v-model="handoverForm.reason_code" placeholder="请选择原因" style="width: 100%">
            <el-option label="离职" value="resignation" />
            <el-option label="长期休假" value="long_leave" />
            <el-option label="岗位轮换" value="rotation" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="补充说明">
          <el-input
            v-model="handoverForm.reason_detail"
            type="textarea"
            :rows="2"
            placeholder="可选，补充交接原因"
          />
        </el-form-item>
        <el-form-item label="生效日期" required>
          <el-date-picker
            v-model="handoverForm.effective_date"
            type="date"
            placeholder="选择生效日期"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>

      <!-- 预览区 -->
      <div v-if="handoverPreview" class="gt-handover-preview">
        <el-divider content-position="left">交接预览</el-divider>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="底稿">{{ handoverPreview.workpapers }} 张</el-descriptions-item>
          <el-descriptions-item label="工单">{{ handoverPreview.issues }} 张</el-descriptions-item>
          <el-descriptions-item label="项目委派">{{ handoverPreview.assignments }} 个</el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="handoverForm.reason_code === 'resignation'"
          type="warning"
          :closable="false"
          style="margin-top: 12px"
          description="离职交接将同时标记该人员未完成的独立性声明为已交接替代。"
        />
      </div>
      <div v-if="handoverPreviewLoading" style="text-align: center; padding: 16px">
        <el-icon class="is-loading"><Loading /></el-icon> 加载预览中...
      </div>

      <template #footer>
        <el-button @click="showHandoverDialog = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!canSubmitHandover"
          :loading="handoverSubmitting"
          @click="executeHandover"
        >
          确认交接
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { listStaff, createStaff, updateStaff, getStaffResume, deleteStaff, type StaffMember } from '@/services/staffApi'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import http from '@/utils/http'

const titles = ['合伙人', '总监', '高级经理', '经理', '高级审计员', '审计员', '实习生']

const staffList = ref<StaffMember[]>([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = 50
const searchQuery = ref('')
const filterDept = ref('')
const showCreateDialog = ref(false)
const showStaffImport = ref(false)
const showResumeDialog = ref(false)
const editingStaff = ref<StaffMember | null>(null)
const saving = ref(false)
const resumeData = ref<any>(null)

const formData = ref({ name: '', employee_no: '', department: '', title: '', partner_name: '', specialty: '', phone: '', email: '' })

let searchTimer: ReturnType<typeof setTimeout> | null = null
function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { currentPage.value = 1; loadStaff() }, 400)
}

async function loadStaff() {
  loading.value = true
  try {
    const res = await listStaff({
      search: searchQuery.value || undefined,
      department: filterDept.value || undefined,
      offset: (currentPage.value - 1) * pageSize,
      limit: pageSize,
    })
    staffList.value = res.items
    total.value = res.total
  } finally { loading.value = false }
}

function onPageChange(page: number) { currentPage.value = page; loadStaff() }

function editStaff(row: StaffMember) {
  editingStaff.value = row
  formData.value = { name: row.name, employee_no: row.employee_no || '', department: row.department || '', title: row.title || '', partner_name: row.partner_name || '', specialty: row.specialty || '', phone: row.phone || '', email: row.email || '' }
  showCreateDialog.value = true
}

async function viewResume(row: StaffMember) {
  try {
    resumeData.value = await getStaffResume(row.id)
    showResumeDialog.value = true
  } catch { ElMessage.error('获取简历失败') }
}

async function saveStaff() {
  if (!formData.value.name) { ElMessage.warning('请输入姓名'); return }
  saving.value = true
  try {
    if (editingStaff.value) {
      await updateStaff(editingStaff.value.id, formData.value)
      ElMessage.success('更新成功')
    } else {
      await createStaff({ ...formData.value, source: 'custom' })
      ElMessage.success('创建成功')
    }
    showCreateDialog.value = false
    editingStaff.value = null
    formData.value = { name: '', employee_no: '', department: '', title: '', partner_name: '', specialty: '', phone: '', email: '' }
    await loadStaff()
  } finally { saving.value = false }
}

async function onDeleteStaff(row: StaffMember) {
  await ElMessageBox.confirm(`确定删除「${row.name}」？此操作仅对自定义人员有效。`, '删除确认', { type: 'warning' })
  try {
    await deleteStaff(row.id)
    ElMessage.success('已删除')
    await loadStaff()
  } catch { ElMessage.error('删除失败') }
}

function onStaffImported() {
  showStaffImport.value = false
  loadStaff()
}

// ── 交接功能 ──

const showHandoverDialog = ref(false)
const handoverTarget = ref<StaffMember | null>(null)
const handoverCandidates = ref<StaffMember[]>([])
const handoverPreview = ref<{ workpapers: number; issues: number; assignments: number } | null>(null)
const handoverPreviewLoading = ref(false)
const handoverSubmitting = ref(false)

const handoverForm = ref({
  target_staff_id: '',
  reason_code: '',
  reason_detail: '',
  effective_date: '',
})

const canSubmitHandover = computed(() => {
  return (
    handoverForm.value.target_staff_id &&
    handoverForm.value.reason_code &&
    handoverForm.value.effective_date &&
    handoverPreview.value !== null &&
    !handoverSubmitting.value
  )
})

function resetHandoverForm() {
  handoverTarget.value = null
  handoverPreview.value = null
  handoverPreviewLoading.value = false
  handoverSubmitting.value = false
  handoverForm.value = { target_staff_id: '', reason_code: '', reason_detail: '', effective_date: '' }
}

async function openHandover(row: StaffMember) {
  handoverTarget.value = row
  showHandoverDialog.value = true

  // 加载候选人列表（排除当前交接人）
  try {
    const res = await listStaff({ limit: 500 })
    handoverCandidates.value = res.items.filter(s => s.id !== row.id)
  } catch {
    handoverCandidates.value = []
  }

  // 加载预览
  await loadHandoverPreview(row.id)
}

async function loadHandoverPreview(staffId: string) {
  handoverPreviewLoading.value = true
  handoverPreview.value = null
  try {
    const { data } = await http.get(`/api/staff/${staffId}/handover/preview`, {
      params: { scope: 'all' },
    })
    handoverPreview.value = data as { workpapers: number; issues: number; assignments: number }
  } catch {
    handoverPreview.value = null
    ElMessage.warning('获取交接预览失败')
  } finally {
    handoverPreviewLoading.value = false
  }
}

function onTargetChange() {
  // 目标人变更时无需重新加载预览（预览只与交接人相关）
}

async function executeHandover() {
  if (!handoverTarget.value) return
  const totalItems = (handoverPreview.value?.workpapers || 0) +
    (handoverPreview.value?.issues || 0) +
    (handoverPreview.value?.assignments || 0)

  if (totalItems === 0) {
    ElMessage.info('该人员名下无需交接的工作项')
    showHandoverDialog.value = false
    return
  }

  try {
    await ElMessageBox.confirm(
      `确认将 ${handoverPreview.value?.workpapers} 张底稿、${handoverPreview.value?.issues} 张工单、${handoverPreview.value?.assignments} 个项目委派交接给目标人？`,
      '交接确认',
      { type: 'warning' },
    )
  } catch {
    return // 用户取消
  }

  handoverSubmitting.value = true
  try {
    await http.post(`/api/staff/${handoverTarget.value.id}/handover`, {
      scope: 'all',
      target_staff_id: handoverForm.value.target_staff_id,
      reason_code: handoverForm.value.reason_code,
      reason_detail: handoverForm.value.reason_detail || undefined,
      effective_date: handoverForm.value.effective_date,
    })
    ElMessage.success(
      `交接完成：${handoverPreview.value?.workpapers} 张底稿、${handoverPreview.value?.issues} 张工单、${handoverPreview.value?.assignments} 个项目委派已转交，新负责人已收到通知`,
    )
    showHandoverDialog.value = false
    await loadStaff()
  } catch {
    // http 拦截器已处理错误提示
  } finally {
    handoverSubmitting.value = false
  }
}

onMounted(loadStaff)
</script>

<style scoped>
.gt-staff-page { padding: var(--gt-space-4); }
.gt-staff-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); flex-wrap: wrap; gap: var(--gt-space-2); }
.gt-staff-header .gt-page-title { font-size: 14px; }
.gt-staff-actions { display: flex; gap: var(--gt-space-2); align-items: center; }
.gt-handover-preview { margin-top: 16px; }
</style>
