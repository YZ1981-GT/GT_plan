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
        <el-table-column prop="full_name" label="全名" min-width="120">
          <template #default="{ row }">
            <span style="color: var(--el-text-color-secondary)">{{ row.full_name || '-' }}</span>
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
        <el-table-column label="操作" width="140" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="editUser(row)" v-permission="'admin'">编辑</el-button>
            <!--
              删除按钮：**禁用当前登录账号自己那一行**。
              后端也有同一条守卫（删自己会让本次会话立即 401），此处前置禁用是
              为了别让用户点完才被告知不行；两处都留，勿只留一处。
            -->
            <el-button
              link
              type="danger"
              size="small"
              :disabled="row.id === currentUserId"
              :loading="deletingId === row.id"
              :title="row.id === currentUserId ? '不能删除当前登录的账号' : ''"
              @click="confirmDeleteUser(row)"
              v-permission="'admin'"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!--
      用户 → 项目 → 角色 三层树（project-data-permission-isolation Task 6.3）

      🔴 **用 `v-if="isAdmin"` 而非 `v-permission="'admin'"`**：
         `v-permission` 是**按钮级**指令（本页第 6/66 行那两处），它在元素已
         渲染后再隐藏；而本组件在 mount 时就会发起 `/users` 请求 ⇒ 非 admin
         账号会打出一个必然 403 的请求，在控制台留下噪声、也白占一次往返。
         `v-if` 才能真正阻止组件创建（Req 4.7 要求"不渲染树形组件"）。
    -->
    <!--
      🔴 **必须额外挂 `gt-users-tree-card`**：`gt-users-card` 带一条
         `:deep(.el-card__body){padding:0}` —— 那是为**表格**卡片写的
         （el-table 自带边距，留 padding 会双层留白）。树卡片复用同一个类
         会被一并清零 ⇒ 工具栏与树节点**贴着卡片左右边缘**，而同卡片的
         header 仍是 20px ⇒ 标题缩进、内容贴边，两者错位（实测 body
         padding=0 vs header padding=20px；工具栏左边界与刷新按钮右边界
         分别等于卡片左右边界）。这个补丁类把 body 的 padding 还原回来。
    -->
    <el-card v-if="isAdmin" shadow="never" class="gt-users-card gt-users-tree-card">
      <template #header>
        <span style="font-weight: 600">用户项目角色分布</span>
      </template>
      <UserProjectRoleTree />
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog append-to-body v-model="showCreate" :title="editingUser ? '编辑用户' : '新增用户'" width="450px" @closed="onDialogClosed">
      <!-- label-width 90px：「所属合伙人」5 字在 80px 下会折成两行（截图实证） -->
      <el-form ref="userFormRef" :model="form" :rules="userFormRules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="全名" prop="full_name">
          <el-input v-model="form.full_name" placeholder="请输入用户全名" />
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
        <el-form-item label="所属部门" prop="dept_id">
          <el-select v-model="form.dept_id" placeholder="请选择部门（可选）" clearable style="width: 100%" :loading="deptLoading">
            <el-option v-for="dept in deptOptions" :key="dept.id" :label="dept.name" :value="dept.id" />
          </el-select>
        </el-form-item>
        <!-- 上级合伙人：仅 manager / auditor 两类角色展示（Requirement 3.4）。
             业务语义上只有这两类账号会挂靠某个 partner，DB 不加角色约束，由前端门控。 -->
        <el-form-item v-if="showParentPartner" label="所属合伙人" prop="parent_partner_id">
          <el-select v-model="form.parent_partner_id" placeholder="请选择合伙人（可选）" clearable filterable style="width: 100%">
            <el-option
              v-for="partner in partnerOptions"
              :key="partner.id"
              :label="userLabel(partner)"
              :value="partner.id"
            />
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
import { ref, computed, watch, onMounted, h } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { listUsers, createUser, updateUser, deleteUser, listDepartments } from '@/services/commonApi'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import UserProjectRoleTree from '@/components/system/UserProjectRoleTree.vue'
import { useAuthStore } from '@/stores/auth'
import { rules, makeRules } from '@/utils/formRules'
import { useFormSubmit } from '@/composables/useFormSubmit'
import { handleApiError } from '@/utils/errorHandler'

// 三层树的门控（Req 4.7）。与 SystemSettings.vue / ReportConfigBaselineTab.vue
// 同一写法 —— 复用既有判定而非另起一套，避免两处口径漂移。
const authStore = useAuthStore()
const isAdmin = computed(() => (authStore.user?.role || '') === 'admin')

// 当前登录账号的 id：用于禁用「删除自己」那一行的按钮。
// 走 store 的 userId getter（`user?.id ?? ''`），不另读 sessionStorage —— 
// 后者是 store 的持久化载体而非真源，两处读会在 token 刷新后口径漂移。
const currentUserId = computed(() => authStore.userId)

