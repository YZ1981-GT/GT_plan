<template>
  <div class="gt-workhours-page gt-fade-in">
    <div class="gt-wh-header">
      <h2 class="gt-page-title">工时管理</h2>
    </div>

    <el-tabs v-model="activeTab">
      <!-- ═══ Tab 1: 我的填报 ═══ -->
      <el-tab-pane label="我的填报" name="mine">
        <div class="gt-wh-actions" style="margin-bottom: 16px;">
          <el-date-picker v-model="dateRange" type="daterange" range-separator="至"
            start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD"
            style="width: 280px" @change="loadHours" />
          <el-button @click="showAISuggest">LLM 预填</el-button>
          <el-button type="primary" @click="showCreateDialog = true">填报工时</el-button>
        </div>

        <!-- 工时列表 -->
        <el-table :data="hours" v-loading="loading" border stripe style="width: 100%">
          <el-table-column prop="work_date" label="日期" width="120" sortable />
          <el-table-column prop="project_name" label="项目" min-width="200" />
          <el-table-column prop="hours" label="小时" width="80" align="right" />
          <el-table-column prop="description" label="工作内容" min-width="200" />
          <el-table-column prop="status" label="状态" width="100" align="center">
            <template #default="{ row }">
              <GtStatusTag :value="row.status" dict-key="workhour_status" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center">
            <template #default="{ row }">
              <el-button v-if="row.status === 'draft'" link type="primary" size="small" @click="confirmHour(row)">确认</el-button>
              <el-button v-if="row.status === 'draft'" link type="danger" size="small" @click="editHour(row)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 填报弹窗 -->
        <el-dialog append-to-body v-model="showCreateDialog" :title="editingHourId ? '编辑工时' : '填报工时'" width="450px">
          <el-form :model="form" label-width="80px">
            <el-form-item label="日期" required>
              <el-date-picker v-model="form.work_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
            <el-form-item label="项目" required>
              <el-select v-model="form.project_id" placeholder="选择项目" style="width: 100%">
                <el-option v-for="p in myProjects" :key="p.project_id" :label="p.project_name" :value="p.project_id" />
              </el-select>
            </el-form-item>
            <el-form-item label="小时数" required>
              <el-input-number v-model="form.hours" :min="0.5" :max="24" :step="0.5" style="width: 100%" />
            </el-form-item>
            <el-form-item label="工作内容">
              <el-input v-model="form.description" type="textarea" :rows="2" />
            </el-form-item>
          </el-form>
          <!-- 警告 -->
          <div v-if="warnings.length" style="margin-top: 8px">
            <el-alert v-for="(w, i) in warnings" :key="i" :title="w.message" type="warning" show-icon :closable="false" style="margin-bottom: 4px" />
          </div>
          <template #footer>
            <el-button @click="showCreateDialog = false">取消</el-button>
            <el-button type="primary" @click="submitHour" :loading="submitting">{{ editingHourId ? '更新' : '保存' }}</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ═══ Tab 2: 待审批（抽取为子组件 R7 技术债 5） ═══ -->
      <el-tab-pane v-if="can('approve_workhours')" label="待审批" name="approve">
        <WorkHourApprovalTab />
      </el-tab-pane>

      <!-- ═══ Tab 3: 统计 ═══ -->
      <el-tab-pane label="统计" name="stats">
        <div style="padding: 40px; text-align: center; color: var(--gt-color-text-secondary);">
          <el-empty description="工时统计功能开发中" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listWorkHours, createWorkHour, updateWorkHour, getAISuggestions, getMyAssignments, getMyStaffId, type WorkHourRecord } from '@/services/staffApi'
import { usePermission } from '@/composables/usePermission'
import GtStatusTag from '@/components/common/GtStatusTag.vue'
import WorkHourApprovalTab from '@/components/workhour/WorkHourApprovalTab.vue'

const { can } = usePermission()
const activeTab = ref('mine')

// ══════════════════════════════════════════════
// Tab 1: 我的填报
// ══════════════════════════════════════════════
const hours = ref<WorkHourRecord[]>([])
const loading = ref(false)
const dateRange = ref<[string, string] | null>(null)
const showCreateDialog = ref(false)
const submitting = ref(false)
const warnings = ref<{ message: string }[]>([])
const myProjects = ref<any[]>([])
const currentStaffId = ref('')
const editingHourId = ref<string | null>(null)

