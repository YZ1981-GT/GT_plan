<template>
  <div class="dept-page">
    <GtPageHeader title="部门管理">
      <template #actions>
        <el-button type="primary" :icon="Plus" @click="openCreate">新增部门</el-button>
        <el-button :icon="Refresh" @click="loadData">刷新</el-button>
      </template>
    </GtPageHeader>

    <el-card shadow="never" class="dept-card">
      <el-table :data="departments" v-loading="loading" border style="width: 100%">
        <el-table-column prop="name" label="部门名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="部门负责人" width="140">
          <template #default="{ row }">
            <span v-if="row.head_name">{{ row.head_name }}</span>
            <span v-else class="gt-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="上级部门" width="140">
          <template #default="{ row }">
            <span v-if="deptName(row.parent_id)">{{ deptName(row.parent_id) }}</span>
            <span v-else class="gt-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="70" align="center" />
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑部门' : '新增部门'" width="480px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="部门名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入部门名称（唯一）" />
        </el-form-item>
        <el-form-item label="部门负责人" prop="head_id">
          <el-select
            v-model="form.head_id"
            placeholder="请选择部门负责人（合伙人）"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.id"
              :label="u.full_name ? `${u.full_name}（${u.username}）` : u.username"
              :value="u.id"
            />
            <template #footer>
              <el-button text type="primary" :icon="Plus" @click="openCreatePartner">新建合伙人</el-button>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="上级部门" prop="parent_id">
          <el-select v-model="form.parent_id" placeholder="请选择上级部门（可选）" clearable style="width: 100%">
            <el-option v-for="d in parentOptions" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="部门描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <!--
      内联「新建合伙人」弹窗：解「建部门要选负责人、负责人还没建」的鸡生蛋。
      append-to-body + destroy-on-close，嵌在部门弹窗之上；保存成功后刷新用户列表
      并自动把新合伙人选进部门表单的 head_id。
    -->
    <el-dialog
      v-model="partnerDialogVisible"
      title="新建合伙人"
      width="440px"
      append-to-body
      destroy-on-close
    >
      <el-form ref="partnerFormRef" :model="partnerForm" :rules="partnerRules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="partnerForm.username" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item label="全名" prop="full_name">
          <el-input v-model="partnerForm.full_name" placeholder="合伙人姓名" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="partnerForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="partnerForm.password" type="password" show-password placeholder="8~64 位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="partnerDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="partnerSaving" @click="submitPartner">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import {
  listDepartments,
  createDepartment,
  updateDepartment,
  deleteDepartment,
  listUsers,
  createUser,
} from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'

const departments = ref<any[]>([])
const users = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref<FormInstance>()
const editingId = ref<string | null>(null)

const form = ref<any>({ name: '', head_id: null, parent_id: null, sort_order: 0, description: '' })

const rules: FormRules = {
  name: [{ required: true, message: '请输入部门名称', trigger: 'blur' }],
  head_id: [{ required: true, message: '请选择部门负责人', trigger: 'change' }],
}

// 部门负责人候选：仅合伙人角色
const userOptions = computed(() => users.value.filter(u => u.role === 'partner'))

// ── 内联新建合伙人 ──
const partnerDialogVisible = ref(false)
const partnerSaving = ref(false)
const partnerFormRef = ref<FormInstance>()
const partnerForm = ref<any>({ username: '', full_name: '', email: '', password: '' })

const partnerRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  full_name: [{ required: true, message: '请输入全名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度 6~64 位', trigger: 'blur' },
  ],
}

function openCreatePartner() {
  partnerForm.value = { username: '', full_name: '', email: '', password: '' }
  partnerDialogVisible.value = true
}

async function submitPartner() {
  if (!partnerFormRef.value) return
  await partnerFormRef.value.validate(async (valid) => {
    if (!valid) return
    partnerSaving.value = true
    try {
      const created = await createUser({ ...partnerForm.value, role: 'partner' })
      ElMessage.success('合伙人已创建')
      // 刷新用户列表，并把新建合伙人选进部门表单
      users.value = await listUsers()
      if (created?.id) form.value.head_id = created.id
      partnerDialogVisible.value = false
    } catch (e) {
      handleApiError(e, '创建合伙人')
    } finally {
      partnerSaving.value = false
    }
  })
}

// 上级部门候选：排除自身（后端防"自己当自己上级"；子部门成环由后端 400 兜底）
const parentOptions = computed(() => departments.value.filter(d => d.id !== editingId.value))

function deptName(id: string | null): string {
  if (!id) return ''
  return departments.value.find(d => d.id === id)?.name || ''
}

function fmtTime(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function loadData() {
  loading.value = true
  try {
    const [depts, usrs] = await Promise.all([listDepartments(), listUsers()])
    departments.value = depts
    users.value = usrs
  } catch (e) {
    handleApiError(e, '加载部门列表')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  isEdit.value = false
  editingId.value = null
  form.value = { name: '', head_id: null, parent_id: null, sort_order: 0, description: '' }
  dialogVisible.value = true
}

function openEdit(row: any) {
  isEdit.value = true
  editingId.value = row.id
  form.value = {
    name: row.name || '',
    head_id: row.head_id || null,
    parent_id: row.parent_id || null,
    sort_order: row.sort_order ?? 0,
    description: row.description || '',
  }
  dialogVisible.value = true
}

async function submit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      if (isEdit.value && editingId.value) {
        await updateDepartment(editingId.value, { ...form.value })
        ElMessage.success('部门已更新')
      } else {
        await createDepartment({ ...form.value })
        ElMessage.success('部门已创建')
      }
      dialogVisible.value = false
      await loadData()
    } catch (e) {
      handleApiError(e, isEdit.value ? '更新部门' : '创建部门')
    } finally {
      saving.value = false
    }
  })
}

async function remove(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除部门「${row.name}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteDepartment(row.id)
    ElMessage.success('部门已删除')
    await loadData()
  } catch (e) {
    handleApiError(e, '删除部门')
  }
}

onMounted(loadData)
</script>

<style scoped>
.dept-page {
  padding: 12px 16px;
}

.dept-card {
  margin-top: 12px;
}
</style>
