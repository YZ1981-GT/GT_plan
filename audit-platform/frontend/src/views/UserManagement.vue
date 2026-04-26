<template>
  <div class="gt-users gt-fade-in">
    <div class="gt-users-header">
      <h2 class="gt-page-title">用户管理</h2>
      <el-button type="primary" @click="showCreate = true">新增用户</el-button>
    </div>
    <el-table :data="users" border stripe v-loading="loading">
      <el-table-column prop="username" label="用户名" width="150" />
      <el-table-column prop="email" label="邮箱" min-width="200" />
      <el-table-column prop="role" label="角色" width="120" />
      <el-table-column prop="is_active" label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="editUser(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog append-to-body v-model="showCreate" :title="editingUser ? '编辑用户' : '新增用户'" width="450px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item>
        <el-form-item v-if="!editingUser" label="密码"><el-input v-model="form.password" type="password" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="合伙人" value="partner" />
            <el-option label="项目经理" value="manager" />
            <el-option label="审计员" value="auditor" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="saveUser" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listUsers, createUser, updateUser } from '@/services/commonApi'
const users = ref<any[]>([])
const loading = ref(false)
const showCreate = ref(false)
const saving = ref(false)
const editingUser = ref<any>(null)
const form = ref({ username: '', email: '', password: '', role: 'auditor' })
async function loadUsers() {
  loading.value = true
  try {
    users.value = await listUsers()
  } catch { users.value = [] }
  finally { loading.value = false }
}
function editUser(row: any) {
  editingUser.value = row
  form.value = { username: row.username, email: row.email, password: '', role: row.role }
  showCreate.value = true
}
async function saveUser() {
  saving.value = true
  try {
    if (editingUser.value) {
      await updateUser(editingUser.value.id, form.value)
    } else {
      await createUser(form.value)
    }
    ElMessage.success('保存成功')
    showCreate.value = false
    editingUser.value = null
    await loadUsers()
  } finally { saving.value = false }
}
onMounted(loadUsers)
</script>
<style scoped>
.gt-users { padding: var(--gt-space-4); }
.gt-users-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
</style>