const users = ref<any[]>([])
const loading = ref(false)
const showCreate = ref(false)
const saving = ref(false)
const editingUser = ref<any>(null)
const form = ref({ username: '', email: '', password: '', role: 'auditor', full_name: '', parent_partner_id: null, dept_id: null })

// 部门列表
const departments = ref<any[]>([])
const deptLoading = ref(false)

// 合伙人候选 = 已加载用户列表中 role=partner 的项，直接从 users 派生。
// 🔴 不可改回二次请求 /api/users/：两个并发同键 GET 会被 utils/http.ts 的去重逻辑
// 互杀（先发的被 abort），导致 loadUsers 落入 catch、用户表恒为空。
const partnerUsers = computed(() => users.value.filter((u: any) => u.role === 'partner'))

// 人员下拉统一展示口径：**优先全名**，全名缺失（V149 之前建的历史账号）才回落用户名。
// 与 BasicInfoStep.vue 的 userLabel() 同一形态 —— 审计师认的是人名不是登录名，
// 下拉里给 username 会让「张三」变成「zhang_san」这类需要二次翻译的文案。
function userLabel(u: any): string {
  return u?.full_name || u?.username || ''
}

// 兜底：待编辑用户的 parent_partner_id 不在候选集内时（该合伙人已停用，或当前账号为
// partner、按 V153 隔离只能看到自己的下属+本人），补一个临时选项，
// 避免 el-select 未命中 option 时把裸 UUID 显示给用户。
// 只给 username 即可 —— userLabel() 的 `full_name || username` 回落会接住它。
const partnerOptions = computed(() => {
  const list = partnerUsers.value
  const cur = form.value.parent_partner_id
  if (cur && !list.some((u: any) => u.id === cur)) {
    return [...list, { id: cur, username: '（当前不可见的合伙人）' }]
  }
  return list
})

// 同上，部门列表为异步加载，冷启动或部门已停用时同样不得暴露裸 UUID。
const deptOptions = computed(() => {
  const list = departments.value
  const cur = form.value.dept_id
  if (cur && !list.some((d: any) => d.id === cur)) {
    return [...list, { id: cur, name: deptLoading.value ? '加载中…' : '（当前不可见的部门）' }]
  }
  return list
})

// 「上级合伙人」适用角色（account-field-completion Requirement 3.4）。
// 单一真源：门控与切换清空共用这一个集合，勿在别处另写一份角色列表。
//
// 🔴 site_lead（现场经理）必须在列（spec site-lead-and-field-lead）：
//    该 spec 的签字合伙人→下属级联（R4.2）是按 `parent_partner_id === signing_partner_id`
//    筛候选人的。若界面永远无法给 site_lead 账号设置上级合伙人，
//    site_lead 就**永远不会出现在项目经理/现场负责人候选名单里** ——
//    表现为「建了现场经理账号却选不到他」，而不是任何报错。
//    参考实现 zt-gt-plan 同样是 ['manager','site_lead','auditor']。
const PARENT_PARTNER_ROLES = ['manager', 'site_lead', 'auditor'] as const

const showParentPartner = computed(() =>
  (PARENT_PARTNER_ROLES as readonly string[]).includes(form.value.role)
)

// 角色切换到不适用的角色时清空已选上级合伙人 —— 否则字段虽被隐藏，
// 旧值仍会随表单提交到后端，写出「partner 账号挂着上级合伙人」这类越界数据。
watch(() => form.value.role, () => {
  if (!showParentPartner.value) form.value.parent_partner_id = null
})

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
//
// ⚠️ manager=「项目经理」、site_lead=「现场经理」是**两个不同角色**（权限相同、
//    可填不同的人）。两个中文名不可互换 —— manager 曾叫「现场经理」，2026-08-26
//    改名为「项目经理」正是为了把「现场经理」这个名字腾给 site_lead。
const ROLE_OPTIONS = [
  { value: 'admin', label: '管理员', tag: 'danger' },
  { value: 'partner', label: '合伙人', tag: 'warning' },
  { value: 'manager', label: '项目经理', tag: '' },
  // site_lead：独立系统角色，权限等同 manager（后端走 ROLE_ALIAS_MAP 别名）
  { value: 'site_lead', label: '现场经理', tag: '' },
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
  // 全名必填：合伙人/项目经理等下拉一律按全名展示（userLabel），
  // 全名为空的账号在那些下拉里只能回落成登录名 ⇒ 从建号入口起就要求填写。
  //
  // 后端 UserCreate/UserUpdate 的 full_name 已同步收紧为必填（含 strip 后判长，
  // 空白串挡在 422），故此处不是唯一防线，而是「早报错、少一次往返」。
  // ⚠️ UserResponse.full_name 刻意保持可空 —— 库里仍有历史账号为 NULL，读模型
  //    一起收紧会让「查看历史账号」直接 500。编辑那些账号时会被强制顺手补全名。
  full_name: [
    rules.required('全名'),
    { min: 2, max: 100, message: '长度 2-100 字符', trigger: 'blur' },
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
  } catch (e: any) {
    // 请求被去重逻辑取消时不清空已有行集，否则表格会闪成空表
    if (!axios.isCancel(e)) users.value = []
  }
  finally { loading.value = false }
}

