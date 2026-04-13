<template>
  <div class="gt-user-management gt-fade-in">
    <el-card>
      <template #header>
        <div class="gt-um-header">
          <span>用户管理</span>
          <el-button v-if="isAdmin" type="primary" @click="openCreateDialog">创建用户</el-button>
        </div>
      </template>

      <el-table :data="users" v-loading="loading" stripe>
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="display_name" label="显示名称" />
        <el-table-column prop="role" label="角色">
          <template #default="{ row }">
            <el-tag>{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="office_code" label="办事处" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column prop="is_active" label="状态">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" v-if="isAdmin" width="140">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑用户' : '创建用户'" width="500px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="isEditing" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item label="显示名称" prop="display_name">
          <el-input v-model="form.display_name" placeholder="显示名称" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" placeholder="选择角色">
            <el-option label="Admin" value="admin" />
            <el-option label="Partner" value="partner" />
            <el-option label="Manager" value="manager" />
            <el-option label="Auditor" value="auditor" />
            <el-option label="QC Reviewer" value="qc_reviewer" />
            <el-option label="Readonly" value="readonly" />
          </el-select>
        </el-form-item>
        <el-form-item label="办事处">
          <el-input v-model="form.office_code" placeholder="办事处代码" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="邮箱地址" />
        </el-form-item>
        <el-form-item v-if="!isEditing" label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="初始密码" />
          <div class="gt-um-password-strength">
            <el-progress :percentage="passwordStrength" :color="strengthColor" />
          </div>
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, FormInstance, FormRules } from 'element-plus'
import { authApi } from '@/services/auditPlatformApi'

const users = ref<any[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEditing = ref(false)
const formRef = ref<FormInstance>()

const isAdmin = computed(() => authApi.getCurrentUser()?.role === 'admin')

const form = ref({
  username: '',
  display_name: '',
  role: 'auditor',
  office_code: '',
  email: '',
  password: '',
  is_active: true,
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  display_name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const passwordStrength = computed(() => {
  const p = form.value.password
  if (!p) return 0
  let score = 0
  if (p.length >= 8) score += 25
  if (/[A-Z]/.test(p)) score += 25
  if (/[0-9]/.test(p)) score += 25
  if (/[^A-Za-z0-9]/.test(p)) score += 25
  return score
})

const strengthColor = computed(() => {
  if (passwordStrength.value < 50) return '#f56c6c'
  if (passwordStrength.value < 75) return '#e6a23c'
  return '#67c23a'
})

const roleLabel = (role: string) => ({
  admin: '管理员', partner: '合伙人', manager: '经理',
  auditor: '审计员', qc_reviewer: '质控复核', readonly: '只读',
}[role] || role)

const loadUsers = async () => {
  loading.value = true
  try {
    const res = await authApi.getUsers()
    users.value = res.data
  } catch {
    ElMessage.error('加载用户列表失败')
  } finally {
    loading.value = false
  }
}

const openCreateDialog = () => {
  isEditing.value = false
  form.value = { username: '', display_name: '', role: 'auditor', office_code: '', email: '', password: '', is_active: true }
  dialogVisible.value = true
}

const openEditDialog = (row: any) => {
  isEditing.value = true
  form.value = { ...row, password: '' }
  dialogVisible.value = true
}

const handleSave = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      if (isEditing.value) {
        await authApi.updateUser(form.value.id, form.value)
        ElMessage.success('用户已更新')
      } else {
        await authApi.createUser(form.value)
        ElMessage.success('用户已创建')
      }
      dialogVisible.value = false
      loadUsers()
    } catch {
      ElMessage.error('保存失败')
    }
  })
}

const handleDelete = async (row: any) => {
  try {
    await authApi.deleteUser(row.id)
    ElMessage.success('用户已删除')
    loadUsers()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.gt-user-management { padding: var(--gt-space-4); }
.gt-um-header { display: flex; justify-content: space-between; align-items: center; }
.gt-um-password-strength { margin-top: 6px; }
</style>
