<template>
  <div class="gt-users gt-fade-in">
    <!-- 页面头部：标题右侧内联操作按钮（避免 actions 插槽在 column 布局下被拉伸） -->
    <GtPageHeader title="用户管理" :show-back="false">
      <div class="gt-users-header-actions">
        <el-button type="primary" @click="showCreate = true" v-permission="'admin'">
          <el-icon style="margin-right: 4px"><Plus /></el-icon>新增用户
        </el-button>
      </div>
    </GtPageHeader>

    <!-- 筛选栏 -->
    <div class="gt-users-filter">
      <el-input
        v-model="searchQuery"
        placeholder="搜索用户名或邮箱"
        clearable
        style="width: 260px"
        :prefix-icon="Search"
      />
      <el-select v-model="filterRole" placeholder="全部角色" clearable style="width: 160px">
        <el-option v-for="opt in ROLE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <span class="gt-users-count">共 {{ filteredUsers.length }} 位用户</span>
    </div>

    <!-- 用户表格 -->
    <el-card shadow="never" class="gt-users-card">
      <el-table :data="filteredUsers" v-loading="loading" style="width: 100%" row-key="id">
        <el-table-column prop="username" label="用户名" min-width="140">
          <template #default="{ row }">
            <div class="gt-user-cell">
              <el-avatar :size="28" style="background: var(--el-color-primary-light-7); color: var(--el-color-primary); font-size: 12px; flex-shrink: 0">
                {{ (row.username || '?')[0].toUpperCase() }}
              </el-avatar>
              <span class="gt-user-name">{{ row.username }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="220">
          <template #default="{ row }">
            <span style="color: var(--el-text-color-secondary)">{{ row.email }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role)" size="small" effect="plain" round>
              {{ roleLabel(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small" effect="light">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="editUser(row)" v-permission="'admin'">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog append-to-body v-model="showCreate" :title="editingUser ? '编辑用户' : '新增用户'" width="450px" @closed="onDialogClosed">
      <el-form ref="userFormRef" :model="form" :rules="userFormRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item v-if="!editingUser" label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="opt in ROLE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="saveUser" :loading="userSubmitting || saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { listUsers, createUser, updateUser } from '@/services/commonApi'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import { rules, makeRules } from '@/utils/formRules'
import { useFormSubmit } from '@/composables/useFormSubmit'

const users = ref<any[]>([])
const loading = ref(false)
const showCreate = ref(false)
const saving = ref(false)
const editingUser = ref<any>(null)
const form = ref({ username: '', email: '', password: '', role: 'auditor' })

// 搜索与筛选
const searchQuery = ref('')
const filterRole = ref('')

const filteredUsers = computed(() => {
  let list = users.value
  if (filterRole.value) {
    list = list.filter(u => u.role === filterRole.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(u =>
      (u.username || '').toLowerCase().includes(q) ||
      (u.email || '').toLowerCase().includes(q)
    )
  }
  return list
})

// 角色选项（单一来源，与后端 UserRole 枚举对齐；qc/eqcr 后端 permission_matrix 已支持）
const ROLE_OPTIONS = [
  { value: 'admin', label: '管理员', tag: 'danger' },
  { value: 'partner', label: '合伙人', tag: 'warning' },
  { value: 'manager', label: '现场经理', tag: '' },
  { value: 'auditor', label: '审计员', tag: 'info' },
  { value: 'qc', label: '质量控制复核人', tag: 'success' },
  { value: 'eqcr', label: 'EQCR技术复核人', tag: 'primary' },
] as const

const ROLE_MAP = Object.fromEntries(ROLE_OPTIONS.map(o => [o.value, o]))

// 角色显示
function roleLabel(role: string): string {
  return ROLE_MAP[role]?.label || role
}
function roleTagType(role: string): string {
  return ROLE_MAP[role]?.tag || 'info'
}

// 表单校验
const userFormRef = ref<FormInstance>()
const userFormRules = computed<FormRules>(() => ({
  username: [
    rules.required('用户名'),
    { min: 2, max: 50, message: '长度 2-50 字符', trigger: 'blur' },
  ],
  email: makeRules('邮箱', rules.email),
  password: editingUser.value
    ? []
    : [
        rules.required('密码'),
        { min: 6, max: 64, message: '长度 6-64 字符', trigger: 'blur' },
      ],
  role: [rules.required('角色', 'change')],
}))
const { submit: submitUserForm, submitting: userSubmitting } = useFormSubmit(userFormRef)

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

function onDialogClosed() {
  editingUser.value = null
  form.value = { username: '', email: '', password: '', role: 'auditor' }
}

async function saveUser() {
  await submitUserForm(async () => {
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
  })
}

onMounted(loadUsers)
</script>

<style scoped>
.gt-users {
  padding: 20px 24px;
  max-width: 1200px;
}

/* 标题行右侧按钮：推到最右，不被 banner 的 column 布局拉伸 */
.gt-users-header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
}

.gt-users-header-actions :deep(.el-button) {
  background: rgba(255, 255, 255, 0.95);
  color: var(--el-color-primary);
  border: none;
  font-weight: 600;
}

.gt-users-header-actions :deep(.el-button:hover) {
  background: #fff;
  color: var(--el-color-primary);
}

.gt-users-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.gt-users-count {
  margin-left: auto;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.gt-users-card {
  border-radius: 8px;
}

.gt-users-card :deep(.el-card__body) {
  padding: 0;
}

/* 表格字号统一 13px */
.gt-users-card :deep(.el-table) {
  font-size: 13px;
}

.gt-users-card :deep(.el-table th) {
  font-size: 13px;
}

.gt-user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.gt-user-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
}
</style>
