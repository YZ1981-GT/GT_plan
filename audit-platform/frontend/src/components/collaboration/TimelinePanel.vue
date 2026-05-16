<template>
  <div class="gt-timeline-panel">
    <div class="panel-header">
      <h3>里程碑管理</h3>
      <el-button type="primary" size="small" @click="openAddDialog">+ 添加里程碑</el-button>
    </div>

    <!-- Milestone Table -->
    <el-table :data="milestones" stripe size="small" v-loading="loading">
      <el-table-column prop="item_code" label="编号" width="100" />
      <el-table-column prop="milestone_name" label="里程碑名称" min-width="160" />
      <el-table-column prop="type" label="类型" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="getTypeTagType(row.type)">{{ row.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="planned_date" label="计划日期" width="120" />
      <el-table-column prop="actual_date" label="实际完成" width="120">
        <template #default="{ row }">
          <span v-if="row.actual_date">{{ row.actual_date }}</span>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="剩余天数" width="100">
        <template #default="{ row }">
          <span
            :class="{ 'text-danger': row.days_remaining < 0, 'text-warning': row.days_remaining >= 0 && row.days_remaining <= 7 }"
          >
            {{ row.days_remaining >= 0 ? row.days_remaining : Math.abs(row.days_remaining) + '天(逾期)' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.actual_date" type="success" size="small">已完成</el-tag>
          <el-tag v-else-if="row.days_remaining < 0" type="danger" size="small">已逾期</el-tag>
          <el-tag v-else type="info" size="small">进行中</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button
            v-if="!row.actual_date"
            size="small"
            type="success"
            @click="markComplete(row)"
          >
            标记完成
          </el-button>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- Add Milestone Dialog -->
    <el-dialog append-to-body v-model="addDialogVisible" title="添加里程碑" width="460px">
      <el-form ref="addFormRef" :model="addForm" :rules="addRules" label-width="110px">
        <el-form-item label="里程碑名称" prop="milestone_name">
          <el-input v-model="addForm.milestone_name" placeholder="请输入里程碑名称" />
        </el-form-item>
        <el-form-item label="编号" prop="item_code">
          <el-input v-model="addForm.item_code" placeholder="如 M-001" />
        </el-form-item>
        <el-form-item label="计划日期" prop="planned_date">
          <el-date-picker
            v-model="addForm.planned_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="类型" prop="type">
          <el-select v-model="addForm.type" placeholder="请选择类型" style="width: 100%">
            <el-option label="项目启动 (KICKOFF)" value="KICKOFF" />
            <el-option label="里程碑 (MILESTONE)" value="MILESTONE" />
            <el-option label="截止日 (DEADLINE)" value="DEADLINE" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="handleAddMilestone">确认添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { projectMgmtApi } from '@/services/collaborationApi'

const projectId = 'current-project-id'

const loading = ref(false)
const adding = ref(false)
const milestones = ref<any[]>([])
const addDialogVisible = ref(false)
const addFormRef = ref<FormInstance>()

const addForm = reactive({
  milestone_name: '',
  item_code: '',
  planned_date: '',
  type: 'MILESTONE',
})

const addRules: FormRules = {
  milestone_name: [{ required: true, message: '请输入里程碑名称', trigger: 'blur' }],
  item_code: [{ required: true, message: '请输入编号', trigger: 'blur' }],
  planned_date: [{ required: true, message: '请选择计划日期', trigger: 'change' }],
  type: [{ required: true, message: '请选择类型', trigger: 'change' }],
}

// Mock milestone data
const mockData = [
  { id: 'm1', item_code: 'M-001', milestone_name: '项目启动会', type: 'KICKOFF', planned_date: '2025-01-10', actual_date: '2025-01-10', days_remaining: 0 },
  { id: 'm2', item_code: 'M-002', milestone_name: '初步分析程序', type: 'MILESTONE', planned_date: '2025-02-15', actual_date: '2025-02-14', days_remaining: 0 },
  { id: 'm3', item_code: 'M-003', milestone_name: '实质性程序完成', type: 'MILESTONE', planned_date: '2025-03-31', actual_date: '', days_remaining: 8 },
  { id: 'm4', item_code: 'M-004', milestone_name: '报告提交', type: 'DEADLINE', planned_date: '2025-04-30', actual_date: '', days_remaining: 38 },
  { id: 'm5', item_code: 'M-005', milestone_name: '风险评估', type: 'MILESTONE', planned_date: '2025-01-20', actual_date: '', days_remaining: -5 },
]

function getTypeTagType(type: string) {
  const map: Record<string, string> = {
    KICKOFF: 'primary',
    MILESTONE: 'success',
    DEADLINE: 'danger',
  }
  return (map[type] ?? 'info') as any
}

async function fetchTimeline() {
  loading.value = true
  try {
    const { data } = await projectMgmtApi.getTimeline(projectId)
    milestones.value = data ?? []
  } catch {
    // Use mock data if API not ready
    const today = new Date()
    milestones.value = mockData.map(m => {
      const planned = new Date(m.planned_date)
      const diffTime = planned.getTime() - today.getTime()
      const daysRemaining = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
      return { ...m, days_remaining: daysRemaining }
    })
  } finally {
    loading.value = false
  }
}

async function markComplete(row: any) {
  try {
    await projectMgmtApi.completeMilestone(projectId, row.id)
    ElMessage.success('里程碑已标记完成')
    row.actual_date = new Date().toISOString().slice(0, 10)
  } catch (e: any) {
    handleApiError(e, '操作')
  }
}

async function handleAddMilestone() {
  if (!addFormRef.value) return
  try {
    await addFormRef.value.validate()
  } catch {
    return
  }

  adding.value = true
  try {
    await projectMgmtApi.createMilestone(projectId, { ...addForm })
    ElMessage.success('里程碑添加成功')
    addDialogVisible.value = false
    addFormRef.value.resetFields()
    addForm.type = 'MILESTONE'
    await fetchTimeline()
  } catch (e: any) {
    handleApiError(e, '添加')
  } finally {
    adding.value = false
  }
}

function openAddDialog() {
  addFormRef.value?.resetFields()
  addForm.type = 'MILESTONE'
  addDialogVisible.value = true
}

onMounted(() => {
  fetchTimeline()
})
</script>

<style scoped>
.gt-timeline-panel {}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.panel-header h3 {
  margin: 0;
  font-size: var(--gt-font-size-base);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}

.text-danger {
  color: var(--gt-color-coral);
  font-weight: 600;
}

.text-warning {
  color: var(--gt-color-wheat);
  font-weight: 500;
}

.text-muted {
  color: var(--gt-color-info);
}
</style>
