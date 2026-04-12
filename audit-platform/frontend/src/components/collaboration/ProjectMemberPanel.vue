<template>
  <div class="project-member-panel">
    <div class="toolbar">
      <span class="title">项目成员</span>
      <el-button v-if="canManage" type="primary" size="small" @click="openAddDialog">添加成员</el-button>
    </div>

    <el-table :data="members" v-loading="loading" stripe size="small">
      <el-table-column prop="user_username" label="用户名" />
      <el-table-column prop="user_display_name" label="显示名" />
      <el-table-column prop="project_role" label="项目角色">
        <template #default="{ row }">
          <el-tag size="small">{{ projectRoleLabel(row.project_role) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="assigned_cycles" label="审计循环">
        <template #default="{ row }">
          <el-tag v-for="c in (row.assigned_cycles || [])" :key="c" size="small" style="margin-right: 4px">{{ c }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="assigned_account_ranges" label="科目范围" show-overflow-tooltip />
      <el-table-column prop="valid_from" label="开始日期" width="110" />
      <el-table-column label="操作" width="80" v-if="canManage">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="handleRemove(row)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="addDialogVisible" title="添加项目成员" width="520px">
      <el-form :model="addForm" :rules="addRules" ref="addFormRef" label-width="100px">
        <el-form-item label="用户" prop="user_id">
          <el-select v-model="addForm.user_id" filterable placeholder="搜索用户">
            <el-option v-for="u in availableUsers" :key="u.id" :label="`${u.username} (${u.display_name})`" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="项目角色" prop="project_role">
          <el-select v-model="addForm.project_role">
            <el-option label="合伙人" value="partner" />
            <el-option label="经理" value="manager" />
            <el-option label="审计员" value="auditor" />
            <el-option label="质控复核" value="qc_reviewer" />
            <el-option label="只读" value="readonly" />
          </el-select>
        </el-form-item>
        <el-form-item label="审计循环">
          <el-select v-model="addForm.assigned_cycles" multiple placeholder="选择循环">
            <el-option label="销售与收款循环" value="sales_receivable" />
            <el-option label="采购与付款循环" value="purchases_payable" />
            <el-option label="生产与存货循环" value="production_inventory" />
            <el-option label="人力资源与薪酬" value="hr_payroll" />
            <el-option label="筹资与投资循环" value="financing_investing" />
            <el-option label="货币资金" value="cash" />
            <el-option label="财务报表审计" value="financial_statements" />
          </el-select>
        </el-form-item>
        <el-form-item label="科目范围">
          <el-input v-model="addForm.assigned_account_ranges" placeholder="如: 1001-1999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAdd">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, FormInstance, FormRules } from 'element-plus'
import { authApi } from '@/services/auditPlatformApi'

const props = defineProps<{ projectId: string }>()

const members = ref<any[]>([])
const availableUsers = ref<any[]>([])
const loading = ref(false)
const addDialogVisible = ref(false)
const addFormRef = ref<FormInstance>()

const canManage = computed(() => ['admin', 'partner', 'manager'].includes(authApi.getCurrentUser()?.role || ''))

const addForm = ref({
  user_id: '',
  project_role: 'auditor',
  assigned_cycles: [] as string[],
  assigned_account_ranges: '',
})

const addRules: FormRules = {
  user_id: [{ required: true, message: '请选择用户', trigger: 'change' }],
  project_role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const projectRoleLabel = (role: string) => ({
  partner: '合伙人', manager: '经理', auditor: '审计员',
  qc_reviewer: '质控复核', readonly: '只读',
}[role] || role)

const loadMembers = async () => {
  loading.value = true
  try {
    const res = await authApi.getProjectMembers(props.projectId)
    members.value = res.data
    const usersRes = await authApi.getUsers()
    const memberIds = new Set(members.value.map((m: any) => m.user_id))
    availableUsers.value = usersRes.data.filter((u: any) => !memberIds.has(u.id) && u.is_active)
  } catch {
    ElMessage.error('加载成员失败')
  } finally {
    loading.value = false
  }
}

const openAddDialog = () => {
  addForm.value = { user_id: '', project_role: 'auditor', assigned_cycles: [], assigned_account_ranges: '' }
  addDialogVisible.value = true
}

const handleAdd = async () => {
  if (!addFormRef.value) return
  await addFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      await authApi.addProjectMember(props.projectId, addForm.value)
      ElMessage.success('成员已添加')
      addDialogVisible.value = false
      loadMembers()
    } catch {
      ElMessage.error('添加失败')
    }
  })
}

const handleRemove = async (row: any) => {
  try {
    await authApi.removeProjectMember(props.projectId, row.user_id)
    ElMessage.success('成员已移除')
    loadMembers()
  } catch {
    ElMessage.error('移除失败')
  }
}

onMounted(loadMembers)
</script>

<style scoped>
.project-member-panel { padding: 8px 0; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.title { font-weight: 600; font-size: 14px; }
</style>