async function loadDepartments() {
  deptLoading.value = true
  try {
    departments.value = await listDepartments()
  } catch { departments.value = [] }
  finally { deptLoading.value = false }
}

function editUser(row: any) {
  editingUser.value = row
  form.value = {
    username: row.username,
    email: row.email,
    password: '',
    role: row.role,
    full_name: row.full_name || '',
    parent_partner_id: row.parent_partner_id || null,
    dept_id: row.dept_id || null,
  }
  showCreate.value = true
}

function onDialogClosed() {
  editingUser.value = null
  form.value = { username: '', email: '', password: '', role: 'auditor', full_name: '', parent_partner_id: null, dept_id: null }
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

// 删除中的行 id：只给正在删的那一行按钮转圈，避免整表 loading 闪烁
const deletingId = ref('')

async function confirmDeleteUser(row: any) {
  // 与后端守卫 1 对齐的前置拦截（按钮已 disabled，这里是双保险）
  if (row.id === currentUserId.value) return

  // 🔴 用 h() 构建 VNode 而非 `\n` 拼字符串：ElMessageBox 默认按纯文本渲染，
  //    而全仓无 `white-space: pre-line` 样式 ⇒ `\n` 会被折叠成空格，多行提示
  //    会挤成一大段（TrialBalance.vue 那几处确认框正是这个状态）。
  //    也不用 dangerouslyUseHTMLString —— 那需要手工转义 username，
  //    而 h() 的文本子节点由 Vue 自动转义，没有 XSS 面。
  const message = h('div', { style: 'line-height: 1.7' }, [
    h('p', { style: 'margin: 0 0 8px' }, [
      '确认删除账号「',
      h('strong', null, userLabel(row) || row.username),
      `」（${row.username}）？`,
    ]),
    h('ul', { style: 'margin: 0; padding-left: 18px; color: var(--el-text-color-regular)' }, [
      h('li', null, '该账号将立即无法登录，已登录的会话下一次请求即失效'),
      h('li', null, '其项目成员身份会一并移除'),
      h('li', null, '已编制/复核的底稿留痕保留不变（审计追溯要求）'),
      // 2026-08-27 改：V160 把用户名/邮箱唯一性收窄为「仅未删除账号」，
      // 且无业务引用的账号会被物理删除 ⇒ 删完可以立刻用同一个用户名重建。
      // 原文案写的「用户名/邮箱也不能再被新账号使用」已不成立，留着会让
      // 管理员以为名字废了、去起一堆 zhangsan2 之类的账号。
      h('li', null, '删除后可以用同一个用户名/邮箱重新创建账号'),
      h('li', null, '删除本身不可撤销（不进回收站），请确认无误'),
    ]),
  ])

  try {
    await ElMessageBox.confirm(message, '删除用户', {
      type: 'warning',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger',
    })
  } catch {
    return  // 用户取消
  }

  deletingId.value = row.id
  try {
    // 后端返回 { hard_deleted }：无业务引用时物理删除、有引用时软删保留留痕。
    // 两种情况用户名都已释放，但提示要说清区别 —— 管理员需要知道"留痕还在"。
    const res = await deleteUser(row.id)
    ElMessage.success(
      res?.hard_deleted
        ? '已彻底删除，该用户名/邮箱可立即重新使用'
        : '已删除（该账号有业务留痕，记录保留以备审计追溯），用户名/邮箱可重新使用',
    )
    await loadUsers()
  } catch (e: any) {
    // 后端四类 400 拒绝（删自己 / 最后一个 admin / 有下属挂靠 / 仍是活跃项目
    // 负责人）的 detail 里带「下一步怎么做」，handleApiError 的 400 分支会
    // 原样展示该字符串 ⇒ 此处不要自己拼文案，否则会盖掉后端的可执行指引。
    handleApiError(e, '删除用户')
  } finally {
    deletingId.value = ''
  }
}

onMounted(() => {
  loadUsers()
  loadDepartments()
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

/* 表格卡片：body 不留 padding（el-table 自带边距，留了会双层留白） */
.gt-users-card :deep(.el-card__body) {
  padding: 0;
}

/*
  树卡片补丁：把上一条清零的 padding 还原。
  取 16px 20px —— 横向与同卡片 header 的 20px 对齐（否则标题缩进、内容贴边）。
  选择器写两个类叠加，特异性 (0,2,0) > 上一条的 (0,1,0)，且与 :deep 同层，
  故无需 !important。
*/
.gt-users-card.gt-users-tree-card :deep(.el-card__body) {
  padding: 16px 20px;
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
