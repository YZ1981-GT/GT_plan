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
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="人员档案" min-width="180">
          <template #default="{ row }">
            <div class="gt-staff-binding-cell">
              <span v-if="bindingLoadFailed" class="gt-staff-binding-empty">加载失败</span>
              <template v-else-if="bindingsFor(row.id).length">
                <span v-for="binding in bindingsFor(row.id)" :key="binding.staff_id" class="gt-staff-binding-item">
                  <span>{{ bindingLabel(binding) }}</span>
                  <el-button link type="danger" size="small" @click="unbindStaff(row, binding)" v-permission="'admin'">解除</el-button>
                </span>
              </template>
              <template v-else>
                <span class="gt-staff-binding-empty">未绑定</span>
                <el-button
                  link type="primary" size="small" :disabled="!row.is_active"
                  @click="openStaffBinding(row)" v-permission="'admin'"
                >绑定</el-button>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="editUser(row)" v-permission="'admin'">编辑</el-button>
            <el-button link type="primary" size="small" @click="openResetPassword(row)" v-permission="'admin'">重置密码</el-button>
            <!-- 不能停用自己（后端同样拒绝） -->
            <el-button
              v-if="row.id !== currentUserId"
              link size="small" :type="row.is_active ? 'danger' : 'success'"
              @click="toggleActive(row)" v-permission="'admin'"
            >{{ row.is_active ? '停用' : '启用' }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="gt-users-card gt-grants-card">
      <template #header>
        <div class="gt-grants-header">
          <div>
            <strong>经理建项授权</strong>
            <span>现场经理仅可为已授权的精确统一社会信用代码建项</span>
          </div>
          <el-button type="primary" plain @click="openGrantDialog" v-permission="'admin'">新增授权</el-button>
        </div>
      </template>
      <el-alert
        v-if="grantLoadError"
        class="gt-grants-error"
        type="error"
        :title="grantLoadError"
        :closable="false"
        show-icon
      >
        <el-button link type="primary" :loading="grantLoading" @click="loadGrants">重新加载</el-button>
      </el-alert>
      <el-table
        :data="grants"
        v-loading="grantLoading"
        style="width: 100%"
        row-key="id"
        :empty-text="grantLoadError ? '授权列表加载失败' : '暂无经理建项授权'"
      >
        <el-table-column prop="manager_username" label="现场经理" min-width="130" />
        <el-table-column prop="company_code" label="统一社会信用代码" min-width="190" />
        <el-table-column label="有效期" min-width="150">
          <template #default="{ row }">{{ row.valid_until ? fmtDate(row.valid_until) : '长期有效' }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="授权原因" min-width="200" show-overflow-tooltip />
        <el-table-column prop="granted_by_username" label="授权人" min-width="110" />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="grantStatus(row.status).tag" size="small">
              {{ grantStatus(row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="revokeGrant(row)" v-permission="'admin'">撤销</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog append-to-body v-model="grantDialog.visible" title="新增经理建项授权" width="520px" @closed="resetGrantDialog">
      <el-form ref="grantFormRef" :model="grantDialog" :rules="grantFormRules" label-width="110px">
        <el-form-item label="现场经理" prop="managerUserId">
          <el-select v-model="grantDialog.managerUserId" filterable placeholder="选择已启用的现场经理" style="width: 100%">
            <el-option v-for="manager in activeManagers" :key="manager.id" :label="manager.username" :value="manager.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="企业代码" prop="companyCodes">
          <el-input v-model="grantDialog.companyCodes" type="textarea" :rows="4" placeholder="输入18位统一社会信用代码；多个代码用换行或逗号分隔" />
        </el-form-item>
        <el-form-item label="有效期至">
          <el-date-picker v-model="grantDialog.validUntil" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" placeholder="留空表示长期有效" style="width: 100%" />
        </el-form-item>
        <el-form-item label="授权原因" prop="reason">
          <el-input v-model="grantDialog.reason" type="textarea" :rows="2" maxlength="500" show-word-limit placeholder="说明客户承接或授权依据" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grantDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="grantSaving" @click="submitGrant">确认授权</el-button>
      </template>
    </el-dialog>

    <!-- 新增/编辑弹窗 -->
    <el-dialog append-to-body v-model="showCreate" :title="editingUser ? '编辑用户' : '新增用户'" width="450px" @closed="onDialogClosed">
      <el-form ref="userFormRef" :model="form" :rules="userFormRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <!-- 用户名是登录名，历史记录都认它，建好后不能改 -->
          <el-input v-model="form.username" placeholder="请输入用户名" :disabled="!!editingUser" />
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

    <!-- 重置密码 -->
    <el-dialog append-to-body v-model="resetDialog.visible" :title="`重置密码：${resetDialog.username}`" width="420px"
      @closed="onResetClosed">
      <el-form ref="resetFormRef" :model="resetDialog" :rules="resetRules" label-width="80px">
        <el-form-item label="新密码" prop="password">
          <el-input v-model="resetDialog.password" type="password" show-password placeholder="8-64 位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="resetDialog.confirm" type="password" show-password placeholder="再输一遍" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="submitResetPassword" :loading="resetSubmitting">确定</el-button>
      </template>
    </el-dialog>

    <StaffBindingDialog
      v-model="staffBindingDialog.visible"
      :user="staffBindingDialog.user"
      @bound="loadStaffBindings"
      @stale="loadStaffBindings"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { listUsers, createUser, updateUser } from '@/services/commonApi'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import { rules, makeRules } from '@/utils/formRules'
import { useFormSubmit } from '@/composables/useFormSubmit'
import { buildUserUpdateBody } from '@/utils/userUpdateBody'
import { useAuthStore } from '@/stores/auth'
import { fmtDate } from '@/utils/formatters'
import {
  grantProjectCreation,
  listProjectCreationGrants,
  revokeProjectCreationGrant,
  type ProjectCreationGrant,
} from '@/services/projectCreationGrantApi'
import {
  listStaffBindings,
  unbindStaffFromUser,
  type StaffBinding,
} from '@/services/staffBindingApi'
import StaffBindingDialog from '@/components/system/StaffBindingDialog.vue'

const currentUserId = computed(() => useAuthStore().userId)

const users = ref<any[]>([])
const loading = ref(false)
const showCreate = ref(false)
const saving = ref(false)
const editingUser = ref<any>(null)
const form = ref({ username: '', email: '', password: '', role: 'auditor' })
const grants = ref<ProjectCreationGrant[]>([])
const grantLoading = ref(false)
const grantLoadError = ref('')
type GrantStatusView = { label: string; tag: 'success' | 'info' | 'warning' }
const GRANT_STATUS: Record<ProjectCreationGrant['status'], GrantStatusView> = {
  active: { label: '有效', tag: 'success' },
  expired: { label: '已过期', tag: 'info' },
  suspended: { label: '已暂停', tag: 'warning' },
}

function grantStatus(status: string): GrantStatusView {
  return GRANT_STATUS[status as ProjectCreationGrant['status']] ?? { label: '未知', tag: 'info' }
}
const grantSaving = ref(false)
const grantDialog = ref({
  visible: false,
  managerUserId: '',
  companyCodes: '',
  validUntil: null as string | null,
  reason: '',
})
const grantFormRef = ref<FormInstance>()
const grantFormRules: FormRules = {
  managerUserId: [rules.required('现场经理', 'change')],
  companyCodes: [rules.required('企业代码')],
  reason: [rules.required('授权原因')],
}

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

const activeManagers = computed(() => users.value.filter(
  user => user.role === 'manager' && user.is_active,
))

// 角色选项（单一来源，与后端 UserRole 枚举对齐；qc/eqcr 后端 permission_matrix 已支持）
const ROLE_OPTIONS = [
  { value: 'admin', label: '管理员', tag: 'danger' },
  { value: 'partner', label: '合伙人', tag: 'warning' },
  { value: 'manager', label: '现场经理', tag: '' },
  { value: 'auditor', label: '审计员', tag: 'info' },
  { value: 'qc', label: '质量控制复核人', tag: 'success' },
  { value: 'eqcr', label: 'EQCR技术复核人', tag: 'primary' },
  { value: 'readonly', label: '只读', tag: 'info' },
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
        { min: 8, max: 64, message: '长度 8-64 字符', trigger: 'blur' },
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

async function loadGrants() {
  grantLoading.value = true
  try {
    grants.value = await listProjectCreationGrants()
    grantLoadError.value = ''
  } catch {
    // 保留上次成功的数据，不能把读取失败显示成“没有授权”。
    grantLoadError.value = '经理建项授权加载失败，请稍后重新加载'
  } finally {
    grantLoading.value = false
  }
}

async function reloadUsersAndGrants() {
  await Promise.all([loadUsers(), loadGrants(), loadStaffBindings()])
}

// ── 人员档案绑定 ──
const staffBindings = ref<StaffBinding[]>([])
const bindingLoadFailed = ref(false)
const staffBindingDialog = ref<{ visible: boolean; user: { id: string; username: string } | null }>({
  visible: false,
  user: null,
})

const bindingsByUser = computed(() => {
  const grouped = new Map<string, StaffBinding[]>()
  for (const binding of staffBindings.value) {
    const list = grouped.get(binding.user_id) || []
    list.push(binding)
    grouped.set(binding.user_id, list)
  }
  return grouped
})

function bindingsFor(userId: string): StaffBinding[] {
  return bindingsByUser.value.get(userId) || []
}

function bindingLabel(binding: StaffBinding): string {
  return binding.employee_no ? `${binding.staff_name}（${binding.employee_no}）` : binding.staff_name
}

let bindingLoadSeq = 0
async function loadStaffBindings() {
  // 绑定 / 解除后会连续重读；只采用最后一次请求的结果，慢的旧响应不覆盖新状态。
  const seq = ++bindingLoadSeq
  try {
    const rows = await listStaffBindings()
    if (seq !== bindingLoadSeq) return
    staffBindings.value = rows
    bindingLoadFailed.value = false
  } catch {
    if (seq !== bindingLoadSeq) return
    // 读取失败不能显示成“未绑定”，否则管理员会重复绑定。
    bindingLoadFailed.value = true
  }
}

function openStaffBinding(row: any) {
  staffBindingDialog.value = { visible: true, user: { id: row.id, username: row.username } }
}

async function unbindStaff(row: any, binding: StaffBinding) {
  try {
    await ElMessageBox.confirm(
      `解除账号「${row.username}」与人员档案「${bindingLabel(binding)}」的绑定？`
        + '解除后该账号不再通过此人员档案获得项目委派权限。',
      '解除人员档案绑定',
      { type: 'warning', confirmButtonText: '解除绑定', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await unbindStaffFromUser(row.id, binding.staff_id)
    ElMessage.success('已解除人员档案绑定')
  } catch {
    // 原因（如该人员仍在项目团队中）由请求拦截器展示。
  }
  await loadStaffBindings()
}

function openGrantDialog() {
  resetGrantDialog()
  grantDialog.value.visible = true
}

function resetGrantDialog() {
  grantDialog.value = {
    visible: false, managerUserId: '', companyCodes: '', validUntil: null, reason: '',
  }
}

function parsedGrantCodes(): string[] {
  return [...new Set(grantDialog.value.companyCodes
    .split(/[\s,，;；]+/)
    .map(value => value.trim().toUpperCase())
    .filter(Boolean))]
}

async function submitGrant() {
  const codes = parsedGrantCodes()
  if (!grantDialog.value.managerUserId) {
    ElMessage.error('请选择现场经理')
    return
  }
  if (!codes.length || codes.some(code => !/^[0-9A-HJ-NPQRTUWXY]{18}$/.test(code))) {
    ElMessage.error('请输入有效的18位统一社会信用代码')
    return
  }
  if (grantDialog.value.reason.trim().length < 3) {
    ElMessage.error('请填写至少3个字符的授权原因')
    return
  }
  try {
    await grantFormRef.value?.validate()
  } catch {
    return
  }
  const managerName = activeManagers.value.find(
    manager => manager.id === grantDialog.value.managerUserId,
  )?.username || '所选现场经理'
  try {
    await ElMessageBox.confirm(
      `确认授予「${managerName}」${codes.length} 个企业代码的建项权限？`,
      '确认经理建项授权',
      { type: 'warning', confirmButtonText: '确认授权', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  grantSaving.value = true
  try {
    await grantProjectCreation(grantDialog.value.managerUserId, {
      company_codes: codes,
      valid_until: grantDialog.value.validUntil,
      reason: grantDialog.value.reason.trim(),
    })
    ElMessage.success(`已授权 ${codes.length} 个企业代码`)
    grantDialog.value.visible = false
    await loadGrants()
  } catch { /* 请求拦截器已展示后端原因 */ }
  finally {
    grantSaving.value = false
  }
}

async function revokeGrant(grant: ProjectCreationGrant) {
  try {
    const result = await ElMessageBox.prompt(
      `撤销「${grant.manager_username}」对 ${grant.company_code} 的建项授权？`,
      '撤销经理建项授权',
      {
        type: 'warning', confirmButtonText: '撤销', cancelButtonText: '取消',
        inputPlaceholder: '填写撤销原因（至少3个字符）',
        inputValidator: value => value.trim().length >= 3 || '撤销原因至少3个字符',
      },
    )
    await revokeProjectCreationGrant(grant.id, grant.version, result.value.trim())
    ElMessage.success('建项授权已撤销')
    await loadGrants()
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    // 失败原因由全局拦截器展示；版本冲突等情况需要刷新到服务端当前状态。
    await loadGrants()
  }
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
        // 只发改了的字段：用户名不可改、密码走「重置密码」（后端多余字段直接 422）
        const body = buildUserUpdateBody(editingUser.value, form.value)
        if (!Object.keys(body).length) {
          ElMessage.info('没有改动')
          showCreate.value = false
          return
        }
        await updateUser(editingUser.value.id, body)
      } else {
        await createUser(form.value)
      }
      ElMessage.success('保存成功')
      showCreate.value = false
      editingUser.value = null
      // 角色变化会让经理建项授权暂停或恢复，两张表同口径刷新。
      await reloadUsersAndGrants()
    } catch { /* 原因已由请求拦截器提示（如邮箱已被其他用户使用） */ }
    finally { saving.value = false }
  })
}

// 启用 / 停用：二次确认；不能停用自己、至少保留一个启用的管理员由后端判（拦截器提示原因）
async function toggleActive(row: any) {
  const enable = !row.is_active
  try {
    await ElMessageBox.confirm(
      enable ? `确定启用「${row.username}」？` : `确定停用「${row.username}」？停用后该账号不能登录。`,
      enable ? '启用账号' : '停用账号',
      { type: 'warning', confirmButtonText: enable ? '启用' : '停用', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await updateUser(row.id, { is_active: enable })
    ElMessage.success(enable ? '已启用' : '已停用')
    await reloadUsersAndGrants()
  } catch { /* 原因已由请求拦截器提示 */ }
}

// 重置密码：只发 password（8-64 位，与后端 UserUpdate 同一下限；两次一致）
const resetFormRef = ref<FormInstance>()
const resetDialog = ref({ visible: false, userId: '', username: '', password: '', confirm: '' })
const resetRules: FormRules = {
  password: [rules.required('新密码'), { min: 8, max: 64, message: '长度 8-64 字符', trigger: 'blur' }],
  confirm: [
    rules.required('确认密码'),
    {
      validator: (_rule, value, callback) =>
        value === resetDialog.value.password ? callback() : callback(new Error('两次输入的密码不一致')),
      trigger: 'blur',
    },
  ],
}
const { submit: submitResetForm, submitting: resetSubmitting } = useFormSubmit(resetFormRef)

function openResetPassword(row: any) {
  resetDialog.value = { visible: true, userId: row.id, username: row.username, password: '', confirm: '' }
}

function onResetClosed() {
  resetDialog.value = { visible: false, userId: '', username: '', password: '', confirm: '' }
}

async function submitResetPassword() {
  await submitResetForm(async () => {
    try {
      await updateUser(resetDialog.value.userId, { password: resetDialog.value.password })
      ElMessage.success(`已重置「${resetDialog.value.username}」的密码`)
      resetDialog.value.visible = false
    } catch { /* 原因已由请求拦截器提示 */ }
  })
}

onMounted(() => {
  void reloadUsersAndGrants()
})
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

.gt-staff-binding-cell { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }
.gt-staff-binding-item { display: inline-flex; align-items: center; gap: 4px; }
.gt-staff-binding-empty { color: var(--el-text-color-secondary); }
.gt-grants-card { margin-top: 16px; }
.gt-grants-error { margin: 12px; width: auto; }
.gt-grants-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.gt-grants-header > div { display: flex; min-width: 0; flex-direction: column; gap: 4px; }
.gt-grants-header span { color: var(--el-text-color-secondary); font-size: 12px; }

@media (max-width: 680px) {
  .gt-users { padding: 12px; }
  .gt-users-filter { align-items: stretch; flex-direction: column; }
  .gt-users-filter :deep(.el-input), .gt-users-filter :deep(.el-select) { width: 100% !important; }
  .gt-users-count { margin-left: 0; }
  .gt-grants-header { align-items: stretch; flex-direction: column; }
}
</style>