const form = ref({ work_date: '', project_id: '', hours: 8, description: '' })

async function loadHours() {
  if (!currentStaffId.value) return
  loading.value = true
  try {
    const params: any = {}
    if (dateRange.value) { params.start_date = dateRange.value[0]; params.end_date = dateRange.value[1] }
    hours.value = await listWorkHours(currentStaffId.value, params)
  } finally { loading.value = false }
}

async function submitHour() {
  if (!form.value.work_date || !form.value.project_id) { ElMessage.warning('请填写日期和项目'); return }
  submitting.value = true
  try {
    let res: any
    if (editingHourId.value) {
      res = await updateWorkHour(editingHourId.value, form.value)
    } else {
      res = await createWorkHour(currentStaffId.value, form.value)
    }
    warnings.value = res.warnings || []
    if (warnings.value.length === 0) {
      ElMessage.success(editingHourId.value ? '工时已更新' : '工时已保存')
      showCreateDialog.value = false
      editingHourId.value = null
      form.value = { work_date: '', project_id: '', hours: 8, description: '' }
      await loadHours()
    }
  } finally { submitting.value = false }
}

async function confirmHour(row: WorkHourRecord) {
  await updateWorkHour(row.id, { status: 'confirmed' })
  ElMessage.success('已确认')
  await loadHours()
}

function editHour(row: WorkHourRecord) {
  editingHourId.value = row.id
  form.value = { work_date: row.work_date, project_id: row.project_id, hours: row.hours, description: row.description || '' }
  showCreateDialog.value = true
}

async function showAISuggest() {
  if (!currentStaffId.value) return
  const today = new Date().toISOString().slice(0, 10)
  try {
    const res = await getAISuggestions(currentStaffId.value, today)
    if (res.suggestions?.length) {
      form.value = { work_date: today, project_id: res.suggestions[0].project_id, hours: res.suggestions[0].hours, description: res.suggestions[0].description || '' }
      showCreateDialog.value = true
      ElMessage.info('已加载 AI 建议，请确认后保存')
    } else { ElMessage.info('暂无建议') }
  } catch { ElMessage.error('AI 预填失败') }
}

// ══════════════════════════════════════════════
// Tab 2: 待审批（已抽取为 WorkHourApprovalTab 子组件）
// ══════════════════════════════════════════════

// ══════════════════════════════════════════════
// Lifecycle
// ══════════════════════════════════════════════
onMounted(async () => {
  // Tab 1 初始化
  try {
    const staffInfo = await getMyStaffId()
    currentStaffId.value = staffInfo.staff_id
  } catch {
    ElMessage.warning('未找到人员信息，请联系管理员')
  }
  try {
    myProjects.value = await getMyAssignments()
  } catch { /* ignore */ }
  if (currentStaffId.value) await loadHours()
})
</script>

<style scoped>
.gt-workhours-page { padding: var(--gt-space-4); }
.gt-wh-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); flex-wrap: wrap; gap: var(--gt-space-2); }
.gt-wh-actions { display: flex; gap: var(--gt-space-2); align-items: center; }

/* 审批 Tab 样式 */
.gt-stats-row { display: flex; gap: 16px; margin-bottom: 20px; }
.gt-stat-card { display: flex; align-items: center; gap: 12px; background: #fff; border: 1px solid var(--gt-color-border-light); border-radius: var(--gt-radius-md); padding: 16px 24px; min-width: 200px; box-shadow: var(--gt-shadow-sm); }
.gt-stat-icon { font-size: 28px; }
.gt-stat-info { display: flex; flex-direction: column; }
.gt-stat-value { font-size: 24px; font-weight: 700; color: var(--gt-color-primary, #4b2d77); }
.gt-stat-approved .gt-stat-value { color: var(--el-color-success, #67c23a); }
.gt-stat-pending .gt-stat-value { color: var(--el-color-warning, #e6a23c); }
.gt-stat-label { font-size: 12px; color: var(--gt-color-text-secondary); margin-top: 2px; }
.gt-filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.gt-batch-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding: 10px 16px; background: #f0f9eb; border: 1px solid #e1f3d8; border-radius: var(--gt-radius-md); }
.gt-batch-info { font-size: 13px; color: var(--gt-color-text); font-weight: 500; }
.gt-status-done { color: var(--gt-color-text-tertiary); }
</style>
